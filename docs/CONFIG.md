# 설정 파일 작성법 — `config/apps.yaml`

> 최종 수정: 2026-08-09

## 0. 먼저 — 이 파일을 직접 안 고쳐도 됩니다 ⭐

프로그램의 **`[≡ 프로그램 설정]`** 버튼을 누르면 화면에서 목록을 편집할 수 있습니다.
`추가` → `찾아보기` 로 exe를 고르면 경로가 자동으로 채워지므로 오타가 날 일이 없습니다.

이 문서는 **파일을 직접 편집하고 싶을 때**, 또는 화면에 없는 항목
(감지 기준값 등)을 손볼 때 보세요.

> ⚠️ **화면에서 저장하면 이 파일을 다시 씁니다.** 직접 적어둔 주석은 그때 사라집니다.
> 직전 내용은 `apps.yaml.bak` 으로 남으니 되돌릴 수 있습니다.
> 손으로만 관리하고 싶다면 화면에서 저장하지 마세요.
> (`detection`·`audio` 값은 화면에서 저장해도 그대로 보존됩니다 — 보정 결과가 날아가지 않습니다)

---

## 0-0. 설정 파일이 두 개입니다

헷갈리기 쉬우니 먼저 구분하고 갑니다.

| 파일 | 누가 관리하나 | 위치 | 내용 |
|------|---------------|------|------|
| `config/apps.yaml` | **내가** 직접 편집 | 저장소 폴더 | 실행할 프로그램, 감지 민감도 |
| `settings.json` | **프로그램**이 저장 | `%LOCALAPPDATA%\ClapDesk\` | UI에서 고른 마이크 |

`settings.json`은 직접 열어볼 일이 거의 없습니다. 마이크를 다시 고르고 싶으면
프로그램의 `🎤 마이크 변경` 버튼을 누르거나, 콘솔에서 `--reset-setup`을 쓰면 됩니다.

`settings.json`에 들어가는 값:

| 항목 | 뜻 | 어디서 바꾸나 |
|------|-----|--------------|
| `device` / `device_label` | 고른 마이크 | 마이크 선택 화면 |
| `detection` | 보정으로 계산된 감지 기준값 | [🎯 박수 보정] |
| `auto_arm_on_unlock` | 화면 잠금을 풀면 자동으로 듣기 시작 | 메인 화면 체크박스 |
| `listen_timeout_min` | 이 시간 동안 박수가 없으면 자동으로 멈춤 (0=무제한) | 메인 화면 '듣는 시간' |

> 💡 **듣는 시간을 짧게 둘수록 오작동이 줄어듭니다.** 이 프로그램은 평소에 마이크를
> 아예 열지 않고, 잠금 해제 직후처럼 필요한 순간에만 잠깐 듣습니다.
> 자세한 이유는 [docs/DETECTION.md](DETECTION.md) 0-1장.

> 왜 나눴나요? 프로그램이 `apps.yaml`을 덮어쓰면 **아래에 있는 설명 주석이 전부 날아갑니다.**
> 그래서 apps.yaml은 읽기만 하고, 프로그램이 저장할 값은 따로 둡니다.

---

## 0-1. 먼저 알아둘 것

- 실제로 쓰는 파일은 `config/apps.yaml`이고, 이 파일은 **git에 올라가지 않습니다.**
  프로그램 설치 경로가 PC마다 다르기 때문입니다. (`C:\` 인 기기도, `D:\` 인 기기도 있음)
- 저장소에는 `config/apps.example.yaml`(예시)만 들어 있습니다. 이걸 복사해서 시작하세요.

```powershell
copy config\apps.example.yaml config\apps.yaml
```

> ⚠️ **다른 PC로 옮길 때 주의**: `apps.yaml`은 git으로 따라오지 않습니다.
> 새 기기에서는 example을 다시 복사해 그 기기의 경로로 채워야 합니다.

### 프로그램이 설정 파일을 찾는 순서

절대 경로를 코드에 박아두지 않고, 아래 순서로 **처음 발견된 파일**을 씁니다.
(기기마다 저장소 위치가 다르고, exe로 만들면 위치가 또 달라지기 때문입니다)

| 순서 | 위치 | 언제 쓰이나 |
|------|------|-------------|
| 1 | 환경변수 `CLAP_LAUNCHER_CONFIG` 가 가리키는 파일 | 다른 설정으로 잠깐 돌려볼 때 |
| 2 | `<프로그램 폴더>/config/apps.yaml` | **보통 이것** (저장소에서 개발·실행할 때) |
| 3 | `%LOCALAPPDATA%\ClapDesk\apps.yaml` | exe를 쓰기 금지 폴더에 설치했을 때 |

지금 어떤 파일을 읽고 있는지는 아래 명령으로 확인할 수 있습니다.

```powershell
python -m clap_launcher --check-config
```

### 고쳤으면 바로 확인하세요 ⭐

경로 오타는 "박수를 쳐도 아무 일도 안 일어난다"의 가장 흔한 원인입니다.
박수를 치기 전에 두 명령으로 미리 확인하세요.

```powershell
python -m clap_launcher --check-config   # 문법·항목 검사 + 실행 목록 보기 (실행은 안 함)
python -m clap_launcher --launch-apps    # 박수 없이 지금 바로 실행해 보기
```

```
✅ 설정 파일을 읽었습니다: F:\dev\clapping_setup\config\apps.yaml

