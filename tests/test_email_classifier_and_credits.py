import unittest
from unittest.mock import patch, MagicMock
from bson import ObjectId
from datetime import datetime

from app.core.email_classifier import (
    extract_email_domain,
    is_public_or_disposable_domain,
    is_company_email,
    PUBLIC_EMAIL_DOMAINS
)
from app.projects.lead_gen import credit_requests
from app.projects.lead_gen.credits import model as credits_model, pipeline as credits_pipeline


class TestEmailClassifier(unittest.TestCase):
    """Unit tests for email classification logic"""

    def test_extract_email_domain(self):
        self.assertEqual(extract_email_domain("test@example.com"), "example.com")
        self.assertEqual(extract_email_domain("  User.Name+tag@Company.IO  "), "company.io")
        self.assertEqual(extract_email_domain("admin@sub.domain.co.uk"), "sub.domain.co.uk")
        self.assertIsNone(extract_email_domain(""))
        self.assertIsNone(extract_email_domain(None))
        self.assertIsNone(extract_email_domain("notanemail"))
        self.assertIsNone(extract_email_domain("@nodomain.com"))

    def test_company_emails_detected_correctly(self):
        company_emails = [
            "anoop@surepass.io",
            "sarah@stripe.com",
            "developer@anthropic.com",
            "recruiter@acme-corp.co.uk",
            "founder@ai-startup.ai",
            "team@mybusiness.co.in",
            "engineering@uber.com",
        ]
        for email in company_emails:
            is_company, domain = is_company_email(email)
            self.assertTrue(is_company, f"Failed for {email}: expected company email")
            self.assertIsNotNone(domain)

    def test_public_and_consumer_emails_rejected_as_company(self):
        public_emails = [
            # Google
            "user@gmail.com",
            "user@googlemail.com",
            "user@google.com",
            # Microsoft
            "user@outlook.com",
            "user@hotmail.com",
            "user@live.com",
            "user@msn.com",
            "user@outlook.in",
            # Yahoo & AOL
            "user@yahoo.com",
            "user@yahoo.co.in",
            "user@ymail.com",
            "user@aol.com",
            # Mail.com
            "user@mail.com",
            "user@email.com",
            "user@usa.com",
            # Apple
            "user@icloud.com",
            "user@me.com",
            # Privacy & Others
            "user@proton.me",
            "user@protonmail.com",
            "user@zoho.com",
            "user@gmx.com",
            "user@yandex.com",
            "user@rediffmail.com",
            # Disposable
            "user@tempmail.com",
            "user@guerrillamail.com",
            "user@mailinator.com",
            "user@10minutemail.com",
            "user@trashmail.com",
            "user@yopmail.com",
        ]
        for email in public_emails:
            is_company, domain = is_company_email(email)
            self.assertFalse(is_company, f"Failed for {email}: expected public/consumer email")
            self.assertIsNotNone(domain)

    def test_public_subdomains_handled(self):
        # Subdomains of public providers should still be identified as public
        subdomain_emails = [
            "test@mail.gmail.com",
            "test@sub.yahoo.com",
            "test@corp.mail.com"
        ]
        for email in subdomain_emails:
            is_company, domain = is_company_email(email)
            self.assertFalse(is_company, f"Failed for {email}: expected subdomain of public domain to be public")


