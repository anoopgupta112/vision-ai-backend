import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

from app.projects.vip_concierge.models.schemas import (
    ClientAttributeModel,
    ConsultationResponseModel,
    ShopConfigModel,
    VipTierModel,
)
from app.projects.vip_concierge.models.templates import get_template, list_templates
from app.projects.vip_concierge.services.gemini_concierge_agent import complete_ai_text

logger = logging.getLogger(__name__)


class VertexGeminiChat(BaseChatModel):
    """
    Standard LangChain BaseChatModel wrapping the application's multi-provider
    Vertex AI / Gemini text generation engine with key rotation and error recovery.
    """

    temperature: float = 0.2
    max_tokens: int = 3000

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt_parts: List[str] = []
        for m in messages:
            role = "user"
            if isinstance(m, SystemMessage):
                role = "system"
            elif isinstance(m, AIMessage):
                role = "assistant"
            prompt_parts.append(f"{role.upper()}:\n{m.content}")

        full_prompt = "\n\n".join(prompt_parts)
        temp = kwargs.get("temperature", self.temperature)
        tokens = kwargs.get("max_tokens", self.max_tokens)

        response_text = complete_ai_text(prompt=full_prompt, temperature=temp, max_tokens=tokens)
        generation = ChatGeneration(message=AIMessage(content=response_text))
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "vertex_gemini_chat"


def extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    """Extracts and parses JSON object from Markdown code blocks or plain text."""
    clean = text.strip()
    match = re.search(r"```json\s*(.*?)\s*```", clean, re.DOTALL)
    if match:
        clean = match.group(1).strip()
    else:
        m2 = re.search(r"(\{.*\})", clean, re.DOTALL)
        if m2:
            clean = m2.group(1).strip()
    try:
        return json.loads(clean)
    except Exception as exc:
        logger.warning("Could not parse JSON payload: %s; raw text: %s", exc, text[:150])
        return None


