from flask import Flask, request, jsonify
from scraper import FacebookReelScraper
import logging
import time
from typing import Optional
import threading
import concurrent.futures

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

def run_scraper_with_fallback(url: str):
    """Run scraper with smart fallback: authenticated -> public -> quick"""
    logger.info(f"Starting scraper with fallback for URL: {url}")
    
    # Try authenticated scraping first (with timeout)
    try:
        logger.info("Attempting authenticated scraping...")
        scraper_auth = FacebookReelScraper(use_cookies=True, auto_login=True)
        result = scraper_auth.get_reel_data(url)
        if result:
            logger.info("✅ Authenticated scraping successful")
            return result
    except Exception as e:
        logger.warning(f"Authenticated scraping failed: {str(e)}")
    
    # Try public scraping as fallback
    try:
        logger.info("Attempting public scraping...")
        scraper_public = FacebookReelScraper(use_cookies=False)
        result = scraper_public.get_reel_data(url)
        if result:
            logger.info("✅ Public scraping successful")
            return result
    except Exception as e:
        logger.warning(f"Public scraping failed: {str(e)}")
    
    # Try quick scraping as last resort
    try:
        logger.info("Attempting quick scraping...")
        scraper_quick = FacebookReelScraper(use_cookies=False)
        result = scraper_quick.quick_scrape(url)
        if result:
            logger.info("✅ Quick scraping successful")
            return result
    except Exception as e:
        logger.warning(f"Quick scraping failed: {str(e)}")
    
    logger.error("❌ All scraping methods failed")
    return None

def run_scraper_with_timeout(url: str, timeout: int = 60):
    """Run scraper with timeout using ThreadPoolExecutor"""
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_scraper_with_fallback, url)
            result = future.result(timeout=timeout)
            return result
    except concurrent.futures.TimeoutError:
        logger.error(f"Scraper timed out after {timeout} seconds")
        return None
    except Exception as e:
        logger.error(f"Scraper error: {str(e)}")
        return None

@app.route("/", methods=["GET"])
def root():
    """Root endpoint with API information"""
    return jsonify({
        "message": "Facebook Reel Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "/search": "POST - Search and scrape Facebook Reel data",
            "/health": "GET - Health check endpoint"
        }
    })

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "API is running"})

@app.route("/test", methods=["GET"])
def test_endpoint():
    """Simple test endpoint to verify API is working"""
    return jsonify({
        "status": "success",
        "message": "API is working correctly",
        "timestamp": "2025-06-19T22:45:00Z"
    })

@app.route("/search", methods=["POST"])
def search_reel():
    """
    Search and scrape Facebook Reel data
    
    This endpoint takes a Facebook Reel URL and returns comprehensive data including:
    - Basic reel information (description, user, date posted)
    - Video URL and thumbnail
    - Engagement metrics (views, likes, comments)
    - User profile information
    - Accurate views extraction from user's reels page
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "Missing URL in request body",
                "message": "Please provide a 'url' field in the JSON body"
            }), 400
        
        url = data['url']
        logger.info(f"Received search request for URL: {url}")
        
        # Run scraper with timeout
        result = run_scraper_with_timeout(url, timeout=60)
        
        if result:
            logger.info("Successfully scraped reel data")
            return jsonify({
                "success": True,
                "data": result,
                "message": "Reel data extracted successfully"
            })
        else:
            logger.warning("Failed to extract reel data")
            return jsonify({
                "success": False,
                "error": "Failed to extract reel data",
                "message": "The scraper could not extract data from the provided URL"
            }), 400
            
    except Exception as e:
        logger.error(f"Error processing search request: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "An error occurred while processing the request"
        }), 500

@app.route("/search/public", methods=["POST"])
def search_reel_public():
    """
    Search and scrape Facebook Reel data using public scraping (no authentication)
    
    This endpoint forces the use of public scraping without requiring cookies.
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "Missing URL in request body",
                "message": "Please provide a 'url' field in the JSON body"
            }), 400
        
        url = data['url']
        logger.info(f"Received public search request for URL: {url}")
        
        # Run scraper with timeout
        result = run_scraper_with_timeout(url, timeout=60)
        
        if result:
            logger.info("Successfully scraped reel data (public mode)")
            return jsonify({
                "success": True,
                "data": result,
                "message": "Reel data extracted successfully using public scraping"
            })
        else:
            logger.warning("Failed to extract reel data (public mode)")
            return jsonify({
                "success": False,
                "error": "Failed to extract reel data",
                "message": "The scraper could not extract data from the provided URL using public mode"
            }), 400
            
    except Exception as e:
        logger.error(f"Error processing public search request: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "An error occurred while processing the request"
        }), 500

@app.route("/search/quick", methods=["POST"])
def search_reel_quick():
    """
    Quick search and scrape Facebook Reel data (basic extraction only)
    
    This endpoint performs basic data extraction without the complex video links
    extraction that can cause timeouts.
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "Missing URL in request body",
                "message": "Please provide a 'url' field in the JSON body"
            }), 400
        
        url = data['url']
        logger.info(f"Received quick search request for URL: {url}")
        
        # Run scraper with shorter timeout for quick mode
        result = run_scraper_with_timeout(url, timeout=30)
        
        if result:
            logger.info("Successfully scraped reel data (quick mode)")
            return jsonify({
                "success": True,
                "data": result,
                "message": "Reel data extracted successfully using quick mode"
            })
        else:
            logger.warning("Failed to extract reel data (quick mode)")
            return jsonify({
                "success": False,
                "error": "Failed to extract reel data",
                "message": "The scraper could not extract data from the provided URL"
            }), 400
            
    except Exception as e:
        logger.error(f"Error processing quick search request: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "An error occurred while processing the request"
        }), 500

if __name__ == "__main__":
    # Run the Flask app
    app.run(
        host="0.0.0.0",
        port=8000,
        debug=True,
        threaded=True
    ) 