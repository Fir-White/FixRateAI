"""Equipment SQLAlchemy models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Equipment status enum values matching database constraints
EquipmentStatus = Literal["active", "under_repair", "retired"]


class EngineeringSystem(Base):
    """Engineering system within a site (heating, water, etc.)."""

    __tablename__ = "engineering_systems"

    system_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.site_id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    notes: Mapped[str | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    site: Mapped["Site"] = relationship(lazy="joined")
    equipment: Mapped[list["Equipment"]] = relationship(
        back_populates="system",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("site_id", "system_id", name="engineering_systems_site_system_unique"),
        UniqueConstraint("site_id", "code", name="engineering_systems_site_code_unique"),
        CheckConstraint("length(trim(name)) > 0", name="engineering_systems_name_check"),
        Index("idx_engineering_systems_site_name", "site_id", "name"),
    )


class EquipmentType(Base):
    """Equipment type classifier."""

    __tablename__ = "equipment_types"

    equipment_type_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    code: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    default_attributes: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Relationships
    equipment: Mapped[list["Equipment"]] = relationship(
        back_populates="equipment_type",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("code", name="equipment_types_code_unique"),
        CheckConstraint(
            "jsonb_typeof(default_attributes) = 'object'",
            name="equipment_types_attributes_check",
        ),
    )


class Equipment(Base):
    """Specific equipment unit with passport and hierarchy."""

    __tablename__ = "equipment"

    equipment_id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.site_id", ondelete="RESTRICT"),
        nullable=False,
    )
    system_id: Mapped[UUID] = mapped_column(
        ForeignKey("engineering_systems.system_id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_equipment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("equipment.equipment_id", ondelete="RESTRICT"),
    )
    equipment_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("equipment_types.equipment_type_id", ondelete="RESTRICT"),
    )
    asset_code: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    serial_number: Mapped[str | None] = mapped_column()
    commissioned_on: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column()
    properties: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    status: Mapped[EquipmentStatus] = mapped_column(
        default="active",
        nullable=False,
    )

    # Relationships
    site: Mapped["Site"] = relationship(lazy="joined")
    system: Mapped["EngineeringSystem"] = relationship(
        back_populates="equipment",
        lazy="joined",
    )
    parent: Mapped["Equipment | None"] = relationship(
        back_populates="children",
        remote_side=[equipment_id],
        lazy="joined",
    )
    children: Mapped[list["Equipment"]] = relationship(
        back_populates="parent",
        lazy="selectin",
    )
    equipment_type: Mapped["EquipmentType | None"] = relationship(
        back_populates="equipment",
        lazy="joined",
    )

    __table_args__ = (
        UniqueConstraint("site_id", "equipment_id", name="equipment_site_equipment_unique"),
        UniqueConstraint(
            "site_id", "system_id", "equipment_id",
            name="equipment_site_system_equipment_unique",
        ),
        UniqueConstraint("site_id", "asset_code", name="equipment_site_asset_code_unique"),
        CheckConstraint(
            "status IN ('active','under_repair','retired')",
            name="equipment_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(properties) = 'object'",
            name="equipment_properties_check",
        ),
        CheckConstraint(
            "parent_equipment_id IS DISTINCT FROM equipment_id",
            name="equipment_parent_self_check",
        ),
        Index("idx_equipment_site_system_status", "site_id", "system_id", "status"),
        Index("idx_equipment_site_parent", "site_id", "parent_equipment_id"),
    )
