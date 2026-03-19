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
    db.jobs.create_index([('user_id', ASCENDING)])
    db.jobs.create_index([('status', ASCENDING)])
    db.leads.create_index([('job_id', ASCENDING)])
    db.leads.create_index([('user_id', ASCENDING)])
    db.saved_searches.create_index([('user_id', ASCENDING)])
    db.saved_searches.create_index([('created_at', ASCENDING)])
    db.credit_ledger.create_index([('user_id', ASCENDING)])
    db.payments.create_index([('user_id', ASCENDING)])
    db.payments.create_index([('stripe_session_id', ASCENDING)])
