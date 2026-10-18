$ErrorActionPreference='Stop'
$project=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$video=Join-Path $project 'video'
$deps=Join-Path $project '.codex/video'
$env:TEMP=Join-Path $deps 'tmp'
$env:TMP=$env:TEMP
$env:npm_config_cache=Join-Path $project '.codex/cache/npm'
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $video 'package.json') -Destination $deps
if(Test-Path (Join-Path $video 'package-lock.json')){Copy-Item -LiteralPath (Join-Path $video 'package-lock.json') -Destination $deps}
npm.cmd install --prefix $deps --no-audit --no-fund
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
Copy-Item -LiteralPath (Join-Path $deps 'package-lock.json') -Destination $video
$link=Join-Path $video 'node_modules'
if(!(Test-Path $link)){New-Item -ItemType Junction -Path $link -Target (Join-Path $deps 'node_modules') | Out-Null}
