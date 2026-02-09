"""
Payment transaction model for storing payment history
"""
from datetime import datetime
from bson import ObjectId
from app.core.database import get_collection

COLLECTION = 'payment_transactions'

STATUS_PENDING = 'pending'
STATUS_SUCCESS = 'success'
STATUS_FAILED = 'failed'

def create_transaction(user_id: str, order_id: str, package_id: str, 
                       amount: int, credits: int):
    """
    Create a new payment transaction record
    
    Args:
        user_id: ID of the user
        order_id: Razorpay order ID
        package_id: Credit package ID
        amount: Amount in paise
        credits: Number of credits to be added
        
    Returns:
        Created transaction document
    """
    coll = get_collection(COLLECTION)
    
    doc = {
        'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
        'razorpay_order_id': order_id,
        'razorpay_payment_id': None,
        'package_id': package_id,
        'amount': amount,
        'currency': 'INR',
        'credits': credits,
        'status': STATUS_PENDING,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    result = coll.insert_one(doc)
    doc['_id'] = result.inserted_id
    return doc

def update_transaction_success(order_id: str, payment_id: str):
    """
    Mark a transaction as successful
    
    Args:
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        
    Returns:
        Updated transaction document
    """
    coll = get_collection(COLLECTION)
    
    result = coll.find_one_and_update(
        {'razorpay_order_id': order_id},
        {
            '$set': {
                'razorpay_payment_id': payment_id,
                'status': STATUS_SUCCESS,
                'updated_at': datetime.utcnow()
            }
        },
        return_document=True
    )
    return result

def update_transaction_failed(order_id: str, error: str = None):
    """Mark a transaction as failed"""
    coll = get_collection(COLLECTION)
    
    update_data = {
        'status': STATUS_FAILED,
        'updated_at': datetime.utcnow()
    }
    if error:
        update_data['error'] = error
    
    result = coll.find_one_and_update(
        {'razorpay_order_id': order_id},
        {'$set': update_data},
        return_document=True
    )
    return result

def get_transaction_by_order_id(order_id: str):
    """Get transaction by Razorpay order ID"""
    coll = get_collection(COLLECTION)
    return coll.find_one({'razorpay_order_id': order_id})

def get_user_transactions(user_id: str, limit: int = 50):
    """Get payment history for a user"""
    coll = get_collection(COLLECTION)
    
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    
    return list(coll.find(
        {'user_id': user_id}
    ).sort('created_at', -1).limit(limit))

def to_response(doc):
    """Convert transaction document to API response"""
    if not doc:
        return None
    
    return {
        'id': str(doc['_id']),
        'order_id': doc['razorpay_order_id'],
        'payment_id': doc.get('razorpay_payment_id'),
        'package_id': doc['package_id'],
        'amount': doc['amount'],
        'display_amount': f"₹{doc['amount'] // 100}",
        'credits': doc['credits'],
        'status': doc['status'],
        'created_at': doc['created_at'].isoformat() if doc.get('created_at') else None
    }
