import os
import json
from datetime import datetime
from .jira_client import JiraClient
from .confluence_client import ConfluenceClient
from .utils import ai_client as ai
from .utils.html_builder import page_header, section, table, info_panel

#----CheckList Template-----
CHECKLIST_TEMPLATE = [
    # Functional
    ("Functional", "요청한 기능이 지정된 동작을 정확히 수행하는가?"),
    ("Functional", "입력값에 따른 출력값이 정확하게 일치하는가?"),
    ("Functional", "사용자 유형에 따른 화면 노출/기능 제한이 정확히 적용되는가?"),
    ("Functional", "이벤트 발생이 명확한 조건으로 정확하게 발생하는가?"),
    ("Functional", "실무에서 예상되는 케이스가 모두 반영되어 있는가?"),
    ("Functional", "요구된 모든 기능이 누락 없이 구현되었는가?"),

    # Non-Functional
    ("Non-Functional", "응답 시간이 요구 성능 기준을 충족하는가?"),
    ("Non-Functional", "동시 사용자 수 증가 시 성능 저하 없이 동작하는가?"),
    ("Non-Functional", "대용량 데이터 처리 시에도 시스템 처리 성능이 저하되지 않는가?"),
    ("Non-Functional", "인증 및 권한 검증이 적절히 수행되는가?"),
    ("Non-Functional", "암호화된 데이터 전송이 이루어지는가?"),
    ("Non-Functional", "세션 관리 및 만료 처리가 적절한가?"),
    ("Non-Functional", "오류 발생 시 시스템이 자동 복구 가능한가?"),
    ("Non-Functional", "외부 시스템 장애 시 대응이 적절한가?"),

    # UI/UX
    ("UI/UX", "사용자가 기능을 이해할 수 있도록, 필요한 위치에 명확하고 일관된 안내 정보가 제공되는가?"),
    ("UI/UX", "메뉴/버튼의 의미가 명확하고 직관적인가?"),
    ("UI/UX", "필수 입력 항목이 시각적으로 잘 구분되는가?"),
    ("UI/UX", "아이콘 및 버튼(폰트, 색상, 정렬 등)이 일관적으로 통일되어 있는가?"),
    ("UI/UX", "디자인이 화면 해상도별로 동일한 시각 체계를 제공하는가?"),

    # Integration
    ("Integration", "모듈 간 데이터가 정상적으로 전달되는가?"),
    ("Integration", "데이터 중복이나 손실 없이 처리되는가?"),
    ("Integration", "외부 시스템 연동 시 데이터 일관성이 유지되는가?"),
    ("Integration", "시스템 구성 요소 변경 시, 통합 시스템의 기능 흐름에 정상 반영되는가?"),

    # Common
    ("Common", "버그 수정 후에도 기존 오류가 재발하지 않는가?"),
    ("Common", "테스트 자동화를 통해 반복 회귀 검증이 수행되는가?"),
    ("Common", "수정된 기능 외 다른 기능에 영향이 없는가?"),
    ("Common", "다양한 운영체제에서 기능의 차이 없이 동작하는가?"),
    ("Common", "다양한 모바일 환경에서 기능의 차이 없이 동작하는가?"),
    ("Common", "다양한 브라우저에서 기능의 차이 없이 동작하는가?"),
    ("Common", "다양한 입력 도구(터치, 키보드 등)에서 잘 동작하는가?"),
    ("Common", "요청 API가 명세서대로 응답 형식과 코드를 반환하는가?"),
    ("Common", "필수 파라미터 누락 시, 적절한 오류 반환이 이루어지는가?"),
    ("Common", "API 호출 실패 시, 적절한 오류 코드와 메시지를 반환하는가?"),

    # Exceptional Handling
    ("Exceptional Handling", "필수 항목이 빠진 상태에서 저장 또는 제출 시, 사용자에게 명확한 오류 메시지가 제공되는가?"),
    ("Exceptional Handling", "비정상 입력값에 대해 유효성 검사 및 오류 메시지가 제공되는가?"),
    ("Exceptional Handling", "데이터 처리 중 예외 발생 시, 전체 시스템이 중단되지 않고 안정적으로 동작을 유지하는가?"),

    # Technical Quality Assurance
    ("Technical Quality Assurance", "일정 트래픽 이상 시 서버가 안정적으로 처리 가능한가?"),
    ("Technical Quality Assurance", "대규모 요청으로 지속적인 부하 발생 시, 시스템 응답이 지연 없이 처리되는가?"),
    ("Technical Quality Assurance", "서버 오류 발생 시 자동 리트라이 또는 대체 처리 흐름이 있는가?"),
    ("Technical Quality Assurance", "불안정한 네트워크 환경에서 오류 없이 작동하는가?"),
    ("Technical Quality Assurance", "네트워크 비연결 상태에서도 기능이 적절히 제한되는가?"),
    ("Technical Quality Assurance", "연결 해제 후 복원 시 세션이나 데이터가 손상되지 않는가?"),
    ("Technical Quality Assurance", "동기화 기능이 불안정한 상황에서도 데이터 유실 없이 처리되는가?"),
    ("Technical Quality Assurance", "다른 앱과 동시 실행 시 앱 충돌이나 동작 오류가 없는가?"),
]


