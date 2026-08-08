# 👏 Clapping Setup

**박수 두 번(짝짝)이면 일할 준비 끝.**

마이크로 박수 소리를 감지해서, 미리 등록해 둔 업무용 프로그램들을 한 번에 실행해 주는 Windows 데스크톱 유틸리티입니다.
재미로 만드는 개인 프로젝트지만, "매일 아침 똑같은 앱 8개 켜기"라는 진짜 귀찮음을 해결하는 게 목적입니다.

```
    짝    짝
     👏 👏      →   VSCode + Chrome + Slack + Spotify ... 동시 실행
```

## 어떻게 동작하나요

1. 프로그램이 백그라운드에서 마이크를 계속 듣습니다. (녹음은 **저장하지 않습니다.** 메모리에서만 분석)
2. "짧고 강한 소리"가 **0.15초~0.8초 간격으로 두 번** 들리면 박수로 판단합니다.
3. `config/apps.yaml`에 적어둔 프로그램들을 순서대로 실행합니다.

## 빠른 시작 (구현 완료 후 기준)

```powershell
# 1. 가상환경
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 설치 (-e 는 코드를 고치면 바로 반영되는 개발 모드)
#    패키지가 src/ 아래에 있어서 이 과정을 거쳐야 `python -m` 으로 실행됩니다.
pip install -e .

# 3. 내 설정 파일 만들기 (예시 파일 복사)
copy config\apps.example.yaml config\apps.yaml

# 4. 실행
python -m clap_launcher
```

> ⚠️ `config/apps.yaml`은 **기기마다 프로그램 설치 경로가 다르므로 git에 올리지 않습니다.**
> 다른 PC에서 쓸 때는 `apps.example.yaml`을 다시 복사해서 그 기기에 맞게 경로를 채워야 합니다.

## 문서

| 문서 | 내용 |
|------|------|
| [docs/PLAN.md](docs/PLAN.md) | 프로젝트 목표, 기능 범위, 리스크, 개발 단계(마일스톤) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 모듈 구조, 데이터 흐름, 박수 감지 알고리즘 상세 |
| [docs/CONFIG.md](docs/CONFIG.md) | 설정 파일(`apps.yaml`) 작성법과 모든 옵션 설명 |

## 상태

🚧 **기획 단계 (v0.0)** — 현재는 계획 문서와 폴더 뼈대만 있습니다. 구현은 [PLAN.md의 마일스톤](docs/PLAN.md#5-개발-단계-마일스톤) 순서대로 진행합니다.

## 환경

- Windows 10/11
- Python 3.12+
- 마이크 (노트북 내장 마이크로 충분)
