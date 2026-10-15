"""SQA – Module Kết nối & Cấu hình (Connectors, Endpoints, Loaders, Models): TC-01 .. TC-10.

Tests marked `xfail(strict=True)` describe the expected behaviour of a defect that was found;
they turn into XPASS (and fail the suite) once the defect is fixed.
"""

from unittest.mock import patch

import pydantic
import pytest
import requests
import yaml

from contextcheck import TestScenario
from contextcheck.connectors.connector_http import ConnectorHTTP
from contextcheck.endpoints.endpoint_cc import EndpointCCConfig
from contextcheck.endpoints.endpoint_config import EndpointConfig
from contextcheck.endpoints.factory import factory as endpoint_factory
from contextcheck.executors.executor import Executor
from contextcheck.loaders.yaml import load_yaml_file
from contextcheck.models.request import RequestBase
from tests.sqa_http_stub import echo, fixed, run_stub, slow, status

OPENAI_CREATE = (
    "contextcheck.connectors.connector_openai_compatible.openai_compatible.chat.completions.create"
)
FAKE_COMPLETION = {
    "choices": [{"message": {"content": "ok"}}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
}


def http_scenario(url: str, steps: list) -> TestScenario:
    endpoint = {"kind": "tg_chatbot", "url": url, "additional_headers": {}}
    return TestScenario.model_validate(
        {"config": {"endpoint_under_test": endpoint}, "steps": steps}
    )


# --- TC-01: HTTP timeout ------------------------------------------------------------------------


def test_tc01_timeout_is_raised_without_retry():
    with run_stub({"/slow": slow(2)}) as (url, state):
        with pytest.raises(requests.Timeout):
            ConnectorHTTP(url=f"{url}/slow", timeout=1).send({"message": "hi"})

        assert len(state.hits("/slow")) == 1  # No retry


@pytest.mark.xfail(strict=True, reason="Endpoint config has no timeout; ConnectorHTTP uses 30 s")
def test_tc01_timeout_is_configurable_from_yaml():
    endpoint = endpoint_factory(
        EndpointConfig(kind="cc_prompt_llm", url="http://127.0.0.1:9/", timeout=5)
    )

    assert endpoint.connector.timeout == 5


@pytest.mark.xfail(strict=True, raises=requests.Timeout, reason="Timeout aborts the whole run")
def test_tc01_timeout_fails_step_and_run_continues():
    with run_stub({"/slow": slow(2), "/echo": echo}) as (url, state):
        executor = Executor(http_scenario(f"{url}/slow", ["first", "second"]))
        executor.endpoint_under_test.connector.timeout = 1

        assert executor.run_all() is False
        assert len(state.hits("/slow")) == 2


# --- TC-02: HTTP 4xx / 5xx ----------------------------------------------------------------------


@pytest.mark.parametrize("code", [400, 401, 404, 500, 503])
def test_tc02_http_errors_are_detected(code):
    with run_stub({"/err": status(code)}) as (url, _):
        endpoint = endpoint_factory(
            EndpointConfig(kind="tg_chatbot", url=f"{url}/err", additional_headers={})
        )

        with pytest.raises(requests.HTTPError, match=str(code)):
            endpoint.send_request(RequestBase(message="hi"))


@pytest.mark.xfail(strict=True, raises=requests.HTTPError, reason="HTTP errors abort the run")
def test_tc02_http_error_fails_step_and_run_continues():
    with run_stub({"/err": status(500)}) as (url, state):
        executor = Executor(http_scenario(f"{url}/err", ["first", "second"]))

        assert executor.run_all() is False
        assert len(state.hits("/err")) == 2


# --- TC-03: OpenAI payload ----------------------------------------------------------------------


def test_tc03_openai_payload_follows_chat_completions_format():
    with patch(OPENAI_CREATE, return_value=FAKE_COMPLETION) as create:
        endpoint = endpoint_factory(
            EndpointConfig(kind="openai", model="gpt-4o-mini", temperature=0.7, max_tokens=50)
        )
        endpoint.send_request(RequestBase(message="Hello"))

    assert create.call_args.kwargs == {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "gpt-4o-mini",
        "provider": "ChatOpenAI",
        "temperature": 0.7,
        "max_tokens": 50,
    }


@pytest.mark.xfail(strict=True, reason="`if self.temperature:` drops temperature=0.0")
def test_tc03_zero_temperature_is_sent():
    with patch(OPENAI_CREATE, return_value=FAKE_COMPLETION) as create:
        endpoint = endpoint_factory(EndpointConfig(kind="openai", temperature=0.0))
        endpoint.send_request(RequestBase(message="Hello"))

    assert create.call_args.kwargs.get("temperature") == 0.0


# --- TC-04: Echo connector ----------------------------------------------------------------------


def test_tc04_echo_returns_the_request_unchanged():
    first = endpoint_factory(EndpointConfig(kind="echo"))
    second = endpoint_factory(EndpointConfig(kind="echo"))

    response = first.send_request(RequestBase(message="Xin chào", extra_field=1))

    assert response.message == "Xin chào"
    assert response.extra_field == 1
    assert response.stats.conn_duration >= 0
    assert first.connector is not second.connector  # No state shared between endpoints


# --- TC-05: Endpoint config defaults ------------------------------------------------------------


def test_tc05_default_endpoint_config():
    assert EndpointConfig().model_dump() == {
        "kind": "openai",
        "model": "gpt-4o-mini",
        "temperature": None,
        "max_tokens": None,
    }
    assert EndpointCCConfig().model_dump(include={"top_k", "use_ranker", "collection_name"}) == {
        "top_k": 3,
        "use_ranker": True,
        "collection_name": "default",
    }
    with pytest.raises(pydantic.ValidationError):
        EndpointConfig(kind="telegram")


def test_tc05_misspelled_config_fields_are_silently_accepted():
    # Observation: extra="allow" means a typo is kept as an unused field instead of an error
    config = EndpointConfig(kind="openai", temprature=0.5)

    assert config.temperature is None
    assert config.model_extra == {"temprature": 0.5}


def test_tc05_cc_retrieval_settings_are_not_sent():
    # Observation: top_k / use_ranker / collection_name are declared but never sent
    with run_stub({"/qa": echo}) as (url, state):
        endpoint = endpoint_factory(
            EndpointConfig(kind="cc_ss", url=f"{url}/qa", top_k=7, collection_name="docs")
        )
        endpoint.send_request(RequestBase(message="hi"))

    assert state.hits("/qa")[0]["body"] == {"prompt": "hi", "query": "hi"}


@pytest.mark.xfail(strict=True, raises=AttributeError, reason="tg_chatbot needs additional_headers")
def test_tc05_tg_chatbot_works_without_additional_headers():
    endpoint = endpoint_factory(EndpointConfig(kind="tg_chatbot", url="http://127.0.0.1:9/"))

    assert endpoint.connector.additional_headers == {}


# --- TC-06: Rate limit (HTTP 429) ---------------------------------------------------------------


def test_tc06_rate_limit_response_is_not_retried():
    with run_stub({"/chat": status(429)}) as (url, state):
        endpoint = endpoint_factory(
            EndpointConfig(kind="tg_chatbot", url=f"{url}/chat", additional_headers={})
        )

        with pytest.raises(requests.HTTPError, match="429"):
            endpoint.send_request(RequestBase(message="hi"))

        assert len(state.hits("/chat")) == 1


@pytest.mark.xfail(strict=True, raises=requests.HTTPError, reason="No retry/backoff on HTTP 429")
def test_tc06_rate_limited_request_is_retried():
    calls = []

    def limited_once(body):
        calls.append(body)
        return (429, {"error": "slow down"}, 0) if len(calls) == 1 else (200, {"message": "ok"}, 0)

    with run_stub({"/chat": limited_once}) as (url, _):
        endpoint = endpoint_factory(
            EndpointConfig(kind="tg_chatbot", url=f"{url}/chat", additional_headers={})
        )

        assert endpoint.send_request(RequestBase(message="hi")).message == "ok"


# --- TC-07: Markdown / Unicode content through tg_chatbot ---------------------------------------


def test_tc07_markdown_and_unicode_are_preserved():
    text = "**Đậm** _nghiêng_ `code`\n- Hà Nội 🇻🇳\n```py\nprint(1)\n```"
    with run_stub({"/chat": echo}) as (url, state):
        endpoint = endpoint_factory(
            EndpointConfig(
                kind="tg_chatbot", url=f"{url}/chat", additional_headers={"X-API-KEY": "k"}
            )
        )
        response = endpoint.send_request(RequestBase(message=text, chat_uuid="abc"))

    received = state.hits("/chat")[0]
    assert response.message == text
    assert received["body"] == {"message": text, "chat_uuid": "abc"}
    assert received["headers"]["X-API-KEY"] == "k"


# --- TC-08: Invalid YAML ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content, error",
    [
        ("steps: [unclosed\n", yaml.YAMLError),  # ParserError
        ("config:\n\tendpoint_under_test: x\n", ValueError),  # ScannerError (tab)
        ('steps:\n  - kind: regex\n    assertion: "\\w+"\n', ValueError),  # ScannerError
    ],
)
def test_tc08_invalid_yaml_raises_parse_error(tmp_path, content, error):
    scenario = tmp_path / "broken.yaml"
    scenario.write_text(content)

    with pytest.raises(error, match="line"):
        load_yaml_file(scenario)


