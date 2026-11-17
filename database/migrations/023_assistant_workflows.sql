BEGIN;
-- Reply transport and user-goal outcome have independent lifecycles.
ALTER TABLE assistant_turns ADD COLUMN workflow jsonb;
ALTER TABLE assistant_turns ADD COLUMN resume_turn_id uuid REFERENCES assistant_turns(turn_id);
ALTER TABLE assistant_turns ADD CONSTRAINT assistant_workflow_object
 CHECK (workflow IS NULL OR jsonb_typeof(workflow)='object');
ALTER TABLE assistant_actions ADD COLUMN workflow_goal_id text;
ALTER TABLE assistant_actions ADD COLUMN workflow_root_turn_id uuid REFERENCES assistant_turns(turn_id);
CREATE UNIQUE INDEX assistant_action_workflow_goal
 ON assistant_actions(workflow_root_turn_id,workflow_goal_id)
 WHERE workflow_root_turn_id IS NOT NULL AND workflow_goal_id IS NOT NULL;
CREATE INDEX assistant_workflow_pending ON assistant_turns(conversation_id)
 WHERE workflow IS NOT NULL;
COMMIT;
