import os
import json
import uuid
from hrflow import Hrflow
import requests

class JobManager:
    def __init__(self, BOARD_KEY, API_KEY, API_USER):
        self.board_key = BOARD_KEY
        self.api_key = API_KEY
        self.api_user = API_USER
        self.client = Hrflow(api_secret=self.api_key, api_user=self.api_user)
        self.all_keys = self.get_all_keys()


    def get_all_keys(self, board_key=None):
        board_key = board_key or self.board_key
        all_keys = []
        page = 1
        
        while True:
            # Rappel : 'source_keys' au pluriel et dans une liste []
            response = self.client.job.storing.list(
                board_keys=[board_key], 
                limit=30, 
                page=page
            )
            
            if response['code'] != 200:
                print(f"Erreur : {response['message']}")
                break
                
            jobs = response.get('data', [])
            
            # Si la page est vide, on a fini
            if not jobs:
                break
                
            # On extrait la 'key' de chaque profil trouvé sur cette page
            for j in jobs:
                all_keys.append(j['key'])
                            
            # Si on a moins de 30 résultats, c'est qu'on est à la dernière page
            if len(jobs) < 30:
                break
                
            page += 1
        
        self.all_keys = all_keys
        return self.all_keys


    def send_job(self, job):
        url = "https://api.hrflow.ai/v1/job/indexing"

        payload = {"board_key": self.board_key, "job": job}
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        ref = job.get("reference", "?")
        print(f"Envoi indexation — reference (envoyée) : {ref!r}, name : {job.get('name', '')!r}")

        response = requests.post(url, json=payload, headers=headers)
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {}
        code = body.get("code", response.status_code)
        if code not in (200, 201) or response.status_code >= 400:
            print(f"Erreur indexation job HTTP {response.status_code} : {body}")
            return None

        data = body.get("data")
        k, r = None, None
        if isinstance(data, dict):
            nested = data.get("job") if isinstance(data.get("job"), dict) else data
            if isinstance(nested, dict):
                k = nested.get("key")
                r = nested.get("reference")
            if not k:
                k = data.get("key")
            if not r:
                r = data.get("reference")
        if k or r:
            print(f"Réponse API — job_key : {k!r}, reference : {r!r}")
        else:
            print(f"Réponse API (aperçu) : code={body.get('code')!r}, data keys={list(data) if isinstance(data, dict) else type(data)}")

        name = job.get("name") or job.get("reference", "?")
        print("sent OK ", name)

        return {"ok": True, "job_key": k, "reference": r, "raw": body}

    
    def archive_job(self, job_key):
        url = "https://api.hrflow.ai/v1/job/indexing/archive"

        payload = {"board_key": self.board_key, "job_key": job_key}

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        response = requests.patch(url, json=payload, headers=headers)
        print("archived ", job_key)


    def archive_all_jobs(self):
        for key in self.all_keys:
            self.archive_job(key)


    def nb_of_jobs(self, board_key=None):
        return len(self.all_keys)
    

    def parse_json_to_text(self, json_name):
        data = json.load(open(json_name, "r", encoding="utf-8"))

        def json_to_array_of_strings(data):
            result = []

            def extract(obj):
                if isinstance(obj, dict):
                    for v in obj.values():
                        extract(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract(item)
                elif isinstance(obj, str):
                    result.append(obj)

            extract(data)
            return result
        
        text = json_to_array_of_strings(data)
        single_text = "\n".join(text)
        return [single_text]


    def text_to_job(self, text):
        url = "https://api.hrflow.ai/v1/text/parsing"

        payload = {
            "texts": text,
            "parsing_model": "atlas",
            "output_object": "job"
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        response = requests.post(url, json=payload, headers=headers)
        return response


    def _prepare_job_for_indexing(self, job, json_name, raw_data):
        """
        Objet `job` conforme à POST /v1/job/indexing (doc HrFlow : `name` requis, `reference` optionnelle).

        - reference : toujours définie (JSON, sinon nom de fichier, sinon UUID).
        - name : obligatoire ; si absent après parsing texte, titre du JSON brut ou \"Job <reference>\".
        - key : retirée pour que l’API attribue une nouvelle clé interne à chaque indexation.
        """
        ref = None
        if isinstance(raw_data, dict):
            r = raw_data.get("reference")
            if r is not None and str(r).strip():
                ref = str(r).strip()
        if not ref:
            stem = os.path.splitext(os.path.basename(os.path.normpath(json_name)))[0]
            if stem and str(stem).strip():
                ref = str(stem).strip()
        if not ref:
            ref = f"job_{uuid.uuid4().hex}"
        job["reference"] = ref

        name = job.get("name")
        if not name or not str(name).strip():
            title = raw_data.get("title") if isinstance(raw_data, dict) else None
            if title and str(title).strip():
                job["name"] = str(title).strip()
            else:
                job["name"] = f"Job {ref}"

        # Pas de `key` à l'envoi : l'API HrFlow en attribue une nouvelle à l'indexation.
        job.pop("key", None)

    def send_json(self, json_name):
        """
        Indexe le JSON comme offre d'emploi. Retourne le dict renvoyé par send_job
        (clé `job_key` attribuée par l'API), ou None en cas d'échec.
        """
        with open(json_name, encoding="utf-8") as f:
            raw = json.load(f)
        text = self.parse_json_to_text(json_name)
        parsed = self.text_to_job(text)
        job = parsed.json()["data"][0]["job"]
        self._prepare_job_for_indexing(job, json_name, raw)
        return self.send_job(job)
    

    def send_text(self, text):
        parsed = self.text_to_job([text])
        job = parsed.json()["data"][0]["job"]
        self._prepare_job_for_indexing(job, "text.txt", [text])
        return self.send_job(job)


    def send_from_directory(self, directory_path):
        files = (os.listdir(directory_path))
        for file in files:  # json
            if file.endswith(".json"):
                self.send_json(os.path.join(directory_path, file))