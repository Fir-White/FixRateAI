BEGIN;

WITH targets AS (
    SELECT source.source_import_id,
           (array_agg(DISTINCT rule.system_id))[1] AS system_id,
           min(edition.effective_from) AS effective_from
    FROM source_imports source
    JOIN regulation_editions edition
      ON edition.site_id=source.site_id AND edition.source_sha256=source.source_sha256
    JOIN maintenance_rules rule
      ON rule.site_id=edition.site_id AND rule.regulation_edition_id=edition.regulation_edition_id
    WHERE source.status='imported'
    GROUP BY source.source_import_id
    HAVING count(DISTINCT rule.system_id)=1 AND count(DISTINCT edition.effective_from)=1
)
UPDATE source_imports source
SET system_id=coalesce(source.system_id, targets.system_id),
    effective_from=coalesce(source.effective_from, targets.effective_from)
FROM targets
WHERE source.source_import_id=targets.source_import_id
  AND (source.system_id IS NULL OR source.effective_from IS NULL)
  AND (source.system_id IS NULL OR source.system_id=targets.system_id)
  AND (source.effective_from IS NULL OR source.effective_from=targets.effective_from);

INSERT INTO source_catalog_index
    (site_id,source_revision,source_sha256,source_ref,search_text,search_vector)
SELECT source.site_id,source.source_revision,source.source_sha256,
       entry.value->>'sourceRef', document.terms, to_tsvector('russian',document.terms)
FROM source_imports source
CROSS JOIN LATERAL jsonb_array_elements(source.source_rows->'rows') AS entry(value)
CROSS JOIN LATERAL (SELECT concat_ws(' ', entry.value->>'code', entry.value->>'title',
    entry.value->>'maintenanceType', entry.value->>'frequency', entry.value->>'normHours') AS terms) document
WHERE source.status='imported' AND entry.value->>'sourceRef' IS NOT NULL
ON CONFLICT (site_id,source_sha256,source_ref) DO NOTHING;

COMMIT;
