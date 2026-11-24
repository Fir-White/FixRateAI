"""A bounded, private projection of the existing confirmation records."""
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text

from .service import now
from .tools import TOOLS


PAGE_SIZE = 25
TITLES = {tool.name: tool.title for tool in TOOLS if tool.mode == "write"}


def _target_id(path):
    # Path parameters may refer to business entities. Never project the body,
    # model explanation, before snapshot, or arbitrary error text.
    for value in (path or {}).values():
        try:
            return str(UUID(str(value)))
        except ValueError:
            continue
    return None


def history(session, principal, offset):
    params = dict(site=principal.site_id, user=principal.user_id, role=principal.role,
                  offset=offset, limit=PAGE_SIZE)
    scope = """
        FROM assistant_actions a JOIN assistant_conversations c USING (conversation_id)
        WHERE c.site_id=:site AND c.user_id=:user AND c.role=:role
    """
    rows = session.execute(text("""
        SELECT a.action_id, a.conversation_id, a.tool_name, a.arguments->'path' AS target,
               a.status, a.created_at, a.expires_at, a.started_at, a.finished_at,
               a.result->'verification'->>'status' AS verification,
               a.result->'status_code' AS failure_code,
               c.title AS conversation_title
    """ + scope + """
        ORDER BY COALESCE(a.finished_at,a.started_at,a.created_at) DESC, a.action_id DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    total = session.scalar(text("SELECT count(*) " + scope), params)
    checked_at = now()
    items = []
    for row in rows:
        status = row["status"]
        if status == "proposed" and row["expires_at"] <= checked_at:
            status = "expired"
        elif status == "executing" and row["started_at"] and row["started_at"] < checked_at - timedelta(minutes=3):
            status = "uncertain"
        code = row["failure_code"]
        verification = row["verification"]
        items.append(dict(
            action_id=row["action_id"], conversation_id=row["conversation_id"],
            conversation_title=row["conversation_title"], title=TITLES.get(row["tool_name"], "Действие помощника"),
            target_id=_target_id(row["target"]), status=status,
            created_at=row["created_at"], confirmed_at=row["started_at"], finished_at=row["finished_at"],
            verification=verification if verification in {"confirmed", "failed", "unverified"} else None,
            failure_code=code if type(code) is int and 400 <= code <= 599 else None,
        ))
    return dict(items=items, total=total, offset=offset, limit=PAGE_SIZE, actor=principal.name)
