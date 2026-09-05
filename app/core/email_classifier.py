"""
Email classification module to differentiate company/business emails from public, consumer, and disposable email domains.
"""
import re
from typing import Tuple, Optional

# Set of known consumer, free webmail, and disposable email domains (normalized lowercase)
PUBLIC_EMAIL_DOMAINS = frozenset({
    # Google
    "gmail.com",
    "googlemail.com",
    "google.com",
    
    # Microsoft Consumer
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "passport.com",
    "windowslive.com",
    "hotmail.co.uk",
    "hotmail.fr",
    "hotmail.de",
    "hotmail.es",
    "hotmail.it",
    "outlook.in",
    "outlook.fr",
    "outlook.de",
    "outlook.es",
    "outlook.co.uk",
    
    # Yahoo & AOL
    "yahoo.com",
    "ymail.com",
    "rocketmail.com",
    "yahoo.co.uk",
    "yahoo.ca",
    "yahoo.co.in",
    "yahoo.in",
    "yahoo.fr",
    "yahoo.de",
    "yahoo.es",
    "yahoo.it",
    "yahoo.com.au",
    "yahoo.com.br",
    "yahoo.co.jp",
    "aol.com",
    "aim.com",
    "love.com",
    "games.com",
    "wow.com",
    
    # Mail.com & Aliases
    "mail.com",
    "email.com",
    "usa.com",
    "myself.com",
    "post.com",
    "dr.com",
    "engineer.com",
    "consultant.com",
    "techie.com",
    "writeme.com",
    "cheerful.com",
    
    # Apple
    "icloud.com",
    "me.com",
    "mac.com",
    
    # Proton & Privacy Webmail
    "proton.me",
    "protonmail.com",
    "protonmail.ch",
    "pm.me",
    "tutanota.com",
    "tuta.io",
    "tuta.com",
    "hushmail.com",
    "fastmail.com",
    
    # Zoho Free Webmail
    "zoho.com",
    "zohomail.com",
    "zoho.in",
    "zoho.eu",
    
    # GMX
    "gmx.com",
    "gmx.net",
    "gmx.de",
    "gmx.at",
    "gmx.ch",
    "gmx.co.uk",
    
    # Yandex & Russian Providers
    "yandex.com",
    "yandex.ru",
    "yandex.by",
    "yandex.kz",
    "yandex.ua",
    "ya.ru",
    "mail.ru",
    "inbox.ru",
    "list.ru",
    "bk.ru",
    
    # Indian / Asian Consumer Webmail
    "rediffmail.com",
    "rediff.com",
    "163.com",
    "126.com",
    "qq.com",
    "sina.com",
    "sohu.com",
    "aliyun.com",
    "naver.com",
    "daum.net",
    "hanmail.net",
    "kakao.com",
    
    # European / Latin Consumer Webmail
    "web.de",
    "freenet.de",
    "t-online.de",
    "orange.fr",
    "wanadoo.fr",
    "free.fr",
    "sfr.fr",
    "laposte.net",
    "bol.com.br",
    "uol.com.br",
    "terra.com.br",
    "ig.com.br",
    "libero.it",
    "virgilio.it",
    
    # Temporary / Disposable Email Services
    "tempmail.com",
    "temp-mail.org",
    "tempmail.net",
    "guerrillamail.com",
    "guerrillamailblock.com",
    "guerrillamail.net",
    "guerrillamail.org",
    "guerrillamail.biz",
    "sharklasers.com",
    "grr.la",
    "mailinator.com",
    "mailinator.net",
    "mailin8r.com",
    "dispostable.com",
    "10minutemail.com",
    "10minutemail.net",
    "10minutemail.org",
    "throwawaymail.com",
    "yopmail.com",
    "yopmail.fr",
    "yopmail.net",
    "trashmail.com",
    "trashmail.net",
    "maildrop.cc",
    "getnada.com",
    "fakeinbox.com",
    "burnermail.io",
    "inboxkitten.com",
    "crazymailing.com",
    "mytemp.email",
    "tempail.com",
    "mohmal.com",
    "emailondeck.com",
    "generator.email",
    "temp-mail.io",
    "disposablemail.com",
    "dropmail.me",
    "nada.ltd"
})

EMAIL_REGEX = re.compile(r"^[^@\s]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$")


def extract_email_domain(email: Optional[str]) -> Optional[str]:
    """
    Extract and normalize the domain from an email address.
    
    Args:
        email: Email string (e.g. 'john.doe@company.com')
        
    Returns:
        Normalized domain string (e.g. 'company.com') or None if invalid.
    """
    if not email or not isinstance(email, str):
        return None
    
    cleaned = email.strip().lower()
    match = EMAIL_REGEX.match(cleaned)
    if not match:
        # Fallback split check
        if "@" in cleaned:
            parts = cleaned.rsplit("@", 1)
            username = parts[0].strip()
            domain = parts[1].strip()
            if username and "." in domain and not domain.startswith(".") and not domain.endswith("."):
                return domain
        return None
    
    return match.group(1).strip()


def is_public_or_disposable_domain(domain: Optional[str]) -> bool:
    """
    Check if a domain or any of its parent domain segments belongs to a public/disposable provider.
    
    Args:
        domain: Domain string (e.g. 'gmail.com', 'mail.yahoo.co.uk')
        
    Returns:
        True if public/disposable, False otherwise.
    """
    if not domain:
        return True
    
    domain = domain.strip().lower()
    
    # Direct match
    if domain in PUBLIC_EMAIL_DOMAINS:
        return True
    
    # Check parent domain hierarchies (e.g. sub.gmail.com -> gmail.com)
    parts = domain.split(".")
    for i in range(1, len(parts) - 1):
        parent_domain = ".".join(parts[i:])
        if parent_domain in PUBLIC_EMAIL_DOMAINS:
            return True
            
    return False


def is_company_email(email: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Determine if an email belongs to a verified company/business domain.
    
    Args:
        email: Email address string
        
    Returns:
        Tuple of (is_company: bool, domain: Optional[str])
    """
    domain = extract_email_domain(email)
    if not domain:
        return False, None
    
    if is_public_or_disposable_domain(domain):
        return False, domain
    
    return True, domain
