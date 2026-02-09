from datetime import datetime
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from app.core.database import get_collection

COLLECTION = 'users'

def create_user_doc(email, password_hash, phone=None):
    return {
        'email': email,
        'phone': phone,
        'password_hash': password_hash,
        'email_verified': False,
        'phone_verified': False,
        'is_admin': False,
        'is_active': True,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }

def to_response(user_doc):
    if not user_doc:
        return None
    return {
        'id': str(user_doc['_id']),
        'email': user_doc['email'],
        'phone': user_doc.get('phone'),
        'email_verified': user_doc.get('email_verified', False),
        'phone_verified': user_doc.get('phone_verified', False),
        'is_admin': user_doc.get('is_admin', False),
        'is_active': user_doc.get('is_active', True),
        'created_at': user_doc['created_at'].isoformat() if user_doc.get('created_at') else None
    }

def create_user(email, password, phone=None):
    users = get_collection(COLLECTION)
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    user_doc = create_user_doc(email, password_hash, phone)
    result = users.insert_one(user_doc)
    user_doc['_id'] = result.inserted_id
    return user_doc

def find_user_by_email(email):
    users = get_collection(COLLECTION)
    return users.find_one({'email': email})

def find_user_by_id(user_id):
    users = get_collection(COLLECTION)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    return users.find_one({'_id': user_id})

def verify_password(user_doc, password):
    if not user_doc:
        return False
    return check_password_hash(user_doc['password_hash'], password)

def update_user(user_id, update_fields):
    users = get_collection(COLLECTION)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    update_fields['updated_at'] = datetime.utcnow()
    users.update_one({'_id': user_id}, {'$set': update_fields})

def delete_user(user_id):
    users = get_collection(COLLECTION)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    users.delete_one({'_id': user_id})

def list_users(limit=100, skip=0):
    users = get_collection(COLLECTION)
    return list(users.find().sort('created_at', -1).skip(skip).limit(limit))

def count_users():
    users = get_collection(COLLECTION)
    return users.count_documents({})

def create_user_from_pending(email, password_hash, phone=None, email_verified=True):
    """
    Create a user from pending registration data.
    Used after email verification to create the actual user.
    The password is already hashed.
    """
    users = get_collection(COLLECTION)
    user_doc = {
        'email': email,
        'phone': phone,
        'password_hash': password_hash,
        'email_verified': email_verified,
        'phone_verified': False,
        'is_admin': False,
        'is_active': True,
        'credits': 100,  # Free credits for new users
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    result = users.insert_one(user_doc)
    user_doc['_id'] = result.inserted_id
    return user_doc

