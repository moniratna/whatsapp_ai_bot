from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Message
from app.schemas.webhook import OpenWAWebhookPayload
from app.services.context_mapper import context_mapper
from app.services.crm_sync import sync_client_to_crm
from app.services.extractor import extract_and_generate_reply
from app.services.openwa import openwa_service

router = APIRouter()


@router.post("/webhook")
async def handle_openwa_webhook(
    payload: OpenWAWebhookPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    print("[DEBUG] OpenWA webhook payload:", payload.model_dump(by_alias=True))
    if payload.event != "message.received" or not payload.data:
        return {"status": "ignored"}

    if payload.data.fromMe:
        return {"status": "ignored_self"}

    chat_id = payload.data.from_id
    user_text = (payload.data.body or "").strip()

    if not chat_id or not user_text:
        return {"status": "empty"}

    # Deduplicate retried/repeated OpenWA webhook events before doing LLM or DB work
    if payload.data.id:
        existing_msg = (
            db.query(Message)
            .filter(Message.external_message_id == payload.data.id)
            .first()
        )
        if existing_msg:
            return {"status": "duplicate_ignored"}

    # 1. Resolve WhatsApp JID -> Client context
    client = context_mapper.get_or_create_client(db, whatsapp_jid=chat_id)
    history = context_mapper.get_recent_history(db, client.id)

    # 2. Save inbound user message with external_message_id
    db.add(
        Message(
            client_id=client.id,
            external_message_id=payload.data.id,
            direction="inbound",
            content=user_text,
        )
    )
    db.commit()

    # 3. Extract structured UAE property/portfolio context & generate next reply
    extracted = await extract_and_generate_reply(client, history, user_text)

    # 4. Merge extracted fields into PostgreSQL client context
    context_mapper.merge_context(db, client, extracted)

    # 5. Save outbound bot message with audit snapshot & send via OpenWA
    db.add(
        Message(
            client_id=client.id,
            direction="outbound",
            content=extracted.next_reply,
            extracted_snapshot=extracted.model_dump(exclude={"next_reply"}),
        )
    )
    db.commit()

    await openwa_service.send_text(chat_id=chat_id, text=extracted.next_reply)

    # 6. Trigger non-blocking CRM sync
    background_tasks.add_task(sync_client_to_crm, str(client.id))

    return {"status": "ok"}
