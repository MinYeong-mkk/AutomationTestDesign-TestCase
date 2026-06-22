import os
import json
from datetime import datetime
from .jira_client import JiraClient
from .confluence_client import ConfluenceClient
from .checklist_data import CHECKLIST_TEMPLATE, format_checklist
from .utils import ai_client as ai
from .utils.html_builder import build_test_design_page, build_tc_draft_page

# ── 1. AI 그룹 분류 ───────────────────────────────────────────────────────────

def classify_stories(stories: list) -> dict:
    """스토리 제목 목록을 AI가 기능 그룹으로 분류"""
    story_list = "\n".join(f"- [{s['key']}] {s['summary']}" for s in stories)
    prompt = f"""
아래 Jira 스토리 목록을 기능 단위로 그룹화해주세요.
비슷한 기능끼리 묶고, 그룹명은 간결하게 한글로 작성해주세요.

스토리 목록:
{story_list}

JSON 형식으로만 응답하세요:
{{
  "그룹명1": ["STORY-1", "STORY-2"],
  "그룹명2": ["STORY-3"]
}}
"""
    return ai.chat_json(prompt, max_tokens=2000)


# ── 2. TC 산출물 생성 ─────────────────────────────────────────────────────────

def generate_test_design_artifacts(stories: list, confluence_spec: str = "", figma_images: list = None) -> dict:
    stories_text = "\n\n".join(
        f"[{s.get('key', '')}] {s.get('summary', '')}\n{s.get('description', '(설명 없음)')}"
        for s in stories
    ) or "(Jira Story 없음)"

    spec_section = confluence_spec[:12000] if confluence_spec else "(Confluence Spec 없음)"
    checklist_text = format_checklist()
    checklist_total = len(CHECKLIST_TEMPLATE)

    figma_section = ""
    if figma_images:
        screen_names = "\n".join(f"- {img['description']}" for img in figma_images)
        figma_section = f"""
## Figma 화면 ({len(figma_images)}개 이미지 첨부됨)
{screen_names}

[Figma 이미지 분석 필수 지시]
- 첨부된 이미지에서 실제 버튼 레이블, 입력 필드명, 팝업 제목, 오류 메시지 문구를 직접 인용하여 TC Step에 사용할 것
- UI/UX 체크리스트 항목 평가 시 이미지에서 관찰된 실제 화면 구성을 근거로 작성할 것
- 화면에 보이는 플로우(버튼 클릭 → 다음 화면 → 결과)를 TC Step 흐름에 반영할 것
"""

    prompt = f"""
당신은 10년 이상 경력의 Senior QA Engineer입니다.
아래 입력 자료를 분석하여 고품질 Test Design 산출물을 작성하세요.
모든 출력은 한국어로 작성한다. 단, 제품명/버튼명/화면 문구/영문 스펙 문구는 원문 그대로 유지한다.

================================================
입력 자료
================================================

## Jira Story
{stories_text}

## Confluence Spec
{spec_section}
{figma_section}
## 회사 Checklist Template ({checklist_total}개)
{checklist_text}

================================================
[CRITICAL] Checklist 평가 규칙
================================================

**반드시 위 Checklist Template {checklist_total}개 항목을 빠짐없이 전부 평가해야 한다.**
- checklist_matrix 배열의 원소 수 = 정확히 {checklist_total}개
- 단 하나도 누락하면 안 된다
- 항목 추가/변경/병합 금지 — Template 원문 그대로 사용
- spec 정보가 부족한 항목은 spec_review_required=true, reason에 부족한 이유 기재
- 해당 없는 항목: applicable=false, reason="해당없음 - [구체적 사유]"
- 해당 항목: applicable=true, test_case_design에 구체적인 검증 방법 기재

각 항목 필수 필드:
  category / checklist / applicable / related_feature / reason / spec_review_required / test_case_design

================================================
[CRITICAL] TC Draft 작성 규칙
================================================

**tc_draft는 반드시 최소 10개 이상의 Scenario를 작성한다.**
- 입력 스토리가 복잡하거나 화면이 다양한 경우 15개 이상 작성
- 기능 단위 TC 생성 금지 — 실제 사용자의 End-to-End 업무 흐름으로 작성
- 하나의 Scenario는 반드시 8~15 Step으로 작성 (5개 이하 절대 금지)
- 각 Step은 "1. [구체적 행동]" 형태로 작성하고, expected_result도 구체적으로 기술
- Validation, Permission, Error Handling, Notification, Integration 등은 해당 Scenario에 자연스럽게 연관될 때만 Step에 포함
- Figma 이미지가 있으면 실제 화면의 버튼명/레이블/팝업을 Step에 직접 인용
- 실제 QA가 즉시 실행 가능한 수준으로 작성

================================================
문서 작성 규칙
================================================

1. Requirement Summary — 기능명, 목적, 영향 모듈, 사용자 유형, 변경 유형
2. Test Scope — In Scope / Out of Scope 명확히 구분 (각 최소 5개)
3. Checklist Matrix — {checklist_total}개 전체 평가
4. Risk Analysis — 최소 5개 이상, impact 근거 포함
5. Mindmap — Mermaid mindmap 문법, TC 대상 기능 중심
6. Flowchart — Mermaid flowchart TD, 주요 사용자 플로우 전체 표현
7. TC Draft — 최소 10개 Scenario

================================================
출력 규칙
================================================

JSON 외 텍스트 출력 금지.
반드시 아래 스키마 JSON으로만 응답한다.

{{
  "style_mode": "detailed",
  "split_recommendation": {{
    "required": false,
    "reason": ""
  }},
  "requirement_summary": {{
    "feature_name": "",
    "purpose": "",
    "affected_modules": [],
    "user_types": [],
    "change_type": ""
  }},
  "test_scope": {{
    "in_scope": [],
    "out_scope": []
  }},
  "checklist_matrix": [
    {{
      "category": "Functional",
      "checklist": "",
      "applicable": true,
      "related_feature": "",
      "reason": "",
      "spec_review_required": false,
      "test_case_design": ""
    }}
  ],
  "risk_analysis": [
    {{
      "risk": "",
      "impact": "High",
      "mitigation": ""
    }}
  ],
  "mindmap_mermaid": "",
  "flowchart_mermaid": "",
  "tc_draft": [
    {{
      "scenario": "",
      "description": "",
      "priority": "High",
      "pre_condition": [],
      "jira_keys": [],
      "test_data": [],
      "note": "",
      "steps": [
        {{
          "step": "",
          "expected_result": ""
        }}
      ]
    }}
  ]
}}
"""

    return ai.chat_json(prompt, max_tokens=16000, images=figma_images or None)

