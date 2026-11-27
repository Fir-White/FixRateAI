"""Replay safe, representative provider envelopes without network or tool calls."""
from http.client import RemoteDisconnected
from io import BytesIO
import json

import pytest

from app.schemas.assistant import AgentStep
from ml_service.app.providers.aitunnel import AITunnelClient, AITunnelConfig, AITunnelFailure
from ml_service.app.providers.ollama import decode_agent_wire


def envelope(model, content, *, refusal=None):
    return {'id': 'synthetic-request', 'model': model, 'choices': [
        {'finish_reason': 'stop', 'message': {'content': content, 'refusal': refusal}}]}


def executable(arguments):
    return json.dumps({'answer': '', 'calls': [{'tool': 'task_read', 'goal_id': 'read',
        'arguments_json': arguments, 'explanation': 'Чтение карточки'}]})


class Replay:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(json.loads(request.data))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return BytesIO(json.dumps(value).encode())


def client(model, *responses):
    provider = AITunnelClient(AITunnelConfig(model=model, api_key='offline-fixture'))
    provider.opener = Replay(responses)
    return provider


def test_c_s22_structured_output_requires_new_validated_arguments():
    model = 'glm-5.3'
    provider = client(model, envelope(model, executable('{')), envelope(model, executable('{"path":{}}')))
    result = provider.assistant_chat([], AgentStep, 800)
    assert result.calls[0].arguments == {'path': {}}
    assert [request['model'] for request in provider.opener.requests] == [model, model]
    assert provider.response_diagnostics[0]['reason'] == 'output_schema'
    assert provider.response_diagnostics[0]['repair_requested'] is True
    invalid = client(model, *[envelope(model, executable('{'))]*2)
    with pytest.raises(AITunnelFailure, match='AITUNNEL_INVALID_RESPONSE'):
        invalid.assistant_chat([], AgentStep, 800)
    assert len(invalid.opener.requests) == 2 and invalid.response_model is None


def test_s03_disconnect_billing_unknown_and_recovery_preserves_model():
    model = 'deepseek-v4.1-flash-1017'
    provider = client(model, RemoteDisconnected(), envelope(model, executable('{}')))
    result = provider.assistant_chat([], AgentStep, 800)
    assert len(result.calls) == 1 and provider.response_model == model
    assert provider.opener.requests[0] == provider.opener.requests[1]
    assert provider.response_diagnostics[0]['billing'] == 'unknown'
    assert provider.response_diagnostics[0]['reason'] == 'transport'
    assert provider.response_diagnostics[1]['billing'] == 'request_identified'


def test_refusal_is_distinct_and_never_retried():
    model = 'glm-5.3'
    provider = client(model, envelope(model, '', refusal='refused'))
    with pytest.raises(AITunnelFailure) as error:
        provider.assistant_chat([], AgentStep, 800)
    assert error.value.reason == 'refusal' and len(provider.opener.requests) == 1


def test_qwen_wire_object_normalizes_to_the_same_pydantic_contract():
    result = decode_agent_wire(AgentStep, executable({'path': {}}), {'task_read': 'read'})
    assert result.calls[0].arguments == {'path': {}}
