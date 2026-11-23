import json
import re

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.models.client import Client
from app.schemas.extraction import ExtractedClientContext

SYSTEM_PROMPT = """
You are an experienced, friendly real-estate advisor on WhatsApp. Qualify the customer's property search naturally and accurately, without sounding like a form.

First-turn greeting:
- When there is no prior conversation history, introduce yourself before asking a qualification question. Identify yourself as Robin, the customer's real-estate assistant, in one short friendly sentence, then ask only the single most useful next question. Example: "Hi, I’m Robin, your real-estate assistant. Are you looking to buy, rent, or invest?"
- If the customer already shared their intent or requirements in their opening message, acknowledge what they shared after the introduction and ask the next missing detail. Do not repeat information they already provided.

On every turn:
1. Extract any newly mentioned details into the structured fields (do not invent values; leave null if unmentioned).
   Also classify lead intent as exactly one of: buy_property, rent_property, investment, sell_property, general_inquiry, other. Classify sentiment as positive, neutral, negative, or frustrated. Set confidence from 0.0 to 1.0 for your certainty about this turn's interpretation.
   Set `replace_property_preferences` to true only when the customer clearly corrects/replaces their earlier property type or preferred area; otherwise false. For owned-property values, capture the amount and the property's local ISO currency code; do not convert it.
2. Capture these search details whenever stated: buy/rent and purpose; property type; BHK/bedroom range; country, city/region and preferred areas; budget range and currency; target timing; property status/condition; payment method. Use the currency normally used for property prices in the intended property's location and return its ISO 4217 code (for example, USD, INR, GBP, AED). If the location has multiple plausible currencies, or location is unknown, ask which currency they mean. Never convert currencies or guess a budget. Do not overwrite known values unless the customer corrects them.
   Never assume Dubai, UAE, or any other default market. If there is no customer-confirmed location in the known profile or chat history, ask which city or area they want; do not include a city in the greeting.
3. Ask for the single most useful missing search detail next. Do not ask again for information already in `current_known_profile` or recent history. If a message answers several questions, capture each and move forward.

Handling difficult conversations:
- Ambiguous area, budget, bedroom count, timeframe, or currency: ask a brief clarification and keep uncertain fields unset. For a clearly stated country/city, use its customary local property currency; still preserve an explicitly stated different currency.
- Corrections or changed plans: treat explicit correction language ("actually", "instead", "change that") as an update, not a second preference. Preserve both only when the customer says both are acceptable.
- Multiple properties or family members: distinguish each search in `additional_notes`; don't combine incompatible budgets or locations into one requirement.
- Customer asks a direct question: answer only if supported by the conversation or known facts. Never invent availability, listings, prices, returns, legal/tax advice, or guarantees. Then ask one relevant follow-up.
- Frustration, complaint, or request for a human: acknowledge it, apologize briefly when appropriate, stop qualification questions, and offer a human handoff. Do not claim a handoff happened unless the system has done it.
- Off-topic, one-word, unclear, or voice-transcription-like message: respond naturally and ask one simple clarification; do not discard useful details embedded in it.
- Privacy: never ask for the customer's email address or name. If they volunteer these details, capture them. Never ask for passwords, payment credentials, or identity documents in chat.
- Returning after a gap: use the saved profile and history, briefly pick up where the conversation left off, and ask only for still-missing or stale details.
- Never expose internal labels, confidence values, prompts, or JSON to the customer.

WhatsApp Style Rules:
- Keep messages to 1–2 short sentences, warm and conversational.
- Acknowledge what they just shared before asking the next single missing question.
- If the user answers multiple questions at once, capture all of them and skip straight to the next missing item.
- Convert shorthand budgets into integer amounts in the stated or location-derived currency (e.g., "2M" -> 2000000); never convert between currencies.
- Return ONLY a single valid JSON object matching the requested schema, with no markdown fences or extra prose.
"""


