# Windows PowerShell 5.1 compatible. This file defines helpers without starting anything.
function Invoke-Wsl([string]$Executable, [string[]]$Arguments, [switch]$Quiet) {
    # Windows PowerShell turns redirected native stderr into ErrorRecords. WSL's
    # proxy warning must not abort a successful command; its exit code is authoritative.
    $ErrorActionPreference = 'Continue'
    if ($Quiet) { & $Executable @Arguments 2>$null }
    else { & $Executable @Arguments }
    $script:WslExitCode = $LASTEXITCODE
}

function Read-LaunchOptions([string[]]$Values) {
    $result = @{ Distro = $env:CAMPUS_WSL_DISTRO; Port = $null; NoBrowser = $false; Check = $false; Help = $false; Version = $false }
    for ($i = 0; $i -lt $Values.Count; $i++) {
        switch ($Values[$i]) {
            { $_ -in '--help', '-h', '-?' } { $result.Help = $true }
            '--version' { $result.Version = $true }
            '--no-browser' { $result.NoBrowser = $true }
            '--check' { $result.Check = $true }
            { $_ -in '--distro', '--port' } {
                $flag = $_
                if (++$i -ge $Values.Count -or $Values[$i].StartsWith('--')) { throw "Missing value for $flag" }
                if ($flag -eq '--distro') { $result.Distro = $Values[$i] }
                else {
                    $port = 0
                    if (![int]::TryParse($Values[$i], [ref]$port) -or $port -lt 1024 -or $port -gt 65535) { throw 'Port must be between 1024 and 65535.' }
                    $result.Port = $port
                }
            }
            default { throw "Unknown option: $($Values[$i]). Use --help." }
        }
    }
    return $result
}

function ConvertFrom-WslList([string[]]$Lines) {
    @($Lines | ForEach-Object { ($_ -replace "`0", '').Trim() } | Where-Object { $_ })
}

function Get-WslCandidates([string[]]$Installed, [string]$Requested, [string]$Default) {
    if ($Requested) {
        if ($Requested -notin $Installed) { throw "WSL distribution '$Requested' is not installed. Run wsl --list --quiet." }
        return @($Requested)
    }
    $usable = @($Installed | Where-Object { $_ -notmatch '^(docker-desktop|podman|rancher-desktop)' })
    if (!$usable) { throw 'No development WSL distribution found. Install Ubuntu or Debian.' }
    @(@($Default | Where-Object { $_ -in $usable }) + @($usable | Where-Object { $_ -ne $Default } | Sort-Object { if ($_ -match '^(Ubuntu|Debian)') { 0 } else { 1 } }, { $_ }))
}

function Find-Edge {
    $candidates = @(
        (Get-Command msedge.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction SilentlyContinue).'(default)',
        (Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction SilentlyContinue).'(default)'
    )
    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, $env:LOCALAPPDATA)) {
        if ($base) { $candidates += Join-Path $base 'Microsoft/Edge/Application/msedge.exe' }
    }
    foreach ($candidate in $candidates) { if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate } }
    throw 'Microsoft Edge was not found. Install Edge for the workspace and school login windows.'
}

function Get-CampusServer([string]$Root, [string]$LaunchId = '') {
    try {
        $state = Get-Content -LiteralPath (Join-Path $Root '.codex/launcher/server.json') -Raw | ConvertFrom-Json
        $port = 0
        if (![int]::TryParse([string]$state.port, [ref]$port) -or $port -lt 1024 -or $port -gt 65535 -or !$state.launch_id -or ($LaunchId -and $state.launch_id -ne $LaunchId)) { return $null }
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/v1/health" -TimeoutSec 2
        if ($health.application -eq 'campus-framework' -and $health.launch_id -eq $state.launch_id) { return $state }
    } catch { }
    return $null
}

function Quote-Bash([string]$Value) { "'" + $Value.Replace("'", "'\''") + "'" }

function Initialize-WindowsTools([string]$Root, [string]$Wsl, [string]$Distribution) {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if (!$nodeCommand) { throw 'Install Windows Node.js 22 or newer and reopen the launcher.' }
    $node = $nodeCommand.Source
    $version = & $node --version
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^v(\d+)\.' -or [int]$Matches[1] -lt 22) { throw 'Install Windows Node.js 22 or newer for school login.' }
    $powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    $linuxPowerShell = (Invoke-Wsl $Wsl @('--distribution', $Distribution, '--exec', 'wslpath', '-u', $powershell) -Quiet) -join ''
    if ($script:WslExitCode -ne 0) { throw 'Could not map the Windows PowerShell path into WSL.' }
    $directory = Join-Path $Root '.codex/launcher/bin'
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $hostScript = Join-Path $Root '.codex/launcher/node-host.ps1'
    $edge = Find-Edge
    $hostText = "`$env:CAMPUS_EDGE = '" + $edge.Replace("'", "''") + "'`r`n& '" + $node.Replace("'", "''") + "' @args`r`nexit `$LASTEXITCODE`r`n"
    [IO.File]::WriteAllText($hostScript, $hostText, [Text.UTF8Encoding]::new($true))
    $prefix = "#!/usr/bin/env bash`nexec /init " + (Quote-Bash $linuxPowerShell.Trim())
    [IO.File]::WriteAllText((Join-Path $directory 'powershell.exe'), $prefix + ' "$@"' + "`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $directory 'node.exe'), $prefix + ' -NoLogo -NoProfile -NonInteractive -File ' + (Quote-Bash $hostScript) + ' "$@"' + "`n", [Text.UTF8Encoding]::new($false))
    Invoke-Wsl $Wsl @('--distribution', $Distribution, '--cd', $Root, '--exec', 'chmod', '+x', '.codex/launcher/bin/powershell.exe', '.codex/launcher/bin/node.exe') -Quiet
    if ($script:WslExitCode -ne 0) { throw 'Could not prepare Windows interoperability helpers.' }
}
