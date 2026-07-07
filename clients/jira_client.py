import os
import re
from .base_client import BaseApiClient


class JiraClient(BaseApiClient):

    def get_projects(self) -> list:
        data = self.get(f"{self.base_url}/rest/api/3/project")
        return [{"key": p["key"], "name": p["name"]} for p in data]

    def get_issues(self, jql: str, fields: list = None, max_results: int = 100) -> list:
        default_fields = "summary,description,status,priority,issuetype,assignee,reporter,created,resolutiondate"
        body = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields if fields else default_fields.split(",")
        }
        data = self.post(f"{self.base_url}/rest/api/3/search/jql", json=body)
        return data["issues"]

    def get_stories(self, jql_or_url: str, max_results: int = 100) -> list:
        """JQL 또는 Jira Board URL로 스토리 목록 조회 (제목만)"""
        jql = self._to_jql(jql_or_url)
        issues = self.get_issues(jql, fields=["summary", "status", "priority"], max_results=max_results)
        return [{"key": i["key"], "summary": i["fields"]["summary"]} for i in issues]

    def get_story_detail(self, issue_key: str) -> dict:
        """스토리 본문 상세 조회"""
        data = self.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            params={"fields": "summary,description,acceptance_criteria"}
        )
        fields = data["fields"]
        acceptance_criteria = fields.get("acceptance_criteria")
        return {
            "key": issue_key,
            "summary": fields.get("summary", ""),
            "description": self._extract_text(fields.get("description") or {}),
            "acceptance_criteria": (
                self._extract_text(acceptance_criteria)
                if isinstance(acceptance_criteria, dict)
                else str(acceptance_criteria or "")
            ),
        }

    def get_bugs(self, project_key: str, max_results: int = 100) -> list:
        jql = f"project = {project_key} AND issuetype = Bug ORDER BY created DESC"
        issues = self.get_issues(jql, fields=["summary", "description", "status", "priority"], max_results=max_results)
        return [self._parse_issue(i) for i in issues]

    def get_all_issues(self, project_key: str, max_results: int = 200) -> list:
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.get_issues(jql, max_results=max_results)

    def _to_jql(self, jql_or_url: str) -> str:
        """URL이면 JQL로 변환, 아니면 그대로 반환"""
        if not jql_or_url.startswith("http"):
            return self._normalize_jql(jql_or_url)

        # Board URL에서 필터/프로젝트 추출
        # 예: .../jira/software/projects/KEY/boards/...
        match = re.search(r"/projects/([A-Z]+)/", jql_or_url)
        if match:
            project_key = match.group(1)
            return f"project = {project_key} AND issuetype = Story ORDER BY created DESC"

        # rapidView(필터) 방식
        match = re.search(r"rapidView=(\d+)", jql_or_url)
        if match:
            return f"filter = {match.group(1)} AND issuetype = Story"

        raise ValueError(f"URL에서 프로젝트/필터를 찾을 수 없어요: {jql_or_url}")

    @staticmethod
    def _normalize_jql(jql: str) -> str:
        """사용자가 자주 입력하는 안전한 JQL 오타만 보정한다."""
        normalized = jql.strip()
        # `XJ AND ...` → `project = XJ AND ...`
        normalized = re.sub(
            r"^([A-Z][A-Z0-9_]*)\s+AND\b",
            r"project = \1 AND",
            normalized,
            flags=re.IGNORECASE,
        )
        # `createdDESC` → `created DESC` (updatedASC 등도 동일)
        normalized = re.sub(
            r"\b(created|updated|priority)(ASC|DESC)\b",
            r"\1 \2",
            normalized,
            flags=re.IGNORECASE,
        )
        return normalized

    def _parse_issue(self, issue: dict) -> dict:
        fields = issue["fields"]
        return {
            "key": issue["key"],
            "summary": fields.get("summary", ""),
            "description": self._extract_text(fields.get("description") or {}),
            "status": (fields.get("status") or {}).get("name", ""),
            "priority": (fields.get("priority") or {}).get("name", ""),
            "created": fields.get("created", ""),
        }

    def _extract_text(self, content: dict) -> str:
        """Jira ADF 전체 트리를 재귀 순회해 목록/표/중첩 문단까지 추출."""
        if not content:
            return ""
        parts = []
        block_types = {
            "paragraph", "heading", "listItem", "tableRow", "blockquote",
            "codeBlock", "panel",
        }

        def walk(node: dict) -> None:
            node_type = node.get("type", "")
            if node_type == "text":
                parts.append(node.get("text", ""))
                return
            if node_type == "hardBreak":
                parts.append("\n")
                return

            if node_type == "listItem":
                parts.append("- ")
            for child in node.get("content", []):
                walk(child)
            if node_type in block_types:
                parts.append("\n")

        walk(content)
        text = "".join(parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
