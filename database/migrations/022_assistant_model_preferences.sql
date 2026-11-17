BEGIN;
CREATE TABLE assistant_model_preferences (
 user_id uuid NOT NULL REFERENCES users(user_id),
 site_id uuid NOT NULL REFERENCES sites(site_id),
 role text NOT NULL CHECK(role IN ('director','chief_engineer','engineer','dispatcher','admin','executor')),
 provider text NOT NULL CHECK(provider IN ('ollama','aitunnel')),
 model text NOT NULL CHECK(length(model) BETWEEN 1 AND 128),
 digest text,
 is_alias boolean NOT NULL DEFAULT false,
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,site_id,role),
 CHECK((provider='ollama' AND digest IS NOT NULL AND digest ~ '^sha256:[0-9a-f]{64}$') OR (provider='aitunnel' AND digest IS NULL)),
 CHECK(NOT is_alias OR provider='aitunnel')
);
ALTER TABLE assistant_turns ADD COLUMN model_selection jsonb;
ALTER TABLE assistant_turns ADD COLUMN deadline_at timestamptz;
ALTER TABLE assistant_turns ADD CONSTRAINT assistant_turn_model_selection_object
 CHECK(model_selection IS NULL OR jsonb_typeof(model_selection)='object');
COMMIT;
