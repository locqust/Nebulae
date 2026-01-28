# utils/url_preview.py
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import traceback

def extract_urls_from_text(text):
    """
    Extract all URLs from text content.
    Returns a list of URLs found in the text.
    """
    if not text:
        return []
    
    # Regex to match URLs
    url_pattern = re.compile(r'(https?://[^\s<>"\'()]+|www\.[^\s<>"\'()]+)')
    matches = url_pattern.findall(text)
    
    # Normalize URLs (add http:// to www. links)
    urls = []
    for url in matches:
        if url.startswith('www.'):
            url = 'http://' + url
        urls.append(url)
    
    return urls


def fetch_url_preview(url, timeout=10):
    """
    Fetches Open Graph metadata from a URL.
    Returns a dict with: title, description, image_url, site_name, url
    Returns None if fetch fails.
    """
    try:
        # Normalize the URL
        parsed = urlparse(url)
        if not parsed.scheme:
            url = 'http://' + url
        
        # Set headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract Open Graph metadata
        og_data = {}
        
        # Try Open Graph tags first
        for meta in soup.find_all('meta', property=lambda x: x and x.startswith('og:')):
            property_name = meta.get('property', '').replace('og:', '')
            content = meta.get('content', '')
            if content:
                og_data[property_name] = content
        
        # Fallback to Twitter Card metadata
        if not og_data.get('title') or not og_data.get('description') or not og_data.get('image'):
            for meta in soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')}):
                name = meta.get('name', '').replace('twitter:', '')
                content = meta.get('content', '')
                if content and name not in og_data:
                    og_data[name] = content
        
        # Final fallback to standard meta tags and title
        if not og_data.get('title'):
            title_tag = soup.find('title')
            if title_tag:
                og_data['title'] = title_tag.string.strip() if title_tag.string else ''
        
        if not og_data.get('description'):
            desc_meta = soup.find('meta', attrs={'name': 'description'})
            if desc_meta:
                og_data['description'] = desc_meta.get('content', '')
        
        # Make image URL absolute
        image_url = og_data.get('image', '')
        if image_url and not image_url.startswith(('http://', 'https://')):
            image_url = urljoin(response.url, image_url)
            og_data['image'] = image_url
        
        # Return structured data
        return {
            'url': response.url,  # Use final URL after redirects
            'title': og_data.get('title', '')[:500],  # Limit length
            'description': og_data.get('description', '')[:1000],
            'image_url': og_data.get('image', '')[:500],
            'site_name': og_data.get('site_name', '')[:200]
        }
    
    except requests.exceptions.Timeout:
        print(f"Timeout fetching URL preview for: {url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL preview for {url}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching URL preview for {url}: {e}")
        traceback.print_exc()
        return None