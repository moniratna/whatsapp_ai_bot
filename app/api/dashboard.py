from collections import Counter
from datetime import datetime, timedelta, timezone
from secrets import compare_digest
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.client import Client, ClientRequirement, Message
from app.schemas.dashboard import (
    BreakdownItem,
    ChartPoint,
    CustomerPage,
    DashboardCustomer,
    DashboardHealth,
    DashboardReport,
    DashboardSummary,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def require_dashboard_key(x_dashboard_key: str | None = Header(default=None)) -> None:
    configured_key = settings.DASHBOARD_API_KEY
    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail="Dashboard API access is not configured. Set DASHBOARD_API_KEY.",
        )
    if not x_dashboard_key or not compare_digest(x_dashboard_key, configured_key):
        raise HTTPException(status_code=401, detail="Invalid dashboard credentials")


def _snapshot(message: Message) -> dict[str, Any]:
    return message.extracted_snapshot if isinstance(message.extracted_snapshot, dict) else {}


def _human(value: str | None, fallback: str = "Not specified") -> str:
    if not value:
        return fallback
    value = value.replace("_", " ").strip()
    return {
        "1 3 months": "1–3 months",
        "3 6 months": "3–6 months",
        "6 plus months": "6+ months",
        "capital appreciation": "Capital appreciation",
        "rental yield": "Rental yield",
        "end use": "End use",
        "golden visa": "Golden visa",
        "payment plan": "Payment plan",
    }.get(value.lower(), value.title())


def _intent(requirement: ClientRequirement | None) -> str:
    if not requirement:
        return "Other"
    intent = (requirement.intent or "").lower()
    known = {
        "buy_property": "Buy property",
        "rent_property": "Rent property",
        "investment": "Investment",
        "sell_property": "Sell property",
        "general_inquiry": "General inquiry",
    }
    if intent in known:
        return known[intent]
    if requirement.purpose in {"rental_yield", "capital_appreciation"}:
        return "Investment"
    if requirement.transaction_type == "rent":
        return "Rent property"
    if requirement.transaction_type in {"buy", "off_plan"}:
        return "Buy property"
    return "Other"


def _sentiment(value: Any) -> str:
    normalized = str(value or "neutral").lower()
    return normalized if normalized in {"positive", "neutral", "negative", "frustrated"} else "neutral"


def _budget(requirement: ClientRequirement | None) -> str:
    if not requirement:
        return "Not specified"
    currency = requirement.budget_currency or ""
    low, high = requirement.budget_min, requirement.budget_max
    if low is not None and high is not None:
        return f"{currency} {low:,} – {high:,}".strip()
    if high is not None:
        return f"Up to {currency} {high:,}".strip()
    if low is not None:
        return f"From {currency} {low:,}".strip()
    return "Not specified"


def _location(requirement: ClientRequirement | None) -> str:
    if not requirement:
        return "Not specified"
    return (
        requirement.city_region
        or requirement.emirate
        or (requirement.preferred_locations or requirement.preferred_communities or [None])[0]
        or "Not specified"
    )


def _latest_signal(messages: list[Message]) -> dict[str, Any]:
    for message in reversed(messages):
        snapshot = _snapshot(message)
        if message.direction == "outbound" and snapshot:
            return snapshot
    return {}


