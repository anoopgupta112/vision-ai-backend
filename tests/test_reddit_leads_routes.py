import unittest
from unittest.mock import MagicMock, patch

import app as app_module

AUTH_HEADERS = {"Authorization": "Bearer valid-token"}


class RedditLeadsRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()

        self.decode_token_patcher = patch("app.core.middleware.decode_token", return_value={"user_id": "user-reddit-1"})
        self.find_user_patcher = patch(
            "app.auth.models.find_user_by_id",
            return_value={"_id": "user-reddit-1", "email": "founder@startup.com", "is_active": True, "is_admin": False},
        )
        self.decode_token_patcher.start()
        self.find_user_patcher.start()

    def tearDown(self):
        self.find_user_patcher.stop()
        self.decode_token_patcher.stop()
        self.create_indexes_patcher.stop()

    def test_meta_returns_presets_and_provider(self):
        response = self.client.get("/api/reddit-leads/meta", headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("provider", data)
        self.assertIn("preset_subreddits", data)
        self.assertIn("comment_styles", data)
        self.assertIn("date_ranges", data)
        self.assertTrue(len(data["preset_subreddits"]) > 0)

    def test_research_requires_name_or_url(self):
        response = self.client.post("/api/reddit-leads/research", json={}, headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    @patch("app.projects.reddit_leads.api.routes.storage.save_search_session")
    @patch("app.projects.reddit_leads.api.routes.batch_generate_comments")
    @patch("app.projects.reddit_leads.api.routes.evaluate_posts")
    @patch("app.projects.reddit_leads.api.routes.search_reddit_discussions")
    @patch("app.projects.reddit_leads.api.routes.research_product")
    def test_research_flow_success(self, mock_research, mock_search, mock_evaluate, mock_batch_comments, mock_save):
        mock_research.return_value = {
            "product_summary": "AI Chatbot for customer support",
            "target_audience": ["SaaS Founders", "Support Leads"],
            "customer_pain_points": ["Slow response times", "High support costs"],
            "buying_intent_phrases": ["looking for chatbot", "alternative to intercom"],
            "competitors_and_alternatives": ["Intercom", "Zendesk"],
            "keywords": ["customer support", "chatbot", "help desk"],
            "negative_keywords": ["crack"],
            "search_queries": ['looking for "customer support chatbot"'],
            "recommended_subreddits": ["SaaS", "startups"],
        }
        mock_search.return_value = [
            {
                "post_id": "test_post_1",
                "title": "Looking for an Intercom alternative that does AI deflection",
                "url": "https://www.reddit.com/r/SaaS/comments/test_post_1/",
                "subreddit": "r/SaaS",
                "author": "u/founder123",
                "created_utc": 1700000000,
                "published_date": "2024-01-01",
                "score": 15,
                "num_comments": 8,
                "selftext": "We are spending $800/mo on Intercom and want an AI-first tool.",
                "is_verified_url": True,
            }
        ]
        mock_evaluate.return_value = [
            {
                "post_id": "test_post_1",
                "title": "Looking for an Intercom alternative that does AI deflection",
                "url": "https://www.reddit.com/r/SaaS/comments/test_post_1/",
                "subreddit": "r/SaaS",
                "author": "u/founder123",
                "created_utc": 1700000000,
                "published_date": "2024-01-01",
                "score": 15,
                "num_comments": 8,
                "selftext": "We are spending $800/mo on Intercom and want an AI-first tool.",
                "is_verified_url": True,
                "relevance_score": 95,
                "intent_level": "high",
                "why_relevant": "Author is actively looking to switch from Intercom due to pricing.",
                "customer_need": "Affordable AI support alternative",
                "status": "active",
            }
        ]
        mock_batch_comments.return_value = [
            {
                "post_id": "test_post_1",
                "title": "Looking for an Intercom alternative that does AI deflection",
                "url": "https://www.reddit.com/r/SaaS/comments/test_post_1/",
                "subreddit": "r/SaaS",
                "author": "u/founder123",
                "created_utc": 1700000000,
                "published_date": "2024-01-01",
                "score": 15,
                "num_comments": 8,
                "selftext": "We are spending $800/mo on Intercom and want an AI-first tool.",
                "is_verified_url": True,
                "relevance_score": 95,
                "intent_level": "high",
                "why_relevant": "Author is actively looking to switch from Intercom due to pricing.",
                "customer_need": "Affordable AI support alternative",
                "status": "active",
                "comment_drafts": {
                    "helpful": "If you're paying $800/mo, look at separating live chat from deflection...",
                    "technical": "You can connect your docs to a RAG pipeline...",
                    "recommendation": "Check out our tool SupportAI, it handles this at 1/5th the cost.",
                    "subtle": "Ran into the exact same pricing shock recently...",
                },
            }
        ]

        mock_save.return_value = {"search_id": "test_search_id_123"}

        payload = {
            "product_name": "SupportAI",
            "website_url": "https://supportai.example.com",
            "description": "AI customer support bot reducing tickets by 70%",
            "subreddits": ["SaaS"],
        }
        response = self.client.post("/api/reddit-leads/research", json=payload, headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("search_id", data)
        self.assertEqual(data["product_name"], "SupportAI")
        self.assertEqual(len(data["opportunities"]), 1)
        self.assertEqual(data["opportunities"][0]["relevance_score"], 95)
        self.assertEqual(data["stats"]["high_intent_count"], 1)

    @patch("app.projects.reddit_leads.models.storage.get_user_searches")
    def test_list_searches(self, mock_get_searches):
        mock_get_searches.return_value = [
            {"search_id": "s1", "product_name": "Product A", "opportunities_count": 5}
        ]
        response = self.client.get("/api/reddit-leads/searches", headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["searches"]), 1)

    @patch("app.projects.reddit_leads.models.storage.get_search_session")
    def test_get_search_details(self, mock_get_session):
        mock_get_session.return_value = {
            "search_id": "s1",
            "product_name": "Product A",
            "opportunities": [],
            "stats": {},
        }
        response = self.client.get("/api/reddit-leads/searches/s1", headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["search_id"], "s1")

    @patch("app.projects.reddit_leads.models.storage.toggle_save_post")
    def test_toggle_save(self, mock_toggle):
        mock_toggle.return_value = True
        response = self.client.post(
            "/api/reddit-leads/posts/p123/save",
            json={"search_id": "s1"},
            headers=AUTH_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["is_saved"])

    @patch("app.projects.reddit_leads.models.storage.dismiss_post")
    def test_dismiss_post(self, mock_dismiss):
        mock_dismiss.return_value = True
        response = self.client.post(
            "/api/reddit-leads/posts/p123/dismiss",
            json={"search_id": "s1"},
            headers=AUTH_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "dismissed")

    @patch("app.projects.reddit_leads.models.storage.get_saved_posts")
    def test_get_saved_posts(self, mock_saved):
        mock_saved.return_value = [{"post_id": "p1", "title": "Saved Discussion"}]
        response = self.client.get("/api/reddit-leads/saved", headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["saved_posts"]), 1)


if __name__ == "__main__":
    unittest.main()
