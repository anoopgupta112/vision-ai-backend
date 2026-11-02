import html
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from app.projects.reddit_leads.services.ai_client import complete_json
from .safe_fetch import fetch_public_text, UnsafeURL

logger = logging.getLogger(__name__)


def extract_playstore_metadata(url: str, timeout: int = 8) -> Dict[str, Any]:
    """
    Extracts rich application metadata from a Google Play Store URL.
    Extracts App Title, Developer, Category, Rating, and feature description.
    """
    parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    qs = urllib.parse.parse_qs(parsed.query)
    package_id = qs.get("id", [""])[0]

    try:
        raw = fetch_public_text(url, timeout=timeout, max_bytes=3_500_000)
    except UnsafeURL:
        raise
    except Exception:
        logger.warning("Product store metadata could not be retrieved")
        return {"is_mobile_app": True, "platform": "Android (Google Play)",
                "app_name": "", "package_id": package_id, "rating": "",
                "short_description": "", "full_description": ""}

    # Extract App Title
    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE)
    raw_title = title_m.group(1).strip() if title_m else ""
    # Strip "- Apps on Google Play"
    clean_title = html.unescape(re.sub(r"\s*-\s*Apps on Google Play.*$", "", raw_title, flags=re.IGNORECASE).strip())

    # Extract Short/Meta Description
    desc_m = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        raw,
        re.IGNORECASE,
    )
    meta_desc = html.unescape(desc_m.group(1).strip()) if desc_m else ""

    # Extract Full App Description from data-g-id='description' or itemprop='description'
    full_desc_m = re.search(r'data-g-id=["\']description["\'][^>]*>(.*?)</div>', raw, re.DOTALL)
    if not full_desc_m:
        full_desc_m = re.search(r'itemprop=["\']description["\'][^>]*>(.*?)</div>', raw, re.DOTALL)
    full_desc = re.sub(r"<[^>]+>", " ", full_desc_m.group(1)) if full_desc_m else ""
    clean_full_desc = " ".join(full_desc.split())[:2000]

    # Extract Star Rating
    rating_m = re.search(r'aria-label=["\']Rated ([\d\.]+) stars', raw)
    rating = rating_m.group(1) if rating_m else ""

    # Extract Genre / Category
    genre_m = re.search(r'itemprop=["\']genre["\'][^>]*>([^<]+)<', raw)
    genre = genre_m.group(1).strip() if genre_m else ""

    return {
        "is_mobile_app": True,
        "platform": "Android (Google Play)",
        "app_name": clean_title or (package_id.split(".")[-1].capitalize() if package_id else "Android App"),
        "package_id": package_id,
        "rating": rating,
        "category": genre,
        "short_description": meta_desc,
        "full_description": clean_full_desc,
    }


def extract_appstore_metadata(url: str, timeout: int = 8) -> Dict[str, Any]:
    """
    Extracts app metadata from an Apple App Store URL.
    """
    try:
        raw = fetch_public_text(url, timeout=timeout)
    except UnsafeURL:
        raise
    except Exception:
        logger.warning("Product store metadata could not be retrieved")
        return {"is_mobile_app": True, "platform": "iOS (Apple App Store)",
                "app_name": "", "rating": "", "short_description": "", "full_description": ""}

    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE)
    raw_title = title_m.group(1).strip() if title_m else ""
    clean_title = re.sub(r"\s*on the App\s*Store.*$", "", raw_title, flags=re.IGNORECASE).strip()

    desc_m = re.search(
        r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']*)["\']',
        raw,
        re.IGNORECASE,
    )
    meta_desc = desc_m.group(1).strip() if desc_m else ""

    return {
        "is_mobile_app": True,
        "platform": "iOS (Apple App Store)",
        "app_name": clean_title or "iOS App",
        "rating": "",
        "category": "Mobile Application",
        "short_description": meta_desc,
        "full_description": meta_desc,
    }


def extract_website_text(url: str, timeout: int = 6) -> tuple:
    """
    Safely retrieves page title and readable content from a product website URL.
    """
    if not url:
        return "", ""

    try:
        html = fetch_public_text(url, timeout=timeout)

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Extract meta description
        desc_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        meta_desc = desc_match.group(1).strip() if desc_match else ""

        # Clean body text
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<[^>]+>", " ", body)
        clean_text = " ".join(body.split())

        preview = f"Title: {title}\nDescription: {meta_desc}\nContent Excerpt: {clean_text[:1800]}"
        return preview.strip(), title
    except UnsafeURL:
        raise
    except Exception as exc:
        logger.info("Could not fetch product website %s: %s", url, exc)
        return "", ""


