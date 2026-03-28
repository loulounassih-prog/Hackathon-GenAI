# HrFlow-GenAI Recruitment Pipeline

An autonomous recruitment pipeline that discovers, scrapes, normalizes, and scores candidates from the web against specific job criteria using HrFlow.ai.

## Overview

This project provides an end-to-end solution for sourcing and evaluating candidates:
1.  **Discovery:** Searches the web (Google, GitHub) for profiles matching specific role keywords and locations.
2.  **Scraping:** Fetches data from discovered URLs, including HTML pages, PDFs, and GitHub API data.
3.  **Normalization:** Cleans and structures the raw data into a consistent JSON format ready for HrFlow.ai ingestion.
4.  **Scoring & Ranking:** Uses HrFlow.ai Scoring API to rank candidates against a target job description.
5.  **Dashboard:** A Django-based frontend to visualize candidate profiles and rankings.

## Repository Structure

-   `backend/src/`: Core logic for discovery, fetching, extraction, and normalization.
-   `backend/scripts/`: Pipeline execution scripts.
-   `backend/ranking/`: Scoring, ranking, and candidate splitting logic.
-   `backend/data/`: Input/output JSON files and raw HTML pages.
-   `frontend/`: Django application for the recruitment dashboard.
-   `scripts/`: Utility scripts for job enhancement and candidate search.

## Prerequisites

-   Python 3.x
-   HrFlow.ai account with API credentials.

## Installation

1.  **Clone the repository.**
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    cd frontend && pip install -r requirements.txt
    ```

## Environment Variables

Create a `.env` file in the root directory (or ensure these are set in your environment):

| Variable | Description |
| :--- | :--- |
| `API_KEY` | HrFlow.ai API Key (X-API-KEY) |
| `API_USER` | HrFlow.ai User Email (X-USER-EMAIL) |
| `HRFLOW_API_SECRET` | HrFlow.ai API Secret (used by frontend) |
| `BOARD_KEY` / `HRFLOW_BOARD_KEY` | HrFlow.ai Board Key |
| `SOURCE_KEY` / `HRFLOW_SOURCE_KEY` | HrFlow.ai Source Key (external scraping) |
| `SOURCE_KEY_2` | HrFlow.ai Source Key (internal applicants) |
| `JOB_KEY` | HrFlow.ai Job Key for scoring |

## Running the App

### 1. Discovery Pipeline
Finds URLs of potential candidates based on criteria in `backend/data/discovery_input.json`.
```bash
python backend/scripts/run_discovery_pipeline.py
```

### 2. Scraping Pipeline
Scrapes and normalizes data from URLs in `backend/data/input_urls.json`.
```bash
python backend/scripts/run_scraping_pipeline.py
```

### 3. Scoring & Ranking
Scores normalized candidates against the job description in `backend/ranking/job.json`.
```bash
python backend/ranking/scoring.py
```

### 4. Recruitment Dashboard
Starts the Django web server to view results.
```bash
cd frontend
python manage.py runserver
```

## Input and Output Files

-   `backend/data/discovery_input.json`: (Input) Search criteria (role, location).
-   `backend/data/discovered_urls.json`: (Output) List of URLs found by the discovery engine.
-   `backend/data/input_urls.json`: (Input) List of URLs to be scraped.
-   `backend/data/candidates.json`: (Output) Normalized candidate data.
-   `backend/ranking/job.json`: (Input) Target job description for scoring.
-   `backend/ranking/grading_output.json`: (Output) Final ranking and scoring results.

## HrFlow.ai APIs Used

-   **Scoring API (`v1/profiles/scoring`):** Ranks candidates against a specific job using HrFlow.ai's AI algorithms.
-   **Profile Parsing (`v1/profile/parsing/file`):** Extracts structured data from CVs and profile documents.
-   **Profile Indexing (`v1/profile/indexing`):** Ingests normalized candidate data into HrFlow.ai sources.
-   **Text Parsing (`v1/text/parsing`):** Extracts entities and skills from raw text.

## Notes / Limitations

-   **API Limits:** Ensure your HrFlow.ai and GitHub API limits are respected.
-   **Discovery:** Relies on `googlesearch-python`; results may vary based on search engine responsiveness.
-   **GitHub Scraping:** Uses the GitHub REST API for profile data and BeautifulSoup for pinned repositories.
