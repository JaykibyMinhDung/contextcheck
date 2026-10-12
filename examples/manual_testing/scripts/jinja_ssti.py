"""TC-19: the questions file is rendered as a Jinja2 template (template injection)."""

import tempfile
from pathlib import Path

from contextcheck.generators.endpoint_wrapper import RagApiWrapperBase
from contextcheck.generators.generate_answers import AnswerGenerator


class NoRag(RagApiWrapperBase):
    def list_documents(self):
        return []

    def get_document_chunks(self, document_id):
        return []

    def query_semantic_db(self, query, **kwargs):
        return []

    def query_qa(self, query, **kwargs):
        return {"result": ""}


with tempfile.TemporaryDirectory() as folder:
    questions = Path(folder) / "questions.yaml"
    questions.write_text(
        'questions:\n  - document: Demo\n    questions: ["What is {{ 7*7 }}?"]\n', encoding="utf-8"
    )
    print("Question written to file :", "What is {{ 7*7 }}?")
    loaded = AnswerGenerator(api_wrapper=NoRag(), questions_file=questions).questions
    print("Question loaded back     :", loaded[0].questions[0])
