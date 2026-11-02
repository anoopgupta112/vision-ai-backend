import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


def _clean_numeric(val: Any, default: float = 0.0) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        match = re.search(r"(\d[\d,]*(?:\.\d+)?)", val)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return default


class VipTierModel(BaseModel):
    name: str = Field(default="VIP", description="Name of the VIP tier, e.g. Diamond, Platinum, Gold, Patron")
    min_spend: float = Field(default=0.0, description="Minimum qualifying lifetime spend in USD")
    perks: str = Field(default="", description="Specific hospitality amenities or services")

    @model_validator(mode="before")
    @classmethod
    def normalize_tier(cls, data: Any) -> Any:
        if isinstance(data, str):
            parts = data.split("-", 1)
            raw_name = parts[0].strip()
            perks = parts[1].strip() if len(parts) > 1 else "Exclusive hospitality recognition"
            spend = _clean_numeric(raw_name, default=5000.0)
            clean_name = re.sub(r"\([^)]*\)", "", raw_name).strip() or "VIP"
            return {"name": clean_name, "min_spend": spend, "perks": perks}
        if isinstance(data, dict):
            spend = _clean_numeric(data.get("min_spend"), default=0.0)
            name = str(data.get("name") or "VIP").strip()
            perks = str(data.get("perks") or "").strip()
            return {"name": name, "min_spend": spend, "perks": perks}
        return data


class ClientAttributeModel(BaseModel):
    key: str = Field(description="Normalized snake_case attribute key, e.g. ring_size, jacket_size")
    label: str = Field(description="User-facing display label, e.g. Ring Finger Size, Chest / Jacket")
    type: str = Field(default="text", description="Data type: text, tags, date, or number")

    @model_validator(mode="before")
    @classmethod
    def normalize_attr(cls, data: Any) -> Any:
        if isinstance(data, str):
            clean = data.strip()
            key = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", clean.lower())).strip("_") or "custom_attribute"
            return {"key": key, "label": clean, "type": "text"}
        if isinstance(data, dict):
            raw_key = str(data.get("key") or data.get("name") or "").strip().lower()
            key = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", raw_key)).strip("_")
            label = str(data.get("label") or data.get("name") or key.replace("_", " ").title()).strip()
            attr_type = str(data.get("type") or "text").strip().lower()
            if attr_type not in ("text", "tags", "date", "number", "select"):
                attr_type = "text"
            if not key:
                key = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", label.lower())).strip("_") or "attribute"
            return {"key": key, "label": label, "type": attr_type}
        return data


class ShopConfigModel(BaseModel):
    shop_id: Optional[str] = Field(default=None, description="Unique shop slug or identifier")
    name: str = Field(default="Luxury Boutique", description="Store or brand name")
    industry: str = Field(default="clothing", description="Industry classification (clothing, jewelry, watches, automotive, art, perfumery, custom)")
    brand_tone: str = Field(default="Bespoke luxury and discreet clienteling", description="Brand hospitality tone and etiquette")
    vip_tiers: List[VipTierModel] = Field(default_factory=list, description="List of VIP qualification tiers")
    client_attributes_schema: List[ClientAttributeModel] = Field(default_factory=list, description="Client sizing and taste attributes to track")
    greeting_protocol: str = Field(default="", description="Standard operating procedure for staff when VIP arrives")
    ai_briefing_prompt: str = Field(default="", description="Custom instructions for generating the staff briefing")
    is_active: bool = Field(default=True, description="Whether this is the currently active store")


class ConsultationResponseModel(BaseModel):
    reply: str = Field(description="Conversational advice, feedback, and targeted follow-up questions from the AI consultant")
    proposed_config: ShopConfigModel = Field(description="Synthesized store configuration profile")
    quick_suggestions: List[str] = Field(default_factory=list, description="Clickable reply recommendations for the user")


class BriefingDossierModel(BaseModel):
    headline: str = Field(description="Summary alert headline including customer name and spend")
    greeting_approach: str = Field(description="Natural, subtle 1-sentence greeting for the associate without mentioning CCTV")
    talking_point: str = Field(description="1-2 sentences referencing taste or previous purchase")
    suggested_items: List[str] = Field(default_factory=list, description="Personalized recommendations tailored to the store catalog")
    preferences_alert: str = Field(default="", description="Crucial sizing, anniversary, or hospitality preference to remember")
