BEGIN;
ALTER TABLE site_memberships
    ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    ADD COLUMN employed_from DATE,
    ADD COLUMN employed_until DATE,
    ADD CHECK (employed_until IS NULL OR employed_from IS NULL OR employed_until >= employed_from);
ALTER TABLE crews ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0);
ALTER TABLE availability_slots ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0);
ALTER TABLE user_skills ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0);

CREATE TABLE employee_shift_rules (
    shift_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL,
    user_id UUID NOT NULL,
    label TEXT NOT NULL CHECK (length(trim(label)) > 0),
    calendar_pattern JSONB NOT NULL CHECK (jsonb_typeof(calendar_pattern)='object'),
    valid_from DATE NOT NULL,
    valid_until DATE,
    starts_local TIME NOT NULL,
    ends_local TIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','unavailable')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    CHECK (valid_until IS NULL OR valid_until >= valid_from),
    CHECK (starts_local <> ends_local),
    FOREIGN KEY(site_id,user_id) REFERENCES site_memberships(site_id,user_id)
);
CREATE INDEX employee_shift_rules_worker ON employee_shift_rules(site_id,user_id);

CREATE TABLE site_join_codes (
    site_id UUID PRIMARY KEY REFERENCES sites(site_id),
    code TEXT NOT NULL UNIQUE DEFAULT replace(gen_random_uuid()::text,'-','')
);
CREATE TABLE employment_applications (
    application_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(site_id),
    user_id UUID NOT NULL REFERENCES users(user_id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    decided_by UUID,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE(site_id,user_id),
    FOREIGN KEY(site_id,decided_by) REFERENCES site_memberships(site_id,user_id)
);
COMMIT;
