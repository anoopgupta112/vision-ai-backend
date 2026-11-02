import logging
import time
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from app.core.middleware import auth_required, get_current_user
from app.projects.reddit_leads.models import storage
from app.projects.reddit_leads.services.ai_client import get_current_provider, RedditAIClientError
from app.projects.reddit_leads.services.safe_fetch import UnsafeURL
from app.projects.reddit_leads.services.reddit_searcher import RedditSearchError, DATE_DAYS
from app.projects.reddit_leads.services.comment_generator import (
    STYLE_DESCRIPTIONS,
    generate_comment_drafts_for_post,
    batch_generate_comments,
)
from app.projects.reddit_leads.services.post_evaluator import evaluate_posts
from app.projects.reddit_leads.services.product_researcher import research_product
from app.projects.reddit_leads.services.reddit_searcher import search_reddit_discussions

logger = logging.getLogger(__name__)

bp = Blueprint("reddit_leads", __name__, url_prefix="/api/reddit-leads")

@bp.errorhandler(ValueError)
def invalid_input(error):
    return jsonify({"error": str(error)}), 400


@bp.errorhandler(RedditSearchError)
@bp.errorhandler(RedditAIClientError)
def provider_error(error):
    return jsonify({"error": str(error)}), 503


def request_data():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    for key in ["product_name", "website_url", "description", "target_audience", "problems_solved", "target_country", "date_range", "search_id", "vote", "reason"]:
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > (10000 if key == "description" else 2000)):
            raise ValueError(key + " must be a string within the allowed length.")
    subs = data.get("subreddits", [])
    import re
    if not isinstance(subs, list) or len(subs) > 10 or any(not isinstance(v, str) or not re.fullmatch(r"(?:r/)?[A-Za-z0-9_]{2,21}", v) for v in subs):
        raise ValueError("Choose up to 10 valid subreddit names.")
    if data.get("date_range") and data["date_range"] not in DATE_DAYS:
        raise ValueError("Unsupported date range.")
    return data



@bp.route("/meta", methods=["GET"])
@auth_required
def get_meta():
    """
    Returns platform metadata, recommended subreddits, and current AI engine status.
    """
    return jsonify({
        "provider": get_current_provider(),
        "preset_subreddits": [
            "SaaS",
            "startups",
            "Entrepreneur",
            "smallbusiness",
            "webdev",
            "marketing",
            "sales",
            "Productivity",
            "indiehackers",
            "technology",
        ],
        "date_ranges": [
            {"id": "all_time", "label": "All Time (Best Discussions)"},
            {"id": "past_year", "label": "Past Year"},
            {"id": "past_month", "label": "Past Month"},
            {"id": "past_week", "label": "Past Week"},
        ],
        "comment_styles": [
            {"id": key, "title": key.replace("_", " ").title(), "desc": STYLE_DESCRIPTIONS[key]}
            for key in ("user_recommendation", "marketing_pitch")
        ],
    }), 200


