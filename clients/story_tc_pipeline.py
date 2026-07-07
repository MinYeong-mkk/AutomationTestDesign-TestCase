import os
import json
import re
import time
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


def normalize_story_groups(groups: dict, stories: list) -> dict:
    """그룹명 대소문자 통합, Story 중복 배정 제거, 누락 Story 보존."""
    valid_keys = {story.get("key") for story in stories if story.get("key")}
    merged = {}
    normalized_names = {}
    assigned = set()

    for raw_name, raw_keys in (groups or {}).items():
        name = str(raw_name).strip() or "미분류"
        normalized = re.sub(r"[\s_-]+", "", name).casefold()
        canonical = normalized_names.setdefault(normalized, name)
        merged.setdefault(canonical, [])
        for key in raw_keys if isinstance(raw_keys, list) else []:
            if key in valid_keys and key not in assigned:
                merged[canonical].append(key)
                assigned.add(key)

    missing = [story["key"] for story in stories if story.get("key") not in assigned]
    if missing:
        merged.setdefault("미분류", []).extend(missing)

    return {name: keys for name, keys in merged.items() if keys}


def _format_story_sources(stories: list) -> str:
    sections = []
    for story in stories:
        sections.append(
            f"## [Jira] {story.get('key', '')} — {story.get('summary', '')}\n"
            f"Description:\n{story.get('description') or '(설명 없음)'}\n"
            f"Acceptance Criteria:\n{story.get('acceptance_criteria') or '(별도 필드 없음)'}"
        )
    return "\n\n".join(sections) or "(Jira Story 없음)"


def analyze_figma_evidence(figma_images: list) -> dict:
    """Figma 이미지와 TEXT 노드에서 화면별 UI 근거를 한 번 구조화한다."""
    if not figma_images:
        return {"screens": []}

    exact_text = []
    for image in figma_images:
        texts = image.get("visible_text", [])
        exact_text.append(
            f"## {image.get('description', '')}\n"
            + "\n".join(f"- {text}" for text in texts[:150])
        )

    prompt = f"""
첨부된 Figma 화면을 QA 근거 자료로 분석하세요.
아래 TEXT 노드는 Figma API에서 직접 추출한 원문이므로 철자와 대소문자를 변경하지 마세요.

{chr(10).join(exact_text)}

규칙:
- source_id는 제공된 화면 description을 정확히 그대로 사용한다.
- visible_text에는 화면에서 실제 확인되는 문구만 원문 그대로 기록한다.
- controls에는 버튼/링크/탭/체크박스와 정확한 레이블을 기록한다.
- input_fields에는 필드명, placeholder, 필수 여부를 관찰 가능한 범위에서 기록한다.
- messages에는 팝업/토스트/오류/안내 문구를 원문 그대로 기록한다.
- states에는 enabled/disabled/selected/empty/loading 등 실제 관찰 상태를 기록한다.
- 화면에 보이지 않는 동작, API 처리, 다음 화면을 추측하지 않는다.

JSON 외 텍스트 출력 금지:
{{
  "screens": [
    {{
      "source_id": "",
      "visible_text": [],
      "controls": [],
      "input_fields": [],
      "messages": [],
      "states": [],
      "uncertainties": []
    }}
  ]
}}
"""
    return ai.chat_json(prompt, max_tokens=6000, images=figma_images)


def _format_figma_evidence(figma_evidence: dict) -> str:
    return json.dumps(figma_evidence or {"screens": []}, ensure_ascii=False, indent=2)


KOREAN_OUTPUT_RULE = (
    "모든 설명/Scenario/description/pre_condition/test_data/step/expected_result/note는 한국어로 작성한다. "
    "단, 제품명, 메뉴명, 버튼명, 필드명, 화면 문구, API명, Jira/Confluence/Figma 원문 인용은 원문 그대로 유지한다."
)


# ── 2. TC 산출물 생성 ─────────────────────────────────────────────────────────

def _legacy_generate_test_design_artifacts(
    stories: list,
    confluence_spec: str = "",
    figma_images: list = None,
    figma_evidence: dict = None,
    story_groups: dict = None,
) -> dict:
    """이전 단일 호출 방식. 실제 파이프라인에서는 사용하지 않는다."""
    stories_text = _format_story_sources(stories)

    spec_section = confluence_spec[:40000] if confluence_spec else "(Confluence Spec 없음)"
    checklist_text = format_checklist()
    checklist_total = len(CHECKLIST_TEMPLATE)
    group_section = "\n".join(
        f"- {name}: {', '.join(keys)}"
        for name, keys in (story_groups or {}).items()
    ) or "- 공통 / E2E: 입력된 전체 요구사항"

    figma_section = ""
    if figma_images:
        screen_names = "\n".join(f"- {img['description']}" for img in figma_images)
        figma_section = f"""
## Figma 화면 ({len(figma_images)}개 이미지 첨부됨)
{screen_names}

## Figma 구조화 근거
{_format_figma_evidence(figma_evidence)}

[Figma 이미지 분석 필수 지시]
- 첨부된 이미지에서 실제 버튼 레이블, 입력 필드명, 팝업 제목, 오류 메시지 문구를 직접 인용하여 TC Step에 사용할 것
- UI/UX 체크리스트 항목 평가 시 이미지에서 관찰된 실제 화면 구성을 근거로 작성할 것
- 화면에 보이는 플로우(버튼 클릭 → 다음 화면 → 결과)를 TC Step 흐름에 반영할 것
"""

    prompt = f"""
당신은 10년 이상 경력의 Senior QA Engineer입니다.
아래 입력 자료를 분석하여 고품질 Test Design 산출물을 작성하세요.
모든 출력은 한국어로 작성한다. 단, 제품명/버튼명/화면 문구/영문 스펙 문구는 원문 그대로 유지한다.

[제품 중립성 및 근거 원칙]
- Jira Story, Confluence Spec, Figma 화면에 실제로 존재하는 제품/기능/화면만 다룬다.
- 특정 제품의 도메인 지식이나 이전 실행 결과를 다른 입력에 재사용하지 않는다.
- 입력에 없는 제품명, 메뉴명, 버튼명, 정책, 수치, 사용자 역할을 추측하거나 발명하지 않는다.
- 자료 간 내용이 충돌하거나 근거가 부족하면 임의 결정하지 말고 "확인 필요"로 표시한다.

================================================
입력 자료
================================================

## Jira Story
{stories_text}

## 기능 분류
{group_section}

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
- TC는 반드시 아래 두 종류를 모두 작성한다.
  1) Functional: 개별 기능의 입력값/권한/경계값/오류 처리/상태별 동작 검증
  2) Workflow E2E: 여러 기능을 연결해 실제 사용자의 업무 목적이 끝까지 완료되는지 검증
- Functional TC의 test_type="Functional", feature_group에는 위 "기능 분류"의 그룹명을 정확히 하나 사용한다.
- 모든 기능 그룹에 Functional Scenario를 최소 3개 배정하고, 복잡한 그룹은 5개 이상 작성한다.
- Workflow E2E TC의 test_type="Workflow E2E", feature_group="공통 / E2E"로 작성한다.
- Workflow E2E TC는 최소 3개 작성한다: 정상 Happy Path / 대체 경로 / 실패 후 재시도 또는 복구 경로.
- Workflow E2E TC의 covered_groups에는 연결되는 기능 그룹명을 실행 순서대로 2개 이상 작성한다.
- 입력 스토리가 복잡하거나 화면이 다양한 경우 15개 이상 작성
- Functional TC는 기능 하나를 깊게 검증하고, Workflow E2E TC는 기능 간 연결과 데이터 전달을 검증한다.
- Functional Scenario는 의미 있는 5~10 Step, Workflow E2E Scenario는 10~20 Step으로 작성한다.
- Step 수를 채우기 위한 로그인/페이지 진입 등의 무의미한 반복은 금지한다.
- 각 Step에는 한 가지 행동만 작성하고 "1. [구체적 행동]" 형태로 번호를 붙인다.
- expected_result는 화면 변화, API/시스템 처리, 데이터 상태, 알림/오류 문구 중 확인 가능한 결과를 구체적으로 기술한다.
- "정상 동작한다", "문제없다", "확인한다"처럼 판정 기준이 없는 표현만 단독으로 사용하지 않는다.
- pre_condition에는 계정 상태, 권한, 선행 데이터, 환경을 구체적으로 작성한다.
- test_data에는 입력값, 데이터 상태, 경계값을 작성한다. 근거 없는 실제 값을 발명하지 말고 필요 시 "준비 필요"로 표시한다.
- source_evidence에는 근거가 된 Jira Key, Confluence 문서 제목/요구사항, Figma 화면명을 작성한다.
- checklist_categories에는 이 TC가 검증하는 Checklist category를 원문 그대로 1개 이상 작성한다.
  사용 가능한 값: Functional / Non-Functional / UI/UX / Integration / Common /
  Exceptional Handling / Technical Quality Assurance
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
5. Mindmap — PlantUML mindmap 문법, TC 대상 기능 중심. 코드 펜스 없이 @startmindmap부터 @endmindmap까지 출력
6. Workflow — PlantUML Activity Diagram 문법으로 주요 사용자 플로우 전체 표현.
   코드 펜스 없이 @startuml부터 @enduml까지 출력
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
  "mindmap_plantuml": "",
  "flowchart_plantuml": "",
  "tc_draft": [
    {{
      "test_type": "Functional",
      "feature_group": "",
      "covered_groups": [],
      "scenario": "",
      "description": "",
      "priority": "High",
      "pre_condition": [],
      "jira_keys": [],
      "test_data": [],
      "source_evidence": [],
      "checklist_categories": [],
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

    return ai.chat_json(prompt, max_tokens=16000)


def generate_test_design_only(
    stories: list,
    confluence_spec: str,
    figma_images: list,
    figma_evidence: dict,
    story_groups: dict,
) -> dict:
    """TC와 다이어그램을 제외한 통합 Test Design만 생성한다."""
    checklist_total = len(CHECKLIST_TEMPLATE)
    groups = "\n".join(
        f"- {name}: {', '.join(keys)}" for name, keys in story_groups.items()
    ) or "- 스펙 기반 기능"
    prompt = f"""
