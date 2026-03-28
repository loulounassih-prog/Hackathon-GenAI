import os
import sys
import json
import logging

# Ensure absolute imports work when run as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.src.fetcher import fetch_page, fetch_github_api, fetch_github_profile_html
from backend.src.extractor import extract_signals, extract_github_pinned_repos
from backend.src.normalizer import normalize_candidate, normalize_github

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
INPUT_FILE = os.path.join(DATA_DIR, 'input_urls.json')
OUTPUT_FILE = os.path.join(DATA_DIR, 'candidates.json')
RAW_PAGES_DIR = os.path.join(DATA_DIR, 'raw_pages')

import urllib.parse

def normalize_domain(url: str) -> str:
    """Extracts a clean lowercase domain without www."""
    if not url: return ""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain

def merge_candidates(candidates: list) -> list:
    """Merges github candidates into public_web candidates if they represent the same person."""
    web_cands = [c for c in candidates if c.get('source_type') == 'public_web']
    gh_cands = [c for c in candidates if c.get('source_type') == 'github']
    unmerged = []

    for gh in gh_cands:
        merged = False
        gh_url_clean = gh.get('source_url', '').rstrip('/').lower()
        gh_username = gh.get('metadata', {}).get('github_username', '').lower().strip()
        gh_name = gh.get('metadata', {}).get('profile_name', '').lower().strip()
        gh_blog_domain = normalize_domain(gh.get('metadata', {}).get('blog', ''))

        for w in web_cands:
            w_url_clean = w.get('source_url', '').rstrip('/').lower()
            w_domain = normalize_domain(w.get('source_url', ''))
            w_links_clean = [l.rstrip('/').lower() for l in w.get('links', [])]
            
            w_title = w.get('title', '').lower().strip()
            w_text = w.get('text', '').lower()
            w_base_name = w_title.replace('|', '-').split('-')[0].strip()

            is_match = False
            
            # 1. Direct Link Match
            if gh_url_clean in w_links_clean or gh_url_clean == w_url_clean:
                is_match = True
                
            # 2. Reciprocal Website/Blog Match
            elif gh_blog_domain and w_domain and gh_blog_domain == w_domain:
                is_match = True
                
            # 3. Explicit GitHub handle in public_web text
            elif gh_username and f"@{gh_username}" in w_text:
                is_match = True
                
            # 4. Strong Exact Name Match
            elif gh_name and len(gh_name) > 3:
                if gh_name == w_base_name or f" {gh_name} " in f" {w_text} ":
                    is_match = True

            if is_match:
                # Merge GitHub into Web candidate
                w['projects'] = gh.get('projects', [])
                
                # Propagate metadata safely (only overwrite if empty)
                for key in ['github_username', 'profile_name', 'company', 'location', 'blog']:
                    gh_val = gh.get('metadata', {}).get(key, '')
                    if gh_val and not w.get('metadata', {}).get(key):
                        w['metadata'][key] = gh_val
                
                # Augment links safely
                all_links = set(w.get('links', []))
                all_links.update(gh.get('links', []))
                all_links.add(gh.get('source_url', ''))
                w['links'] = sorted(list(filter(None, all_links)))
                
                # Augment emails safely
                all_emails = set(w.get('emails', []))
                all_emails.update(gh.get('emails', []))
                w['emails'] = sorted(list(filter(None, all_emails)))
                
                # Enrich text
                gh_text = gh.get('text', '').strip()
                if gh_text:
                    w['text'] = w.get('text', '') + f"\n\n=== GitHub Enrichment ===\n{gh_text}"
                
                # Summary hint fallback
                if not w.get('summary_hint') and gh.get('summary_hint'):
                    w['summary_hint'] = gh.get('summary_hint')

                merged = True
                logger.info(f"Merged GitHub profile {gh_url_clean} into Web profile {w_url_clean}")
                break

        if not merged:
            unmerged.append(gh)

    return web_cands + unmerged

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Generate dummy input if it does not exist to make the pipeline runnable immediately
    if not os.path.exists(INPUT_FILE):
        logger.info(f"Input file not found at {INPUT_FILE}. Creating a sample one.")
        with open(INPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(["https://example.com"], f)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        try:
            urls = json.load(f)
        except json.JSONDecodeError:
            logger.error("Invalid JSON format in input_urls.json")
            return

    try:
        import trafilatura
    except ImportError:
        logger.warning("trafilatura is not installed. Falling back to BeautifulSoup text extraction.")
        logger.warning("Please install it via: pip install trafilatura")

    candidates = []

    for url in urls:
        logger.info(f"--- Processing: {url} ---")
        
        if "github.com/" in url:
            parts = url.rstrip('/').split('github.com/')
            username = parts[-1].split('/')[0]
            
            user_data = fetch_github_api(f"https://api.github.com/users/{username}")
            if not user_data:
                logger.warning(f"Skipping {url} due to GitHub API failure or user not found.")
                continue
                
            repos_data = fetch_github_api(f"https://api.github.com/users/{username}/repos?per_page=100&sort=pushed") or []
            
            pinned_repos = []
            profile_html = fetch_github_profile_html(username)
            if profile_html:
                pinned_repos = extract_github_pinned_repos(profile_html)
            
            candidate = normalize_github(user_data, repos_data, url, pinned_repos)
            candidates.append(candidate)
            logger.info(f"Success! Normalized GitHub package for: {candidate.get('title') or url}")
            continue
            
        # Public web fetch
        html_or_pdf, fetch_status, source_format = fetch_page(url, RAW_PAGES_DIR)
        
        # 2. Extract
        if not html_or_pdf:
            logger.warning(f"Skipping extraction for {url} due to {fetch_status}.")
            # Dummy raw signal to trace the failure in the output JSON
            raw_signals = {
                "source_url": url,
                "text": "",
                "fetch_status": fetch_status,
                "source_format": source_format
            }
        else:
            if source_format == "pdf":
                from backend.src.extractor import extract_pdf_signals
                raw_signals = extract_pdf_signals(html_or_pdf, url)
            else:
                raw_signals = extract_signals(html_or_pdf, url)
            
            raw_signals["fetch_status"] = fetch_status
            raw_signals["source_format"] = source_format
        
        # 3. Normalize
        candidate = normalize_candidate(raw_signals)
        candidates.append(candidate)
        
        logger.info(f"Success! Normalized package for: {candidate['title'] or url}")

    # Write output
    merged_candidates = merge_candidates(candidates)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(merged_candidates, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Pipeline complete. {len(merged_candidates)} candidates saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()