@bp.route("/research", methods=["POST"])
@auth_required
def run_research():
    """
    Executes end-to-end Reddit customer discovery:
    1. Product analysis & keyword generation (Gemini)
    2. Multi-query Reddit search & deduplication
    3. Buying intent scoring & relevance evaluation (Gemini)
    4. Comment draft generation (Gemini)
    5. Persistence in MongoDB
    """
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    data = request_data()

    product_name = (data.get("product_name") or "").strip()
    website_url = (data.get("website_url") or "").strip()
    description = (data.get("description") or "").strip()

    if not product_name and not website_url:
        return jsonify({"error": "Please provide a Product Name or Website URL."}), 400

    if not product_name and website_url:
        # Heuristically derive product name from domain
        import urllib.parse
        parsed = urllib.parse.urlparse(website_url if "://" in website_url else f"https://{website_url}")
        host_parts = parsed.netloc.split(".")
        product_name = host_parts[-2].capitalize() if len(host_parts) >= 2 else "My Product"

    target_audience = (data.get("target_audience") or "").strip()
    problems_solved = (data.get("problems_solved") or "").strip()
    target_country = (data.get("target_country") or "").strip()
    subreddits = data.get("subreddits") or []
    date_range = data.get("date_range") or "all_time"

    start_time = time.time()

    # Step 1: Research product & generate keyword groups
    logger.info("Step 1: Researching product %s", product_name)
    product_profile = research_product(
        product_name=product_name,
        website_url=website_url,
        description=description,
        target_audience=target_audience,
        problems_solved=problems_solved,
        target_country=target_country,
        custom_subreddits=subreddits,
    )

    if product_profile.get("brand_name") and (not product_name or product_name == "My Product"):
        product_name = str(product_profile["brand_name"]).strip()

    product_profile["feedback_preferences"] = storage.get_feedback_preferences(user_id, product_name)

    # Step 2: Discover discussions on Reddit
    search_queries = product_profile.get("search_queries", [])
    active_subreddits = subreddits or product_profile.get("recommended_subreddits", [])[:5]
    logger.info("Step 2: Searching Reddit across %d queries", len(search_queries))
    raw_candidates = search_reddit_discussions(
        queries=search_queries,
        subreddits=active_subreddits,
        max_candidates=30,
        date_range=date_range,
    )

    # Step 3: Evaluate and rank posts by buying intent
    logger.info("Step 3: Evaluating %d candidate posts with Gemini", len(raw_candidates))
    evaluated_opportunities = evaluate_posts(
        product_name=product_name,
        product_profile=product_profile,
        candidate_posts=raw_candidates,
        include_irrelevant=True,
    )

    # Preserve mentions even when the post is not a sales opportunity.
    mentions = evaluated_opportunities
    evaluated_opportunities = [o for o in evaluated_opportunities if o.get("is_opportunity", True)]

    # Step 4: Batch generate comment suggestions for top matches
    logger.info("Step 4: Generating personalized comment suggestions")
    enriched_opportunities = batch_generate_comments(
        product_name=product_name,
        product_profile=product_profile,
        posts=evaluated_opportunities,
        max_to_generate=3,
    )

    # Step 5: Compute summary metrics, competitor mentions & brand sentiments
    duration_sec = round(time.time() - start_time, 2)
    high_intent_count = sum(1 for o in enriched_opportunities if o.get("intent_level") == "high")
    medium_intent_count = sum(1 for o in enriched_opportunities if o.get("intent_level") == "medium")
    unique_subreddits = list(set(o.get("subreddit") for o in enriched_opportunities if o.get("subreddit")))

    competitor_mentions = [
        o for o in mentions
        if o.get("is_competitor_mention") or o.get("competitor_name")
    ]
    brand_sentiments = [
        o for o in mentions
        if o.get("is_brand_mention")
    ]

    # Calculate sentiment distribution
    pos_count = sum(1 for b in brand_sentiments if b.get("brand_sentiment") == "Positive")
    mixed_count = sum(1 for b in brand_sentiments if b.get("brand_sentiment") == "Mixed")
    neu_count = sum(1 for b in brand_sentiments if b.get("brand_sentiment") == "Neutral")
    neg_count = sum(1 for b in brand_sentiments if b.get("brand_sentiment") == "Negative")

    sentiment_breakdown = {
        "positive": pos_count,
        "mixed": mixed_count,
        "neutral": neu_count,
        "negative": neg_count,
        "total": pos_count + mixed_count + neu_count + neg_count,
    }

    stats = {
        "candidates_found": len(raw_candidates),
        "verified_opportunities": len(enriched_opportunities),
        "high_intent_count": high_intent_count,
        "medium_intent_count": medium_intent_count,
        "competitor_mentions_count": len(competitor_mentions),
        "brand_mentions_count": len(brand_sentiments),
        "subreddits_scanned_count": len(unique_subreddits),
        "subreddits_scanned": unique_subreddits[:8],
        "duration_seconds": duration_sec,
        "ai_provider": get_current_provider(),
    }

    diagnostics = getattr(raw_candidates, "diagnostics", {})
    warnings = list(product_profile.get("research_warnings", [])) + diagnostics.get("warnings", [])
    if any(o.get("evaluation_method") == "heuristic" for o in mentions):
        warnings.append("AI scoring was unavailable; results use keyword estimates.")
    if any(o.get("draft_error") for o in enriched_opportunities):
        warnings.append("Some replies could not be generated. You can retry them individually.")
    stats["warnings"] = warnings
    stats["source_health"] = diagnostics

    # Step 6: Persist search session in MongoDB
    saved_doc = storage.save_search_session(
        user_id=user_id,
        product_name=product_name,
        website_url=website_url,
        description=description,
        target_audience=target_audience,
        problems_solved=problems_solved,
        subreddits=subreddits,
        date_range=date_range,
        product_profile=product_profile,
        opportunities=enriched_opportunities,
        competitor_mentions=competitor_mentions,
        brand_sentiments=brand_sentiments,
        sentiment_breakdown=sentiment_breakdown,
        stats=stats,
    )

    return jsonify({
        "search_id": saved_doc["search_id"],
        "product_name": product_name,
        "website_url": website_url,
        "product_profile": product_profile,
        "description": description, "target_audience": target_audience, "problems_solved": problems_solved,
        "subreddits": subreddits, "date_range": date_range,
        "opportunities": enriched_opportunities,
        "competitor_mentions": competitor_mentions,
        "brand_sentiments": brand_sentiments,
        "sentiment_breakdown": sentiment_breakdown,
        "stats": stats,
    }), 201


@bp.route("/searches", methods=["GET"])
@auth_required
def list_searches():
    """
    Lists recent search sessions for the user.
    """
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    searches = storage.get_user_searches(user_id=user_id)
    return jsonify({"searches": searches}), 200


