#!/usr/bin/env python3

import sys
import json
import logging
import subprocess
import time
from scraper import FacebookReelScraper

def setup_logger():
    """Setup logger with timestamp and formatting"""
    logger = logging.getLogger('FacebookReelScraper')
    logger.setLevel(logging.INFO)
    
    # Create console handler with formatting
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(ch)
    return logger

def install_playwright_browsers():
    """Install Playwright browsers"""
    logger = logging.getLogger('FacebookReelScraper')
    logger.info("Installing Playwright browsers...")
    try:
        subprocess.run(['playwright', 'install', 'chromium'], check=True, capture_output=True)
        logger.info("Playwright browsers installed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Playwright browsers: {str(e)}")
        logger.info("Continuing anyway - browsers might already be installed")
    except FileNotFoundError:
        logger.warning("Playwright not found in PATH. Make sure it's installed: pip install playwright")
        logger.info("Continuing anyway - browsers might already be installed")

def main():
    logger = setup_logger()
    logger.info("Starting Facebook Reel Scraper (Command Line)")
    
    # Install Playwright browsers if not already installed
    install_playwright_browsers()
    
    if len(sys.argv) != 2:
        logger.error("Invalid number of arguments")
        print("Usage: python newmain.py <facebook_reel_url>")
        print("Example: python newmain.py \"https://web.facebook.com/reel/686568827564173\"")
        sys.exit(1)
        
    url = sys.argv[1]
    logger.info(f"Processing URL: {url}")
    
    # Initialize scraper with both modes - use single instances
    logger.info("Initializing scrapers...")
    scraper_authenticated = FacebookReelScraper(use_cookies=True, auto_login=True)
    scraper_public = FacebookReelScraper(use_cookies=False)
    
    try:
        # Try authenticated scraping first
        logger.info("Attempting authenticated scraping...")
        start_time = time.time()
        reel_data = scraper_authenticated.get_reel_data(url)
        auth_time = time.time() - start_time
        
        if reel_data:
            logger.info(f"✅ Successfully scraped reel data (authenticated) in {auth_time:.2f}s")
            print("\n" + "="*60)
            print("SCRAPED DATA (Authenticated)")
            print("="*60)
            print(json.dumps(reel_data, indent=2))
        else:
            logger.warning(f"Authenticated scraping failed after {auth_time:.2f}s, trying public scraping...")
            
            # Try public scraping as fallback
            start_time = time.time()
            reel_data = scraper_public.get_reel_data(url)
            public_time = time.time() - start_time
            
            if reel_data:
                logger.info(f"✅ Successfully scraped reel data (public) in {public_time:.2f}s")
                print("\n" + "="*60)
                print("SCRAPED DATA (Public)")
                print("="*60)
                print(json.dumps(reel_data, indent=2))
            else:
                logger.warning(f"Public scraping also failed after {public_time:.2f}s, trying quick scrape...")
                
                # Try quick scrape as last resort
                start_time = time.time()
                reel_data = scraper_public.quick_scrape(url)
                quick_time = time.time() - start_time
                
                if reel_data:
                    logger.info(f"✅ Successfully scraped reel data (quick mode) in {quick_time:.2f}s")
                    print("\n" + "="*60)
                    print("SCRAPED DATA (Quick Mode)")
                    print("="*60)
                    print(json.dumps(reel_data, indent=2))
                else:
                    logger.error(f"❌ All scraping methods failed")
                    print("\n" + "="*60)
                    print("SCRAPING FAILED")
                    print("="*60)
                    print("All scraping methods failed:")
                    print(f"- Authenticated: Failed after {auth_time:.2f}s")
                    print(f"- Public: Failed after {public_time:.2f}s")
                    print(f"- Quick: Failed after {quick_time:.2f}s")
                    print("\nPossible reasons:")
                    print("- URL might be invalid or private")
                    print("- Facebook might be blocking the scraper")
                    print("- Network connectivity issues")
                    print("- Reel might require login to view")
                    sys.exit(1)
        
        # Print summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        if reel_data:
            print(f"URL: {reel_data.get('url', 'N/A')}")
            print(f"User: {reel_data.get('user_posted', 'N/A')}")
            print(f"Description: {reel_data.get('description', 'N/A')[:100]}...")
            print(f"Views: {reel_data.get('views', 'N/A')}")
            print(f"Comments: {reel_data.get('num_comments', 'N/A')}")
            print(f"Video URL: {reel_data.get('video_url', 'N/A')[:100]}...")
            print(f"User Profile: {reel_data.get('user_profile_url', 'N/A')}")
            print(f"Views Source: {reel_data.get('views_source', 'N/A')}")
            print(f"Hashtags: {reel_data.get('hashtags', [])}")
            print(f"Scraping Time: {auth_time if 'auth_time' in locals() else public_time if 'public_time' in locals() else quick_time:.2f}s")
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        print("\nScraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error occurred: {str(e)}")
        print(f"\nError: {str(e)}")
        print("\nIf you're seeing subprocess errors, try:")
        print("1. Restarting the script")
        print("2. Checking your internet connection")
        print("3. Verifying the URL is accessible")
        sys.exit(1)
    finally:
        logger.info("Scraping process completed")

if __name__ == "__main__":
    main() 