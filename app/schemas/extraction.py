from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PortfolioEntry(BaseModel):
    location: str = Field(..., description="City, region, or neighborhood")
    property_type: Optional[str] = Field(
        None, description="e.g., 1BR Apartment, Villa, Commercial"
    )
    estimated_value: Optional[int] = None
    estimated_value_currency: Optional[str] = Field(
        None,
        pattern=r"^[A-Z]{3}$",
        description="Uppercase ISO 4217 currency code for estimated_value",
    )
    status: Optional[Literal["rented", "vacant", "primary_residence", "mortgaged"]] = (
        None
    )
    intent: Optional[Literal["hold", "sell_to_fund", "refinance"]] = None


class ExtractedClientContext(BaseModel):
    # Explicit, bounded lead intent and per-turn understanding signals.
    intent: Literal[
        "buy_property",
        "rent_property",
        "investment",
        "sell_property",
        "general_inquiry",
        "other",
    ] = "other"
    sentiment: Literal["positive", "neutral", "negative", "frustrated"] = "neutral"
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Model estimate of confidence in this turn's extracted details, from 0 to 1",
    )
    replace_property_preferences: bool = Field(
        False,
        description="True only when the customer explicitly corrects/replaces previously stored property types or preferred communities",
    )

    # Capture identity details only if the customer volunteers them.
    full_name: Optional[str] = None
    email: Optional[str] = None

    # Location and property requirements
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
    country: Optional[str] = None
    city_region: Optional[str] = None
    preferred_locations: List[str] = Field(
        default_factory=list,
        description="Preferred city districts, neighborhoods, or regions",
    )
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    budget_currency: Optional[str] = Field(
        None,
        pattern=r"^[A-Z]{3}$",
        description="Uppercase ISO 4217 currency code for the property budget",
    )
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