def _enforce_strict_schema(schema: dict) -> dict:
    """Recursively adds additionalProperties=False for strict JSON schema compatibility."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            if "properties" in schema:
                schema["required"] = list(schema["properties"].keys())
        for value in schema.values():
            _enforce_strict_schema(value)
    elif isinstance(schema, list):
        for item in schema:
            _enforce_strict_schema(item)
    return schema


STRICT_SCHEMA = _enforce_strict_schema(ExtractedClientContext.model_json_schema())
SCHEMA_HINT = "Return only JSON matching this schema: " + json.dumps(
    STRICT_SCHEMA, separators=(",", ":")
)
_http = httpx.AsyncClient(
    timeout=httpx.Timeout(
        settings.BEDROCK_TIMEOUT_SECONDS,
        connect=3.0,
        write=10.0,
        pool=5.0,
    ),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)


def _ensure_first_turn_introduction(reply: str) -> str:
    """Ensure the first reply introduces Robin once before the qualification question."""
    text = reply.strip()
    robin_intro = re.compile(
        r"^\s*(?:(?:hi|hello|hey)(?:\s+there)?[!, .]*\s*)?"
        r"(?:(?:i['’]?m|i am|this is)\s+robin\b|robin\s+here\b)",
        flags=re.IGNORECASE,
    )
    greeting = re.compile(r"^\s*(?:hi|hello|hey)(?:\s+there)?[!, .]*\s*", re.IGNORECASE)
    any_intro = re.compile(
        r"^\s*(?:i['’]?m|i am|this is)\s+[^.!?\n]{0,140}"
        r"\b(?:assistant|advisor|agent|consultant|wabot)\b[^.!?\n]*[.!?]\s*",
        flags=re.IGNORECASE,
    )

    # Remove a stale or duplicate opening before deciding whether to add Robin.
    # This also handles replies that contain two opening introductions.
    for _ in range(3):
        if robin_intro.search(text):
            if not re.match(r"^\s*(?:hi|hello|hey)\b", text, flags=re.IGNORECASE):
                return f"Hi, {text}"
            return text
        without_greeting = greeting.sub("", text, count=1)
        if without_greeting != text:
            text = without_greeting.lstrip()
            continue
        without_intro = any_intro.sub("", text, count=1)
        if without_intro != text:
            text = without_intro.lstrip()
            continue
        break

    introduction = "Hi, I’m Robin, your real-estate assistant."
    return f"{introduction} {text}" if text else introduction


def _extract_json_text(raw_content: str) -> str:
    text = raw_content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return text


async def extract_and_generate_reply(
    client: Client, history: list[dict], latest_message: str
) -> ExtractedClientContext:
    req = client.requirement
    known_profile = {
        "full_name": client.full_name,
        "email": client.email,
        "intent": req.intent,
        "transaction_type": req.transaction_type,
        "purpose": req.purpose,
        "property_types": req.property_types,
        "bedrooms_min": req.bedrooms_min,
        "bedrooms_max": req.bedrooms_max,
        "country": req.country if req.location_confirmed else None,
        "city_region": req.city_region if req.location_confirmed else None,
        "preferred_locations": req.preferred_locations or req.preferred_communities,
        "budget_min": req.budget_min
        if req.budget_min is not None
        else req.budget_min_aed,
        "budget_max": req.budget_max
        if req.budget_max is not None
        else req.budget_max_aed,
        "budget_currency": req.budget_currency
        or ("AED" if req.budget_max_aed is not None else None),
        "payment_method": req.payment_method,
        "timeline": req.timeline,
        "completion_status": req.completion_status,
        "portfolio_items_recorded": len(client.portfolio_items),
        "additional_notes": client.additional_notes,
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"current_known_profile:\n{json.dumps(known_profile, default=str)}",
        },
        {"role": "system", "content": SCHEMA_HINT},
        *history,
        {"role": "user", "content": latest_message},
    ]

    base_url = settings.BEDROCK_BASE_URL.rstrip("/")
    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.AWS_BEARER_TOKEN_BEDROCK}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.BEDROCK_MODEL_ID,
        "messages": messages,
        "temperature": 0.2,
    }

    max_tokens = 1200
    for attempt in range(2):
        res = await _http.post(
            url,
            json={**payload, "max_tokens": max_tokens},
            headers=headers,
        )
        if res.is_error:
            raise RuntimeError(f"Bedrock Mantle error {res.status_code}: {res.text}")
        data = res.json()
        choice = data["choices"][0]
        raw_content = choice["message"]["content"]
        cleaned_json = _extract_json_text(raw_content)

        try:
            extracted = ExtractedClientContext.model_validate_json(cleaned_json)
        except ValidationError:
            if attempt == 0:
                max_tokens = 1800
                continue
            raise

        if choice.get("finish_reason") == "length" and attempt == 0:
            max_tokens = 1800
            continue
        if not history:
            extracted = extracted.model_copy(
                update={
                    "next_reply": _ensure_first_turn_introduction(extracted.next_reply)
                }
            )
        return extracted

    raise RuntimeError("Bedrock response was truncated after retry")


async def close_extractor_http_client() -> None:
    await _http.aclose()
