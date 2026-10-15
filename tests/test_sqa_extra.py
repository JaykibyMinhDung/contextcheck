"""Additional SQA tests tracing requirements of the supplementary SRS (SRS-CC-N11 v0.2).

Each test names the requirement it verifies. Tests marked `xfail(strict=True)` describe the
required behaviour of a confirmed defect (see the defect list of the group report).
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pydantic
import pytest

from contextcheck.assertions.assertions import DETERMINISTIC_METRICS_MAPPING
from contextcheck.assertions.assertions import DeterministicMetricsEnum as Kind
from contextcheck.assertions.factory import factory as assertion_factory
from contextcheck.connectors.connector_echo import ConnectorEcho
from contextcheck.connectors.connector_http import ConnectorHTTP
from contextcheck.connectors.connector_openai_compatible import ConnectorOpenAICompatible
from contextcheck.endpoints.endpoint_config import EndpointConfig
from contextcheck.endpoints.factory import factory as endpoint_factory
from contextcheck.generators.endpoint_wrapper import RagApiWrapperBase
from contextcheck.generators.generate_questions import QuestionsGenerator
from contextcheck.models.response import ResponseBase

ENDPOINT_FACTORY = "contextcheck.generators.generate_questions.endpoint_factory"
CHUNKS = ["Warsaw is the capital of Poland and its largest city."] * 5


def run(*args: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
        timeout=120,
    )


class Wrapper(RagApiWrapperBase):
    retrieved: list[dict] = [{"chunk": CHUNKS[0]}]

    def list_documents(self):
        return [{"id": "1", "name": "Geography"}]

    def get_document_chunks(self, document_id):
        return CHUNKS

    def query_semantic_db(self, query, **kwargs):
        return self.retrieved

    def query_qa(self, query, **kwargs):
        return {"result": "x"}


def generator(wrapper: RagApiWrapperBase) -> QuestionsGenerator:
    return QuestionsGenerator(
        api_wrapper=wrapper,
        questions_generator_endpoint_config=EndpointConfig(kind="echo"),
        num_topics=2,
        questions_per_topic=2,
    )


# --- FR-CN-03 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config, connector",
    [
        ({"kind": "openai"}, ConnectorOpenAICompatible),
        ({"kind": "openai_compatible"}, ConnectorOpenAICompatible),
        ({"kind": "cc_prompt_llm", "url": "http://127.0.0.1:9/"}, ConnectorHTTP),
        ({"kind": "cc_ss", "url": "http://127.0.0.1:9/"}, ConnectorHTTP),
        (
            {"kind": "tg_chatbot", "url": "http://127.0.0.1:9/", "additional_headers": {}},
            ConnectorHTTP,
        ),
        ({"kind": "echo"}, ConnectorEcho),
    ],
)
def test_fr_cn_03_each_kind_uses_the_expected_connector(config, connector):
    assert type(endpoint_factory(EndpointConfig(**config)).connector) is connector


# --- FR-GEN-01, FR-GEN-05, FR-GEN-08 -------------------------------------------------------------


def test_fr_gen_01_questions_generator_without_arguments_shows_help(tmp_path):
    result = run("contextcheck.questions_generator", cwd=tmp_path)

    assert result.returncode == 0
    assert "--wrapper-class-path" in result.stdout


@pytest.mark.xfail(strict=True, reason="The LLM is asked for questions even without any chunk")
def test_fr_gen_05_llm_is_not_called_when_no_chunk_is_retrieved():
    with patch(ENDPOINT_FACTORY) as factory:
        factory.return_value.send_request.return_value = ResponseBase(message='{"question": "Q?"}')
        generator(Wrapper(retrieved=[])).generate()

    assert not factory.return_value.send_request.called


def test_fr_gen_08_questions_file_folders_are_created(tmp_path):
    target = tmp_path / "a" / "b" / "questions.yaml"
    with patch(ENDPOINT_FACTORY) as factory:
        factory.return_value.send_request.return_value = ResponseBase(message='{"question": "Q?"}')
        generator(Wrapper()).save_to_yaml(str(target))

    assert target.is_file()
    assert "Q?" in target.read_text(encoding="utf-8")


# --- FR-MET-01, FR-MET-05, FR-MET-06 -------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="A definition with two metric keys is silently accepted")
def test_fr_met_01_definition_with_two_metric_keys_is_rejected():
    with pytest.raises((ValueError, pydantic.ValidationError)):
        assertion_factory({"kind": "contains", "assertion": "a", "llm_metric": "hallucination"})


@pytest.mark.xfail(strict=True, reason="regex uses re.match, anchored at the start of the response")
def test_fr_met_05_regex_matches_anywhere_in_the_response():
    assert DETERMINISTIC_METRICS_MAPPING[Kind.REGEX](r"\d{3}", "Order number: 123") is True


@pytest.mark.xfail(strict=True, reason="An invalid JSON schema is reported as a failed response")
def test_fr_met_06_invalid_json_schema_is_a_configuration_error():
    with pytest.raises(Exception):
        DETERMINISTIC_METRICS_MAPPING[Kind.HAS_VALID_JSON_SCHEMA]({"type": "no-such-type"}, "{}")


# --- FR-EXE-11 ---------------------------------------------------------------------------------

LATER_STEP_FAILS = """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: passes
    request: hello
    asserts:
      - kind: equals
        assertion: hello
  - name: fails
    request: hello
    asserts:
      - kind: equals
        assertion: nope
