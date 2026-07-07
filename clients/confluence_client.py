import os
import re
from html import unescape
from html.parser import HTMLParser
from .base_client import BaseApiClient


class _StorageTextParser(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


class ConfluenceClient(BaseApiClient):

    def get_page_content(self, page_url: str) -> dict:
        return self.get_page_content_by_id(self._extract_page_id(page_url))

    def get_page_content_by_id(self, page_id: str) -> dict:
        data = self.get(
            f"{self.base_url}/wiki/rest/api/content/{page_id}",
            params={"expand": "body.storage"}
        )
        content = data["body"]["storage"]["value"]
        return {
            "title": data["title"],
            "content": content,
            "content_text": self.storage_to_text(content),
        }

    @staticmethod
    def storage_to_text(content: str) -> str:
        """Confluence storage XHTML을 AI가 읽기 쉬운 구조화 텍스트로 변환."""
        parser = _StorageTextParser()
        parser.feed(content or "")
        text = unescape("".join(parser.parts))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def get_child_pages(self, page_id: str) -> list:
        """하위 페이지 재귀 조회"""
        data = self.get(f"{self.base_url}/wiki/rest/api/content/{page_id}/child/page", params={"limit": 50})
        pages = []
        for child in data.get("results", []):
            pages.append({"id": child["id"], "title": child["title"]})
            pages.extend(self.get_child_pages(child["id"]))
        return pages

    def get_all_pages_content(self, root_page_id: str) -> str:
        """상위 페이지 + 모든 하위 페이지 내용 합치기"""
        all_pages = [{"id": root_page_id}] + self.get_child_pages(root_page_id)
        contents = []
        for p in all_pages:
            try:
                page = self.get_page_content_by_id(p["id"])
                contents.append(f"## {page['title']}\n{page['content']}")
                print(f"  읽는 중: {page['title']}")
            except Exception as e:
                print(f"  오류 ({p.get('title', p['id'])}): {e}")
        return "\n\n".join(contents)

    def create_page(self, space_key: str, title: str, content: str, parent_id: str = None) -> str:
        body = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": content, "representation": "storage"}}
        }
        if parent_id:
            body["ancestors"] = [{"id": parent_id}]
        data = self.post(f"{self.base_url}/wiki/rest/api/content", json=body)
        return data["_links"]["webui"]

    def find_page_link(self, space_key: str, title: str, parent_id: str = None) -> str:
        data = self.get(
            f"{self.base_url}/wiki/rest/api/content",
            params={
                "spaceKey": space_key,
                "title": title,
                "type": "page",
                "expand": "ancestors",
                "limit": 25,
            },
        )
        for page in data.get("results", []):
            if page.get("title") != title:
                continue
            if parent_id:
                ancestors = page.get("ancestors", [])
                if not any(str(item.get("id")) == str(parent_id) for item in ancestors):
                    continue
            return page.get("_links", {}).get("webui", "")
        return ""

    def _extract_page_id(self, url: str) -> str:
        parts = url.split("/pages/")
        if len(parts) > 1:
            return parts[1].split("/")[0]
        raise ValueError(f"페이지 ID를 URL에서 찾을 수 없어요: {url}")
