# 설정 파일 작성법 — `config/apps.yaml`

> 최종 수정: 2026-08-08

## 0. 먼저 알아둘 것

- 실제로 쓰는 파일은 `config/apps.yaml`이고, 이 파일은 **git에 올라가지 않습니다.**
  프로그램 설치 경로가 PC마다 다르기 때문입니다. (`C:\` 인 기기도, `D:\` 인 기기도 있음)
- 저장소에는 `config/apps.example.yaml`(예시)만 들어 있습니다. 이걸 복사해서 시작하세요.

```powershell
copy config\apps.example.yaml config\apps.yaml
```

> ⚠️ **다른 PC로 옮길 때 주의**: `apps.yaml`은 git으로 따라오지 않습니다.
> 새 기기에서는 example을 다시 복사해 그 기기의 경로로 채워야 합니다.

---

## 1. 전체 구조

파일은 크게 두 덩어리입니다.

```yaml
detection:   # 박수를 얼마나 예민하게 감지할지
apps:        # 박수 치면 무엇을 실행할지
```

---

## 2. `apps` — 실행할 프로그램 목록

항목 하나에 프로그램 하나입니다. **위에서 아래 순서대로** 실행됩니다.

```yaml
apps:
  - name: VS Code                 # 로그에 표시될 이름 (아무거나)
    type: exe                     # 종류 (아래 표 참고)
    path: "C:/Program Files/Microsoft VS Code/Code.exe"
    args: ["F:/dev/clapping_setup"]   # 실행 인자 (선택)
    delay: 0.5                    # 실행 후 다음 항목까지 대기 초 (선택)
```

### `type` 종류

| type | 무엇을 여나 | `path`에 쓰는 값 | 예시 |
|------|-------------|------------------|------|
| `exe` | 설치된 프로그램 | 실행파일 전체 경로 | `"C:/Program Files/Google/Chrome/Application/chrome.exe"` |
| `url` | 웹사이트 (기본 브라우저) | 주소 | `"https://github.com"` |
| `folder` | 탐색기 창 | 폴더 경로 | `"F:/dev"` |
| `store` | Microsoft Store 앱 | 앱 ID (아래 3장 참고) | `"Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"` |

### 자주 쓰는 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `name` | (필수) | 로그에 표시할 이름 |
| `type` | `exe` | 위 표 참고 |
| `path` | (필수) | 경로 또는 주소 |
| `args` | 없음 | 실행 인자 목록. 브라우저에 열 주소, IDE에 열 폴더 등 |
| `delay` | `0` | **이 항목을 실행한 뒤** 다음 항목까지 기다릴 초. 무거운 프로그램 뒤에 0.5~2초를 주면 PC가 덜 버벅입니다 |
| `enabled` | `true` | `false`로 두면 지우지 않고 잠시 끌 수 있습니다 |

### 경로 쓸 때 주의 ⚠️

Windows 경로의 역슬래시(`\`)는 YAML에서 특수문자로 해석될 수 있습니다. 셋 중 하나로 쓰세요.

```yaml
path: "C:/Program Files/App/app.exe"      # ✅ 권장: 슬래시(/) — Windows도 이걸 이해합니다
path: 'C:\Program Files\App\app.exe'      # ✅ 작은따옴표로 감싸기
path: "C:\\Program Files\\App\\app.exe"   # ✅ 역슬래시 두 번
path: "C:\Program Files\App\app.exe"      # ❌ 깨질 수 있음
```

---

## 3. 실행 경로 찾는 법

**설치된 프로그램(exe)**
1. 시작 메뉴에서 프로그램 검색 → 우클릭 → `파일 위치 열기`
2. 나온 바로가기 우클릭 → `속성` → `대상(T)` 칸의 경로를 복사

**Microsoft Store 앱(store)**
1. `Win + R` → `shell:AppsFolder` 입력 → 앱 목록 창이 열림
2. 원하는 앱 우클릭 → `바로 가기 만들기` → 만들어진 바로가기 속성에서 ID 확인

또는 PowerShell에서:
```powershell
Get-StartApps | Where-Object { $_.Name -like "*계산기*" }
```

---

## 4. `detection` — 감지 민감도

기본값으로 시작하고, 문제가 생기면 아래 표를 보고 조절하세요.

```yaml
detection:
  sensitivity: 6.0        # 배경 소음 대비 몇 배 커야 박수로 볼지
  min_interval_ms: 150    # 두 박수 사이 최소 간격
  max_interval_ms: 800    # 두 박수 사이 최대 간격
  high_freq_ratio: 0.4    # 고음 비율 하한 (저음 소리 배제용)
  cooldown_sec: 5.0       # 발동 후 재감지 금지 시간
```

### 증상별 처방 💊

| 증상 | 이렇게 고치세요 |
|------|-----------------|
| 아무것도 안 했는데 프로그램이 켜짐 (오탐) | `sensitivity`를 7~9로 올리기 → 더 큰 소리만 인정 |
| 키보드·마우스 소리에 반응 | `high_freq_ratio`를 0.5~0.6으로 올리기 |
| 문 닫는 소리, 발소리에 반응 | `high_freq_ratio`를 올리기 (저음 차단) |
| 박수를 쳐도 안 켜짐 | `sensitivity`를 4~5로 내리기 / 마이크에 더 가까이 |
| 박수를 천천히 치는데 인식 안 됨 | `max_interval_ms`를 1000~1200으로 올리기 |
| 한 번 박수에 두 번 발동 | `cooldown_sec`를 8~10으로 올리기 |

> 💡 **튜닝 순서 추천**: `sensitivity`를 먼저 맞추고 → 그래도 오탐이 있으면 `high_freq_ratio` → 마지막에 간격 값.
> 한 번에 여러 개를 바꾸면 뭐가 효과였는지 알 수 없습니다.

---

## 5. 전체 예시

```yaml
detection:
  sensitivity: 6.0
  max_interval_ms: 800

apps:
  # 1. 작업 폴더를 연 상태로 IDE 실행
  - name: VS Code
    type: exe
    path: "C:/Program Files/Microsoft VS Code/Code.exe"
    args: ["F:/dev/clapping_setup"]
    delay: 1.0        # 무거우니 다음 앱까지 1초 대기

  # 2. 업무용 탭 2개를 한 창에
  - name: 업무 브라우저
    type: exe
    path: "C:/Program Files/Google/Chrome/Application/chrome.exe"
    args: ["https://github.com", "https://mail.google.com"]

  # 3. 메신저
  - name: Slack
    type: exe
    path: "C:/Users/User/AppData/Local/slack/slack.exe"

  # 4. 오늘은 음악 없이 — 지우지 않고 꺼두기
  - name: Spotify
    type: exe
    path: "C:/Users/User/AppData/Roaming/Spotify/Spotify.exe"
    enabled: false
```
