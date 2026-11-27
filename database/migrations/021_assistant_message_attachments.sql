BEGIN;
ALTER TABLE assistant_turns ADD CONSTRAINT assistant_turns_conversation_identity UNIQUE(turn_id,conversation_id);
ALTER TABLE assistant_attachments ADD CONSTRAINT assistant_attachments_conversation_identity UNIQUE(attachment_id,conversation_id);
CREATE TABLE assistant_turn_attachments (
 turn_id uuid NOT NULL,
 attachment_id uuid NOT NULL,
 conversation_id uuid NOT NULL,
 position smallint NOT NULL CHECK(position BETWEEN 0 AND 19),
 inferred_legacy boolean NOT NULL DEFAULT false,
 PRIMARY KEY(turn_id,attachment_id),
 UNIQUE(turn_id,position),
 FOREIGN KEY(turn_id,conversation_id) REFERENCES assistant_turns(turn_id,conversation_id) ON DELETE CASCADE,
 FOREIGN KEY(attachment_id,conversation_id) REFERENCES assistant_attachments(attachment_id,conversation_id) ON DELETE CASCADE
);
CREATE INDEX assistant_turn_attachments_file ON assistant_turn_attachments(attachment_id);
-- The old transport sent every staged file's metadata with the next message.
-- Preserve that historical association explicitly, marked as inferred. Files
-- uploaded after the last message remain pending; old files are not re-sent.
WITH historical AS (
 SELECT a.attachment_id,a.conversation_id,a.created_at,t.turn_id
 FROM assistant_attachments a
 JOIN LATERAL (
   SELECT turn_id FROM assistant_turns
   WHERE conversation_id=a.conversation_id AND created_at>=a.created_at
   ORDER BY created_at,turn_id LIMIT 1
 ) t ON true
)
INSERT INTO assistant_turn_attachments(turn_id,attachment_id,conversation_id,position,inferred_legacy)
 SELECT turn_id,attachment_id,conversation_id,
        (row_number() OVER (PARTITION BY turn_id ORDER BY created_at,attachment_id)-1)::smallint,true
 FROM historical;
COMMIT;
