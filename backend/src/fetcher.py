import os
import requests
import hashlib
import logging

logger = logging.getLogger(__name__)

USER_AGENT = "Hackathon-Recruiter-Bot/1.0"

from typing import Tuple, Optional

def fetch_page(url: str, raw_pages_dir: str) -> Tuple[Optional[str], str, str]:
    """Fetches a page, checking Content-Type (HTML or PDF), and saves a raw snapshot."""
    try:
        logger.info(f"Fetching URL: {url}")
        with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(5, 10), verify=False, stream=True) as response:
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
            os.makedirs(raw_pages_dir, exist_ok=True)
            
            # Handle PDF
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                filepath = os.path.join(raw_pages_dir, f"{url_hash}.pdf")
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"Saved PDF to {filepath}")
                return filepath, "success", "pdf"
            
            # Allow empty Content-Type gracefully, but check if explicit
            if content_type and not any(t in content_type for t in ['text/html', 'text/plain', 'application/xhtml+xml']):
                logger.warning(f"Skipping non-HTML/PDF content type: {content_type} for {url}")
                return None, "non_html", ""
            
            # Improve decoding handling using apparent_encoding
            if response.encoding == 'ISO-8859-1' or not response.encoding:
                response.encoding = response.apparent_encoding
                
            try:
                html_content = response.text
            except Exception:
                html_content = response.content.decode('utf-8', errors='replace')
        
        # Save raw HTML
        filepath = os.path.join(raw_pages_dir, f"{url_hash}.html")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        logger.info(f"Saved raw HTML to {filepath}")
        return html_content, "success", "html"
        
    except requests.Timeout:
        logger.error(f"Timeout fetching {url}")
        return None, "timeout", ""
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None, "fetch_error", ""

def fetch_github_api(url: str) -> dict | list | None:
    """Fetches public JSON data from the GitHub API."""
    try:
        logger.info(f"Fetching GitHub API: {url}")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.v3+json"}
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch GitHub API {url}: {e}")
        return None

def fetch_github_profile_html(username: str) -> str | None:
    """Fetches the raw HTML of a GitHub profile to scrape pinned repos."""
    try:
        url = f"https://github.com/{username}"
        logger.info(f"Fetching GitHub Profile HTML: {url}")
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10, verify=False)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Failed to fetch GitHub HTML for {username}: {e}")
        return None