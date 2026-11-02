from pymongo import MongoClient, ASCENDING
from app.core.config import Config

_client = None
_db = None

def get_client():
    global _client
    if _client is None:
        _client = MongoClient(
            Config.MONGODB_URI,
            maxPoolSize=50,
            minPoolSize=5,
            maxIdleTimeMS=30000,
            serverSelectionTimeoutMS=5000
        )
    return _client

def get_database():
    global _db
    if _db is None:
        client = get_client()
        _db = client[Config.MONGODB_DATABASE]
    return _db

def get_collection(name):
    db = get_database()
    return db[name]

def create_indexes():
    db = get_database()
    db.users.create_index([('email', ASCENDING)], unique=True)
    db.lead_jobs.create_index([('user_id', ASCENDING)])
    db.lead_jobs.create_index([('status', ASCENDING)])
    db.lead_leads.create_index([('job_id', ASCENDING)])
    db.lead_leads.create_index([('user_id', ASCENDING)])
    db.lead_saved_searches.create_index([('user_id', ASCENDING)])
    db.lead_saved_searches.create_index([('created_at', ASCENDING)])
    db.lead_credit_ledger.create_index([('user_id', ASCENDING)])
    db.lead_credit_requests.create_index([('user_id', ASCENDING)])
    db.lead_credit_requests.create_index([('status', ASCENDING)])
    db.lead_payment_transactions.create_index([('user_id', ASCENDING)])
    db.lead_payment_transactions.create_index([('razorpay_order_id', ASCENDING)])
    db.hr_forms.create_index([('user_id', ASCENDING)])
    db.hr_forms.create_index([('updated_at', ASCENDING)])
    db.hr_submissions.create_index([('form_id', ASCENDING)])
    db.hr_submissions.create_index([('created_at', ASCENDING)])
    db.reddit_searches.create_index([('user_id', ASCENDING)])
    db.reddit_searches.create_index([('created_at', ASCENDING)])
    db.reddit_saved_posts.create_index([('user_id', ASCENDING)])
    db.vip_customers.create_index([('user_id', ASCENDING)])
    db.vip_customers.create_index([('shop_id', ASCENDING)])
    db.vip_visits.create_index([('customer_id', ASCENDING)])
    db.vip_visits.create_index([('created_at', ASCENDING)])
    db.vip_visits.create_index([('user_id', ASCENDING)])
    db.reddit_saved_posts.create_index([('post_id', ASCENDING)])
