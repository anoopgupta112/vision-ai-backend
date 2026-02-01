from datetime import datetime
from bson import ObjectId
from app.core.database import get_collection

COLLECTION = 'leads'

def create_doc(job_id, user_id, name, phone=None, email=None, website=None, address=None, source='google_maps'):
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    return {
        'job_id': job_id,
        'user_id': user_id,
        'name': name,
        'phone': phone,
        'email': email,
        'website': website,
        'address': address,
        'source': source,
        'created_at': datetime.utcnow()
    }

def to_response(doc):
    if not doc:
        return None
    return {
        'id': str(doc['_id']),
        'name': doc['name'],
        'phone': doc.get('phone'),
        'email': doc.get('email'),
        'website': doc.get('website'),
        'address': doc.get('address'),
        'source': doc.get('source')
    }

def create(job_id, user_id, name, **kwargs):
    coll = get_collection(COLLECTION)
    doc = create_doc(job_id, user_id, name, **kwargs)
    result = coll.insert_one(doc)
    doc['_id'] = result.inserted_id
    return doc

def find_by_job(job_id, limit=1000, skip=0):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    return list(coll.find({'job_id': job_id}).skip(skip).limit(limit))

def count_by_job(job_id):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    return coll.count_documents({'job_id': job_id})

def delete_by_job(job_id):
    coll = get_collection(COLLECTION)
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    coll.delete_many({'job_id': job_id})
