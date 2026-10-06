"""Review tests for YAML scenario loading, TestsRouter routing and error fallbacks.

Tests marked `xfail(strict=True)` describe the desired behaviour of a defect found during the
review; they start failing (XPASS) once the defect is fixed, so the marker must then be removed.
"""

import json
from pathlib import Path

import pydantic
import pytest
import requests

from contextcheck import TestScenario
from contextcheck.executors.executor import Executor
from contextcheck.executors.tests_router import TestsRouter
from contextcheck.loaders.yaml import load_yaml_file

ECHO_SCENARIO = """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: {name}
    request: {request}
    asserts:
      - kind: contains
        assertion: {request}
"""


def write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


# --- YAML loading -------------------------------------------------------------------------------


def test_jinja_variables_are_rendered_and_multiline_values_flattened(tmp_path):
    scenario = write(
        tmp_path / "vars.yaml",
        """
variables:
  country: Poland
  long_text: |
    first line
    second line
config:
  endpoint_under_test:
    kind: echo
steps:
  - "Capital of {{ country }}?"
  - "Summary: {{ long_text }}"
""",
    )
    ts = TestScenario.from_yaml(scenario)

    assert ts.steps[0].request.message == "Capital of Poland?"
    assert ts.steps[1].request.message == "Summary: first line second line "


def test_default_request_is_merged_into_every_step(tmp_path):
    scenario = write(
        tmp_path / "default.yaml",
        """
config:
  endpoint_under_test:
    kind: echo
  default_request:
    parse_response_as_json: true
steps:
  - plain string step
  - name: dict step
    request:
      message: dict request
      parse_response_as_json: false
""",
    )
    ts = TestScenario.from_yaml(scenario)

    # Step-level values override the default ones
    assert ts.steps[0].request.parse_response_as_json is True
    assert ts.steps[1].request.parse_response_as_json is False
    assert ts.steps[1].request.message == "dict request"


def test_double_quoted_regex_gives_friendly_error(tmp_path):
    scenario = write(tmp_path / "regex.yaml", 'steps:\n  - kind: regex\n    assertion: "\\w+"\n')

    with pytest.raises(ValueError, match="Use single quotes"):
        load_yaml_file(scenario)


def test_unknown_endpoint_kind_is_rejected_at_load_time(tmp_path):
    scenario = write(
        tmp_path / "kind.yaml", "config:\n  endpoint_under_test:\n    kind: foo\nsteps: [hi]\n"
    )

    with pytest.raises(pydantic.ValidationError, match="endpoint_under_test.kind"):
        TestScenario.from_yaml(scenario)


def test_missing_config_section_is_rejected(tmp_path):
    scenario = write(tmp_path / "noconfig.yaml", "steps: [hi]\n")

    with pytest.raises(pydantic.ValidationError, match="config"):
        TestScenario.from_yaml(scenario)


@pytest.mark.xfail(strict=True, reason="Empty YAML file raises AttributeError on None.get")
def test_empty_yaml_file_gives_clear_error(tmp_path):
    scenario = write(tmp_path / "empty.yaml", "")

    with pytest.raises((ValueError, pydantic.ValidationError)):
        TestScenario.from_yaml(scenario)


@pytest.mark.xfail(strict=True, reason="Undefined Jinja variables silently render as ''")
def test_undefined_jinja_variable_is_reported(tmp_path):
    scenario = write(
        tmp_path / "undefined.yaml",
        "config:\n  endpoint_under_test:\n    kind: echo\nsteps:\n  - '{{ typo_var }}'\n",
    )

    with pytest.raises(Exception, match="typo_var"):
        TestScenario.from_yaml(scenario)


# --- Routing ------------------------------------------------------------------------------------


def test_router_runs_all_files_and_writes_one_report_each(tmp_path):
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    write(scenarios / "a.yaml", ECHO_SCENARIO.format(name="a", request="alpha"))
    write(scenarios / "b.yaml", ECHO_SCENARIO.format(name="b", request="beta"))
    output = tmp_path / "out"

    TestsRouter(output_type="file", folder=scenarios, output_folder=output).run_tests()

    reports = sorted(output.glob("*.json"))
    assert [r.name.split("_")[0] for r in reports] == ["a", "b"]
    assert all(json.loads(r.read_text())["result"] is True for r in reports)


def test_router_folder_only_collects_dot_yaml_files(tmp_path):
    write(tmp_path / "a.yaml", ECHO_SCENARIO.format(name="a", request="alpha"))
    write(tmp_path / "b.yml", ECHO_SCENARIO.format(name="b", request="beta"))
    output = tmp_path / "out"

    TestsRouter(output_type="file", folder=tmp_path, output_folder=output).run_tests()

    # `.yml` files are silently ignored: only a.yaml produces a report
    assert [r.name.split("_")[0] for r in output.glob("*.json")] == ["a"]


def test_router_with_no_scenarios_does_nothing(tmp_path):
    TestsRouter(output_type="console", folder=tmp_path).run_tests()


# --- Fallbacks ----------------------------------------------------------------------------------


def test_failing_assertion_is_isolated_and_remaining_assertions_run(tmp_path):
    scenario = write(
        tmp_path / "asserts.yaml",
        """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: step
    request: hello
    asserts:
      - 'undefined_name == 1'
      - '1 + 1'
      - kind: contains
        assertion: hello
""",
    )
    executor = Executor(TestScenario.from_yaml(scenario))

    assert executor.run_all() is False
    assert [a.result for a in executor.test_scenario.steps[0].asserts] == [None, None, True]


@pytest.mark.xfail(
    strict=True, raises=requests.ConnectionError, reason="Endpoint errors abort the whole run"
)
def test_unreachable_endpoint_fails_step_and_run_continues(tmp_path):
    write(
        tmp_path / "a_down.yaml",
        "config:\n  endpoint_under_test:\n    kind: cc_prompt_llm\n    url: http://127.0.0.1:9/\n"
        "steps: [hi]\n",
    )
    write(tmp_path / "b_ok.yaml", ECHO_SCENARIO.format(name="b", request="beta"))
    output = tmp_path / "out"

    TestsRouter(output_type="file", folder=tmp_path, output_folder=output).run_tests()

    assert len(list(output.glob("*.json"))) == 2


@pytest.mark.xfail(
    strict=True, raises=AttributeError, reason="Time statistics read responses of skipped steps"
)
def test_time_statistics_after_early_stop(tmp_path):
    write(
        tmp_path / "s.yaml",
        """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: fails
    request: hello
    asserts:
      - kind: equals
        assertion: nope
  - name: skipped
    request: world
""",
    )

    TestsRouter(
        output_type="file",
        folder=tmp_path,
        output_folder=tmp_path / "out",
        exit_on_failure=True,
        show_time_statistics=True,
    ).run_tests()
