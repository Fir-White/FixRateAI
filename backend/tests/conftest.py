"""Pytest configuration and fixtures."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.security import hash_password
from app.models.base import Base
from app.models.equipment import EngineeringSystem, EquipmentType
from app.models.users import Site, SiteMembership, User


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Start PostgreSQL test container."""
    with PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="fixrate_test",
    ) as pg:
        yield pg


@pytest_asyncio.fixture(scope="session")
async def database_url(postgres_container: PostgresContainer) -> str:
    """Get database URL from test container."""
    return postgres_container.get_connection_url().replace(
        "postgresql://",
        "postgresql+psycopg://",
    )


@pytest_asyncio.fixture(scope="session")
async def engine(database_url: str):
    """Create test database engine."""
    engine = create_async_engine(database_url, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session with rollback after each test."""
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_site(db_session: AsyncSession) -> Site:
    """Create test site."""
    site = Site(
        name="Test Site",
        address="Test Address",
        timezone="Asia/Yekaterinburg",
    )
    db_session.add(site)
    await db_session.flush()
    return site


@pytest_asyncio.fixture
async def test_system(db_session: AsyncSession, test_site: Site) -> EngineeringSystem:
    """Create test engineering system."""
    system = EngineeringSystem(
        site_id=test_site.site_id,
        code="TEST_SYSTEM",
        name="Test System",
    )
    db_session.add(system)
    await db_session.flush()
    return system


@pytest_asyncio.fixture
async def test_equipment_type(db_session: AsyncSession) -> EquipmentType:
    """Create test equipment type."""
    eq_type = EquipmentType(
        code="TEST_TYPE",
        name="Test Equipment Type",
        default_attributes={},
    )
    db_session.add(eq_type)
    await db_session.flush()
    return eq_type


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create test user."""
    user = User(
        full_name="Test User",
        email="test@example.com",
        password_hash=hash_password("testpassword"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_admin_user(db_session: AsyncSession) -> User:
    """Create test admin user."""
    user = User(
        full_name="Test Admin",
        email="admin@example.com",
        password_hash=hash_password("adminpassword"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_membership(
    db_session: AsyncSession,
    test_site: Site,
    test_user: User,
) -> SiteMembership:
    """Create test site membership."""
    membership = SiteMembership(
        site_id=test_site.site_id,
        user_id=test_user.user_id,
        role="executive",
    )
    db_session.add(membership)
    await db_session.flush()
    return membership
