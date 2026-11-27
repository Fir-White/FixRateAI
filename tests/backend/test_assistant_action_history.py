import json

from sqlalchemy import text

from tests.backend.test_assistant import (
    B, assistant_case, confirm, equipment_body, managed, proposal, rpc, runtime, thread,
)


def test_history_projects_confirmations_across_owned_conversations(assistant_case):
    engine, _, admin, _, ids = assistant_case
    first = thread(admin)
    second = thread(admin)
    rejected = proposal(admin, first, "equipment_create", {"body": equipment_body(ids)})
    completed = proposal(admin, second, "equipment_create", {"body": equipment_body(ids)})
    assert admin.post(B + f"/actions/{rejected['action_id']}/reject", json={}).status_code == 200
    assert confirm(admin, completed).status_code == 200
    assert confirm(admin, completed).status_code == 200
    waiting = proposal(admin, second, "equipment_create", {"body": equipment_body(ids)})
    expired = proposal(admin, second, "equipment_create", {"body": equipment_body(ids)})
    with engine.begin() as session:
        session.execute(text("""
            UPDATE assistant_actions
            SET expires_at=now()-interval '1 minute', result='{"message":"private marker"}'
            WHERE action_id=:identity
        """), {"identity": expired["action_id"]})

    response = admin.get(B + "/actions")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    result = response.json()
    assert result["total"] == 4
    assert result["actor"]
    assert [item["status"] for item in result["items"]] == ["expired", "proposed", "succeeded", "rejected"]
    assert [item["action_id"] for item in result["items"]] == [
        expired["action_id"], waiting["action_id"], completed["action_id"], rejected["action_id"],
    ]
    done = result["items"][2]
    assert done["conversation_id"] == second
    assert done["confirmed_at"] and done["finished_at"]
    assert done["verification"] == "confirmed"
    assert "arguments" not in done and "result" not in done and "private marker" not in response.text
    assert admin.get(B + "/actions?offset=3").json()["items"] == result["items"][3:]
    assert admin.get(B + "/actions?offset=-1").status_code == 422
    assert admin.chief.get(B + "/actions").json()["total"] == 0

    transported = rpc(admin, "tools/call", {"name": "assistant_action_history", "arguments": {}})
    assert not transported.json()["result"]["isError"]
    assert json.loads(transported.json()["result"]["content"][0]["text"])["total"] == 4

    params = {"site": ids["site"], "user": ids["user"]}
    with engine.begin() as session:
        session.execute(text("UPDATE site_memberships SET role='chief_engineer' WHERE site_id=:site AND user_id=:user"), params)
    try:
        assert admin.get(B + "/actions").json()["total"] == 0
    finally:
        with engine.begin() as session:
            session.execute(text("UPDATE site_memberships SET role='admin' WHERE site_id=:site AND user_id=:user"), params)
