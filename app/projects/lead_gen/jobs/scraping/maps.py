from playwright.sync_api import sync_playwright
import time
import sys
import traceback
from bson import ObjectId
from app.core.database import get_collection
from app.projects.lead_gen.jobs import model as jobs_model
from app.projects.lead_gen.leads import model as leads_model
from app.projects.lead_gen.jobs.scraping.emails import EmailExtractor
from app.projects.lead_gen.jobs.scraping.normalize import normalize_url, normalize_phone
from app.projects.lead_gen.jobs.scraping.concurrency import LeadProcessor

import threading

class MapsScraper:
    def __init__(self, job_id):
        self.job_id = job_id
        self.email_extractor = EmailExtractor()
        # Phone-based deduplication
        self.seen_phones = set()
        self._phone_lock = threading.Lock()
        # Background workers may be exercised directly in tests or reused before run().
        self.search_location_parts = []
        self.last_activity_time = time.time()
        self.processor = None

    def run(self):
        job = jobs_model.find_by_id(self.job_id)
        if not job:
            return

        print(f"MapsScraper starting for job {self.job_id}")
        
        # Extract location from query for filtering (e.g. "digital marketing in delhi, india" → ["delhi", "india"])
        query_text = job.get('query_text', '')
        self.search_location_parts = []
        if ' in ' in query_text.lower():
            raw_location = query_text.lower().split(' in ')[-1].strip()
            # Split by comma to get individual location parts (city, state, country)
            self.search_location_parts = [part.strip() for part in raw_location.split(',') if part.strip()]
            print(f"📍 Location filter active: {self.search_location_parts}")
        
        # Initialize thread processor
        # Increased to 10 threads for higher speed
        self.processor = LeadProcessor(use_threads=True, max_threads=10)
        
        # Track last activity for stagnation check
        self.last_activity_time = time.time()

        with sync_playwright() as p:
            is_macos = sys.platform == 'darwin'
            
            if is_macos:
                print("🍎 Using Firefox browser (macOS)")
                browser = p.firefox.launch(
                    headless=True,
                    firefox_user_prefs={
                        "dom.webdriver.enabled": False,
                        "useAutomationExtension": False
                    }
                )
            else:
                print("🐧 Using Chromium browser (Linux)")
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
            
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.set_default_timeout(60000)

            try:
                page.goto(f"https://www.google.com/maps/search/{job['query_text']}", timeout=90000)
                page.wait_for_selector('div[role="feed"]', timeout=60000)
                
                feed_selector = 'div[role="feed"]'
                seen_urls = set()
                
                MAX_ITER = 100 
                iter_count = 0
                STAGNATION_LIMIT = 120 # 2 minutes
                
                while job['leads_delivered'] < job['leads_requested'] and iter_count < MAX_ITER:
                    # Check for stagnation
                    if time.time() - self.last_activity_time > STAGNATION_LIMIT:
                        print(f"Stopping job {self.job_id} due to stagnation (no new leads for {STAGNATION_LIMIT}s)")
                        break

                    iter_count += 1
                    
                    links = page.locator(f'{feed_selector} > div > div a[href*="/maps/place/"]').all()
                    
                    found_new_on_view = False
                    
                    for link in links:
                        if job['leads_delivered'] >= job['leads_requested']:
                            break
                            
                        url = link.get_attribute('href')
                        if not url: 
                            continue
                        
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        found_new_on_view = True
                        
                        try:
                            link.click(timeout=15000)
                            page.wait_for_selector('div[role="main"]', timeout=15000)
                            time.sleep(2)
                            
                            self.extract_details(page, url)
                            
                            job = jobs_model.find_by_id(self.job_id)
                            
                            try:
                                if not page.is_visible(feed_selector):
                                    back_btn = page.locator('button[aria-label="Back"]')
                                    if back_btn.is_visible():
                                        back_btn.click()
                                        page.wait_for_selector(feed_selector)
                            except:
                                pass
                                    
                        except Exception as e:
                            print(f"Failed to extract item: {e}")
                            try:
                                if page and not page.is_closed():
                                    if not page.is_visible(feed_selector):
                                        page.go_back()
                                        page.wait_for_selector(feed_selector, timeout=10000)
                            except:
                                try:
                                    page.goto(f"https://www.google.com/maps/search/{job['query_text']}", timeout=60000)
                                    page.wait_for_selector(feed_selector, timeout=30000)
                                except:
                                    break

                    page.hover(feed_selector)
                    page.mouse.wheel(0, 2000)
                    time.sleep(2)
                    
            except Exception as e:
                print(f"Scraper critical error: {e}")
                traceback.print_exc()
            finally:
                browser.close()
                self.processor.shutdown()

    def process_lead_background(self, data):
        """Background task to extract email and save lead"""
        import threading
        t_name = threading.current_thread().name
        try:
            name = data['name']
            phone = data['phone']
            website = data['website']
            address = data['address']
            google_url = data['google_url']
            
            norm_phone = normalize_phone(phone)
            norm_web = normalize_url(website)
            
            if not norm_phone and not norm_web:
                return
            
            # Filter out "Sponsored" entries with no real name
            if name.strip().lower() == 'sponsored':
                print(f"[{t_name}] Skipping sponsored listing (no real name)")
                return
            
            # Location filter: skip leads from other cities
            if self.search_location_parts and address:
                addr_lower = address.lower()
                # Check if ANY location part (city/state/country) appears in the address
                if not any(part in addr_lower for part in self.search_location_parts):
                    print(f"[{t_name}] Skipping out-of-location lead: {name} (address: {address})")
                    return
            
            # Deduplicate by phone number (skip if already seen)
            if norm_phone:
                with self._phone_lock:
                    if norm_phone in self.seen_phones:
                        print(f"[{t_name}] Skipping duplicate phone: {norm_phone} ({name})")
                        return
                    self.seen_phones.add(norm_phone)
                
            email = None
            if norm_web:
                try:
                    email = self.email_extractor.extract(norm_web)
                except: 
                    pass
                
            self.save_lead(name, norm_phone, norm_web, email, address, google_url)
            print(f"[{t_name}] Processed lead: {name}")
        except Exception as e:
            print(f"[{t_name}] Background processing failed: {e}")

    def extract_details(self, page, google_url):
        try:
            try:
                name = page.locator('div[role="main"] h1').first.inner_text()
            except:
                name = ""
            
            if not name or name.strip() == "Results" or name.strip() == "":
                try:
                    h1s = page.locator('h1').all_inner_texts()
                    for h in h1s:
                        if h.strip() and h.strip() != "Results":
                            name = h
                            break
                except: 
                    pass

            if not name or name.strip() == "Results" or name.strip() == "":
                title = page.title()
                if " - Google Maps" in title:
                    name = title.replace(" - Google Maps", "")
                elif "Google Maps" not in title:
                    name = title
            
            if not name:
                name = "Unknown"

            print(f"Extracted Name: {name}")
        except:
            name = "Unknown"
            print("Name extraction failed completely.")
            
        website = None
        try:
            ws_btn = page.locator('a[data-item-id="authority"]')
            if ws_btn.count() > 0:
                website = ws_btn.get_attribute('href')
            
            if not website:
                ws_link = page.locator('a[aria-label^="Website:"]') 
                if ws_link.count() > 0:
                    website = ws_link.get_attribute('href')

        except: 
            pass
        
        phone = None
        try:
            ph_btn = page.locator('button[data-item-id^="phone:tel:"]')
            if ph_btn.count() > 0:
                phone = ph_btn.get_attribute('data-item-id').replace('phone:tel:', '')
        except: 
            pass
        
        address = None
        try:
            addr_btn = page.locator('button[data-item-id="address"]')
            if addr_btn.count() > 0:
                address = addr_btn.get_attribute('aria-label').replace('Address: ', '')
        except: 
            pass

        # Prepare data for background processing
        data = {
            'name': name,
            'phone': phone,
            'website': website,
            'address': address,
            'google_url': google_url
        }
        
        # Submit to thread pool
        self.processor.submit_lead(data, self.process_lead_background)

    def save_lead(self, name, phone, website, email, address, maps_url):
        try:
            job = jobs_model.find_by_id(self.job_id)
            if not job:
                return
            
            # Prevent over-delivery due to race conditions
            if job.get('leads_delivered', 0) >= job.get('leads_requested', 0):
                print(f"Skipping save for {name}: Limit reached.")
                return

            user_id = str(job['user_id'])
            
            # DB-level dedup: check if phone already exists for this job
            if phone:
                coll = get_collection('lead_leads')
                existing = coll.find_one({
                    'job_id': ObjectId(self.job_id) if isinstance(self.job_id, str) else self.job_id,
                    'phone': phone
                })
                if existing:
                    print(f"Skipping duplicate (DB check): {name} - {phone}")
                    return

            # Save lead
            leads_model.create(
                job_id=self.job_id,
                user_id=user_id,
                name=name,
                phone=phone,
                email=email,
                website=website,
                address=address,
                source='google_maps'
            )
            
            # Update job progress
            jobs_model.update_progress(self.job_id, job['leads_delivered'] + 1)
            
            # Update activity timestamp
            self.last_activity_time = time.time()
            
            print(f"Saved lead: {name}")
            
        except Exception as e:
            print(f"Failed to save lead: {e}")
            traceback.print_exc()
