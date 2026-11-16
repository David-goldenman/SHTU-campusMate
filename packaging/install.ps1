param(
    [ValidateSet('Install','Rollback','Uninstall')][string]$Mode = 'Install',
    [string]$PayloadDirectory,
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'Programs\campusMate'),
    [switch]$NoShortcuts,
    [switch]$SkipLaunchCheck
)
$ErrorActionPreference = 'Stop'
function Assert-PlainPath([string]$Path) {
    # GetFullPath normalizes spelling only; a parent junction can still redirect it.
    $candidate = [IO.Path]::GetFullPath($Path)
    while ($candidate) {
        if (Test-Path -LiteralPath $candidate) {
            if ((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Program and data paths cannot contain links in any parent directory.' }
        }
        $parent = [IO.Directory]::GetParent($candidate)
        $candidate = if ($parent) { $parent.FullName } else { $null }
    }
}
$installRoot = [IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\')
if ($installRoot -eq [IO.Path]::GetPathRoot($installRoot).TrimEnd('\')) { throw 'An install folder is required.' }
Assert-PlainPath $installRoot
$dataRoots = @([IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'campusMate\data')).TrimEnd('\'))
if ($env:CAMPUS_DATA_DIR) { $dataRoots += [IO.Path]::GetFullPath($env:CAMPUS_DATA_DIR).TrimEnd('\') }
foreach ($dataRoot in $dataRoots) {
    Assert-PlainPath $dataRoot
    if ($installRoot.Equals($dataRoot, [StringComparison]::OrdinalIgnoreCase) -or $dataRoot.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or $installRoot.StartsWith($dataRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Program and user data directories must not overlap.' }
}
$pointer = Join-Path $installRoot 'current.json'
$ownerFile = Join-Path $installRoot 'campusmate-install.json'
$versions = Join-Path $installRoot 'versions'
$registry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\campusMate'
$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'campusMate'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$utf8 = New-Object Text.UTF8Encoding($false)
$pending = $null
$operationLock = $null

function Assert-Contained([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes this installation.' }
    Assert-PlainPath $full
    return $full
}
function Version-Path([string]$Name) {
    if ($Name -notmatch '^v[0-9A-Za-z.-]+-[a-f0-9]{12}$') { throw 'Invalid installed version.' }
    return Assert-Contained (Join-Path $versions $Name)
}
function Read-State {
    if (-not (Test-Path -LiteralPath $pointer)) { return $null }
    $value = Get-Content -LiteralPath $pointer -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($value.product -ne 'campusMate' -or $value.schema -ne 1) { throw 'This folder belongs to another application.' }
    $null = Version-Path $value.current
    return $value
}
function Save-State($Value) {
    $next = Assert-Contained (Join-Path $installRoot ('current-' + [Guid]::NewGuid().ToString('N') + '.next'))
    [IO.File]::WriteAllText($next, ($Value | ConvertTo-Json), $utf8)
    if (Test-Path -LiteralPath $pointer) { [IO.File]::Replace($next, $pointer, (Join-Path $installRoot 'previous-pointer.json')) }
    else { [IO.File]::Move($next, $pointer) }
}
function Check-Payload([string]$Directory) {
    foreach ($relative in @('campusMate.exe','resources\app.asar','resources\campus\runtime\python\python.exe','resources\campus\runtime\node\node.exe','resources\campus\scripts\desktop_service.py','resources\campus\runtime\harness-home\campus-template.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Directory $relative) -PathType Leaf)) { throw ('Incomplete application: ' + $relative) }
    }
    $manifest = Get-Content -LiteralPath (Join-Path $Directory 'resources\campus\release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.product -ne 'campusMate' -or $manifest.version -notmatch '^\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$') { throw 'Invalid release manifest.' }
    return $manifest
}
function Check-Launch([string]$Directory, [string]$Version) {
    if ($SkipLaunchCheck) { return }
    $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    $testRoot = Join-Path $tempBase ('campusMate-verify-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    try {
        $output = Join-Path $testRoot 'result.json'
        $start = New-Object Diagnostics.ProcessStartInfo
        $start.FileName = Join-Path $Directory 'campusMate.exe'
        $start.Arguments = '--port=0 "--smoke-test=' + $output + '"'
        $start.WorkingDirectory = $Directory
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
        $start.EnvironmentVariables['CAMPUS_DATA_DIR'] = Join-Path $testRoot 'data'
        $start.EnvironmentVariables.Remove('ELECTRON_RUN_AS_NODE')
        $process = [Diagnostics.Process]::Start($start)
        if (-not $process.WaitForExit(90000)) { $process.Kill(); $process.WaitForExit(); throw 'Candidate startup timed out; the previous version was kept.' }
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $output)) {
            $detail = if (Test-Path -LiteralPath $output) { Get-Content -LiteralPath $output -Raw -Encoding UTF8 } else { 'No startup result was returned.' }
            [IO.File]::WriteAllText((Join-Path $installRoot 'last-validation.txt'), ('Exit ' + $process.ExitCode + ': ' + $detail), $utf8)
            $logs = Join-Path $testRoot 'data\runtime\logs'
            if (Test-Path -LiteralPath $logs) {
                $diagnostic = (Get-ChildItem -LiteralPath $logs -Filter '*.log' | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 }) -join "`r`n"
                [IO.File]::WriteAllText((Join-Path $installRoot 'last-validation.log'), $diagnostic, $utf8)
            }
            throw ('Candidate startup failed (exit ' + $process.ExitCode + '): ' + $detail + ' The previous version was kept.')
        }
        $result = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $result.ready -or $result.version -ne $Version) { throw 'Candidate validation failed; the previous version was kept.' }
    } finally {
        $checked = [IO.Path]::GetFullPath($testRoot)
        if (-not $checked.StartsWith($tempBase + '\campusMate-verify-', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid validation cleanup path.' }
        if (Test-Path -LiteralPath $checked) { Remove-Item -LiteralPath $checked -Recurse -Force }
    }
}
function Create-Shortcut([string]$Name,[string]$Arguments,[string]$Icon) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Name)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $installRoot
    $shortcut.WindowStyle = 7
    $shortcut.IconLocation = $Icon
    $shortcut.Save()
}
try {
    if ($Mode -ne 'Install' -and -not (Test-Path -LiteralPath $pointer)) { throw 'No campusMate installation exists here.' }
    if (Test-Path -LiteralPath $installRoot) {
        if (Test-Path -LiteralPath $ownerFile) {
            $owner = Get-Content -LiteralPath $ownerFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($owner.product -ne 'campusMate' -or $owner.schema -ne 1) { throw 'Installation ownership cannot be verified.' }
        } elseif (Get-ChildItem -LiteralPath $installRoot -Force | Select-Object -First 1) { throw 'Choose an empty folder; existing unrelated files will not be changed.' }
    }
    New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $ownerFile)) { [IO.File]::WriteAllText($ownerFile, '{"product":"campusMate","schema":1}', $utf8) }
    $operationLock = [IO.File]::Open((Join-Path $installRoot 'install.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $state = Read-State
    $active = Get-Process campusMate -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($installRoot + '\', [StringComparison]::OrdinalIgnoreCase) }
    if ($active) { throw 'Close campusMate before changing the installation.' }
    if ($Mode -eq 'Rollback') {
        if (-not $state.previous) { throw 'No previous version is available.' }
        $previous = Version-Path $state.previous
        $manifest = Check-Payload $previous
        Check-Launch $previous $manifest.version
        Save-State @{schema=1;product='campusMate';current=$state.previous;previous=$state.current;version=$manifest.version}
        Write-Output 'Previous version restored. User data was preserved.'
    } elseif ($Mode -eq 'Install') {
        $source = (Resolve-Path -LiteralPath $PayloadDirectory).Path
        $manifest = Check-Payload $source
        if (Get-ChildItem -LiteralPath $source -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1) { throw 'Installation payload cannot contain links.' }
        New-Item -ItemType Directory -Path $versions -Force | Out-Null
        $name = 'v' + $manifest.version + '-' + [Guid]::NewGuid().ToString('N').Substring(0,12)
        $pending = Assert-Contained (Join-Path $versions ('.pending-' + [Guid]::NewGuid().ToString('N')))
        $destination = Version-Path $name
        $longestNative = (Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object { $_.Extension -in '.pyd','.dll' } | ForEach-Object { $_.FullName.Length - $source.Length } | Measure-Object -Maximum).Maximum
        if ($longestNative -and ([Math]::Max($pending.Length,$destination.Length) + $longestNative -ge 248)) { throw 'This install path is too long for Windows native libraries. Choose a shorter directory, preferably the default location.' }
        New-Item -ItemType Directory -Path $pending | Out-Null
        Get-ChildItem -LiteralPath $source -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $pending -Recurse -Force }
        $null = Check-Payload $pending
        Check-Launch $pending $manifest.version
        $checkedPending = Assert-Contained $pending
        Move-Item -LiteralPath $checkedPending -Destination $destination
        $pending = $null
        foreach ($pair in @(@('launch-desktop.ps1','launch.ps1'),@('install.ps1','install.ps1'))) {
            $target = Assert-Contained (Join-Path $installRoot $pair[1])
            # Keep schema 1 launch compatibility, but ship current maintenance safety checks.
            $entrySource = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $pair[0]))
            if (($pair[1] -eq 'install.ps1' -or -not (Test-Path -LiteralPath $target)) -and -not $entrySource.Equals($target, [StringComparison]::OrdinalIgnoreCase)) {
                Copy-Item -LiteralPath $entrySource -Destination $target -Force
            }
        }
        if (-not $NoShortcuts) {
            New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
            $arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $installRoot 'launch.ps1') + '"'
            $icon = Join-Path $destination 'campusMate.exe'
            Create-Shortcut (Join-Path $startMenu 'campusMate.lnk') $arguments $icon
            Create-Shortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'campusMate.lnk') $arguments $icon
            $maintenance = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $installRoot 'install.ps1') + '" -InstallDirectory "' + $installRoot + '" -Mode '
            Create-Shortcut (Join-Path $startMenu 'Restore previous version.lnk') ($maintenance + 'Rollback') $icon
            New-Item -Path $registry -Force | Out-Null
            New-ItemProperty -Path $registry -Name DisplayName -Value 'campusMate' -Force | Out-Null
            New-ItemProperty -Path $registry -Name DisplayVersion -Value $manifest.version -Force | Out-Null
            New-ItemProperty -Path $registry -Name UninstallString -Value ('"' + $powershell + '" ' + $maintenance + 'Uninstall') -Force | Out-Null
        }
        Save-State @{schema=1;product='campusMate';current=$name;previous=$(if($state){$state.current}else{$null});version=$manifest.version}
        Write-Output ('Installed campusMate ' + $manifest.version + '. User data was preserved.')
    } else {
        # Only the program tree is removed. %LOCALAPPDATA%\campusMate\data is separate.
        $null = Read-State
        $operationLock.Dispose();$operationLock=$null
        if (-not $NoShortcuts) {
            if (Test-Path -LiteralPath $startMenu) { Remove-Item -LiteralPath $startMenu -Recurse -Force }
            $shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'campusMate.lnk'
            if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force }
            if (Test-Path $registry) { Remove-Item -Path $registry -Recurse -Force }
        }
        Assert-PlainPath $installRoot
        # The program path and its ancestry are plain, and ownership was checked above.
        Remove-Item -LiteralPath $installRoot -Recurse -Force
        Write-Output 'campusMate program removed. User data was preserved.'
    }
} catch {
    if ((Test-Path -LiteralPath $ownerFile) -and (Test-Path -LiteralPath $installRoot)) { [IO.File]::WriteAllText((Join-Path $installRoot 'install-error.txt'), $_.Exception.Message, $utf8) }
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    if ($operationLock) { $operationLock.Dispose() }
    if ($pending -and (Test-Path -LiteralPath $pending)) {
        $checked = Assert-Contained $pending
        Remove-Item -LiteralPath $checked -Recurse -Force
    }
}
