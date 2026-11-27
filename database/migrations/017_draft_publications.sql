BEGIN;
CREATE TABLE draft_publication_proposals (
    proposal_id UUID PRIMARY KEY,
    site_id UUID NOT NULL,
    draft_id UUID NOT NULL,
    base_revision INTEGER NOT NULL,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 2000),
    scope_note TEXT NOT NULL CHECK(length(trim(scope_note)) BETWEEN 1 AND 2000),
    state TEXT NOT NULL DEFAULT 'prepared' CHECK(state IN ('prepared','approved','rejected','published')),
    proposal_digest CHAR(64) NOT NULL,
    source_digest CHAR(64) NOT NULL,
    resource_digest CHAR(64) NOT NULL,
    input_snapshot JSONB NOT NULL CHECK(jsonb_typeof(input_snapshot)='object'),
    items JSONB NOT NULL CHECK(jsonb_typeof(items)='array'),
    obligation_keys JSONB NOT NULL CHECK(jsonb_typeof(obligation_keys)='array'),
    summary JSONB NOT NULL CHECK(jsonb_typeof(summary)='object'),
    validation_snapshot JSONB NOT NULL CHECK(jsonb_typeof(validation_snapshot)='object'),
    blockers JSONB NOT NULL CHECK(jsonb_typeof(blockers)='array'),
    blocker_count INTEGER NOT NULL CHECK(blocker_count>=0),
    idempotency_key UUID NOT NULL,
    request_sha256 CHAR(64) NOT NULL,
    decided_by UUID REFERENCES users(user_id),
    decided_at TIMESTAMPTZ,
    decision_reason TEXT,
    approval_token UUID,
    published_at TIMESTAMPTZ,
    publication_id UUID,
    UNIQUE(site_id,proposal_id),
    UNIQUE(site_id,idempotency_key),
    FOREIGN KEY(site_id,draft_id,base_revision) REFERENCES planning_draft_versions(site_id,draft_id,revision),
    CHECK(expires_at>created_at),
    CHECK(state NOT IN ('approved','published') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL AND approval_token IS NOT NULL)),
    CHECK(state<>'published' OR (published_at IS NOT NULL AND publication_id IS NOT NULL))
);
CREATE INDEX draft_publication_proposals_history ON draft_publication_proposals(site_id,draft_id,created_at DESC);

CREATE TABLE draft_publications (
    publication_id UUID PRIMARY KEY,
    site_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    draft_id UUID NOT NULL,
    revision INTEGER NOT NULL,
    published_by UUID NOT NULL REFERENCES users(user_id),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    proposal_digest CHAR(64) NOT NULL,
    idempotency_key UUID NOT NULL,
    request_sha256 CHAR(64) NOT NULL,
    UNIQUE(site_id,publication_id),
    UNIQUE(site_id,proposal_id),
    UNIQUE(site_id,idempotency_key),
    FOREIGN KEY(site_id,proposal_id) REFERENCES draft_publication_proposals(site_id,proposal_id),
    FOREIGN KEY(site_id,draft_id,revision) REFERENCES planning_draft_versions(site_id,draft_id,revision)
);
ALTER TABLE draft_publication_proposals ADD FOREIGN KEY(site_id,publication_id) REFERENCES draft_publications(site_id,publication_id);

-- One source event per asset cannot be issued twice, including through another
-- draft/import ID or changed interpretation. Cancellation preserves this history.
CREATE TABLE published_catalog_obligations (
    site_id UUID NOT NULL,
    obligation_key CHAR(64) NOT NULL,
    publication_id UUID NOT NULL,
    occurrence_id UUID NOT NULL,
    equipment_id UUID NOT NULL,
    PRIMARY KEY(site_id,obligation_key),
    FOREIGN KEY(site_id,publication_id) REFERENCES draft_publications(site_id,publication_id),
    FOREIGN KEY(site_id,equipment_id) REFERENCES equipment(site_id,equipment_id)
);
CREATE TABLE published_catalog_tasks (
    site_id UUID NOT NULL,
    publication_id UUID NOT NULL,
    item_id UUID NOT NULL,
    work_order_id UUID NOT NULL,
    occurrence_id UUID NOT NULL,
    segment_ids JSONB NOT NULL CHECK(jsonb_typeof(segment_ids)='array'),
    PRIMARY KEY(site_id,publication_id,item_id),
    UNIQUE(site_id,work_order_id),
    FOREIGN KEY(site_id,publication_id) REFERENCES draft_publications(site_id,publication_id),
    FOREIGN KEY(site_id,work_order_id) REFERENCES work_orders(site_id,work_order_id)
);
COMMIT;
