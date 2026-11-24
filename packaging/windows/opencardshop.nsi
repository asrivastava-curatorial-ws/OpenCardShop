; OpenCardShop Windows installer (NSIS 3). Built by packaging/build_windows.sh, which
; passes /DVERSION=<x.y.z> /DSTAGE=<folder with runtime\, app\, opencardshop.ico, LICENSE.txt> /DOUTFILE=<exe>.
; Installs for the current user only: no administrator rights are needed.
Unicode true
SetCompressor /SOLID lzma
!include "MUI2.nsh"

!define APP "OpenCardShop"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenCardShop"
!define PYW '"$INSTDIR\runtime\pythonw.exe" -E -s "$INSTDIR\app\main.py"'

Name "${APP} ${VERSION}"
OutFile "${OUTFILE}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\OpenCardShop"
InstallDirRegKey HKCU "Software\OpenCardShop" "InstallDir"
BrandingText "${APP} ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${APP} installer"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2026 Abhisht Srivastava, MIT licence"

!define MUI_ICON "${STAGE}\opencardshop.ico"
!define MUI_UNICON "${STAGE}\opencardshop.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchOpenCardShop
!define MUI_FINISHPAGE_RUN_TEXT "Start OpenCardShop"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${STAGE}\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function LaunchOpenCardShop
    Exec '${PYW}'
FunctionEnd

Section "OpenCardShop" SecMain
    SectionIn RO
    ; An upgrade replaces the program; My library and settings live in %LOCALAPPDATA% / %APPDATA%.
    RMDir /r "$INSTDIR\runtime"
    RMDir /r "$INSTDIR\app"
    SetOutPath "$INSTDIR"
    File /r "${STAGE}\runtime"
    File /r "${STAGE}\app"
    File "${STAGE}\opencardshop.ico"
    File "${STAGE}\LICENSE.txt"
    File "${STAGE}\opencardshop-cli.cmd"

    CreateShortcut "$SMPROGRAMS\OpenCardShop.lnk" "$INSTDIR\runtime\pythonw.exe" '-E -s "$INSTDIR\app\main.py"' "$INSTDIR\opencardshop.ico" 0 SW_SHOWNORMAL "" "Design, personalise and print folded cards"
    CreateShortcut "$DESKTOP\OpenCardShop.lnk" "$INSTDIR\runtime\pythonw.exe" '-E -s "$INSTDIR\app\main.py"' "$INSTDIR\opencardshop.ico" 0 SW_SHOWNORMAL "" "Design, personalise and print folded cards"

    ; Open .occard cards with OpenCardShop (current user).
    WriteRegStr HKCU "Software\Classes\.occard" "" "OpenCardShop.Card"
    WriteRegStr HKCU "Software\Classes\OpenCardShop.Card" "" "OpenCardShop card"
    WriteRegStr HKCU "Software\Classes\OpenCardShop.Card\DefaultIcon" "" "$INSTDIR\opencardshop.ico"
    WriteRegStr HKCU "Software\Classes\OpenCardShop.Card\shell\open\command" "" '${PYW} "%1"'
    System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'

    WriteRegStr HKCU "Software\OpenCardShop" "InstallDir" "$INSTDIR"
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "Abhisht Srivastava"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\opencardshop.ico"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "EstimatedSize" ${SIZE_KB}
SectionEnd

Section "Uninstall"
    Delete "$SMPROGRAMS\OpenCardShop.lnk"
    Delete "$DESKTOP\OpenCardShop.lnk"
    RMDir /r "$INSTDIR\runtime"
    RMDir /r "$INSTDIR\app"
    Delete "$INSTDIR\opencardshop.ico"
    Delete "$INSTDIR\LICENSE.txt"
    Delete "$INSTDIR\opencardshop-cli.cmd"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"
    ReadRegStr $0 HKCU "Software\Classes\.occard" ""
    StrCmp $0 "OpenCardShop.Card" 0 +2
        DeleteRegKey HKCU "Software\Classes\.occard"
    DeleteRegKey HKCU "Software\Classes\OpenCardShop.Card"
    System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
    DeleteRegKey HKCU "Software\OpenCardShop"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
    ; Your cards, My library (%LOCALAPPDATA%\OpenCardShop) and settings (%APPDATA%\OpenCardShop) are kept.
SectionEnd
