from datetime import datetime
import os
import re
from uuid import uuid4


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


def _wrap_mermaid_node_labels(code: str, max_chars: int = 18) -> str:
    """따옴표로 감싼 Mermaid 노드 문구가 박스 밖으로 넘치지 않게 줄바꿈한다."""
    node_label = re.compile(r'(?<=[\[\(\{])"([^"\n]+)"(?=[\]\)\}])')

    def wrap(match: re.Match) -> str:
        label = match.group(1)
        if "<br/>" in label or len(label) <= max_chars:
            return f'"{label}"'

        words = label.split()
        lines = []
        current = ""
        for word in words:
            if len(word) > max_chars:
                if current:
                    lines.append(current)
                    current = ""
                lines.extend(word[i:i + max_chars] for i in range(0, len(word), max_chars))
            elif not current:
                current = word
            elif len(current) + 1 + len(word) <= max_chars:
                current += f" {word}"
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        return f'"{"<br/>".join(lines)}"'

    return node_label.sub(wrap, code)


def mermaid_macro(code: str) -> str:
    """Visualize for Confluence의 Mermaid 매크로 storage format."""
    code = (code or "").strip()
    if code.startswith("```mermaid"):
        code = code[len("```mermaid"):].strip()
    if code.endswith("```"):
        code = code[:-3].strip()

    if not code:
        return "<p>생성된 Mermaid 다이어그램 없음</p>"

    code = _wrap_mermaid_node_labels(code)
    # CDATA 종료 문자열이 Mermaid 본문에 들어와 XML을 깨뜨리는 것을 방지한다.
    code = code.replace("]]>", "]] ]>")
    macro_id = str(uuid4())
    return (
        '<ac:structured-macro ac:name="vfcVisualizeMermaid" '
        'ac:schema-version="1" data-layout="default" '
        f'ac:macro-id="{macro_id}">'
        '<ac:parameter ac:name="display-options">'
        '{:rf &quot;mermaid&quot;}'
        '</ac:parameter>'
        f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>'
        '</ac:structured-macro>'
    )


