-- Session table for user authentication.
-- Applied after 001_tl02.sql.

BEGIN;

CREATE TABLE sessions (
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    csrf_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    revoked_at TIMESTAMPTZ,
    PRIMARY KEY (session_id),
    UNIQUE (csrf_token),
    CHECK (expires_at > created_at)
);

CREATE INDEX idx_sessions_user_id ON sessions (user_id);
CREATE INDEX idx_sessions_user_active ON sessions (user_id, expires_at);

ALTER TABLE sessions ADD CONSTRAINT fk_sessions_user
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE;

COMMIT;
