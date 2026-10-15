"""Concurrency test (CC-01..CC-03): 50 simultaneous requests. Start mock_server.py first."""

import time
from concurrent.futures import ThreadPoolExecutor, wait

from contextcheck import Executor, TestScenario
from contextcheck.endpoints.endpoint_config import EndpointConfig
from contextcheck.endpoints.factory import factory
from contextcheck.models.request import RequestBase

N = 50
URL = "http://127.0.0.1:8765/echo?delay=0.2"


def run_parallel(fn):
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N) as pool:
        futures = [pool.submit(fn, i) for i in range(N)]
        done, not_done = wait(futures, timeout=30)
    results = [f.result() for f in done]
    return results, len(not_done), time.perf_counter() - start


def independent(i):
    scenario = TestScenario.model_validate(
        {
            "config": {"endpoint_under_test": {"kind": "cc_ss", "url": URL}},
            "steps": [
                {
                    "name": f"s{i}",
                    "request": f"request-{i}",
                    "asserts": [{"kind": "equals", "assertion": f"request-{i}"}],
                }
            ],
        }
    )
    return Executor(scenario).run_all()


shared = factory(EndpointConfig(kind="cc_ss", url=URL))


def on_shared_endpoint(i):
    start = time.perf_counter()
    response = shared.send_request(RequestBase(message=f"request-{i}"))
    real = time.perf_counter() - start
    return response.message == f"request-{i}", response.stats.conn_duration, real


results, hung, elapsed = run_parallel(independent)
print(
    f"CC-01 independent executors: {sum(results)}/{N} passed, {hung} hung, {elapsed:.2f} s "
    f"(serial would take ~{N * 0.2:.0f} s)"
)

results, hung, elapsed = run_parallel(on_shared_endpoint)
correct = sum(ok for ok, _, _ in results)
wrong_time = sum(abs(d - real) > 0.2 * real for _, d, real in results)
print(f"CC-02 shared endpoint      : {correct}/{N} responses matched their request, {hung} hung")
print(f"CC-03 shared endpoint      : {wrong_time}/{N} responses report a wrong conn_duration")
