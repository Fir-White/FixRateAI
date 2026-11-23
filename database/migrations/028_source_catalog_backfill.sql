BEGIN;

UPDATE source_imports
SET catalog_revision = COALESCE(catalog_revision, source_revision)
WHERE catalog_revision IS NULL;

COMMIT;
