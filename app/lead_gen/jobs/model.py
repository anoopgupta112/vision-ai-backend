from datetime import datetime
from bson import ObjectId
from app.core.database import get_collection

COLLECTION = 'jobs'
PRODUCT_ID = 'lead_gen'

STATUS_QUEUED = 'queued'
STATUS_RUNNING = 'running'
STATUS_DONE = 'done'
STATUS_FAILED = 'failed'

def create_doc(user_id, query_text, leads_requested):
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    return {
        'user_id': user_id,
        'product_id': PRODUCT_ID,
        'query_text': query_text,
        'leads_requested': leads_requested,
        'leads_delivered': 0,
        'status': STATUS_QUEUED,
        'error_message': None,
        'created_at': datetime.utcnow(),
        'started_at': None,
        'finished_at': None
    }

def to_response(doc):
    if not doc:
        return None
    return {
        'id': str(doc['_id']),
        'query_text': doc['query_text'],
        'leads_requested': doc['leads_requested'],
        'leads_delivered': doc['leads_delivered'],
        'status': doc['status'],
        'error_message': doc.get('error_message'),
        'created_at': doc['created_at'].isoformat() if doc.get('created_at') else None,
        'finished_at': doc['finished_at'].isoformat() if doc.get('finished_at') else None
    }

def create(user_id, query_text, leads_requested):
    coll = get_collection(COLLECTION)
    doc = create_doc(user_id, query_text, leads_requested)
    result = coll.insert_one(doc)
    doc['_id'] = result.inserted_id
    return doc

def find_by_id(job_id):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    return coll.find_one({'_id': job_id})

def find_by_user(user_id, limit=50, skip=0):
    coll = get_collection(COLLECTION)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    return list(coll.find({
        'user_id': user_id, 
        'product_id': PRODUCT_ID
    }).sort('created_at', -1).skip(skip).limit(limit))

def update_status(job_id, status, error_message=None):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    update = {'status': status}
    if status == STATUS_RUNNING:
        update['started_at'] = datetime.utcnow()
    elif status in [STATUS_DONE, STATUS_FAILED]:
        update['finished_at'] = datetime.utcnow()
    if error_message:
        update['error_message'] = error_message
    coll.update_one({'_id': job_id}, {'$set': update})

def update_progress(job_id, leads_delivered):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    coll.update_one({'_id': job_id}, {'$set': {'leads_delivered': leads_delivered}})

def reset_for_retry(job_id):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    coll.update_one(
        {'_id': job_id},
        {
            '$set': {
                'status': STATUS_QUEUED,
                'leads_delivered': 0,
                'error_message': None,
                'started_at': None,
                'finished_at': None,
            }
        },
    )

def delete(job_id):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    coll.delete_one({'_id': job_id})
