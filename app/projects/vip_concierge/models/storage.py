from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId

from app.core.database import get_collection


def customers_col():
    return get_collection("vip_customers")


def visits_col():
    return get_collection("vip_visits")


def cameras_col():
    return get_collection("vip_cameras")


def shops_col():
    return get_collection("vip_shops")


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return {}
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    if "face_embedding" in doc:
        doc["face_enrolled"] = bool(doc.get("face_embedding") and len(doc.get("face_embedding") or []) >= 128)
        doc.pop("face_embedding", None)
    return doc


def create_customer(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    customer_doc = {
        "user_id": user_id,
        "shop_id": data.get("shop_id", "default"),
        "name": data["name"],
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "tier": data.get("tier", "Gold"),
        "total_spent": float(data.get("total_spent", 0.0)),
        "currency": data.get("currency", "USD"),
        "sizes": data.get("sizes", {}),
        "preferred_styles": data.get("preferred_styles", []),
        "notes": data.get("notes", ""),
        "purchases": data.get("purchases", []),
        "avatar_url": data.get("avatar_url", ""),
        "registered_face_thumbnail": data.get("registered_face_thumbnail", ""),
        "face_embedding": data.get("face_embedding"),
        "visit_count": int(data.get("visit_count", 0)),
        "last_visit_at": None,
        "created_at": now,
        "updated_at": now,
    }
    res = customers_col().insert_one(customer_doc)
    customer_doc["id"] = str(res.inserted_id)
    customer_doc.pop("_id", None)
    return serialize_doc(customer_doc)


def get_customer(customer_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {"_id": ObjectId(customer_id)}
    if user_id:
        query["user_id"] = user_id
    doc = customers_col().find_one(query)
    return serialize_doc(doc) if doc else None


def list_customers(
    user_id: str, shop_id: Optional[str] = None, limit: int = 50, skip: int = 0
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"user_id": user_id}
    if shop_id:
        query["shop_id"] = shop_id
    cursor = customers_col().find(query).sort("total_spent", -1).skip(skip).limit(limit)
    return [serialize_doc(d) for d in cursor]


def update_customer(customer_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updates["updated_at"] = datetime.now(timezone.utc)
    res = customers_col().find_one_and_update(
        {"_id": ObjectId(customer_id), "user_id": user_id},
        {"$set": updates},
        return_document=True,
    )
    return serialize_doc(res) if res else None


def delete_customer(customer_id: str, user_id: str) -> bool:
    res = customers_col().delete_one({"_id": ObjectId(customer_id), "user_id": user_id})
    return res.deleted_count > 0


def log_visit(event_data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    visit_doc = {
        "customer_id": event_data["customer_id"],
        "user_id": event_data.get("user_id"),
        "shop_id": event_data.get("shop_id", "default"),
        "camera_id": event_data.get("camera_id", "webcam"),
        "confidence": float(event_data.get("confidence", 0.0)),
        "alert_triggered": bool(event_data.get("alert_triggered", True)),
        "live_crop_b64": event_data.get("live_crop_b64", ""),
        "dossier": event_data.get("dossier", {}),
        "status": "new",  # new | greeted | dismissed
        "staff_notes": "",
        "created_at": now,
    }
    res = visits_col().insert_one(visit_doc)
    visit_doc["id"] = str(res.inserted_id)
    visit_doc.pop("_id", None)

    # Update customer visit stats
    customers_col().update_one(
        {"_id": ObjectId(event_data["customer_id"])},
        {
            "$inc": {"visit_count": 1},
            "$set": {"last_visit_at": now},
        },
    )
    return serialize_doc(visit_doc)


def list_recent_visits(
    user_id: Optional[str] = None, shop_id: Optional[str] = None, limit: int = 30
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if user_id:
        query["user_id"] = user_id
    if shop_id:
        query["shop_id"] = shop_id
    cursor = visits_col().find(query).sort("created_at", -1).limit(limit)
    return [serialize_doc(d) for d in cursor]


def update_visit_status(visit_id: str, status: str, staff_notes: str = "") -> bool:
    res = visits_col().update_one(
        {"_id": ObjectId(visit_id)},
        {"$set": {"status": status, "staff_notes": staff_notes, "updated_at": datetime.now(timezone.utc)}},
    )
    return res.modified_count > 0


def list_cameras(user_id: str, shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"user_id": user_id}
    if shop_id:
        query["shop_id"] = shop_id
    cursor = cameras_col().find(query).sort("created_at", -1)
    return [serialize_doc(d) for d in cursor]


def create_camera(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    camera_doc = {
        "user_id": user_id,
        "shop_id": data.get("shop_id", "default"),
        "name": data["name"],
        "rtsp_url": data.get("rtsp_url", ""),
        "location": data.get("location", "Main Entrance"),
        "is_active": bool(data.get("is_active", True)),
        "created_at": now,
        "updated_at": now,
    }
    res = cameras_col().insert_one(camera_doc)
    camera_doc["id"] = str(res.inserted_id)
    camera_doc.pop("_id", None)
    return serialize_doc(camera_doc)


def get_camera(camera_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if ObjectId.is_valid(camera_id):
        query["_id"] = ObjectId(camera_id)
    else:
        query["id"] = camera_id
    if user_id:
        query["user_id"] = user_id
    doc = cameras_col().find_one(query)
    return serialize_doc(doc) if doc else None


def delete_camera(camera_id: str, user_id: str) -> bool:
    res = cameras_col().delete_one({"_id": ObjectId(camera_id), "user_id": user_id})
    return res.deleted_count > 0


# ==============================================================================
# Shop Configuration Storage
# ==============================================================================

DEFAULT_SHOP_PROFILE = {
    "shop_id": "default",
    "name": "Maison De Luxe",
    "industry": "clothing",
    "brand_tone": "Warm bespoke European luxury, discreet and attentive",
    "vip_tiers": [
        {"name": "Diamond", "min_spend": 15000, "perks": "Private VIP Salon, reserved vintage champagne, dedicated personal stylist"},
        {"name": "Platinum", "min_spend": 5000, "perks": "First access to runway capsules, complimentary alterations"},
        {"name": "Gold", "min_spend": 1500, "perks": "Complimentary garment pressing, espresso service"}
    ],
    "client_attributes_schema": [
        {"key": "jacket_size", "label": "Jacket / Chest Size", "type": "text"},
        {"key": "shoe_size", "label": "Shoe Size", "type": "text"},
        {"key": "favorite_fabrics", "label": "Favorite Fabrics (Linen, Silk, Cashmere)", "type": "tags"},
        {"key": "fit_preference", "label": "Fit Preference (Slim, Structured, Relaxed)", "type": "text"}
    ],
    "greeting_protocol": "1. Greet by name with warm eye contact within 5 seconds. 2. Offer preferred refreshment (espresso/champagne). 3. Escort to styling suite with curated pieces matching their size.",
    "ai_briefing_prompt": "Focus on tailoring fit, garment craftsmanship, complementary pieces to past purchases, and upcoming seasonal wardrobe needs.",
    "is_active": True,
}


def get_shop(shop_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {"shop_id": shop_id}
    if user_id:
        query["user_id"] = user_id
    doc = shops_col().find_one(query)
    if not doc and ObjectId.is_valid(shop_id):
        query_id: Dict[str, Any] = {"_id": ObjectId(shop_id)}
        if user_id:
            query_id["user_id"] = user_id
        doc = shops_col().find_one(query_id)
    return serialize_doc(doc) if doc else None


def get_active_shop(user_id: Optional[str] = None) -> Dict[str, Any]:
    if user_id:
        doc = shops_col().find_one({"user_id": user_id, "is_active": True})
        if not doc:
            doc = shops_col().find_one({"user_id": user_id}, sort=[("updated_at", -1)])
        if doc:
            return serialize_doc(doc)

    doc_default = shops_col().find_one({"shop_id": "default"})
    if doc_default:
        return serialize_doc(doc_default)

    return dict(DEFAULT_SHOP_PROFILE)


def list_shops(user_id: str) -> List[Dict[str, Any]]:
    cursor = shops_col().find({"user_id": user_id}).sort("updated_at", -1)
    results = [serialize_doc(d) for d in cursor]
    if not results:
        results.append(get_active_shop(user_id))
    return results


def upsert_shop(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    shop_id = (data.get("shop_id") or data.get("id") or "").strip()
    if not shop_id or shop_id == "default":
        name = data.get("name", "Boutique").strip()
        slug = "".join(c if c.isalnum() else "_" for c in name.lower())[:24]
        shop_id = f"shop_{slug}_{int(now.timestamp())}"

    is_active = bool(data.get("is_active", True))
    if is_active:
        shops_col().update_many({"user_id": user_id}, {"$set": {"is_active": False}})

    shop_doc = {
        "user_id": user_id,
        "shop_id": shop_id,
        "name": data.get("name", "Luxury Boutique").strip(),
        "industry": data.get("industry", "clothing").strip().lower(),
        "brand_tone": data.get("brand_tone", "Warm bespoke luxury, discreet and attentive"),
        "vip_tiers": data.get("vip_tiers", []),
        "client_attributes_schema": data.get("client_attributes_schema", []),
        "greeting_protocol": data.get("greeting_protocol", ""),
        "ai_briefing_prompt": data.get("ai_briefing_prompt", ""),
        "is_active": is_active,
        "updated_at": now,
    }

    res = shops_col().find_one_and_update(
        {"shop_id": shop_id, "user_id": user_id},
        {"$set": shop_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
        return_document=True,
    )
    return serialize_doc(res)


def set_active_shop(user_id: str, shop_id: str) -> bool:
    shops_col().update_many({"user_id": user_id}, {"$set": {"is_active": False}})
    res = shops_col().update_one(
        {"user_id": user_id, "shop_id": shop_id},
        {"$set": {"is_active": True, "updated_at": datetime.now(timezone.utc)}}
    )
    return res.matched_count > 0


