"""End-to-end Q&A flow against a mock RAG API.

Flow: generate questions from RAG documents -> generate reference answers through the RAG QA
endpoint -> turn them into a ContextCheck scenario -> run it with the `ccheck` CLI.
The question-writing LLM is replaced by a stub so the test needs no API key.
"""

import importlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from contextcheck.endpoints.endpoint_config import EndpointConfig
from contextcheck.generators.generate_answers import AnswerGenerator
from contextcheck.generators.generate_questions import QuestionsGenerator
from tests.mock_rag_server import NO_ANSWER, run_mock_rag_server

STUB_QUESTIONS = "\n".join(
    [
        '{"question": "What is the capital of Poland?"}',
        '{"question": "What is the capital of France?"}',
    ]
)


@pytest.fixture
def rag():
    with run_mock_rag_server() as (base_url, state):
        yield base_url, state


@pytest.fixture
def api_wrapper(rag, monkeypatch):
    base_url, _ = rag
    # cc_api_wrapper reads these at import time, so they must exist before importing it
    monkeypatch.setenv("ENDPOINT_BASE_URL", base_url)
    monkeypatch.setenv("HEADER_KEY", "x-api-key")
    monkeypatch.setenv("HEADER_VALUE", "test")
    module = importlib.import_module("contextcheck.generators.cc_api_wrapper")
    return module.ContextClueApiWrapper(
        endpoint_base_url=base_url, header_key="x-api-key", header_value="test", timeout=10
    )


def generate_questions(api_wrapper, path: Path) -> list[dict]:
    with patch("contextcheck.generators.generate_questions.endpoint_factory") as factory:
        llm = factory.return_value
        llm.send_request.return_value.message = STUB_QUESTIONS
        generator = QuestionsGenerator(
            api_wrapper=api_wrapper,
            questions_generator_endpoint_config=EndpointConfig(kind="echo"),
            num_topics=2,
            questions_per_topic=2,
        )
        generator.save_to_yaml(str(path))
    return generator.generated_questions, llm


def build_scenario(qa: dict, rag_url: str) -> str:
    steps = [
        {
            "name": item["question"],
            "request": item["question"],
            "asserts": [{"kind": "equals", "assertion": item["answer"]}],
        }
        for entry in qa["QA"]
        for item in entry["qa"]
    ]
    config = {"endpoint_under_test": {"kind": "cc_prompt_llm", "url": f"{rag_url}/cc/qa"}}
    return yaml.safe_dump({"config": config, "steps": steps})


def run_ccheck(scenario: Path, output: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "contextcheck.run_tests", "--output-type", "file"]
        + ["--filename", str(scenario), "--output-folder", str(output)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def read_report(output: Path) -> dict:
    (report,) = output.glob("*.json")
    return json.loads(report.read_text())


def test_e2e_qa_flow(rag, api_wrapper, tmp_path):
    base_url, _ = rag

    questions, _ = generate_questions(api_wrapper, tmp_path / "questions.yaml")
    assert questions[0]["document"] == "Geography"
    assert "What is the capital of Poland?" in questions[0]["questions"]

    qa = AnswerGenerator(
        api_wrapper=api_wrapper, questions_file=tmp_path / "questions.yaml", debug=True
    ).generate()
    answers = {item["question"]: item for item in qa["QA"][0]["qa"]}
    poland = answers["What is the capital of Poland?"]
    assert poland["answer"] == "Warsaw is the capital of Poland."
    assert poland["chunks_and_documents"][0][0]["document"] == "Geography"

    scenario = tmp_path / "regression.yaml"
    scenario.write_text(build_scenario(qa, base_url))
    result = run_ccheck(scenario, tmp_path / "out")

    assert result.returncode == 0, result.stderr
    report = read_report(tmp_path / "out")
    assert report["result"] is True
    assert len(report["steps"]) == len(qa["QA"][0]["qa"])


def test_question_generation_with_empty_retriever(rag, api_wrapper, tmp_path):
    _, state = rag
    state.retriever_empty = True

    questions, llm = generate_questions(api_wrapper, tmp_path / "questions.yaml")

    # The LLM is still asked (with no context chunks) and the flow completes
    assert llm.send_request.called
    assert questions[0]["questions"]


def test_answer_generation_with_empty_retriever(rag, api_wrapper, tmp_path):
    _, state = rag
    (tmp_path / "questions.yaml").write_text(
        'questions:\n  - document: Geography\n    questions: ["What is the capital of Poland?"]\n'
    )
    state.retriever_empty = True

    qa = AnswerGenerator(
        api_wrapper=api_wrapper, questions_file=tmp_path / "questions.yaml", debug=True
    ).generate()

    item = qa["QA"][0]["qa"][0]
    assert item["answer"] == NO_ANSWER
    assert item["chunks_and_documents"] == []


def test_regression_run_with_empty_retriever_fails_gracefully(rag, tmp_path):
    base_url, state = rag
    qa = {
        "QA": [
            {
                "document": "Geography",
                "qa": [
                    {
                        "question": "What is the capital of Poland?",
                        "answer": "Warsaw is the capital of Poland.",
                    }
                ],
            }
        ]
    }
    scenario = tmp_path / "regression.yaml"
    scenario.write_text(build_scenario(qa, base_url))
    state.retriever_empty = True

    result = run_ccheck(scenario, tmp_path / "out")

    # The regression is detected as a failed assertion, not as a crash
    assert result.returncode == 0, result.stderr
    report = read_report(tmp_path / "out")
    assert report["result"] is False
    assert report["steps"][0]["response"]["message"] == NO_ANSWER


@pytest.mark.xfail(strict=True, raises=ValueError, reason="LDA fails on a document with no chunks")
def test_question_generation_with_document_without_chunks(rag, api_wrapper, tmp_path):
    _, state = rag
    state.chunks = []

    questions, _ = generate_questions(api_wrapper, tmp_path / "questions.yaml")

    assert questions == [{"document": "Geography", "questions": []}]


@pytest.mark.xfail(strict=True, reason="cc_api_wrapper reads os.environ[...] at import time")
def test_cc_api_wrapper_importable_without_env(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", "import contextcheck.generators.cc_api_wrapper"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": "", "PYTHONPATH": str(Path(__file__).parents[1])},
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