def _customer_payload(
    client: Client,
    messages: list[Message] | None = None,
    *,
    last_message: Message | None = None,
    include_history: bool = False,
) -> dict[str, Any]:
    requirement = client.requirement
    messages = messages or []
    latest = _latest_signal(messages)
    name = client.full_name or client.phone_number
    property_types = requirement.property_types or [] if requirement else []
    bedrooms = "Not specified"
    if requirement and (requirement.bedrooms_min is not None or requirement.bedrooms_max is not None):
        low, high = requirement.bedrooms_min, requirement.bedrooms_max
        bedrooms = f"{low}–{high} bedrooms" if low is not None and high is not None and low != high else f"{low if low is not None else high} bedrooms"
    sentiment = _sentiment(latest.get("sentiment"))
    confidence = latest.get("confidence", 0.5)
    try:
        confidence = max(0, min(100, round(float(confidence) * 100)))
    except (TypeError, ValueError):
        confidence = 50
    tags = list(dict.fromkeys((client.preference_tags or []) + (requirement.preferred_communities or [] if requirement else [])))
    signals = [_snapshot(message) for message in messages if message.direction == "outbound" and _snapshot(message)]
    intent_signals = [str(snapshot.get("intent", "")).lower() for snapshot in signals if snapshot.get("intent")]
    purpose_signals = [str(snapshot.get("purpose", "")).lower() for snapshot in signals if snapshot.get("purpose") in {"capital_appreciation", "rental_yield"}]
    sentiment_signals = [_sentiment(snapshot.get("sentiment")) for snapshot in signals if snapshot.get("sentiment")]
    sentiment_total = len(sentiment_signals)
    sentiment_breakdown = {
        label: round(sentiment_signals.count(label) * 100 / sentiment_total) if sentiment_total else 0
        for label in ("positive", "neutral", "negative", "frustrated")
    }
    investment_total = len(purpose_signals)
    payload: dict[str, Any] = {
        "id": str(client.id),
        "name": name,
        "phone": client.phone_number,
        "email": client.email,
        "initials": "".join(part[0] for part in name.split()[:2]).upper() or "?",
        "color": ["rose", "lavender", "sage", "peach", "butter"][sum(name.encode("utf-8")) % 5],
        "intent": _intent(requirement),
        "location": _location(requirement),
        "budget": _budget(requirement),
        "sentiment": sentiment.title(),
        "confidence": confidence,
        "crm": (client.crm_sync_status or "PENDING").title(),
        "lastActive": (last_message.created_at if last_message and last_message.created_at else client.updated_at).isoformat() if (last_message and last_message.created_at) or client.updated_at else None,
        "joined": client.created_at.isoformat() if client.created_at else None,
        "propertyType": ", ".join(property_types) if property_types else "Not specified",
        "bedrooms": bedrooms,
        "purpose": _human(requirement.purpose) if requirement else "Not specified",
        "timeline": _human(requirement.timeline) if requirement else "Not specified",
        "payment": _human(requirement.payment_method) if requirement else "Not specified",
        "tags": tags,
        "buyIntent": round(intent_signals.count("buy_property") * 100 / len(intent_signals)) if intent_signals else 0,
        "growthIntent": round(purpose_signals.count("capital_appreciation") * 100 / investment_total) if investment_total else 0,
        "sentimentBreakdown": sentiment_breakdown,
        "notes": client.additional_notes,
        "crmExternalId": client.crm_external_id,
        "crmLastSyncedAt": client.crm_last_synced_at.isoformat() if client.crm_last_synced_at else None,
        "transactionType": requirement.transaction_type if requirement else None,
        "country": requirement.country if requirement else None,
        "preferredLocations": list(requirement.preferred_locations or []) if requirement else [],
        "preferredCommunities": list(requirement.preferred_communities or []) if requirement else [],
        "locationConfirmed": bool(requirement.location_confirmed) if requirement else False,
        "emirate": requirement.emirate if requirement else None,
        "completionStatus": requirement.completion_status if requirement else None,
        "qualificationStatus": requirement.qualification_status if requirement else None,
        "budgetMin": requirement.budget_min if requirement else None,
        "budgetMax": requirement.budget_max if requirement else None,
        "budgetCurrency": requirement.budget_currency if requirement else None,
        "portfolio": [],
        "turns": [],
    }
    if include_history:
        payload["turns"] = [
            {
                "direction": message.direction,
                "content": message.content,
                "time": message.created_at.isoformat() if message.created_at else "",
                "sentiment": _sentiment(_snapshot(message).get("sentiment")).title() if _snapshot(message).get("sentiment") else None,
                "confidence": round(float(_snapshot(message).get("confidence", 0)) * 100) if _snapshot(message).get("confidence") is not None else None,
            }
            for message in messages
        ]
        payload["portfolio"] = [
            {
                "location": item.location,
                "propertyType": item.property_type,
                "estimatedValue": item.estimated_value,
                "currency": item.estimated_value_currency,
                "status": item.status,
                "intent": item.intent,
            }
            for item in client.portfolio_items
        ]
    return payload


