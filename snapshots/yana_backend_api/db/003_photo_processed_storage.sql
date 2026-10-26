-- Хранение оригинала и безопасной обработанной копии фото отдельно.
-- Применять после db/001_init.sql и до загрузки новых фотографий.
BEGIN;

ALTER TABLE request_photos
    ADD COLUMN processed_storage_key TEXT;

UPDATE request_photos
SET processed_storage_key = storage_key
WHERE processed_storage_key IS NULL;

ALTER TABLE request_photos
    ALTER COLUMN processed_storage_key SET NOT NULL;

ALTER TABLE request_photos
    ADD CONSTRAINT request_photos_processed_storage_key_key
    UNIQUE (processed_storage_key);

COMMIT;
