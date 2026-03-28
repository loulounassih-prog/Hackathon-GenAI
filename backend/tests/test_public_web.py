import pytest
from unittest.mock import patch, MagicMock
from backend.src.fetcher import fetch_page
from backend.src.extractor import extract_signals, extract_pdf_signals
from backend.src.normalizer import normalize_candidate
import os

@patch("backend.src.fetcher.requests.get")
def test_fetch_non_html(mock_get, tmp_path):
    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "application/octet-stream"}
    mock_response.raise_for_status.return_value = None
    mock_response.__enter__.return_value = mock_response
    mock_get.return_value = mock_response

    html, status, format_type = fetch_page("https://example.com/file.bin", str(tmp_path))
    assert html is None
    assert status == "non_html"
    assert format_type == ""

@patch("backend.src.fetcher.requests.get")
def test_fetch_pdf(mock_get, tmp_path):
    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "application/pdf"}
    mock_response.iter_content.return_value = [b"%PDF-1.4 mock pdf content"]
    mock_response.raise_for_status.return_value = None
    mock_response.__enter__.return_value = mock_response
    mock_get.return_value = mock_response

    filepath, status, format_type = fetch_page("https://example.com/resume.pdf", str(tmp_path))
    assert filepath is not None
    assert status == "success"
    assert format_type == "pdf"
    assert filepath.endswith(".pdf")
    assert os.path.exists(filepath)

@patch("backend.src.fetcher.requests.get")
def test_fetch_404(mock_get, tmp_path):
    from requests.exceptions import HTTPError
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = HTTPError("404 Client Error")
    mock_response.__enter__.return_value = mock_response
    mock_get.return_value = mock_response

    html, status, format_type = fetch_page("https://example.com/404", str(tmp_path))
    assert html is None
    assert status == "fetch_error"
    assert format_type == ""

def test_email_extraction():
    html = "<html><body>Contact: real.name+tag@sub.domain.com and ignore logo@2x.png and style@1.css</body></html>"
    signals = extract_signals(html, "https://example.com")
    assert "real.name+tag@sub.domain.com" in signals["emails"]
    assert "logo@2x.png" not in signals["emails"]
    assert "style@1.css" not in signals["emails"]

def test_is_candidate_like_truth_set():
    # Tiangolo
    t1 = "Sebastián Ramírez (@tiangolo)"
    txt1 = "I am the creator of FastAPI. My GitHub is tiangolo."
    url1 = "https://tiangolo.com/"
    signals1 = extract_signals(f"<html><title>{t1}</title><body>{txt1}</body></html>", url1)
    assert signals1["is_candidate_like"] is True
    assert signals1["profile_name"] == "Sebastián Ramírez"

    # Karpathy
    t2 = "Andrej Karpathy"
    txt2 = "I was at OpenAI and Tesla. I work on deep learning."
    url2 = "https://karpathy.ai/"
    signals2 = extract_signals(f"<html><title>{t2}</title><body>{txt2}</body></html>", url2)
    assert signals2["is_candidate_like"] is True
    assert signals2["profile_name"] == "Andrej Karpathy"

    # Tom Mitchell
    t3 = "Tom Mitchell's Home Page"
    txt3 = "Professor at CMU. Research in machine learning."
    url3 = "https://www.cs.cmu.edu/~tom/"
    signals3 = extract_signals(f"<html><title>{t3}</title><body>{txt3}</body></html>", url3)
    assert signals3["is_candidate_like"] is True
    assert signals3["profile_name"] == "Tom Mitchell"

    # Generic Example
    t4 = "Example Domain"
    txt4 = "This domain is for use in illustrative examples in documents."
    url4 = "https://example.com/"
    signals4 = extract_signals(f"<html><title>{t4}</title><body>{txt4}</body></html>", url4)
    assert signals4["is_candidate_like"] is False
    cand4 = normalize_candidate({**signals4, "fetch_status": "success"})
    assert cand4["metadata"]["scraping_status"] == "not_candidate_like"
    assert cand4["metadata"]["parse_ready"] is False

    # Httpbin (Literary/Generic)
    t5 = "httpbin.org"
    txt5 = "The heavy bear who goes with me, A manifold and many-colored thing."
    url5 = "https://httpbin.org/html"
    signals5 = extract_signals(f"<html><title>{t5}</title><body>{txt5}</body></html>", url5)
    assert signals5["is_candidate_like"] is False

def test_stable_structure_on_failure():
    signals = {
        "source_url": "https://example.com/broken",
        "text": "",
        "fetch_status": "fetch_error"
    }
    candidate = normalize_candidate(signals)
    assert candidate["metadata"]["scraping_status"] == "fetch_error"
    assert candidate["metadata"]["parse_ready"] is False
    assert candidate["source_url"] == "https://example.com/broken"
    assert "projects" in candidate
    assert "links" in candidate

@patch("backend.src.extractor.pypdf.PdfReader")
def test_pdf_extraction(mock_pdf_reader, tmp_path):
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Jane Doe\nSoftware Engineer\nEmail: jane.doe@example.com\nPython, Java, C++\n" * 5 # repeat to be > 100 chars
    mock_reader_instance = MagicMock()
    mock_reader_instance.pages = [mock_page]
    mock_pdf_reader.return_value = mock_reader_instance
    
    # Create dummy file to pass open()
    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.write_bytes(b"%PDF")
    
    signals = extract_pdf_signals(str(dummy_pdf), "https://example.com/resume.pdf")
    
    assert signals["source_format"] == "pdf"
    assert signals["is_candidate_like"] is True
    assert "jane.doe@example.com" in signals["emails"]
    assert signals["profile_name"] == "Jane Doe"
    
    candidate = normalize_candidate(signals)
    assert candidate["metadata"]["source_format"] == "pdf"
    assert candidate["metadata"]["candidate_reasons"] == "pdf_resume_detected"
    assert candidate["metadata"]["parse_ready"] is True