def _format_checklist_template() -> str:
    return "\n".join(
        f"- [{category}] {item}"
        for category, item in CHECKLIST_TEMPLATE
    )

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
    return ai.chat_json(prompt)


# ── 2. TC 산출물 생성 ─────────────────────────────────────────────────────────

def generate_test_design_artifacts(stories: list, confluence_spec: str = "") -> dict:
    stories_text = "\n\n".join(
        f"[{s.get('key', '')}] {s.get('summary', '')}\n{s.get('description', '(설명 없음)')}"
        for s in stories
    ) or "(Jira Story 없음)"

    spec_section = confluence_spec[:6000] if confluence_spec else "(Confluence Spec 없음)"
    checklist_text = _format_checklist_template()

    prompt = f"""
    당신은 Senior QA Engineer입니다.
    회사 Test Design Template 기준으로
    요구사항 분석 및 테스트 설계를 수행하세요.
    모든 출력은 한국어로 작성한다. 단, 제품명/버튼명/화면 문구/영문 스펙 문구는 원문 그대로 유지한다.

    출력 분량 규칙
    - Checklist Template의 모든 항목을 평가한다.
    - 해당 없는 경우:
    applicable=false
    reason="해당없음 - 사유"

    - tc_draft는 기능 복잡도에 따라 작성한다.
    - 복합 기능(AuraVue, 결제, 구독, 외부 연동 등)은 Scenario 단위로 작성한다.

    ## Jira Story
    {stories_text}

    ## Confluence Spec
    {spec_section}

    ## 회사 Checklist Template
    {checklist_text}

    ==================================================
    Checklist 평가 규칙
    ==================================================

    - spec 정보가 부족하면 spec_review_required=true
    - checklist_matrix는 리스트로 작성한다.
    - 추가 Checklist 생성 금지

    각 항목은 반드시 아래 필드를 포함한다.

    category
    checklist
    applicable
    related_feature
    reason
    spec_review_required
    test_case_design

    ==================================================
    문서 작성 규칙
    ==================================================

    1. Requirement Summary
    2. Test Scope
    3. Checklist Matrix
    4. Risk Analysis
    5. Mindmap
    6. Flowchart
    7. TC Draft

    ==================================================
    Mindmap 규칙
    ==================================================

    - Mermaid mindmap 문법 사용
    - 실제 TC 작성 대상만 포함

    ==================================================
    Flowchart 규칙
    ==================================================

    - Mermaid flowchart TD 사용
    - 주요 사용자 플로우만 표현

    ==================================================
    TC Draft 규칙
    ==================================================

    - 기능 단위 TC 생성 금지
    - 실제 사용자의 End-to-End 업무 흐름으로 작성한다.
    - 하나의 Scenario는 일반적으로 8~15 Step으로 작성한다.
    - Notification, Email, Validation, Permission, Error Handling, Integration 검증을 Scenario 내부 Step에 포함한다.
    - 실제 QA가 즉시 실행 가능한 수준으로 작성한다.
    - TestCollab 업로드 가능한 수준으로 작성한다.

    ==================================================
    출력 규칙
    ==================================================

    JSON 외 텍스트 출력 금지
    반드시 아래 스키마와 동일한 JSON으로 응답한다.

    style_mode
    split_recommendation
    requirement_summary
    test_scope
    checklist_matrix
    risk_analysis
    mindmap_mermaid
    flowchart_mermaid
    tc_draft

    JSON 예시

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

    return ai.chat_json(prompt, max_tokens=8000)

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

# ── 3. Confluence 페이지 빌더 ─────────────────────────────────────────────────

def build_test_design_page(group_name: str, stories: list, artifacts: dict) -> str:
    summary = artifacts.get("requirement_summary", {})
    if isinstance(summary, str):
        summary = {
            "feature_name": group_name,
            "purpose": summary,
            "change_type": "",
            "affected_modules": [],
            "user_types": [],
        }

    scope = artifacts.get("test_scope", {})

    if isinstance(scope, str):
        scope = {
            "in_scope": [scope],
            "out_scope": [],
        }
    elif isinstance(scope, list):
        scope = {
            "in_scope": scope,
            "out_scope": [],
        }
    elif not isinstance(scope, dict):
        scope = {
            "in_scope": [],
            "out_scope": [],
        }

    split = artifacts.get("split_recommendation", {})
    if isinstance(split, bool):
        split = {
            "required": split,
            "reason": "",
            "suggested_documents": [],
        }
    elif isinstance(split, str):
        split = {
            "required": True,
            "reason": split,
            "suggested_documents": [],
        }

    summary_html = f"""