def research_product(
    product_name: str,
    website_url: Optional[str] = None,
    description: Optional[str] = None,
    target_audience: Optional[str] = None,
    problems_solved: Optional[str] = None,
    target_country: Optional[str] = None,
    custom_subreddits: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Analyzes the product details using Gemini to produce high-signal keywords,
    customer pain points, competitor alternatives, search queries, and subreddits.
    Supports Google Play Store URLs, Apple App Store URLs, and SaaS/web URLs.
    """
    website_content = ""
    website_title = ""
    app_meta = None
    is_playstore = False
    is_appstore = False

    if website_url:
        lowered_url = website_url.lower()
        if "play.google.com/store/apps" in lowered_url:
            is_playstore = True
            app_meta = extract_playstore_metadata(website_url)
            website_title = app_meta.get("app_name", "")
            website_content = (
                f"Platform: Google Play Store (Android)\n"
                f"App Title: {app_meta.get('app_name')}\n"
                f"Package ID: {app_meta.get('package_id')}\n"
                f"Rating: {app_meta.get('rating')}\n"
                f"Category: {app_meta.get('category')}\n"
                f"Tagline: {app_meta.get('short_description')}\n"
                f"Features & Full Description:\n{app_meta.get('full_description')}"
            )
        elif "apps.apple.com" in lowered_url:
            is_appstore = True
            app_meta = extract_appstore_metadata(website_url)
            website_title = app_meta.get("app_name", "")
            website_content = (
                f"Platform: Apple App Store (iOS)\n"
                f"App Title: {app_meta.get('app_name')}\n"
                f"Rating: {app_meta.get('rating')}\n"
                f"Category: {app_meta.get('category')}\n"
                f"Description:\n{app_meta.get('full_description')}"
            )
        else:
            website_content, website_title = extract_website_text(website_url)

    # If product_name was empty or placeholder, derive from title
    clean_title_brand = ""
    if website_title:
        # e.g. "TickTick:To Do List & Calendar" -> "TickTick"
        clean_title_brand = re.split(r"[-|:•]", website_title)[0].strip()

    resolved_product_name = (clean_title_brand if product_name == "My Product" else product_name) or clean_title_brand or "My Product"

    mobile_instructions = ""
    if is_playstore:
        mobile_instructions = """
NOTE: THIS IS A GOOGLE PLAY STORE ANDROID APPLICATION.
1. The brand_name MUST be the concise app name (e.g. 'TickTick' or 'Spotify').
2. Recommend mobile subreddits: r/androidapps, r/Android, r/googleplay, r/apps, plus niche subreddits for this app's category.
3. Ensure search_queries include app recommendation requests (e.g., 'best android app for...', 'looking for an app that...', 'alternative to [competitor app]', 'what app do you use for...').
4. Identify real mobile competitor apps in this category.
"""
    elif is_appstore:
        mobile_instructions = """
NOTE: THIS IS AN APPLE APP STORE IOS APPLICATION.
1. Recommend iOS subreddits: r/iosapps, r/apple, r/iPhone, r/apps, plus category subreddits.
2. Include mobile app queries (e.g., 'best iOS app for...', 'looking for an iPhone app that...').
"""

    prompt = f"""
You are an expert SaaS & Mobile App growth strategist, Reddit marketing specialist, and social listening expert.
Analyze the following product information and generate comprehensive customer discovery keywords, pain points, competitor alternatives, brand mention queries, and Reddit search operators.

PRODUCT DETAILS:
- Product Name: {resolved_product_name}
- Product Website/Store URL: {website_url or 'N/A'}
- Product Description: {description or 'N/A'}
- Stated Target Audience: {target_audience or 'N/A'}
- Problems Solved: {problems_solved or 'N/A'}
- Target Country / Language: {target_country or 'Global (English)'}
- Scraped Store/Website Information:
{website_content or 'None available'}
{mobile_instructions}

TASK:
Return a JSON object with this exact structure:
{{
  "brand_name": "{resolved_product_name}",
  "product_summary": "A concise 2-sentence summary of what this product does and its core value proposition.",
  "target_audience": ["Persona 1", "Persona 2", "Persona 3"],
  "customer_pain_points": [
    "Pain point 1 that drives someone to seek this product",
    "Pain point 2",
    "Pain point 3",
    "Pain point 4"
  ],
  "buying_intent_phrases": [
    "looking for a tool/app that...",
    "recommend me an app for...",
    "need help with...",
    "best software/app for..."
  ],
  "competitors_and_alternatives": [
    "Competitor 1",
    "Competitor 2",
    "Competitor 3",
    "Competitor 4"
  ],
  "keywords": [
    "primary keyword 1",
    "keyword 2",
    "keyword 3",
    "keyword 4",
    "keyword 5",
    "keyword 6",
    "keyword 7",
    "keyword 8"
  ],
  "negative_keywords": [
    "free download",
    "crack",
    "jobs",
    "hiring"
  ],
  "search_queries": [
    "looking for {resolved_product_name or 'app'}",
    "alternative to competitor",
    "recommend app/tool for pain point",
    "best app for target audience",
    "switch from competitor"
  ],
  "recommended_subreddits": [
    "SaaS",
    "startups",
    "androidapps",
    "Productivity",
    "webdev"
  ]
}}

Ensure search_queries are high-intent phrases that real people post on Reddit when looking for solutions.
Respond ONLY with a valid JSON object.
"""

    research_warnings = []
    try:
        profile = complete_json(prompt, temperature=0.2)
    except Exception as exc:
        logger.warning("AI product research failed: %s. Using heuristic fallback.", exc)
        research_warnings.append("AI product analysis is unavailable; search uses the details you supplied.")
        # Use user-supplied facts without inventing competitors or product capabilities.
        profile = {
            "brand_name": resolved_product_name,
            "product_summary": description or f"Product: {resolved_product_name}. Add a description to improve relevance.",
            "target_audience": [target_audience] if target_audience else ["Founders", "Users", "Professionals"],
            "customer_pain_points": [problems_solved] if problems_solved else ["Manual workflows", "High costs", "Time-consuming processes"],
            "buying_intent_phrases": ["looking for", "recommend a tool", "alternative to", "need recommendations"],
            "competitors_and_alternatives": [],
            "keywords": [resolved_product_name.lower(), "software", "tool", "app", "automation"],
            "negative_keywords": ["crack", "pirated", "homework"],
            "search_queries": [
                f'looking for "{resolved_product_name}"',
                "recommend app",
                "how to solve",
                "alternative to",
            ],
            "recommended_subreddits": ["androidapps", "Productivity", "SaaS", "startups", "webdev"] if is_playstore else ["SaaS", "startups", "Entrepreneur", "smallbusiness", "webdev"],
        }

    for key in ["target_audience", "customer_pain_points", "buying_intent_phrases", "competitors_and_alternatives", "keywords", "negative_keywords", "search_queries", "recommended_subreddits"]:
        values = profile.get(key)
        profile[key] = [v.strip()[:200] for v in values if isinstance(v, str) and v.strip()][:20] if isinstance(values, list) else []
    if not profile["search_queries"]:
        profile["search_queries"] = [resolved_product_name]
    profile["research_warnings"] = research_warnings
    profile["analysis_method"] = "user_details" if research_warnings else "ai"

    # Attach mobile metadata to profile
    if app_meta:
        profile["is_mobile_app"] = True
        profile["platform"] = app_meta.get("platform", "Mobile App")
        profile["rating"] = app_meta.get("rating", "")
        profile["category"] = app_meta.get("category", "")
        profile["package_id"] = app_meta.get("package_id", "")
    else:
        profile["is_mobile_app"] = False
        profile["platform"] = "Web / SaaS"
        profile["rating"] = ""
        profile["category"] = "Web Application"

    # Merge custom user subreddits if provided
    if custom_subreddits:
        clean_subs = [s.strip().replace("r/", "").replace("/", "") for s in custom_subreddits if s.strip()]
        existing = profile.get("recommended_subreddits", [])
        profile["recommended_subreddits"] = list(dict.fromkeys(clean_subs + existing))

    return profile
