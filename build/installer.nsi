; 音频停顿编辑器 NSIS 安装脚本
; 用法: makensis build/installer.nsi

!define APP_NAME "音频停顿编辑器"
!define APP_VERSION "0.1.0"
!define APP_PUBLISHER "audio-pause-editor"
!define APP_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

SetCompressor /SOLID lzma

Name "${APP_NAME}"
OutFile "../dist/audio-pause-editor_${APP_VERSION}_x64-setup.exe"

InstallDir "$PROGRAMFILES64\${APP_NAME}"

; 安装页面
InstallDirRegKey HKLM "Software\${APP_NAME}" ""
ShowInstDetails show

Section "${APP_NAME}" SEC01
    SetOutPath "$INSTDIR"
    File /r "../dist/win-unpacked/*"

    ; 创建桌面快捷方式
    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\音频停顿编辑器.exe"
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\音频停顿编辑器.exe"

    ; 写入卸载信息
    WriteRegStr HKLM "Software\${APP_NAME}" "" "$INSTDIR"
    WriteRegStr HKLM "${APP_UNINST_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "${APP_UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "${APP_UNINST_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "${APP_UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${APP_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\uninstall.exe"
    RMDir /r "$INSTDIR"

    Delete "$DESKTOP\${APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"

    DeleteRegKey HKLM "Software\${APP_NAME}"
    DeleteRegKey HKLM "${APP_UNINST_KEY}"
SectionEnd