def _snapshot_rows(db: Session, since: datetime) -> list[dict[str, Any]]:
    rows = (
        db.query(Message.extracted_snapshot)
        .filter(Message.direction == "outbound", Message.created_at >= since)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [row[0] for row in rows if isinstance(row[0], dict)]


def _sentiment_counts(snapshots: list[dict[str, Any]]) -> Counter[str]:
    return Counter(_sentiment(snapshot.get("sentiment")) for snapshot in snapshots if snapshot.get("sentiment"))


def _intent_counts(db: Session) -> Counter[str]:
    rows = db.query(ClientRequirement).all()
    return Counter(_intent(row) for row in rows)


def _pct(part: int | float, total: int | float) -> int:
    return round(part * 100 / total) if total else 0


def _current_and_previous_counts(db: Session, now: datetime, days: int) -> tuple[int, int]:
    current_since = now - timedelta(days=days)
    previous_since = now - timedelta(days=days * 2)
    current = db.query(func.count(Client.id)).filter(Client.created_at >= current_since).scalar() or 0
    previous = db.query(func.count(Client.id)).filter(Client.created_at >= previous_since, Client.created_at < current_since).scalar() or 0
    return current, previous


@router.get("/health", response_model=DashboardHealth, dependencies=[Depends(require_dashboard_key)])
def dashboard_health(db: Session = Depends(get_db)) -> DashboardHealth:
    db.query(Client.id).limit(1).all()
    return DashboardHealth()


@router.get("/summary", response_model=DashboardSummary, dependencies=[Depends(require_dashboard_key)])
def dashboard_summary(
    days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db)
) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    total = db.query(func.count(Client.id)).scalar() or 0
    qualified = db.query(func.count(ClientRequirement.id)).filter(ClientRequirement.qualification_status == "QUALIFIED").scalar() or 0
    synced = db.query(func.count(Client.id)).filter(func.upper(Client.crm_sync_status) == "SYNCED").scalar() or 0
    current_new, previous_new = _current_and_previous_counts(db, now, days)
    current_qualified = (
        db.query(func.count(ClientRequirement.id))
        .filter(ClientRequirement.qualification_status == "QUALIFIED", ClientRequirement.updated_at >= now - timedelta(days=days))
        .scalar() or 0
    )
    previous_qualified = (
        db.query(func.count(ClientRequirement.id))
        .filter(
            ClientRequirement.qualification_status == "QUALIFIED",
            ClientRequirement.updated_at >= now - timedelta(days=days * 2),
            ClientRequirement.updated_at < now - timedelta(days=days),
        ).scalar() or 0
    )
    snapshots = _snapshot_rows(db, now - timedelta(days=days))
    sentiments = _sentiment_counts(snapshots)
    intents = _intent_counts(db)
    confidence_values = []
    for snapshot in snapshots:
        try:
            confidence_values.append(float(snapshot["confidence"]))
        except (KeyError, TypeError, ValueError):
            continue
    positive = sentiments.get("positive", 0)
    total_sentiment = sum(sentiments.values())
    buy = intents.get("Buy property", 0)
    total_intents = sum(intents.values())
    investment_purposes = Counter(dict(db.query(ClientRequirement.purpose, func.count(ClientRequirement.id)).filter(ClientRequirement.purpose.in_(["capital_appreciation", "rental_yield"])).group_by(ClientRequirement.purpose).all()))
    return DashboardSummary(
        totalCustomers=total,
        qualifiedLeads=qualified,
        positiveSentimentPct=_pct(positive, total_sentiment),
        crmSynced=synced,
        crmSyncPct=_pct(synced, total),
        customerGrowthPct=round((current_new - previous_new) * 100 / previous_new, 1) if previous_new else None,
        qualifiedGrowthPct=round((current_qualified - previous_qualified) * 100 / previous_qualified, 1) if previous_qualified else None,
        newCustomers=current_new,
        buyIntentPct=_pct(buy, total_intents),
        growthIntentPct=_pct(investment_purposes.get("capital_appreciation", 0), sum(investment_purposes.values())),
        averageConfidence=round(sum(confidence_values) * 100 / len(confidence_values)) if confidence_values else None,
        sentimentCounts=dict(sentiments),
        intentCounts=dict(intents),
    )


