#define MyAppName "小智打工人搭子"
#define MyAppVersion "0.3.1"
#define MyAppExeName "XiaozhiDesktopAssistant.exe"
[Setup]
AppId={{9E8732A5-BB92-4E96-9BD1-8C37D0C3CFA9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\XiaozhiDesktopAssistant
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=XiaozhiDesktopAssistant-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE-UPSTREAM-XIAOZHI-MCP-COMPUTER.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "其他选项:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
