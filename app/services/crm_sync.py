from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.client import Client


async def sync_client_to_crm(client_id: str) -> None:
    db: Session = SessionLocal()
    client = None
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client or client.crm_sync_status == "SYNCED":
            return

        req = client.requirement
        payload = {
            "client_id": str(client.id),
            "whatsapp_jid": client.whatsapp_jid,
            "phone_number": client.phone_number,
            "full_name": client.full_name,
            "email": client.email,
            "requirements": {
                "intent": req.intent,
                "transaction_type": req.transaction_type,
                "purpose": req.purpose,
                "property_types": req.property_types,
                "bedrooms_min": req.bedrooms_min,
                "bedrooms_max": req.bedrooms_max,
                "country": req.country,
                "city_region": req.city_region,
                "preferred_locations": req.preferred_locations or req.preferred_communities,
                "budget_min": req.budget_min if req.budget_min is not None else req.budget_min_aed,
                "budget_max": req.budget_max if req.budget_max is not None else req.budget_max_aed,
                "budget_currency": req.budget_currency
                or ("AED" if req.budget_max_aed is not None else None),
                # Retained for consumers of the legacy UAE-specific contract.
                "emirate": req.emirate,
                "preferred_communities": req.preferred_communities,
                "budget_min_aed": req.budget_min_aed,
                "budget_max_aed": req.budget_max_aed,
                "payment_method": req.payment_method,
                "timeline": req.timeline,
                "completion_status": req.completion_status,
                "qualification_status": req.qualification_status,
            },
            "current_portfolio": [
                {
                    "location": p.location,
                    "property_type": p.property_type,
                    "estimated_value": (
                        p.estimated_value
                        if p.estimated_value is not None
                        else p.estimated_value_aed
                    ),
                    "estimated_value_currency": p.estimated_value_currency
                    or ("AED" if p.estimated_value_aed is not None else None),
                    "estimated_value_aed": p.estimated_value_aed,
                    "status": p.status,
                    "intent": p.intent,
                }
                for p in client.portfolio_items
            ],
            "additional_notes": client.additional_notes,
            "preference_tags": client.preference_tags,
        }

        if settings.CRM_WEBHOOK_URL:
            headers = (
                {"Authorization": f"Bearer {settings.CRM_API_KEY}"}
                if settings.CRM_API_KEY
                else {}
            )
            async with httpx.AsyncClient(timeout=10.0) as http:
                res = await http.post(
                    settings.CRM_WEBHOOK_URL, json=payload, headers=headers
                )
                res.raise_for_status()
                data = res.json()
                if isinstance(data, dict) and data.get("id"):
                    client.crm_external_id = str(data["id"])

        client.crm_sync_status = "SYNCED"
        client.crm_last_synced_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        if client:
            client.crm_sync_status = "FAILED"
            db.commit()
    finally:
        db.close()
