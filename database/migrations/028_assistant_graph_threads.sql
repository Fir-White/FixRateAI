ALTER TABLE assistant_turns ADD COLUMN execution_engine text NOT NULL DEFAULT 'v2'
    CHECK (execution_engine IN ('v2', 'v3'));

CREATE SCHEMA IF NOT EXISTS assistant_checkpoints;

CREATE TABLE assistant_graph_threads (
    thread_id text PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES assistant_conversations(conversation_id) ON DELETE CASCADE
);
CREATE INDEX assistant_graph_threads_conversation_idx ON assistant_graph_threads(conversation_id);
