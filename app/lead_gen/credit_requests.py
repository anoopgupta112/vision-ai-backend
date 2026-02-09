"""
Credit request model for storing and managing credit requests
"""
from datetime import datetime
from bson import ObjectId
from app.core.database import get_collection

COLLECTION = 'credit_requests'

STATUS_PENDING = 'pending'
STATUS_APPROVED = 'approved'
STATUS_REJECTED = 'rejected'

DEFAULT_CREDIT_AMOUNT = 50

def create_request(user_id: str, amount: int = DEFAULT_CREDIT_AMOUNT, reason: str = None) -> dict:
    """
    Create a new credit request
    
    Args:
        user_id: ID of the user requesting credits
        amount: Number of credits requested
        reason: Optional reason for the request
        
    Returns:
        Created request document
    """
    coll = get_collection(COLLECTION)
    
    # Check if user already has a pending request
    existing = coll.find_one({
        'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
        'status': STATUS_PENDING
    })
    
    if existing:
        return None  # Already has pending request
    
    doc = {
        'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
        'amount': amount,
        'reason': reason,
        'status': STATUS_PENDING,
        'admin_note': None,
        'processed_by': None,
        'created_at': datetime.utcnow(),
        'processed_at': None
    }
    
    result = coll.insert_one(doc)
    doc['_id'] = result.inserted_id
    return doc

def get_pending_requests(limit: int = 100, skip: int = 0) -> list:
    """Get all pending credit requests"""
    coll = get_collection(COLLECTION)
    return list(coll.find({'status': STATUS_PENDING}).sort('created_at', -1).skip(skip).limit(limit))

def get_user_requests(user_id: str, limit: int = 10) -> list:
    """Get credit requests for a specific user"""
    coll = get_collection(COLLECTION)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    return list(coll.find({'user_id': user_id}).sort('created_at', -1).limit(limit))

def get_request_by_id(request_id: str) -> dict:
    """Get a credit request by ID"""
    coll = get_collection(COLLECTION)
    if isinstance(request_id, str):
        request_id = ObjectId(request_id)
    return coll.find_one({'_id': request_id})

def approve_request(request_id: str, admin_id: str, admin_note: str = None) -> dict:
    """Approve a credit request"""
    coll = get_collection(COLLECTION)
    if isinstance(request_id, str):
        request_id = ObjectId(request_id)
    if isinstance(admin_id, str):
        admin_id = ObjectId(admin_id)
    
    result = coll.find_one_and_update(
        {'_id': request_id, 'status': STATUS_PENDING},
        {
            '$set': {
                'status': STATUS_APPROVED,
                'admin_note': admin_note,
                'processed_by': admin_id,
                'processed_at': datetime.utcnow()
            }
        },
        return_document=True
    )
    return result

def reject_request(request_id: str, admin_id: str, admin_note: str = None) -> dict:
    """Reject a credit request"""
    coll = get_collection(COLLECTION)
    if isinstance(request_id, str):
        request_id = ObjectId(request_id)
    if isinstance(admin_id, str):
        admin_id = ObjectId(admin_id)
    
    result = coll.find_one_and_update(
        {'_id': request_id, 'status': STATUS_PENDING},
        {
            '$set': {
                'status': STATUS_REJECTED,
                'admin_note': admin_note,
                'processed_by': admin_id,
                'processed_at': datetime.utcnow()
            }
        },
        return_document=True
    )
    return result

def count_pending() -> int:
    """Count pending credit requests"""
    coll = get_collection(COLLECTION)
    return coll.count_documents({'status': STATUS_PENDING})

def to_response(doc, user_email: str = None) -> dict:
    """Convert request document to API response"""
    if not doc:
        return None
    
    return {
        'id': str(doc['_id']),
        'user_id': str(doc['user_id']),
        'user_email': user_email,
        'amount': doc['amount'],
        'reason': doc.get('reason'),
        'status': doc['status'],
        'admin_note': doc.get('admin_note'),
        'created_at': doc['created_at'].isoformat() if doc.get('created_at') else None,
        'processed_at': doc['processed_at'].isoformat() if doc.get('processed_at') else None
    }
