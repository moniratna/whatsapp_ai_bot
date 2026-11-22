from sqlalchemy.orm import Session

from app.models.client import Client, ClientPortfolioItem, ClientRequirement, Message
from app.schemas.extraction import ExtractedClientContext


class ContextMapper:
    def get_or_create_client(self, db: Session, whatsapp_jid: str) -> Client:
        client = db.query(Client).filter(Client.whatsapp_jid == whatsapp_jid).first()
        if not client:
            phone = whatsapp_jid.split("@")[0]
            client = Client(whatsapp_jid=whatsapp_jid, phone_number=phone)
            db.add(client)
            db.flush()
            db.add(ClientRequirement(client_id=client.id))
            db.commit()
            db.refresh(client)
        return client

    def get_recent_history(self, db: Session, client_id, limit: int = 10) -> list[dict]:
        rows = (
            db.query(Message)
            .filter(Message.client_id == client_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        history = []
        for msg in reversed(rows):
            role = "user" if msg.direction == "inbound" else "assistant"
            history.append({"role": role, "content": msg.content})
        return history

    def merge_context(
        self, db: Session, client: Client, extracted: ExtractedClientContext
    ) -> None:
        if extracted.full_name:
            client.full_name = extracted.full_name
        if extracted.email:
            client.email = extracted.email.lower()

        if extracted.additional_notes:
            existing = client.additional_notes or ""
            if extracted.additional_notes not in existing:
                client.additional_notes = (
                    f"{existing}\n• {extracted.additional_notes}".strip()
                )

        if extracted.preference_tags:
            client.preference_tags = list(
                set((client.preference_tags or []) + extracted.preference_tags)
            )

        req = client.requirement
        scalar_fields = [
            "transaction_type",
            "purpose",
            "bedrooms_min",
            "bedrooms_max",
            "emirate",
            "budget_min_aed",
            "budget_max_aed",
            "payment_method",
            "timeline",
            "completion_status",
        ]
        for field in scalar_fields:
            value = getattr(extracted, field)
            if value is not None:
                setattr(req, field, value)

        if extracted.property_types:
            req.property_types = list(
                set((req.property_types or []) + extracted.property_types)
            )

        if extracted.preferred_communities:
            req.preferred_communities = list(
                set((req.preferred_communities or []) + extracted.preferred_communities)
            )

        # Mark qualified once core matchmaking fields are captured
        if (
            req.transaction_type
            and req.property_types
            and req.budget_max_aed
            and req.preferred_communities
        ):
            req.qualification_status = "QUALIFIED"

        for item in extracted.new_portfolio_items:
            db.add(
                ClientPortfolioItem(
                    client_id=client.id,
                    location=item.location,
                    property_type=item.property_type,
                    estimated_value_aed=item.estimated_value_aed,
                    status=item.status,
                    intent=item.intent,
                )
            )

        client.crm_sync_status = "PENDING"
        db.commit()


context_mapper = ContextMapper()
