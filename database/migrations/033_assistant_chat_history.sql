BEGIN;
ALTER TABLE assistant_conversations
    ADD COLUMN pinned_at timestamptz,
    ADD COLUMN title_manually_set boolean NOT NULL DEFAULT false;
CREATE INDEX assistant_conversations_history
    ON assistant_conversations(site_id,user_id,role,pinned_at DESC NULLS LAST,updated_at DESC,conversation_id);
COMMIT;
