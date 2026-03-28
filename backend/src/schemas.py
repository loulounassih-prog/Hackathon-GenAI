from typing import TypedDict, List, Dict, Any

class MetadataDict(TypedDict):
    page_title: str
    meta_description: str
    content_markers: List[str]
    github_username: str
    profile_name: str
    company: str
    location: str
    blog: str
    scraping_status: str
    candidate_reasons: str
    source_format: str
    parse_ready: bool
    parse_readiness_reasons: str

class IngestionPackageDict(TypedDict):
    reference: str
    source_type: str
    source_url: str
    title: str
    text: str
    summary_hint: str
    emails: List[str]
    links: List[str]
    metadata: MetadataDict
    projects: List[Dict[str, Any]]