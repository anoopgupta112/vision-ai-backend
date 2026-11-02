import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import get_collection

logger = logging.getLogger(__name__)


def _searches_col():
    return get_collection("reddit_searches")


def _saved_col():
    return get_collection("reddit_saved_posts")


def save_search_session(
    user_id: str,
    product_name: str,
    website_url: Optional[str],
    description: Optional[str],
    target_audience: Optional[str],
    problems_solved: Optional[str],
    subreddits: Optional[List[str]],
    date_range: Optional[str],
    product_profile: Dict[str, Any],
    opportunities: List[Dict[str, Any]],
    stats: Dict[str, Any],
    competitor_mentions: Optional[List[Dict[str, Any]]] = None,
    brand_sentiments: Optional[List[Dict[str, Any]]] = None,
    sentiment_breakdown: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Saves a complete Reddit lead discovery session to MongoDB.
    """
    search_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    doc = {
        "search_id": search_id,
        "user_id": str(user_id),
        "product_name": product_name,
        "website_url": website_url or "",
        "description": description or "",
        "target_audience": target_audience or "",
        "problems_solved": problems_solved or "",
        "subreddits": subreddits or [],
        "date_range": date_range or "all_time",
        "product_profile": product_profile,
        "opportunities": opportunities,
        "competitor_mentions": competitor_mentions or [],
        "brand_sentiments": brand_sentiments or [],
        "sentiment_breakdown": sentiment_breakdown or {"positive": 0, "mixed": 0, "neutral": 0, "negative": 0, "total": 0},
        "stats": stats,
        "created_at": now,
        "updated_at": now,
    }

    _searches_col().insert_one(doc)
    doc["_id"] = str(doc.get("_id", search_id))
    return doc


def get_user_searches(user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Returns recent search sessions for a user (without heavy post bodies for speed).
    """
    docs = list(
        _searches_col()
        .find(
            {"user_id": str(user_id)},
            {
                "search_id": 1,
                "product_name": 1,
                "website_url": 1,
                "subreddits": 1,
                "stats": 1,
                "created_at": 1,
                "opportunities_count": {"$size": "$opportunities"},
            },
        )
        .sort("created_at", -1)
        .limit(limit)
    )

    results = []
    for d in docs:
        d["_id"] = str(d["_id"])
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        results.append(d)
    return results


def get_search_session(search_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves full search session and annotates saved/bookmarked statuses.
    """
    doc = _searches_col().find_one({"search_id": search_id, "user_id": str(user_id)})
    if not doc:
        return None

    doc["_id"] = str(doc["_id"])
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    if isinstance(doc.get("updated_at"), datetime):
        doc["updated_at"] = doc["updated_at"].isoformat()

    breakdown = {"positive": 0, "mixed": 0, "neutral": 0, "negative": 0}
    for mention in doc.get("brand_sentiments", []):
        sentiment = str(mention.get("brand_sentiment") or "Neutral").lower()
        breakdown[sentiment if sentiment in breakdown else "neutral"] += 1
    breakdown["total"] = sum(breakdown.values())
    doc["sentiment_breakdown"] = breakdown
    doc.setdefault("stats", {}).update({
        "competitor_mentions_count": len(doc.get("competitor_mentions", [])),
        "brand_mentions_count": len(doc.get("brand_sentiments", []))})

    # Query user's saved posts to tag opportunities
    saved_posts = set(
        s.get("post_id")
        for s in _saved_col().find({"user_id": str(user_id)}, {"post_id": 1})
    )

    for opp in doc.get("opportunities", []):
        opp["is_saved"] = opp.get("post_id") in saved_posts

    return doc


def delete_search_session(search_id: str, user_id: str) -> bool:
    """
    Deletes a search session for the user.
    """
    res = _searches_col().delete_one({"search_id": search_id, "user_id": str(user_id)})
    return res.deleted_count > 0


def toggle_save_post(user_id: str, search_id: str, post_id: str, post_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    Toggles bookmark/saved status for an opportunity.
    Returns True if now saved, False if removed.
    """
    existing = _saved_col().find_one({"user_id": str(user_id), "post_id": post_id})
    if existing:
        _saved_col().delete_one({"user_id": str(user_id), "post_id": post_id})
        return False

    # Fetch post data from search if not directly passed
    if not post_data:
        search = _searches_col().find_one({"search_id": search_id, "user_id": str(user_id)})
        if search:
            for opp in search.get("opportunities", []):
                if opp.get("post_id") == post_id:
                    post_data = opp
                    break

    now = datetime.now(timezone.utc)
    _saved_col().insert_one({
        "user_id": str(user_id),
        "search_id": search_id,
        "post_id": post_id,
        "post_data": post_data or {},
        "saved_at": now,
    })
    return True


def dismiss_post(user_id: str, search_id: str, post_id: str) -> bool:
    """
    Marks a post as dismissed in the search session.
    """
    return update_post(user_id, search_id, post_id, {"status": "dismissed"})


def get_saved_posts(user_id: str) -> List[Dict[str, Any]]:
    """
    Returns all saved opportunities for a user across all searches.
    """
    docs = list(_saved_col().find({"user_id": str(user_id)}).sort("saved_at", -1))
    results = []
    for d in docs:
        post = d.get("post_data", {})
        post["saved_at"] = d.get("saved_at", datetime.now(timezone.utc)).isoformat()
        post["is_saved"] = True
        post["search_id"] = d.get("search_id")
        results.append(post)
    return results


def update_post(user_id, search_id, post_id, fields):
    """Update the owned post wherever it occurs; repeated updates are idempotent."""
    found = False
    for key in ("opportunities", "competitor_mentions", "brand_sentiments"):
        result = _searches_col().update_one(
            {"user_id": str(user_id), "search_id": search_id, key + ".post_id": post_id},
            {"$set": {key + ".$." + field: value for field, value in fields.items()}})
        found = found or result.matched_count > 0
    if found:
        _saved_col().update_many({"user_id": str(user_id), "post_id": post_id},
            {"$set": {"post_data." + key: value for key, value in fields.items()}})
    return found


def save_feedback(user_id, search_id, post_id, vote, reason):
    doc = get_search_session(search_id, user_id)
    if not doc:
        return False
    post = next((p for key in ("opportunities", "competitor_mentions", "brand_sentiments") for p in doc.get(key, []) if p.get("post_id") == post_id), None)
    if not post:
        return False
    product_key = doc["product_name"].strip().casefold()
    feedback_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(user_id) + ":" + product_key + ":" + post_id))
    feedback = {"vote": vote, "reason": reason.strip()[:1000]}
    get_collection("reddit_feedback").update_one({"_id": feedback_id}, {"$set": {
        "user_id": str(user_id), "product_key": product_key, "post_id": post_id,
        "title": post.get("title", ""), "subreddit": post.get("subreddit", ""),
        **feedback, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return update_post(user_id, search_id, post_id, {"feedback": feedback})


def get_feedback_preferences(user_id, product_name):
    docs = get_collection("reddit_feedback").find(
        {"user_id": str(user_id), "product_key": product_name.strip().casefold()},
        {"_id": 0, "title": 1, "subreddit": 1, "vote": 1, "reason": 1}
    ).sort("updated_at", -1).limit(30)
    return list(docs)
