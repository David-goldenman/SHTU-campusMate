$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'scripts/launcher.ps1')
function Assert($Condition, [string]$Message) { if (!$Condition) { throw $Message } }
function Rejects([scriptblock]$Work) {
    $failed = $false
    try { & $Work | Out-Null } catch { $failed = $true }
    Assert $failed 'Invalid launch options must be rejected.'
}

$options = Read-LaunchOptions @('--distro', 'My Ubuntu', '--port', '17666', '--no-browser')
Assert ($options.Distro -eq 'My Ubuntu' -and $options.Port -eq 17666 -and $options.NoBrowser) 'CLI values were not preserved.'
Assert (Read-LaunchOptions @('--help')).Help 'Help flag failed.'
Assert (Read-LaunchOptions @('--version')).Version 'Version flag failed.'
Assert ((Read-LaunchOptions @('--share')).Share) 'Share flag failed.'
Assert (!(Read-LaunchOptions @()).Share) 'Phone access must stay opt-in.'
foreach ($invalid in @(@('--port'), @('--port', '80'), @('--port', '65536'), @('--port', 'a'), @('--distro'), @('--unknown'))) {
    Rejects { Read-LaunchOptions $invalid }
}
$names = ConvertFrom-WslList @("U`0b`0u`0n`0t`0u`0-`02`02`0.`00`04`0`r", '', '  Debian ')
Assert (($names -join ',') -eq 'Ubuntu-22.04,Debian') 'WSL UTF-16/null normalization failed.'
$installed = @('docker-desktop', 'Ubuntu-22.04', 'Debian', 'Other Linux')
Assert ((Get-WslCandidates $installed '' 'Debian')[0] -eq 'Debian') 'Default WSL was not preferred.'
Assert ((@(Get-WslCandidates $installed 'Other Linux' 'Debian') -join '') -eq 'Other Linux') 'Explicit WSL selection failed.'
Assert ((Get-WslCandidates $installed '' 'docker-desktop') -notcontains 'docker-desktop') 'Container-managed WSL must not be auto-selected.'
Rejects { Get-WslCandidates $installed 'Missing' 'Debian' }
Rejects { Get-WslCandidates @('docker-desktop') '' 'docker-desktop' }
Assert ((Quote-Bash "a'b c") -eq "'a'\''b c'") 'Shell path quoting failed.'
Assert ((Get-UvCandidates 'C:\workspace' | Where-Object { $_ -match 'runtime[\\/]tools[\\/]uv[\\/]Scripts[\\/]uv\.exe$' })) 'Private uv bootstrap path is missing.'

$previousUv = $env:CAMPUS_UV
$temporary = Join-Path $root ('.codex/tmp/launcher-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
$fakeUv = Join-Path $temporary 'uv.exe'
New-Item -ItemType File -Path $fakeUv -Force | Out-Null
try {
    $env:CAMPUS_UV = $fakeUv
    Assert ((Find-Uv $temporary) -eq $fakeUv) 'CAMPUS_UV override was not used.'
    $env:CAMPUS_UV = Join-Path $temporary 'missing-uv.exe'
    Rejects { Find-Uv $temporary }
} finally {
    if ($null -ne $previousUv) { $env:CAMPUS_UV = $previousUv }
    else { Remove-Item Env:CAMPUS_UV -ErrorAction SilentlyContinue }
}

New-Item -ItemType Directory -Path (Join-Path $temporary '.private/runtime/launcher') -Force | Out-Null
@{ launch_id = 'owned-instance'; port = 17666; pid = 123 } | ConvertTo-Json | Set-Content (Join-Path $temporary '.private/runtime/launcher/server.json')
$script:Health = @{ application = 'campus-framework'; launch_id = 'owned-instance' }
function Invoke-RestMethod { param($Uri, $TimeoutSec) return $script:Health }
try {
    Assert ((Get-CampusServer $temporary).port -eq 17666) 'Matching running instance was not reused.'
    Assert ($null -eq (Get-CampusServer $temporary 'another-launch')) 'Watcher accepted another launch.'
    $script:Health.launch_id = 'different-checkout'
    Assert ($null -eq (Get-CampusServer $temporary)) 'A different checkout on the same port was accepted.'
    $script:Health = @{ application = 'another-app'; launch_id = 'owned-instance' }
    Assert ($null -eq (Get-CampusServer $temporary)) 'Another application on the port was accepted.'
    @{ launch_id = 'owned-instance'; port = '16666@example.invalid' } | ConvertTo-Json | Set-Content (Join-Path $temporary '.private/runtime/launcher/server.json')
    $script:InvalidPortRequests = 0
    function Invoke-RestMethod { $script:InvalidPortRequests++; return @{ application = 'campus-framework'; launch_id = 'owned-instance' } }
    Assert ($null -eq (Get-CampusServer $temporary)) 'Malformed port was accepted.'
    Assert ($script:InvalidPortRequests -eq 0) 'Invalid port must be rejected before making a request.'
} finally {
    Remove-Item Function:\Invoke-RestMethod
    # The generated fixture is retained under .codex for diagnosis; it holds no private data.
}
Write-Host 'launcher: argument validation, WSL selection, path quoting and server ownership passed'
