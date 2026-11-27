"""Turn-correlated diagnostics without prompts, arguments or provider payloads."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import re
from time import monotonic


logger = logging.getLogger('app.assistant.service')
_turn: ContextVar[str | None] = ContextVar('assistant_graph_trace_turn', default=None)


@contextmanager
def trace_turn(turn_id):
    token = _turn.set(str(turn_id))
    try:
        yield
    finally:
        _turn.reset(token)


def plan_route(path, reason, tools, catalog_tools):
    turn = _turn.get()
    if turn is None:
        return
    logger.info('assistant_graph_route turn=%s path=%s reason=%s authorized=%d offered=%d',
                turn, path, reason, len(tools), len(catalog_tools))
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug('assistant_graph_tools turn=%s authorized=%s offered=%s',
                     turn, sorted(tools), sorted(catalog_tools))


@contextmanager
def trace_inference(client, schema, budget):
    turn = _turn.get()
    if turn is None:
        yield
        return
    schema_name = schema.__name__ if schema else 'text'
    metrics = getattr(client, 'metrics', ())
    if not isinstance(metrics, (list, tuple)):
        metrics = ()
    before = len(metrics)
    started = monotonic()
    status = 'failed'
    logger.info('assistant_graph_inference_start turn=%s schema=%s max_tokens=%d', turn, schema_name, budget)
    try:
        yield
        status = 'completed'
    finally:
        model = getattr(client, 'response_model', None) or getattr(getattr(client, 'config', None), 'model_ref', None)
        model_ref = model if isinstance(model, str) and re.fullmatch(r'[\w:@./-]{1,200}', model) else 'unknown'
        attempts = metrics[before:]
        prompt = sum(row.get('prompt_eval_count', 0) for row in attempts) if attempts else None
        completion = sum(row.get('eval_count', 0) for row in attempts) if attempts else None
        logger.info('assistant_graph_inference turn=%s schema=%s status=%s model=%s seconds=%.4f requests=%s prompt_tokens=%s completion_tokens=%s',
                    turn, schema_name, status, model_ref, monotonic()-started, len(attempts) if attempts else None,
                    prompt, completion)
