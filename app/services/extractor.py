import json

import httpx

from app.core.config import settings
from app.models.client import Client
from app.schemas.extraction import ExtractedClientContext

SYSTEM_PROMPT = """
You are a sharp, friendly Real Estate Advisor chatting on WhatsApp.
Your goal is to qualify the client naturally while mapping everything they say into structured data for property matchmaking.

On every turn:
1. Extract any newly mentioned details into the structured fields (do not invent values; leave null if unmentioned).
2. Check `current_known_profile` to see what is still missing from our capture checklist:
   - Step 1 (Greeting & Intent): Welcome them warmly and ask if they are looking to buy, rent (and their goal: living, rental yield).
   - Step 2 (Property Type & Size): Property type (Apartment, Villa, Townhouse, Penthouse, Commercial, Plot) & bedrooms.
   - Step 3 (Location): Preferred locations (e.g., Dubai Marina, Downtown, Dubai Hills, Palm Jumeirah, Business Bay, Yas Island, Mumbai, Bangalore).
   - Step 4 (Budget & Financing): Budget range in INR and payment preference (Cash, Mortgage, or Developer Payment Plan).
   - Step 5 (Timing): Target move-in/closing timeline and Ready vs. Off-Plan preference.
   - Step 6 (Current Portfolio): Ask if they currently own any real estate in or internationally (and whether they plan to hold, sell, or leverage it).
   - Step 7 (Anything Else): Ask if there are any must-haves (views, developer preference, schools, chiller-free, etc.) or their name/email for sending curated options.

WhatsApp Style Rules:
- Keep messages concise (2–3 short sentences max), warm, and conversational—never sound like a rigid form.
- Acknowledge what they just shared before asking the next single missing question.
- If the user answers multiple questions at once, capture all of them and skip straight to the next missing item.
- Convert shorthand budgets into integer AED (e.g., "2M" -> 2000000, "1.5 million" -> 1500000).
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
        "transaction_type": req.transaction_type,
        "purpose": req.purpose,
        "property_types": req.property_types,
        "bedrooms_min": req.bedrooms_min,
        "bedrooms_max": req.bedrooms_max,
        "emirate": req.emirate,
        "preferred_communities": req.preferred_communities,
        "budget_min_aed": req.budget_min_aed,
        "budget_max_aed": req.budget_max_aed,
        "payment_method": req.payment_method,
        "timeline": req.timeline,
        "completion_status": req.completion_status,
        "portfolio_items_recorded": len(client.portfolio_items),
        "additional_notes": client.additional_notes,
    }

    schema_hint = (
        "Respond with ONLY valid JSON adhering to this JSON Schema:\n"
        f"{json.dumps(STRICT_SCHEMA)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"current_known_profile:\n{json.dumps(known_profile, default=str)}",
        },
        {"role": "system", "content": schema_hint},
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

    async with httpx.AsyncClient(timeout=30.0) as http:
        res = await http.post(url, json=payload, headers=headers)
        if res.is_error:
            raise RuntimeError(f"Bedrock Mantle error {res.status_code}: {res.text}")
        data = res.json()

    raw_content = data["choices"][0]["message"]["content"]
    cleaned_json = _extract_json_text(raw_content)
    return ExtractedClientContext.model_validate_json(cleaned_json)
