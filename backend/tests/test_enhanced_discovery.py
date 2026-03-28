import pytest
from unittest.mock import patch, MagicMock
from backend.src.discovery import DiscoveryEngine

def test_generate_queries_enhanced():
    criteria = {
        "role_keywords": ["Machine Learning Engineer"],
        "skills": ["Python", "PyTorch"],
        "locations": ["Paris"]
    }
    engine = DiscoveryEngine(criteria)
    queries = engine.generate_queries()
    
    assert any("Machine Learning Engineer" in q for q in queries)
    assert any("orcid.org" in q for q in queries)
    assert any("github.com" in q for q in queries)

@patch("backend.src.discovery.requests.get")
def test_discover_orcid(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": [
            {"orcid-identifier": {"path": "0000-0001-2345-6789"}}
        ]
    }
    mock_get.return_value = mock_response
    
    criteria = {"role_keywords": ["Researcher"]}
    engine = DiscoveryEngine(criteria)
    engine.discover_orcid()
    
    assert len(engine.results) == 1
    assert engine.results[0]["url"] == "https://orcid.org/0000-0001-2345-6789"
    assert engine.results[0]["source_type"] == "orcid"

def test_score_url_enhanced():
    engine = DiscoveryEngine({})
    
    # PDF CV
    score, reason, source = engine.score_url("https://example.com/resume.pdf")
    assert score >= 0.90
    assert "PDF" in reason
    
    # ORCID
    score, reason, source = engine.score_url("https://orcid.org/0000-0001-2345-6789")
    assert score >= 0.80
    assert source == "orcid"
    
    # Academic/Edu
    score, reason, source = engine.score_url("https://mit.edu/~jdoe")
    assert score > 0.60
    assert "Academic" in reason
    
    # Noise
    score, reason, source = engine.score_url("https://github.com/user/repo/issues/1")
    assert score == 0.0
    assert "Noise" in reason

def test_parse_ready_logic():
    from backend.src.normalizer import normalize_candidate
    
    # Success case
    extracted = {
        "source_url": "https://jdoe.com",
        "text": "I am a software engineer with 10 years of experience in Python and Cloud computing. " * 5,
        "title": "John Doe",
        "is_candidate_like": True,
        "fetch_status": "success",
        "profile_name": "John Doe"
    }
    candidate = normalize_candidate(extracted)
    assert candidate["metadata"]["parse_ready"] is True
    assert "Ready" in candidate["metadata"]["parse_readiness_reasons"]
    
    # Low content case
    extracted_low = {**extracted, "text": "Too short"}
    candidate_low = normalize_candidate(extracted_low)
    assert candidate_low["metadata"]["parse_ready"] is False
    assert "Low content" in candidate_low["metadata"]["parse_readiness_reasons"]
    
    # Not candidate like case
    extracted_not_cand = {**extracted, "is_candidate_like": False, "candidate_reason": "generic_domain"}
    candidate_not_cand = normalize_candidate(extracted_not_cand)
    assert candidate_not_cand["metadata"]["parse_ready"] is False
    assert "Not candidate-like" in candidate_not_cand["metadata"]["parse_readiness_reasons"]
