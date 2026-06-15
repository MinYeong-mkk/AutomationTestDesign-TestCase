import os
from datetime import datetime
from .jira_client import JiraClient
from .confluence_client import ConfluenceClient
from .utils import ai_client as ai
from .utils.html_builder import page_header, section, table


def run_duplicate_detector():
    print("\n=== 중복 버그 탐지 ===")

    jira = JiraClient()
    projects = jira.get_projects()

    print("\n프로젝트 목록:")
    for i, p in enumerate(projects, 1):
        print(f"  {i}. [{p['key']}] {p['name']}")

    project = projects[int(input("\n분석할 프로젝트 번호 선택: ").strip()) - 1]

    print(f"\n{project['name']} 버그 가져오는 중...")
    bugs = jira.get_bugs(project["key"], max_results=100)
    print(f"총 {len(bugs)}개 버그 분석 중...")

    groups = _analyze_duplicates(bugs)

    print(f"\n=== 분석 결과: {len(groups)}개 그룹 ===")
    for g in groups:
        print(f"\n[{g['group_name']}]")
        print(f"  이슈: {', '.join(g['keys'])}")
        print(f"  공통 원인: {g['cause']}")

    if input("\nConfluence에 저장할까요? (y/n): ").strip().lower() != "y":
        return

    confluence = ConfluenceClient()
    title = f"[중복버그] {project['name']} - {datetime.now().strftime('%Y-%m-%d')}"
    link = confluence.create_page(
        os.getenv("CONFLUENCE_SPACE_KEY"),
        title,
        _build_page(groups, project["name"])
    )
    print(f"\nConfluence 페이지 생성 완료: {link}")


def _analyze_duplicates(bugs: list) -> list:
    import json
    bugs_text = json.dumps(
        [{"key": b["key"], "summary": b["summary"], "description": b["description"][:500]} for b in bugs],
        ensure_ascii=False
    )
    prompt = f"""
QA 엔지니어로서 아래 버그 목록에서 중복/동일 원인 버그를 그룹화해주세요.
제목이 아닌 Description과 문제 유형 기준으로 판단하고, 애매한 건 "검토 필요"로 분리하세요.

{bugs_text}

JSON 배열로만 응답:
[{{"group_name": "그룹명", "keys": ["KEY-1"], "cause": "원인", "pattern": "재현 패턴"}}]
"""
    return ai.chat_json(prompt, max_tokens=2000)


def _build_page(groups: list, project_name: str) -> str:
    rows = []
    for g in groups:
        rows.append([g["group_name"], ", ".join(g["keys"]), g["cause"], g.get("pattern", "-")])

    return (
        page_header(f"🔍 {project_name} 중복 버그 분석")
        + section("분석 결과", table(["그룹명", "이슈 키", "공통 원인", "재현 패턴"], rows))
    )
