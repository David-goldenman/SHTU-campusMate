$ErrorActionPreference = 'Stop'
& wsl.exe -d Ubuntu-26.04 --cd $PSScriptRoot -- bash -l ./run.sh @args
exit $LASTEXITCODE
