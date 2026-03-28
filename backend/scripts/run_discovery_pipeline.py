import os
import sys
import json
import logging

# Ensure absolute imports work when run as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.src.discovery import DiscoveryEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
INPUT_FILE = os.path.join(DATA_DIR, 'discovery_input.json')
OUTPUT_FILE = os.path.join(DATA_DIR, 'discovered_urls.json')

def main():
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Discovery input file not found at {INPUT_FILE}")
        return

    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            criteria = json.load(f)
    except json.JSONDecodeError:
        logger.error("Invalid JSON format in discovery_input.json")
        return

    logger.info("--- Starting Autonomous Discovery Pipeline ---")
    logger.info(f"Targeting: {criteria.get('role_keywords', ['unknown'])} in {criteria.get('locations', ['anywhere'])}")
    
    engine = DiscoveryEngine(criteria)
    results = engine.run()

    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info(f"Discovery Pipeline Complete.")
    logger.info(f"Found {len(results)} high-confidence URLs.")
    logger.info(f"Results saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
