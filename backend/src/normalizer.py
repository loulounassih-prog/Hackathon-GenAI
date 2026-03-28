import hashlib
import re
from typing import Dict, Any
from .schemas import IngestionPackageDict, MetadataDict

def clean_candidate_text(text: str) -> str:
    """Cleans excess whitespace to prepare a clean raw text for HrFlow parsing."""
    if not text: return ""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {3,}', ' ', text)
    return text.strip()

def _derive_core_text(text: str) -> str:
    """Extracts the candidate-centered intro, stopping ONLY at pure admin markers."""
    if not text:
        return ""
    
    # We REMOVED academic markers (publications, teaching, etc.) because HrFlow can parse them.
    # We only stop at pure administrative/newsletter boilerplate.
    admin_markers = [
        "prospective phd students", "prospective interns", "post-docs",
        "weekly letters", "subscribe", "companies", "company portfolio",
        "latest related", "all related"
    ]
    
    lines = text.split('\n')
    core_lines = []
    found_real_content = False
    
    for line in lines:
        cleaned_line = line.strip().lower()
        if not cleaned_line:
            continue
            
        # 1. Skip leading boilerplate fragments until we find a "real" sentence
        if not found_real_content:
            # Heuristic: Real content is usually a medium-to-long line with spaces
            if len(cleaned_line) > 60 or (len(cleaned_line) > 20 and ' ' in cleaned_line):
                found_real_content = True
            else:
                continue

        if cleaned_line.endswith(':'):
            cleaned_line = cleaned_line[:-1].strip()
            
        # 2. Check for admin outreach paragraphs starting with specific phrases
        is_marker = False
        for admin in admin_markers:
            if cleaned_line.startswith(admin):
                is_marker = True
                break
            # conservative check for specific marketing phrases in short lines
            if admin in ["weekly letters", "subscribe"] and admin in cleaned_line and len(cleaned_line) < 80:
                is_marker = True
                break
                
        if is_marker:
            break
            
        core_lines.append(line)
        
    core_text = "\n".join(core_lines)
    return clean_candidate_text(core_text)

def normalize_candidate(extracted: Dict[str, Any]) -> IngestionPackageDict:
    """Converts raw extracted signals into a clean ingestion package for HrFlow."""
    url = extracted.get("source_url", "")
    raw_text = extracted.get("text", "")
    title = extracted.get("title", "")
    description = extracted.get("description", "")
    emails = extracted.get("emails", [])
    links = extracted.get("links", [])
    content_markers = extracted.get("content_markers", [])
    fetch_status = extracted.get("fetch_status", "success")
    is_candidate_like = extracted.get("is_candidate_like", True)
    candidate_reason = extracted.get("candidate_reason", "")

    # Derive candidate-centered text
    core_text = _derive_core_text(raw_text)
    
    # Advanced diagnostic check
    scraping_status = fetch_status
    word_count = len(core_text.split())
    
    reasons = []
    if scraping_status != "success":
        reasons.append(f"Fetch failed: {scraping_status}")
    
    if not is_candidate_like:
        scraping_status = "not_candidate_like"
        reasons.append(f"Not candidate-like: {candidate_reason}")
    
    if word_count < 20: # Slightly stricter word count for parse-ready
        if scraping_status == "success":
            scraping_status = "low_content"
        reasons.append(f"Low content ({word_count} words)")
            
    parse_ready = (scraping_status == "success")
    parse_readiness_reasons = "Ready for HrFlow Profile Parsing" if parse_ready else "; ".join(reasons)
    
    # 3. Summary Hint (extractive only, preferring first 1-3 sentences)
    summary_hint = ""
    if core_text:
        # Split by punctuation followed by a space
        sentences = re.split(r'(?<=[.!?])\s+', core_text)
        # Filter out very short "sentences" that might be noise
        sentences = [s.strip() for s in sentences if len(s.split()) > 3]
        summary_hint = " ".join(sentences[:3]).strip()
        
    if not summary_hint:
        summary_hint = description

    reference = hashlib.md5(url.encode('utf-8')).hexdigest() if url else ""

    metadata: MetadataDict = {
        "page_title": title,
        "meta_description": description,
        "content_markers": content_markers,
        "github_username": "",
        "profile_name": extracted.get("profile_name", ""),
        "company": extracted.get("company", ""),
        "location": extracted.get("location", ""),
        "blog": "",
        "scraping_status": scraping_status,
        "candidate_reasons": candidate_reason,
        "source_format": extracted.get("source_format", "html"),
        "parse_ready": parse_ready,
        "parse_readiness_reasons": parse_readiness_reasons
    }

    ingestion_package: IngestionPackageDict = {
        "reference": reference,
        "source_type": "public_web",
        "source_url": url,
        "title": title,
        "text": core_text,
        "summary_hint": summary_hint,
        "emails": emails,
        "links": links,
        "metadata": metadata,
        "projects": []
    }
    
    return ingestion_package

