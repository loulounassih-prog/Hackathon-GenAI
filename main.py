from cv import CVManager
import time as t
from dotenv import load_dotenv
import os
import json


load_dotenv()
SOURCE_KEY = os.getenv("SOURCE_KEY")
API_KEY = os.getenv("API_KEY")
API_USER = os.getenv("API_USER")


manager = CVManager(SOURCE_KEY, API_KEY, API_USER)

manager.archive_all_profiles()

manager.send_json("cv.json")