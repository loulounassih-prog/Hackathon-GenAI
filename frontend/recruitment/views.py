import os
from django.shortcuts import render
from hrflow import Hrflow
from dotenv import load_dotenv

load_dotenv()

# Initialize the HrFlow Client with the API Secret from the environment
API_SECRET = os.getenv("HRFLOW_API_SECRET", "YOUR_HRFLOW_API_SECRET")
BOARD_KEY = os.getenv("HRFLOW_BOARD_KEY", "YOUR_HRFLOW_BOARD_KEY")
SOURCE_KEY = os.getenv("HRFLOW_SOURCE_KEY", "YOUR_HRFLOW_SOURCE_KEY")

try:
    client = Hrflow(api_secret=API_SECRET)
except Exception as e:
    client = None
    print(f"Failed to initialize HrFlow client: {e}")

def home(request):
    """View to list both Jobs and Applicants on the homepage."""
    jobs = []
    profiles = []
    error = None

    if not client:
        error = "HrFlow client not initialized. Check your HRFLOW_API_SECRET."
        return render(request, 'recruitment/home.html', {'jobs': jobs, 'profiles': profiles, 'error': error})

    try:
        # Fetch Jobs from the board
        jobs_response = client.job.searching.list(board_keys=[BOARD_KEY], limit=10, sort_by='created_at', order_by='desc')
        if jobs_response.get('code') == 200:
            jobs = jobs_response.get('data', {}).get('jobs', [])

        # Fetch Profiles (Applicants) from the source
        profiles_response = client.profile.searching.list(source_keys=[SOURCE_KEY], limit=10, sort_by='created_at', order_by='desc')
        if profiles_response.get('code') == 200:
            profiles = profiles_response.get('data', {}).get('profiles', [])

    except Exception as e:
        error = f"Error fetching data from HrFlow: {str(e)}"

    return render(request, 'recruitment/home.html', {
        'jobs': jobs,
        'profiles': profiles,
        'error': error
    })
