; ClapDesk 설치본 만들기 (Inno Setup 6)
;
; 직접 컴파일하지 말고 python tools/build_installer.py 를 쓰세요.
; 그 스크립트가 exe 를 먼저 굽고(--onedir), 버전을 소스에서 읽어 여기에 넘겨줍니다.
;
; ⚠️ 관리자 권한을 요구하지 않습니다 (PrivilegesRequired=lowest).
;    개인 유틸리티에 UAC 창을 띄울 이유가 없고, 무엇보다 사용자 폴더에 설치하면
;    프로그램 옆에 설정 파일(config/apps.yaml)을 쓸 수 있습니다.
;    Program Files 에 넣으면 그 폴더가 읽기 전용이라 설정이 %LOCALAPPDATA% 로 흩어집니다.

#define AppName "ClapDesk"
#define AppPublisher "enryu0210"
#define AppExe "ClapDesk.exe"

; 아래 두 값은 build_installer.py 가 /D 옵션으로 넘겨줍니다 (없으면 기본값 사용)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\ClapDesk"
#endif

[Setup]
AppId={{8E2F6A31-4C7D-4B58-9E0A-7C1D2F5B3A64}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

; {autopf} 는 권한에 따라 알아서 결정된다.
; 관리자 없이 설치하므로 실제로는 %LOCALAPPDATA%\Programs\ClapDesk 가 된다.
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 결과물
OutputDir=..\dist
OutputBaseFilename=ClapDesk-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 64비트 Windows 전용 (sounddevice·PortAudio 가 64비트로 묶인다)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 설치·제거 중에 프로그램이 켜져 있으면 알아서 닫는다.
; ⚠️ 이게 없으면 "파일이 사용 중" 오류가 나거나, 낡은 파일이 남아 이상하게 동작한다.
CloseApplications=yes
RestartApplications=no

; 제거 프로그램에 아이콘을 붙인다 (Windows 설정 > 앱 목록에서 보인다)
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; \
    GroupDescription: "추가 작업:"; Flags: unchecked
Name: "autostart"; Description: "Windows 시작할 때 자동 실행 (트레이에서 조용히 시작)"; \
    GroupDescription: "추가 작업:"

[Files]
; --onedir 로 구운 폴더를 통째로 넣는다
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 설정 예시를 함께 넣어 둔다. 손으로 편집하고 싶은 사람에게 출발점이 된다.
; (프로그램은 [프로그램 설정] 화면에서 config\apps.yaml 을 알아서 만든다)
Source: "..\config\apps.example.yaml"; DestDir: "{app}\config"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; ⚠️ 값 이름(ClapDesk)과 명령 형식(--minimized)은 프로그램의 autostart.py 와
;    **똑같아야 한다.** 다르면 화면의 '자동 실행' 토글이 꺼진 것처럼 보이는데
;    실제로는 로그인할 때 실행되는 유령 상태가 된다.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "ClapDesk"; \
    ValueData: """{app}\{#AppExe}"" --minimized"; \
    Flags: uninsdeletevalue; Tasks: autostart
; 자동 실행을 고르지 않았다면 예전에 남아 있던 등록을 지운다 (재설치 시 정리)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: none; ValueName: "ClapDesk"; \
    Flags: deletevalue uninsdeletevalue; Tasks: not autostart

[Run]
Description: "지금 {#AppName} 실행"; Filename: "{app}\{#AppExe}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 프로그램이 만든 설정 파일까지 지운다. 사용자가 만든 목록이라 아깝지만,
; 제거했는데 찌꺼기가 남는 것도 좋지 않다. (마이크 선택·보정값은 %LOCALAPPDATA% 에
; 따로 있고 그건 남긴다 — 다시 설치했을 때 처음부터 설정하지 않아도 되게)
Type: filesandordirs; Name: "{app}\config"
