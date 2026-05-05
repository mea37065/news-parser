param(
    [string]$ServiceName = "NewsParserBot",
    [string]$NssmExe = "nssm"
)

$ErrorActionPreference = "Stop"

$status = & $NssmExe status $ServiceName 2>$null
if ($LASTEXITCODE -eq 0 -and $status -notmatch "SERVICE_STOPPED") {
    & $NssmExe stop $ServiceName
}

& $NssmExe remove $ServiceName confirm

Write-Host "Removed $ServiceName."
