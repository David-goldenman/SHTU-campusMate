$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'scripts/launcher.ps1')

$lock = $null
$browserJob = $null
try {
    $options = Read-LaunchOptions $args
    if ($options.Help) {
        Write-Host 'Campus Framework launcher'
        Write-Host 'run.cmd [--distro NAME] [--port PORT] [--no-browser] [--check]'
        Write-Host 'Auto-select WSL, start the local server, then open Microsoft Edge.'
        Write-Host 'Keep this window open. Press Ctrl+C to stop the server.'
        Write-Host '--check validates launch dependencies without starting the server.'
        Write-Host '--version prints the application version.'
        exit 0
    }
    if ($options.Version) {
        $project = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'pyproject.toml') -Raw
        Write-Host ([regex]::Match($project, '(?m)^version = "([^"]+)"').Groups[1].Value)
        exit 0
    }
    $edge = if (!$options.NoBrowser -and !$options.Check) { Find-Edge } else { $null }
    $running = Get-CampusServer $PSScriptRoot
    if ($running -and !$options.Check) {
        if ($options.Port -and $options.Port -ne $running.port) {
            throw "This workspace is already running on port $($running.port). Stop it before changing ports."
        }
        $url = "http://127.0.0.1:$($running.port)"
        Write-Host "Already running: $url"
        if ($edge) { Start-Process -FilePath $edge -ArgumentList $url }
        exit 0
    }
    $directory = Join-Path $PSScriptRoot '.private/runtime/launcher'
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    if (!$options.Check) {
        try { $lock = [IO.File]::Open((Join-Path $directory 'launch.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch { throw 'This workspace is already starting. Wait for its startup window, then try again.' }
    }

    $wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (!$wslCommand) { throw 'WSL was not found. Install Windows Subsystem for Linux and an Ubuntu or Debian distribution.' }
    $wsl = $wslCommand.Source
    $installed = ConvertFrom-WslList (Invoke-Wsl $wsl @('--list', '--quiet') -Quiet)
    if ($script:WslExitCode -ne 0 -or !$installed) { throw 'No WSL distribution found. Install WSL and Ubuntu, then run this launcher again.' }
    $default = ((Invoke-Wsl $wsl @('--exec', 'printenv', 'WSL_DISTRO_NAME') -Quiet) -join '').Trim([char]0, [char]13, [char]10, [char]32)
    $candidates = Get-WslCandidates $installed $options.Distro $default
    $distribution = $null
    foreach ($candidate in $candidates) {
        Invoke-Wsl $wsl @('--distribution', $candidate, '--cd', $PSScriptRoot, '--exec', 'bash', '-c', 'command -v wslpath >/dev/null && test -x /init && test -f run.sh') -Quiet
        if ($script:WslExitCode -eq 0) { $distribution = $candidate; break }
    }
    if (!$distribution) { throw 'No usable WSL distribution found. Enable Windows interoperability and install bash, or pass --distro NAME.' }
    Write-Host "Using WSL: $distribution"
    Initialize-WindowsTools $PSScriptRoot $wsl $distribution
    if ($options.Check) {
        Invoke-Wsl $wsl @('--distribution', $distribution, '--cd', $PSScriptRoot, '--exec', 'bash', './run.sh', '--check')
        exit $script:WslExitCode
    }
    $launchId = [guid]::NewGuid().ToString('N')
    $serverArgs = @('--launch-id', $launchId)
    if ($options.Port) { $serverArgs += @('--port', [string]$options.Port) }
    if ($edge) {
        $browserJob = Start-Job -FilePath (Join-Path $PSScriptRoot 'scripts/open-workspace.ps1') -ArgumentList $PSScriptRoot, $edge, $launchId
    }
    Write-Host 'Preparing the environment. The first launch may download Python dependencies.'
    Write-Host 'Keep this window open; Ctrl+C stops the service.'
    if ($edge) { Write-Host 'Edge opens when the service is ready.' }
    Invoke-Wsl $wsl (@('--distribution', $distribution, '--cd', $PSScriptRoot, '--exec', 'bash', './run.sh') + $serverArgs)
    $code = $script:WslExitCode
    if ($code -ne 0) { Write-Host "Startup failed (exit $code). See the message above. If the port is occupied, use --port 17666." }
    exit $code
} catch {
    Write-Host "Startup error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($browserJob) {
        Stop-Job $browserJob -ErrorAction SilentlyContinue
        Receive-Job $browserJob -ErrorAction SilentlyContinue
        Remove-Job $browserJob -Force -ErrorAction SilentlyContinue
    }
    if ($lock) { $lock.Dispose() }
}
