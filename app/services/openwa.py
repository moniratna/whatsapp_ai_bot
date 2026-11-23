import httpx

from app.core.config import settings


class OpenWAService:
    def __init__(self):
        self.base_url = settings.OPENWA_BASE_URL.rstrip("/")
        self.session_id = settings.OPENWA_SESSION_ID
        self.headers = {"X-Api-Key": settings.OPENWA_API_KEY}
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=3.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def send_text(self, chat_id: str, text: str) -> None:
        url = f"{self.base_url}/sessions/{self.session_id}/messages/send-text"
        payload = {"chatId": chat_id, "text": text}
        response = await self._http.post(url, json=payload, headers=self.headers)
        response.raise_for_status()

    async def close(self) -> None:
        await self._http.aclose()


openwa_service = OpenWAService()
