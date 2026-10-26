param([Parameter(Mandatory=$true, Position=0)][string]$Destination)
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot/scripts/python.ps1" -Bootstrap "$PSScriptRoot/harness" adopt $Destination --apply
exit $LASTEXITCODE