당신은 Senior QA Test Architect입니다. 아래 근거만 사용해 통합 Test Design을 작성하세요.
TC와 다이어그램은 별도 단계에서 생성하므로 여기서는 절대 작성하지 않습니다.
{KOREAN_OUTPUT_RULE}

[근거 원칙]
- Jira/Confluence/Figma에 없는 기능, UI 문구, 정책, 수치, 복구 방식을 발명하지 않는다.
- 충돌하거나 부족한 정보는 "확인 필요"로 표시한다.
- Jira Key, Confluence 제목, Figma source_id는 제공된 문자열을 그대로 사용한다.
- 위험 완화책은 구현된 기능처럼 단정하지 말고 QA 검증 또는 검토 제안으로 작성한다.

## Jira 상세 및 Acceptance Criteria
{_format_story_sources(stories)}

## 기능 분류
{groups}

## Confluence 정제 원문
{confluence_spec[:40000] if confluence_spec else "(없음)"}

## Figma 구조화 근거
{_format_figma_evidence(figma_evidence)}

## 회사 Checklist Template ({checklist_total}개)
{format_checklist()}

[Checklist 규칙]
- checklist_matrix는 정확히 {checklist_total}개이며 원문을 변경/병합하지 않는다.
- 해당 자료로 검증 필요성이 입증된 경우만 applicable=true로 한다.
- 근거가 부족하면 applicable 판단과 별개로 spec_review_required=true로 한다.
- reason에는 근거 Jira Key/Confluence 제목/Figma source_id 또는 부족한 자료를 명시한다.
- 일반적인 QA 상식만으로 모든 항목을 applicable=true로 만들지 않는다.

[문서 분리 판단]
- Story가 서로 다른 제품/사용자 목표/Workflow를 다루거나 기능 그룹이 5개 이상이면 required=true.
- required가 true든 false든 reason은 반드시 구체적으로 작성한다.

JSON 외 텍스트 출력 금지:
{{
  "style_mode": "detailed",
  "split_recommendation": {{"required": false, "reason": "", "suggested_documents": []}},
  "requirement_summary": {{
    "feature_name": "", "purpose": "", "affected_modules": [],
    "user_types": [], "change_type": ""
  }},
  "test_scope": {{"in_scope": [], "out_scope": []}},
  "checklist_matrix": [
    {{
      "category": "", "checklist": "", "applicable": false,
      "related_feature": "", "reason": "", "spec_review_required": false,
      "test_case_design": ""
    }}
  ],
  "risk_analysis": [
    {{"risk": "", "impact": "High", "mitigation": "", "source_evidence": []}}
  ]
}}
"""
    return ai.chat_json(prompt, max_tokens=12000)


def _source_catalog(stories: list, confluence_spec: str, figma_images: list) -> list:
    sources = [f"Jira:{story.get('key')}" for story in stories if story.get("key")]
    sources.extend(
        f"Confluence:{title.strip()}"
        for title in re.findall(r"^## \[Confluence\] (.+)$", confluence_spec or "", re.M)
    )
    sources.extend(
        f"Figma:{image.get('description')}"
        + (f" (node_id:{image.get('node_id')})" if image.get("node_id") else "")
        for image in (figma_images or [])
        if image.get("description")
    )
    return sources


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value or "tc_pipeline")
    return name.strip("._")[:80] or "tc_pipeline"


def _save_local_output_backup(
    document_name: str,
    now: str,
    artifacts: dict,
    design_html: str,
    tc_html: str,
) -> str:
    backup_dir = os.path.join("outputs", "tc_pipeline")
    os.makedirs(backup_dir, exist_ok=True)
    base_name = _safe_filename(f"{now}_{document_name}")
    paths = {
        "artifacts": os.path.join(backup_dir, f"{base_name}_artifacts.json"),
        "design": os.path.join(backup_dir, f"{base_name}_test_design.html"),
        "tc": os.path.join(backup_dir, f"{base_name}_tc_draft.html"),
    }
    with open(paths["artifacts"], "w", encoding="utf-8") as file:
        json.dump(artifacts, file, ensure_ascii=False, indent=2)
    with open(paths["design"], "w", encoding="utf-8") as file:
        file.write(design_html)
    with open(paths["tc"], "w", encoding="utf-8") as file:
        file.write(tc_html)
    return backup_dir


def _create_confluence_page_with_recovery(
    confluence: ConfluenceClient,
    space_key: str,
    title: str,
    html: str,
    parent_id: str,
    attempts: int = 2,
) -> str:
    for attempt in range(1, attempts + 1):
        try:
            return confluence.create_page(space_key, title, html, parent_id=parent_id)
        except Exception as e:
            print(f"  Confluence 저장 시도 {attempt}/{attempts} 실패: {title} - {e}")
            try:
                existing_link = confluence.find_page_link(space_key, title, parent_id=parent_id)
                if existing_link:
                    print(f"  → 응답은 실패했지만 페이지가 생성되어 있습니다: {existing_link}")
                    return existing_link
            except Exception as lookup_error:
                print(f"  → 생성 여부 확인 실패: {lookup_error}")
            if attempt < attempts:
                time.sleep(5 * attempt)
    raise RuntimeError(f"Confluence 페이지 저장 실패: {title}")


def generate_functional_tcs(
    group_name: str,
    stories: list,
    confluence_spec: str,
    figma_images: list,
    figma_evidence: dict,
) -> list:
    """기능 그룹 하나만 집중 분석해 Functional TC를 생성한다."""
    required_count = max(3, len(stories))
    allowed_jira = [story.get("key") for story in stories if story.get("key")]
    sources = _source_catalog(stories, confluence_spec, figma_images)
    prompt = f"""
당신은 실제 실행 가능한 Functional TC를 작성하는 Senior QA Engineer입니다.
이번 호출에서는 오직 `{group_name}` 기능만 다룹니다.
{KOREAN_OUTPUT_RULE}

