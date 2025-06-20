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
from dotenv import load_dotenv
import pickle
from pathlib import Path

class FacebookReelScraper:
    def __init__(self, use_cookies=True):
        self.setup_logger()
        self.logger.info("Initializing Facebook Reel Scraper")
        self.use_cookies = use_cookies
        self.video_global = None
        if use_cookies:
            self.cookies = self.load_cookies('facebook_cookies.json')
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

    def extract_username_from_profile_id(self, profile_url):
        """Extract username from profile.php URL by navigating to it"""
        try:
            # Extract profile ID from URL
            import re
            profile_id_match = re.search(r'id=(\d+)', profile_url)
            if not profile_id_match:
                self.logger.warning("No profile ID found in URL")
                return None
                
            profile_id = profile_id_match.group(1)
            self.logger.info(f"Extracting username for profile ID: {profile_id}")
            self.logger.info(f"Navigating to profile URL: {profile_url}")
            
            # Use a separate process to avoid async/sync conflicts
            import subprocess
            import sys
            
            # Create a simple script to extract username
            script_content = f'''
import asyncio
from playwright.async_api import async_playwright
import re
import sys

async def extract_username():
    browser = None
    context = None
    page = None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Set shorter timeout
            page.set_default_timeout(20000)
            
            # Navigate to profile page
            await page.goto("{profile_url}", wait_until='domcontentloaded', timeout=20000)
            
            # Get the final URL after redirect
            final_url = page.url
            print(f"FINAL_URL:{{final_url}}")
            
            # Extract username from the final URL
            # Handle URLs like: https://web.facebook.com/username/reels/
            if '/reels/' in final_url:
                # Extract username before /reels/
                username_match = re.search(r'/([^/]+)/reels/?$', final_url)
            else:
                # Extract username from the end of URL
                username_match = re.search(r'/([^/]+)/?$', final_url)
                
            if username_match and username_match.group(1) != 'profile.php':
                username = username_match.group(1)
                print(f"USERNAME:{{username}}")
            else:
                print("USERNAME:None")
            
    except Exception as e:
        print(f"ERROR:{{str(e)}}")
        print("USERNAME:None")
    finally:
        # Ensure proper cleanup
        try:
            if page:
                await page.close()
        except:
            pass
        try:
            if context:
                await context.close()
        except:
            pass
        try:
            if browser:
                await browser.close()
        except:
            pass

# Run with proper error handling
try:
    asyncio.run(extract_username())
except Exception as e:
    print(f"ERROR:{{str(e)}}")
    print("USERNAME:None")
'''
            
            # Write script to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            try:
                # Run the script with increased timeout and better error handling
                result = subprocess.run([sys.executable, script_path], 
                                      capture_output=True, text=True, timeout=90)
                
                # Parse output
                output_lines = result.stdout.strip().split('\n')
                final_url = None
                username = None
                error = None
                
                for line in output_lines:
                    if line.startswith('FINAL_URL:'):
                        final_url = line.replace('FINAL_URL:', '').strip()
                    elif line.startswith('USERNAME:'):
                        username = line.replace('USERNAME:', '').strip()
                        if username == 'None':
                            username = None
                    elif line.startswith('ERROR:'):
                        error = line.replace('ERROR:', '').strip()
                
                if error:
                    self.logger.error(f"Subprocess error: {error}")
                    return None
                
                if final_url:
                    self.logger.info(f"Profile page redirected to: {final_url}")
                
                if username:
                    self.logger.info(f"Extracted username: {username}")
                    return username
                else:
                    self.logger.warning(f"Could not extract username from final URL: {final_url}")
                
            except subprocess.TimeoutExpired:
                self.logger.error("Subprocess timed out")
                return None
            except Exception as e:
                self.logger.error(f"Subprocess execution error: {str(e)}")
                return None
            finally:
                # Clean up temporary file
                import os
                try:
                    os.unlink(script_path)
                except:
                    pass
                
        except Exception as e:
            self.logger.error(f"Failed to extract username from profile ID: {str(e)}")
            
        return None

    def get_redirected_profile_url(self, complex_profile_url):
        """Get the redirected clean URL from complex profile URL using subprocess"""
        if not complex_profile_url or complex_profile_url == "/":
            return None
            
        try:
            # Use subprocess to handle JavaScript redirects properly
            import subprocess
            import sys
            
            # Create a script to get the redirected URL
            script_content = f'''
import asyncio
from playwright.async_api import async_playwright
import re
import sys

async def get_redirected_url():
    browser = None
    context = None
    page = None
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Set shorter timeout
            page.set_default_timeout(20000)
            
            # Navigate to the complex profile URL
            await page.goto("{complex_profile_url}", wait_until='domcontentloaded', timeout=20000)
            
            # Get the final URL after redirect
            final_url = page.url
            print(f"FINAL_URL:{{final_url}}")
            
            # Extract username if it's a clean URL
            if '/profile.php' not in final_url and 'web.facebook.com' in final_url:
                if '/reels/' in final_url:
                    # URL already has /reels/, return as is
                    print(f"REDIRECTED_URL:{{final_url}}")
                else:
                    # Add /reels/ to the clean URL
                    reels_url = final_url.rstrip('/') + '/reels/'
                    print(f"REDIRECTED_URL:{{reels_url}}")
            else:
                # Still complex, try to extract username
                if '/profile.php' in final_url:
                    # Extract username from the redirected URL
                    if '/reels/' in final_url:
                        username_match = re.search(r'/([^/]+)/reels/?$', final_url)
                    else:
                        username_match = re.search(r'/([^/]+)/?$', final_url)
                    
                    if username_match and username_match.group(1) != 'profile.php':
                        username = username_match.group(1)
                        reels_url = f"https://web.facebook.com/{{username}}/reels/"
                        print(f"REDIRECTED_URL:{{reels_url}}")
                    else:
                        print(f"REDIRECTED_URL:{{final_url}}")
                else:
                    print(f"REDIRECTED_URL:{{final_url}}")
            
    except Exception as e:
        print(f"ERROR:{{str(e)}}")
        print(f"REDIRECTED_URL:{{complex_profile_url}}")
    finally:
        # Ensure proper cleanup
        try:
            if page:
                await page.close()
        except:
            pass
        try:
            if context:
                await context.close()
        except:
            pass
        try:
            if browser:
                await browser.close()
        except:
            pass

# Run with proper error handling
try:
    asyncio.run(get_redirected_url())
except Exception as e:
    print(f"ERROR:{{str(e)}}")
    print(f"REDIRECTED_URL:{{complex_profile_url}}")
'''
            
            # Write script to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            try:
                # Run the script with increased timeout and better error handling
                result = subprocess.run([sys.executable, script_path], 
                                      capture_output=True, text=True, timeout=90)
                
                # Parse output
                output_lines = result.stdout.strip().split('\n')
                final_url = None
                redirected_url = None
                error = None
                
                for line in output_lines:
                    if line.startswith('FINAL_URL:'):
                        final_url = line.replace('FINAL_URL:', '').strip()
                    elif line.startswith('REDIRECTED_URL:'):
                        redirected_url = line.replace('REDIRECTED_URL:', '').strip()
                    elif line.startswith('ERROR:'):
                        error = line.replace('ERROR:', '').strip()
                
                if error:
                    self.logger.error(f"Subprocess error: {error}")
                    return complex_profile_url
                
                if final_url:
                    self.logger.info(f"Profile page redirected to: {final_url}")
                
                if redirected_url:
                    self.logger.info(f"Using redirected URL: {redirected_url}")
                    return redirected_url
                else:
                    self.logger.warning("Could not get redirected URL")
                    return complex_profile_url
                
            except subprocess.TimeoutExpired:
                self.logger.error("Subprocess timed out")
                return complex_profile_url
            except Exception as e:
                self.logger.error(f"Subprocess execution error: {str(e)}")
                return complex_profile_url
            finally:
                # Clean up temporary file
                import os
                try:
                    os.unlink(script_path)
                except:
                    pass
                
        except Exception as e:
            self.logger.error(f"Failed to get redirected profile URL: {str(e)}")
            return complex_profile_url

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
                
                # Step 2: Get user profile URL and navigate to user's reels page
                user_profile_url = basic_data.get('user_profile_url')
                if not user_profile_url:
                    self.logger.error("Could not find user profile URL")
                    # Build basic result without views
                    reel_data = {
                        'url': url,
                        'user_posted': basic_data.get('user_name', ''),
                        'description': basic_data.get('description', ''),
                        'hashtags': self.extract_hashtags(basic_data.get('description', '')),
                        'num_comments': basic_data.get('comments'),
                        'shares': basic_data.get('shares'),
                        'views': None,
                        'video_url': basic_data.get('video_url', ''),
                        'user_profile_url': None,
                        'post_id': reel_id,
                        'views_source': 'no_user_profile'
                    }
                    return reel_data
                
                # Convert to reels page URL
                if '/profile.php' in user_profile_url:
                    # Handle complex profile URLs
                    self.logger.info("Complex profile URL detected, getting redirected URL...")
                    clean_profile_url = self.get_redirected_profile_url(user_profile_url)
                    if clean_profile_url:
                        user_profile_url = clean_profile_url
                        self.logger.info(f"Redirected to: {user_profile_url}")
                    else:
                        self.logger.warning("Could not get redirected URL, using original")
                
                # Ensure it's a reels page URL
                if not user_profile_url.endswith('/reels/'):
                    user_profile_url = user_profile_url.rstrip('/') + '/reels/'
                
                self.logger.info("=" * 50)
                self.logger.info("STEP 2: NAVIGATING TO USER'S REELS PAGE")
                self.logger.info(f"User reels URL: {user_profile_url}")
                self.logger.info("=" * 50)
                
                # Navigate to user's reels page
                try:
                    page.goto(user_profile_url, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(3000)
                    self.logger.info("Successfully navigated to user's reels page")
                except Exception as e:
                    self.logger.error(f"Failed to navigate to user's reels page: {str(e)}")
                    # Build result without views
                    reel_data = {
                        'url': url,
                        'user_posted': basic_data.get('user_name', ''),
                        'description': basic_data.get('description', ''),
                        'hashtags': self.extract_hashtags(basic_data.get('description', '')),
                        'num_comments': basic_data.get('comments'),
                        'shares': basic_data.get('shares'),
                        'views': None,
                        'video_url': basic_data.get('video_url', ''),
                        'user_profile_url': user_profile_url,
                        'post_id': reel_id,
                        'views_source': 'navigation_failed'
                    }
                    return reel_data
                
                # Step 3: Find the specific reel and extract its views
                self.logger.info("Searching for reel in user's reels page...")
                
                target_reel_id = reel_id
                views = None
                max_scroll_attempts = 15  # Limit scrolling to prevent infinite loops
                
                for scroll_attempt in range(max_scroll_attempts):
                    try:
                        # Find all reels on the current page
                        reels = page.query_selector_all('a[href*="/reel/"]')
                        
                        # Quickly check if our target reel is in the current page
                        target_reel_found = False
                        target_reel_url = None
                        
                        for reel in reels:
                            try:
                                href = reel.get_attribute('href')
                                if href and target_reel_id in href:
                                    target_reel_url = "https://web.facebook.com" + href if href.startswith('/') else href
                                    target_reel_found = True
                                    self.logger.info(f"Found target reel: {target_reel_url}")
                                    break
                            except Exception as e:
                                continue
                        
                        if target_reel_found and target_reel_url:
                            # Extract views from the target reel on current page
                            try:
                                # Find the target reel element and extract views from it
                                target_reel_element = None
                                for reel in reels:
                                    try:
                                        href = reel.get_attribute('href')
                                        if href and target_reel_id in href:
                                            target_reel_element = reel
                                            break
                                    except Exception as e:
                                        continue
                                
                                if target_reel_element:
                                    # Extract views from the target reel element
                                    views_data = page.evaluate('''(targetReelElement) => {
                                        // Get the number directly from the a tag and its span
                                        const aTag = targetReelElement;
                                        if (!aTag) return null;
                                        
                                        // Look for span elements inside the a tag
                                        const spans = aTag.querySelectorAll('span');
                                        for (const span of spans) {
                                            const text = span.textContent.trim();
                                            // Look for numbers (including K, M suffixes)
                                            const match = text.match(/(\\d+(\\.\\d+)?[KMkm]?)/);
                                            if (match) {
                                                return match[1];
                                            }
                                        }
                                        
                                        // If no numbers found in spans, check the a tag itself
                                        const aTagText = aTag.textContent.trim();
                                        const match = aTagText.match(/(\\d+(\\.\\d+)?[KMkm]?)/);
                                        if (match) {
                                            return match[1];
                                        }
                                        
                                        return null;
                                    }''', target_reel_element)
                                    
                                    if views_data:
                                        views = views_data
                                        self.logger.info(f"Extracted views: {views}")
                                    else:
                                        self.logger.warning("Could not extract views from target reel")
                                else:
                                    self.logger.warning("Could not find target reel element")
                                
                                break  # Exit the scroll loop since we found our target
                                
                            except Exception as e:
                                self.logger.error(f"Error extracting views from target reel: {str(e)}")
                                break
                        
                        else:
                            # Target reel not found on current page, try to scroll/load more
                            # Try different scrolling methods
                            try:
                                # Method 1: Scroll down
                                page.evaluate('window.scrollBy(0, 1000)')
                                page.wait_for_timeout(2000)
                                
                                # Method 2: Look for "See more" or "Load more" button
                                load_more_button = page.query_selector('button:has-text("See more"), button:has-text("Load more"), [aria-label*="See more"], [aria-label*="Load more"]')
                                if load_more_button:
                                    load_more_button.click()
                                    page.wait_for_timeout(3000)
                                
                                # Method 3: Look for pagination or next page
                                next_button = page.query_selector('a[aria-label*="Next"], a[aria-label*="next"], button[aria-label*="Next"], button[aria-label*="next"]')
                                if next_button:
                                    next_button.click()
                                    page.wait_for_timeout(3000)
                                    
                            except Exception as e:
                                self.logger.warning(f"Error during scrolling: {str(e)}")
                                break  # Exit if scrolling fails
                                
                    except Exception as e:
                        self.logger.error(f"Error during scroll attempt {scroll_attempt + 1}: {str(e)}")
                        if "Target page, context or browser has been closed" in str(e):
                            self.logger.error("Browser was closed unexpectedly, stopping search")
                            break
                        continue
                
                if not views:
                    self.logger.warning(f"Could not find target reel after {max_scroll_attempts} scroll attempts")
                
                # Build final result
                reel_data = {
                    'url': url,
                    'user_posted': basic_data.get('user_name', ''),
                    'description': basic_data.get('description', ''),
                    'hashtags': self.extract_hashtags(basic_data.get('description', '')),
                    'num_comments': basic_data.get('comments'),
                    'shares': basic_data.get('shares'),
                    'likes': basic_data.get('likes'),
                    'views': views,
                    'video_url': basic_data.get('video_url', ''),
                    'user_profile_url': user_profile_url,
                    'post_id': reel_id,
                    'views_source': 'user_reels_page' if views else 'not_found'
                }
                
                self.logger.info("=" * 50)
                self.logger.info("SCRAPING COMPLETED")
                self.logger.info(f"Views: {views}, Comments: {reel_data.get('num_comments')}, Shares: {reel_data.get('shares')}, Likes: {reel_data.get('likes')}")
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

    def get_reel_data(self, url):
        """Main method - uses authenticated scraping if cookies available, otherwise public scraping"""
        if self.use_cookies and self.cookies:
            self.logger.info("Using authenticated scraping")
            return self.get_reel_data_authenticated(url)
        else:
            self.logger.info("Using public scraping (no authentication)")
            return self.get_reel_data_public(url)

    def get_reel_data_authenticated(self, url):
        """Scrape Facebook Reel with authentication following the exact flow: reel page -> user profile -> views"""
        self.logger.info(f"Scraping reel with authentication: {url}")
        reel_id = self.extract_reel_id(url)
        
        browser = None
        context = None
        page = None
        
        try:
            with sync_playwright() as p:
                # Step 1: Navigate to the reel page and extract basic data
                self.logger.info("=" * 50)
                self.logger.info("STEP 1: EXTRACTING BASIC DATA FROM REEL PAGE (Authenticated)")
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
                
                context = browser.new_context()
                
                # Add cookies for authentication
                cookies_list = [{"name": k, "value": v, "domain": ".facebook.com", "path": "/"} for k, v in self.cookies.items()]
                context.add_cookies(cookies_list)
                
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
                
                # Step 2: Get user profile URL and navigate to user's reels page
                user_profile_url = basic_data.get('user_profile_url')
                if not user_profile_url:
                    self.logger.error("Could not find user profile URL")
                    # Build basic result without views
                    reel_data = {
                        'url': url,
                        'user_posted': basic_data.get('user_name', ''),
                        'description': basic_data.get('description', ''),
                        'hashtags': self.extract_hashtags(basic_data.get('description', '')),
                        'num_comments': basic_data.get('comments'),
                        'shares': basic_data.get('shares'),
                        'views': None,
                        'video_url': basic_data.get('video_url', ''),
                        'user_profile_url': None,
                        'post_id': reel_id,
                        'views_source': 'no_user_profile'
                    }
                    return reel_data
                
                # Convert to reels page URL
                if '/profile.php' in user_profile_url:
                    # Handle complex profile URLs
                    self.logger.info("Complex profile URL detected, getting redirected URL...")
                    clean_profile_url = self.get_redirected_profile_url(user_profile_url)
                    if clean_profile_url:
                        user_profile_url = clean_profile_url
                        self.logger.info(f"Redirected to: {user_profile_url}")
                    else:
                        self.logger.warning("Could not get redirected URL, using original")
                
                # Ensure it's a reels page URL
                if not user_profile_url.endswith('/reels/'):
                    user_profile_url = user_profile_url.rstrip('/') + '/reels/'
                
                self.logger.info("=" * 50)
                self.logger.info("STEP 2: NAVIGATING TO USER'S REELS PAGE (Authenticated)")
                self.logger.info(f"User reels URL: {user_profile_url}")
                self.logger.info("=" * 50)
                
                # Navigate to user's reels page
                try:
                    page.goto(user_profile_url, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(3000)
                    self.logger.info("Successfully navigated to user's reels page")
                except Exception as e:
                    self.logger.error(f"Failed to navigate to user's reels page: {str(e)}")
                    # Build result without views
                    reel_data = {
                        'url': url,
                        'user_posted': basic_data.get('user_name', ''),
                        'description': basic_data.get('description', ''),
                        'hashtags': self.extract_hashtags(basic_data.get('description', '')),
                        'num_comments': basic_data.get('comments'),
                        'shares': basic_data.get('shares'),
                        'views': None,
                        'video_url': basic_data.get('video_url', ''),
                        'user_profile_url': user_profile_url,
                        'post_id': reel_id,
                        'views_source': 'navigation_failed'
                    }
                    return reel_data
                
                # Step 3: Find the specific reel and extract its views
                self.logger.info("Searching for reel in user's reels page...")
                
                target_reel_id = reel_id
                views = None
                max_scroll_attempts = 15  # Limit scrolling to prevent infinite loops
                
                for scroll_attempt in range(max_scroll_attempts):
                    try:
                        # Find all reels on the current page
                        reels = page.query_selector_all('a[href*="/reel/"]')
                        
                        # Quickly check if our target reel is in the current page
                        target_reel_found = False
                        target_reel_url = None
                        
                        for reel in reels:
                            try:
                                href = reel.get_attribute('href')
                                if href and target_reel_id in href:
                                    target_reel_url = "https://web.facebook.com" + href if href.startswith('/') else href
                                    target_reel_found = True
                                    self.logger.info(f"Found target reel: {target_reel_url}")
                                    break
                            except Exception as e:
                                continue
                        
                        if target_reel_found and target_reel_url:
                            # Extract views from the target reel on current page
                            try:
                                # Find the target reel element and extract views from it
                                target_reel_element = None
                                for reel in reels:
                                    try:
                                        href = reel.get_attribute('href')
                                        if href and target_reel_id in href:
                                            target_reel_element = reel
                                            break
                                    except Exception as e:
                                        continue
                                
                                if target_reel_element:
                                    # Extract views from the target reel element
                                    views_data = page.evaluate('''(targetReelElement) => {
                                        // Get the number directly from the a tag and its span
                                        const aTag = targetReelElement;
                                        if (!aTag) return null;
                                        
                                        // Look for span elements inside the a tag
                                        const spans = aTag.querySelectorAll('span');
                                        for (const span of spans) {
                                            const text = span.textContent.trim();
                                            // Look for numbers (including K, M suffixes)
                                            const match = text.match(/(\\d+(\\.\\d+)?[KMkm]?)/);
                                            if (match) {
                                                return match[1];
                                            }
                                        }
                                        
                                        // If no numbers found in spans, check the a tag itself
                                        const aTagText = aTag.textContent.trim();
                                        const match = aTagText.match(/(\\d+(\\.\\d+)?[KMkm]?)/);
                                        if (match) {
                                            return match[1];
                                        }
                                        
                                        return null;
                                    }''', target_reel_element)
                                    
                                    if views_data:
                                        views = views_data
                                        self.logger.info(f"Extracted views: {views}")
                                    else:
                                        self.logger.warning("Could not extract views from target reel")
                                else:
                                    self.logger.warning("Could not find target reel element")
                                
                                break  # Exit the scroll loop since we found our target
                                
                            except Exception as e:
                                self.logger.error(f"Error extracting views from target reel: {str(e)}")
                                break
                        
                        else:
                            # Target reel not found on current page, try to scroll/load more
                            # Try different scrolling methods
                            try:
                                # Method 1: Scroll down
                                page.evaluate('window.scrollBy(0, 1000)')
                                page.wait_for_timeout(2000)
                                
                                # Method 2: Look for "See more" or "Load more" button
                                load_more_button = page.query_selector('button:has-text("See more"), button:has-text("Load more"), [aria-label*="See more"], [aria-label*="Load more"]')
                                if load_more_button:
                                    load_more_button.click()
                                    page.wait_for_timeout(3000)
                                
                                # Method 3: Look for pagination or next page
                                next_button = page.query_selector('a[aria-label*="Next"], a[aria-label*="next"], button[aria-label*="Next"], button[aria-label*="next"]')
                                if next_button:
                                    next_button.click()
                                    page.wait_for_timeout(3000)
                                    
                            except Exception as e:
                                self.logger.warning(f"Error during scrolling: {str(e)}")
                                break  # Exit if scrolling fails
                                
                    except Exception as e:
                        self.logger.error(f"Error during scroll attempt {scroll_attempt + 1}: {str(e)}")
                        if "Target page, context or browser has been closed" in str(e):
                            self.logger.error("Browser was closed unexpectedly, stopping search")
                            break
                        continue
                
                if not views:
                    self.logger.warning(f"Could not find target reel after {max_scroll_attempts} scroll attempts")
                
                # Build final result
                reel_data = {
                    'url': url,
                    'user_posted': basic_data.get('user_name', ''),
                    'description': basic_data.get('description', ''),
                    'hashtags': self.extract_hashtags(basic_data.get('description', '')),
                    'num_comments': basic_data.get('comments'),
                    'shares': basic_data.get('shares'),
                    'likes': basic_data.get('likes'),
                    'views': views,
                    'video_url': basic_data.get('video_url', ''),
                    'user_profile_url': user_profile_url,
                    'post_id': reel_id,
                    'views_source': 'user_reels_page' if views else 'not_found'
                }
                
                self.logger.info("=" * 50)
                self.logger.info("SCRAPING COMPLETED (Authenticated)")
                self.logger.info(f"Views: {views}, Comments: {reel_data.get('num_comments')}, Shares: {reel_data.get('shares')}, Likes: {reel_data.get('likes')}")
                self.logger.info("=" * 50)
                
                return reel_data
                
        except Exception as e:
            self.logger.error(f"Authenticated scraping failed: {str(e)}")
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

    def get_views_from_user_reels_page(self, user_profile_url, target_video_url):
        """Open the user's reels page, find the reel with the given video URL, and extract its views."""
        self.logger.info("=" * 60)
        self.logger.info("STARTING ACCURATE VIEWS EXTRACTION")
        self.logger.info(f"User Profile URL: {user_profile_url}")
        self.logger.info(f"Target Video URL: {target_video_url}")
        self.logger.info("=" * 60)
        
        try:
            # Use subprocess to avoid async/sync conflicts
            import subprocess
            import sys
            
            # Create a script to extract video links from user's reels page
            script_content = f'''
import asyncio
from playwright.async_api import async_playwright
import re
import json

async def extract_video_links_from_reels():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={{'width': 1920, 'height': 1080}}
            )
            page = await context.new_page()
            
            # Navigate to user's reels page
            print(f"NAVIGATING:{{user_profile_url}}")
            await page.goto("{user_profile_url}", wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            print(f"LOADED_PAGE:{{page.url}}")

            video_links = []
            total_reels_checked = 0
            
            for scroll_attempt in range(10):  # Scroll up to 10 times
                print(f"SCROLL_ATTEMPT:{{scroll_attempt + 1}}")
                
                # Find all reel links on the current page
                reels = await page.query_selector_all('a[href*="/reel/"]')
                print(f"FOUND_REELS:{{len(reels)}}")
                
                if not reels:
                    print("NO_REELS_FOUND")
                    await page.evaluate('window.scrollBy(0, 1000)')
                    await page.wait_for_timeout(2000)
                    continue
                
                for reel_index, reel in enumerate(reels):
                    try:
                        href = await reel.get_attribute('href')
                        reel_url = "https://web.facebook.com" + href if href and href.startswith('/') else href
                        
                        if not reel_url:
                            print(f"INVALID_URL:{{reel_index + 1}}")
                            continue
                        
                        total_reels_checked += 1
                        print(f"CHECKING_REEL:{{total_reels_checked}}:{{reel_url}}")
                        
                        # Open reel in new tab
                        new_page = await context.new_page()
                        await new_page.goto(reel_url, wait_until='networkidle', timeout=20000)
                        await new_page.wait_for_timeout(2000)
                        
                        # Extract video URL from this reel
                        video = await new_page.query_selector('video')
                        if video:
                            video_src = await video.get_attribute('src')
                            if video_src:
                                print(f"REEL_VIDEO_URL:{{total_reels_checked}}:{{video_src}}")
                                video_links.append({{
                                    'reel_url': reel_url,
                                    'video_url': video_src,
                                    'reel_number': total_reels_checked
                                }})
                            else:
                                print(f"NO_VIDEO_SRC:{{total_reels_checked}}")
                        else:
                            print(f"NO_VIDEO_ELEMENT:{{total_reels_checked}}")
                        
                        await new_page.close()
                        
                    except Exception as e:
                        print(f"ERROR_REEL:{{total_reels_checked}}:{{str(e)}}")
                        try:
                            await new_page.close()
                        except:
                            pass
                        continue
                
                # If we found some video links, we can stop scrolling
                if video_links:
                    print(f"FOUND_VIDEO_LINKS:{{len(video_links)}}")
                    break
                
                # Scroll down to load more reels
                print("SCROLLING_DOWN")
                await page.evaluate('window.scrollBy(0, 1000)')
                await page.wait_for_timeout(2000)
            
            await page.close()
            await context.close()
            await browser.close()
            
            # Return the video links as JSON
            print(f"VIDEO_LINKS_JSON:{{json.dumps(video_links)}}")
            print(f"TOTAL_REELS_CHECKED:{{total_reels_checked}}")
            
    except Exception as e:
        print(f"ERROR:{{str(e)}}")
        print("VIDEO_LINKS_JSON:[]")

asyncio.run(extract_video_links_from_reels())
'''
            
            # Write script to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            try:
                # Run the script
                result = subprocess.run([sys.executable, script_path], 
                                      capture_output=True, text=True, timeout=120)
                
                # Parse output
                output_lines = result.stdout.strip().split('\n')
                video_links = []
                navigation_url = None
                loaded_url = None
                total_reels_checked = 0
                error = None
                
                for line in output_lines:
                    if line.startswith('NAVIGATING:'):
                        navigation_url = line.replace('NAVIGATING:', '').strip()
                        self.logger.info(f"Navigating to: {navigation_url}")
                    elif line.startswith('LOADED_PAGE:'):
                        loaded_url = line.replace('LOADED_PAGE:', '').strip()
                        self.logger.info(f"Successfully loaded page: {loaded_url}")
                    elif line.startswith('SCROLL_ATTEMPT:'):
                        scroll_num = line.replace('SCROLL_ATTEMPT:', '').strip()
                        self.logger.info(f"Scroll attempt {scroll_num}/10")
                    elif line.startswith('FOUND_REELS:'):
                        reel_count = line.replace('FOUND_REELS:', '').strip()
                        self.logger.info(f"Found {reel_count} reel links on current page")
                    elif line.startswith('NO_REELS_FOUND'):
                        self.logger.info("No reel links found, scrolling to load more...")
                    elif line.startswith('CHECKING_REEL:'):
                        parts = line.replace('CHECKING_REEL:', '').split(':', 1)
                        if len(parts) == 2:
                            reel_num = parts[0]
                            reel_url = parts[1]
                            total_reels_checked = int(reel_num)
                            self.logger.info(f"Checking reel {reel_num}: {reel_url}")
                    elif line.startswith('REEL_VIDEO_URL:'):
                        parts = line.replace('REEL_VIDEO_URL:', '').split(':', 1)
                        if len(parts) == 2:
                            reel_num = parts[0]
                            video_url = parts[1]
                            self.logger.info(f"Reel {reel_num} video URL: {video_url}")
                    elif line.startswith('NO_VIDEO_SRC:'):
                        reel_num = line.replace('NO_VIDEO_SRC:', '').strip()
                        self.logger.debug(f"Reel {reel_num}: No video source found")
                    elif line.startswith('NO_VIDEO_ELEMENT:'):
                        reel_num = line.replace('NO_VIDEO_ELEMENT:', '').strip()
                        self.logger.debug(f"Reel {reel_num}: No video element found")
                    elif line.startswith('ERROR_REEL:'):
                        parts = line.replace('ERROR_REEL:', '').split(':', 1)
                        if len(parts) == 2:
                            reel_num = parts[0]
                            error_msg = parts[1]
                            self.logger.error(f"Error checking reel {reel_num}: {error_msg}")
                    elif line.startswith('FOUND_VIDEO_LINKS:'):
                        link_count = line.replace('FOUND_VIDEO_LINKS:', '').strip()
                        self.logger.info(f"Found {link_count} video links, stopping scroll")
                    elif line.startswith('SCROLLING_DOWN'):
                        self.logger.info("Scrolling down to load more reels...")
                    elif line.startswith('VIDEO_LINKS_JSON:'):
                        json_data = line.replace('VIDEO_LINKS_JSON:', '').strip()
                        try:
                            video_links = json.loads(json_data)
                            self.logger.info(f"Successfully parsed {len(video_links)} video links")
                        except json.JSONDecodeError:
                            self.logger.error(f"Failed to parse video links JSON: {json_data}")
                            video_links = []
                    elif line.startswith('TOTAL_REELS_CHECKED:'):
                        reel_count = line.replace('TOTAL_REELS_CHECKED:', '').strip()
                        self.logger.info(f"Total reels checked: {reel_count}")
                    elif line.startswith('ERROR:'):
                        error = line.replace('ERROR:', '').strip()
                        self.logger.error(f"Subprocess error: {error}")
                
                if error:
                    self.logger.error(f"Subprocess error: {error}")
                    return []
                
                self.logger.info("=" * 60)
                self.logger.info("VIDEO LINKS EXTRACTION COMPLETED")
                self.logger.info(f"Found {len(video_links)} video links")
                for i, link in enumerate(video_links):
                    self.logger.info(f"  {i+1}. Reel {link['reel_number']}: {link['video_url']}")
                self.logger.info("=" * 60)
                
                return video_links
                
            finally:
                # Clean up temporary file
                import os
                try:
                    os.unlink(script_path)
                except:
                    pass
                
        except Exception as e:
            self.logger.error(f"Failed to extract video links from user's reels page: {str(e)}")
            return []

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