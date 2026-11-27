BEGIN;
-- Infrastructure singleton; organization data belongs in the database, never .env.
CREATE TABLE fixrate_installation (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    bootstrap_token_hash CHAR(64),
    completed_at TIMESTAMPTZ,
    organization_name TEXT,
    first_admin_id UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (completed_at IS NULL OR bootstrap_token_hash IS NULL)
);
-- An upgrade must never reopen first-install registration on an existing database.
INSERT INTO fixrate_installation(singleton,completed_at)
SELECT true, CASE WHEN EXISTS (SELECT 1 FROM users) THEN now() ELSE NULL END;
COMMIT;
