from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PortfolioEntry(BaseModel):
    location: str = Field(
        ..., description="City or UAE community of the currently owned property"
    )
    property_type: Optional[str] = Field(
        None, description="e.g., 1BR Apartment, Villa, Commercial"
    )
    estimated_value_aed: Optional[int] = None
    status: Optional[Literal["rented", "vacant", "primary_residence", "mortgaged"]] = (
        None
    )
    intent: Optional[Literal["hold", "sell_to_fund", "refinance"]] = None


class ExtractedClientContext(BaseModel):
    # Client identity details if shared in chat
    full_name: Optional[str] = None
    email: Optional[str] = None

    # UAE Property Requirements
    transaction_type: Optional[Literal["buy", "rent", "off_plan"]] = None
    purpose: Optional[
        Literal["end_use", "rental_yield", "capital_appreciation", "golden_visa"]
    ] = None
    property_types: List[str] = Field(
        default_factory=list,
        description="Normalized values only: apartment, villa, townhouse, penthouse, commercial, plot",
    )
    bedrooms_min: Optional[int] = None
    bedrooms_max: Optional[int] = None
    emirate: Optional[str] = Field(
        None, description="e.g., Dubai, Abu Dhabi, Ras Al Khaimah, Sharjah"
    )
    preferred_communities: List[str] = Field(
        default_factory=list,
        description="Normalized UAE communities e.g. Dubai Marina, Downtown Dubai, Dubai Hills Estate",
    )
    budget_min_aed: Optional[int] = None
    budget_max_aed: Optional[int] = None
    payment_method: Optional[Literal["cash", "mortgage", "payment_plan"]] = None
    timeline: Optional[
        Literal["immediate", "1_3_months", "3_6_months", "6_plus_months"]
    ] = None
    completion_status: Optional[Literal["ready", "off_plan", "any"]] = None

    # Current Portfolio & Open Context
    new_portfolio_items: List[PortfolioEntry] = Field(default_factory=list)
    preference_tags: List[str] = Field(
        default_factory=list,
        description="Short tags e.g. waterfront, high_floor, emaar, chiller_free, near_metro",
    )
    additional_notes: Optional[str] = Field(
        None,
        description="Any extra context, lifestyle needs, or notes shared by the client",
    )

    # Next WhatsApp message to send back
    next_reply: str = Field(
        ...,
        description="Short, natural WhatsApp reply acknowledging their message and asking the next missing question",
    )
