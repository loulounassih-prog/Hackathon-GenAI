from pathlib import Path

from dotenv import load_dotenv
import os

from axel.job import JobManager


def main():
    def write_job_key_to_dotenv(env_path: Path, job_key: str) -> None:
        """Met à jour (ou ajoute) la ligne JOB_KEY dans le fichier .env."""
        if not env_path.is_file():
            raise FileNotFoundError(f".env introuvable : {env_path}")

        text = env_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        new_lines: list[str] = []
        replaced = False
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("JOB_KEY") and "=" in stripped:
                new_lines.append(f'JOB_KEY = "{job_key}"')
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append(f'JOB_KEY = "{job_key}"')

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


    REPO_ROOT = Path(__file__).resolve().parent.parent
    DOTENV_PATH = REPO_ROOT / ".env"

    load_dotenv(DOTENV_PATH)
    API_KEY = os.getenv("API_KEY")
    API_USER = os.getenv("API_USER")
    BOARD_KEY = os.getenv("BOARD_KEY")

    job_manager = JobManager(BOARD_KEY, API_KEY, API_USER)
    job_manager.archive_job(job_manager.get_all_keys()[0])
    # result = job_manager.send_json("axel/job.json")
    result = job_manager.send_text(open("axel/text.txt", "r").read())

    if result and result.get("job_key"):
        job_key = result["job_key"]
        # print(job_key)
        write_job_key_to_dotenv(DOTENV_PATH, job_key)
        print(f"JOB_KEY mis à jour dans {DOTENV_PATH}")
        load_dotenv(DOTENV_PATH, override=True)
    else:
        print("Échec ou job_key absent dans la réponse API :", result)


if __name__ == "__main__":
    main()