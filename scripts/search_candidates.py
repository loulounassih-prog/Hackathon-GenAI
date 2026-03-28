import json
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Search and rank candidates based on enriched job context")
    parser.add_argument('--input', type=str, required=True, help='Path to enriched job context JSON')
    parser.add_argument('--output', type=str, required=True, help='Path to output candidates JSON')
    args = parser.parse_args()

    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            job_context = json.load(f)
    except Exception as e:
        print(f"Error reading input: {e}")
        sys.exit(1)

    # TODO: Implement your actual candidate search and ranking logic here
    skills_str = ", ".join(job_context.get('required_skills', []))
    
    candidates_result = {
        "job_context_used": job_context.get("name"),
        "candidats": [
            {
                "nom": "Alice Dupont",
                "resume": f"{job_context.get('experience_years', 5)} ans d'expérience. Compétences: {skills_str}",
                "reason": "Correspond parfaitement aux compétences techniques requises et au niveau d'expérience demandé."
            },
            {
                "nom": "Bob Martin",
                "resume": "Développeur fullstack avec une forte expertise en architecture logicielle.",
                "reason": f"Excellente expérience sur des projets similaires chez {job_context.get('company', 'une autre entreprise')}."
            }
        ]
    }

    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(candidates_result, f, indent=4, ensure_ascii=False)
        print("Successfully searched candidates.")
    except Exception as e:
        print(f"Error writing output: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()