## Jira 상세 및 Acceptance Criteria
{_format_story_sources(stories)}

## Confluence 정제 원문
{confluence_spec[:40000] if confluence_spec else "(없음)"}

## Figma 구조화 근거
{_format_figma_evidence(figma_evidence)}

## 허용 Jira Key
{json.dumps(allowed_jira, ensure_ascii=False)}

## 허용 source_evidence
{json.dumps(sources, ensure_ascii=False)}

[필수 규칙]
- JSON 키와 enum 값(test_type, feature_group, checklist_categories 등)은 지정된 스키마/허용값을 유지하되, 사람이 읽는 모든 본문 값은 한국어로 작성한다.
- 최소 {required_count}개 TC를 작성하고 모든 허용 Jira Key를 최소 한 TC에서 커버한다.
- test_type="Functional", feature_group="{group_name}"을 정확히 사용한다.
- 각 TC는 의미 있는 5~10 Step이며 정상/실패/경계값/권한/상태 조합을 분산해 다룬다.
- Step마다 행동은 하나만 쓰고 `1. `부터 순서대로 번호를 붙인다.
- Expected Result는 관찰 가능한 UI 문구/상태/API·데이터 결과를 구체적으로 쓴다.
- 버튼명/필드명/메시지는 Figma visible_text 또는 Confluence/Jira 원문에 정확히 존재할 때만 따옴표로 인용한다.
- 근거에 없는 UI 명칭은 발명하지 말고 `[UI 문구 확인 필요]`라고 쓴다.
- source_evidence는 허용 목록의 문자열만 그대로 사용한다.
- 화면, 버튼, 입력 필드, 모달, 팝업, 배지, 툴팁 등 UI를 검증하는 TC는 관련된 `Figma:` source_evidence를 반드시 포함한다.
- 제공된 Figma에서 관련 화면을 찾을 수 없으면 임의 연결하지 말고 note에 "Figma 화면 확인 필요"를 작성한다.
- jira_keys는 허용 Jira Key만 사용하며 Scenario와 실제 관련된 Key만 연결한다.
- pre_condition, test_data, source_evidence, checklist_categories는 빈 배열일 수 없다.
- 단순 페이지 이동만으로 끝나는 TC, 여러 Story를 이름만 묶은 TC는 금지한다.

JSON 외 텍스트 출력 금지:
{{"tc_draft": [{{
  "test_type": "Functional", "feature_group": "{group_name}", "covered_groups": [],
  "scenario": "", "description": "", "priority": "High",
  "pre_condition": [], "jira_keys": [], "test_data": [],
  "source_evidence": [], "checklist_categories": [], "note": "",
  "steps": [{{"step": "1. ", "expected_result": ""}}]
}}]}}
"""
    result = ai.chat_json(prompt, max_tokens=12000)
    return result.get("tc_draft", []) if isinstance(result, dict) else []


def generate_workflow_tcs(
    grouped_stories: list,
    confluence_spec: str,
    figma_images: list,
    figma_evidence: dict,
) -> list:
    """전체 기능 그룹의 실제 연결 근거를 바탕으로 Workflow E2E TC를 별도 생성."""
    all_stories = [story for _, items in grouped_stories for story in items]
    groups = [name for name, _ in grouped_stories]
    group_map = {
        name: [story.get("key") for story in items if story.get("key")]
        for name, items in grouped_stories
    }
    allowed_jira = [story.get("key") for story in all_stories if story.get("key")]
    sources = _source_catalog(all_stories, confluence_spec, figma_images)
    prompt = f"""
당신은 사용자 목표 기반 Workflow/E2E TC를 작성하는 Senior QA Engineer입니다.
{KOREAN_OUTPUT_RULE}

## 기능 그룹과 Jira Key
{json.dumps(group_map, ensure_ascii=False, indent=2)}

## Jira 상세 및 Acceptance Criteria
{_format_story_sources(all_stories)}

## Confluence 정제 원문
{confluence_spec[:40000] if confluence_spec else "(없음)"}

## Figma 구조화 근거
{_format_figma_evidence(figma_evidence)}

## 허용 source_evidence
{json.dumps(sources, ensure_ascii=False)}

[필수 규칙]
- JSON 키와 enum 값(test_type, feature_group, checklist_categories 등)은 지정된 스키마/허용값을 유지하되, 사람이 읽는 모든 본문 값은 한국어로 작성한다.
- 최소 3개 Workflow TC를 작성한다: Happy Path / 대체 경로 / 실패 후 복구 또는 재시도.
- 실제 자료에서 순서 관계가 확인되는 기능만 하나의 Workflow로 연결한다.
- 연결 근거가 없다면 임의로 버튼/화면/API 순서를 발명하지 말고 note에 "Workflow 연결 근거 확인 필요"를 쓴다.
- test_type="Workflow E2E", feature_group="공통 / E2E"를 정확히 사용한다.
- covered_groups는 {json.dumps(groups, ensure_ascii=False)} 안의 정확한 그룹명만 실행 순서대로 사용한다.
- 각 TC는 의미 있는 10~20 Step이며 사용자 행동뿐 아니라 시스템 결과와 데이터 전달을 검증한다.
- 버튼명/필드명/메시지는 제공된 원문에 정확히 존재할 때만 인용한다.
- source_evidence는 허용 목록의 문자열만, jira_keys는 허용 Jira Key만 사용한다.
- UI 화면이나 조작을 포함하는 Workflow TC는 실제 관련된 `Figma:` source_evidence를 포함한다. 관련 화면이 제공되지 않았으면 note에 "Figma 화면 확인 필요"를 작성한다.
- pre_condition, test_data, source_evidence, checklist_categories는 빈 배열일 수 없다.

JSON 외 텍스트 출력 금지:
{{"tc_draft": [{{
  "test_type": "Workflow E2E", "feature_group": "공통 / E2E", "covered_groups": [],
  "scenario": "", "description": "", "priority": "High",
  "pre_condition": [], "jira_keys": [], "test_data": [],
  "source_evidence": [], "checklist_categories": [], "note": "",
  "steps": [{{"step": "1. ", "expected_result": ""}}]
}}]}}
"""
    result = ai.chat_json(prompt, max_tokens=14000)
    return result.get("tc_draft", []) if isinstance(result, dict) else []


def generate_detailed_diagrams(
    stories: list,
    confluence_spec: str,
    figma_images: list,
    figma_evidence: dict,
    artifacts: dict,
) -> dict:
    """기본 산출물을 근거로 상세 Mindmap/Flowchart를 별도 생성한다."""
    stories_text = _format_story_sources(stories)
    figma_text = "\n".join(
        f"- {img.get('description', '')}" for img in (figma_images or [])
    ) or "(Figma 화면 없음)"

    # 다이어그램에 필요한 정보만 전달해 TC 본문 전체로 인한 입력 과밀을 줄인다.
    design_context = {
        "requirement_summary": artifacts.get("requirement_summary", {}),
        "test_scope": artifacts.get("test_scope", {}),
        "checklist_matrix": artifacts.get("checklist_matrix", []),
        "risk_analysis": artifacts.get("risk_analysis", []),
        "tc_scenarios": [
            {
                "title": tc.get("title", ""),
                "test_type": tc.get("test_type", ""),
                "feature_group": tc.get("feature_group", ""),
                "covered_groups": tc.get("covered_groups", []),
                "priority": tc.get("priority", ""),
                "pre_condition": tc.get("pre_condition", []),
                "steps": tc.get("steps", []),
            }
            for tc in artifacts.get("tc_draft", [])
        ],
    }

    prompt = f"""
당신은 복잡한 제품 요구사항을 시각화하는 Senior QA Test Architect입니다.
아래 원본 자료와 이미 작성된 Test Design을 근거로, QA 검토에 바로 사용할 수 있는
상세 PlantUML Mindmap과 Workflow Activity Diagram을 작성하세요.

================================================
원본 자료
================================================

## Jira Story
{stories_text}

## Confluence Spec
{confluence_spec[:40000] if confluence_spec else "(Confluence Spec 없음)"}

