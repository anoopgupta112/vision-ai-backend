EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

IGNORE_EMAILS = {
    'example@', 'test@', 'noreply@', 'no-reply@', 'info@domain.com', 
    'admin@domain.com', 'email@email.com', 'yourname@', 'username@'
}

# Google Maps Selectors (Subject to change as Google updates UI)
SELECTOR_RESULT_ITEM = 'div[role="feed"] > div > div[jsaction]'
SELECTOR_NAME = 'h1.DUwDvf'
SELECTOR_DETAILS_CONTAINER = 'div[role="main"]'

CONTACT_KEYWORDS = ['contact', 'about', 'get in touch', 'reach us', 'support']
