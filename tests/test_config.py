"""설정 파일 처리 테스트.

설정 오류는 사용자가 가장 자주 만나는 문제다. 죽더라도 '왜 죽었는지'가
메시지에 있어야 하므로, 에러 상황을 테스트로 고정한다.

TODO(M4): load_config 구현 후 아래 시나리오를 실제 테스트로 작성.

  - 파일이 없을 때        → ConfigError, 메시지에 'apps.example.yaml' 안내 포함
  - YAML 문법이 깨졌을 때 → ConfigError, 문제 줄 번호 포함
  - apps 항목에 path 누락 → ConfigError, 몇 번째 항목인지 표시
  - detection 생략        → 기본값으로 정상 로드
  - enabled: false 항목   → 실행 대상에서 제외
"""
