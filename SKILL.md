---
name: candidate-search
description: Two-phase recruitment search process. 1. Extracts and enriches job details, then pauses for user confirmation. 2. Performs candidate search based on confirmed job details. Use when the user wants to search for candidates.
---

# Candidate Search Workflow

This skill executes a two-phase recruitment search process. It is critical to strictly follow this sequence and await user confirmation between phases to ensure data accuracy.

## Phase 1: Fetching Job Details

1. **Create Initial Input:** Based on the user's request, create a temporary file named `initial_job_input.json` strictly structured as follows:
   ```json
   {
     "name": "<titre du poste>",
     "url": "<url du poste si fournie, sinon chaine vide>",
     "recruiter-details": "<instructions spécifiques de l'utilisateur>"
   }
   ```
2. **Run Fetch Script:** Execute the job detail extraction script using Python 3:
   ```bash
   python3 /Users/hackathon-team9/.openclaw/workspace/skills/candidate-search/scripts/fetch_job_details.py --input initial_job_input.json --output job_context.json
   ```
3. **Present & Wait:** Read the generated `job_context.json` file. Present the extracted/enriched job details clearly to the user.
   **CRITICAL ACTION:** You MUST ask the user to confirm if these details are correct. **DO NOT** proceed to Phase 2 until the user explicitly replies with validation. 

## Phase 2: Candidate Search

Only begin this phase AFTER the user has explicitly confirmed the job details from Phase 1.

1. **Acknowledge:** Reply to the user's confirmation by starting your message with exactly: "Début de la recherche"
2. **Run Search Script:** Execute the candidate search script, passing the confirmed context JSON:
   ```bash
   python3 /Users/hackathon-team9/.openclaw/workspace/skills/candidate-search/scripts/search_candidates.py --input job_context.json --output final_candidates.json
   ```
3. **Present Final Results:** Read `final_candidates.json` and present the recommended candidates to the user clearly (nom, résumé, raison).
4. **Cleanup:** Clean up the temporary files (`initial_job_input.json`, `job_context.json`, `final_candidates.json`).