## Figma 화면명
{figma_text}

## Figma 구조화 근거
{_format_figma_evidence(figma_evidence)}

## 기존 Test Design
{json.dumps(design_context, ensure_ascii=False)}

================================================
공통 원칙
================================================

- 입력 자료에 없는 제품 동작, 화면명, 수치, 정책을 사실처럼 발명하지 않는다.
- 정보가 불명확하면 해당 노드에 "확인 필요"를 명시한다.
- 단순 키워드 나열이 아니라 조건 → 사용자 행동 → 시스템 처리 → 검증 결과가 드러나야 한다.
- 각 노드는 문장이 아닌 핵심 행동/상태 중심의 짧은 구문으로 작성한다.
- 다이어그램의 설명, 분기명, 상태명은 한글로 작성한다. 단, Figma/Jira/Confluence에 존재하는 실제 영문 UI 레이블과 제품명은 원문을 유지한다.
- 한 노드의 표시 문구는 한 줄당 한글 기준 18자 이내, 최대 2줄로 제한한다.
- Mindmap 노드 문구가 길면 의미 단위로 PlantUML 줄바꿈 문자 `\\n`을 한 번 넣거나 하위 노드로 분리한다. `<br>`와 `<br/>`는 사용하지 않는다.
- 노드 안에 요구사항 설명 전체나 여러 검증 조건을 한꺼번에 넣지 않는다.
- 각 JSON 문자열에는 PlantUML 코드만 넣고 코드 펜스는 넣지 않는다.
- 장식용 아이콘과 emoji는 사용하지 않는다. Confluence 렌더러 호환성을 우선한다.

================================================
PlantUML Mindmap 작성 규칙
================================================

- 반드시 `@startmindmap`으로 시작하고 `@endmindmap`으로 끝낸다.
- `@startmindmap` 바로 다음에 아래 style 블록을 정확히 넣는다:
  <style>
  mindmapDiagram {{
    node {{
      BackgroundColor #F8FAFC
      FontColor #334155
      LineColor #CBD5E1
      FontSize 13
      RoundCorner 14
      Padding 10
      Margin 6
      MaximumWidth 180
    }}
    rootNode {{
      BackgroundColor #334155
      FontColor #FFFFFF
      LineColor #1E293B
      FontSize 18
      RoundCorner 18
      Padding 14
    }}
    :depth(1) {{
      BackgroundColor #DBEAFE
      FontColor #1E3A5F
      LineColor #93C5FD
      FontSize 15
    }}
    :depth(2) {{
      BackgroundColor #ECFDF5
      FontColor #065F46
      LineColor #A7F3D0
    }}
    :depth(3) {{
      BackgroundColor #FFFBEB
      FontColor #92400E
      LineColor #FDE68A
    }}
    arrow {{
      LineColor #94A3B8
      LineThickness 1.2
    }}
  }}
  </style>
- root는 requirement_summary의 실제 기능명을 `+ **기능명**`으로 작성한다. 길면 `+ **첫 줄\\n두 번째 줄**`처럼 `\\n`으로 줄바꿈한다.
- 1차 가지는 최소 7개로 구성한다:
  기능 테스트 / UI/UX 테스트 / 통합 테스트 /
  예외 처리 테스트 / 비기능 테스트 /
  기술 품질 보증 / 공통·호환성 테스트
- 오른쪽 1차 가지는 `++ **기능 테스트**`, 왼쪽 1차 가지는 `-- **UI/UX 테스트**` 문법을 사용한다.
- 7개 1차 가지를 좌우 4:3 또는 3:4로 나눠 한쪽으로 쏠리지 않게 배치한다.
- 오른쪽 하위 depth는 `+++`, `++++`, 왼쪽 하위 depth는 `---`, `----`처럼 부호 개수로 표현한다.
- 각 1차 가지는 기능 영역 → 조건 또는 상태 → 사용자 행동 → 기대 결과 순으로 3~4 depth까지 확장한다.
- 전체 leaf node는 28~40개로 제한해 상세함과 가독성을 함께 유지한다.
- 한 부모 아래 자식은 최대 5개까지만 두고, 넘으면 의미 있는 중간 분류 노드를 추가한다.
- 각 노드는 짧은 검증 관점만 작성하고, 필요한 경우 `\\n`으로 최대 2줄까지만 나눈다.
- 정상/실패/경계값/권한/데이터 상태/네트워크/복구/플랫폼 차이를 자료 범위 안에서 포함한다.
- 해당 기능과 명백히 무관한 항목을 개수 채우기용으로 넣지 않는다.

================================================
PlantUML Workflow Activity Diagram 작성 규칙
================================================

- 반드시 `@startuml`으로 시작하고 `@enduml`로 끝낸다.
- `@startuml` 바로 다음에 아래 스타일을 정확히 넣는다:
  `!pragma useVerticalIf on`
  `skinparam backgroundColor #FFFFFF`
  `skinparam shadowing false`
  `skinparam roundcorner 14`
  `skinparam defaultFontName Arial`
  `skinparam defaultFontSize 13`
  `skinparam ArrowColor #94A3B8`
  `skinparam ArrowThickness 1.2`
  `skinparam activityBackgroundColor #EFF6FF`
  `skinparam activityBorderColor #93C5FD`
  `skinparam activityFontColor #1E3A5F`
  `skinparam activityDiamondBackgroundColor #FFFBEB`
  `skinparam activityDiamondBorderColor #FBBF24`
  `skinparam activityDiamondFontColor #92400E`
  `skinparam activityStartColor #334155`
  `skinparam activityEndColor #334155`
  `skinparam swimlaneBorderColor #CBD5E1`
  `skinparam swimlaneTitleBackgroundColor #F8FAFC`
  `skinparam swimlaneTitleFontColor #334155`
- `start`와 `stop`을 포함하고, 최소 20개 activity를 작성한다.
- Happy Path뿐 아니라 대체 경로, 실패 경로, 재시도 또는 복구 경로를 함께 표현한다.
- `if (...) then (예)`, `else (아니오)`, `endif` 조건 분기를 최소 4개 포함한다.
- 재시도 흐름은 가능하면 `repeat`, `backward`, `repeat while` 문법을 사용한다.
- 사용자 행동, 화면/클라이언트 처리, API/외부 연동, 데이터 반영, 사용자 피드백을 구분한다.
- 실제 자료에 존재하는 영역만 아래 swimlane 문법으로 구분한다:
  `|사용자 / UI|`, `|시스템 / API|`, `|데이터 / 외부 연동|`, `|예외 / 복구|`
- activity는 `:사용자 행동;`처럼 작성하고, 한 activity에는 한 행동/처리만 넣는다.
- 긴 문구는 `:첫 번째 줄\n두 번째 줄;`처럼 최대 2줄로 작성하며 한 줄은 한글 기준 18자 이내로 제한한다.
- 사용자/UI activity는 기본 파랑 스타일을 사용한다.
- 정상 완료/성공 결과는 `#ECFDF5:정상 결과;`, 오류/실패/복구는 `#FFF1F2:오류 처리;`,
  API/DB/외부 연동은 `#F5F3FF:시스템 처리;`처럼 activity 앞에 배경색을 지정한다.
- 병렬 처리가 실제 요구사항에 있으면 `fork`, `fork again`, `end fork`를 사용한다.
- 자료에 없는 시스템 레이어나 처리 단계를 시각적 완성도를 위해 발명하지 않는다.

================================================
출력 형식
================================================

