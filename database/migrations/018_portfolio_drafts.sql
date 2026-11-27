BEGIN;
-- A real regulation portfolio is not an Excel import. Keep old rows untouched.
ALTER TABLE planning_draft_versions ALTER COLUMN import_id DROP NOT NULL;
ALTER TABLE planning_draft_versions ADD CONSTRAINT planning_draft_source_kind CHECK ((
    (coalesce(source_snapshot->'input'->>'kind','catalog')='catalog' AND import_id IS NOT NULL)
    OR (source_snapshot->'input'->>'kind'='portfolio' AND import_id IS NULL
        AND coalesce(summary->>'source_kind','')='portfolio')
) IS TRUE);
CREATE INDEX planning_draft_versions_portfolio ON planning_draft_versions(site_id,created_at DESC)
    WHERE import_id IS NULL;
COMMIT;
