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


def format_checklist() -> str:
    return "\n".join(f"- [{category}] {item}" for category, item in CHECKLIST_TEMPLATE)
