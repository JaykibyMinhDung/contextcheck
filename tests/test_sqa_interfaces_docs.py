"""SQA – Giao diện Báo cáo & Tài liệu (TUI console, JSON output, code quality, docs):
TC-41 .. TC-50.

Tests marked `xfail(strict=True)` describe the expected behaviour of a defect that was found.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import jsonschema
import pytest
import yaml
from rich.cells import cell_len

from contextcheck import TestScenario
from contextcheck.assertions.assertions import AssertionLLM, DeterministicMetricsEnum
from contextcheck.assertions.llm_metrics import LlmMetricEnum
from contextcheck.endpoints.endpoint import EndpointBase
from contextcheck.executors.tests_router import TestsRouter
from contextcheck.models.request import RequestBase
from contextcheck.models.response import ResponseBase

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs" / "docs"

SCENARIO = """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: echo a fairly long step name to check wrapping in narrow terminals
    request: "Hello, this is a long request message that should wrap in narrow terminals."
    asserts:
      - kind: contains
        assertion: Hello
      - kind: is-valid-json
"""


def ccheck(*args: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "contextcheck.run_tests", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        # UTF-8 by default so results do not depend on the OS code page; TC-42 overrides it
        env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
        timeout=120,
    )


@pytest.fixture
def scenario(tmp_path: Path) -> Path:
    path = tmp_path / "ui.yaml"
    path.write_text(SCENARIO)
    return path


# --- TC-41: Console layout at different terminal widths -----------------------------------------


@pytest.mark.parametrize("columns", [40, 80, 160])
def test_tc41_console_output_fits_the_terminal_width(scenario, columns):
    result = ccheck(
        "--output-type",
        "console",
        "--filename",
        scenario.name,
        "--aggregate-results",
        "--show-time-statistics",
        cwd=scenario.parent,
        env={"COLUMNS": str(columns)},
    )

    assert result.returncode == 0
    widths = [cell_len(line) for line in result.stdout.splitlines()]
    assert max(widths) <= columns
    if columns == 40:
        assert "…" in result.stdout  # Observation: content is truncated, not wrapped


# --- TC-42: Terminals / platforms ---------------------------------------------------------------


def test_tc42_plain_terminal_gets_no_ansi_codes(scenario):
    result = ccheck(
        "--output-type",
        "console",
        "--filename",
        scenario.name,
        cwd=scenario.parent,
        env={"NO_COLOR": "1", "TERM": "dumb"},
    )

    assert result.returncode == 0
    assert "\x1b[" not in result.stdout


@pytest.mark.xfail(strict=True, reason="Emoji panel titles crash on legacy code pages (cp1252)")
@pytest.mark.parametrize("encoding", ["cp1252", "cp437"])
def test_tc42_console_output_on_legacy_windows_code_page(scenario, encoding):
    # Simulates Windows cmd/PowerShell with redirected output (python uses the ANSI code page)
    result = ccheck(
        "--output-type",
        "console",
        "--filename",
        scenario.name,
        cwd=scenario.parent,
        env={"PYTHONIOENCODING": encoding},
    )

    assert result.returncode == 0, result.stderr[-300:]


# --- TC-43: Read-only output folder -------------------------------------------------------------


@pytest.fixture
def read_only_dir(tmp_path: Path):
    path = tmp_path / "read_only"
    path.mkdir()
    path.chmod(0o555)
    immutable = False
    if os.access(path, os.W_OK) and shutil.which("chattr"):  # root ignores chmod
        immutable = subprocess.run(["chattr", "+i", str(path)]).returncode == 0
    try:
        (path / ".probe").write_text("")
        pytest.skip("Cannot create a read-only directory in this environment")
    except PermissionError:
        pass
    yield path
    if immutable:
        subprocess.run(["chattr", "-i", str(path)])
    path.chmod(0o755)


def test_tc43_read_only_output_folder_fails_the_run(scenario, read_only_dir):
    result = ccheck(
        "--output-type",
        "file",
        "--filename",
        scenario.name,
        "--output-folder",
        str(read_only_dir),
        cwd=scenario.parent,
    )

    assert result.returncode != 0
    assert "PermissionError" in result.stderr


@pytest.mark.xfail(strict=True, reason="PermissionError is not caught: traceback, results lost")
def test_tc43_read_only_output_folder_is_reported_cleanly(scenario, read_only_dir):
    result = ccheck(
        "--output-type",
        "file",
        "--filename",
        scenario.name,
        "--output-folder",
        str(read_only_dir),
        cwd=scenario.parent,
    )

    assert "Traceback" not in result.stderr
    assert "permission" in result.stderr.lower()


# --- TC-44: JSON validator ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "response, valid",
    [('{"a": 1}', True), ('{"a": 1', False), ("{'a': 1}", False), ("", False), ("[1, 2,]", False)],
)
def test_tc44_is_valid_json_flags_malformed_json(response, valid):
    scenario = TestScenario.model_validate(
        {
            "config": {"endpoint_under_test": {"kind": "echo"}},
            "steps": [{"name": "s", "request": response, "asserts": [{"kind": "is-valid-json"}]}],
        }
    )
    from contextcheck.executors.executor import Executor

    assert Executor(scenario).run_all() is valid


def test_tc44_invalid_schema_is_reported_as_a_failed_response():
    # Observation: a broken schema in YAML looks like an invalid response, not a config error
    from contextcheck.assertions.assertions import DETERMINISTIC_METRICS_MAPPING as metrics

    check = metrics[DeterministicMetricsEnum.HAS_VALID_JSON_SCHEMA]

    assert check({"type": "not-a-type"}, '{"a": 1}') is False


# --- TC-45: Structure of the JSON report --------------------------------------------------------

REPORT_SCHEMA = {
    "type": "object",
    "required": [
        "steps",
        "config",
        "result",
        "filename",
        "global_test_timestamp",
        "test_timestamp",
        "report",
        "time_statistics",
    ],
    "properties": {
        "result": {"type": ["boolean", "null"]},
        "filename": {"type": "string"},
        "global_test_timestamp": {"type": "string"},
        "test_timestamp": {"type": "string"},
        "config": {"type": "object", "required": ["endpoint_under_test"]},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "request", "response", "asserts", "result"],
                "properties": {
                    "result": {"type": ["boolean", "null"]},
                    "asserts": {
                        "type": "array",
                        "items": {"type": "object", "required": ["result"]},
                    },
                    "response": {
                        "type": "object",
                        "required": ["message", "stats"],
                        "properties": {"stats": {"type": "object", "required": ["conn_duration"]}},
                    },
                },
            },
        },
        "report": {"type": "object"},
        "time_statistics": {
            "type": "object",
            "required": ["mean", "median", "minimum", "maximum", "std"],
        },
    },
}


def test_tc45_json_report_matches_the_schema(scenario, tmp_path):
    output = tmp_path / "out"
    result = ccheck(
        "--output-type",
        "file",
        "--filename",
        scenario.name,
        "--output-folder",
        str(output),
        "--aggregate-results",
        "--show-time-statistics",
        cwd=scenario.parent,
    )

    assert result.returncode == 0, result.stderr[-300:]
    (report_file,) = output.glob("*.json")
    jsonschema.validate(json.loads(report_file.read_text()), REPORT_SCHEMA)


@pytest.mark.xfail(strict=True, reason="Reports are named <name before first dot>_<second>.json")
def test_tc45_scenarios_with_the_same_prefix_get_separate_reports(tmp_path):
    for name in ("smoke.v1.yaml", "smoke.v2.yaml"):
        (tmp_path / name).write_text(SCENARIO)
    output = tmp_path / "out"
    frozen = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with patch("contextcheck.interfaces.interface_output_file.datetime") as clock:
        clock.now.return_value = frozen
        clock.timestamp = datetime.timestamp
        TestsRouter(output_type="file", folder=tmp_path, output_folder=output).run_tests()

    assert len(list(output.glob("*.json"))) == 2


# --- TC-46: flake8 ------------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="flake8 reports 36 issues (E501, W291, E722)")
def test_tc46_flake8_reports_no_issues():
    pytest.importorskip("flake8")
    result = subprocess.run(
        [sys.executable, "-m", "flake8", "contextcheck", "--count"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=300,
    )

    assert result.returncode == 0, result.stdout[-500:]


# --- TC-47: pytest configuration ----------------------------------------------------------------


def test_tc47_custom_markers_and_flags_are_registered():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--markers", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=ROOT / "tests",
        timeout=120,
    )

    assert "@pytest.mark.openai" in result.stdout
    assert "@pytest.mark.ollama" in result.stdout


def test_tc47_tests_router_triggers_a_collection_warning():
    # Observation: TestsRouter starts with "Test" but, unlike TestScenario, lacks __test__ = False
    assert getattr(TestScenario, "__test__", True) is False
    assert getattr(TestsRouter, "__test__", True) is True


# --- TC-48: Following the getting-started documentation -----------------------------------------


def yaml_blocks(path: Path) -> list[str]:
    return re.findall(r"```yaml\n(.*?)```", path.read_text(), re.S)


def test_tc48_every_scenario_example_in_the_docs_is_valid():
    docs = [p for p in DOCS.rglob("*.md") if "testing" not in p.parts] + [ROOT / "README.md"]
    examples = [
        data
        for path in docs
        for block in yaml_blocks(path)
        if isinstance(data := yaml.safe_load(block), dict) and "steps" in data
    ]

    assert len(examples) == 11
    for example in examples:
        TestScenario.model_validate({"config": {}} | example)


def test_tc48_readme_cli_commands_work(scenario):
    scenario.write_text(SCENARIO.replace("      - kind: is-valid-json\n", ""))
    (scenario.parent / "my_tests").mkdir()
    shutil.copy(scenario, scenario.parent / "my_tests" / "a.yaml")

    commands = [
        ["--help"],
        ["--output-type", "console", "--filename", scenario.name, scenario.name],
        ["--exit-on-failure", "--output-type", "console", "--folder", "my_tests"],
    ]
    for args in commands:
        assert ccheck(*args, cwd=scenario.parent).returncode == 0, args


# --- TC-49: Metrics documentation vs. code ------------------------------------------------------


def test_tc49_documented_metric_names_match_the_code():
    deterministic = (DOCS / "user_guide" / "deterministic_metrics.md").read_text()
    llm_based = (DOCS / "user_guide" / "llm_based_metrics.md").read_text()

    assert all(f"`{kind.value}`" in deterministic for kind in DeterministicMetricsEnum)
    assert all(f"`{name.value}`" in llm_based for name in LlmMetricEnum)


@pytest.mark.xfail(strict=True, reason="regex uses re.match: the pattern must match at position 0")
def test_tc49_documented_regex_example_matches_an_answer_containing_an_email():
    example = yaml.safe_load(yaml_blocks(DOCS / "user_guide" / "deterministic_metrics.md")[-1])
    definition = example["steps"][0]["asserts"][0]
    scenario = TestScenario.model_validate(
        {
            "config": {"endpoint_under_test": {"kind": "echo"}},
            "steps": [
                {
                    "name": "regex",
                    "request": "The HR department can be reached at hr@company.com.",
                    "asserts": [definition],
                }
            ],
        }
    )
    from contextcheck.executors.executor import Executor

    assert Executor(scenario).run_all() is True


def test_tc49_documented_hallucination_example_sends_an_empty_reference():
    # Observation: docs show `llm_metric: hallucination` without `reference` and say reference
    # documents are fetched from the RAG; the code only uses the `reference` field of the assert.
    prompts = []

    class Judge(EndpointBase):
        def send_request(self, req: RequestBase) -> ResponseBase:
            prompts.append(req.message)
            return ResponseBase(message="factual")

    AssertionLLM(llm_metric="hallucination")(
        RequestBase(message="q"), ResponseBase(message="a", documents=["doc"]), Judge()
    )

    assert "[Reference text]: \n" in prompts[0]


# --- TC-50: Example notebook --------------------------------------------------------------------


def test_tc50_example_notebook_needs_an_openai_key(monkeypatch, tmp_path):
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")
    pytest.importorskip("ipykernel")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # Never call the paid API from tests

    notebook = nbformat.read(ROOT / "examples" / "ex1.ipynb", as_version=4)
    client = nbclient.NotebookClient(
        notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": tmp_path}}
    )
    executed = 0
    with pytest.raises(nbclient.exceptions.CellExecutionError, match="OPENAI_API_KEY"):
        with client.setup_kernel():
            for index, cell in enumerate(notebook.cells):
                if cell.cell_type == "code":
                    client.execute_cell(cell, index)
                    executed += 1

    assert executed == 6  # Cells up to the first `executor.run_all()` work without a key
