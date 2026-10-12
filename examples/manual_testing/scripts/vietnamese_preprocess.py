"""TC-17: text cleaning used before topic modelling (LDA) in the questions generator."""

from contextcheck.endpoints.endpoint_config import EndpointConfig
from contextcheck.generators.endpoint_wrapper import RagApiWrapperBase
from contextcheck.generators.generate_questions import QuestionsGenerator


class NoRag(RagApiWrapperBase):
    def list_documents(self):
        return []

    def get_document_chunks(self, document_id):
        return []

    def query_semantic_db(self, query, **kwargs):
        return []

    def query_qa(self, query, **kwargs):
        return {}


generator = QuestionsGenerator(  # downloads NLTK stop words on first run
    api_wrapper=NoRag(), questions_generator_endpoint_config=EndpointConfig(kind="echo")
)
for text in (
    "The <b>capital</b> of Poland is Warsaw!!! @#$ 2024 naïve café",
    "Thủ đô của Việt Nam là Hà Nội, thành phố có hơn một nghìn năm lịch sử.",
):
    print(f"\n{text}\n  -> {generator.preprocess_text(text)}")
