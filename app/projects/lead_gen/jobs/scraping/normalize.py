import re
from urllib.parse import urlparse, urlunparse

def normalize_url(url):
    if not url:
        return None
    url = url.strip()
    if not url.startswith('http'):
        url = 'http://' + url
    
    try:
        parsed = urlparse(url)
        # remove fragments, keep params maybe? usually valid business site is root
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    except:
        return url

def normalize_phone(phone):
    if not phone:
        return None
    # Remove spacing, parens, hyphens
    # Keep + if present
    cleaned = re.sub(r'[^\d+]', '', phone)
    return cleaned if len(cleaned) > 5 else None
