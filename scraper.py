from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import json
import time
import re
from datetime import datetime, timedelta
from fake_useragent import UserAgent
import requests
import logging
from urllib3.exceptions import TimeoutError as UrllibTimeoutError
from requests.exceptions import RequestException
import backoff
import asyncio
import os
import tempfile
import subprocess
import sys
from dotenv import load_dotenv
import pickle
from pathlib import Path

class FacebookReelScraper:
    def __init__(self, use_cookies=True, auto_login=True):
        self.setup_logger()
        self.logger.info("Initializing Facebook Reel Scraper")
        self.use_cookies = use_cookies
        self.auto_login = auto_login
        self.video_global = None
        self.login_attempted = False  # Track if login has been attempted
        
        if use_cookies:
            self.cookies = self.load_cookies('facebook_cookies.json')
            # If cookies are empty or invalid, try to login automatically
            if not self.cookies and auto_login:
                self.logger.info("No valid cookies found, attempting automatic login...")
                self.cookies = self.login_and_save_cookies()
                self.login_attempted = True
        else:
            self.cookies = {}

    def setup_logger(self):
        """Setup logger with timestamp and formatting"""
        self.logger = logging.getLogger('FacebookReelScraper')
        
        # Only add handler if it doesn't already exist
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            
            # Create console handler with formatting
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            
            # Add handler to logger
            self.logger.addHandler(ch)
        
    def load_cookies(self, path):
        """Load cookies from file, convert to dict if needed."""
        if not os.path.exists(path):
            self.logger.error(f"Cookie file {path} not found.")
            return {}
        with open(path, 'r') as f:
            cookies = json.load(f)
        # If it's a list, convert to dict
        if isinstance(cookies, list):
            cookies_dict = {cookie['name']: cookie['value'] for cookie in cookies if 'name' in cookie and 'value' in cookie}
            # Overwrite the file with the correct format
            with open(path, 'w') as f2:
                json.dump(cookies_dict, f2)
            self.logger.info("Converted cookie file to name-value dict format.")
            return cookies_dict
        return cookies

    def login_and_save_cookies(self):
        """Login to Facebook and save cookies for future use"""
        self.logger.info("Starting automatic Facebook login...")
        
        # Load environment variables
        load_dotenv()
        
        # Get credentials from environment variables
        email = os.getenv('FACEBOOK_EMAIL')
        password = os.getenv('FACEBOOK_PASSWORD')
        
        if not email or not password:
            self.logger.error("Facebook credentials not found in environment variables (FACEBOOK_EMAIL, FACEBOOK_PASSWORD)")
            return {}
        
        self.logger.info(f"Attempting login with email: {email}")
        
        try:
            # Use direct Playwright approach instead of subprocess
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                
                page = context.new_page()
                
                # Navigate to Facebook login page
                self.logger.info("Navigating to Facebook login page...")
                page.goto("https://web.facebook.com/login", wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(3000)
                
                # Fill in email
                self.logger.info("Filling email...")
                page.fill('input[name="email"]', email)
                page.wait_for_timeout(1000)
                
                # Fill in password
                self.logger.info("Filling password...")
                page.fill('input[name="pass"]', password)
                page.wait_for_timeout(1000)
                
                # Click login button
                self.logger.info("Clicking login button...")
                page.click('button[name="login"]')
                
                # Wait for login to complete
                self.logger.info("Waiting for login to complete...")
                page.wait_for_timeout(5000)
                
                # Check if login was successful
                current_url = page.url
                self.logger.info(f"Current URL after login: {current_url}")
                
                if "login" not in current_url and "checkpoint" not in current_url:
                    self.logger.info("Login successful!")
                    
                    # Get cookies
                    cookies = context.cookies()
                    cookies_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                    
                    # Save cookies to file
                    with open('facebook_cookies.json', 'w') as f:
                        json.dump(cookies_dict, f, indent=2)
                    
                    self.logger.info(f"Saved {len(cookies_dict)} cookies to file")
                    return cookies_dict
                else:
                    self.logger.error("Login failed - still on login page or checkpoint")
                    return {}
                    
        except Exception as e:
            self.logger.error(f"Failed to login to Facebook: {str(e)}")
            return {}

    def validate_cookies(self):
        """Validate if current cookies are still valid, refresh if needed"""
        if not self.cookies:
            self.logger.info("No cookies available, attempting login...")
            return self.login_and_save_cookies()
        
        self.logger.info("Validating existing cookies...")
        
        try:
            # Use direct Playwright approach instead of subprocess
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                
                # Add cookies to context
                cookies_list = []
                for name, value in self.cookies.items():
                    cookies_list.append({
                        'name': name,
                        'value': value,
                        'domain': '.facebook.com',
                        'path': '/'
                    })
                
                context.add_cookies(cookies_list)
                
                page = context.new_page()
                
                # Navigate to Facebook to check if logged in
                self.logger.info("Validating cookies by navigating to Facebook...")
                page.goto("https://web.facebook.com", wait_until='domcontentloaded', timeout=20000)
                page.wait_for_timeout(3000)
                
                # Check if we're logged in by looking for logout button or profile elements
                current_url = page.url
                self.logger.info(f"Current URL: {current_url}")
                
                # Check for elements that indicate we're logged in
                logged_in = False
                try:
                    # Look for elements that indicate logged in state
                    profile_link = page.query_selector('a[href*="/me/"], a[href*="/profile.php"]')
                    if profile_link:
                        logged_in = True
                        self.logger.info("Found profile link - logged in")
                    else:
                        self.logger.info("No profile link found")
                except:
                    pass
                
                # Also check URL patterns
                if "login" not in current_url and "checkpoint" not in current_url:
                    logged_in = True
                    self.logger.info("URL indicates logged in")
                else:
                    self.logger.info("URL indicates not logged in")
                
                if logged_in:
                    self.logger.info("Cookies are valid!")
                    # Get fresh cookies
                    fresh_cookies = context.cookies()
                    fresh_cookies_dict = {cookie['name']: cookie['value'] for cookie in fresh_cookies}
                    
                    # Save fresh cookies
                    with open('facebook_cookies.json', 'w') as f:
                        json.dump(fresh_cookies_dict, f, indent=2)
                    
                    self.logger.info(f"Updated with {len(fresh_cookies_dict)} fresh cookies")
                    self.cookies = fresh_cookies_dict
                    return fresh_cookies_dict
                else:
                    self.logger.warning("Cookies are invalid, attempting fresh login...")
                    return self.login_and_save_cookies()
                    
        except Exception as e:
            self.logger.error(f"Failed to validate cookies: {str(e)}")
            return self.login_and_save_cookies()

    def extract_reel_id(self, url):
        """Extract reel ID from URL"""
        try:
            # Try to extract ID from URL
            match = re.search(r'/(\d+)/?', url)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            self.logger.error(f"Failed to extract reel ID: {str(e)}")
            return None

    def get_reel_data(self, url):
        """Main method - uses authenticated scraping if cookies available, otherwise public scraping"""
        if self.use_cookies and self.cookies:
            self.logger.info("Using authenticated scraping")
            return self.get_reel_data_authenticated(url)
        else:
            self.logger.info("Using public scraping (no authentication)")
            return self.get_reel_data_public(url)

    def get_reel_data_public(self, url):
        """Scrape Facebook Reel following the exact flow: reel page -> user profile -> views"""
        self.logger.info(f"Scraping public reel: {url}")
        reel_id = self.extract_reel_id(url)
        
        browser = None
        context = None
        page = None
        
        try:
            with sync_playwright() as p:
                # Step 1: Navigate to the reel page and extract basic data
                self.logger.info("=" * 50)
                self.logger.info("STEP 1: EXTRACTING BASIC DATA FROM REEL PAGE")
                self.logger.info("=" * 50)
                
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                
                page = context.new_page()
                page.set_default_timeout(20000)  # Reduced timeout to 20 seconds
                
                # Navigate to reel page with timeout
                self.logger.info(f"Navigating to reel page: {url}")
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=20000)
                    page.wait_for_timeout(3000)  # Reduced wait time
                    self.logger.info("Successfully loaded reel page")
                except Exception as e:
                    self.logger.error(f"Failed to load reel page: {str(e)}")
                    return None
                
                # Wait for engagement elements to load with shorter timeout
                self.logger.info("Waiting for engagement elements to load...")
                try:
                    # Wait for either comments or shares to appear
                    page.wait_for_selector('[aria-label="Comment"], [aria-label="Share"], [aria-label="Like"]', timeout=5000)
                    self.logger.info("Engagement elements found")
                except:
                    self.logger.warning("Engagement elements not found, continuing anyway")
                
                # Check what elements are actually on the page
                self.logger.info("Extracting data from reel page...")
                try:
                    basic_data = page.evaluate('''() => {
                        const result = {};
                        
                        // Find all spans with numbers
                        const allSpans = Array.from(document.querySelectorAll('span'));
                        const numberSpans = allSpans.filter(span => {
                            const text = span.textContent.trim();
                            return text.match(/^\\d+(\\.\\d+)?[KMkm]?$/);
                        });
                        
                        // Extract engagement numbers using a smarter approach
                        // Method 1: Look for numbers near engagement buttons
                        const engagementButtons = document.querySelectorAll('[aria-label="Comment"], [aria-label="Share"], [aria-label="Like"]');
                        
                        engagementButtons.forEach((button, i) => {
                            const ariaLabel = button.getAttribute('aria-label');
                            
                            // Look for numbers in the same container or nearby
                            const container = button.closest('div');
                            if (container) {
                                // Look in the same container first
                                const containerSpans = container.querySelectorAll('span');
                                
                                for (const span of containerSpans) {
                                    const text = span.textContent.trim();
                                    if (text.match(/^\\d+(\\.\\d+)?[KMkm]?$/)) {
                                        let number = text;
                                        if (text.toLowerCase().includes('k')) {
                                            number = parseFloat(text.replace(/[KMkm]/g, '')) * 1000;
                                        } else if (text.toLowerCase().includes('m')) {
                                            number = parseFloat(text.replace(/[KMkm]/g, '')) * 1000000;
                                        } else {
                                            number = parseInt(text);
                                        }
                                        
                                        if (ariaLabel === 'Comment') {
                                            result.comments = number;
                                        } else if (ariaLabel === 'Share') {
                                            result.shares = number;
                                        } else if (ariaLabel === 'Like') {
                                            result.likes = number;
                                        }
                                        break;
                                    }
                                }
                                
                                // If not found in container, look in parent containers
                                if (!result.comments && ariaLabel === 'Comment' || 
                                    !result.shares && ariaLabel === 'Share' || 
                                    !result.likes && ariaLabel === 'Like') {
                                    
                                    let currentParent = container.parentElement;
                                    let depth = 0;
                                    while (currentParent && depth < 3) {
                                        const parentSpans = currentParent.querySelectorAll('span');
                                        
                                        for (const span of parentSpans) {
                                            const text = span.textContent.trim();
                                            if (text.match(/^\\d+(\\.\\d+)?[KMkm]?$/)) {
                                                let number = text;
                                                if (text.toLowerCase().includes('k')) {
                                                    number = parseFloat(text.replace(/[KMkm]/g, '')) * 1000;
                                                } else if (text.toLowerCase().includes('m')) {
                                                    number = parseFloat(text.replace(/[KMkm]/g, '')) * 1000000;
                                                } else {
                                                    number = parseInt(text);
                                                }
                                                
                                                if (ariaLabel === 'Comment' && !result.comments) {
                                                    result.comments = number;
                                                } else if (ariaLabel === 'Share' && !result.shares) {
                                                    result.shares = number;
                                                } else if (ariaLabel === 'Like' && !result.likes) {
                                                    result.likes = number;
                                                }
                                                break;
                                            }
                                        }
                                        
                                        if ((result.comments && ariaLabel === 'Comment') || 
                                            (result.shares && ariaLabel === 'Share') || 
                                            (result.likes && ariaLabel === 'Like')) {
                                            break;
                                        }
                                        
                                        currentParent = currentParent.parentElement;
                                        depth++;
                                    }
                                }
                            }
                        });
                        
                        // Method 2: If we still don't have all numbers, use the known numbers we found
                        if (!result.comments || !result.shares || !result.likes) {
                            const knownNumbers = numberSpans.map(span => {
                                const text = span.textContent.trim();
                                let number = text;
                                if (text.toLowerCase().includes('k')) {
                                    number = parseFloat(text.replace(/[KMkm]/g, '')) * 1000;
                                } else if (text.toLowerCase().includes('m')) {
                                    number = parseFloat(text.replace(/[KMkm]/g, '')) * 1000000;
                                } else {
                                    number = parseInt(text);
                                }
                                return { text, number };
                            });
                            
                            // Assign numbers based on typical patterns
                            // Usually: likes (largest), comments (medium), shares (smallest)
                            if (knownNumbers.length >= 3) {
                                const sortedNumbers = knownNumbers.sort((a, b) => b.number - a.number);
                                
                                if (!result.likes) {
                                    result.likes = sortedNumbers[0].number;
                                }
                                if (!result.comments) {
                                    result.comments = sortedNumbers[1].number;
                                }
                                if (!result.shares) {
                                    result.shares = sortedNumbers[2].number;
                                }
                            } else if (knownNumbers.length >= 2) {
                                const sortedNumbers = knownNumbers.sort((a, b) => b.number - a.number);
                                if (!result.likes) {
                                    result.likes = sortedNumbers[0].number;
                                }
                                if (!result.comments) {
                                    result.comments = sortedNumbers[1].number;
                                }
                            } else if (knownNumbers.length >= 1) {
                                if (!result.likes) {
                                    result.likes = knownNumbers[0].number;
                                }
                            }
                        }
                        
                        // Extract user profile link
                        const userSelectors = [
                            'a[href*="/profile.php"]',
                            'a[href*="/people/"]',
                            'h3 a[href*="/"]',
                            '[data-testid="post_actor_link"]'
                        ];
                        
                        for (const selector of userSelectors) {
                            const el = document.querySelector(selector);
                            if (el && el.href) {
                                result.user_profile_url = el.href;
                                result.user_name = el.textContent.trim();
                                break;
                            }
                        }
                        
                        // Extract description
                        const descEl = document.querySelector('[data-testid="post_message"], [data-ad-preview="message"], .userContent');
                        if (descEl) {
                            result.description = descEl.textContent.trim();
                        }
                        
                        // Extract video URL
                        const video = document.querySelector('video');
                        if (video && video.src) {
                            result.video_url = video.src;
                        }
                        
                        return result;
                    }''')
                    
                    self.logger.info(f"Data extracted - Comments: {basic_data.get('comments', 'N/A')}, Shares: {basic_data.get('shares', 'N/A')}, Likes: {basic_data.get('likes', 'N/A')}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to extract basic data: {str(e)}")
                    return None
                
                # Build basic result without views (simplified for now)
                reel_data = {
                    'url': url,
                    'user_posted': basic_data.get('user_name', ''),
                    'description': basic_data.get('description', ''),
                    'hashtags': self.extract_hashtags(basic_data.get('description', '')),
                    'num_comments': basic_data.get('comments'),
                    'shares': basic_data.get('shares'),
                    'likes': basic_data.get('likes'),
                    'views': None,
                    'video_url': basic_data.get('video_url', ''),
                    'user_profile_url': basic_data.get('user_profile_url'),
                    'post_id': reel_id,
                    'views_source': 'public_scrape'
                }
                
                self.logger.info("=" * 50)
                self.logger.info("SCRAPING COMPLETED")
                self.logger.info(f"Comments: {reel_data.get('num_comments')}, Shares: {reel_data.get('shares')}, Likes: {reel_data.get('likes')}")
                self.logger.info("=" * 50)
                
                return reel_data
                
        except Exception as e:
            self.logger.error(f"Public scraping failed: {str(e)}")
            return None
        finally:
            # Ensure proper cleanup
            try:
                if page:
                    page.close()
            except:
                pass
            try:
                if context:
                    context.close()
            except:
                pass
            try:
                if browser:
                    browser.close()
            except:
                pass

    def get_reel_data_authenticated(self, url):
        """Scrape Facebook Reel with authentication - simplified version"""
        self.logger.info(f"Scraping reel with authentication: {url}")
        # For now, just use the public method since we have the same logic
        return self.get_reel_data_public(url)

    def extract_number(self, text):
        """Extract number from text with K/M suffixes"""
        try:
            if not text:
                return 0
            text = text.lower().strip()
            text = re.sub(r'[^0-9km.]', '', text)
            if 'k' in text:
                number = float(text.replace('k', ''))
                return int(number * 1000)
            elif 'm' in text:
                number = float(text.replace('m', ''))
                return int(number * 1000000)
            else:
                return int(float(text))
        except Exception:
            return 0

    def extract_hashtags(self, text):
        """Extract hashtags from text"""
        self.logger.debug(f"Extracting hashtags from text: {text[:100]}...")
        hashtags = re.findall(r'#\w+', text)
        self.logger.info(f"Found {len(hashtags)} hashtags")
        return hashtags

    def quick_scrape(self, url):
        """Quick scrape method that skips complex video links extraction"""
        self.logger.info(f"Quick scraping reel: {url}")
        reel_id = self.extract_reel_id(url)
        
        try:
            with sync_playwright() as p:
                # Launch browser with minimal settings for speed
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-web-security'
                    ]
                )
                
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 720}
                )
                
                page = context.new_page()
                page.set_default_timeout(15000)  # 15 seconds
                
                # Quick navigation
                self.logger.info("Quick navigation to reel page...")
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=15000)
                    self.logger.info("Page loaded successfully")
                except Exception as e:
                    self.logger.error(f"Failed to load page: {str(e)}")
                    browser.close()
                    return None
                
                # Quick data extraction
                self.logger.info("Quick data extraction...")
                try:
                    data = page.evaluate('''() => {
                        const result = {};
                        
                        // Basic video URL extraction
                        const video = document.querySelector('video');
                        if (video && video.src) {
                            result.video_url = video.src;
                        }
                        
                        // Basic description
                        const messageEl = document.querySelector('[data-testid="post_message"], [data-ad-preview="message"], .userContent');
                        if (messageEl) {
                            result.description = messageEl.textContent.trim();
                        }
                        
                        // Basic user info
                        const userEl = document.querySelector('a[role="link"][tabindex="0"], h3 a, [data-testid="post_actor_link"]');
                        if (userEl) {
                            result.user_posted = userEl.textContent.trim();
                            result.user_profile_url = userEl.href;
                        }
                        
                        // Basic engagement numbers
                        const spans = Array.from(document.querySelectorAll('span'));
                        const numbers = spans
                            .map(span => span.textContent.trim())
                            .filter(text => /^\\d+(\\.\\d+)?[KMkm]?$/.test(text))
                            .map(text => {
                                const num = parseFloat(text.replace(/[KMkm]/g, ''));
                                if (text.toLowerCase().includes('k')) return num * 1000;
                                if (text.toLowerCase().includes('m')) return num * 1000000;
                                return num;
                            });
                        
                        if (numbers.length >= 1) result.views = numbers[0];
                        if (numbers.length >= 2) result.num_comments = numbers[1];
                        
                        // Basic date
                        const timeEl = document.querySelector('time, [data-testid="post_timestamp"], .timestamp');
                        if (timeEl) {
                            result.date_posted = timeEl.textContent.trim();
                        }
                        
                        return result;
                    }''')
                    
                    self.logger.info("Quick data extraction completed")
                    
                except Exception as e:
                    self.logger.error(f"Failed to extract data: {str(e)}")
                    browser.close()
                    return None
                
                # Extract hashtags
                hashtags = self.extract_hashtags(data.get('description', ''))
                
                # Build basic reel data (skip complex video links extraction)
                reel_data = {
                    'url': url,
                    'user_posted': data.get('user_posted', ''),
                    'description': data.get('description', ''),
                    'hashtags': hashtags,
                    'num_comments': data.get('num_comments'),
                    'date_posted': data.get('date_posted'),
                    'likes': data.get('views'),
                    'views': data.get('views'),
                    'video_play_count': data.get('views'),
                    'top_comments': [],
                    'post_id': reel_id,
                    'thumbnail': '',
                    'shortcode': reel_id,
                    'content_id': reel_id,
                    'product_type': 'clips',
                    'coauthor_producers': [],
                    'tagged_users': [],
                    'length': None,
                    'video_url': data.get('video_url', ''),
                    'audio_url': '',
                    'posts_count': None,
                    'followers': None,
                    'following': None,
                    'user_profile_url': data.get('user_profile_url'),
                    'is_paid_partnership': None,
                    'is_verified': None,
                    'views_source': 'quick_scrape'
                }
                
                browser.close()
                self.logger.info("Quick scrape completed successfully")
                return reel_data
                
        except Exception as e:
            self.logger.error(f"Quick scraping failed: {str(e)}")
            return None 