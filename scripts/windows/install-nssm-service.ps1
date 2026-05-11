param(
    [string]$ServiceName = "NewsParserBot",
    [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$PythonExe = "",
    [string]$NssmExe = "nssm",
    [string]$RunAsUser = "",
    [securestring]$RunAsPassword,
    [switch]$Start
)

$ErrorActionPreference = "Stop"

function Invoke-Nssm {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $NssmExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "nssm $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

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

Invoke-Nssm -Arguments @("install", $ServiceName, $PythonExe, $BotScript)
Invoke-Nssm -Arguments @("set", $ServiceName, "AppDirectory", $ProjectDir)
Invoke-Nssm -Arguments @("set", $ServiceName, "DisplayName", "News Parser Bot")
Invoke-Nssm -Arguments @(
    "set",
    $ServiceName,
    "Description",
    "Parses RSS feeds, sends Telegram review messages, and publishes approved posts to LinkedIn."
)
Invoke-Nssm -Arguments @("set", $ServiceName, "Start", "SERVICE_AUTO_START")
Invoke-Nssm -Arguments @("set", $ServiceName, "AppStdout", $StdoutLog)
Invoke-Nssm -Arguments @("set", $ServiceName, "AppStderr", $StderrLog)
Invoke-Nssm -Arguments @("set", $ServiceName, "AppRotateFiles", "1")
Invoke-Nssm -Arguments @("set", $ServiceName, "AppRotateOnline", "1")
Invoke-Nssm -Arguments @("set", $ServiceName, "AppRotateBytes", "10485760")

if ($RunAsUser) {
    if (-not $RunAsPassword) {
        $RunAsPassword = Read-Host -AsSecureString -Prompt "Password for $RunAsUser"
    }

    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $RunAsPassword
    )
    try {
        $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
            $passwordPointer
        )
        Invoke-Nssm -Arguments @(
            "set",
            $ServiceName,
            "ObjectName",
            $RunAsUser,
            $plainPassword
        )
    }
    finally {
        if ($passwordPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
        }
    }
}

if ($Start) {
    Invoke-Nssm -Arguments @("start", $ServiceName)
}

Write-Host "Installed $ServiceName with NSSM."
Write-Host "Check status with: $NssmExe status $ServiceName"
