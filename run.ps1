$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = '1'
try {
    $pythonPath = $null
    $forwarded = [System.Collections.Generic.List[string]]::new()
    for ($index = 0; $index -lt $args.Count; $index++) {
        switch (([string]$args[$index]).ToLowerInvariant()) {
            { $_ -in '-pythonpath', '--python' } {
                $index++
                if ($index -ge $args.Count) { throw '请在 --python 后填写已有 python.exe 的完整路径。' }
                $pythonPath = $args[$index]
                break
            }
            '-port' { $forwarded.Add('--port'); break }
            '-nobrowser' { $forwarded.Add('--no-browser'); break }
            '-checkruntime' { $forwarded.Add('--check'); break }
            '-stop' { $forwarded.Add('--stop'); break }
            default { $forwarded.Add($args[$index]) }
        }
    }
    if (-not $pythonPath -and $env:CAMPUS_PYTHON) { $pythonPath = $env:CAMPUS_PYTHON }
    $configuration = Join-Path $PSScriptRoot 'python-path.txt'
    if (-not $pythonPath -and (Test-Path -LiteralPath $configuration)) {
        $pythonPath = (Get-Content -LiteralPath $configuration -Raw -Encoding UTF8).Trim()
    }
    if (-not $pythonPath) {
        $candidates = @(
            (Join-Path $PSScriptRoot '.codex\venv\Scripts\python.exe'),
            (Join-Path $env:USERPROFILE 'anaconda3\python.exe'),
            (Join-Path $env:USERPROFILE 'miniconda3\python.exe'),
            'D:\anaconda\python.exe',
            'C:\ProgramData\anaconda3\python.exe'
        )
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $pythonPath = $candidate; break }
        }
    }
    if (-not $pythonPath -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw '未找到已有 Python。请在 python-path.txt 写入现有 Python 3.12+ 的 python.exe 完整路径；启动器不会下载环境。'
    }
    $pythonPath = (Resolve-Path -LiteralPath $pythonPath).Path
    & $pythonPath -X utf8 -B (Join-Path $PSScriptRoot 'scripts\launch.py') @forwarded
    exit $LASTEXITCODE
}
catch {
    [Console]::Error.WriteLine('启动器无法完成操作：' + $_.Exception.Message)
    exit 1
}
