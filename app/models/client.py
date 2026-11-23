import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    whatsapp_jid = Column(
        String, unique=True, index=True, nullable=False
    )  # e.g. "971501234567@c.us"
    phone_number = Column(
        String, unique=True, index=True, nullable=False
    )  # e.g. "971501234567"
    full_name = Column(String, nullable=True)
    email = Column(
        String, nullable=True
    )  # Captured if they share it in chat for CRM enrichment

    # CRM Sync Tracking
    crm_external_id = Column(String, unique=True, index=True, nullable=True)
    crm_sync_status = Column(
        String, default="PENDING", nullable=False
    )  # PENDING | SYNCED | FAILED
    crm_last_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Catch-all for extra preferences & free-form context
    additional_notes = Column(Text, nullable=True)
    preference_tags = Column(ARRAY(String), default=list, nullable=False)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    requirement = relationship(
        "ClientRequirement",
        back_populates="client",
        uselist=False,
        cascade="all, delete-orphan",
    )
    portfolio_items = relationship(
        "ClientPortfolioItem", back_populates="client", cascade="all, delete-orphan"
    )
    messages = relationship(
        "Message", back_populates="client", cascade="all, delete-orphan"
    )


class ClientRequirement(Base):
    """Structured property requirements for future inventory matchmaking."""

    __tablename__ = "client_requirements"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(
        UUID(as_uuid=True), ForeignKey("clients.id"), unique=True, nullable=False
    )

    intent = Column(String, nullable=True)  # predefined lead intent

    transaction_type = Column(String, nullable=True)  # buy | rent | off_plan
    purpose = Column(
        String, nullable=True
    )  # end_use | rental_yield | capital_appreciation | golden_visa
    property_types = Column(
        ARRAY(String), default=list
    )  # ["apartment", "villa", "townhouse", "penthouse", "commercial", "plot"]
    bedrooms_min = Column(Integer, nullable=True)
    bedrooms_max = Column(Integer, nullable=True)

    country = Column(String, nullable=True)
    city_region = Column(String, nullable=True)
    location_confirmed = Column(Boolean, default=False, nullable=False)
    preferred_locations = Column(ARRAY(String), default=list, nullable=False)
    emirate = Column(String, nullable=True)  # legacy compatibility
    preferred_communities = Column(ARRAY(String), default=list)

    budget_min = Column(BigInteger, nullable=True)
    budget_max = Column(BigInteger, nullable=True)
    budget_currency = Column(String(3), nullable=True)
    budget_min_aed = Column(BigInteger, nullable=True)
    budget_max_aed = Column(BigInteger, nullable=True)
    payment_method = Column(String, nullable=True)  # cash | mortgage | payment_plan

    timeline = Column(
        String, nullable=True
    )  # immediate | 1_3_months | 3_6_months | 6_plus_months
    completion_status = Column(String, nullable=True)  # ready | off_plan | any

    qualification_status = Column(
        String, default="IN_PROGRESS"
    )  # IN_PROGRESS | QUALIFIED
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    client = relationship("Client", back_populates="requirement")


class ClientPortfolioItem(Base):
    """Existing properties owned by the client."""

    __tablename__ = "client_portfolio_items"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True
    )

    location = Column(String, nullable=False)  # e.g., "Dubai Marina" or "London"
    property_type = Column(String, nullable=True)  # e.g., "2BR Apartment"
    estimated_value = Column(BigInteger, nullable=True)
    estimated_value_currency = Column(String(3), nullable=True)
    estimated_value_aed = Column(BigInteger, nullable=True)  # legacy compatibility
    status = Column(
        String, nullable=True
    )  # rented | vacant | primary_residence | mortgaged
    intent = Column(String, nullable=True)  # hold | sell_to_fund | refinance

    client = relationship("Client", back_populates="portfolio_items")


class Message(Base):
    """Full WhatsApp chat history + per-turn extraction audit snapshot."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True
    )
    direction = Column(String, nullable=False)  # "inbound" | "outbound"
    content = Column(Text, nullable=False)
    extracted_snapshot = Column(JSON, default=dict)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    external_message_id = Column(String, unique=True, index=True, nullable=True)

    client = relationship("Client", back_populates="messages")
