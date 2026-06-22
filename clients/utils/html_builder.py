from datetime import datetime


def page_header(title: str, subtitle: str = "") -> str:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    return f"""
<h2>{title}</h2>
<p>생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
{sub}
""".strip()


def table(headers: list, rows: list) -> str:
    """headers: 컬럼명 리스트 / rows: 각 행을 리스트로"""
    ths = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><tr>{ths}</tr>{trs}</table>"


def section(title: str, content: str, level: int = 3) -> str:
    return f"<h{level}>{title}</h{level}>\n{content}\n"


def info_panel(text: str) -> str:
    """Confluence info 매크로"""
    return f'<ac:structured-macro ac:name="info"><ac:rich-text-body><p>{text}</p></ac:rich-text-body></ac:structured-macro>'


def code_block(code: str, language: str = "none") -> str:
    return f'<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">{language}</ac:parameter><ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body></ac:structured-macro>'


def build_test_design_page(group_name: str, stories: list, artifacts: dict) -> str:
    summary = artifacts.get("requirement_summary", {})
    if isinstance(summary, str):
        summary = {"feature_name": group_name, "purpose": summary, "change_type": "", "affected_modules": [], "user_types": []}

    scope = artifacts.get("test_scope", {})
    if isinstance(scope, str):
        scope = {"in_scope": [scope], "out_scope": []}
    elif isinstance(scope, list):
        scope = {"in_scope": scope, "out_scope": []}
    elif not isinstance(scope, dict):
        scope = {"in_scope": [], "out_scope": []}

    split = artifacts.get("split_recommendation", {})
    if isinstance(split, bool):
        split = {"required": split, "reason": "", "suggested_documents": []}
    elif isinstance(split, str):
        split = {"required": True, "reason": split, "suggested_documents": []}

    summary_html = (
        f"<p><strong>기능명:</strong> {summary.get('feature_name', '')}</p>"
        f"<p><strong>목적:</strong> {summary.get('purpose', '')}</p>"
        f"<p><strong>변경 유형:</strong> {summary.get('change_type', '')}</p>"
        f"<p><strong>영향 모듈:</strong> {', '.join(summary.get('affected_modules', []))}</p>"
        f"<p><strong>사용자 유형:</strong> {', '.join(summary.get('user_types', []))}</p>"
    )

    scope_html = (
        "<h4>In Scope</h4><ul>"
        + "".join(f"<li>{item}</li>" for item in scope.get("in_scope", []))
        + "</ul><h4>Out of Scope</h4><ul>"
        + "".join(f"<li>{item}</li>" for item in scope.get("out_scope", []))
        + "</ul>"
    )

    split_html = (
        f"<p><strong>Style Mode:</strong> {artifacts.get('style_mode', '')}</p>"
        f"<p><strong>분리 필요:</strong> {'Y' if split.get('required') else 'N'}</p>"
        f"<p><strong>사유:</strong> {split.get('reason', '')}</p>"
        "<ul>" + "".join(f"<li>{item}</li>" for item in split.get("suggested_documents", [])) + "</ul>"
    )

    story_rows = [[s.get("key", ""), s.get("summary", "")] for s in stories]
    story_table = table(["스토리 키", "제목"], story_rows) if story_rows else "<p>Jira Story 없음</p>"

    checklist_matrix = artifacts.get("checklist_matrix", {})
    checklist_rows = []
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
                    item.get("test_case_design", ""),
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
                item.get("test_case_design", ""),
            ])

    checklist_table = table(
        ["필수 요소", "체크리스트", "적용", "관련 기능", "미적용 사유/판단 사유", "Spec 검토 필요", "Test Case 구성 정보"],
        checklist_rows,
    )

    coverage_rows = [
        [c.get("feature", ""), c.get("checklist_category", ""), c.get("test_type", ""), c.get("tc_id", "")]
        for c in artifacts.get("coverage_matrix", [])
    ]
    coverage_table = table(["Feature", "Checklist Category", "Test Type", "TC ID"], coverage_rows) if coverage_rows else "<p>Coverage Matrix 없음</p>"

    risk_rows = [[r.get("risk", ""), r.get("impact", ""), r.get("mitigation", "")] for r in artifacts.get("risk_analysis", [])]
    risk_table = table(["Risk", "Impact", "Mitigation"], risk_rows) if risk_rows else "<p>Risk 없음</p>"

    mindmap = artifacts.get("mindmap_mermaid", "")
    flowchart = artifacts.get("flowchart_mermaid", "")
    output_html = f"<h4>Mindmap Mermaid</h4><pre>{mindmap}</pre><h4>Flowchart Mermaid</h4><pre>{flowchart}</pre>"

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
            tc_rows.append([tc.get("title", ""), "", pre_condition, "", "", tc.get("description", ""), ""])
            continue

        for idx, step in enumerate(steps):
            tc_rows.append([
                tc.get("title", "") if idx == 0 else "",
                tc.get("type", "") if idx == 0 else "",
                pre_condition if idx == 0 else "",
                step.get("step", ""),
                step.get("expected_result", ""),
                tc.get("description", "") if idx == 0 else "",
                ", ".join(s.get("key", "") for s in stories) if idx == 0 else "",
            ])

    tc_table = (
        table(["Depth1", "Depth2", "Pre-condition", "Step", "Expected Result", "Note", "JIRA"], tc_rows)
        if tc_rows else "<p>생성된 TC Draft 없음</p>"
    )

    return (
        page_header(f"[TC Draft] {group_name}", "TestCollab 이관용 TC Draft")
        + section("Test Cases", tc_table)
        + info_panel("AI가 생성한 TC Draft 초안입니다. QA 검토 후 TestCollab으로 이관하세요.")
    )
