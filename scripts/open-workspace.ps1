param([string]$Root, [string]$Edge, [string]$LaunchId)
$ErrorActionPreference = 'Stop'
. (Join-Path $Root 'scripts/launcher.ps1')
# Only open the instance started by this launch, never another service on the port.
while ($true) {
    $state = Get-CampusServer $Root $LaunchId
    if ($state) {
        Start-Process -FilePath $Edge -ArgumentList "http://127.0.0.1:$($state.port)"
        break
    }
    Start-Sleep -Milliseconds 500
}
