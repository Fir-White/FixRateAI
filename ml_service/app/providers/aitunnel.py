"""Bounded AI Tunnel transport. No redirects, retries, response-body logs or client secrets."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from http.client import IncompleteRead, RemoteDisconnected
import math
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from pydantic import ValidationError

DEFAULT_MODEL = "qwen3.7-flash"
MAX_RESPONSE_BYTES = 1_048_576


class AITunnelFailure(Exception):
    """Only stable non-secret codes cross the provider boundary."""

    def __init__(self, code, *, reason=None):
        super().__init__(code)
        self.reason = reason


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AITunnelFailure("AITUNNEL_REDIRECT_REJECTED")


@dataclass(frozen=True)
class AITunnelConfig:
    model: str
    api_key: str = field(repr=False)
    base_url: str = "https://api.aitunnel.ru/v1"
    timeout: float = 90.0
    reasoning_effort: str = "none"
    allow_model_alias: bool = False

    @classmethod
    def from_environment(cls, tool="vision", environment=None):
        values = os.environ if environment is None else environment
        base = values.get("AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1/").rstrip("/")
        parsed = urlsplit(base)
        if (parsed.scheme != "https" or parsed.hostname != "api.aitunnel.ru" or parsed.port not in (None, 443)
                or parsed.username or parsed.password or parsed.path != "/v1" or parsed.query or parsed.fragment):
            raise ValueError("AITUNNEL_BASE_URL must be https://api.aitunnel.ru/v1/")
        model = values.get("AITUNNEL_" + tool.upper() + "_MODEL", DEFAULT_MODEL).strip()
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}", model):
            raise ValueError("Invalid AITUNNEL model identifier")
        key = (values.get("AITUNNEL_API_KEY") or values.get("AI_TUNNEL_API_KEY") or "").strip()
        if any(c.isspace() for c in key) or len(key) > 4096:
            raise ValueError("Invalid AITUNNEL_API_KEY format")
        try:
            timeout = float(values.get("AITUNNEL_TIMEOUT_SECONDS", "90"))
        except ValueError:
            raise ValueError("AITUNNEL_TIMEOUT_SECONDS must be a number") from None
        if not math.isfinite(timeout) or not 0 < timeout <= 110:
            raise ValueError("AITUNNEL_TIMEOUT_SECONDS must be in (0, 110]")
        effort = values.get("AITUNNEL_REASONING_EFFORT", "none").strip()
        if effort not in ("none", "low", "medium", "high"):
            raise ValueError("Invalid AITUNNEL_REASONING_EFFORT")
        return cls(model=model, api_key=key, base_url=base, timeout=timeout, reasoning_effort=effort,allow_model_alias=model=='auto')

    @property
    def model_ref(self):
        # Cloud aliases are not downloadable weight digests. Keep the provider explicit.
        return "aitunnel:" + self.model


class AITunnelClient:
    supports_dialogue_routing = True
    supports_semantic_plan = True
    supports_request_coverage = True
    def __init__(self, config):
        self.config = config
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.deadline = time.monotonic() + config.timeout
        self.response_model = None
        self.response_diagnostics = []

    def chat(self, messages, schema, tokens, *, tools=None):
        diagnostic = {"schema": schema.__name__ if schema else "tools" if tools is not None else "text",
                      "max_tokens": tokens, "stage": "request"}
        self.response_diagnostics.append(diagnostic)
        if not self.config.api_key:
            raise AITunnelFailure("AITUNNEL_NOT_CONFIGURED")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AITunnelFailure("AITUNNEL_TIMEOUT")
        # images in the shared vision pipeline become OpenAI-compatible multipart content.
        converted = []
        for message in messages:
            content = message["content"]
            if message.get("images"):
                content = [{"type": "text", "text": content}, *[
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}}
                    for data in message["images"]]]
            entry = {"role": message["role"], "content": content}
            if tools is not None and message["role"] == "assistant" and message.get("tool_calls"):
                entry["tool_calls"] = [
                    {"id": call["id"], "type": "function", "function": {
                        "name": call["function"]["name"],
                        "arguments": json.dumps(call["function"]["arguments"], ensure_ascii=False)}}
                    for call in message["tool_calls"]]
            if tools is not None and message["role"] == "tool":
                entry["tool_call_id"] = message["tool_call_id"]
            converted.append(entry)
        instructions = "\n\n".join(message["content"] for message in converted if message["role"] == "system")
        converted = [message for message in converted if message["role"] != "system"]
        output_instructions = ("\n\n" +
            "Return exactly ONE JSON OBJECT matching this schema. Never return a JSON array or Markdown. "
            "Use exactly the property names from the schema; never translate property names. "
            "Include every required field. Empty lists must be [], not null. "
            "Respond in Russian only for descriptive string VALUES. JSON schema: " + json.dumps(schema.model_json_schema(), ensure_ascii=False)) if schema else ""
        converted.insert(0, {"role": "system", "content": instructions + output_instructions})
        payload = {"model": self.config.model, "messages": converted, "stream": False,
                   "max_tokens": tokens, "include_reasoning": False,
                   "reasoning": {"effort": self.config.reasoning_effort}}
        if schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "strict": True, "schema": schema.model_json_schema()}}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = Request(self.config.base_url + "/chat/completions",
                          data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.config.api_key})
        try:
            with self.opener.open(request, timeout=remaining) as response:
                headers = getattr(response, 'headers', {})
                diagnostic['billing'] = 'request_identified' if headers.get('X-Request-Id') else 'unknown'
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            diagnostic.update(stage="envelope", response_bytes=len(raw))
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE")
            envelope = json.loads(raw)
            if isinstance(envelope, dict) and isinstance(envelope.get('id'), str) and envelope['id']:
                diagnostic['billing'] = 'request_identified'
            choices = envelope["choices"]
            diagnostic["stage"] = "choices"
            if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict):
                reason = choices[0].get("finish_reason")
                diagnostic["finish_reason"] = reason if reason in ("stop", "length", "content_filter", "tool_calls", "function_call") else "unknown"
            allowed_reasons = ("stop", "tool_calls") if tools else ("stop",)
            if not isinstance(choices, list) or len(choices) != 1 or choices[0].get("finish_reason") not in allowed_reasons:
                raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE")
            diagnostic["stage"] = "message"
            message = choices[0]["message"]
            if message.get("refusal"):
                raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE", reason='refusal')
            if not isinstance(message.get("content"), str) and not (tools and message.get("tool_calls")):
                raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE", reason='invalid_message')
            diagnostic["content_characters"] = len(message.get("content") or "")
            diagnostic["stage"] = "model"
            actual_model = envelope.get("model")
            if not isinstance(actual_model, str) or not actual_model or len(actual_model) > 200:
                raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE")
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,199}", actual_model):
                raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE")
            if not self.config.allow_model_alias and actual_model != self.config.model and not actual_model.startswith(self.config.model + "-"):
                raise AITunnelFailure("AITUNNEL_MODEL_MISMATCH")
            diagnostic["stage"] = "schema"
            if tools is not None:result = message
            elif schema:result = schema.model_validate_json(message["content"])
            else:
                result = message["content"].strip()
                if not result or len(result)>32000:raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE")
            diagnostic["stage"] = "validated"
            self.response_model = actual_model
            return result
        except AITunnelFailure as exc:
            diagnostic["error_code"] = str(exc)
            if exc.reason:
                diagnostic['reason'] = exc.reason
            raise
        except HTTPError as exc:
            code = {401: "AITUNNEL_AUTH_FAILED", 403: "AITUNNEL_AUTH_FAILED", 402: "AITUNNEL_QUOTA_EXCEEDED",
                    429: "AITUNNEL_RATE_LIMITED", 404: "AITUNNEL_MODEL_UNAVAILABLE"}.get(exc.code,
                    "AITUNNEL_INVALID_REQUEST" if 400 <= exc.code < 500 else "AITUNNEL_UNAVAILABLE")
            raise AITunnelFailure(code) from None
        except (IncompleteRead, RemoteDisconnected):
            diagnostic.update(reason='transport', error_code='AITUNNEL_UNAVAILABLE')
            diagnostic.setdefault('billing', 'unknown')
            raise AITunnelFailure('AITUNNEL_UNAVAILABLE', reason='transport') from None
        except TimeoutError:
            diagnostic.update(reason='timeout', error_code='AITUNNEL_TIMEOUT')
            diagnostic.setdefault('billing', 'unknown')
            raise AITunnelFailure("AITUNNEL_TIMEOUT", reason='timeout') from None
        except (URLError, OSError) as exc:
            code = "AITUNNEL_TIMEOUT" if isinstance(getattr(exc, "reason", None), TimeoutError) else "AITUNNEL_UNAVAILABLE"
            reason = 'timeout' if code == 'AITUNNEL_TIMEOUT' else 'transport'
            diagnostic.update(reason=reason, error_code=code)
            diagnostic.setdefault('billing', 'unknown')
            raise AITunnelFailure(code, reason=reason) from None
        except ValidationError as exc:
            fields = set(schema.model_fields)
            diagnostic["validation_errors"] = [
                {"type": issue["type"], "location": [part if isinstance(part, int) or part in fields else "unknown_field" for part in issue["loc"]]}
                for issue in exc.errors(include_input=False, include_context=False, include_url=False)[:8]
            ]
            reason = 'output_json' if any(issue['type'] == 'json_invalid' for issue in diagnostic['validation_errors']) else 'output_schema'
            diagnostic.update(reason=reason, error_code='AITUNNEL_INVALID_RESPONSE')
            raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE", reason=reason) from None

        except json.JSONDecodeError:
            diagnostic.update(reason='transport_json', error_code='AITUNNEL_INVALID_RESPONSE')
            raise AITunnelFailure('AITUNNEL_INVALID_RESPONSE', reason='transport_json') from None
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            diagnostic["error_code"] = "AITUNNEL_INVALID_RESPONSE"
            raise AITunnelFailure("AITUNNEL_INVALID_RESPONSE") from None

    def assistant_chat(self, messages, schema, tokens):
        """Retry inference once inside the same deadline before dispatching any tool calls."""
        try:
            return self.chat(messages, schema, tokens)
        except AITunnelFailure as exc:
            if exc.reason not in ('transport', 'output_json', 'output_schema') or self.deadline-time.monotonic() < 8:
                raise
            self.response_diagnostics[-1]['repair_requested'] = True
            if exc.reason != 'transport':
                instructions = ('Return one complete JSON object matching the schema. '
                                'For arguments_json use a string containing a valid complete JSON object, such as "{}". '
                                'Keep the original request and parameters.')
                messages = [*messages, {'role': 'system', 'content': instructions}]
        return self.chat(messages, schema, tokens)

    def text(self, messages, tokens=8192):
        """User-facing prose shares the same deadline, envelope checks and privacy rules."""
        return self.chat(messages, None, tokens)

    def tool_chat(self, messages, tools, tokens):
        return self.chat(messages, None, tokens, tools=tools)