def plantuml_macro(code: str) -> str:
    """Visualizer for Confluence의 PlantUML 매크로 storage format."""
    code = (code or "").strip()
    if code.startswith("```plantuml"):
        code = code[len("```plantuml"):].strip()
    if code.endswith("```"):
        code = code[:-3].strip()
    if not code:
        return "<p>생성된 PlantUML 마인드맵 없음</p>"

    if code.startswith("@startmindmap"):
        # Confluence Visualizer에서 mindmap의 Creole <br> 처리가 버전에 따라 깨질 수 있어
        # PlantUML arithmetic mindmap 노드 안의 줄바꿈 문자로 보정한다.
        code = re.sub(r"<br\s*/?>", r"\\n", code, flags=re.IGNORECASE)
    else:
        # PlantUML Creole 줄바꿈은 <br>이며 <br/>는 일부 Confluence Visualizer에서 문자로 노출된다.
        code = re.sub(r"<br\s*/>", "<br>", code, flags=re.IGNORECASE)
    # Provider가 지시를 놓쳐도 QA 분류 노드명은 문서 언어에 맞춰 일관되게 표시한다.
    branch_names = {
        "Functional Testing": "기능 테스트",
        "UI/UX Testing": "UI/UX 테스트",
        "UI-UX Testing": "UI/UX 테스트",
        "Integration Testing": "통합 테스트",
        "Exceptional Handling Testing": "예외 처리 테스트",
        "Non-Functional Testing": "비기능 테스트",
        "Technical Quality Assurance": "기술 품질 보증",
        "Common-Compatibility Testing": "공통/호환성 테스트",
    }
    for english, korean in branch_names.items():
        code = code.replace(english, korean)

    code = code.replace("]]>", "]] ]>")
    macro_name = os.getenv("CONFLUENCE_PLANTUML_MACRO_NAME", "vfcVisualizePlantUML")
    macro_id = str(uuid4())
    return (
        f'<ac:structured-macro ac:name="{macro_name}" '
        'ac:schema-version="1" data-layout="default" '
        f'ac:macro-id="{macro_id}">'
        '<ac:parameter ac:name="display-options">'
        '{:rf &quot;plantuml&quot;}'
        '</ac:parameter>'
        f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>'
        '</ac:structured-macro>'
    )


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

    coverage_summary = artifacts.get("coverage_summary", {})
    uncovered_keys = coverage_summary.get("uncovered_jira_keys", [])
    coverage_info = (
        f"<p><strong>Jira Story Coverage:</strong> "
        f"{coverage_summary.get('covered_stories', 0)} / {coverage_summary.get('total_stories', 0)} "
        f"({coverage_summary.get('coverage_rate', 0)}%)</p>"
        f"<p><strong>Functional TC:</strong> {coverage_summary.get('functional_tc_count', 0)} / "
        f"<strong>Workflow E2E TC:</strong> {coverage_summary.get('workflow_tc_count', 0)}</p>"
        f"<p><strong>미커버 Jira:</strong> {', '.join(uncovered_keys) if uncovered_keys else '없음'}</p>"
    )
    coverage_rows = []
    for item in artifacts.get("coverage_matrix", []):
        jira_keys = item.get("jira_keys", [])
        categories = item.get("checklist_category", [])
        if isinstance(jira_keys, str):
            jira_keys = [jira_keys]
        if isinstance(categories, str):
            categories = [categories]
        coverage_rows.append([
            item.get("feature", ""),
            ", ".join(jira_keys),
            ", ".join(categories) or "미매핑",
            item.get("test_type", ""),
            item.get("tc_id", ""),
            item.get("scenario", ""),
            item.get("coverage_status", ""),
        ])
    coverage_table = (
        coverage_info
        + table(
            ["Feature", "Jira", "Checklist Category", "Test Type", "TC ID", "Scenario", "Status"],
            coverage_rows,
        )
        if coverage_rows else coverage_info + "<p>Coverage Matrix 없음</p>"
    )

    figma_summary = artifacts.get("figma_coverage_summary", {})
    figma_rows = [
        [
            row.get("figma_source", ""),
            ", ".join(row.get("tc_ids", [])),
            "<br/>".join(row.get("scenarios", [])),
            row.get("coverage_status", ""),
        ]
        for row in artifacts.get("figma_coverage_matrix", [])
    ]
    figma_coverage_html = (
        f"<p><strong>화면 Coverage:</strong> {figma_summary.get('covered_screens', 0)} / "
        f"{figma_summary.get('total_screens', 0)} ({figma_summary.get('coverage_rate', 0)}%)</p>"
        + (
            table(["Figma 화면", "TC ID", "Scenario", "Status"], figma_rows)
            if figma_rows else "<p>제공된 Figma 화면 없음</p>"
        )
    )

    risk_rows = [[r.get("risk", ""), r.get("impact", ""), r.get("mitigation", "")] for r in artifacts.get("risk_analysis", [])]
    risk_table = table(["Risk", "Impact", "Mitigation"], risk_rows) if risk_rows else "<p>Risk 없음</p>"

    mindmap = artifacts.get("mindmap_plantuml", "")
    legacy_mindmap = artifacts.get("mindmap_mermaid", "")
    flowchart = artifacts.get("flowchart_plantuml", "")
    legacy_flowchart = artifacts.get("flowchart_mermaid", "")
    mindmap_html = plantuml_macro(mindmap) if mindmap else mermaid_macro(legacy_mindmap)
    flowchart_html = plantuml_macro(flowchart) if flowchart else mermaid_macro(legacy_flowchart)
    output_html = (
        f"<h4>Mindmap PlantUML</h4>{mindmap_html}"
        f"<h4>Workflow PlantUML</h4>{flowchart_html}"
    )

    return (
        page_header(f"[Test Design] {group_name}", "회사 Test Design Template 기반 자동 생성")
        + section("문서 정보", "<p><strong>담당자:</strong> </p><p><strong>작성일/최종 수정일:</strong> </p>")
        + section("테스트 개요", summary_html)
        + section("Test Scope", scope_html)
        + section("문서 분리 판단", split_html)
        + section("Jira 정보", story_table)
        + section("Test Case 설계", checklist_table)
        + section("Coverage Matrix", coverage_table)
        + section("Figma Coverage Matrix", figma_coverage_html)
        + section("Risk Analysis", risk_table)
        + section("산출물", output_html)
        + info_panel("AI가 생성한 Test Design 초안입니다. QA 검토 후 최종 확정하세요.")
    )


