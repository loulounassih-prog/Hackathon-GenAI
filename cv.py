import os
import json
from hrflow import Hrflow
import requests



class CVManager:
    def __init__(self, SOURCE_KEY, API_KEY, API_USER):
        self.source_key = SOURCE_KEY
        self.api_key = API_KEY
        self.api_user = API_USER
        self.client = Hrflow(api_secret=self.api_key, api_user=self.api_user)
        self.all_keys = self.get_all_keys()


    def send_resume_pdf(self, file_name):
        url = "https://api.hrflow.ai/v1/profile/parsing/file"

        headers = {
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        files = {
            "file": open(file_name, "rb")
        }

        data = {
            "source_key": self.source_key
        }

        response = requests.post(url, headers=headers, files=files, data=data)
        print("sent ", file_name)
        # data = response.json()['data']
        # print(response.text)

    
    def send_profile(self, profile):
        url = "https://api.hrflow.ai/v1/profile/indexing"

        payload = {
            "profile": profile,
            "source_key": self.source_key
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        response = requests.post(url, json=payload, headers=headers)

    # prend en argument un fichier json et retourne un tableau de strings
    def parse_json_to_text(self, json_name):
        data = json.load(open(json_name, "r"))

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
        
        texts = json_to_array_of_strings(data)
        single_text = "\n".join(texts)
        return [single_text]


    def texts_to_profile(self, texts):
        url = "https://api.hrflow.ai/v1/text/parsing"

        payload = {
            "texts": texts,
            "parsing_model": "atlas",
            "output_object": "profile"
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        response = requests.post(url, json=payload, headers=headers)
        return response


    def archive_profile(self, profile_key, source_key=None):
        source_key = source_key or self.source_key

        url = "https://api.hrflow.ai/v1/profile/indexing/archive"

        payload = {
            "source_key": source_key,
            "key": profile_key
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        response = requests.patch(url, json=payload, headers=headers)
        print("archived ", profile_key)


    def archive_all_profiles(self):
        for key in self.all_keys:
            self.archive_profile(key)

    def get_all_keys(self, source_key=None):
        source_key = source_key or self.source_key
        all_keys = []
        page = 1
        
        while True:
            # Rappel : 'source_keys' au pluriel et dans une liste []
            response = self.client.profile.storing.list(
                source_keys=[source_key], 
                limit=30, 
                page=page
            )
            
            if response['code'] != 200:
                print(f"Erreur : {response['message']}")
                break
                
            profiles = response.get('data', [])
            
            # Si la page est vide, on a fini
            if not profiles:
                break
                
            # On extrait la 'key' de chaque profil trouvé sur cette page
            for p in profiles:
                all_keys.append(p['key'])
                            
            # Si on a moins de 30 résultats, c'est qu'on est à la dernière page
            if len(profiles) < 30:
                break
                
            page += 1
        
        self.all_keys = all_keys
        return self.all_keys    

    
    def nb_of_profiles(self, source_key=None):
        return len(self.all_keys)


    def parse_resume(self, profile_key):
        
        url = f"https://api.hrflow.ai/v1/profile/parsing?source_key={self.source_key}&key={profile_key}"


        headers = {
            "accept": "application/json",
            "X-API-KEY": self.api_key,
            "X-USER-EMAIL": self.api_user
        }

        response = requests.get(url, headers=headers)
        print("parsed ", profile_key)
        return response.json()

    def send_json(self, json_name):

        texts = self.parse_json_to_text(json_name)
        parsed = self.texts_to_profile(texts)
        profile = parsed.json()['data'][0]['profile']
        self.send_profile(profile)
        print("sent ", json_name)