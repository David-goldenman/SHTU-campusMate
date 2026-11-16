Unicode true
RequestExecutionLevel user
Name "campusMate"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\campusMate"
SetCompressor /SOLID lzma
SetCompressorDictSize 32
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchCampusMate
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "SimpChinese"

Section "campusMate"
  InitPluginsDir
  SetOutPath "$PLUGINSDIR\payload"
  File /r "${PAYLOAD}\*"
  SetOutPath "$PLUGINSDIR"
  File "${SCRIPTS}\install.ps1"
  File "${SCRIPTS}\launch-desktop.ps1"
  StrCpy $0 ""
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/NoShortcuts" $R1
  ${IfNot} ${Errors}
    StrCpy $0 "-NoShortcuts"
  ${EndIf}
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\install.ps1" -PayloadDirectory "$PLUGINSDIR\payload" -InstallDirectory "$INSTDIR" $0'
  Pop $1
  ${If} $1 != 0
    SetErrorLevel 1
    Abort "Installation could not finish. The previous program and user data were preserved."
  ${EndIf}
SectionEnd

Function LaunchCampusMate
  Exec '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$INSTDIR\launch.ps1"'
FunctionEnd
