# FixRate AI Backend

Backend API for the FixRate AI maintenance planning system.

## Architecture

```
backend/
├── app/
│   ├── api/v1/          # API endpoints (auth, users, equipment)
│   ├── core/            # Core infrastructure (config, database, security)
│   ├── models/          # SQLAlchemy ORM models
│   ├── repositories/    # Database access layer
│   ├── schemas/         # Pydantic request/response schemas
│   ├── services/        # Business logic layer
│   └── main.py          # FastAPI application entry point
├── scripts/             # Database initialization scripts
├── tests/               # Test suite
└── requirements.txt     # Python dependencies
```

## Quick Start

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env` and adjust settings:

```bash
cp .env.example .env  # or edit .env directly
```

Key settings:
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET` - Secret key for JWT tokens (min 32 chars)
- `APP_ENV` - Environment: `local`, `development`, `production`, `test`

### 3. Initialize database

Apply migrations to your PostgreSQL database:

```bash
# Apply all migrations in order
psql -U fixrate -d fixrate -f ../database/migrations/001_tl02.sql
psql -U fixrate -d fixrate -f ../database/migrations/002_planning_contract.sql
psql -U fixrate -d fixrate -f ../database/migrations/003_occurrence_uniqueness.sql
psql -U fixrate -d fixrate -f ../database/migrations/004_sessions.sql
```

### 4. Seed test data (optional)

For development/testing, create test users:

```bash
python scripts/init_db.py
```

This creates test users with known credentials (see output).

### 5. Run the application

```bash
# Development with auto-reload
uvicorn app.main:app --reload

# Or directly
python -m app.main
```

The API will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/api/docs` (development only)

## Testing

### Run tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_auth.py
```

Tests use `testcontainers` to automatically start a PostgreSQL database in Docker. Ensure Docker is running.

### Test coverage

The test suite includes:
- **Unit tests** - Service logic, validation, security utilities
- **Integration tests** - API endpoints with real database
- **RBAC tests** - Role-based access control verification

## API Endpoints

### Authentication
- `POST /api/v1/session` - Login
- `GET /api/v1/session` - Get current session
- `DELETE /api/v1/session` - Logout

### Users
- `GET /api/v1/users/me` - Get current user profile
- `GET /api/v1/users/roles` - Get role permissions matrix
- `GET /api/v1/users/{id}/roles` - Get user roles

### Equipment
- `GET /api/v1/equipment` - List equipment (paginated)
- `POST /api/v1/equipment` - Create equipment
- `GET /api/v1/equipment/{id}` - Get equipment
- `PATCH /api/v1/equipment/{id}` - Update equipment
- `DELETE /api/v1/equipment/{id}` - Retire equipment

### System
- `GET /health` - Health check

## Security

### Authentication
- Session-based authentication with HttpOnly cookies
- JWT tokens for stateless validation
- CSRF protection for state-changing operations

### Password Storage
- Passwords hashed with bcrypt via `passlib`
- Never stored or transmitted in plain text

### Role-Based Access Control
- Four API roles: `admin`, `dispatcher`, `engineer`, `executor`
- Mapped from database roles: `executive`, `chief_engineer`, `engineer`, `technician`
- Permissions checked on every endpoint
- Site-scoped access control

## Development Guidelines

### Code Style
- Use type hints everywhere
- Follow existing naming conventions
- Write docstrings for public functions
- Keep functions small and focused

### Adding New Endpoints
1. Create Pydantic schemas in `app/schemas/`
2. Add repository methods in `app/repositories/`
3. Implement service logic in `app/services/`
4. Create endpoint in `app/api/v1/`
5. Write tests in `tests/`

### Database Changes
1. Update SQLAlchemy models in `app/models/`
2. Create migration in `database/migrations/`
3. Update tests if needed

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENV` | Environment | `local` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DATABASE_URL` | PostgreSQL URL | `postgresql+psycopg://...` |
| `JWT_SECRET` | JWT signing key | Required |
| `JWT_EXPIRE_MINUTES` | Session duration | `60` |
| `STORAGE_DIR` | File storage path | `var/storage` |
| `ML_BASE_URL` | ML service URL | `http://127.0.0.1:8001` |

## Troubleshooting

### Database connection failed
- Check `DATABASE_URL` in `.env`
- Ensure PostgreSQL is running
- Verify database and user exist

### Import errors
- Ensure you're in the `backend/` directory
- Check `PYTHONPATH` includes `backend/`
- Verify all dependencies are installed

### Tests failing
- Ensure Docker is running (for testcontainers)
- Check database migrations are applied
- Review test output for specific errors

## License

Internal project - FixRate AI Team
