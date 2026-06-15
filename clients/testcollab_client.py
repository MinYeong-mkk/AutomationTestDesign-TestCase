import os
import requests

class TestCollabClient:
    def __init__(self):
        self.token = os.getenv("TESTCOLLAB_API_TOKEN")
        self.project_id = os.getenv("TESTCOLLAB_PROJECT_ID")
        self.base_url = "https://api.testcollab.io"

    def _params(self, extra: dict = {}) -> dict:
        return {"token": self.token, **extra}

    def get_suites(self) -> list:
        url = f"{self.base_url}/suites"
        response = requests.get(url, params=self._params({"project": self.project_id, "_limit": 100}))
        response.raise_for_status()
        return response.json()

    def create_test_case(self, title: str, description: str, pre_condition: str,
                          steps: list, suite_id: int = None, priority: str = "Normal") -> dict:
        url = f"{self.base_url}/testcases"
        priority_map = {"High": 1, "Normal": 2, "Low": 3}
        body = {
            "project": int(self.project_id),
            "title": title,
            "description": description,
            "priority": priority_map.get(priority, 2),
            "steps": [
                {"step": s.get("step", ""), "expected_result": s.get("expected_result", "")}
                for s in steps
            ],
            "custom_fields": [
                {
                    "id": 959,
                    "name": "Pre-Condition_editor",
                    "label": "Pre-Condition",
                    "value": pre_condition,
                    "valueLabel": pre_condition,
                    "color": ""
                }
            ]
        }
        if suite_id:
            body["suite"] = int(suite_id)

        response = requests.post(url, params=self._params(), json=body)
        response.raise_for_status()
        return response.json()