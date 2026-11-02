import json
import logging
import os
from typing import Any, Dict, List, Optional
from flask import current_app, has_app_context
from app.projects.vip_concierge.models.schemas import BriefingDossierModel

logger = logging.getLogger(__name__)


def _get_config(key: str, default=None):
    if has_app_context():
        val = current_app.config.get(key)
        if val is not None:
            return val
    return os.environ.get(key, default)


def complete_ai_text(prompt: str, model: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 700) -> str:
    """Invokes Vertex Gemini, Gemini Direct, or Groq based on configured keys."""
    # 1. Vertex AI (Gemini 2.5 Flash)
    if _get_config("VERTEX_API_KEY"):
        try:
            from app.clients import vertex_client
            target_model = model or _get_config("VERTEX_MODEL", "gemini-2.5-flash")
            return vertex_client.complete_chat(
                prompt=prompt,
                model=target_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("Vertex AI completion failed in VIP concierge: %s", exc)

    # 2. Gemini Direct (Google Generative AI)
    if _get_config("GEMINI_API_KEY") or _get_config("GEMINI_API_KEY_1"):
        try:
            from app.clients import gemini_client
            return gemini_client.complete_chat(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("Gemini Direct completion failed in VIP concierge: %s", exc)

    # 3. Fallback: Groq
    if _get_config("GROQ_API_KEY"):
        try:
            from app.clients import groq_client
            return groq_client.complete_chat(
                prompt=prompt,
                model=model or _get_config("GROQ_MODEL"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.warning("Groq completion failed in VIP concierge: %s", exc)

    raise RuntimeError("No AI provider (Vertex/Gemini/Groq) successfully completed request.")


class GeminiConciergeAgent:
    def __init__(self):
        self.model = "gemini-2.5-flash"

    def generate_briefing(
        self,
        customer: Dict[str, Any],
        match_meta: Optional[Dict[str, Any]] = None,
        shop: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generates an instant 3-second staff briefing card tailored to the specific shop:
        - One-liner greeting context matching shop brand tone and greeting protocol
        - Conversational talking point referencing store catalog/niche
        - Suggested cross-sell recommendations
        - VIP alert preferences (beverage, sizing/attributes, dislikes)
        """
        from app.projects.vip_concierge.models import storage

        if not shop:
            shop_id = customer.get("shop_id") or "default"
            shop = storage.get_shop(shop_id, user_id=customer.get("user_id"))
            if not shop or shop.get("shop_id") == "default":
                shop = storage.get_active_shop(user_id=customer.get("user_id"))

        shop_name = shop.get("name", "Luxury Boutique")
        shop_industry = shop.get("industry", "clothing")
        brand_tone = shop.get("brand_tone", "Warm bespoke luxury, discreet and attentive")
        greeting_protocol = shop.get("greeting_protocol", "Greet by name within 5 seconds and offer refreshments.")
        ai_briefing_prompt = shop.get("ai_briefing_prompt", "Focus on bespoke recommendations and personalized client care.")

        name = customer.get("name", "Valued Guest")
        tier = customer.get("tier", "Gold VIP")
        total_spent = float(customer.get("total_spent", 0))
        currency = customer.get("currency", "USD")
        purchases = customer.get("purchases", [])
        notes = customer.get("notes", "")
        sizes = customer.get("sizes", {})
        preferred_styles = customer.get("preferred_styles", [])

        prompt = f"""You are the master In-Store VIP Concierge Intelligence AI for '{shop_name}' (Industry: {shop_industry.upper()}).
Brand Tone & Etiquette: {brand_tone}
Store Greeting Protocol: {greeting_protocol}
Custom Store Instructions: {ai_briefing_prompt}

A high-value customer just walked in through the entrance camera.
Synthesize their client history into an ultra-sharp, 3-second actionable briefing for the sales associate on the shop floor.

Customer Profile:
- Name: {name}
- Tier: {tier}
- Total Lifetime Spend: {currency} {total_spent:,.2f}
- Preferences / Notes: {notes}
- Preferred Styles / Interests: {', '.join(preferred_styles) if preferred_styles else 'Bespoke Luxury'}
- Custom Sizing / Client Attributes: {json.dumps(sizes)}
- Past Purchases: {json.dumps(purchases[-5:] if purchases else [])}

CRITICAL RULES:
- Tailor the greeting and recommendations strictly to this store type ({shop_industry}).
- Never mention CCTV, cameras, or facial recognition algorithms.
- Keep greeting natural, sophisticated, and aligned with the store's brand tone.

Respond ONLY with a JSON object adhering to this structure:
{{
  "headline": "<e.g. VIP {name} entered • {tier} Client ({currency} {total_spent:,.0f} LTV)>",
  "greeting_approach": "<Exact 1-sentence warm, subtle greeting for the associate to say>",
  "talking_point": "<1-2 sentences referencing their taste, last purchase, or compliment>",
  "suggested_items": [
    "<Recommendation 1 fitting this {shop_industry} store with reason>",
    "<Recommendation 2 fitting this {shop_industry} store with reason>"
  ],
  "preferences_alert": "<Crucial size, attribute, milestone date, favorite drink, or sensitivity to remember>"
}}
"""
        try:
            raw_response = complete_ai_text(
                prompt=prompt,
                model=self.model,
                temperature=0.3,
                max_tokens=600,
            )
            # Parse JSON
            cleaned = raw_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())
            return BriefingDossierModel.model_validate(data).model_dump()
        except Exception as exc:
            logger.warning("AI briefing generation failed: %s; using dynamic rule-based fallback", exc)
            return self._fallback_briefing(customer, shop=shop)

    def _fallback_briefing(self, customer: Dict[str, Any], shop: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        shop = shop or {}
        industry = (shop.get("industry") or "boutique").lower()
        shop_name = shop.get("name") or "our boutique"

        name = customer.get("name", "VIP Client")
        tier = customer.get("tier", "VIP")
        spent = float(customer.get("total_spent", 0))
        curr = customer.get("currency", "USD")
        notes = customer.get("notes") or ""

        # Dynamically tailor suggestions and hospitality etiquette to the shop industry
        if "jewel" in industry or "gem" in industry:
            suggested = ["Private viewing of rare gemstone collection", "Complimentary ultrasonic inspection"]
            pref_alert = f"Anniversary/milestone notes: {notes}" if notes else "Offer chilled vintage champagne."
        elif "watch" in industry or "horolog" in industry:
            suggested = ["New grand complication reference arrivals", "Complimentary strap inspection & timing test"]
            pref_alert = f"Collector tastes: {notes}" if notes else "Prepare loupe, velvet tray, and single-malt or espresso."
        elif "auto" in industry or "motor" in industry:
            suggested = ["Bespoke aerodynamic package preview", "Exclusive track-day invitational"]
            pref_alert = f"Garage fleet: {notes}" if notes else "Offer barista espresso in VIP Heritage Lounge."
        elif "art" in industry or "galer" in industry:
            suggested = ["Private studio acquisitions preview", "Vernissage advance catalog"]
            pref_alert = f"Collector focus: {notes}" if notes else "Escort to private gallery suite with custom lighting."
        elif "perfum" in industry or "fragran" in industry:
            suggested = ["Private bespoke formulation consultation", "Limited seasonal extrait flacons"]
            pref_alert = f"Olfactive sensitivities: {notes}" if notes else "Offer room-temperature palate cleanser water."
        else:
            suggested = ["Curated seasonal collection preview", "Private styling consultation"]
            pref_alert = notes or "Offer complimentary beverage and escort to VIP suite."

        headline = f"VIP {name} entered • {tier} Client ({curr} {spent:,.0f} LTV)"
        greeting = f"Welcome back to {shop_name}, {name}! Wonderful to see you today."
        talking_point = f"Acknowledge their ongoing patronage with {shop_name} and inquire how they are enjoying their collection."

        dossier = BriefingDossierModel(
            headline=headline,
            greeting_approach=greeting,
            talking_point=talking_point,
            suggested_items=suggested,
            preferences_alert=pref_alert,
        )
        return dossier.model_dump()

    def generate_text_embedding(self, text: str) -> Optional[List[float]]:
        """Generates a 768-d semantic embedding for text using Google Generative AI."""
        try:
            import google.generativeai as genai
            keys = gemini_client._configured_api_keys()
            if not keys:
                return None
            genai.configure(api_key=keys[0])
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_document",
            )
            return result.get("embedding")
        except Exception as exc:
            logger.warning("Gemini text embedding generation failed: %s", exc)
            return None


gemini_concierge_agent = GeminiConciergeAgent()

