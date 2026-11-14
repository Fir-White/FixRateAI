BEGIN;
CREATE TABLE assistant_attachments (
 attachment_id uuid PRIMARY KEY,
 conversation_id uuid NOT NULL REFERENCES assistant_conversations(conversation_id),
 original_name text NOT NULL CHECK(length(original_name) BETWEEN 1 AND 160),
 mime_type text NOT NULL, size_bytes bigint NOT NULL CHECK(size_bytes BETWEEN 1 AND 10485760),
 sha256 char(64) NOT NULL, storage_key text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(conversation_id,sha256,original_name)
);
CREATE INDEX assistant_attachments_owner ON assistant_attachments(conversation_id,created_at DESC);
COMMIT;