실행 목록 (3개 켜짐 / 전체 4개):
  ○ [exe   ] VS Code — C:/Program Files/Microsoft VS Code/Code.exe  delay=1.0s
  ○ [url   ] 캘린더 확인 — https://calendar.google.com
  ○ [folder] 작업 폴더 열기 — F:/dev
  × [exe   ] Spotify — C:/.../Spotify.exe        ← × 는 enabled: false 로 꺼둔 항목
```

> 💡 **하나가 실패해도 나머지는 그대로 실행됩니다.** 실패한 항목은 이름과 이유를
> 함께 알려주므로(`Slack: 경로를 찾을 수 없습니다: ...`) 어디를 고칠지 바로 알 수 있습니다.
> 프로그램을 껐다 켤 필요 없이, 파일을 고치면 다음 박수부터 새 설정이 적용됩니다.

---

## 1. 전체 구조

파일은 크게 세 덩어리입니다.

```yaml
audio:       # 어떤 마이크를 쓸지
detection:   # 박수를 얼마나 예민하게 감지할지
apps:        # 박수 치면 무엇을 실행할지
```

---

## 1-1. `audio` — 쓸 마이크 고르기

> 💡 **보통은 이 항목을 직접 손댈 필요가 없습니다.** 프로그램을 처음 실행하면
> 마이크 선택 화면이 나오고, 거기서 고른 값이 자동으로 저장됩니다.
> 아래 내용은 콘솔로 작업하거나 설정을 직접 지정하고 싶을 때 보세요.

```yaml
audio:
  device:            # 비워두면 Windows 기본 입력 장치
```

**박수를 쳐도 아무 반응이 없다면 십중팔구 마이크 선택이 원인**입니다.

> ⚠️ **가장 흔한 함정**: 오디오 인터페이스나 Elgato Wave Link, 가상 오디오 케이블 같은
> 프로그램이 깔려 있으면 Windows 기본 입력 장치가 **실제 마이크가 아니라 가상 장치**로
> 잡혀 있는 경우가 많습니다. 그 프로그램이 꺼져 있으면 무음만 들어옵니다.

**확인 순서:**

```powershell
# 1. 어떤 장치들이 있는지 본다
python -m clap_launcher --list-devices

# 2. 지금 쓰는 장치가 실제로 소리를 받는지 본다 (박수 치면 막대가 튀어야 정상)
python -m clap_launcher --level

# 3. 안 튀면 다른 장치를 지정해서 다시 확인
python -m clap_launcher --level --device 3
python -m clap_launcher --level --device Logitech    # 이름 일부로도 됩니다
```

잘 되는 장치를 찾았으면 `apps.yaml`에 적어둡니다.

```yaml
audio:
  device: 3            # 번호로 지정
  # device: "Logitech" # 이름 일부로 지정 — USB를 다시 꽂아 번호가 바뀌어도 안전합니다