def build_tc_draft_page(group_name: str, stories: list, artifacts: dict) -> str:
    test_cases = artifacts.get("tc_draft", [])
    feature_groups = list(artifacts.get("feature_groups", []))

    for tc in test_cases:
        name = tc.get("feature_group", "") or "공통 / E2E"
        if name not in feature_groups and name != "공통 / E2E":
            feature_groups.append(name)

    def is_workflow(tc: dict) -> bool:
        return (
            tc.get("test_type") == "Workflow E2E"
            or (tc.get("feature_group", "") or "공통 / E2E") == "공통 / E2E"
        )

    def build_tc_table(cases: list) -> str:
        if not cases:
            return "<p>생성된 TC Draft 없음</p>"
        def display_lines(value) -> str:
            if value is None:
                return ""
            values = value if isinstance(value, list) else [value]
            lines = []
            for item in values:
                if isinstance(item, dict):
                    lines.append(", ".join(f"{key}: {val}" for key, val in item.items()))
                elif isinstance(item, (list, tuple)):
                    lines.extend(str(part) for part in item)
                else:
                    lines.append(str(item))
            return "<br/>".join(lines)

        tc_rows = []
        for tc in cases:
            pre_condition = display_lines(tc.get("pre_condition", ""))
            test_data = display_lines(tc.get("test_data", ""))
            note_parts = [tc.get("description", ""), tc.get("note", "")]
            note_text = "<br/>".join(part for part in note_parts if part)

            jira_keys = tc.get("jira_keys", [])
            if isinstance(jira_keys, str):
                jira_keys = [jira_keys]
            jira_text = ", ".join(str(key) for key in jira_keys)
            covered_groups = tc.get("covered_groups", [])
            if isinstance(covered_groups, str):
                covered_groups = [covered_groups]
            coverage_text = " → ".join(str(group) for group in covered_groups) or str(tc.get("feature_group", ""))
            source_evidence = tc.get("source_evidence", [])
            if isinstance(source_evidence, str):
                source_evidence = [source_evidence]
            evidence_text = display_lines(source_evidence)

            steps = tc.get("steps", [])
            if not steps:
                tc_rows.append([
                    tc.get("id", ""), tc.get("test_type", "Functional"),
                    tc.get("priority", ""), tc.get("title", ""), pre_condition,
                    test_data, "", "", note_text, coverage_text, evidence_text, jira_text,
                ])
                continue

            for step_index, step in enumerate(steps):
                tc_rows.append([
                    tc.get("id", "") if step_index == 0 else "",
                    tc.get("test_type", "Functional") if step_index == 0 else "",
                    tc.get("priority", "") if step_index == 0 else "",
                    tc.get("title", "") if step_index == 0 else "",
                    pre_condition if step_index == 0 else "",
                    test_data if step_index == 0 else "",
                    str(step.get("step", "")),
                    str(step.get("expected_result", "")),
                    note_text if step_index == 0 else "",
                    coverage_text if step_index == 0 else "",
                    evidence_text if step_index == 0 else "",
                    jira_text if step_index == 0 else "",
                ])

        return table(
            [
                "TC ID", "Type", "Priority", "Scenario", "Pre-condition", "Test Data", "Step",
                "Expected Result", "Note", "Coverage", "근거 자료", "JIRA",
            ],
            tc_rows,
        )

    functional_sections = []
    for group_index, feature_group in enumerate(feature_groups, 1):
        group_tcs = [
            tc for tc in test_cases
            if not is_workflow(tc)
            and (tc.get("feature_group", "") or "공통 / E2E") == feature_group
        ]
        functional_sections.append(
            f"<h5>1.{group_index} {feature_group}</h5>{build_tc_table(group_tcs)}"
        )

    workflow_tcs = [tc for tc in test_cases if is_workflow(tc)]
    quality = artifacts.get("quality_report", {})
    quality_rows = [
        [
            issue.get("severity", ""), issue.get("tc_id", ""),
            issue.get("rule", ""), issue.get("message", ""),
        ]
        for issue in quality.get("issues", [])
    ]
    quality_content = (
        f"<p><strong>결과:</strong> {'PASS' if quality.get('passed') else 'REVIEW REQUIRED'} / "
        f"ERROR {quality.get('error_count', 0)} / WARNING {quality.get('warning_count', 0)}</p>"
        + (
            table(["Severity", "TC ID", "Rule", "Message"], quality_rows)
            if quality_rows else "<p>발견된 품질 이슈 없음</p>"
        )
    )
    figma_summary = artifacts.get("figma_coverage_summary", {})
    unmapped_ui = figma_summary.get("unmapped_ui_tc_ids", [])
    figma_content = (
        f"<p><strong>화면 Coverage:</strong> {figma_summary.get('covered_screens', 0)} / "
        f"{figma_summary.get('total_screens', 0)} ({figma_summary.get('coverage_rate', 0)}%)</p>"
        f"<p><strong>Figma 미연결 UI TC:</strong> "
        f"{', '.join(unmapped_ui) if unmapped_ui else '없음'}</p>"
    )
    tc_content = (
        "<h4>1. 기능별 Functional TC</h4>"
        + ("".join(functional_sections) if functional_sections else "<p>생성된 Functional TC 없음</p>")
        + "<h4>2. Workflow / E2E TC</h4>"
        + build_tc_table(workflow_tcs)
    )

    return (
        page_header(f"[TC Draft] {group_name}", "TestCollab 이관용 TC Draft")
        + section("TC 품질 검사", quality_content)
        + section("Figma Coverage", figma_content)
        + section("Test Cases", tc_content)
        + info_panel("AI가 생성한 TC Draft 초안입니다. QA 검토 후 TestCollab으로 이관하세요.")
    )
