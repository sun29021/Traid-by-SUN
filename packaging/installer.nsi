; Traid installer (NSIS). Built by scripts\build-installer.ps1 after PyInstaller.
; Per-user install: no administrator rights needed, nothing written outside the user profile.
Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!define APP_NAME "Traid"
!define APP_VERSION "0.1.0"
!define APP_PUBLISHER "Xavier Sun"
!define APP_EXE "Traid.exe"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Traid"
!ifndef SOURCE_DIR
  !define SOURCE_DIR "..\build\dist\Traid"
!endif
!ifndef OUT_FILE
  !define OUT_FILE "..\build\Traid-Setup-${APP_VERSION}.exe"
!endif

Name "${APP_NAME}"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"
BrandingText "Traid · Designed & developed by Xavier Sun"

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "FileDescription" "Traid installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "Designed & developed by Xavier Sun"

!include "MUI2.nsh"
!define MUI_ICON "traid.ico"
!define MUI_UNICON "traid.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Install Traid"
!define MUI_WELCOMEPAGE_TEXT "Traid replaces short text in your photos using real characters learned from your own reference images. Everything runs on this computer.$\r$\n$\r$\nDesigned & developed by Xavier Sun."
!define MUI_LICENSEPAGE_TEXT_TOP "Please read the acceptable use terms."
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Start Traid now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "terms.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ; Close a running Traid so its files can be replaced.
  nsExec::Exec 'taskkill /IM ${APP_EXE} /F'
FunctionEnd

Section "Traid" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  ; Replace a previous version cleanly (user data lives elsewhere, in %LOCALAPPDATA%\Traid).
  RMDir /r "$INSTDIR\_internal"
  File /r "${SOURCE_DIR}\*.*"
  File "traid.ico"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\traid.ico"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\traid.ico"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\traid.ico"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /IM ${APP_EXE} /F'
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\traid.ico"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  DeleteRegKey HKCU "Software\${APP_NAME}"
  ; Profiles, glyphs, edits and backups in %LOCALAPPDATA%\Traid are kept on purpose.
SectionEnd