class ShopConsultantAgent:
    """
    LangChain-driven AI Consultant that takes inputs from a store owner
    (e.g., jewelry salon, clothing atelier, watchmaker, exotic dealership, art gallery, perfumery, or custom concept)
    and customizes the VIP Concierge settings, client attributes schema, and greeting protocols.
    """

    def __init__(self):
        self.chat_model = VertexGeminiChat()

    def get_agent_welcome(self, current_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generates an initial welcoming greeting and context-aware quick suggestions
        tailored to the active store or industry.
        """
        current_config = current_config or {}
        industry = current_config.get("industry") or "general luxury"
        name = current_config.get("name") or "your boutique"

        templates = list_templates()
        industry_names = [t.get("name", t.get("industry", "")) for t in templates[:4]]

        suggestions = [
            f"Configure for {templates[0]['name']}" if templates else "Configure for Fine Jewelry",
            f"Configure for {templates[1]['name']}" if len(templates) > 1 else "Configure for Haute Couture",
            f"Configure for {templates[2]['name']}" if len(templates) > 2 else "Configure for Haute Horlogerie",
        ]

        reply = (
            f"Welcome to the VIP Concierge Experience Studio. I am your LangChain AI Retail Experience Consultant.\n\n"
            f"I help tailor in-store biometric radar, client attribute tracking, and 3-second staff briefings "
            f"specifically for {name} ({industry.title()}).\n\n"
            f"Tell me about your boutique: What is your brand name, your VIP spend brackets, "
            f"and what critical client attributes or sizing details should our staff have before greeting them?"
        )

        return {
            "reply": reply,
            "quick_suggestions": suggestions,
            "active_industry": industry,
        }

    def consult(
        self,
        user_message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        current_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Interactive conversational consultation with the shop owner.
        Uses LangChain VertexGeminiChat with Pydantic domain models for synthesis.
        """
        chat_history = chat_history or []
        current_config = current_config or {}

        industry = current_config.get("industry") or "clothing"
        base_template = get_template(industry) or {}

        # Available template industries for reference
        available_templates = list_templates()
        template_summary = [
            f"- {t.get('industry')}: {t.get('name')} (Brand tone: {t.get('brand_tone', '')[:60]}...)"
            for t in available_templates
        ]

        system_prompt = f"""You are an elite In-Store Retail Experience Architect & Clienteling Consultant.
You are interviewing a store owner to configure their in-store AI VIP Concierge & Facial Recognition Radar.

Current Active Profile:
{json.dumps(current_config, indent=2) if current_config else "No existing profile."}

Available Industry Blueprints in Database:
{chr(10).join(template_summary)}

Your Objectives:
1. Conduct an intelligent, consultative dialogue.
2. Inquire about their store niche, brand hospitality tone, VIP tier spend thresholds, customer attributes to record (e.g. ring sizes for jewelry, jacket sizes for clothing, complication interests for watches, art period preferences for galleries), and staff greeting etiquette.
3. Continually synthesize and update the store configuration.

CRITICAL INSTRUCTIONS:
- You MUST respond with a valid JSON object wrapped in ```json ```.
- Include these exact keys:
  "reply": (string) Your warm, consultative, expert reply to the shop manager. Acknowledge what they shared and ask 1-2 focused questions if anything is missing.
  "proposed_config": (object) The complete updated shop configuration with:
      - "name": Store brand name
      - "industry": Store industry classification
      - "brand_tone": Concise phrase describing the etiquette (e.g. "Quiet luxury, discreet and heirloom-focused")
      - "vip_tiers": Array of objects: [{{"name": "Diamond", "min_spend": 25000, "perks": "..."}}]
      - "client_attributes_schema": Array of objects: [{{"key": "ring_size", "label": "Ring Finger Size", "type": "text" | "tags" | "date" | "number"}}]
      - "greeting_protocol": Step-by-step greeting procedure for staff when the VIP is recognized
      - "ai_briefing_prompt": Custom prompt instruction for the 3-second staff briefing
  "quick_suggestions": Array of 3 short suggested replies (strings) the store owner can click to answer quickly.
"""

        messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]

        for turn in chat_history[-6:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))

        messages.append(HumanMessage(content=user_message))

        try:
            chain = self.chat_model | RunnableLambda(lambda msg: extract_json_payload(msg.content))
            raw_result = chain.invoke(messages)

            if raw_result and isinstance(raw_result, dict) and "reply" in raw_result:
                # Validate with Pydantic ConsultationResponseModel
                try:
                    validated = ConsultationResponseModel.model_validate(raw_result)
                    return validated.model_dump()
                except Exception as val_exc:
                    logger.warning("Pydantic validation warning on consultation response: %s; normalizing", val_exc)
                    # Normalize proposed_config with ShopConfigModel
                    proposed = raw_result.get("proposed_config") or {}
                    validated_config = ShopConfigModel.model_validate(proposed)
                    return {
                        "reply": str(raw_result.get("reply")),
                        "proposed_config": validated_config.model_dump(),
                        "quick_suggestions": list(raw_result.get("quick_suggestions") or [
                            "Review VIP spend tiers",
                            "Customize client sizing attributes",
                            "Save and activate this store"
                        ]),
                    }
        except Exception as exc:
            logger.error("LangChain consultation chain failed: %s", exc)

        # Dynamic fallback matching the requested industry
        fallback_config = ShopConfigModel.model_validate(base_template).model_dump()
        fallback_name = fallback_config.get("name", "Boutique")
        return {
            "reply": (
                f"I would love to help configure the VIP Concierge for {fallback_name}. "
                f"What are your typical VIP spending milestones, and what specific client sizes or taste preferences "
                f"should your staff have on their briefing card?"
            ),
            "proposed_config": fallback_config,
            "quick_suggestions": [
                f"Customize {fallback_config.get('industry', 'boutique').title()} Tiers",
                "Add custom client attributes",
                "Define greeting etiquette protocol",
            ],
        }

    def generate_preset(
        self,
        industry: str,
        store_name: Optional[str] = None,
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fast-track generation: Creates or personalizes an industry configuration.
        Leverages MongoDB templates as baseline and uses LangChain for bespoke tailoring.
        """
        key = industry.lower().strip()
        template = get_template(key) or get_template("clothing") or {}
        config_data = dict(template)

        if store_name:
            config_data["name"] = store_name.strip()

        # If custom owner details or non-standard industry provided, personalize via LangChain
        if details or key not in ["clothing", "jewelry", "watches", "automotive", "art", "perfumery"]:
            prompt = f"""You are an elite Luxury Retail In-Store Experience Architect.
Configure an in-store VIP Concierge profile for a store with:
- Industry: {key}
- Store Name: {store_name or config_data.get('name', 'Boutique')}
- Owner Description / Specialization: "{details or 'Tailored for this specific luxury specialty'}"
- Base Reference: {json.dumps(config_data)}

Respond ONLY with a valid JSON object wrapped in ```json ``` with keys:
name, industry, brand_tone, vip_tiers, client_attributes_schema, greeting_protocol, ai_briefing_prompt
"""
            try:
                raw = self.chat_model.invoke([HumanMessage(content=prompt)])
                parsed = extract_json_payload(raw.content)
                if parsed and isinstance(parsed, dict):
                    validated = ShopConfigModel.model_validate(parsed)
                    return validated.model_dump()
            except Exception as e:
                logger.warning("Could not customize preset with LangChain: %s", e)

        # Return validated config from template
        return ShopConfigModel.model_validate(config_data).model_dump()


shop_consultant_agent = ShopConsultantAgent()
