"""Concurrency safety: 50 simultaneous requests against a mock RAG API.

ContextCheck itself runs scenarios sequentially (see the TODO in TestsRouter.run_tests); these
tests check what happens when it is driven from several threads at once, e.g. by a parallel CI
runner or by a library user.
"""

import time
from concurrent.futures import ThreadPoolExecutor, wait

import pytest

from contextcheck import TestScenario
from contextcheck.endpoints.endpoint_config import EndpointConfig
from contextcheck.endpoints.factory import factory as endpoint_factory
from contextcheck.executors.executor import Executor
from contextcheck.models.request import RequestBase
from tests.mock_rag_server import run_mock_rag_server

N_REQUESTS = 50
DEADLOCK_TIMEOUT = 30  # seconds; serial execution would take ~N_REQUESTS * mean delay
DELAY = (0.05, 0.2)


@pytest.fixture
def rag():
    with run_mock_rag_server() as (base_url, state):
        state.delay = DELAY
        yield base_url, state


def run_concurrently(fn) -> tuple[list, float]:
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N_REQUESTS) as pool:
        futures = [pool.submit(fn, i) for i in range(N_REQUESTS)]
        done, not_done = wait(futures, timeout=DEADLOCK_TIMEOUT)
        assert not not_done, f"{len(not_done)} requests did not finish: possible deadlock"
    return [f.result() for f in futures], time.perf_counter() - start


def all_released(state, timeout: float = 2.0) -> bool:
    """Wait until the server has finished handling every request."""
    deadline = time.perf_counter() + timeout
    while state.active and time.perf_counter() < deadline:
        time.sleep(0.01)
    return state.active == 0


def test_50_concurrent_scenarios_with_independent_executors(rag):
    base_url, state = rag

    def run_scenario(i: int) -> bool:
        scenario = TestScenario.model_validate(
            {
                "config": {"endpoint_under_test": {"kind": "cc_ss", "url": f"{base_url}/echo"}},
                "steps": [
                    {
                        "name": f"step-{i}",
                        "request": f"request-{i}",
                        "asserts": [{"kind": "equals", "assertion": f"request-{i}"}],
                    }
                ],
            }
        )
        return Executor(scenario).run_all()

    results, elapsed = run_concurrently(run_scenario)

    assert all(results)
    assert state.requests == N_REQUESTS
    assert state.max_active > 1  # Requests really overlapped
    assert all_released(state)
    assert elapsed < N_REQUESTS * DELAY[0]  # Faster than the best possible serial run


def test_50_concurrent_requests_on_a_shared_endpoint(rag):
    base_url, state = rag
    endpoint = endpoint_factory(EndpointConfig(kind="cc_ss", url=f"{base_url}/echo"))

    def send(i: int) -> str:
        return endpoint.send_request(RequestBase(message=f"request-{i}")).message

    messages, _ = run_concurrently(send)

    # Every response belongs to its own request: no cross-talk between threads
    assert messages == [f"request-{i}" for i in range(N_REQUESTS)]
    assert state.max_active > 1
    assert all_released(state)


@pytest.mark.xfail(
    strict=True, reason="ConnectorBase.stats is shared mutable state between threads"
)
def test_connection_time_stats_on_a_shared_endpoint(rag):
    base_url, _ = rag
    endpoint = endpoint_factory(EndpointConfig(kind="cc_ss", url=f"{base_url}/echo"))

    def send(i: int) -> tuple[float | None, float]:
        start = time.perf_counter()
        response = endpoint.send_request(RequestBase(message=f"request-{i}"))
        return response.stats.conn_duration, time.perf_counter() - start

    results, _ = run_concurrently(send)

    wrong = [(d, real) for d, real in results if d is None or abs(d - real) > 0.2 * real]
    assert not wrong, f"{len(wrong)}/{N_REQUESTS} responses report a wrong conn_duration"
