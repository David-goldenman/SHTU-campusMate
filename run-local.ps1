$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = '1'
$previousScriptPolicy = $env:PSExecutionPolicyPreference
try {
    # Allow trusted repository helpers in children, then restore the caller's process setting.
    $env:PSExecutionPolicyPreference = 'Bypass'
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
        $runtimePython = Join-Path $PSScriptRoot '.private\runtime\windows\venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $runtimePython -PathType Leaf) { $pythonPath = $runtimePython }
        else {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($pythonCommand) { $pythonPath = $pythonCommand.Source }
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
finally {
    if ($null -eq $previousScriptPolicy) { Remove-Item Env:\PSExecutionPolicyPreference -ErrorAction SilentlyContinue }
    else { $env:PSExecutionPolicyPreference = $previousScriptPolicy }
}
