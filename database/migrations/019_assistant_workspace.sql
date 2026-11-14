BEGIN;
CREATE TABLE assistant_conversations (
 conversation_id uuid PRIMARY KEY, site_id uuid NOT NULL REFERENCES sites(site_id),
 user_id uuid NOT NULL REFERENCES users(user_id), role text NOT NULL CHECK(role IN ('director','chief_engineer','engineer','dispatcher','admin','executor')),
 title text NOT NULL CHECK(length(title)<=160),
 agent text NOT NULL CHECK(agent IN ('assistant','planner','photo')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX assistant_conversations_owner ON assistant_conversations(site_id,user_id,role,updated_at DESC);
CREATE TABLE assistant_turns (
 turn_id uuid PRIMARY KEY, conversation_id uuid NOT NULL REFERENCES assistant_conversations(conversation_id),
 request_key uuid NOT NULL, content text NOT NULL CHECK(length(content) BETWEEN 1 AND 12000),
 status text NOT NULL CHECK(status IN ('running','completed','failed')),
 answer text NOT NULL DEFAULT '', error_code text, model_ref text, prompt_version text NOT NULL,
 trace jsonb NOT NULL DEFAULT '[]', created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 UNIQUE(conversation_id,request_key)
);
CREATE INDEX assistant_turns_page ON assistant_turns(conversation_id,created_at DESC,turn_id);
CREATE TABLE assistant_actions (
 action_id uuid PRIMARY KEY, conversation_id uuid NOT NULL REFERENCES assistant_conversations(conversation_id),
 turn_id uuid REFERENCES assistant_turns(turn_id), tool_name text NOT NULL,
 arguments jsonb NOT NULL, payload_sha256 char(64) NOT NULL, before_snapshot jsonb,
 explanation text NOT NULL CHECK(length(explanation)<=3000),
 status text NOT NULL CHECK(status IN ('proposed','rejected','executing','succeeded','failed','uncertain','stale')),
 result jsonb, created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 started_at timestamptz, finished_at timestamptz
);
CREATE INDEX assistant_actions_conversation ON assistant_actions(conversation_id,created_at DESC);
COMMIT;
