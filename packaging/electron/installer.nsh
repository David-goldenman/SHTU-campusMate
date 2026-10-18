; Keep user data in place while uninstalling/replacing program files.
!macro customInstallMode
  StrCpy $isForceCurrentInstall "1"
!macroend

!macro customInstall
  CreateDirectory "$INSTDIR\.private"
!macroend

!macro customRemoveFiles
  IfFileExists "$INSTDIR\resources\app.asar" 0 invalidInstallRoot
  RMDir /r "$INSTDIR\resources"
  RMDir /r "$INSTDIR\locales"
  Delete "$INSTDIR\*.*"
  SetOutPath "$TEMP"
  Goto doneRemoving
  invalidInstallRoot:
    Abort "CampusMate program files could not be verified. User data was preserved."
  doneRemoving:
!macroend