@router.get("/customers", response_model=CustomerPage, dependencies=[Depends(require_dashboard_key)])
def list_customers(
    q: str | None = Query(default=None, max_length=200),
    intent: str | None = Query(default=None, max_length=40),
    sentiment: str | None = Query(default=None, max_length=20),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CustomerPage:
    query = db.query(Client).options(selectinload(Client.requirement)).outerjoin(ClientRequirement)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(or_(Client.full_name.ilike(term), Client.phone_number.ilike(term), Client.email.ilike(term), ClientRequirement.city_region.ilike(term)))
    if intent:
        normalized_intent = intent.strip().lower().replace("_", " ")
        intent_clauses = {
            "buy property": or_(ClientRequirement.intent == "buy_property", ClientRequirement.transaction_type == "buy"),
            "rent property": or_(ClientRequirement.intent == "rent_property", ClientRequirement.transaction_type == "rent"),
            "investment": or_(ClientRequirement.intent == "investment", ClientRequirement.purpose.in_(["rental_yield", "capital_appreciation"])),
        }
        query = query.filter(intent_clauses.get(normalized_intent, ClientRequirement.intent == normalized_intent.replace(" ", "_")))
    if sentiment:
        latest_signal = (
            db.query(
                Message.client_id.label("client_id"),
                Message.extracted_snapshot["sentiment"].as_string().label("sentiment"),
                func.row_number().over(
                    partition_by=Message.client_id,
                    order_by=Message.created_at.desc(),
                ).label("position"),
            )
            .filter(Message.direction == "outbound", Message.extracted_snapshot["sentiment"].as_string().isnot(None))
            .subquery()
        )
        query = query.join(
            latest_signal,
            and_(Client.id == latest_signal.c.client_id, latest_signal.c.position == 1),
        ).filter(func.lower(latest_signal.c.sentiment) == sentiment.strip().lower())
    total = query.count()
    clients = query.order_by(Client.updated_at.desc().nullslast(), Client.created_at.desc().nullslast()).offset(skip).limit(limit).all()
    ids = [client.id for client in clients]
    latest_outbound = (
        db.query(Message.client_id.label("client_id"), func.max(Message.id).label("message_id"))
        .filter(Message.client_id.in_(ids), Message.direction == "outbound")
        .group_by(Message.client_id)
        .subquery()
    ) if ids else None
    latest_activity = (
        db.query(Message.client_id.label("client_id"), func.max(Message.id).label("message_id"))
        .filter(Message.client_id.in_(ids))
        .group_by(Message.client_id)
        .subquery()
    ) if ids else None
    latest_signal_rows = (
        db.query(Message).join(latest_outbound, Message.id == latest_outbound.c.message_id).all()
    ) if latest_outbound is not None else []
    latest_activity_rows = (
        db.query(Message).join(latest_activity, Message.id == latest_activity.c.message_id).all()
    ) if latest_activity is not None else []
    messages_by_client = {message.client_id: [message] for message in latest_signal_rows}
    activity_by_client = {message.client_id: message for message in latest_activity_rows}
    items = [
        _customer_payload(client, messages_by_client.get(client.id, []), last_message=activity_by_client.get(client.id))
        for client in clients
    ]
    return CustomerPage(items=items, total=total, skip=skip, limit=limit)


@router.get("/customers/{client_id}", response_model=DashboardCustomer, dependencies=[Depends(require_dashboard_key)])
def get_customer(client_id: UUID, db: Session = Depends(get_db)) -> DashboardCustomer:
    client = (
        db.query(Client)
        .options(selectinload(Client.requirement), selectinload(Client.portfolio_items))
        .filter(Client.id == client_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Customer not found")
    messages = db.query(Message).filter(Message.client_id == client.id).order_by(Message.created_at.asc()).all()
    return DashboardCustomer(
        **_customer_payload(client, messages, last_message=messages[-1] if messages else None, include_history=True)
    )


@router.get("/reports", response_model=DashboardReport, dependencies=[Depends(require_dashboard_key)])
def dashboard_reports(
    days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db)
) -> DashboardReport:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    client_rows = db.query(Client.created_at).filter(Client.created_at >= since).all()
    daily: Counter[str] = Counter()
    for (created_at,) in client_rows:
        if created_at:
            created_at_utc = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
            daily[created_at_utc.strftime("%Y-%m-%d")] += 1
    growth = [
        ChartPoint(label=(since.date() + timedelta(days=offset)).strftime("%b %-d"), count=daily[(since.date() + timedelta(days=offset)).strftime("%Y-%m-%d")])
        for offset in range(days + 1)
    ]
    intents = _intent_counts(db)
    intent_total = sum(intents.values())
    intent_distribution = [BreakdownItem(label=label, count=count, percentage=_pct(count, intent_total)) for label, count in intents.most_common()]
    snapshots = _snapshot_rows(db, since)
    sentiments = _sentiment_counts(snapshots)
    sentiment_total = sum(sentiments.values())
    sentiment_distribution = [BreakdownItem(label=label.title(), count=count, percentage=_pct(count, sentiment_total)) for label, count in sentiments.most_common()]
    purpose_counts = Counter(
        {"Capital appreciation": 0, "Rental yield": 0, "End use": 0, "Other": 0}
    )
    for purpose, count in db.query(ClientRequirement.purpose, func.count(ClientRequirement.id)).group_by(ClientRequirement.purpose).all():
        purpose_counts[_human(purpose, "Other")] += count
    purpose_total = sum(purpose_counts.values())
    purpose_distribution = [BreakdownItem(label=label, count=count, percentage=_pct(count, purpose_total)) for label, count in purpose_counts.most_common() if count]
    confidence_values = []
    confidence_bands: Counter[str] = Counter()
    for snapshot in snapshots:
        try:
            confidence = float(snapshot["confidence"])
            confidence_values.append(confidence)
            confidence_bands["0–49%" if confidence < 0.5 else "50–69%" if confidence < 0.7 else "70–84%" if confidence < 0.85 else "85–100%"] += 1
        except (KeyError, TypeError, ValueError):
            continue
    buy = intents.get("Buy property", 0)
    total_intents = sum(intents.values())
    return DashboardReport(
        customerGrowth=growth,
        intentDistribution=intent_distribution,
        sentimentDistribution=sentiment_distribution,
        investmentPurpose=purpose_distribution,
        confidenceDistribution=[BreakdownItem(label=label, count=count, percentage=_pct(count, len(confidence_values))) for label, count in confidence_bands.items()],
        averageConfidence=round(sum(confidence_values) * 100 / len(confidence_values)) if confidence_values else None,
        positiveSentimentPct=_pct(sentiments.get("positive", 0), sentiment_total),
        buyIntentPct=_pct(buy, total_intents),
        growthIntentPct=_pct(purpose_counts.get("Capital appreciation", 0), purpose_counts.get("Capital appreciation", 0) + purpose_counts.get("Rental yield", 0)),
        newCustomers=len(client_rows),
        totalCustomers=db.query(func.count(Client.id)).scalar() or 0,
    )
