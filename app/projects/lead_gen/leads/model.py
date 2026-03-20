from datetime import datetime
from bson import ObjectId
from urllib.parse import urlparse
from app.core.database import get_collection

COLLECTION = 'lead_leads'


def _normalize_website_url(website):
    if not website:
        return None

    candidate = website.strip()
    if not candidate:
        return None

    if '://' not in candidate:
        candidate = f'https://{candidate}'

    parsed = urlparse(candidate)
    if not parsed.netloc:
        return None

    path = parsed.path or ''
    if parsed.params:
        path = f'{path};{parsed.params}'

    normalized = f'{parsed.scheme}://{parsed.netloc}{path}'
    if parsed.query:
        normalized = f'{normalized}?{parsed.query}'
    return normalized


def _website_domain(website_url):
    if not website_url:
        return None
    return urlparse(website_url).netloc or None


def _website_actions(website_url):
    can_use_website = bool(website_url)
    return {
        'can_open': can_use_website,
        'can_preview': can_use_website,
        'open_url': website_url,
        'preview_url': website_url,
    }

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
    website_url = _normalize_website_url(doc.get('website'))
    return {
        'id': str(doc['_id']),
        'name': doc['name'],
        'phone': doc.get('phone'),
        'email': doc.get('email'),
        'website': doc.get('website'),
        'website_url': website_url,
        'website_domain': _website_domain(website_url),
        'website_actions': _website_actions(website_url),
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
