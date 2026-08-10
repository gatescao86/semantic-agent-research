import json

from agents.router import DOMAIN_NAMES, _build_domain_list_text, _build_output_schema, route_question


class _FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text, stop_reason="end_turn", request_id="req_test123"):
        self.content = [_FakeTextBlock(text)]
        self.stop_reason = stop_reason
        self._request_id = request_id


class _FakeStreamCM:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get_final_message(self):
        return self._response


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeStreamCM(self._response)


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def test_domain_list_text_includes_every_configured_domain():
    text = _build_domain_list_text()
    for name in DOMAIN_NAMES:
        assert name in text


def test_output_schema_constrains_domains_to_known_names():
    schema = _build_output_schema()
    assert schema["schema"]["properties"]["domains"]["items"]["enum"] == DOMAIN_NAMES
    assert schema["schema"]["additionalProperties"] is False


def test_route_question_parses_structured_response():
    payload = {
        "domains": ["economic_indicators", "geography"],
        "reasoning": "Needs mortgage rate trend by metro area.",
        "ambiguous": False,
    }
    fake_client = _FakeClient(_FakeResponse(json.dumps(payload)))

    decision = route_question(fake_client, "What was the mortgage rate trend in Evansville?")

    assert decision.domains == ["economic_indicators", "geography"]
    assert decision.ambiguous is False
    assert decision.request_id == "req_test123"
    assert decision.latency_ms >= 0
    # sanity: the call actually requested structured output
    assert fake_client.messages.last_kwargs["output_config"]["format"]["type"] == "json_schema"


def test_route_question_handles_refusal():
    fake_client = _FakeClient(_FakeResponse("", stop_reason="refusal"))

    decision = route_question(fake_client, "some question")

    assert decision.domains == []
    assert decision.ambiguous is True
