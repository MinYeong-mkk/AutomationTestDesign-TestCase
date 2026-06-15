import os
import requests
from requests.auth import HTTPBasicAuth


class BaseApiClient:
    """Jira/Confluence 공통 인증 베이스"""

    def __init__(self):
        self.base_url = os.getenv("JIRA_URL").rstrip("/")
        self.auth = HTTPBasicAuth(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def get(self, url: str, **kwargs) -> dict:
        response = requests.get(url, auth=self.auth, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response.json()

    def post(self, url: str, **kwargs) -> dict:
        response = requests.post(url, auth=self.auth, headers=self.headers, **kwargs)

        if response.status_code >= 400:
            print("\n=== API ERROR ===")
            print("URL:", url)
            print("STATUS:", response.status_code)
            print("RESPONSE:", response.text[:5000])
            print("=================\n")

        response.raise_for_status()
        return response.json()
