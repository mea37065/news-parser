param(
    [string]$ServiceName = "NewsParserBot",
    [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$PythonExe = "",
    [string]$NssmExe = "nssm",
    [string]$RunAsUser = "",
    [switch]$Start
)

$ErrorActionPreference = "Stop"

if (-not $PythonExe) {
    $PythonExe = Join-Path $ProjectDir "venv\Scripts\python.exe"
}

$BotScript = Join-Path $ProjectDir "bot.py"
$LogsDir = Join-Path $ProjectDir "logs"
$StdoutLog = Join-Path $LogsDir "news-parser-service.out.log"
$StderrLog = Join-Path $LogsDir "news-parser-service.err.log"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe. Create the venv first with: py -m venv venv"
}

if (-not (Test-Path $BotScript)) {
    throw "Bot entrypoint not found: $BotScript"
}

if (-not (Test-Path (Join-Path $ProjectDir ".env"))) {
    Write-Warning "No .env file found in $ProjectDir. The service must receive configuration from environment variables or Windows Credential Manager."
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

& $NssmExe install $ServiceName $PythonExe $BotScript
& $NssmExe set $ServiceName AppDirectory $ProjectDir
& $NssmExe set $ServiceName DisplayName "News Parser Bot"
& $NssmExe set $ServiceName Description "Parses RSS feeds, sends Telegram review messages, and publishes approved posts to LinkedIn."
& $NssmExe set $ServiceName Start SERVICE_AUTO_START
& $NssmExe set $ServiceName AppStdout $StdoutLog
& $NssmExe set $ServiceName AppStderr $StderrLog
& $NssmExe set $ServiceName AppRotateFiles 1
& $NssmExe set $ServiceName AppRotateOnline 1
& $NssmExe set $ServiceName AppRotateBytes 10485760

if ($RunAsUser) {
    Write-Host "Setting service account for $ServiceName. NSSM will ask for the account password."
    & $NssmExe set $ServiceName ObjectName $RunAsUser
}

if ($Start) {
    & $NssmExe start $ServiceName
}

Write-Host "Installed $ServiceName with NSSM."
Write-Host "Check status with: $NssmExe status $ServiceName"
