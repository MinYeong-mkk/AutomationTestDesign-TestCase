import os
from collections import defaultdict
from datetime import datetime
from .jira_client import JiraClient
from .confluence_client import ConfluenceClient
from .utils.html_builder import page_header, section, table


def run_kpi_dashboard():
    print("\n=== KPI 대시보드 생성 ===")

    jira = JiraClient()
    projects = jira.get_projects()

    print("\n프로젝트 목록:")
    for i, p in enumerate(projects, 1):
        print(f"  {i}. [{p['key']}] {p['name']}")

    project = projects[int(input("\n분석할 프로젝트 번호 선택: ").strip()) - 1]

    print(f"\n{project['name']} 이슈 가져오는 중...")
    issues = jira.get_all_issues(project["key"], max_results=200)
    print(f"총 {len(issues)}개 이슈 분석 중...")

    kpi = _analyze(issues)
    _print_kpi(kpi, project["name"])

    if input("\nConfluence에 저장할까요? (y/n): ").strip().lower() != "y":
        return

    confluence = ConfluenceClient()
    title = f"[KPI] {project['name']} - {datetime.now().strftime('%Y-%m-%d')}"
    link = confluence.create_page(
        os.getenv("CONFLUENCE_SPACE_KEY"),
        title,
        _build_page(kpi, project["name"])
    )
    print(f"\nConfluence 페이지 생성 완료: {link}")


def _analyze(issues: list) -> dict:
    reporter_stats = defaultdict(lambda: {"reported": 0, "closed": 0})
    assignee_stats = defaultdict(lambda: {"assigned": 0, "closed": 0})
    priority_counts = defaultdict(int)
    type_counts = defaultdict(int)
    monthly_counts = defaultdict(int)

    for issue in issues:
        f = issue["fields"]
        reporter = (f.get("reporter") or {}).get("displayName", "Unknown")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        status = (f.get("status") or {}).get("name", "")
        is_closed = status in ("Done", "Closed", "Resolved")

        reporter_stats[reporter]["reported"] += 1
        assignee_stats[assignee]["assigned"] += 1
        priority_counts[(f.get("priority") or {}).get("name", "None")] += 1
        type_counts[(f.get("issuetype") or {}).get("name", "")] += 1
        monthly_counts[f.get("created", "")[:7]] += 1

        if is_closed:
            reporter_stats[reporter]["closed"] += 1
            assignee_stats[assignee]["closed"] += 1

    return {
        "total": len(issues),
        "reporter_stats": dict(reporter_stats),
        "assignee_stats": dict(assignee_stats),
        "priority_counts": dict(priority_counts),
        "type_counts": dict(type_counts),
        "monthly_counts": dict(sorted(monthly_counts.items())),
    }


def _print_kpi(kpi: dict, project_name: str):
    print(f"\n프로젝트: {project_name} | 전체: {kpi['total']}개")
    for label, data in [("이슈 타입", kpi["type_counts"]), ("우선순위", kpi["priority_counts"])]:
        print(f"\n[{label}별]")
        for k, v in data.items():
            print(f"  {k}: {v}개")
    print("\n[리포터별]")
    for name, s in kpi["reporter_stats"].items():
        print(f"  {name}: 제출 {s['reported']}개 / 완료 {s['closed']}개")


def _build_page(kpi: dict, project_name: str) -> str:
    priority_rows = [[k, v] for k, v in kpi["priority_counts"].items()]
    reporter_rows = [[n, s["reported"], s["closed"]] for n, s in kpi["reporter_stats"].items()]

    return (
        page_header(f"📊 {project_name} KPI 대시보드", f"전체 이슈: {kpi['total']}개")
        + section("우선순위별 이슈", table(["Priority", "건수"], priority_rows))
        + section("팀원별 리포트 현황", table(["이름", "제출", "완료"], reporter_rows))
    )
