"""Resolve an explicitly named report target within the executor's assigned orders."""
import re

from sqlalchemy import text


_TITLE = re.compile(r'\bнаряд(?:а|у|е|ом)?\s*:?\s*(?:«([^«»\r\n]+)»|"([^"\r\n]+)")', re.IGNORECASE)
TARGET_REQUIRED = ('Не удалось однозначно выбрать доступный наряд. Укажите точный код, напишите `Наряд «Название»` '
                   'или откройте «Спросить ИИ по наряду».')
_CODES = re.compile(r'(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8})')


def named_order_references(question):
    return list(_TITLE.finditer(question))


def resolve_report_target(session, principal, question):
    names = named_order_references(question)
    if len(names) > 1:
        return None
    exact_title = (names[0][1] or names[0][2]).strip() if names else None
    if names and not exact_title:
        return None
    words = _TITLE.sub(' ', question).casefold().translate(str.maketrans(
        {symbol: ' ' for symbol in '/?#&=.,:;!?()[]{}«»„“”"\'`'})).split()
    codes = sorted({word for word in words if _CODES.fullmatch(word)})
    if exact_title is None and not codes:
        return None
    # Use the same title precedence as Views.operation. Check cardinality
    # across all assigned orders, not the model's current search page.
    rows = session.execute(text("""WITH targets AS (
        SELECT o.work_order_id,
            btrim(coalesce(nullif(o.operation_snapshot->>'title', ''), p.title, 'Работа')) = :title AS title_matches
        FROM work_orders o
        LEFT JOIN maintenance_rules r ON r.site_id=o.site_id AND r.maintenance_rule_id=o.maintenance_rule_id
        LEFT JOIN operation_templates p ON p.site_id=o.site_id AND p.operation_template_id=r.operation_template_id
        WHERE o.site_id=:site AND EXISTS (
            SELECT 1 FROM work_assignments a WHERE a.site_id=o.site_id AND a.work_order_id=o.work_order_id
                AND a.user_id=:user AND a.status NOT IN ('cancelled','declined')
        )
    )
    SELECT work_order_id, title_matches FROM targets
        WHERE title_matches OR CAST(work_order_id AS text)=ANY(:codes)
            OR left(CAST(work_order_id AS text),8)=ANY(:codes)
        LIMIT 2"""), dict(site=principal.site_id, user=principal.user_id, title=exact_title, codes=codes)).all()
    if len(rows) != 1 or (exact_title is not None and not rows[0].title_matches):
        return None
    return rows[0].work_order_id
