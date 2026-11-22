from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message


class BotEngine:
    def _log_message(
        self, db: Session, conversation_id: int, sender: str, content: str
    ) -> None:
        msg = Message(conversation_id=conversation_id, sender=sender, content=content)
        db.add(msg)

    def process_incoming_message(
        self, db: Session, phone_number: str, text: str
    ) -> str:
        conv = (
            db.query(Conversation)
            .filter(Conversation.phone_number == phone_number)
            .first()
        )
        if not conv:
            conv = Conversation(
                phone_number=phone_number, current_step="GREETING", lead_data={}
            )
            db.add(conv)
            db.flush()  # Get conv.id without committing yet

        # Store user message
        self._log_message(db, conv.id, "user", text)

        # State machine (ready to be replaced/augmented with AI later)
        if conv.current_step == "GREETING":
            reply = (
                "Hello! Welcome to our Real Estate Assistant.\n"
                "What type of property are you looking to buy or rent? "
                "(e.g., Apartment, Villa, Plot, Commercial)"
            )
            conv.current_step = "ASK_PROPERTY_TYPE"

        elif conv.current_step == "ASK_PROPERTY_TYPE":
            updated_data = dict(conv.lead_data)
            updated_data["property_type"] = text
            conv.lead_data = updated_data
            conv.current_step = "READY_FOR_NEXT"
            reply = f"Got it — noted your interest in *{text}*."

        else:
            reply = "Thanks! We have recorded your property preference."

        # Store bot reply and commit transaction atomically
        self._log_message(db, conv.id, "bot", reply)
        db.commit()

        return reply


bot_engine = BotEngine()
