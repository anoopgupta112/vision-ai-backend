import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
    MONGODB_DATABASE = os.environ.get('MONGODB_DATABASE', 'platform_db')
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
    RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
    MAX_LEADS_PER_JOB = int(os.environ.get('MAX_LEADS_PER_JOB', 500))
    JWT_EXPIRY_HOURS = int(os.environ.get('JWT_EXPIRY_HOURS', 24))
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
