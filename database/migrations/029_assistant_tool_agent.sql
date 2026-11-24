ALTER TABLE assistant_turns DROP CONSTRAINT assistant_turns_execution_engine_check;
ALTER TABLE assistant_turns ADD CONSTRAINT assistant_turns_execution_engine_check
    CHECK (execution_engine IN ('v2', 'v3', 'v4'));
ALTER TABLE assistant_turns ADD COLUMN agent_context jsonb;
ALTER TABLE assistant_conversations ADD COLUMN subject_task_id uuid;
