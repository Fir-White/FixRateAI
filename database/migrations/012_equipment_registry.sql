-- Explicit system groups and installed-part history. Existing catalog rows remain unchanged.
BEGIN;
ALTER TABLE engineering_systems ADD COLUMN system_group TEXT
    CHECK (system_group IN ('electricity','water','air'));
ALTER TABLE engineering_systems ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0);

CREATE TABLE equipment_components (
    component_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL,
    equipment_id UUID NOT NULL,
    position_code TEXT NOT NULL CHECK (length(trim(position_code)) BETWEEN 1 AND 128),
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 256),
    part_number TEXT,
    serial_number TEXT,
    installed_on DATE NOT NULL,
    removed_on DATE CHECK (removed_on >= installed_on),
    removal_reason TEXT,
    usage_unit TEXT NOT NULL CHECK (usage_unit IN ('hour','cycle','km')),
    initial_usage NUMERIC(15,3) NOT NULL DEFAULT 0 CHECK (initial_usage >= 0),
    resource_limit NUMERIC(15,3) CHECK (resource_limit > 0),
    resource_basis TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id,component_id),
    FOREIGN KEY (site_id,equipment_id) REFERENCES equipment(site_id,equipment_id) ON DELETE CASCADE,
    CHECK (resource_limit IS NULL OR length(trim(resource_basis)) > 0 AND resource_basis IS NOT NULL),
    CHECK ((removed_on IS NULL) = (removal_reason IS NULL))
);
CREATE UNIQUE INDEX equipment_components_active_position
    ON equipment_components(site_id,equipment_id,position_code) WHERE removed_on IS NULL;

CREATE TABLE component_usage_readings (
    reading_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL,
    component_id UUID NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL,
    usage_value NUMERIC(15,3) NOT NULL CHECK (usage_value >= 0),
    note TEXT NOT NULL CHECK (length(trim(note)) BETWEEN 1 AND 2000),
    photo_key TEXT,
    photo_mime TEXT,
    photo_sha256 TEXT,
    recorded_by UUID NOT NULL REFERENCES users(user_id),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (site_id,component_id) REFERENCES equipment_components(site_id,component_id) ON DELETE CASCADE,
    UNIQUE (site_id,component_id,measured_at),
    CHECK ((photo_key IS NULL) = (photo_mime IS NULL)),
    CHECK ((photo_key IS NULL) = (photo_sha256 IS NULL))
);
CREATE INDEX component_usage_readings_history ON component_usage_readings(site_id,component_id,measured_at DESC);
COMMIT;
