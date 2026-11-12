-- Preserve all memberships and references while renaming the leadership role.
ALTER TABLE site_memberships DROP CONSTRAINT site_memberships_role_check;
UPDATE site_memberships SET role = 'director' WHERE role = 'executive';
ALTER TABLE site_memberships ADD CONSTRAINT site_memberships_role_check
    CHECK (role IN ('director','chief_engineer','engineer','technician','admin','dispatcher','executor'));
