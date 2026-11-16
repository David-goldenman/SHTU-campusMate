$ErrorActionPreference = 'Stop'
try {
    $state = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'current.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.product -ne 'campusMate' -or $state.current -notmatch '^v[0-9A-Za-z.-]+-[a-f0-9]{12}$') { throw 'Invalid installed version record.' }
    $directory = Join-Path (Join-Path $PSScriptRoot 'versions') $state.current
    Start-Process -FilePath (Join-Path $directory 'campusMate.exe') -WorkingDirectory $directory -WindowStyle Hidden
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'campusMate') | Out-Null
    exit 1
}
