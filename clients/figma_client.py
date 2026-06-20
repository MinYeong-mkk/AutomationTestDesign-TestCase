import os
import re
import base64
import requests


class FigmaClient:
    BASE_URL = "https://api.figma.com/v1"

    def __init__(self):
        self.token = os.getenv("FIGMA_API_TOKEN")
        if not self.token:
            raise ValueError("FIGMA_API_TOKEN 환경변수가 설정되지 않았어요. .env를 확인하세요.")
        self.headers = {"X-Figma-Token": self.token}

    # ── URL 파싱 ──────────────────────────────────────────────────────────────

    def parse_url(self, url: str) -> tuple:
        """Figma URL에서 (file_key, node_id or None) 추출"""
        m = re.search(r'/(?:file|design|proto)/([A-Za-z0-9]+)', url)
        file_key = m.group(1) if m else None

        n = re.search(r'node-id=([^&\s]+)', url)
        if n:
            raw = n.group(1)
            node_id = raw.replace('%3A', ':')
            # 숫자-숫자 패턴이면 - → : (Figma 최신 URL 포맷)
            if re.match(r'^\d+-\d+$', node_id):
                node_id = node_id.replace('-', ':')
        else:
            node_id = None

        return file_key, node_id

    # ── API 호출 ──────────────────────────────────────────────────────────────

    def get_file_meta(self, file_key: str) -> dict:
        """파일 최상위 구조 조회 (depth=2로 페이지+프레임만)"""
        r = requests.get(
            f"{self.BASE_URL}/files/{file_key}",
            headers=self.headers,
            params={"depth": 2}
        )
        r.raise_for_status()
        return r.json()

    def get_node(self, file_key: str, node_id: str) -> dict:
        """특정 노드 상세 조회"""
        r = requests.get(
            f"{self.BASE_URL}/files/{file_key}/nodes",
            headers=self.headers,
            params={"ids": node_id}
        )
        r.raise_for_status()
        return r.json()

    def get_image_urls(self, file_key: str, node_ids: list) -> dict:
        """노드 ID 목록 → {node_id: image_url} 렌더링 요청"""
        r = requests.get(
            f"{self.BASE_URL}/images/{file_key}",
            headers=self.headers,
            params={"ids": ",".join(node_ids), "format": "png", "scale": 1}
        )
        r.raise_for_status()
        return r.json().get("images", {})

    def download_as_base64(self, url: str) -> str:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return base64.b64encode(r.content).decode("utf-8")

    # ── 화면 목록 조회 ────────────────────────────────────────────────────────

    def get_top_level_frames(self, file_key: str) -> list:
        """파일 내 최상위 프레임/섹션 목록 반환"""
        data = self.get_file_meta(file_key)
        frames = []
        for page in data.get("document", {}).get("children", []):
            for child in page.get("children", []):
                if child.get("type") in ("FRAME", "COMPONENT", "SECTION"):
                    frames.append({
                        "id": child["id"],
                        "name": child["name"],
                        "page": page["name"]
                    })
        return frames

    # ── 메인 진입점 ───────────────────────────────────────────────────────────

    def fetch_screens(self, url_or_key: str, max_images: int = 5) -> list:
        """
        Figma URL 또는 file_key에서 화면 이미지를 가져와 base64 목록 반환.
        반환: [{description, url, image(base64)}]
        """
        if url_or_key.startswith("http"):
            file_key, node_id = self.parse_url(url_or_key)
        else:
            file_key, node_id = url_or_key, None

        if not file_key:
            raise ValueError("Figma file key를 URL에서 찾을 수 없어요.")

        # 특정 노드가 지정된 경우
        if node_id:
            print(f"  지정된 노드 조회 중: {node_id}")
            node_data = self.get_node(file_key, node_id)
            nodes = []
            for nid, info in node_data.get("nodes", {}).items():
                doc = info.get("document", {})
                nodes.append({"id": nid, "name": doc.get("name", nid), "page": ""})
        else:
            # 최상위 프레임 목록 조회 후 선택
            print("  Figma 파일 구조 읽는 중...")
            frames = self.get_top_level_frames(file_key)
            if not frames:
                print("  프레임을 찾을 수 없어요.")
                return []

            print(f"\n=== Figma 화면 목록 ({len(frames)}개) ===")
            for i, f in enumerate(frames[:30], 1):
                print(f"  {i}. [{f['page']}] {f['name']}")

            print(f"\n참고할 화면 번호 선택 (콤마로 여러 개, 전체는 0, 최대 {max_images}개)")
            choice = input("선택: ").strip()

            if choice == "0":
                nodes = frames[:max_images]
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
                    nodes = [frames[i] for i in indices if 0 <= i < len(frames)][:max_images]
                except (ValueError, IndexError):
                    print("  잘못된 선택입니다. Figma 화면 없이 진행합니다.")
                    return []

        if not nodes:
            return []

        # 이미지 렌더링 요청
        print(f"  이미지 렌더링 요청 중 ({len(nodes)}개)...")
        node_ids = [n["id"] for n in nodes]
        try:
            image_urls = self.get_image_urls(file_key, node_ids)
        except Exception as e:
            print(f"  이미지 URL 요청 실패: {e}")
            return []

        # 이미지 다운로드 + base64 변환
        screens = []
        for node in nodes:
            img_url = image_urls.get(node["id"])
            if not img_url:
                print(f"  이미지 없음: {node['name']}")
                continue
            print(f"  다운로드 중: {node['name']}")
            try:
                b64 = self.download_as_base64(img_url)
                screens.append({
                    "description": f"[{node.get('page', '')}] {node['name']}",
                    "url": img_url,
                    "image": b64
                })
            except Exception as e:
                print(f"  다운로드 실패 ({node['name']}): {e}")

        print(f"  Figma 화면 {len(screens)}개 로드 완료")
        return screens
