# Backend Development Guide

## Project Structure

```
backend/
├── app/
│   ├── api/v1/              # API endpoints
│   │   ├── auth.py          # Authentication (login/logout/session)
│   │   ├── equipment.py     # Equipment CRUD
│   │   └── users.py         # User management
│   ├── core/                # Core infrastructure
│   │   ├── config.py        # Settings from environment
│   │   ├── database.py      # SQLAlchemy async engine
│   │   └── security.py      # Password hashing, JWT, CSRF
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── base.py          # Base model class
│   │   ├── users.py         # User, Site, SiteMembership
│   │   ├── equipment.py     # Equipment, EngineeringSystem
│   │   └── session.py       # Session (auth)
│   ├── repositories/        # Database access layer
│   │   ├── user_repository.py
│   │   ├── session_repository.py
│   │   └── equipment_repository.py
│   ├── schemas/             # Pydantic schemas
│   │   ├── users.py         # User/auth schemas
│   │   ├── equipment.py     # Equipment schemas
│   │   └── common.py        # Error responses
│   ├── services/            # Business logic
│   │   ├── auth_service.py  # Authentication logic
│   │   ├── equipment_service.py
│   │   └── rbac_service.py  # Role-based access control
│   └── main.py              # FastAPI application
├── scripts/
│   └── init_db.py           # Database seeding
├── tests/                   # Test suite
│   ├── conftest.py          # Pytest fixtures
│   ├── test_auth.py
│   ├── test_equipment_api.py
│   └── test_rbac.py
└── requirements.txt
```

## Architecture Layers

1. **API Layer** (`app/api/v1/`)
   - HTTP endpoints
   - Request validation (Pydantic)
   - Response formatting
   - HTTP status codes

2. **Service Layer** (`app/services/`)
   - Business logic
   - Orchestration between repositories
   - Domain-specific validation
   - Error handling

3. **Repository Layer** (`app/repositories/`)
   - Database queries
   - ORM operations
   - Data access patterns

4. **Model Layer** (`app/models/`)
   - SQLAlchemy ORM models
   - Database schema mapping
   - Relationships

## Key Design Decisions

### 1. Async Everywhere
Using async/await for all database operations to handle concurrent requests efficiently.

### 2. Repository Pattern
Separating database access from business logic for testability and maintainability.

### 3. Pydantic Schemas
Strict validation of request/response data with clear error messages.

### 4. RBAC with Site Scope
Users have roles per site, enabling multi-tenant access control.

### 5. Session-Based Auth
HttpOnly cookies for session storage, CSRF tokens for state-changing operations.

## Adding New Features

### Example: Adding a new endpoint

1. **Create schema** (`app/schemas/new_feature.py`):
```python
from pydantic import BaseModel

class NewFeatureCreate(BaseModel):
    name: str
    # ... fields

class NewFeatureResponse(BaseModel):
    id: UUID
    name: str
    
    class Config:
        from_attributes = True
```

2. **Add repository** (`app/repositories/new_feature_repository.py`):
```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.new_feature import NewFeature

class NewFeatureRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, data: dict) -> NewFeature:
        # ... create logic
```

3. **Add service** (`app/services/new_feature_service.py`):
```python
class NewFeatureService:
    def __init__(self, session: AsyncSession):
        self.repo = NewFeatureRepository(session)
    
    async def create_feature(self, data: NewFeatureCreate):
        # ... business logic
        return await self.repo.create(data.model_dump())
```

4. **Add endpoint** (`app/api/v1/new_feature.py`):
```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/new-features", tags=["new-feature"])

@router.post("", response_model=NewFeatureResponse)
async def create(
    data: NewFeatureCreate,
    session: AsyncSession = Depends(get_db_session),
):
    service = NewFeatureService(session)
    return await service.create_feature(data)
```

5. **Register router** (`app/api/v1/__init__.py`):
```python
from app.api.v1.new_feature import router as new_feature_router
api_router.include_router(new_feature_router)
```

6. **Write tests** (`tests/test_new_feature.py`):
```python
import pytest

class TestNewFeature:
    async def test_create(self, db_session):
        # ... test logic
```

## Database Migrations

Migrations are in `database/migrations/`. Apply in order:

```bash
psql -U fixrate -d fixrate -f database/migrations/001_tl02.sql
psql -U fixrate -d fixrate -f database/migrations/002_planning_contract.sql
psql -U fixrate -d fixrate -f database/migrations/003_occurrence_uniqueness.sql
psql -U fixrate -d fixrate -f database/migrations/004_sessions.sql
```

## Testing Strategy

### Unit Tests
- Test individual functions/methods
- Mock dependencies
- Fast execution

### Integration Tests
- Test API endpoints
- Use testcontainers for PostgreSQL
- Verify database interactions

### RBAC Tests
- Verify role permissions
- Test site scope isolation
- Check access denial scenarios

Run tests:
```bash
pytest tests/ -v
pytest tests/test_auth.py -v  # Specific file
pytest -k "test_login" -v     # Specific test
```

## Security Checklist

- [x] Password hashing (SHA-256 with salt - upgrade to bcrypt for production)
- [x] JWT tokens for session validation
- [x] CSRF protection for state-changing operations
- [x] HttpOnly cookies for session storage
- [x] Role-based access control
- [x] Site-scoped permissions
- [ ] Rate limiting (TODO)
- [ ] Input sanitization (TODO)
- [ ] SQL injection prevention (SQLAlchemy handles this)
- [ ] XSS prevention (frontend responsibility)

## Performance Considerations

1. **Database Queries**
   - Use eager loading for relationships
   - Index frequently queried fields
   - Use pagination for lists

2. **Caching**
   - TODO: Add Redis for session caching
   - TODO: Cache frequently accessed data

3. **Connection Pooling**
   - SQLAlchemy connection pool configured
   - Adjust `pool_size` and `max_overflow` based on load

## Common Issues

### Import Errors
```bash
# Ensure you're in backend/ directory
cd backend

# Set PYTHONPATH if needed
$env:PYTHONPATH="D:\Programing\Python\UrFU\FixRate_AI\backend"
```

### Database Connection
```bash
# Check DATABASE_URL in .env
# Ensure PostgreSQL is running
# Verify database exists
```

### Test Failures
```bash
# Ensure Docker is running for testcontainers
# Check test database is created
# Run with verbose output: pytest -v -s
```

## Next Steps

1. **Complete RBAC integration**
   - Add permission checks to all endpoints
   - Implement middleware for automatic auth

2. **Add more endpoints**
   - Operations CRUD
   - Schedule management
   - Work orders

3. **Enhance security**
   - Upgrade to bcrypt for password hashing
   - Add rate limiting
   - Implement audit logging

4. **Performance**
   - Add caching layer
   - Optimize queries
   - Add database indexes

5. **Documentation**
   - OpenAPI/Swagger docs (auto-generated)
   - API usage examples
   - Deployment guide