```

> 💡 같은 마이크가 목록에 여러 번 보이는 것은 정상입니다. Windows가 드라이버 방식
> (MME / DirectSound / WASAPI)별로 하나씩 보여주기 때문입니다. 아무거나 골라도 되지만,
> 잘 안 되면 같은 이름의 다른 방식을 시도해 보세요.

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
| `skip_if_running` | `true` | 이미 켜져 있으면 건너뜁니다. **창을 하나 더 띄우고 싶으면 `false`** |

> 💡 **`skip_if_running` 은 `exe` 에만 적용됩니다.** 웹 주소는 탭을 하나 더 여는 게
> 자연스럽고, 스토어 앱은 실행파일 이름을 알 수 없어 검사할 방법이 없습니다.
> 검사는 실행파일 **이름**으로 합니다(`Code.exe`). 그래서 서로 다른 폴더에 있는
> 같은 이름의 프로그램은 같은 것으로 봅니다.

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

## 4. `detection` — 감지 기준값

> 🎯 **먼저 이것부터**: 프로그램의 **[🎯 박수 보정]** 버튼을 누르고 박수를 5번 치세요.
> 본인 마이크로 친 실제 박수를 재서 아래 값들을 자동으로 정해줍니다.
> 손으로 숫자를 맞추는 것보다 훨씬 정확하고, 보정 결과가 아래 설정보다 우선합니다.

아래는 보정을 쓰지 않고 직접 만질 때의 설명입니다.

```yaml
detection:
  onset_rise_db: 8.0            # 배경 대비 몇 dB 뛰어야 "소리가 났다"고 볼지
  min_high_freq_ratio: 0.55     # 고음 비율 하한
  min_flatness: 0.12            # 잡음스러움 하한
  max_flatness: 0.50            # 잡음스러움 상한
  min_zero_crossing_rate: 0.35  # 날카로움 하한
  max_harmonicity: 0.55         # 음정 상한
  max_decay_ms: 60.0            # 소리 길이 상한 (종이·음악 배제)
  min_decay_ms: 14.0            # 소리 길이 하한 (키보드·클릭 배제)
  min_interval_ms: 150
  max_interval_ms: 800
  cooldown_sec: 5.0
```

> 🛡️ **오타는 조용히 무시하지 않고 오류로 알려줍니다.** 예를 들어 `max_harmonicty`(i 빠짐)라고
> 적으면 "모르는 항목입니다"라며 쓸 수 있는 항목 목록을 보여줍니다.
> 무시하고 넘어가면 "설정을 바꿨는데 왜 안 먹지?"로 시간을 날리게 되기 때문입니다.
>
> 하한이 상한보다 큰 조합(`min_decay_ms: 80` + `max_decay_ms: 60`)도 막습니다.
> 그렇게 두면 **어떤 소리도 통과할 수 없어** 박수를 쳐도 영영 반응하지 않습니다.

**⚠️ 여기에 '음량' 항목이 없는 것이 핵심입니다.** 판정은 전부 소리의 '모양'(비율)으로 합니다.
리미터(클리핑 가드)가 걸린 마이크에서도 흔들리지 않게 하기 위해서입니다.
자세한 이유는 [docs/DETECTION.md](DETECTION.md).

### 증상별 처방 💊

| 증상 | 이렇게 고치세요 |
|------|-----------------|
| **아무거나 다 반응함 / 안 잡힘 (대부분)** | **[🎯 박수 보정]을 먼저 하세요.** 아래 손보정은 그 다음입니다 |
| 기침·말소리에 반응 | `max_harmonicity`를 0.45로 내리기 (음정 있는 소리를 더 강하게 배제) |
| **키보드·마우스 클릭에 반응** | **보정을 다시 하되 2단계(평소 소리 내기)에서 실제로 타이핑하세요.** 손으로 고치려면 `min_decay_ms`를 18~20으로 올리거나 `max_flatness`를 0.42로 내리기 |
| 문 닫는 소리, 발소리에 반응 | `min_high_freq_ratio`를 0.7로 올리기 (저음 차단 강화) |
| 종이·비닐 소리에 반응 | `max_decay_ms`를 40으로 내리기 (짧은 소리만 인정) |
| 아무 소리에나 자꾸 반응 | `onset_rise_db`를 12~15로 올리기 (확실히 튀는 소리만 분석) |
| 박수를 쳐도 안 잡힘 | 메인 화면의 **'들린 소리' 로그에서 걸러진 이유**를 보고 그 항목을 완화 |
| 박수를 천천히 치는데 인식 안 됨 | `max_interval_ms`를 1000~1200으로 올리기 |
| 한 번 박수에 두 번 발동 | `cooldown_sec`를 8~10으로 올리기 |

> 💡 **메인 화면의 '들린 소리' 로그를 보세요.** 걸러진 소리마다 이유가 찍힙니다.
> 예를 들어 `· 음정이 있음(0.71) — 기침·말소리`가 뜨면서 내 박수가 안 잡힌다면,
> `max_harmonicity`를 0.75로 올리면 됩니다. 추측하지 말고 로그를 보고 고치세요.
>
> 한 번에 여러 개를 바꾸면 뭐가 효과였는지 알 수 없습니다. 하나씩 바꾸세요.

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
