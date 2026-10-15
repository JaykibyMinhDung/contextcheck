"""Black-box tests of the `ccheck` command line interface (TC-01 .. TC-08).

The CLI is executed in a subprocess exactly as a user would run it; only exit codes, console
output and produced files are checked.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PASSING_SCENARIO = """
config:
  endpoint_under_test:
    kind: echo
steps:
  - name: echo works
    request: hello
    asserts:
      - kind: equals
        assertion: hello
"""

FAILING_SCENARIO = PASSING_SCENARIO.replace("assertion: hello", "assertion: something else")


def ccheck(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    # UTF-8 on both ends: Windows pipes default to the ANSI code page, which cannot encode the
    # emoji printed by the console UI (tracked separately as defect D-14 / TC-42)
    return subprocess.run(
        [sys.executable, "-m", "contextcheck.run_tests", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    (tmp_path / "pass.yaml").write_text(PASSING_SCENARIO)
    (tmp_path / "fail.yaml").write_text(FAILING_SCENARIO)
    return tmp_path


def test_tc01_help(workdir):
    result = ccheck("--help", cwd=workdir)

    assert result.returncode == 0
    assert "--output-type" in result.stdout


def test_tc02_missing_required_output_type(workdir):
    result = ccheck("--filename", "pass.yaml", cwd=workdir)

    assert result.returncode == 2
    assert "the following arguments are required: --output-type" in result.stderr


def test_tc03_invalid_output_type(workdir):
    result = ccheck("--output-type", "xml", "--filename", "pass.yaml", cwd=workdir)

    assert result.returncode == 2
    assert "invalid choice: 'xml'" in result.stderr


def test_tc04_file_output_without_input(workdir):
    result = ccheck("--output-type", "file", cwd=workdir)

    assert result.returncode == 2
    assert "--filename or --folder is required" in result.stderr


def test_tc05_file_output_without_output_folder(workdir):
    result = ccheck("--output-type", "file", "--filename", "pass.yaml", cwd=workdir)

    assert result.returncode == 2
    assert "--output-folder is required" in result.stderr


def test_tc06_nonexistent_scenario_file(workdir):
    result = ccheck("--output-type", "console", "--filename", "missing.yaml", cwd=workdir)

    assert result.returncode != 0
    assert "missing.yaml do not exist" in result.stderr


def test_tc07_console_run_of_passing_scenario(workdir):
    result = ccheck("--output-type", "console", "--filename", "pass.yaml", cwd=workdir)

    assert result.returncode == 0
    assert "echo works" in result.stdout


def test_tc08_file_output_and_exit_on_failure(workdir):
    result = ccheck(
        "--output-type",
        "file",
        "--filename",
        "pass.yaml",
        "fail.yaml",
        "--output-folder",
        "out",
        "--exit-on-failure",
        "--aggregate-results",
        cwd=workdir,
    )

    assert result.returncode == 1
    reports = {p.name.split("_")[0]: json.loads(p.read_text()) for p in (workdir / "out").iterdir()}
    assert reports["pass"]["result"] is True
    assert reports["fail"]["result"] is False
    assert "report" in reports["fail"]


@pytest.mark.xfail(strict=True, reason="`--debug` combines type=bool with action='store_true'")
def test_question_answering_cli_starts(workdir):
    result = subprocess.run(
        [sys.executable, "-m", "contextcheck.question_answering", "--help"],
        capture_output=True,
        text=True,
        cwd=workdir,
        timeout=120,
    )

    assert result.returncode == 0
