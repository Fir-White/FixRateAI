-- FixRate AI · reproducible catalog/search queries.
-- Apply 001_init.sql, 002_seed_demo.sql and 003_normative_source_versions.sql.
-- The first queries return rows from the DEMO seed; replace literals with bound
-- parameters in backend repositories. No query mutates data.

-- 1. Exact rate code with its concrete source edition.
-- Expected after DEMO seed: one DEMO-FACADE-CRACK-01 row, edition 2026.1.
SELECT r.rate_id, r.rate_code, r.work_name, r.unit_code,
       r.rate_unit_multiplier, r.base_price, r.currency,
       s.source_id, s.source_series_id, s.source_type, s.title,
       s.edition, s.region, s.is_verified, s.is_current
  FROM rates r
  JOIN norm_sources s ON s.source_id = r.source_id
 WHERE r.rate_code = 'DEMO-FACADE-CRACK-01';

-- 2. Lexical search by a part of the work name (PostgreSQL FTS, not BM25).
-- Expected after DEMO seed: one facade-crack row with a positive rank.
SELECT r.rate_id, r.rate_code, r.work_name, ts_rank(
           to_tsvector('russian', r.work_name),
           plainto_tsquery('russian', 'трещина фасада')
       ) AS rank
  FROM rates r
 WHERE to_tsvector('russian', r.work_name)
       @@ plainto_tsquery('russian', 'трещина фасада')
 ORDER BY rank DESC, r.rate_code;

-- 3. Region and source-type filter.
-- Expected after DEMO seed: three rows for Свердловская область / DEMO.
SELECT r.rate_code, r.work_name, s.region, s.source_type, s.edition
  FROM rates r
  JOIN norm_sources s ON s.source_id = r.source_id
 WHERE s.region = 'Свердловская область'
   AND s.source_type = 'DEMO'
 ORDER BY r.rate_code;

-- 4. All rates from a concrete edition.
-- Expected after DEMO seed: three rows belonging to edition 2026.1.
SELECT r.rate_code, r.work_name, r.base_price, r.currency
  FROM rates r
 WHERE r.source_id = 'd0000000-0000-4000-8000-000000000001'
 ORDER BY r.rate_code;

-- 5. Recommended editions and active rates. The partial UNIQUE index guarantees
-- at most one is_current row inside a source series; applicability dates remain
-- visible so the caller can apply an explicit calculation date.
-- Expected after DEMO seed: three active rates from the one current source.
SELECT s.source_series_id, s.source_id, s.title, s.edition,
       s.region, s.effective_date, s.valid_to,
       r.rate_id, r.rate_code, r.base_price, r.currency
  FROM norm_sources s
  JOIN rates r ON r.source_id = s.source_id
 WHERE s.is_current
   AND r.is_active
 ORDER BY s.title, r.rate_code;

-- 6. Edition valid on a requested calculation date. If this returns multiple
-- rows, selection is ambiguous and must be resolved explicitly, never guessed.
-- Expected after DEMO seed: one edition; its open period includes the date.
SELECT s.*
  FROM norm_sources s
 WHERE s.source_series_id = (
       SELECT source_series_id FROM norm_sources
        WHERE source_id = 'd0000000-0000-4000-8000-000000000001'
   )
   AND DATE '2026-10-22' >= COALESCE(s.effective_date, '-infinity'::date)
   AND DATE '2026-10-22' <= COALESCE(s.valid_to, 'infinity'::date)
 ORDER BY s.effective_date DESC NULLS LAST;

-- 7. Canonical source/rate snapshot to persist in estimate_items.source_snapshot.
-- Expected after DEMO seed: one JSON object with origin=demo and price 850 RUB.
SELECT fixrate_rate_snapshot('d1000000-0000-4000-8000-000000000001');

-- 8. Restore the accepted historical price without consulting mutable catalog
-- values. The placeholder UUID returns zero rows on DEMO seed; bind a real
-- item_id in application code.
SELECT ei.item_id, ei.work_name, ei.quantity, ei.unit_code, ei.unit_price,
       ei.coefficient, ei.base_cost, ei.total_cost,
       ei.source_snapshot ->> 'source_title' AS source_title,
       ei.source_snapshot ->> 'source_version' AS source_version,
       ei.source_snapshot ->> 'rate_code' AS original_rate_code,
       (ei.source_snapshot ->> 'base_price')::NUMERIC AS original_base_price,
       ei.source_snapshot ->> 'currency' AS original_currency
  FROM estimate_items ei
 WHERE ei.item_id = '00000000-0000-0000-0000-000000000000';

-- 9. Compare editions of the same rate code inside one source series.
-- Expected after DEMO seed: one row; the version test creates two rows.
SELECT s.source_series_id, s.edition, s.effective_date, s.valid_to,
       s.is_current, r.rate_code, r.base_price, r.currency
  FROM norm_sources s
  JOIN rates r ON r.source_id = s.source_id
 WHERE s.source_series_id = (
       SELECT source_series_id FROM norm_sources
        WHERE source_id = 'd0000000-0000-4000-8000-000000000001'
   )
   AND r.rate_code = 'DEMO-FACADE-CRACK-01'
 ORDER BY s.effective_date, s.edition;

-- 10. Audit incomplete provenance. Any returned active row requires correction
-- before it may participate in an accepted estimate.
-- Expected after DEMO seed: zero rows.
SELECT r.rate_id, r.rate_code, s.source_id, s.source_type,
       CASE
         WHEN COALESCE(NULLIF(btrim(s.edition), ''), s.effective_date::text) IS NULL
           THEN 'missing source version'
         WHEN r.base_price IS NULL THEN 'missing price'
         WHEN r.currency IS NULL THEN 'missing currency'
         WHEN s.source_type IN ('FER','FERR','TER','TERR','COMMERCIAL')
              AND NOT s.is_verified THEN 'unverified source'
         WHEN s.source_type = 'COMMERCIAL' AND s.provider_name IS NULL
           THEN 'missing provider'
       END AS problem
  FROM rates r
  JOIN norm_sources s ON s.source_id = r.source_id
 WHERE r.is_active
   AND (
       COALESCE(NULLIF(btrim(s.edition), ''), s.effective_date::text) IS NULL
       OR r.base_price IS NULL
       OR r.currency IS NULL
       OR (s.source_type IN ('FER','FERR','TER','TERR','COMMERCIAL') AND NOT s.is_verified)
       OR (s.source_type = 'COMMERCIAL' AND s.provider_name IS NULL)
   )
 ORDER BY s.source_id, r.rate_code;
