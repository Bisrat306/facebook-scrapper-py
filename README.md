# Facebook Reel Scraper API

A Flask-based API for scraping Facebook Reels data with accurate views extraction and comprehensive engagement metrics.

## Features

- **Automatic Login**: Automatically logs into Facebook using credentials and creates cookies for future use
- **Cookie Management**: Validates and refreshes cookies automatically
- **Multiple Scraping Modes**: 
  - Authenticated scraping (with login)
  - Public scraping (without login)
  - Quick scraping (basic data only)
- **Comprehensive Data Extraction**:
  - Video URL
  - Description and hashtags
  - User information
  - Engagement metrics (likes, comments, shares, views)
  - Timestamps
  - Metadata
- **Accurate Views Extraction**: Navigate to user's reels page to get precise view counts
- **Smart Fallback System**: Authenticated → Public → Quick scraping with automatic fallback
- **Enhanced Engagement Metrics**: Extract likes, comments, shares with intelligent parsing
- **Dual Mode Support**: Authenticated scraping (with cookies) and public scraping (no login required)
- **Timeout Protection**: Built-in timeout handling to prevent hanging requests
- **Detailed Logging**: Comprehensive logging for debugging and monitoring

## Installation

1. **Clone the repository**:
```bash
git clone <repository-url>
cd facebook-scraper-py
```

2. **Create virtual environment (recommended)**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
playwright install chromium
```

4. **Set up environment variables** (for auto-login):
```bash
# Create .env file
echo "FACEBOOK_EMAIL=your_email@example.com" > .env
echo "FACEBOOK_PASSWORD=your_password" >> .env
```

## Usage

### Starting the API Server

```bash
python main.py
```

The API will be available at `http://localhost:8000`

### API Endpoints

#### 1. Health Check
```bash
GET /health
```

#### 2. API Information
```bash
GET /
```

#### 3. Search Reel (Smart Fallback)
```bash
POST /search
Content-Type: application/json

{
    "url": "https://web.facebook.com/reel/686568827564173"
}
```

#### 4. Search Reel (Public Only)
```bash
POST /search/public
Content-Type: application/json

{
    "url": "https://web.facebook.com/reel/686568827564173"
}
```

#### 5. Quick Search (Fast Mode)
```bash
POST /search/quick
Content-Type: application/json

{
    "url": "https://web.facebook.com/reel/686568827564173"
}
```

### Example Usage

#### Using curl:
```bash
# Test the main search endpoint (smart fallback)
curl -X POST "http://localhost:8000/search" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://web.facebook.com/reel/686568827564173"}'

# Test the public search endpoint
curl -X POST "http://localhost:8000/search/public" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://web.facebook.com/reel/686568827564173"}'

# Test the quick search endpoint
curl -X POST "http://localhost:8000/search/quick" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://web.facebook.com/reel/686568827564173"}'
```

#### Using Python requests:
```python
import requests

# Search with smart fallback (authenticated → public → quick)
response = requests.post(
    "http://localhost:8000/search",
    json={"url": "https://web.facebook.com/reel/686568827564173"}
)
result = response.json()

# Search without authentication
response = requests.post(
    "http://localhost:8000/search/public",
    json={"url": "https://web.facebook.com/reel/686568827564173"}
)
result = response.json()

# Quick search for fast results
response = requests.post(
    "http://localhost:8000/search/quick",
    json={"url": "https://web.facebook.com/reel/686568827564173"}
)
result = response.json()
```

### Response Format

```json
{
    "success": true,
    "data": {
        "url": "https://web.facebook.com/reel/686568827564173",
        "user_posted": "Username",
        "description": "Reel description...",
        "hashtags": ["#hashtag1", "#hashtag2"],
        "views": 1200,
        "likes": 15800,
        "num_comments": 55,
        "shares": 201,
        "date_posted": "2 hours ago",
        "video_url": "https://video-url-here.com/video.mp4",
        "thumbnail": "https://thumbnail-url-here.com/thumb.jpg",
        "user_profile_url": "https://web.facebook.com/username/reels/",
        "views_source": "user_reels_page",
        "post_id": "686568827564173"
    },
    "message": "Reel data extracted successfully"
}
```

## Command Line Usage

For direct command-line usage without the API:

```bash
python newmain.py "https://web.facebook.com/reel/686568827564173"
```

This will run the scraper with smart fallback and display results directly.

## Testing

### Test the API:
```bash
# Start the server
python main.py

# In another terminal, test with curl
curl -X POST "http://localhost:8000/search" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://web.facebook.com/reel/686568827564173"}'
```

### Test the scraper directly:
```bash
python newmain.py "https://web.facebook.com/reel/686568827564173"
```

## Configuration

### Environment Variables

Create a `.env` file for configuration:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

# Scraper Configuration
USE_COOKIES=true
COOKIE_FILE=facebook_cookies.json
```

### Cookie Setup (Optional)

For authenticated scraping, create a `facebook_cookies.json` file:

```json
{
    "c_user": "your_user_id",
    "xs": "your_session_token",
    "datr": "your_datr_token",
    "fr": "your_fr_token"
}
```

## Scraping Modes

### 1. Smart Fallback (Default)
- **Authenticated scraping** first (if cookies available)
- **Public scraping** as fallback
- **Quick scraping** as last resort
- **Timeout protection** at each step

### 2. Public Only
- Forces public scraping without authentication
- Useful when cookies are invalid or unavailable

### 3. Quick Mode
- Basic data extraction only
- Faster response times (30s timeout)
- Skips complex video URL extraction

## Troubleshooting

### Common Issues

1. **Playwright not installed**:
   ```bash
   playwright install chromium
   ```

2. **Missing dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Cookie authentication failing**:
   - Ensure `facebook_cookies.json` exists and is valid
   - Try using the `/search/public` endpoint instead
   - The smart fallback will automatically try public scraping

4. **Scraper hanging or timing out**:
   - The new timeout system should prevent this
   - Try the `/search/quick` endpoint for faster results
   - Check logs for detailed error messages

5. **Video URL extraction failing**:
   - Facebook may have changed their page structure
   - Try different scraping modes
   - Check the logs for detailed error messages

### Performance Tips

- **For speed**: Use `/search/quick` endpoint
- **For reliability**: Use `/search` endpoint (smart fallback)
- **For public content**: Use `/search/public` endpoint
- **For debugging**: Check the detailed logs in the console

## License

This project is for educational purposes. Please respect Facebook's terms of service and use responsibly. 