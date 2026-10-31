# DTO ↔ Database Discrepancies

This document tracks differences between Pydantic DTOs and database schema that need resolution.

## Status: Resolved in FX26-BE02

The following discrepancies were identified and resolved by aligning API with database schema.

---

## 1. Equipment Status Field

**DTO (original - maintenance_api.py):**
```python
state: Literal["active", "out_of_service", "retired"]
```

**Database (001_tl02.sql):**
```sql
status TEXT DEFAULT 'active' NOT NULL,
CHECK (status IN ('active','under_repair','retired'))
```

**Resolution:** API now uses `status` field matching database values:
- `active` - operational
- `under_repair` - undergoing maintenance
- `retired` - decommissioned

**Rationale:** Database is the source of truth. "under_repair" is more specific than "out_of_service".

**Impact:** Frontend needs to use `status` instead of `state`.

---

## 2. Equipment Asset Code Field

**DTO (original - maintenance_api.py):**
```python
inventory_code: Text
```

**Database (001_tl02.sql):**
```sql
asset_code TEXT NOT NULL
```

**Resolution:** API now uses `asset_code` matching database.

**Rationale:** Consistency with database schema.

**Impact:** Frontend needs to use `asset_code` instead of `inventory_code`.

---

## 3. User Roles

**DTO (original - maintenance_api.py):**
```python
role: Literal["admin", "dispatcher", "executor", "engineer"]
```

**Database (001_tl02.sql):**
```sql
role TEXT NOT NULL,
CHECK (role IN ('executive','chief_engineer','engineer','technician'))
```

**Resolution:** Implemented role mapping layer:
- API roles: `admin`, `dispatcher`, `engineer`, `executor`
- Database roles: `executive`, `chief_engineer`, `engineer`, `technician`

**Mapping:**
```python
DB_TO_API_ROLE = {
    "executive": "admin",
    "chief_engineer": "engineer",
    "engineer": "engineer",
    "technician": "executor",
}
```

**Rationale:** 
- API roles are user-friendly and permission-based
- Database roles reflect organizational structure
- Mapping layer provides flexibility

**Impact:** 
- API consumers see simplified roles
- Database maintains detailed role information
- Multiple API roles can map to same DB role (e.g., admin and dispatcher both use executive)

---

## 4. Role Permissions

**DTO (original - maintenance_api.py):**
```python
ROLE_PERMISSIONS = {
    "admin": ("reference:read", "reference:write", "users:write"),
    "dispatcher": ("equipment:read", "operation:write", "schedule:write", "task:assign"),
    "executor": ("task:read_assigned", "execution:write", "photo:write"),
    "engineer": ("equipment:read", "execution:read", "execution:accept", "forecast:read"),
}
```

**Resolution:** Expanded permission matrix with comprehensive coverage:
```python
ROLE_PERMISSIONS = {
    "admin": frozenset({
        "reference:read", "reference:write",
        "users:read", "users:write",
        "equipment:read", "equipment:write",
        "schedule:read", "schedule:write",
    }),
    "dispatcher": frozenset({
        "equipment:read", "equipment:write",
        "operation:read", "operation:write",
        "schedule:read", "schedule:write",
        "task:assign",
    }),
    "engineer": frozenset({
        "equipment:read",
        "operation:read",
        "schedule:read",
        "execution:read", "execution:accept",
        "forecast:read",
    }),
    "executor": frozenset({
        "task:read_assigned",
        "execution:write",
        "photo:write",
    }),
}
```

**Rationale:** More granular permissions for better access control.

**Impact:** Finer-grained access control, more flexibility for future features.

---

## Migration Notes

### For Frontend Developers

If you were using the original DTO field names, update your code:

| Old (DTO) | New (API) | Database |
|-----------|-----------|----------|
| `state` | `status` | `status` |
| `inventory_code` | `asset_code` | `asset_code` |
| Role: `admin` | Role: `admin` | DB: `executive` |
| Role: `dispatcher` | Role: `dispatcher` | DB: `executive` |
| Role: `executor` | Role: `executor` | DB: `technician` |
| Role: `engineer` | Role: `engineer` | DB: `engineer` / `chief_engineer` |

### For Backend Developers

- All new code should use database-aligned field names
- Use `RBACService` for permission checks
- Role mapping is handled automatically

---

## Future Considerations

If the team decides to realign DTOs with original specifications:

1. **Option A: Update Database**
   - Modify column names/values in database
   - Create migration scripts
   - Update all references

2. **Option B: Add Adapter Layer**
   - Keep database as-is
   - Add DTO ↔ ORM adapter in repository layer
   - Maintain both naming conventions

3. **Option C: Keep Current Approach** (Recommended)
   - API aligned with database
   - Clear and consistent
   - Minimal code complexity

**Recommendation:** Keep current approach (Option C) for simplicity and consistency.