def test_tc08_duplicate_keys_are_silently_merged(tmp_path):
    # Observation: PyYAML keeps the last value; a duplicated `config` is not reported
    scenario = tmp_path / "dup.yaml"
    scenario.write_text("config: {}\nconfig: {a: 1}\nsteps: [x]\n")

    assert load_yaml_file(scenario)["config"] == {"a": 1}


# --- TC-09: Request / step schema ---------------------------------------------------------------


@pytest.mark.parametrize(
    "step, missing",
    [({"name": "no request"}, "request"), ({"request": "no name"}, "name")],
)
def test_tc09_step_without_required_field_is_rejected(step, missing):
    with pytest.raises(pydantic.ValidationError, match=f"steps.0.{missing}"):
        TestScenario.model_validate({"config": {}, "steps": [step]})


def test_tc09_request_of_wrong_type_is_rejected():
    with pytest.raises(pydantic.ValidationError, match="steps.0.request"):
        TestScenario.model_validate({"config": {}, "steps": [{"name": "x", "request": [1, 2]}]})


def test_tc09_empty_request_is_accepted_with_no_message():
    # Observation: `request: {}` passes validation and sends message=None
    ts = TestScenario.model_validate(
        {
            "config": {"endpoint_under_test": {"kind": "echo"}},
            "steps": [{"name": "x", "request": {}}],
        }
    )

    assert ts.steps[0].request.message is None


