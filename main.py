import os
from dotenv import load_dotenv

load_dotenv()

MENU = {
    "1": ("TC 산출물 생성 (Jira 스토리 / Confluence 스펙 기반)", "clients.story_tc_pipeline", "run_tc_pipeline"),
    "2": ("KPI 대시보드 생성", "clients.kpi_dashboard", "run_kpi_dashboard"),
    "3": ("중복 버그 탐지", "clients.duplicate_detector", "run_duplicate_detector"),
    "4": ("TestCollab TC 생성 테스트", None, None),
    "9": ("브라우저 탐색 기반 TC 생성 (추후 개발)", None, None),
}


def test_testcollab_create_only():
    from clients.testcollab_client import TestCollabClient
    result = TestCollabClient().create_test_case(
        title="API 테스트_TC 생성",
        description="API 생성 확인용",
        pre_condition="테스트용 사전조건",
        steps=[{"step": "1. 테스트 동작", "expected_result": "1. 테스트 결과"}],
        suite_id=112218,
        priority="Normal"
    )
    print("생성 성공:", result)


def main():
    print("=== QA 자동화 툴 ===")
    for key, (label, _, _) in MENU.items():
        print(f"{key}. {label}")
    print("0. 종료")

    choice = input("\n선택: ").strip()

    if choice == "0":
        print("종료합니다.")
        return

    if choice not in MENU:
        print("잘못된 입력입니다.")
        return

    label, module_path, func_name = MENU[choice]

    if choice == "4":
        test_testcollab_create_only()
        return

    if choice == "9" or module_path is None:
        print("추후 개발 예정입니다.")
        return

    import importlib
    getattr(importlib.import_module(module_path), func_name)()


if __name__ == "__main__":
    main()