class TestCreditAutoApprovalIntegration(unittest.TestCase):
    """Tests for credit request endpoints with company email auto-approval"""

    def setUp(self):
        import app as app_module
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        self.create_indexes_patcher.stop()

    @patch('app.projects.lead_gen.credits.routes.get_current_user')
    @patch('app.projects.lead_gen.credits.routes.pipeline')
    @patch('app.projects.lead_gen.credits.routes.credit_requests')
    def test_company_email_credit_request_auto_approved(self, mock_credit_requests, mock_pipeline, mock_get_user):
        """A user with a company email (@surepass.io) should be auto-approved immediately"""
        user_id = str(ObjectId())
        mock_get_user.return_value = {
            '_id': ObjectId(user_id),
            'email': 'anoop@surepass.io',
            'role': 'user'
        }
        mock_credit_requests.has_pending_request.return_value = False
        mock_credit_requests.has_approved_request.return_value = False
        mock_credit_requests.DEFAULT_CREDIT_AMOUNT = 50
        
        req_doc = {
            '_id': ObjectId(),
            'user_id': ObjectId(user_id),
            'amount': 50,
            'reason': 'First-time credit request',
            'status': 'approved',
            'admin_note': 'Auto-approved for verified company domain: surepass.io',
            'processed_by': 'system_auto_approval',
            'created_at': datetime.utcnow(),
            'processed_at': datetime.utcnow()
        }
        mock_credit_requests.create_auto_approved_request.return_value = req_doc
        mock_credit_requests.to_response.return_value = {
            'id': str(req_doc['_id']),
            'user_id': user_id,
            'user_email': 'anoop@surepass.io',
            'amount': 50,
            'status': 'approved',
            'admin_note': 'Auto-approved for verified company domain: surepass.io'
        }
        mock_pipeline.get_user_balance.return_value = 50

        with patch('app.core.middleware.jwt.decode', return_value={'user_id': user_id}), \
             patch('app.auth.models.find_user_by_id', return_value=mock_get_user.return_value):
            response = self.client.post(
                '/api/lead_gen/credits/request',
                json={'reason': 'Evaluating for team'},
                headers={'Authorization': 'Bearer test-token'}
            )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data['auto_approved'])
        self.assertEqual(data['balance'], 50)
        self.assertIn('surepass.io', data['message'])
        self.assertEqual(data['request']['status'], 'approved')
        
        # Verify ledger was credited
        mock_pipeline.add_credits.assert_called_once()
        mock_credit_requests.create_auto_approved_request.assert_called_once()

    @patch('app.projects.lead_gen.credits.routes.get_current_user')
    @patch('app.projects.lead_gen.credits.routes.pipeline')
    @patch('app.projects.lead_gen.credits.routes.credit_requests')
    def test_public_email_credit_request_queued_as_pending(self, mock_credit_requests, mock_pipeline, mock_get_user):
        """A user with a public email (@gmail.com) should be queued as pending for admin approval"""
        user_id = str(ObjectId())
        mock_get_user.return_value = {
            '_id': ObjectId(user_id),
            'email': 'john.doe@gmail.com',
            'role': 'user'
        }
        mock_credit_requests.has_pending_request.return_value = False
        mock_credit_requests.has_approved_request.return_value = False
        mock_credit_requests.DEFAULT_CREDIT_AMOUNT = 50
        
        req_doc = {
            '_id': ObjectId(),
            'user_id': ObjectId(user_id),
            'amount': 50,
            'reason': 'First-time credit request',
            'status': 'pending',
            'admin_note': None,
            'processed_by': None,
            'created_at': datetime.utcnow(),
            'processed_at': None
        }
        mock_credit_requests.create_request.return_value = req_doc
        mock_credit_requests.to_response.return_value = {
            'id': str(req_doc['_id']),
            'user_id': user_id,
            'user_email': 'john.doe@gmail.com',
            'amount': 50,
            'status': 'pending'
        }

        with patch('app.core.middleware.jwt.decode', return_value={'user_id': user_id}), \
             patch('app.auth.models.find_user_by_id', return_value=mock_get_user.return_value):
            response = self.client.post(
                '/api/lead_gen/credits/request',
                json={'reason': 'Trying out service'},
                headers={'Authorization': 'Bearer test-token'}
            )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertFalse(data['auto_approved'])
        self.assertEqual(data['request']['status'], 'pending')
        self.assertIn('Awaiting admin approval', data['message'])
        
        # Pipeline add_credits should NOT be called for pending requests
        mock_pipeline.add_credits.assert_not_called()
        mock_credit_requests.create_request.assert_called_once()

    @patch('app.projects.lead_gen.credits.routes.get_current_user')
    @patch('app.projects.lead_gen.credits.routes.credit_requests')
    def test_duplicate_free_credit_request_prevented(self, mock_credit_requests, mock_get_user):
        """User who already received approved free credits cannot request again"""
        user_id = str(ObjectId())
        mock_get_user.return_value = {
            '_id': ObjectId(user_id),
            'email': 'user@company.com',
            'role': 'user'
        }
        mock_credit_requests.has_pending_request.return_value = False
        mock_credit_requests.has_approved_request.return_value = True

        with patch('app.core.middleware.jwt.decode', return_value={'user_id': user_id}), \
             patch('app.auth.models.find_user_by_id', return_value=mock_get_user.return_value):
            response = self.client.post(
                '/api/lead_gen/credits/request',
                json={'reason': 'Give me more'},
                headers={'Authorization': 'Bearer test-token'}
            )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn('already received', data['error'].lower())


if __name__ == '__main__':
    unittest.main()