# --- TC-10: Response schema ---------------------------------------------------------------------


def test_tc10_openai_response_is_mapped_with_correct_types():
    with patch(OPENAI_CREATE, return_value=FAKE_COMPLETION):
        response = endpoint_factory(EndpointConfig(kind="openai")).send_request(
            RequestBase(message="Hello")
        )

    assert response.message == "ok"
    assert (response.stats.tokens_request, response.stats.tokens_response) == (12, 3)
    assert response.stats.tokens_total == 15
    assert isinstance(response.stats.conn_duration, float)


def test_tc10_non_string_message_is_rejected():
    with run_stub({"/chat": fixed({"message": 42})}) as (url, _):
        endpoint = endpoint_factory(
            EndpointConfig(kind="tg_chatbot", url=f"{url}/chat", additional_headers={})
        )

        with pytest.raises(pydantic.ValidationError, match="message"):
            endpoint.send_request(RequestBase(message="hi"))


def test_tc10_response_without_message_field_is_accepted_as_none():
    # Observation: a response without `message` is not flagged; assertions then fail later
    with run_stub({"/chat": fixed({"answer": "Paris"})}) as (url, _):
        endpoint = endpoint_factory(
            EndpointConfig(kind="tg_chatbot", url=f"{url}/chat", additional_headers={})
        )
        response = endpoint.send_request(RequestBase(message="hi"))

    assert response.message is None
    assert response.answer == "Paris"
