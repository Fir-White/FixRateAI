"""Database initialization script for test users and reference data."""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.base import Base
from app.models.users import Site, SiteMembership, User
from app.models.equipment import EngineeringSystem, EquipmentType


# Test users matching P0 scenarios
TEST_USERS = [
    {
        "email": "qa_admin@fixrate.test",
        "full_name": "QA Admin",
        "password": "admin123",
        "role": "executive",
    },
    {
        "email": "qa_dispatcher@fixrate.test",
        "full_name": "QA Dispatcher",
        "password": "dispatcher123",
        "role": "executive",  # Dispatcher is executive sub-role
    },
    {
        "email": "qa_engineer@fixrate.test",
        "full_name": "QA Engineer",
        "password": "engineer123",
        "role": "engineer",
    },
    {
        "email": "qa_executor@fixrate.test",
        "full_name": "QA Executor",
        "password": "executor123",
        "role": "technician",
    },
]


async def initialize_test_database() -> None:
    """Initialize test database with reference data and users."""
    settings = get_settings()

    # Create engine
    engine = create_async_engine(
        str(settings.database_url),
        echo=False,
    )

    # Create session factory
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        # Create all tables (for test environment only)
        if settings.is_test:
            print("Creating database tables...")
            await conn.run_sync(Base.metadata.create_all)
            print("✓ Database tables created")

    async with session_factory() as session:
        # Check if data already exists
        result = await session.execute(text("SELECT COUNT(*) FROM users"))
        count = result.scalar()
        if count and count > 0:
            print(f"Database already has {count} users, skipping initialization")
            await engine.dispose()
            return

        print("Initializing test data...")

        # Create test site
        site_id = uuid4()
        site = Site(
            site_id=site_id,
            name="Test Site A",
            address="Test Address, 123",
            timezone="Asia/Yekaterinburg",
        )
        session.add(site)
        print(f"✓ Created site: {site.name} (ID: {site_id})")

        # Create engineering system
        system_id = uuid4()
        system = EngineeringSystem(
            system_id=system_id,
            site_id=site_id,
            code="HEATING",
            name="Heating System",
        )
        session.add(system)
        print(f"✓ Created engineering system: {system.name}")

        # Create equipment type
        type_id = uuid4()
        equipment_type = EquipmentType(
            equipment_type_id=type_id,
            code="GAUGE",
            name="Pressure Gauge",
            default_attributes={"range": "0-10 bar"},
        )
        session.add(equipment_type)
        print(f"✓ Created equipment type: {equipment_type.name}")

        # Create test users
        for user_data in TEST_USERS:
            user_id = uuid4()
            user = User(
                user_id=user_id,
                full_name=user_data["full_name"],
                email=user_data["email"],
                password_hash=hash_password(user_data["password"]),
            )
            session.add(user)

            # Assign role on site
            membership = SiteMembership(
                site_id=site_id,
                user_id=user_id,
                role=user_data["role"],
            )
            session.add(membership)
            print(f"✓ Created user: {user.full_name} ({user.email}) with role {user_data['role']}")

        await session.commit()
        print("✓ Test data initialization complete")

    await engine.dispose()


def main() -> None:
    """Entry point for database initialization."""
    print("FixRate AI - Database Initialization")
    print("=" * 50)

    asyncio.run(initialize_test_database())

    print("\nInitialization complete!")
    print("\nTest credentials:")
    for user in TEST_USERS:
        print(f"  {user['email']} / {user['password']}")


if __name__ == "__main__":
    main()
