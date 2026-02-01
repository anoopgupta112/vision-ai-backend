from datetime import datetime
from bson import ObjectId
from app.core.database import get_collection

COLLECTION = 'credit_ledger'
PRODUCT_ID = 'lead_gen'

REASON_PURCHASE = 'purchase'
REASON_USAGE = 'usage'
REASON_ADMIN = 'admin'
REASON_REFUND = 'refund'

def create_doc(user_id, delta, reason, note=None, job_id=None):
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    if job_id and isinstance(job_id, str):
        job_id = ObjectId(job_id)
    return {
        'user_id': user_id,
        'product_id': PRODUCT_ID,
        'job_id': job_id,
        'delta': delta,
        'reason': reason,
        'note': note,
        'created_at': datetime.utcnow()
    }

def to_response(doc):
    if not doc:
        return None
    return {
        'id': str(doc['_id']),
        'delta': doc['delta'],
        'reason': doc['reason'],
        'note': doc.get('note'),
        'created_at': doc['created_at'].isoformat() if doc.get('created_at') else None
    }

def create(user_id, delta, reason, note=None, job_id=None):
    coll = get_collection(COLLECTION)
    doc = create_doc(user_id, delta, reason, note, job_id)
    result = coll.insert_one(doc)
    doc['_id'] = result.inserted_id
    return doc

def get_balance(user_id):
    coll = get_collection(COLLECTION)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    pipe = [
        {'$match': {'user_id': user_id, 'product_id': PRODUCT_ID}},
        {'$group': {'_id': None, 'total': {'$sum': '$delta'}}}
    ]
    result = list(coll.aggregate(pipe))
    return result[0]['total'] if result else 0

def get_history(user_id, limit=50, skip=0):
    coll = get_collection(COLLECTION)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    return list(coll.find({
        'user_id': user_id, 
        'product_id': PRODUCT_ID
    }).sort('created_at', -1).skip(skip).limit(limit))

def add(user_id, amount, reason=REASON_ADMIN, note=None):
    return create(user_id, amount, reason, note)

def deduct(user_id, amount, job_id=None):
    return create(user_id, -abs(amount), REASON_USAGE, job_id=job_id)