<p><strong>기능명:</strong> {summary.get("feature_name", "")}</p>
<p><strong>목적:</strong> {summary.get("purpose", "")}</p>
<p><strong>변경 유형:</strong> {summary.get("change_type", "")}</p>
<p><strong>영향 모듈:</strong> {", ".join(summary.get("affected_modules", []))}</p>
<p><strong>사용자 유형:</strong> {", ".join(summary.get("user_types", []))}</p>
"""

    scope_html = f"""
<h4>In Scope</h4>
<ul>
{''.join(f"<li>{item}</li>" for item in scope.get("in_scope", []))}
</ul>

<h4>Out of Scope</h4>
<ul>
{''.join(f"<li>{item}</li>" for item in scope.get("out_scope", []))}
</ul>
"""

    split_html = f"""
<p><strong>Style Mode:</strong> {artifacts.get("style_mode", "")}</p>
<p><strong>분리 필요:</strong> {"Y" if split.get("required") else "N"}</p>
<p><strong>사유:</strong> {split.get("reason", "")}</p>
<ul>
{''.join(f"<li>{item}</li>" for item in split.get("suggested_documents", []))}
</ul>
"""

    story_rows = [[s.get("key", ""), s.get("summary", "")] for s in stories]
    story_table = table(["스토리 키", "제목"], story_rows) if story_rows else "<p>Jira Story 없음</p>"

    checklist_rows = []
    checklist_matrix = artifacts.get("checklist_matrix", {})

    if isinstance(checklist_matrix, dict):
        for category, items in checklist_matrix.items():
            for item in items:
                checklist_rows.append([
                    category,
                    item.get("checklist") or item.get("item", ""),
                    "Y" if item.get("applicable", item.get("evaluation", False)) else "N",
                    item.get("related_feature", ""),
                    item.get("reason", ""),
                    "Y" if item.get("spec_review_required", False) else "N",
                    item.get("test_case_design", "")
                ])
    else:
        for item in checklist_matrix:
            checklist_rows.append([
                item.get("category", ""),
                item.get("checklist", ""),
                "Y" if item.get("applicable", False) else "N",
                item.get("related_feature", ""),
                item.get("reason", ""),
                "Y" if item.get("spec_review_required", False) else "N",
                item.get("test_case_design", "")
            ])

    checklist_table = table(
        [
            "필수 요소",
            "체크리스트",
            "적용",
            "관련 기능",
            "미적용 사유/판단 사유",
            "Spec 검토 필요",
            "Test Case 구성 정보"
        ],
        checklist_rows
    )

    coverage_rows = [
        [
            c.get("feature", ""),
            c.get("checklist_category", ""),
            c.get("test_type", ""),
            c.get("tc_id", "")
        ]
        for c in artifacts.get("coverage_matrix", [])
    ]

    coverage_table = table(
        ["Feature", "Checklist Category", "Test Type", "TC ID"],
        coverage_rows
    ) if coverage_rows else "<p>Coverage Matrix 없음</p>"

    risk_rows = [
        [
            r.get("risk", ""),
            r.get("impact", ""),
            r.get("mitigation", "")
        ]
        for r in artifacts.get("risk_analysis", [])
    ]

    risk_table = table(
        ["Risk", "Impact", "Mitigation"],
        risk_rows
    ) if risk_rows else "<p>Risk 없음</p>"

    mindmap = artifacts.get("mindmap_mermaid", "")
    flowchart = artifacts.get("flowchart_mermaid", "")

    output_html = f"""
<h4>Mindmap Mermaid</h4>
<pre>{mindmap}</pre>