def normalize_test_design_artifacts(artifacts: dict) -> dict:
    if not isinstance(artifacts, dict):
        return {}

    if isinstance(artifacts.get("requirement_summary"), str):
        artifacts["requirement_summary"] = {
            "feature_name": "",
            "purpose": artifacts["requirement_summary"],
            "affected_modules": [],
            "user_types": [],
            "change_type": ""
        }

    scope = artifacts.get("test_scope", {})

    if isinstance(scope, str):
        artifacts["test_scope"] = {
            "in_scope": [scope],
            "out_scope": []
        }
    elif isinstance(scope, list):
        artifacts["test_scope"] = {
            "in_scope": scope,
            "out_scope": []
        }
    elif not isinstance(scope, dict):
        artifacts["test_scope"] = {
            "in_scope": [],
            "out_scope": []
        }

    if isinstance(artifacts.get("split_recommendation"), bool):
        artifacts["split_recommendation"] = {
            "required": artifacts["split_recommendation"],
            "reason": "",
            "suggested_documents": []
        }
    elif isinstance(artifacts.get("split_recommendation"), str):
        artifacts["split_recommendation"] = {
            "required": True,
            "reason": artifacts["split_recommendation"],
            "suggested_documents": []
        }

    risk = artifacts.get("risk_analysis", [])

    if isinstance(risk, str):
        artifacts["risk_analysis"] = [
            {
                "risk": risk,
                "impact": "Medium",
                "mitigation": ""
            }
        ]
    elif isinstance(risk, list):
        artifacts["risk_analysis"] = [
            r if isinstance(r, dict) else {
                "risk": str(r),
                "impact": "Medium",
                "mitigation": ""
            }
            for r in risk
        ]
    else:
        artifacts["risk_analysis"] = []

    if not isinstance(artifacts.get("checklist_matrix"), (dict, list)):
        artifacts["checklist_matrix"] = []

    fixed_tcs = []
    for i, tc in enumerate(artifacts.get("tc_draft", []), 1):
        if not isinstance(tc, dict):
            continue

        steps = tc.get("steps", [])
        if not isinstance(steps, list) or not steps:
            steps = [{
                "step": "1. 테스트를 수행한다.",
                "expected_result": "1. 기대 결과가 확인된다."
            }]

        fixed_tcs.append({
            "id": f"TC-{i:03d}",
            "title": tc.get("scenario") or tc.get("title") or tc.get("description", ""),
            "priority": tc.get("priority", "Normal"),
            "description": tc.get("description", ""),
            "pre_condition": tc.get("pre_condition", []),
            "test_data": tc.get("test_data", []),
            "note": tc.get("note", ""),
            "steps": steps
        })

    artifacts["tc_draft"] = fixed_tcs

    return artifacts

# ── 3. 입력 수집 / 그룹 처리 ─────────────────────────────────────────────────

def _load_confluence_specs(confluence: ConfluenceClient) -> str:
    print("\nConfluence 스펙 페이지 URL 입력 (빈 줄로 완료):")
    contents = []
    while True:
        url = input("URL: ").strip()
        if not url:
            break
        try:
            page = confluence.get_page_content(url)
            contents.append(f"## {page['title']}\n{page['content']}")
            print(f"  로드 완료: {page['title']} ({len(page['content'])}자)")
        except Exception as e:
            print(f"  로드 실패 (계속 진행): {e}")
    return "\n\n".join(contents)


# ── 4-1. Figma 화면 로드 헬퍼 ────────────────────────────────────────────────