"""


@pytest.mark.xfail(strict=True, reason="Executor.run_all only counts the first step on early stop")
def test_fr_exe_11_exit_on_failure_returns_1_when_a_later_step_fails(tmp_path):
    (tmp_path / "later.yaml").write_text(LATER_STEP_FAILS, encoding="utf-8")

    result = run(
        "contextcheck.run_tests",
        "--output-type",
        "file",
        "--filename",
        "later.yaml",
        "--output-folder",
        "out",
        "--exit-on-failure",
        cwd=tmp_path,
    )

    assert result.returncode == 1


# --- FR-UI-02 .. FR-UI-05 ------------------------------------------------------------------------

EARLY_STOP = """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: passes
    request: hello
    asserts:
      - kind: equals
        assertion: hello
  - name: fails
    request: hello
    asserts:
      - kind: equals
        assertion: nope
  - name: skipped
    request: world
"""


@pytest.fixture
def scenario(tmp_path: Path) -> Path:
    path = tmp_path / "ui.yaml"
    path.write_text(EARLY_STOP, encoding="utf-8")
    return path


def test_fr_ui_02_summary_shows_ok_fail_and_skipped(scenario):
    result = run(
        "contextcheck.run_tests",
        "--output-type",
        "console",
        "--filename",
        scenario.name,
        "--exit-on-failure",
        cwd=scenario.parent,
        env={"COLUMNS": "160"},
    )

    for label in ("Request", "Response", "Asserts", "Valid", "OK", "FAIL", "SKIPPED"):
        assert label in result.stdout


def test_fr_ui_03_04_aggregate_and_time_tables(scenario):
    scenario.write_text(EARLY_STOP.split("  - name: fails")[0], encoding="utf-8")

    result = run(
        "contextcheck.run_tests",
        "--output-type",
        "console",
        "--filename",
        scenario.name,
        "--aggregate-results",
        "--show-time-statistics",
        cwd=scenario.parent,
        env={"COLUMNS": "160"},
    )

    assert result.returncode == 0
    for label in ("Metric type", "Metric name", "Mean score", "Test count"):
        assert label in result.stdout
    for label in ("Mean", "Median", "Minimum", "Maximum", "Std"):
        assert label in result.stdout


@pytest.mark.xfail(strict=True, reason="Narrow terminals truncate table content with an ellipsis")
def test_fr_ui_05_long_content_is_wrapped_not_truncated(scenario):
    result = run(
        "contextcheck.run_tests",
        "--output-type",
        "console",
        "--filename",
        scenario.name,
        cwd=scenario.parent,
        env={"COLUMNS": "40"},
    )

    assert "…" not in result.stdout