<h4>Flowchart Mermaid</h4>
<pre>{flowchart}</pre>
"""

    return (
        page_header(f"[Test Design] {group_name}", "회사 Test Design Template 기반 자동 생성")
        + section("문서 정보", "<p><strong>담당자:</strong> </p><p><strong>작성일/최종 수정일:</strong> </p>")
        + section("테스트 개요", summary_html)
        + section("Test Scope", scope_html)
        + section("문서 분리 판단", split_html)
        + section("Jira 정보", story_table)
        + section("Test Case 설계", checklist_table)
        + section("Coverage Matrix", coverage_table)
        + section("Risk Analysis", risk_table)
        + section("산출물", output_html)
        + info_panel("AI가 생성한 Test Design 초안입니다. QA 검토 후 최종 확정하세요.")
    )

def build_tc_draft_page(group_name: str, stories: list, artifacts: dict) -> str:
    tc_rows = []

    for tc in artifacts.get("tc_draft", []):
        pre_condition = tc.get("pre_condition", "")
        if isinstance(pre_condition, list):
            pre_condition = "<br/>".join(pre_condition)

        steps = tc.get("steps", [])
        if not steps:
            tc_rows.append([
                tc.get("title", ""),
                "",
                pre_condition,
                "",
                "",
                tc.get("description", ""),
                ""
            ])
            continue

        for idx, step in enumerate(steps):
            tc_rows.append([
                tc.get("title", "") if idx == 0 else "",
                tc.get("type", "") if idx == 0 else "",
                pre_condition if idx == 0 else "",
                step.get("step", ""),
                step.get("expected_result", ""),
                tc.get("description", "") if idx == 0 else "",
                ", ".join(s.get("key", "") for s in stories) if idx == 0 else ""
            ])

    tc_table = table(
        [
            "Depth1",
            "Depth2",
            "Pre-condition",
            "Step",
            "Expected Result",
            "Note",
            "JIRA"
        ],
        tc_rows
    ) if tc_rows else "<p>생성된 TC Draft 없음</p>"

    return (
        page_header(f"[TC Draft] {group_name}", "TestCollab 이관용 TC Draft")
        + section("Test Cases", tc_table)
        + info_panel("AI가 생성한 TC Draft 초안입니다. QA 검토 후 TestCollab으로 이관하세요.")
    )

# ── 4. 컨플 스펙 로드 헬퍼 ───────────────────────────────────────────────────

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


# ── 5. 메인 파이프라인 ────────────────────────────────────────────────────────

def run_tc_pipeline():
    print("\n=== TC 산출물 생성 ===")

    jira = JiraClient()
    confluence = ConfluenceClient()
    space_key = os.getenv("CONFLUENCE_SPACE_KEY")
    parent_id = os.getenv("CONFLUENCE_PARENT_PAGE_ID")

    # Step 1. 컨플 스펙 입력 (선택)
    confluence_spec = ""
    use_spec = input("Confluence 스펙 페이지를 참고할까요? (y/n): ").strip().lower()
    if use_spec == "y":
        confluence_spec = _load_confluence_specs(confluence)

    # Step 2. Jira 스토리 입력 (선택)
    use_jira = input("\nJira 스토리도 참고할까요? (y/n): ").strip().lower()
    stories = []
    if use_jira == "y":
        print("Jira Board URL 또는 JQL 입력:")
        print("예시 JQL: project = MYPROJ AND issuetype = Story AND sprint in openSprints()")
        jql_or_url = input("입력: ").strip()
        if jql_or_url:
            print("\n스토리 조회 중...")
            stories = jira.get_stories(jql_or_url)
            print(f"총 {len(stories)}개 스토리 조회됨")

    if not stories and not confluence_spec:
        print("스펙이나 스토리 중 하나는 입력해야 해요.")
        return

    # Step 3. 스토리 있으면 AI 그룹 분류 → 그룹 선택
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
        # 스토리 없이 컨플 스펙만으로 → 그룹 없이 단일 처리
        selected_groups = [("스펙 기반 TC", [])]

    # Step 4. 그룹별 스토리 본문 조회 → 산출물 생성 → 컨플 저장
    for group_name, keys in selected_groups:
        print(f"\n[{group_name}] 처리 중...")

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

        print("  AI Test Design 생성 중...")
        artifacts = generate_test_design_artifacts(group_stories, confluence_spec)

        artifacts = normalize_test_design_artifacts(artifacts)

        print("\n========== AI RESULT ==========")
        print(json.dumps(artifacts, indent=2, ensure_ascii=False))
        print("========== END ==========\n")

        checklist_matrix = artifacts.get("checklist_matrix", {})

        if isinstance(checklist_matrix, dict):
            checklist_count = sum(len(items) for items in checklist_matrix.values())
        else:
            checklist_count = len(checklist_matrix)

        print(
            f"  → Checklist {checklist_count}개 / "
            f"TC Draft {len(artifacts.get('tc_draft', []))}개 생성"
        )

        save = input(f"  Confluence에 저장할까요? (y/n): ").strip().lower()
        if save == "y":
            now = datetime.now().strftime("%Y-%m-%d %H:%M")

            design_html = build_test_design_page(group_name, group_stories, artifacts)
            design_title = f"[Test Design] {group_name} ({now})"
            design_link = confluence.create_page(
                space_key,
                design_title,
                design_html,
                parent_id=parent_id
            )

            tc_html = build_tc_draft_page(group_name, group_stories, artifacts)
            tc_title = f"[TC Draft] {group_name} ({now})"
            tc_link = confluence.create_page(
                space_key,
                tc_title,
                tc_html,
                parent_id=parent_id
            )

            print(f"  ✓ Test Design 저장 완료: {design_link}")
            print(f"  ✓ TC Draft 저장 완료: {tc_link}")

    print("\n=== 완료 ===")
