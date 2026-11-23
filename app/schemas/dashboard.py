from typing import Literal

from pydantic import BaseModel, Field


class DashboardTurn(BaseModel):
    direction: Literal["inbound", "outbound"]
    content: str
    time: str
    sentiment: str | None = None
    confidence: int | None = None


class DashboardPortfolioItem(BaseModel):
    location: str
    propertyType: str | None = None
    estimatedValue: int | None = None
    currency: str | None = None
    status: str | None = None
    intent: str | None = None


class DashboardCustomer(BaseModel):
    id: str
    name: str
    phone: str
    email: str | None = None
    initials: str
    color: str
    intent: str
    location: str
    budget: str
    sentiment: str
    confidence: int
    crm: str
    lastActive: str | None = None
    joined: str | None = None
    propertyType: str
    bedrooms: str
    purpose: str
    timeline: str
    payment: str
    tags: list[str] = Field(default_factory=list)
    buyIntent: int = 0
    growthIntent: int = 0
    sentimentBreakdown: dict[str, int] = Field(default_factory=dict)
    turns: list[DashboardTurn] = Field(default_factory=list)
    notes: str | None = None
    crmExternalId: str | None = None
    crmLastSyncedAt: str | None = None
    transactionType: str | None = None
    country: str | None = None
    preferredLocations: list[str] = Field(default_factory=list)
    preferredCommunities: list[str] = Field(default_factory=list)
    locationConfirmed: bool = False
    emirate: str | None = None
    completionStatus: str | None = None
    qualificationStatus: str | None = None
    budgetMin: int | None = None
    budgetMax: int | None = None
    budgetCurrency: str | None = None
    portfolio: list[DashboardPortfolioItem] = Field(default_factory=list)


class CustomerPage(BaseModel):
    items: list[DashboardCustomer]
    total: int
    skip: int
    limit: int


class DashboardSummary(BaseModel):
    totalCustomers: int
    qualifiedLeads: int
    positiveSentimentPct: int
    crmSynced: int
    crmSyncPct: int
    customerGrowthPct: float | None = None
    qualifiedGrowthPct: float | None = None
    newCustomers: int
    buyIntentPct: int
    growthIntentPct: int
    averageConfidence: int | None = None
    sentimentCounts: dict[str, int]
    intentCounts: dict[str, int]


class ChartPoint(BaseModel):
    label: str
    count: int


class BreakdownItem(BaseModel):
    label: str
    count: int
    percentage: int


class DashboardReport(BaseModel):
    customerGrowth: list[ChartPoint]
    intentDistribution: list[BreakdownItem]
    sentimentDistribution: list[BreakdownItem]
    investmentPurpose: list[BreakdownItem]
    confidenceDistribution: list[BreakdownItem] = Field(default_factory=list)
    averageConfidence: int | None = None
    positiveSentimentPct: int = 0
    buyIntentPct: int = 0
    growthIntentPct: int = 0
    newCustomers: int = 0
    totalCustomers: int = 0


class DashboardHealth(BaseModel):
    database: Literal["connected"] = "connected"

