from typing import Optional

from pydantic import BaseModel, Field


class OpenWAMessageData(BaseModel):
    id: Optional[str] = None
    from_id: Optional[str] = Field(None, alias="from")
    body: Optional[str] = ""
    fromMe: bool = False


class OpenWAWebhookPayload(BaseModel):
    event: str
    data: Optional[OpenWAMessageData] = None