def normalize_github(user_data: dict, repos_data: list, source_url: str, pinned_repos: list = None) -> IngestionPackageDict:
    """Converts raw GitHub API signals into a clean ingestion package."""
    username = user_data.get("login", "")
    name = user_data.get("name") or username
    bio = user_data.get("bio") or ""
    company = user_data.get("company") or ""
    location = user_data.get("location") or ""
    blog = user_data.get("blog") or ""
    email = user_data.get("email") or ""
    
    pinned_repos = pinned_repos or []
    projects = []
    languages = set()
    added_urls = set()
    
    # Process pinned repos first (they are implicitly high signal)
    for r in pinned_repos:
        if len(projects) >= 8:
            break
        # Filter completely empty pinned items just in case
        if not r.get("description") and not r.get("language") and not r.get("stars"):
            continue
            
        lang = r.get("language") or ""
        if lang:
            languages.add(lang)
            
        proj = {
            "name": r.get("name", ""),
            "url": r.get("url", ""),
            "description": r.get("description", ""),
            "language": lang,
            "stars": r.get("stars", 0),
            "topics": r.get("topics") or [],
            "is_pinned": True # internal flag for sorting
        }
        projects.append(proj)
        added_urls.add(proj["url"])

    # Process API repos
    # Filter out forks, gists (usually don't have descriptions in this endpoint but just to be sure), 
    # and completely weak repos (0 stars AND no description)
    valid_repos = []
    for r in repos_data:
        if r.get("fork"):
            continue
        stars = r.get("stargazers_count", 0)
        desc = r.get("description", "")
        if stars == 0 and not desc:
            continue
        valid_repos.append(r)
        
    # Prioritize by stars descending, then recent updates
    valid_repos.sort(key=lambda x: (x.get("stargazers_count", 0), x.get("pushed_at", "")), reverse=True)
    
    for r in valid_repos:
        if len(projects) >= 8:
            break
        repo_url = r.get("html_url", "")
        if repo_url in added_urls:
            continue
            
        lang = r.get("language") or ""
        if lang:
            languages.add(lang)
            
        proj = {
            "name": r.get("name", ""),
            "url": repo_url,
            "description": r.get("description", ""),
            "language": lang,
            "stars": r.get("stargazers_count", 0),
            "topics": r.get("topics") or [],
            "is_pinned": False
        }
        projects.append(proj)
        added_urls.add(repo_url)
        
    # Final sort: Pinned first, then by stars
    projects.sort(key=lambda x: (not x.pop("is_pinned"), -x["stars"]))
    
    repo_texts = []
    for proj in projects:
        lang_str = f", {proj['language']}" if proj['language'] else ""
        repo_texts.append(f"- {proj['name']} ({proj['stars']} stars{lang_str}): {proj['description']}")
        
    # Build a clean text block
    text_parts = [f"GitHub Profile: {name} ({username})"]
    if bio: text_parts.append(f"Bio: {bio}")
    if company: text_parts.append(f"Company: {company}")
    if location: text_parts.append(f"Location: {location}")
    if languages: text_parts.append(f"Top Languages: {', '.join(filter(None, languages))}")
    if repo_texts:
        text_parts.append("\nTop Projects:")
        text_parts.extend(repo_texts)
        
    text = "\n".join(text_parts)
    
    # Extractive summary hint (strict)
    summary_hint = bio
    if not summary_hint:
        # Build a stronger extractive fallback from actual extracted project data
        fallback_parts = []
        if company:
            fallback_parts.append(company)
        if languages:
            fallback_parts.append(f"Languages: {', '.join(list(languages)[:3])}")
        if projects:
            fallback_parts.append(f"Top Project: {projects[0]['name']}")
            
        if fallback_parts:
            summary_hint = " | ".join(fallback_parts)
        elif location:
            summary_hint = location

    links = []
    if blog:
        if not blog.startswith("http"):
            blog = "https://" + blog
        links.append(blog)

    metadata: MetadataDict = {
        "page_title": f"{name} - GitHub",
        "meta_description": bio,
        "content_markers": [],
        "github_username": username,
        "profile_name": name,
        "company": company,
        "location": location,
        "blog": blog,
        "scraping_status": "success",
        "candidate_reasons": "github_profile_api",
        "source_format": "github_api",
        "parse_ready": True,
        "parse_readiness_reasons": "Ready for HrFlow Profile Parsing"
    }

    ingestion_package: IngestionPackageDict = {
        "reference": hashlib.md5(source_url.encode('utf-8')).hexdigest(),
        "source_type": "github",
        "source_url": source_url,
        "title": f"{name} - GitHub",
        "text": text,
        "summary_hint": summary_hint[:500],
        "emails": [email] if email else [],
        "links": links,
        "metadata": metadata,
        "projects": projects
    }
    
    return ingestion_package
