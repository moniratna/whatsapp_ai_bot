import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.models.client import Message
from app.schemas.webhook import OpenWAWebhookPayload
from app.services.context_mapper import context_mapper
from app.services.crm_sync import sync_client_to_crm
from app.services.extractor import extract_and_generate_reply
from app.services.openwa import openwa_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhook/openwa", include_in_schema=False)
@router.post("/webhook")
async def handle_openwa_webhook(
    payload: OpenWAWebhookPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if payload.event != "message.received" or not payload.data:
        return {"status": "ignored"}

    if payload.data.fromMe:
        return {"status": "ignored_self"}

    chat_id = payload.data.from_id
    user_text = (payload.data.body or "").strip()

    if not chat_id or not user_text:
        return {"status": "empty"}

    # Deduplicate retried/repeated OpenWA webhook events before doing LLM or DB work
    def load_context_and_save_inbound():
        if payload.data.id:
            existing_msg = (
                db.query(Message)
                .filter(Message.external_message_id == payload.data.id)
                .first()
            )
            if existing_msg:
                return None, None

        client = context_mapper.get_or_create_client(db, whatsapp_jid=chat_id)
        history = context_mapper.get_recent_history(db, client.id)
        db.add(
            Message(
                client_id=client.id,
                external_message_id=payload.data.id,
                direction="inbound",
                content=user_text,
            )
        )
        db.commit()
        return client, history

    client, history = await run_in_threadpool(load_context_and_save_inbound)
    if not client:
        return {"status": "duplicate_ignored"}

    # 3. Extract structured property/portfolio context & generate next reply
    try:
        extracted = await extract_and_generate_reply(client, history, user_text)
    except Exception:
        logger.exception("AI reply generation failed")
        fallback_reply = "Thanks for your message. I’m having trouble processing it right now. Could you try sending it again in a moment?"

        def persist_fallback_reply():
            db.add(
                Message(
                    client_id=client.id,
                    direction="outbound",
                    content=fallback_reply,
                    extracted_snapshot={"processing_error": True},
                )
            )
            db.commit()

        await run_in_threadpool(persist_fallback_reply)
        await openwa_service.send_text(chat_id=chat_id, text=fallback_reply)
        return {"status": "temporarily_unavailable"}

    # 4. Merge extracted fields into PostgreSQL client context
    def persist_extraction_and_reply():
        context_mapper.merge_context(db, client, extracted)
        db.add(
            Message(
                client_id=client.id,
                direction="outbound",
                content=extracted.next_reply,
                extracted_snapshot=extracted.model_dump(exclude={"next_reply"}),
            )
        )
        db.commit()

    await run_in_threadpool(persist_extraction_and_reply)

    await openwa_service.send_text(chat_id=chat_id, text=extracted.next_reply)

    # 6. Trigger non-blocking CRM sync
    background_tasks.add_task(sync_client_to_crm, str(client.id))

    return {"status": "ok"}
