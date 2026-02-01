import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from app.lead_gen.jobs.scraping.constants import EMAIL_REGEX, IGNORE_EMAILS, CONTACT_KEYWORDS

class EmailExtractor:
    def __init__(self, max_pages=3, max_depth=1, timeout=10):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.visited = set()

    def extract(self, start_url):
        if not start_url:
            return None
            
        emails = set()
        queue = [(start_url, 0)]
        self.visited = {start_url}
        pages_crawled = 0

        while queue and pages_crawled < self.max_pages:
            url, depth = queue.pop(0)
            pages_crawled += 1
            
            try:
                resp = requests.get(url, headers=self.headers, timeout=self.timeout)
                if resp.status_code != 200:
                    continue
                
                text = resp.text
                
                # Find emails in current page
                found = re.findall(EMAIL_REGEX, text)
                for email in found:
                    email_lower = email.lower()
                    if not any(ign in email_lower for ign in IGNORE_EMAILS):
                        # Simple extension validation
                        if '.' in email.split('@')[1]:
                            emails.add(email)

                # Look for contact pages if depth allows
                if depth < self.max_depth:
                    soup = BeautifulSoup(text, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        full_url = urljoin(url, href)
                        
                        # Only follow internal links
                        if urlparse(full_url).netloc != urlparse(start_url).netloc:
                            continue
                            
                        # Only follow if looks like contact page
                        link_text = a.get_text().lower()
                        link_href_lower = href.lower()
                        
                        is_contact = any(k in link_text for k in CONTACT_KEYWORDS) or \
                                     any(k in link_href_lower for k in CONTACT_KEYWORDS)
                                     
                        if is_contact and full_url not in self.visited:
                            self.visited.add(full_url)
                            queue.append((full_url, depth + 1))
                            
            except Exception as e:
                pass
                
        return list(emails)[0] if emails else None
