import httpx

from app.core.config import settings


class OpenWAService:
    def __init__(self):
        self.base_url = settings.OPENWA_BASE_URL.rstrip("/")
        self.session_id = settings.OPENWA_SESSION_ID
        self.headers = {"X-Api-Key": settings.OPENWA_API_KEY}

    async def send_text(self, chat_id: str, text: str) -> None:
        url = f"{self.base_url}/sessions/{self.session_id}/messages/send-text"
        payload = {"chatId": chat_id, "text": text}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()


openwa_service = OpenWAService()
