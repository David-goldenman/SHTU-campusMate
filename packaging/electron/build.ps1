param([string]$Uv='uv',[switch]$Unpacked)
$ErrorActionPreference='Stop'
$Project=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$BuildRoot=Join-Path $Project '.codex/desktop'
$Stage=Join-Path $BuildRoot 'stage'
$Tools=Join-Path $BuildRoot 'tools'
New-Item -ItemType Directory -Path "$BuildRoot/tmp",$Tools,"$Stage/runtime" -Force | Out-Null
$env:TEMP="$BuildRoot/tmp"
$env:TMP=$env:TEMP
$env:UV_CACHE_DIR="$BuildRoot/cache/uv"
$env:npm_config_cache="$BuildRoot/cache/npm"
$env:ELECTRON_CACHE="$BuildRoot/cache/electron"
$env:ELECTRON_BUILDER_CACHE="$BuildRoot/cache/builder"
$env:npm_config_update_notifier='false'
$env:CSC_IDENTITY_AUTO_DISCOVERY='false'
$proxy=git -C $Project config --get http.proxy
if($proxy){
  $env:HTTP_PROXY=$proxy
  $env:HTTPS_PROXY=$proxy
  $env:npm_config_proxy=$proxy
  $env:npm_config_https_proxy=$proxy
  $env:GLOBAL_AGENT_HTTP_PROXY=$proxy
  $env:ELECTRON_GET_USE_PROXY='1'
}
function Remove-GeneratedDirectory([string]$Target){
  $resolved=[IO.Path]::GetFullPath($Target)
  $boundary=[IO.Path]::GetFullPath($BuildRoot).TrimEnd('\')+'\'
  if(!$resolved.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase)){throw 'Build cleanup target is outside .codex/desktop'}
  if(Test-Path -LiteralPath $resolved){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
function Fetch-File([string]$Url,[string]$Target){
  $options=@{Uri=$Url;OutFile=$Target;UseBasicParsing=$true;TimeoutSec=600}
  if($proxy){$options.Proxy=$proxy}
  Invoke-WebRequest @options
}
Copy-Item -LiteralPath "$PSScriptRoot/package.json","$PSScriptRoot/package-lock.json" -Destination $Tools -Force
Push-Location $Project
try{
  $toolsHash=(Get-FileHash -LiteralPath "$PSScriptRoot/package-lock.json" -Algorithm SHA256).Hash
  $toolsReady=Join-Path $BuildRoot 'tools-ready'
  if(!(Test-Path -LiteralPath $toolsReady) -or (Get-Content -LiteralPath $toolsReady -Raw).Trim() -ne $toolsHash){
    npm ci --prefix $Tools --no-audit --no-fund --registry=https://registry.npmjs.org
    if($LASTEXITCODE -ne 0){throw 'Desktop dependency setup failed'}
    $toolsHash | Set-Content -LiteralPath $toolsReady -Encoding ascii
  }
  if(!(Test-Path -LiteralPath "$Tools/node_modules/electron/dist/electron.exe")){
    node "$Tools/node_modules/electron/install.js"
    if($LASTEXITCODE -ne 0){throw 'Pinned Electron runtime download failed'}
  }
  $PythonVersion='3.12.15'
  $PythonRoot=Join-Path $Stage 'runtime/python'
  $Python=Join-Path $PythonRoot 'python.exe'
  $fingerprint=(Get-FileHash -LiteralPath "$Project/uv.lock" -Algorithm SHA256).Hash+"-$PythonVersion"
  $ready=Join-Path $BuildRoot 'python-ready'
  if(!(Test-Path -LiteralPath $ready) -or (Get-Content -LiteralPath $ready -Raw).Trim() -ne $fingerprint){
    & $Uv python install $PythonVersion --install-dir "$BuildRoot/python-download"
    if($LASTEXITCODE -ne 0){throw 'Bundled Python download failed'}
    $managed=Get-ChildItem -LiteralPath "$BuildRoot/python-download" -Directory | Where-Object {$_.Name.StartsWith("cpython-$PythonVersion-windows-x86_64-")}
    if(@($managed).Count -ne 1){throw 'Pinned Windows x64 Python was not found'}
    Remove-GeneratedDirectory $PythonRoot
    Copy-Item -LiteralPath $managed.FullName -Destination $PythonRoot -Recurse
    & $Uv export --locked --no-dev --no-hashes --no-emit-project --format requirements-txt --output-file "$BuildRoot/requirements.txt"
    if($LASTEXITCODE -ne 0){throw 'Locked dependency export failed'}
    & $Uv pip install --python $Python --target "$PythonRoot/Lib/site-packages" --link-mode copy --no-deps --requirements "$BuildRoot/requirements.txt"
    if($LASTEXITCODE -ne 0){throw 'Bundled Python dependencies failed'}
    $fingerprint | Set-Content -LiteralPath $ready -Encoding ascii
  }
  $NodeVersion='22.23.3'
  $NodeRoot=Join-Path $Stage 'runtime/node'
  if(!(Test-Path -LiteralPath "$NodeRoot/node.exe")){
    $archive="node-v$NodeVersion-win-x64.zip"
    Fetch-File "https://nodejs.org/dist/v$NodeVersion/$archive" "$BuildRoot/$archive"
    Fetch-File "https://nodejs.org/dist/v$NodeVersion/SHASUMS256.txt" "$BuildRoot/SHASUMS256.txt"
    $expected=((Get-Content -LiteralPath "$BuildRoot/SHASUMS256.txt" | Where-Object {$_.EndsWith(" $archive")}) -split '\s+')[0]
    if($expected -notmatch '^[0-9a-f]{64}$' -or (Get-FileHash -LiteralPath "$BuildRoot/$archive" -Algorithm SHA256).Hash -ine $expected){throw 'Node archive checksum verification failed'}
    Expand-Archive -LiteralPath "$BuildRoot/$archive" -DestinationPath "$BuildRoot/node-download" -Force
    Copy-Item -LiteralPath "$BuildRoot/node-download/node-v$NodeVersion-win-x64" -Destination $NodeRoot -Recurse
  }
  Remove-GeneratedDirectory "$Stage/runtime/pnpm"
  Copy-Item -LiteralPath "$Tools/node_modules/pnpm" -Destination "$Stage/runtime/pnpm" -Recurse
  @('@echo off','"%~dp0node.exe" "%~dp0..\pnpm\bin\pnpm.cjs" %*') | Set-Content -LiteralPath "$NodeRoot/pnpm.cmd" -Encoding ascii
  Remove-GeneratedDirectory "$Stage/backend"
  New-Item -ItemType Directory -Path "$Stage/backend" -Force | Out-Null
  $files=@(git -C $Project -c core.quotepath=false ls-files backend modules web scripts pyproject.toml uv.lock .python-version)
  if($LASTEXITCODE -ne 0){throw 'Tracked source enumeration failed'}
  $files+=@('packaging/electron/server.py')
  foreach($relative in $files){
    if($relative -match '(^|/)checks/|\.packaging-bak$'){continue}
    $destination=Join-Path "$Stage/backend" $relative
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $Project $relative) -Destination $destination -Force
  }
  $package=Get-Content -LiteralPath "$PSScriptRoot/package.json" -Raw | ConvertFrom-Json
  $commit=git -C $Project rev-parse HEAD
  @{application='CampusMate';version=$package.version;source_commit=$commit;platform='win32-x64';python=$PythonVersion;node=$NodeVersion;electron=$package.devDependencies.electron} |
    ConvertTo-Json | Set-Content -LiteralPath "$Stage/release.json" -Encoding utf8
  & $Python -s -B -c "from PIL import Image; Image.open(r'$Project/web/brand/campusmate-app-icon.png').convert('RGBA').save(r'$BuildRoot/icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
  if($LASTEXITCODE -ne 0){throw 'Application icon conversion failed'}
  $builder=@("$Tools/node_modules/electron-builder/out/cli/cli.js",'--projectDir',$PSScriptRoot,'--config',"$PSScriptRoot/builder.cjs",'--win','--x64','--publish','never')
  if($Unpacked){$builder+='--dir'}
  node @builder
  if($LASTEXITCODE -ne 0){throw 'Electron package build failed'}
  Get-ChildItem -LiteralPath "$BuildRoot/dist" -File | Select-Object Name,Length
}finally{Pop-Location}

