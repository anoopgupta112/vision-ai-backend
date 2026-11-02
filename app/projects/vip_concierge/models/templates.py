import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.core.database import get_collection
from app.projects.vip_concierge.models.schemas import ShopConfigModel, VipTierModel, ClientAttributeModel

logger = logging.getLogger(__name__)


def templates_col():
    return get_collection("vip_shop_templates")


# Seed data if collection is brand new
SEED_TEMPLATES: List[Dict[str, Any]] = [
    {
        "template_id": "jewelry",
        "name": "Fine Jewelry & Rare Gems",
        "industry": "jewelry",
        "icon": "gem",
        "tagline": "Rings, Gems, Anniversaries",
        "brand_tone": "Quiet luxury, generational trust, private vault hospitality, heirloom appreciation",
        "vip_tiers": [
            {"name": "Diamond", "min_spend": 50000, "perks": "Private vault viewing, Head Gemologist dedicated, iced vintage champagne, bespoke commissions"},
            {"name": "Platinum", "min_spend": 20000, "perks": "Priority access to rare gemstone acquisitions, annual complimentary clean & inspect"},
            {"name": "Gold", "min_spend": 5000, "perks": "Custom engraving, private salon preview"}
        ],
        "client_attributes_schema": [
            {"key": "ring_size", "label": "Ring Finger Size", "type": "text"},
            {"key": "metal_preference", "label": "Preferred Metals (Platinum, 18k Rose Gold)", "type": "tags"},
            {"key": "gemstone_preference", "label": "Gemstone Tastes (Emeralds, Sapphires, Diamonds)", "type": "tags"},
            {"key": "anniversary_date", "label": "Anniversary / Milestone Date", "type": "date"},
            {"key": "spouse_name", "label": "Spouse / Partner Name", "type": "text"}
        ],
        "greeting_protocol": "1. Welcome discreetly by surname. 2. Escort directly to Private Viewing Salon A. 3. Offer chilled vintage champagne and bring the Head Gemologist with pieces matching upcoming anniversary milestones.",
        "ai_briefing_prompt": "Alert staff to significant dates (anniversaries, birthdays), note metal & stone preferences (e.g. Platinum, Emeralds), and highlight rare pieces matching their collection.",
    },
    {
        "template_id": "clothing",
        "name": "Haute Couture & Tailoring",
        "industry": "clothing",
        "icon": "shopping-bag",
        "tagline": "Tailoring, Sizes, Fabrics",
        "brand_tone": "Warm bespoke European luxury, discreet and attentive styling",
        "vip_tiers": [
            {"name": "Diamond", "min_spend": 15000, "perks": "Private VIP Salon, reserved vintage champagne, dedicated master stylist"},
            {"name": "Platinum", "min_spend": 5000, "perks": "First access to runway capsules, complimentary alterations"},
            {"name": "Gold", "min_spend": 1500, "perks": "Complimentary garment pressing, espresso service"}
        ],
        "client_attributes_schema": [
            {"key": "jacket_size", "label": "Jacket / Chest Size", "type": "text"},
            {"key": "shoe_size", "label": "Shoe Size", "type": "text"},
            {"key": "waist_size", "label": "Trousers / Waist Size", "type": "text"},
            {"key": "favorite_fabrics", "label": "Favorite Fabrics (Loro Piana Cashmere, Silk, Linen)", "type": "tags"},
            {"key": "fit_preference", "label": "Fit Preference (Slim, Structured, Relaxed)", "type": "text"}
        ],
        "greeting_protocol": "1. Greet by name with warm eye contact within 5 seconds. 2. Offer preferred refreshment (espresso/champagne). 3. Escort to styling suite with curated pieces matching their size.",
        "ai_briefing_prompt": "Focus on garment tailoring fit, fabric craftsmanship, complementary pieces to past purchases, and upcoming seasonal wardrobe needs.",
    },
    {
        "template_id": "watches",
        "name": "Haute Horlogerie & Timepieces",
        "industry": "watches",
        "icon": "clock",
        "tagline": "Complications, Cases, Reference Wishlists",
        "brand_tone": "Swiss watchmaking reverence, technical connoisseurship, collector camaraderie",
        "vip_tiers": [
            {"name": "Diamond", "min_spend": 75000, "perks": "Allocation for Grand Complications, manufacture tours in Vallée de Joux"},
            {"name": "Platinum", "min_spend": 25000, "perks": "Limited edition allocations, master watchmaker regulation service"},
            {"name": "Gold", "min_spend": 10000, "perks": "Collector cocktail evenings, complimentary bespoke strap"}
        ],
        "client_attributes_schema": [
            {"key": "wrist_size", "label": "Wrist Size (mm)", "type": "text"},
            {"key": "favorite_complications", "label": "Complications (Chronograph, Tourbillon, Perpetual Calendar)", "type": "tags"},
            {"key": "case_metals", "label": "Preferred Metals (Titanium, Rose Gold, Platinum)", "type": "tags"},
            {"key": "grail_wishlist", "label": "Grail Wishlist Reference Numbers", "type": "text"}
        ],
        "greeting_protocol": "1. Greet the collector by name. 2. Offer single-malt Scotch or espresso. 3. Discreetly prepare loupe, velvet tray, and newest allocated reference.",
        "ai_briefing_prompt": "Brief staff on collector's technical interests, current collection gaps, and newly arrived references with high horological interest.",
    },
    {
        "template_id": "automotive",
        "name": "Exotic & Hypercars",
        "industry": "automotive",
        "icon": "radio",
        "tagline": "Garage Fleet, Track Spec, Bespoke Delivery",
        "brand_tone": "High-octane prestige, motorsport heritage, white-glove bespoke commissioning",
        "vip_tiers": [
            {"name": "Diamond", "min_spend": 250000, "perks": "Track-day hospitality, allocation for limited hypercars, factory aero delivery"},
            {"name": "Platinum", "min_spend": 100000, "perks": "Priority service vehicle collection, bespoke interior commissioning sessions"},
            {"name": "Gold", "min_spend": 50000, "perks": "VIP lounge access, invite to annual supercar rally"}
        ],
        "client_attributes_schema": [
            {"key": "current_garage", "label": "Current Vehicles in Garage", "type": "text"},
            {"key": "preferred_spec", "label": "Preferred Spec (Carbon package, Alcantara, Manual)", "type": "tags"},
            {"key": "track_interest", "label": "Track vs Grand Touring Preference", "type": "text"}
        ],
        "greeting_protocol": "1. Greet with enthusiasm by name. 2. Offer barista espresso in the VIP Heritage Lounge. 3. Pull up vehicle configuration studio on the 4K display.",
        "ai_briefing_prompt": "Remind sales consultant of current garage fleet, track preferences, and launch allocation updates.",
    },
    {
        "template_id": "art",
        "name": "Fine Art & Antiques",
        "industry": "art",
        "icon": "sparkles",
        "tagline": "Provenance, Wall Specs, Vernissage Previews",
        "brand_tone": "Curatorial sophistication, cultural depth, intellectual and discreet clienteling",
        "vip_tiers": [
            {"name": "Diamond", "min_spend": 100000, "perks": "Private gallery previews before vernissage, private dinner with the artist"},
            {"name": "Platinum", "min_spend": 30000, "perks": "Curator studio visits, primary market access"},
            {"name": "Gold", "min_spend": 10000, "perks": "Private catalog previews, art fair VIP passes"}
        ],
        "client_attributes_schema": [
            {"key": "collecting_focus", "label": "Focus (Post-War Contemporary, Abstract, Sculpture)", "type": "tags"},
            {"key": "wall_dimensions", "label": "Living Space / Gallery Wall Dimensions", "type": "text"},
            {"key": "favorite_artists", "label": "Favorite Artists / Periods", "type": "text"}
        ],
        "greeting_protocol": "1. Acknowledge by name warmly. 2. Lead to the private viewing gallery with custom lighting. 3. Offer sparkling wine and provide curatorial condition reports.",
        "ai_briefing_prompt": "Highlight artist provenance, thematic links to existing collection, and rarity of the medium.",
    },
    {
        "template_id": "perfumery",
        "name": "Haute Parfumerie & Fragrance",
        "industry": "perfumery",
        "icon": "wand-2",
        "tagline": "Olfactive Notes, Scent Profiles, Flacons",
        "brand_tone": "Sensory intimacy, olfactive artistry, bespoke formulation etiquette",
        "vip_tiers": [
            {"name": "Diamond", "min_spend": 5000, "perks": "Custom bespoke formulation with Master Nez, engraved crystal flacon"},
            {"name": "Platinum", "min_spend": 1500, "perks": "Seasonal private vintage releases, private fragrance masterclasses"},
            {"name": "Gold", "min_spend": 500, "perks": "Complimentary travel atomizer refilling, priority bookings"}
        ],
        "client_attributes_schema": [
            {"key": "scent_families", "label": "Preferred Notes (Oud, Amber, Iris, Bergamot, Leather)", "type": "tags"},
            {"key": "skin_sensitivity", "label": "Skin Sensitivity / Alcohol Tolerance", "type": "text"},
            {"key": "signature_scent", "label": "Current Signature Fragrance", "type": "text"}
        ],
        "greeting_protocol": "1. Greet by name and offer room-temperature still water to cleanse palate. 2. Escort to the Olfactive Bar with raw fragrance extracts and ceramic smelling stones.",
        "ai_briefing_prompt": "Remind consultant of preferred olfactive accords, avoid allergens, and suggest harmonious extrait de parfum pairings.",
    }
]


def ensure_templates_seeded():
    """Initializes templates collection in MongoDB if empty."""
    col = templates_col()
    if col.count_documents({}) == 0:
        now = datetime.now(timezone.utc)
        for t in SEED_TEMPLATES:
            doc = dict(t)
            doc["created_at"] = now
            col.update_one({"template_id": doc["template_id"]}, {"$set": doc}, upsert=True)
        logger.info("Seeded %d VIP store templates into database", len(SEED_TEMPLATES))


def list_templates() -> List[Dict[str, Any]]:
    ensure_templates_seeded()
    cursor = templates_col().find({}, {"_id": 0})
    templates = list(cursor)
    return templates if templates else SEED_TEMPLATES


def get_template(industry: str) -> Optional[Dict[str, Any]]:
    ensure_templates_seeded()
    key = industry.lower().strip()
    doc = templates_col().find_one({"$or": [{"template_id": key}, {"industry": key}]}, {"_id": 0})
    if doc:
        return doc
    # Fallback to clothing if unknown
    return next((t for t in SEED_TEMPLATES if t["industry"] == key), SEED_TEMPLATES[1])

