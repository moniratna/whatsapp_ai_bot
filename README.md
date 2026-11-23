# WhatsApp Real Estate Assistant

## Conversation behavior

The Bedrock-backed assistant is location- and currency-agnostic. It collects intent, property type, BHK/bedrooms, country/city/area, budget in the property's local currency, timeline, and related preferences. It records budgets using an ISO 4217 currency code and does not convert currencies. It uses saved client requirements and the six latest messages to continue a conversation when a customer returns. Its conversation instructions cover ambiguous answers, corrections, multiple searches, direct questions, frustration, human handoff requests, privacy, and unsupported claims.

The assistant should ask one useful follow-up at a time, avoid repeating already captured details, and never invent property availability, pricing, returns, or a completed human handoff. Sentiment and model-estimated confidence are recorded in each outbound message's `extracted_snapshot`.

## Latency behavior

Bedrock and OpenWA HTTP connections are reused across requests, request and response sizes are bounded, and synchronous database work is moved off the async event loop. Tune Bedrock model choice and hosting region for the deployment; those account and infrastructure choices have the largest impact on generation latency.
