import json
import logging
import re
from urllib.parse import urlparse
import requests
from typing import List, Dict, Any, Tuple

# Lightweight web search library
try:
    from googlesearch import search as google_search
    HAS_GOOGLE_SEARCH = True
except ImportError:
    HAS_GOOGLE_SEARCH = False

logger = logging.getLogger(__name__)

class DiscoveryEngine:
    def __init__(self, criteria: Dict[str, Any]):
        self.criteria = criteria
        self.max_results = criteria.get("max_results", 30)
        self.results = []
        self.seen_urls = set()

    def generate_queries(self) -> List[str]:
        """Generates a few high-signal search queries from criteria."""
        roles = self.criteria.get("role_keywords", [])
        skills = self.criteria.get("skills", [])
        locations = self.criteria.get("locations", [])
        
        queries = []
        if roles:
            role = roles[0]
            skill_str = " ".join(skills[:2]) if skills else ""
            loc = locations[0] if locations else ""
            
            # Query 1: Role + Skills + Location (No strict quotes to be more flexible)
            queries.append(f'{role} {skill_str} {loc}'.strip())
            
            # Query 2: Profile centric
            queries.append(f'{role} {loc} (site:github.com OR site:orcid.org OR "about me" OR "portfolio")'.strip())
            
            # Query 3: CV/Resume centric (high signal)
            queries.append(f'{role} {loc} filetype:pdf (cv OR resume)'.strip())

        return list(set(q for q in queries if q))

    def discover_github(self):
        """Discovers candidates via GitHub Search API."""
        logger.info("Starting GitHub discovery...")
        roles = self.criteria.get("role_keywords", [])
        locations = self.criteria.get("locations", [])
        
        if not roles:
            return

        # Simple GitHub query: role + location
        q_loc = f" location:{locations[0]}" if locations else ""
        query = f"{roles[0]}{q_loc}"
        url = f"https://api.github.com/search/users?q={query}&per_page={self.max_results}"
        
        try:
            # Public API headers
            headers = {"Accept": "application/vnd.github.v3+json"}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                items = response.json().get("items", [])
                for i, item in enumerate(items):
                    profile_url = item.get("html_url")
                    if profile_url and profile_url not in self.seen_urls:
                        score, reason, source_type = self.score_url(profile_url)
                        # Dynamic confidence: slight boost for API match, decay by rank
                        decay = i * 0.01
                        final_score = max(round((score + 0.05) - decay, 3), 0.50)
                        reason = f"{reason} (API match, rank {i+1})"
                        self.add_result(profile_url, source_type, query, reason, final_score)
            else:
                logger.warning(f"GitHub API status {response.status_code} for query: {query}")
        except Exception as e:
            logger.error(f"GitHub discovery error: {e}")

    def discover_orcid(self):
        """Discovers candidates via ORCID Public API."""
        logger.info("Starting ORCID discovery...")
        roles = self.criteria.get("role_keywords", [])
        skills = self.criteria.get("skills", [])
        
        if not roles and not skills:
            return

        # Simple ORCID query: role or first skill
        search_term = roles[0] if roles else skills[0]
        url = f"https://pub.orcid.org/v3.0/search?q={search_term}"
        
        try:
            headers = {"Accept": "application/json"}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                results = response.json().get("result", [])
                for i, res in enumerate(results):
                    orcid_id = res.get("orcid-identifier", {}).get("path")
                    if orcid_id:
                        profile_url = f"https://orcid.org/{orcid_id}"
                        if profile_url not in self.seen_urls:
                            score, reason, source_type = self.score_url(profile_url)
                            decay = i * 0.01
                            final_score = max(round((score + 0.05) - decay, 3), 0.50)
                            reason = f"{reason} (API match, rank {i+1})"
                            self.add_result(profile_url, source_type, search_term, reason, final_score)
            else:
                logger.warning(f"ORCID API status {response.status_code}")
        except Exception as e:
            logger.error(f"ORCID discovery error: {e}")

    def discover_web(self):
        """Discovers candidates via lightweight web search with fallback."""
        logger.info("[PUBLIC_WEB] Starting Web discovery...")
        queries = self.generate_queries()
        logger.info(f"[PUBLIC_WEB] Generated {len(queries)} queries: {queries}")
        
        total_found = 0
        total_rejected = 0
        rejection_reasons = {}

        for q in queries:
            added_for_query = 0
            logger.info(f"[PUBLIC_WEB] Launching query: '{q}'")
            
            # Try Google first (if library available)
            raw_results = []
            if HAS_GOOGLE_SEARCH:
                try:
                    # Capture up to 15 results
                    for url in google_search(q, num_results=15):
                        raw_results.append(url)
                    logger.info(f"[PUBLIC_WEB] Google returned {len(raw_results)} results for '{q}'")
                except Exception as e:
                    logger.warning(f"[PUBLIC_WEB] Google Search failed or blocked for '{q}': {e}")
            
            # Fallback to DuckDuckGo if Google returns nothing (often means blocked)
            if not raw_results:
                logger.info(f"[PUBLIC_WEB] No Google results. Trying DuckDuckGo fallback for '{q}'...")
                try:
                    ddg_url = f"https://duckduckgo.com/html/?q={q}"
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    resp = requests.get(ddg_url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        from bs4 import BeautifulSoup
                        from urllib.parse import unquote
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        # DDG HTML results are in class result__a
                        for a in soup.find_all('a', class_='result__a'):
                            raw_url = a['href']
                            # Extract actual URL if it's a DDG redirect
                            if "/l/?uddg=" in raw_url:
                                actual_url = unquote(raw_url.split("/l/?uddg=")[1].split("&rut=")[0])
                                raw_results.append(actual_url)
                            else:
                                raw_results.append(raw_url)
                        logger.info(f"[PUBLIC_WEB] DuckDuckGo returned {len(raw_results)} results for '{q}'")
                except Exception as e:
                    logger.error(f"[PUBLIC_WEB] DuckDuckGo fallback failed: {e}")

            # Process combined/fallback results
            for i, url in enumerate(raw_results):
                if added_for_query >= 10:
                    break
                
                if url in self.seen_urls:
                    total_rejected += 1
                    rejection_reasons["Already seen"] = rejection_reasons.get("Already seen", 0) + 1
                    continue

                score, reason, source_type = self.score_url(url)
                decay = i * 0.015
                final_score = max(round(score - decay, 3), 0.30)
                logger.info(f"[PUBLIC_WEB] Scored URL {url}: base={score}, final={final_score}, reason={reason}")
                
                if final_score > 0.35: # Slightly lower threshold to be more inclusive in discovery
                    reason = f"{reason} (Web search, rank {i+1})"
                    self.add_result(url, source_type, q, reason, final_score)
                    added_for_query += 1
                    total_found += 1
                else:
                    total_rejected += 1
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            
            logger.info(f"[PUBLIC_WEB] Query '{q}': Added {added_for_query} to potential results.")

        logger.info(f"[PUBLIC_WEB] Discovery finished. Total found: {total_found}, Total rejected: {total_rejected}")
        if rejection_reasons:
            logger.info(f"[PUBLIC_WEB] Rejection reasons: {rejection_reasons}")

    def score_url(self, url: str) -> Tuple[float, str, str]:
        """Assigns a deterministic confidence score and classification based on URL patterns."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        domain = parsed.netloc.lower()
        
        if "github.com" in domain:
            source_type = "github"
            base_score = 0.50
        elif "orcid.org" in domain:
            source_type = "orcid"
            base_score = 0.50
        else:
            source_type = "public_web"
            base_score = 0.92 # Boosted base score for web results to ensure they appear
        
        # 1. Negative patterns (noise)
        noise = ["/issues/", "/pull/", "/commit/", "/blob/", "/search", "/login", "/signup", "/docs/", "/api/", "/tags/", "/category/", "/pricing", "/legal", "/privacy"]
        if any(p in path for p in noise):
            return 0.0, "Noise pattern", source_type
            
        if url.endswith((".zip", ".gz", ".ppt", ".docx", ".mp4", ".png", ".jpg")):
            return 0.0, "Non-profile file format", source_type

        score = base_score
        reason = "Matched query keywords"
        
        # Detect PDF CVs
        if url.endswith(".pdf") or ".pdf?" in url:
            if any(k in url.lower() for k in ['cv', 'resume', 'profile', 'curriculum']):
                return 0.98, "PDF CV/Resume detected", "pdf"
            else:
                return 0.40, "Generic PDF (low confidence)", "pdf"

        profile_hints = ["/about", "/people/", "/team/", "/bio", "/profile", "/cv", "/resume", "/speaker", "/~"]
        if any(p in path for p in profile_hints):
            score += 0.30
            reason = "Candidate-like path pattern detected"
            
        # Penalize generic homepages without profile hints
        if path in ['', '/'] and not any(k in domain for k in ['person', 'portfolio', 'me', 'blog', 'github', 'orcid']):
            score -= 0.20
            reason += " (Generic root domain penalization)"
            
        if source_type == "github":
            parts = [p for p in path.split('/') if p]
            if len(parts) == 1:
                score += 0.40
                reason = "GitHub profile detected"
            else:
                score -= 0.1

        if source_type == "orcid":
            score += 0.40
            reason = "ORCID profile detected"

        if ".edu" in domain or ".ac." in domain:
            score += 0.15
            reason += " (Institutional/Academic source)"

        return min(max(round(score, 2), 0.0), 0.95), reason, source_type

    def add_result(self, url: str, source_type: str, query: str, reason: str, confidence: float):
        if url in self.seen_urls:
            return
        
        self.results.append({
            "url": url,
            "source_type": source_type,
            "discovery_query": query,
            "reason": reason,
            "confidence": confidence
        })
        self.seen_urls.add(url)

    def run(self) -> List[Dict[str, Any]]:
        """Executes the full discovery pipeline."""
        # 1. GitHub
        if "github.com" in self.criteria.get("domains_of_interest", []):
            self.discover_github()
            
        # 2. ORCID
        if self.criteria.get("include_orcid", True):
            self.discover_orcid()
        
        # 3. Web search (Always run to diversify sources)
        self.discover_web()
            
        # Ensure diversity by limiting the number of elements per source before final sort
        # We want to ensure that all discovered sources have a chance to appear
        num_sources = len(set(r["source_type"] for r in self.results))
        diversity_limit = max(self.max_results // (num_sources or 1), 5)
        
        grouped = {}
        for r in self.results:
            grouped.setdefault(r["source_type"], []).append(r)
            
        diverse_results = []
        for src, items in grouped.items():
            items.sort(key=lambda x: x["confidence"], reverse=True)
            taken = items[:diversity_limit]
            diverse_results.extend(taken)
            logger.info(f"Source {src}: Found {len(items)}, kept {len(taken)} (limit {diversity_limit})")
            
        diverse_results.sort(key=lambda x: x["confidence"], reverse=True)
        logger.info(f"Total diverse results: {len(diverse_results)}. Final cut to {self.max_results}.")
        return diverse_results[:self.max_results]
