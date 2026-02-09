"""
OTP model for storing and verifying one-time passwords
"""
import random
import string
from datetime import datetime, timedelta
from bson import ObjectId
from app.core.database import get_collection

COLLECTION = 'otps'

OTP_TYPE_EMAIL = 'email'
OTP_TYPE_PHONE = 'phone'

OTP_EXPIRY_MINUTES = 10

def generate_otp(length: int = 6) -> str:
    """Generate a random numeric OTP"""
    return ''.join(random.choices(string.digits, k=length))

def create_otp(user_id: str, otp_type: str, email: str = None, phone: str = None) -> dict:
    """
    Create and store a new OTP
    
    Args:
        user_id: User ID (can be None for registration)
        otp_type: 'email' or 'phone'
        email: Email address (for email OTP)
        phone: Phone number (for phone OTP)
        
    Returns:
        OTP document with code
    """
    coll = get_collection(COLLECTION)
    
    # Invalidate existing OTPs for this user/type
    if user_id:
        coll.update_many(
            {'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id, 'type': otp_type},
            {'$set': {'is_used': True}}
        )
    
    code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    doc = {
        'user_id': ObjectId(user_id) if user_id and isinstance(user_id, str) else user_id,
        'type': otp_type,
        'code': code,
        'email': email,
        'phone': phone,
        'is_used': False,
        'created_at': datetime.utcnow(),
        'expires_at': expires_at
    }
    
    result = coll.insert_one(doc)
    doc['_id'] = result.inserted_id
    
    return doc

def verify_otp(email: str, code: str, otp_type: str = OTP_TYPE_EMAIL) -> bool:
    """
    Verify an OTP code
    
    Args:
        email: Email address used for OTP
        code: OTP code to verify
        otp_type: Type of OTP
        
    Returns:
        True if valid, False otherwise
    """
    coll = get_collection(COLLECTION)
    
    otp = coll.find_one({
        'email': email,
        'type': otp_type,
        'code': code,
        'is_used': False,
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    if otp:
        # Mark as used
        coll.update_one({'_id': otp['_id']}, {'$set': {'is_used': True}})
        return True
    
    return False

def get_pending_otp(email: str, otp_type: str = OTP_TYPE_EMAIL) -> dict:
    """Get the most recent pending OTP for an email"""
    coll = get_collection(COLLECTION)
    
    return coll.find_one({
        'email': email,
        'type': otp_type,
        'is_used': False,
        'expires_at': {'$gt': datetime.utcnow()}
    })

def cleanup_expired_otps():
    """Remove expired OTPs (can be run as a background task)"""
    coll = get_collection(COLLECTION)
    coll.delete_many({'expires_at': {'$lt': datetime.utcnow()}})
