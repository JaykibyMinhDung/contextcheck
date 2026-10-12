"""TC-03: show the payload ContextCheck sends to OpenAI (no API key needed, nothing is sent)."""

from unittest.mock import patch

from contextcheck.endpoints.endpoint_config import EndpointConfig
from contextcheck.endpoints.factory import factory
from contextcheck.models.request import RequestBase

CREATE = (
    "contextcheck.connectors.connector_openai_compatible.openai_compatible.chat.completions.create"
)
FAKE = {
    "choices": [{"message": {"content": "ok"}}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
}

with patch(CREATE, return_value=FAKE) as create:
    for temperature in (0.7, 0.0):
        endpoint = factory(EndpointConfig(kind="openai", temperature=temperature, max_tokens=50))
        response = endpoint.send_request(RequestBase(message="Hello"))
        print(f"\nYAML temperature = {temperature}")
        print("  payload sent :", create.call_args.kwargs)
        print("  response     :", response.message, "| tokens:", response.stats.tokens_total)