def _load_figma_screens() -> list:
    from .figma_client import FigmaClient
    try:
        figma = FigmaClient()
    except ValueError as e:
        print(f"  Figma 연결 불가: {e}")
        return []

    print("\nFigma 파일 URL 또는 file_key 입력:")
    print("예시: https://www.figma.com/design/ABC123/My-File?node-id=1-2")
    url = input("Figma URL: ").strip()
    if not url:
        return []

    try:
        return figma.fetch_screens(url)
    except Exception as e:
        print(f"  Figma 로드 실패 (계속 진행): {e}")
        return []


# ── 5. 메인 파이프라인 ────────────────────────────────────────────────────────

def _collect_inputs(jira: JiraClient, confluence: ConfluenceClient) -> tuple:
    """사용자 입력 수집. (figma_images, confluence_spec, stories) 반환."""
    figma_images = []
    if input("Figma 화면을 참고할까요? (y/n): ").strip().lower() == "y":
        figma_images = _load_figma_screens()

    confluence_spec = ""
    if input("\nConfluence 스펙 페이지를 참고할까요? (y/n): ").strip().lower() == "y":
        confluence_spec = _load_confluence_specs(confluence)

    stories = []
    if input("\nJira 스토리도 참고할까요? (y/n): ").strip().lower() == "y":
        print("Jira Board URL 또는 JQL 입력:")
        print("예시 JQL: project = MYPROJ AND issuetype = Story AND sprint in openSprints()")
        jql_or_url = input("입력: ").strip()
        if jql_or_url:
            print("\n스토리 조회 중...")
            stories = jira.get_stories(jql_or_url)
            print(f"총 {len(stories)}개 스토리 조회됨")

    return figma_images, confluence_spec, stories


def _process_group(
    group_name: str,
    group_stories: list,
    confluence_spec: str,
    figma_images: list,
    confluence: ConfluenceClient,
    space_key: str,
    parent_id: str,
) -> None:
    """그룹 하나에 대한 AI 생성 + Confluence 저장."""
    print(f"\n[{group_name}] 처리 중...")
    print("  AI Test Design 생성 중...")

    artifacts = generate_test_design_artifacts(group_stories, confluence_spec, figma_images or None)
    artifacts = normalize_test_design_artifacts(artifacts)

    print("\n========== AI RESULT ==========")
    print(json.dumps(artifacts, indent=2, ensure_ascii=False))
    print("========== END ==========\n")

    checklist_matrix = artifacts.get("checklist_matrix", {})
    checklist_count = (
        sum(len(items) for items in checklist_matrix.values())
        if isinstance(checklist_matrix, dict)
        else len(checklist_matrix)
    )
    tc_draft = artifacts.get("tc_draft", [])
    print(f"  → Checklist {checklist_count}개 / TC Draft {len(tc_draft)}개 생성")

    if input("  Confluence에 저장할까요? (y/n): ").strip().lower() != "y":
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    design_link = confluence.create_page(
        space_key,
        f"[Test Design] {group_name} ({now})",
        build_test_design_page(group_name, group_stories, artifacts),
        parent_id=parent_id,
    )
    tc_link = confluence.create_page(
        space_key,
        f"[TC Draft] {group_name} ({now})",
        build_tc_draft_page(group_name, group_stories, artifacts),
        parent_id=parent_id,
    )

    print(f"  ✓ Test Design 저장 완료: {design_link}")
    print(f"  ✓ TC Draft 저장 완료: {tc_link}")


def run_tc_pipeline():
    print("\n=== TC 산출물 생성 ===")

    jira = JiraClient()
    confluence = ConfluenceClient()
    space_key = os.getenv("CONFLUENCE_SPACE_KEY")
    parent_id = os.getenv("CONFLUENCE_PARENT_PAGE_ID")

    figma_images, confluence_spec, stories = _collect_inputs(jira, confluence)

    if not stories and not confluence_spec and not figma_images:
        print("Figma / Confluence 스펙 / Jira 스토리 중 하나는 입력해야 해요.")
        return

    if stories:
        print("\nAI가 기능 그룹 분류 중...")
        groups = classify_stories(stories)
        group_list = list(groups.items())

        print("\n=== 분류된 그룹 ===")
        for i, (name, keys) in enumerate(group_list, 1):
            print(f"  {i}. {name} ({len(keys)}개): {', '.join(keys)}")

        choice = input("\n작업할 그룹 번호 선택 (전체는 0): ").strip()
        selected_groups = group_list if choice == "0" else [group_list[int(choice) - 1]]
    else:
        selected_groups = [("스펙 기반 TC", [])]

    for group_name, keys in selected_groups:
        group_stories = []
        if keys:
            key_set = set(keys)
            print(f"  스토리 본문 조회 중 ({len(key_set)}개)...")
            for s in [s for s in stories if s["key"] in key_set]:
                try:
                    group_stories.append(jira.get_story_detail(s["key"]))
                except Exception as e:
                    print(f"  {s['key']} 조회 실패: {e}")
                    group_stories.append(s)

        _process_group(group_name, group_stories, confluence_spec, figma_images, confluence, space_key, parent_id)

    print("\n=== 완료 ===")