@bp.route("/searches/<search_id>", methods=["GET"])
@auth_required
def get_search(search_id: str):
    """
    Retrieves full details of a specific search session.
    """
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    doc = storage.get_search_session(search_id=search_id, user_id=user_id)
    if not doc:
        return jsonify({"error": "Search session not found."}), 404
    return jsonify(doc), 200


@bp.route("/searches/<search_id>", methods=["DELETE"])
@auth_required
def delete_search(search_id: str):
    """
    Deletes a search session.
    """
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    success = storage.delete_search_session(search_id=search_id, user_id=user_id)
    if not success:
        return jsonify({"error": "Search not found or already deleted."}), 404
    return jsonify({"message": "Search session deleted."}), 200


@bp.route("/posts/<post_id>/comment", methods=["POST"])
@auth_required
def generate_comment(post_id: str):
    """
    Generates comment suggestions for a specific post.
    """
    data = request_data()
    product_name = data.get("product_name", "Our Solution")
    product_profile = data.get("product_profile") or {}
    post_data = data.get("post") or {}

    if not isinstance(product_profile, dict) or not isinstance(post_data, dict):
        raise ValueError("Product profile and post must be objects.")
    search_id = data.get("search_id")
    if search_id:
        user = get_current_user()
        user_id = str(user.get("_id") or user.get("id"))
        doc = storage.get_search_session(search_id, user_id)
        if not doc:
            return jsonify({"error": "Search session not found."}), 404
        post_data = next((p for key in ("opportunities", "competitor_mentions", "brand_sentiments") for p in doc.get(key, []) if p.get("post_id") == post_id), None)
        if not post_data:
            return jsonify({"error": "Post not found."}), 404
        product_name, product_profile = doc["product_name"], doc["product_profile"]
    for key in ("customer_pain_points", "target_audience", "competitors_and_alternatives"):
        values = product_profile.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("Product profile lists must contain strings.")
    if any(post_data.get(k) is not None and not isinstance(post_data[k], str) for k in ("title", "selftext", "subreddit", "why_relevant")):
        raise ValueError("Post text fields must be strings.")
    drafts = generate_comment_drafts_for_post(
        product_name=product_name,
        product_profile=product_profile,
        post=post_data,
    )
    if search_id:
        storage.update_post(user_id, search_id, post_id, {"comment_drafts": drafts, "draft_error": None})
    return jsonify({"post_id": post_id, "comment_drafts": drafts}), 200


@bp.route("/posts/<post_id>/save", methods=["POST"])
@auth_required
def toggle_save(post_id: str):
    """
    Toggles bookmark/saved status for an opportunity.
    """
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    data = request_data()
    search_id = data.get("search_id", "")
    post_data = data.get("post_data")
    if post_data is not None and not isinstance(post_data, dict):
        raise ValueError("Post data must be an object.")

    is_saved = storage.toggle_save_post(
        user_id=user_id,
        search_id=search_id,
        post_id=post_id,
        post_data=post_data,
    )
    return jsonify({
        "post_id": post_id,
        "is_saved": is_saved,
        "message": "Opportunity saved to bookmarks." if is_saved else "Opportunity removed from bookmarks.",
    }), 200


@bp.route("/posts/<post_id>/dismiss", methods=["POST"])
@auth_required
def dismiss_opportunity(post_id: str):
    """
    Dismisses an irrelevant opportunity.
    """
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    data = request_data()
    search_id = data.get("search_id", "")

    if not storage.dismiss_post(user_id=user_id, search_id=search_id, post_id=post_id):
        return jsonify({"error": "Post not found."}), 404
    return jsonify({"post_id": post_id, "status": "dismissed"}), 200


@bp.route("/saved", methods=["GET"])
@auth_required
def get_saved():
    """
    Retrieves all bookmarked opportunities across all searches.
    """
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    saved_posts = storage.get_saved_posts(user_id=user_id)
    return jsonify({"saved_posts": saved_posts}), 200


@bp.route("/posts/<post_id>/feedback", methods=["POST"])
@auth_required
def submit_feedback(post_id):
    data = request_data()
    if data.get("vote") not in ("up", "down"):
        raise ValueError("Feedback vote must be up or down.")
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    if not storage.save_feedback(user_id, data.get("search_id", ""), post_id, data["vote"], data.get("reason", "")):
        return jsonify({"error": "Post not found."}), 404
    return jsonify({"post_id": post_id, "vote": data["vote"]}), 200


@bp.route("/posts/<post_id>/engage", methods=["POST"])
@auth_required
def mark_engaged(post_id):
    data = request_data()
    user = get_current_user()
    user_id = str(user.get("_id") or user.get("id"))
    if not storage.update_post(user_id, data.get("search_id", ""), post_id, {"engaged": True}):
        return jsonify({"error": "Post not found."}), 404
    return jsonify({"post_id": post_id, "engaged": True}), 200
