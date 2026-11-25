"""Offline contract tests for per-item photo_required enforcement, assistant missing_report, and photo agent routing."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.assistant import model_catalog, task_execution, tool_agent
from app.assistant.tool_agent_tools import (
    PhotoAgentArgs,
    PhotoAgentObservation,
    ProposedPhotoReview,
    ToolSession,
)
from app.integration.photo_evidence import validate_submission_evidence
from tests.ml.test_cv import make_test_jpeg


def _item(item_id, *, required=True, photo_required=False):
    return {
        "id": str(item_id),
        "text": "Проверить состояние узла",
        "answerKind": "boolean",
        "unit": None,
        "required": required,
        "visualVerifiability": "visible",
        "photoRequired": photo_required,
    }


def test_per_item_photo_required_validation_rules():
    eq_1, eq_2 = uuid4(), uuid4()
    item_req, item_opt = uuid4(), uuid4()
    checklist = [_item(item_req, photo_required=True), _item(item_opt, photo_required=False)]
    answers = {str(item_req): "done", str(item_opt): "done"}

    # Missing required photo pair fails
    with pytest.raises(HTTPException) as exc:
        validate_submission_evidence(checklist, answers, [], {eq_1})
    assert exc.value.status_code == 422

    # Photos on optional item do NOT satisfy required item
    opt_pair = [
        SimpleNamespace(stage="before", checklist_item_id=item_opt, view_key="front", equipment_id=eq_1),
        SimpleNamespace(stage="after", checklist_item_id=item_opt, view_key="front", equipment_id=eq_1),
    ]
    with pytest.raises(HTTPException) as exc:
        validate_submission_evidence(checklist, answers, opt_pair, {eq_1})
    assert exc.value.status_code == 422

    # Different equipment fails
    wrong_eq = [
        SimpleNamespace(stage="before", checklist_item_id=item_req, view_key="front", equipment_id=eq_1),
        SimpleNamespace(stage="after", checklist_item_id=item_req, view_key="front", equipment_id=eq_2),
    ]
    with pytest.raises(HTTPException) as exc:
        validate_submission_evidence(checklist, answers, wrong_eq, {eq_1})
    assert exc.value.status_code == 422

    # Missing equipment_id on photos fails even when both before and after have None
    none_eq = [
        SimpleNamespace(stage="before", checklist_item_id=item_req, view_key="front", equipment_id=None),
        SimpleNamespace(stage="after", checklist_item_id=item_req, view_key="front", equipment_id=None),
    ]
    with pytest.raises(HTTPException) as exc:
        validate_submission_evidence(checklist, answers, none_eq, {eq_1})
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        validate_submission_evidence(checklist, answers, none_eq, set())
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        validate_submission_evidence(
            checklist,
            answers,
            [
                SimpleNamespace(stage="before", checklist_item_id=item_req, view_key="front", equipment_id=eq_1),
                SimpleNamespace(stage="after", checklist_item_id=item_req, view_key="front", equipment_id=eq_1),
            ],
            set(),
        )
    assert exc.value.status_code == 422

    # Different view_key fails
    wrong_view = [
        SimpleNamespace(stage="before", checklist_item_id=item_req, view_key="front", equipment_id=eq_1),
        SimpleNamespace(stage="after", checklist_item_id=item_req, view_key="side", equipment_id=eq_1),
    ]
    with pytest.raises(HTTPException) as exc:
        validate_submission_evidence(checklist, answers, wrong_view, {eq_1})
    assert exc.value.status_code == 422

    # Matching equipment, item, view_key, before+after passes
    valid_pair = [
        SimpleNamespace(stage="before", checklist_item_id=item_req, view_key="front", equipment_id=eq_1),
        SimpleNamespace(stage="after", checklist_item_id=item_req, view_key="front", equipment_id=eq_1),
    ]
    validate_submission_evidence(checklist, answers, valid_pair, {eq_1})

    # When photo_required=False on all items, submission succeeds with zero photos
    validate_submission_evidence([_item(item_opt, photo_required=False)], {str(item_opt): "done"}, [], {eq_1})


def test_task_execution_missing_report_requires_same_equipment_and_view():
    eq_1, eq_2 = str(uuid4()), str(uuid4())
    item_req = str(uuid4())
    item_opt = str(uuid4())
    task = {
        "equipmentId": eq_1,
        "equipmentIds": [eq_1],
        "actualRequired": False,
        "measurementRequirements": [],
        "requiredActs": [],
    }
    base_report = {
        "checklist": [
            {**_item(item_req, photo_required=True), "answer": "done"},
            {**_item(item_opt, photo_required=False), "answer": "done"},
        ],
        "actual": {},
        "readings": [],
        "acts": [],
    }

    # Mixed equipment on before/after MUST NOT satisfy photo requirement
    mixed_eq = task_execution.missing_report(
        task,
        {
            **base_report,
            "photos": [
                {"phase": "before", "checklistItemId": item_req, "viewKey": "front", "equipmentId": eq_1},
                {"phase": "after", "checklistItemId": item_req, "viewKey": "front", "equipmentId": eq_2},
            ],
        },
    )
    assert len(mixed_eq) == 1 and "фото до и после" in mixed_eq[0]

    # Foreign equipment pair MUST NOT satisfy photo requirement
    foreign_eq = task_execution.missing_report(
        task,
        {
            **base_report,
            "photos": [
                {"phase": "before", "checklistItemId": item_req, "viewKey": "front", "equipmentId": eq_2},
                {"phase": "after", "checklistItemId": item_req, "viewKey": "front", "equipmentId": eq_2},
            ],
        },
    )
    assert len(foreign_eq) == 1 and "фото до и после" in foreign_eq[0]

    # Photos without equipmentId MUST NOT satisfy photo requirement
    missing_eq = task_execution.missing_report(
        task,
        {
            **base_report,
            "photos": [
                {"phase": "before", "checklistItemId": item_req, "viewKey": "front", "equipmentId": None},
                {"phase": "after", "checklistItemId": item_req, "viewKey": "front", "equipmentId": None},
            ],
        },
    )
    assert len(missing_eq) == 1 and "фото до и после" in missing_eq[0]

    # Mismatched view_key MUST NOT satisfy photo requirement
    wrong_view = task_execution.missing_report(
        task,
        {
            **base_report,
            "photos": [
                {"phase": "before", "checklistItemId": item_req, "viewKey": "front", "equipmentId": eq_1},
                {"phase": "after", "checklistItemId": item_req, "viewKey": "side", "equipmentId": eq_1},
            ],
        },
    )
    assert len(wrong_view) == 1 and "фото до и после" in wrong_view[0]

    # Same equipment in order, same checklist item, same view_key, before + after MUST pass
    valid = task_execution.missing_report(
        task,
        {
            **base_report,
            "photos": [
                {"phase": "before", "checklistItemId": item_req, "viewKey": "front", "equipmentId": eq_1},
                {"phase": "after", "checklistItemId": item_req, "viewKey": "front", "equipmentId": eq_1},
            ],
        },
    )
    assert valid == []


def test_model_supports_vision_rejects_text_only_models():
    app = SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(photo_review_provider="aitunnel")))
    assert model_catalog.model_supports_vision(app, {"provider": "aitunnel", "model": "deepseek-chat", "supports_vision": False}) is False
    assert model_catalog.model_supports_vision(app, {"provider": "aitunnel", "model": "qwen3.7-flash", "supports_vision": True}) is True


def test_call_photo_agent_requires_real_image_bytes_and_handles_missing_vision(monkeypatch):
    app = SimpleNamespace(
        routes=[],
        state=SimpleNamespace(
            settings=SimpleNamespace(photo_review_provider="aitunnel"),
            photo_agent_provider_factory=None,
        ),
    )
    principal = SimpleNamespace(user_id=uuid4(), site_id=uuid4(), role="engineer")
    thread = {"conversation_id": uuid4(), "agent": "assistant"}
    session = ToolSession(app, principal, thread, uuid4(), {}, [], local_date=tool_agent.date.today())

    # Without any attachments or task_id, must refuse to inspect
    no_img = asyncio.run(session.call_photo_agent(PhotoAgentArgs(question="Что на фото?")))
    assert no_img["ok"] is False and no_img["status"] == "no_images" and no_img["inspected_count"] == 0

    # With a real attachment but missing AI Tunnel key, must return unavailable, never fake summary
    att_id = uuid4()
    session.files = {
        att_id: {"attachment_id": att_id, "mime_type": "image/jpeg", "original_name": "valve.jpg"}
    }
    monkeypatch.delenv("AITUNNEL_API_KEY", raising=False)
    monkeypatch.delenv("AI_TUNNEL_API_KEY", raising=False)
    jpeg = make_test_jpeg("clean_serviced")
    with (
        patch("app.assistant.tool_agent_tools.owned"),
        patch("app.assistant.tool_agent_tools.attachment_content", return_value=({"mime_type": "image/jpeg"}, jpeg)),
    ):
        unavail = asyncio.run(session.call_photo_agent(PhotoAgentArgs(attachment_ids=[att_id], question="Опиши")))
    assert unavail["ok"] is False and unavail["status"] == "unavailable" and unavail["inspected_count"] == 1

    # With a real vision-capable photo agent client, actual JPEG bytes reach the vision model
    seen = []

    class FakeVisionClient:
        def chat(self, messages, schema, tokens):
            seen.append(messages)
            return PhotoAgentObservation(
                summary="На снимке виден чистый корпус манометра без видимого налёта.",
                observations=["Вторая фотография для сравнения не приложена."],
            )

    app.state.photo_agent_provider_factory = lambda: FakeVisionClient()
    with (
        patch("app.assistant.tool_agent_tools.owned"),
        patch("app.assistant.tool_agent_tools.attachment_content", return_value=({"mime_type": "image/jpeg"}, jpeg)),
    ):
        ok_res = asyncio.run(session.call_photo_agent(PhotoAgentArgs(attachment_ids=[att_id], question="Что видно?")))
    assert ok_res.result["ok"] is True and ok_res.result["agent"] == "photo"
    assert len(seen) == 1 and len(seen[0][-1]["images"]) == 1
    assert ok_res.result["disclaimer"] == "Проверьте фотографии самостоятельно."


def test_propose_photo_review_passes_thread_dict_and_prevents_duplicates():
    from app.main import create_app

    pending_rows = []

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return iter(self._rows)

    class _FakeSession:
        def execute(self, statement, params=None):
            return _FakeResult(pending_rows)

    @contextmanager
    def _fake_factory():
        yield _FakeSession()

    app = create_app()
    app.state.factory = _fake_factory
    principal = SimpleNamespace(user_id=uuid4(), site_id=uuid4(), role="engineer")
    thread = {"conversation_id": uuid4(), "agent": "assistant"}
    tool_session = ToolSession(app, principal, thread, uuid4(), {}, [], local_date=tool_agent.date.today())
    task_id = uuid4()
    captured = []

    async def fake_backend(name, **kwargs):
        assert name == "task_read"
        return {
            "task": {"id": str(task_id), "code": str(task_id)[:8], "revision": 3},
            "allowedActions": ["photo_review"],
        }

    tool_session.backend = fake_backend
    action_id = uuid4()

    async def fake_propose(app_arg, session_arg, principal_arg, thread_arg, tool_arg, arguments, summary, headers, turn_id=None):
        captured.append({"thread": thread_arg, "arguments": arguments})
        return {"action_id": action_id, "status": "proposed"}

    with patch("app.assistant.tool_agent_tools.service.propose", side_effect=fake_propose):
        res = asyncio.run(
            tool_session.propose_photo_review(
                ProposedPhotoReview(task_id=task_id, expected_revision=3, comparability_confirmed=True)
            )
        )
        assert captured[0]["thread"] is thread
        assert captured[0]["arguments"]["body"]["comparability_confirmed"] is True
        assert tool_session.proposal == action_id
        assert res["action_id"] == str(action_id)
        assert res["status"] == "awaiting_confirmation"
        assert res["tool"] == "photo_review"
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                tool_session.propose_photo_review(
                    ProposedPhotoReview(task_id=task_id, expected_revision=3, comparability_confirmed=False)
                )
            )
        assert exc.value.status_code == 409

        # Cross-turn pending proposal with matching body MUST be reused without duplicate service.propose()
        pending_rows[:] = [
            {
                "action_id": action_id,
                "arguments": {"body": {"expected_revision": 3, "comparability_confirmed": True}},
            }
        ]
        next_turn_session = ToolSession(app, principal, thread, uuid4(), {}, [], local_date=tool_agent.date.today())
        next_turn_session.backend = fake_backend
        reused = asyncio.run(
            next_turn_session.propose_photo_review(
                ProposedPhotoReview(task_id=task_id, expected_revision=3, comparability_confirmed=True)
            )
        )
        assert reused["action_id"] == str(action_id)
        assert reused["reused"] is True
        assert next_turn_session.proposal == action_id
        assert len(captured) == 1

        # Different comparability_confirmed on a new turn creates a fresh proposal instead of reusing mismatched args
        other_turn_session = ToolSession(app, principal, thread, uuid4(), {}, [], local_date=tool_agent.date.today())
        other_turn_session.backend = fake_backend
        asyncio.run(
            other_turn_session.propose_photo_review(
                ProposedPhotoReview(task_id=task_id, expected_revision=3, comparability_confirmed=False)
            )
        )
        assert len(captured) == 2


def test_run_loop_blocks_raw_images_for_text_only_chat_model():
    seen_messages = []

    async def dispatch(name, args):
        return tool_agent.Observation(
            {"photos": [{"id": "1", "image_index": 1}]},
            images=("base64-jpeg",),
        )

    class CallsFirstClient:
        step = 0

        def tool_chat(self, messages, tools, tokens):
            seen_messages.append(messages)
            self.step += 1
            if self.step == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "c1", "function": {"name": "read_report_photos", "arguments": {}}}],
                }
            return {"role": "assistant", "content": "Готово."}

    specs = [{"function": {"name": "read_report_photos"}}]
    asyncio.run(
        tool_agent.run_loop(
            CallsFirstClient(),
            [{"role": "user", "content": "Проверь фото"}],
            specs,
            dispatch,
            lambda: None,
            vision_capable=False,
        )
    )
    # Never append raw images to text-only model turns
    assert all("images" not in msg for turn in seen_messages for msg in turn)


def test_photo_agent_observation_schema_marks_all_properties_required():
    schema = PhotoAgentObservation.model_json_schema()
    assert set(schema["properties"]).issubset(set(schema.get("required", ())))


def test_analyze_photo_review_accepts_single_optional_photo_and_rejects_invalid_equipment(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import hashlib
    from fastapi import FastAPI
    import sqlalchemy as sa
    from sqlalchemy.orm import registry
    from app.config import RuntimeSettings
    from app.integration.ml import MLCommand, register_ml_routes
    from tests.ml.test_local_vision import assessment

    app = FastAPI()
    app.state.settings = RuntimeSettings.from_environment()
    jpeg = make_test_jpeg("clean_serviced")
    photo_file = tmp_path / "photo.jpg"
    photo_file.write_bytes(jpeg)
    sha = hashlib.sha256(jpeg).hexdigest()
    task_id = uuid4()
    site_id = uuid4()
    report_id = uuid4()
    item_id = uuid4()
    eq_1, eq_2 = uuid4(), uuid4()
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    order = SimpleNamespace(
        work_order_id=task_id,
        site_id=site_id,
        status="in_review",
        revision=1,
        required_people_snapshot=1,
        norm_hours_snapshot=1.0,
        norm_hours_basis_snapshot="total_person_hours",
        operation_snapshot={
            "data_origin": "synthetic_demo",
            "maintenance_type": "ТО1",
            "code": "OP-1",
            "title": "Осмотр узла",
            "required_acts": [],
            "equipment_type": "pump",
        },
    )
    rule = SimpleNamespace(
        data_origin="synthetic_demo",
        operation_template_id=uuid4(),
        maintenance_rule_id=uuid4(),
        rule_version=1,
        publication_status="published",
        source_ref="synthetic-demo-source",
        operation=SimpleNamespace(code="OP-1", title="Осмотр узла", description="Осмотр"),
    )
    report = SimpleNamespace(
        work_report_id=report_id,
        revision_no=1,
        status="submitted",
        submitted_at=now,
        submitted_by=user_id,
        comment="Одно фото",
        execution_context={},
        checklist_snapshot=[_item(item_id, required=False, photo_required=False)],
    )
    predictor_table = sa.Table(
        "predictor_versions",
        sa.MetaData(),
        sa.Column("predictor_version_id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String()),
        sa.Column("name", sa.String()),
        sa.Column("version", sa.String()),
        sa.Column("artifact_ref", sa.String()),
    )
    mapper_registry = registry()

    @mapper_registry.mapped
    class PredictorVersion:
        __table__ = predictor_table

    predictor_cls = PredictorVersion

    def _make_photo(equipment_id):
        return SimpleNamespace(
            evidence_file_id=uuid4(),
            stage="after",
            checklist_item_id=item_id,
            view_key="front",
            equipment_id=equipment_id,
            file_size=len(jpeg),
            sha256=sha,
            mime_type="image/jpeg",
            captured_at=None,
            uploaded_at=now,
            uploaded_by=user_id,
        )

    class _FakeRepo:
        def __init__(self):
            self.added = []

        def add(self, table, **kwargs):
            self.added.append((table, kwargs))

    class _FakeSession:
        committed = False

        def execute(self, *args, **kwargs):
            return None

        def scalar(self, *args, **kwargs):
            return SimpleNamespace(predictor_version_id=uuid4())

        def commit(self):
            self.committed = True

    def _make_vault(photos):
        repo = _FakeRepo()
        session = _FakeSession()
        return SimpleNamespace(
            principal=SimpleNamespace(user_id=user_id, site_id=site_id, role="engineer"),
            models={"predictor_versions": predictor_cls},
            session=session,
            repo=repo,
            task=lambda tid, lock=False: order,
            operation=lambda o: (rule, None, None, False),
            rows=lambda table, **kw: {
                "work_reports": [report],
                "evidence_files": photos,
                "checklist_results": [],
                "work_readings": [],
            }[table],
        )

    register_ml_routes(
        app,
        lambda: None,
        lambda photo: photo_file,
        lambda *roles: None,
        lambda o, rev: None,
    )
    endpoint = next(
        r.endpoint
        for r in app.routes
        if getattr(r, "path", None) == "/api/v1/maintenance/tasks/{task_id}/photo-review"
    )

    # 1. Bound photos without equipment_id MUST return 422 rather than triggering ValidationError (500)
    with pytest.raises(HTTPException) as missing_eq_exc:
        endpoint(task_id, MLCommand(expected_revision=1), v=_make_vault([_make_photo(None)]))
    assert missing_eq_exc.value.status_code == 422

    # 2. Mixed equipment_id across bound photos MUST return 422
    with pytest.raises(HTTPException) as mixed_eq_exc:
        endpoint(task_id, MLCommand(expected_revision=1), v=_make_vault([_make_photo(eq_1), _make_photo(eq_2)]))
    assert mixed_eq_exc.value.status_code == 422

    # 3. Single valid optional photo validates through PhotoReviewRequest and runs assess_single cleanly
    monkeypatch.setenv("AITUNNEL_API_KEY", "test-key")
    single_calls = []

    def fake_assess_single(self, request, item, blob, phase):
        single_calls.append((len(request.photos), phase))
        return assessment(
            conclusion="insufficient_evidence",
            comparable="uncertain",
            summary="Проверено одиночное фото после выполнения.",
        )

    vault_ok = _make_vault([_make_photo(eq_1)])
    with patch("ml_service.app.cv.aitunnel.AITunnelVisionClient.assess_single", fake_assess_single):
        res = endpoint(task_id, MLCommand(expected_revision=1), v=vault_ok)
    assert single_calls == [(1, "after")]
    assert res["status"] == "uncertain"
    assert len(res["items"]) == 1
    assert vault_ok.session.committed is True