JSON 외 텍스트 출력 금지:
{{
  "mindmap_plantuml": "",
  "flowchart_plantuml": ""
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

    def text_list(value) -> list:
        """Claude가 문자열/객체/배열 중 무엇을 반환해도 표시 가능한 문자열 배열로 만든다."""
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        normalized = []
        for item in values:
            if isinstance(item, dict):
                normalized.append(", ".join(f"{key}: {val}" for key, val in item.items()))
            elif isinstance(item, (list, tuple)):
                normalized.extend(str(part) for part in item)
            elif str(item).strip():
                normalized.append(str(item).strip())
        return normalized

    allowed_categories = {category for category, _ in CHECKLIST_TEMPLATE}

    def checklist_categories(value) -> list:
        raw_items = text_list(value)
        mapped = []
        for item in raw_items:
            if item in allowed_categories:
                mapped.append(item)
                continue
            lowered = item.casefold()
            if any(word in lowered for word in ("오류", "실패", "유효성", "필수", "예외")):
                mapped.append("Exceptional Handling")
            elif any(word in lowered for word in ("ui", "ux", "버튼", "모달", "화면", "배지", "툴팁", "아이콘")):
                mapped.append("UI/UX")
            elif any(word in lowered for word in ("연동", "동기화", "외부", "이메일", "stripe", "import")):
                mapped.append("Integration")
            elif any(word in lowered for word in ("성능", "부하", "네트워크", "복구", "리트라이")):
                mapped.append("Technical Quality Assurance")
            else:
                mapped.append("Functional")
        return list(dict.fromkeys(mapped)) or ["Functional"]

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
        else:
            normalized_steps = []
            for step_index, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    action = step.get("step") or step.get("action") or ""
                    expected = (
                        step.get("expected_result")
                        or step.get("expected")
                        or step.get("result")
                        or ""
                    )
                else:
                    action, expected = step, ""
                action = str(action)
                expected = str(expected)
                if not re.match(r"^\d+\.\s*", action):
                    action = f"{step_index}. {action}"
                normalized_steps.append({
                    "step": action,
                    "expected_result": expected,
                })
            steps = normalized_steps

        feature_group = tc.get("feature_group", "") or "공통 / E2E"
        test_type = tc.get("test_type") or (
            "Workflow E2E" if feature_group == "공통 / E2E" else "Functional"
        )
        jira_keys = tc.get("jira_keys", [])
        covered_groups = tc.get("covered_groups", [])
        source_evidence = tc.get("source_evidence", [])
        normalized_categories = checklist_categories(tc.get("checklist_categories", []))
        jira_keys = text_list(jira_keys)
        covered_groups = text_list(covered_groups)
        if isinstance(source_evidence, str):
            source_evidence = [source_evidence]
        fixed_tcs.append({
            "id": f"TC-{i:03d}",
            "test_type": test_type,
            "feature_group": feature_group,
            "covered_groups": covered_groups,
            "title": str(tc.get("scenario") or tc.get("title") or tc.get("description", "")),
            "priority": str(tc.get("priority", "Normal")),
            "description": "<br/>".join(text_list(tc.get("description", ""))),
            "pre_condition": text_list(tc.get("pre_condition", [])),
            "jira_keys": jira_keys,
            "test_data": text_list(tc.get("test_data", [])),
            "source_evidence": text_list(source_evidence),
            "checklist_categories": normalized_categories,
            "note": "<br/>".join(text_list(tc.get("note", ""))),
            "steps": steps
        })

    artifacts["tc_draft"] = fixed_tcs

    return artifacts


def _is_ui_tc(tc: dict) -> bool:
    """화면 근거 연결이 필요한 UI 중심 TC인지 보수적으로 판별한다."""
    categories = tc.get("checklist_categories", [])
    if isinstance(categories, str):
        categories = [categories]
    if "UI/UX" in categories:
        return True
    text = " ".join([
        str(tc.get("title", "")),
        str(tc.get("description", "")),
        " ".join(
            f"{step.get('step', '')} {step.get('expected_result', '')}"
            for step in tc.get("steps", []) if isinstance(step, dict)
        ),
    ]).casefold()
    ui_terms = (
        "화면", "버튼", "클릭", "입력 필드", "모달", "팝업", "다이얼로그",
        "메뉴", "탭", "배지", "툴팁", "아이콘", "레이블", "표시", "노출",
        "screen", "button", "modal", "popup", "tooltip", "badge",
    )
    return any(term in text for term in ui_terms)


def build_coverage_matrix(artifacts: dict, stories: list) -> dict:
    """Jira Story와 생성 TC 간 추적성 및 미커버 Story를 계산한다."""
    rows = []
    covered_keys = set()

    for tc in artifacts.get("tc_draft", []):
        jira_keys = tc.get("jira_keys", [])
        if isinstance(jira_keys, str):
            jira_keys = [jira_keys]
        jira_keys = [key for key in jira_keys if key]
        covered_keys.update(jira_keys)

        categories = tc.get("checklist_categories", [])
        if isinstance(categories, str):
            categories = [categories]

        rows.append({
            "feature": tc.get("feature_group", ""),
            "jira_keys": jira_keys,
            "checklist_category": categories,
            "test_type": tc.get("test_type", ""),
            "tc_id": tc.get("id", ""),
            "scenario": tc.get("title", ""),
            "coverage_status": "Covered" if jira_keys else "Source 확인 필요",
        })

    story_map = {
        story.get("key", ""): story.get("summary", "")
        for story in stories
        if story.get("key")
    }
    uncovered_keys = [key for key in story_map if key not in covered_keys]
    for key in uncovered_keys:
        rows.append({
            "feature": "미커버 Story",
            "jira_keys": [key],
            "checklist_category": [],
            "test_type": "미커버",
            "tc_id": "",
            "scenario": story_map[key],
            "coverage_status": "Uncovered",
        })

    total_stories = len(story_map)
    covered_story_count = total_stories - len(uncovered_keys)
    coverage_rate = round(covered_story_count / total_stories * 100, 1) if total_stories else 0.0

    artifacts["coverage_matrix"] = rows
    artifacts["coverage_summary"] = {
        "total_stories": total_stories,
        "covered_stories": covered_story_count,
        "coverage_rate": coverage_rate,
        "functional_tc_count": sum(
            1 for tc in artifacts.get("tc_draft", []) if tc.get("test_type") == "Functional"
        ),
        "workflow_tc_count": sum(
            1 for tc in artifacts.get("tc_draft", []) if tc.get("test_type") == "Workflow E2E"
        ),
        "uncovered_jira_keys": uncovered_keys,
    }

    figma_sources = [
        source for source in artifacts.get("source_catalog", [])
        if str(source).startswith("Figma:")
    ]
    covered_figma = set()
    unmapped_ui_tc_ids = []
    figma_rows = []
    for tc in artifacts.get("tc_draft", []):
        evidence = tc.get("source_evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        tc_figma = [source for source in evidence if str(source).startswith("Figma:")]
        covered_figma.update(source for source in tc_figma if source in figma_sources)
        if figma_sources and _is_ui_tc(tc) and not tc_figma:
            unmapped_ui_tc_ids.append(tc.get("id", ""))

    for source in figma_sources:
        linked_tcs = []
        scenarios = []
        for tc in artifacts.get("tc_draft", []):
            evidence = tc.get("source_evidence", [])
            if isinstance(evidence, str):
                evidence = [evidence]
            if source in evidence:
                linked_tcs.append(tc.get("id", ""))
                scenarios.append(tc.get("title", ""))
        figma_rows.append({
            "figma_source": source,
            "tc_ids": linked_tcs,
            "scenarios": scenarios,
            "coverage_status": "Covered" if linked_tcs else "Uncovered",
        })

    artifacts["figma_coverage_matrix"] = figma_rows
    artifacts["figma_coverage_summary"] = {
        "total_screens": len(figma_sources),
        "covered_screens": len(covered_figma),
        "coverage_rate": (
            round(len(covered_figma) / len(figma_sources) * 100, 1)
            if figma_sources else 0.0
        ),
        "ui_tc_count": sum(_is_ui_tc(tc) for tc in artifacts.get("tc_draft", [])),
        "unmapped_ui_tc_ids": [tc_id for tc_id in unmapped_ui_tc_ids if tc_id],
    }
    return artifacts


def validate_tc_quality(artifacts: dict, stories: list, evidence_corpus: str = "") -> dict:
    """저장 전에 실행 가능성과 구체성을 규칙 기반으로 검사한다."""
    issues = []
    story_keys = {story.get("key") for story in stories if story.get("key")}
    feature_groups = artifacts.get("feature_groups", [])
    story_groups = artifacts.get("story_groups", {})
    allowed_sources = set(artifacts.get("source_catalog", []))
    figma_sources = {
        source for source in allowed_sources if str(source).startswith("Figma:")
    }
    allowed_categories = {category for category, _ in CHECKLIST_TEMPLATE}
    seen_titles = set()

    def add(tc_id: str, severity: str, rule: str, message: str) -> None:
        issues.append({
            "tc_id": tc_id,
            "severity": severity,
            "rule": rule,
            "message": message,
        })

    vague_expected = re.compile(
        r"^(?:\d+\.\s*)?(정상(?:적으로)? 동작한다|문제없다|문제없이 동작한다|"
        r"기대 결과가 확인된다|성공한다|처리된다|확인된다)[.!]?$"
    )

    for tc in artifacts.get("tc_draft", []):
        tc_id = tc.get("id", "TC-UNKNOWN")
        title = tc.get("title", "").strip()
        test_type = tc.get("test_type", "Functional")
        steps = tc.get("steps", [])

        if not title:
            add(tc_id, "ERROR", "title", "Scenario 제목이 없습니다.")
        elif title in seen_titles:
            add(tc_id, "WARNING", "duplicate_title", "동일한 Scenario 제목이 중복되었습니다.")
        seen_titles.add(title)

        min_steps, max_steps = (10, 20) if test_type == "Workflow E2E" else (5, 10)
        if len(steps) < min_steps or len(steps) > max_steps:
            add(
                tc_id, "ERROR", "step_count",
                f"{test_type} 필수 Step 수는 {min_steps}~{max_steps}개이며 현재 {len(steps)}개입니다.",
            )

        for index, step in enumerate(steps, 1):
            action = str(step.get("step", "")).strip()
            expected = str(step.get("expected_result", "")).strip()
            if not action:
                add(tc_id, "ERROR", "missing_action", f"Step {index}의 행동이 비어 있습니다.")
            elif not re.match(rf"^{index}\.\s*\S", action):
                add(tc_id, "WARNING", "step_number", f"Step {index}의 번호 형식이 올바르지 않습니다.")
            if not expected:
                add(tc_id, "ERROR", "missing_expected", f"Step {index}의 Expected Result가 비어 있습니다.")
            elif vague_expected.fullmatch(expected):
                add(tc_id, "WARNING", "vague_expected", f"Step {index}의 Expected Result가 모호합니다: {expected}")
            if evidence_corpus:
                quoted_terms = re.findall(r"['\"]([^'\"\n]{2,100})['\"]", f"{action} {expected}")
                unsupported = [term for term in quoted_terms if term not in evidence_corpus]
                if unsupported:
                    add(
                        tc_id, "WARNING", "unsupported_ui_text",
                        f"Step {index}에서 근거 자료에 없는 UI 문구를 인용했습니다: {', '.join(unsupported)}",
                    )

        if not tc.get("pre_condition"):
            add(tc_id, "ERROR", "pre_condition", "계정/권한/데이터/환경 사전조건이 없습니다.")
        if not tc.get("test_data"):
            add(tc_id, "ERROR", "test_data", "구체적인 Test Data가 없습니다.")
        if not tc.get("source_evidence"):
            add(tc_id, "ERROR", "source_evidence", "Jira/Confluence/Figma 근거가 없습니다.")
        else:
            invalid_sources = [source for source in tc.get("source_evidence", []) if source not in allowed_sources]
            if invalid_sources:
                add(
                    tc_id, "ERROR", "invalid_source_evidence",
                    f"허용 목록에 없는 근거입니다: {', '.join(invalid_sources)}",
                )
        if figma_sources and _is_ui_tc(tc):
            linked_figma = [
                source for source in tc.get("source_evidence", [])
                if str(source).startswith("Figma:")
            ]
            if not linked_figma:
                add(
                    tc_id, "WARNING", "figma_mapping",
                    "UI 관련 TC이지만 연결된 Figma 화면 근거가 없습니다.",
                )
        if not tc.get("checklist_categories"):
            add(tc_id, "ERROR", "checklist_mapping", "Checklist category 연결이 없습니다.")
        else:
            invalid_categories = [
                category for category in tc.get("checklist_categories", [])
                if category not in allowed_categories
            ]
            if invalid_categories:
                add(
                    tc_id, "ERROR", "invalid_checklist_category",
                    f"허용되지 않은 Checklist category입니다: {', '.join(invalid_categories)}",
                )

        jira_keys = tc.get("jira_keys", [])
        if isinstance(jira_keys, str):
            jira_keys = [jira_keys]
        if story_keys and not jira_keys:
            add(tc_id, "ERROR", "jira_mapping", "연결된 Jira Story가 없습니다.")
        invalid_jira = [key for key in jira_keys if key not in story_keys]
        if invalid_jira:
            add(tc_id, "ERROR", "invalid_jira_mapping", f"입력에 없는 Jira Key입니다: {', '.join(invalid_jira)}")

        if test_type == "Workflow E2E":
            required_groups = 2 if len(feature_groups) > 1 else 1
            covered_groups = tc.get("covered_groups", [])
            if len(covered_groups) < required_groups:
                add(
                    tc_id, "ERROR", "workflow_coverage",
                    f"Workflow E2E는 기능 그룹 {required_groups}개 이상을 연결해야 합니다.",
                )
            invalid_groups = [group for group in covered_groups if group not in feature_groups]
            if invalid_groups:
                add(tc_id, "ERROR", "invalid_workflow_group", f"존재하지 않는 기능 그룹입니다: {', '.join(invalid_groups)}")

    for group_name in feature_groups:
        functional_tcs = [
            tc for tc in artifacts.get("tc_draft", [])
            if tc.get("test_type") == "Functional" and tc.get("feature_group") == group_name
        ]
        required_count = max(3, len(story_groups.get(group_name, [])))
        if len(functional_tcs) < required_count:
            add(
                "GROUP", "ERROR", "functional_tc_count",
                f"{group_name}: Functional TC 최소 {required_count}개 중 {len(functional_tcs)}개만 생성되었습니다.",
            )
        covered = {
            key for tc in functional_tcs for key in tc.get("jira_keys", [])
        }
        missing = [key for key in story_groups.get(group_name, []) if key not in covered]
        if missing:
            add(
                "GROUP", "ERROR", "group_jira_coverage",
                f"{group_name}: Functional TC에서 미커버 Jira {', '.join(missing)}",
            )

    workflow_count = sum(
        1 for tc in artifacts.get("tc_draft", []) if tc.get("test_type") == "Workflow E2E"
    )
    if workflow_count < 3:
        add("WORKFLOW", "ERROR", "workflow_tc_count", f"Workflow E2E 최소 3개 중 {workflow_count}개만 생성되었습니다.")

    coverage = artifacts.get("coverage_summary", {})
    if coverage.get("total_stories") and coverage.get("coverage_rate", 0) < 80:
        add(
            "COVERAGE", "ERROR", "jira_coverage_rate",
            f"Jira Coverage가 {coverage.get('coverage_rate', 0)}%로 최소 기준 80%보다 낮습니다.",
        )

    errors = sum(1 for issue in issues if issue["severity"] == "ERROR")
    warnings = sum(1 for issue in issues if issue["severity"] == "WARNING")
    artifacts["quality_report"] = {
        "passed": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "issues": issues,
    }
    return artifacts


def repair_tc_draft(artifacts: dict, evidence_corpus: str) -> list:
    """품질 ERROR가 난 TC Draft를 근거 안에서 한 번 자동 보정한다."""
    errors = [
        issue for issue in artifacts.get("quality_report", {}).get("issues", [])
        if issue.get("severity") == "ERROR"
    ]
    prompt = f"""
아래 TC Draft가 규칙 기반 품질 검사에서 실패했습니다. 오류를 모두 수정한 전체 TC 목록을 반환하세요.
{KOREAN_OUTPUT_RULE}

수정 규칙:
- JSON 키와 enum 값(test_type, feature_group, checklist_categories 등)은 지정된 스키마/허용값을 유지하되, 사람이 읽는 모든 본문 값은 한국어로 작성한다.
- 기존의 유효한 TC는 삭제하지 말고 오류가 있는 항목만 최소 수정한다.
- Functional은 5~10 Step, Workflow E2E는 10~20 Step으로 만든다.
- 각 Step은 구체적인 사용자 행동과 관찰 가능한 Expected Result를 가진다.
- UI 레이블과 메시지는 근거에 실제 존재하는 문구만 그대로 사용한다. 근거가 없으면 임의 이름을 만들지 말고 일반 행동으로 표현한다.
- jira_keys, feature_group, covered_groups, source_evidence는 아래 허용 목록 안에서만 사용한다.
- 누락된 그룹 TC, Workflow TC, Jira 커버리지는 새 TC를 추가해 충족한다.
- 모든 TC에 pre_condition, test_data, checklist_categories, source_evidence를 채운다.

품질 오류:
{json.dumps(errors, ensure_ascii=False, indent=2)}

허용 기능 그룹:
{json.dumps(artifacts.get('feature_groups', []), ensure_ascii=False)}

그룹별 Jira:
{json.dumps(artifacts.get('story_groups', {}), ensure_ascii=False, indent=2)}

허용 Source Evidence:
{json.dumps(artifacts.get('source_catalog', []), ensure_ascii=False, indent=2)}

허용 Checklist Categories:
{json.dumps([category for category, _ in CHECKLIST_TEMPLATE], ensure_ascii=False)}

근거 원문:
{evidence_corpus}

현재 TC Draft:
{json.dumps(artifacts.get('tc_draft', []), ensure_ascii=False, indent=2)}

JSON 외 텍스트 출력 금지:
{{"tc_draft": [/* 수정 완료된 전체 TC */]}}
"""
    result = ai.chat_json(prompt, max_tokens=16000)
    return result.get("tc_draft", []) if isinstance(result, dict) else []

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
            contents.append(
                f"## [Confluence] {page['title']}\n"
                f"Source URL: {url}\n"
                f"{page['content_text']}"
            )
            print(
                f"  로드 완료: {page['title']} "
                f"(정제 전 {len(page['content'])}자 / 정제 후 {len(page['content_text'])}자)"
            )
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
        while True:
            jql_or_url = input("입력 (건너뛰려면 빈 줄): ").strip()
            if not jql_or_url:
                break
            normalized_jql = jira._to_jql(jql_or_url)
            if normalized_jql != jql_or_url:
                print(f"  JQL 자동 교정: {normalized_jql}")
            try:
                print("\n스토리 조회 중...")
                stories = jira.get_stories(normalized_jql)
                print(f"총 {len(stories)}개 스토리 조회됨")
                break
            except Exception as e:
                print(f"  Jira 조회 실패: {e}")
                print("  JQL을 수정해 다시 입력하세요. 앞서 불러온 Figma/Confluence 자료는 유지됩니다.")

    return figma_images, confluence_spec, stories


def _process_groups(
    grouped_stories: list,
    confluence_spec: str,
    figma_images: list,
    confluence: ConfluenceClient,
    space_key: str,
    parent_id: str,
) -> None:
    """선택한 그룹 전체를 통합 분석해 Design/TC Draft 페이지를 하나씩 저장."""
    group_names = [name for name, _ in grouped_stories]
    all_stories = [story for _, items in grouped_stories for story in items]
    story_groups = {
        name: [story.get("key", "") for story in items if story.get("key")]
        for name, items in grouped_stories
    }
    document_name = group_names[0] if len(group_names) == 1 else "통합 테스트"

    print(f"\n[{document_name}] 통합 처리 중...")
    print("  Figma UI 근거 구조화 중...")
    try:
        figma_evidence = analyze_figma_evidence(figma_images or [])
    except Exception as e:
        print(f"  Figma 근거 구조화 실패 — TEXT 노드만 사용: {e}")
        figma_evidence = {
            "screens": [
                {
                    "source_id": image.get("description", ""),
                    "visible_text": image.get("visible_text", []),
                    "controls": [], "input_fields": [], "messages": [],
                    "states": [], "uncertainties": ["이미지 구조화 분석 실패"],
                }
                for image in (figma_images or [])
            ]
        }

    print("  AI 통합 Test Design 생성 중...")

    artifacts = generate_test_design_only(
        all_stories,
        confluence_spec,
        figma_images or [],
        figma_evidence,
        story_groups,
    )
    raw_tcs = []
    for index, (group_name, group_stories) in enumerate(grouped_stories, 1):
        print(f"  [{index}/{len(grouped_stories)}] {group_name} Functional TC 생성 중...")
        try:
            raw_tcs.extend(generate_functional_tcs(
                group_name,
                group_stories,
                confluence_spec,
                figma_images or [],
                figma_evidence,
            ))
        except Exception as e:
            print(f"  {group_name} Functional TC 생성 실패: {e}")

    print("  Workflow / E2E TC 생성 중...")
    try:
        raw_tcs.extend(generate_workflow_tcs(
            grouped_stories,
            confluence_spec,
            figma_images or [],
            figma_evidence,
        ))
    except Exception as e:
        print(f"  Workflow / E2E TC 생성 실패: {e}")

    artifacts["tc_draft"] = raw_tcs
    artifacts = normalize_test_design_artifacts(artifacts)
    artifacts["feature_groups"] = group_names
    artifacts["story_groups"] = story_groups
    artifacts["source_catalog"] = _source_catalog(all_stories, confluence_spec, figma_images)

    print("  상세 Mindmap / Flowchart 생성 중...")
    try:
        diagrams = generate_detailed_diagrams(
            all_stories,
            confluence_spec,
            figma_images or [],
            figma_evidence,
            artifacts,
        )
        if diagrams.get("mindmap_plantuml"):
            artifacts["mindmap_plantuml"] = diagrams["mindmap_plantuml"]
        if diagrams.get("flowchart_plantuml"):
            artifacts["flowchart_plantuml"] = diagrams["flowchart_plantuml"]
    except Exception as e:
        print(f"  상세 다이어그램 생성 실패 — 기본 다이어그램 사용: {e}")

    artifacts = build_coverage_matrix(artifacts, all_stories)
    evidence_corpus = "\n".join([
        _format_story_sources(all_stories),
        confluence_spec or "",
        _format_figma_evidence(figma_evidence),
    ])
    artifacts = validate_tc_quality(artifacts, all_stories, evidence_corpus)

    if artifacts.get("quality_report", {}).get("error_count"):
        first_error_count = artifacts["quality_report"]["error_count"]
        print(f"  품질 ERROR {first_error_count}개 자동 보정 중... (최대 1회)")
        try:
            repaired_tcs = repair_tc_draft(artifacts, evidence_corpus)
            if repaired_tcs:
                artifacts["tc_draft"] = repaired_tcs
                artifacts = normalize_test_design_artifacts(artifacts)
                artifacts["feature_groups"] = group_names
                artifacts["story_groups"] = story_groups
                artifacts["source_catalog"] = _source_catalog(
                    all_stories, confluence_spec, figma_images
                )
                artifacts = build_coverage_matrix(artifacts, all_stories)
                artifacts = validate_tc_quality(artifacts, all_stories, evidence_corpus)
                print(
                    f"  자동 보정 후 ERROR "
                    f"{artifacts['quality_report']['error_count']}개"
                )
        except Exception as e:
            print(f"  자동 보정 실패 — 기존 결과를 유지합니다: {e}")

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
    for index, name in enumerate(group_names, 1):
        count = sum(
            1 for tc in tc_draft
            if tc.get("test_type") == "Functional" and tc.get("feature_group") == name
        )
        print(f"     1.{index} {name} Functional: {count}개")
    workflow_count = sum(1 for tc in tc_draft if tc.get("test_type") == "Workflow E2E")
    print(f"     2. Workflow / E2E: {workflow_count}개")

    coverage = artifacts.get("coverage_summary", {})
    if coverage.get("total_stories"):
        print(
            f"  → Jira Coverage: {coverage.get('covered_stories', 0)}/"
            f"{coverage.get('total_stories', 0)} ({coverage.get('coverage_rate', 0)}%)"
        )
        if coverage.get("uncovered_jira_keys"):
            print(f"     미커버: {', '.join(coverage['uncovered_jira_keys'])}")

    figma_coverage = artifacts.get("figma_coverage_summary", {})
    if figma_coverage.get("total_screens"):
        print(
            f"  → Figma Coverage: {figma_coverage.get('covered_screens', 0)}/"
            f"{figma_coverage.get('total_screens', 0)} "
            f"({figma_coverage.get('coverage_rate', 0)}%)"
        )
        if figma_coverage.get("unmapped_ui_tc_ids"):
            print(
                "     Figma 미연결 UI TC: "
                + ", ".join(figma_coverage["unmapped_ui_tc_ids"])
            )

    quality = artifacts.get("quality_report", {})
    print(
        f"  → TC 품질 검사: ERROR {quality.get('error_count', 0)} / "
        f"WARNING {quality.get('warning_count', 0)}"
    )
    for issue in quality.get("issues", []):
        print(
            f"     [{issue.get('severity')}] {issue.get('tc_id')} "
            f"{issue.get('rule')}: {issue.get('message')}"
        )

    save_with_errors = False
    if quality.get("error_count"):
        print(
            "  ⚠ 자동 보정 후에도 품질 ERROR가 남았습니다. "
            "TC Draft에는 품질 이슈 목록이 함께 표시됩니다."
        )
        save_with_errors = (
            input("  그래도 Confluence에 임시 산출물로 저장할까요? (y/n): ")
            .strip().lower() == "y"
        )
        if not save_with_errors:
            _print_ai_usage()
            return

    if not save_with_errors and input("  Confluence에 저장할까요? (y/n): ").strip().lower() != "y":
        _print_ai_usage()
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 렌더링 오류로 한 페이지만 생성되는 일을 막기 위해 외부 저장 전에 두 HTML을 모두 완성한다.
    design_html = build_test_design_page(document_name, all_stories, artifacts)
    tc_html = build_tc_draft_page(document_name, all_stories, artifacts)
    backup_dir = _save_local_output_backup(
        document_name,
        now.replace(":", "-").replace(" ", "_"),
        artifacts,
        design_html,
        tc_html,
    )
    print(f"  → 로컬 백업 저장 완료: {backup_dir}")

    design_title = f"[Test Design] {document_name} ({now})"
    tc_title = f"{'[품질검토필요] ' if save_with_errors else ''}[TC Draft] {document_name} ({now})"
    design_link = ""
    tc_link = ""
    try:
        design_link = _create_confluence_page_with_recovery(
            confluence, space_key, design_title, design_html, parent_id
        )
        print(f"  ✓ Test Design 저장 완료: {design_link}")
        tc_link = _create_confluence_page_with_recovery(
            confluence, space_key, tc_title, tc_html, parent_id
        )
        print(f"  ✓ TC Draft 저장 완료: {tc_link}")
    except Exception as e:
        print(f"  Confluence 저장 실패: {e}")
        print(
            "  네트워크/API 타임아웃일 수 있습니다. Confluence에 일부 페이지만 생성됐는지 확인하고, "
            f"필요하면 {backup_dir}의 HTML/JSON 백업으로 복구하세요."
        )
        if design_link:
            print(f"  생성 완료된 Test Design: {design_link}")
        if tc_link:
            print(f"  생성 완료된 TC Draft: {tc_link}")
        _print_ai_usage()
        return

    if input("\n  TestCollab에도 TC를 등록할까요? (y/n): ").strip().lower() == "y":
        _upload_to_testcollab(artifacts, document_name)

    _print_ai_usage()


def _upload_to_testcollab(artifacts: dict, document_name: str) -> None:
    """생성된 TC Draft를 TestCollab에 업로드한다."""
    from .testcollab_client import TestCollabClient
    try:
        tc_client = TestCollabClient()
        if not tc_client.token or not tc_client.project_id:
            print("  TestCollab API 토큰 또는 프로젝트 ID가 설정되지 않았습니다.")
            print("  .env에 TESTCOLLAB_API_TOKEN, TESTCOLLAB_PROJECT_ID를 확인해주세요.")
            return
    except Exception as e:
        print(f"  TestCollab 연결 실패: {e}")
        return

    suites = []
    try:
        suites = tc_client.get_suites()
    except Exception as e:
        print(f"  Suite 목록 조회 실패: {e}")

    suite_id = None
    if suites:
        print("\n  기존 Suite 목록:")
        for i, suite in enumerate(suites, 1):
            print(f"    {i}. {suite.get('title', '')} (ID: {suite.get('id', '')})")
        print("    0. 새 Suite 생성")
        choice = input("  Suite 번호 선택: ").strip()
        if choice == "0":
            suite_title = input(f"  새 Suite 이름 (기본: {document_name}): ").strip() or document_name
            try:
                new_suite = tc_client.create_suite(suite_title)
                suite_id = new_suite.get("id")
                print(f"  ✓ Suite 생성 완료: {suite_title} (ID: {suite_id})")
            except Exception as e:
                print(f"  Suite 생성 실패: {e}")
                return
        else:
            try:
                suite_id = suites[int(choice) - 1].get("id")
            except (ValueError, IndexError):
                print("  올바른 번호를 입력해주세요.")
                return
    else:
        suite_title = input(f"  새 Suite 이름 (기본: {document_name}): ").strip() or document_name
        try:
            new_suite = tc_client.create_suite(suite_title)
            suite_id = new_suite.get("id")
            print(f"  ✓ Suite 생성 완료: {suite_title} (ID: {suite_id})")
        except Exception as e:
            print(f"  Suite 생성 실패: {e}")
            return

    tc_draft = artifacts.get("tc_draft", [])
    print(f"\n  TestCollab에 TC {len(tc_draft)}개 업로드 중...")
    results = tc_client.upload_tc_draft(tc_draft, suite_id)
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    fail_count = len(results) - ok_count
    print(f"  → 업로드 완료: 성공 {ok_count}개 / 실패 {fail_count}개")


def _print_ai_usage() -> None:
    usage = ai.usage_summary()
    cost = (
        f"${usage['estimated_cost_usd']:.4f}"
        if usage.get("pricing_known") else "가격표 미등록 모델"
    )
    print(
        f"  → AI 사용량: {usage['provider']}/{usage['model']} · "
        f"{usage['calls']} calls · input {usage['input_tokens']:,} · "
        f"output {usage['output_tokens']:,} tokens · 예상 {cost}"
    )


def _select_ai_provider() -> bool:
    print("\n사용할 AI를 선택하세요:")
    print("  1. OpenAI (기본: gpt-4o)")
    print("  2. Claude (기본: claude-sonnet-4-6)")
    choice = input("선택 (기본 1): ").strip() or "1"
    provider = "anthropic" if choice == "2" else "openai"
    try:
        ai.configure(provider)
    except RuntimeError as e:
        print(f"설정 오류: {e}")
        return False
    provider_name, model = ai.current_config()
    print(f"  → {provider_name}/{model} 사용")
    return True


def run_tc_pipeline():
    print("\n=== TC 산출물 생성 ===")

    if not _select_ai_provider():
        return

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
        groups = normalize_story_groups(classify_stories(stories), stories)
        group_list = list(groups.items())

        print("\n=== 분류된 그룹 ===")
        for i, (name, keys) in enumerate(group_list, 1):
            print(f"  {i}. {name} ({len(keys)}개): {', '.join(keys)}")

        choice = input("\n작업할 그룹 번호 선택 (전체는 0): ").strip()
        selected_groups = group_list if choice == "0" else [group_list[int(choice) - 1]]
    else:
        selected_groups = [("스펙 기반 TC", [])]

    grouped_stories = []
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
        grouped_stories.append((group_name, group_stories))

    _process_groups(
        grouped_stories,
        confluence_spec,
        figma_images,
        confluence,
        space_key,
        parent_id,
    )

    print("\n=== 완료 ===")
