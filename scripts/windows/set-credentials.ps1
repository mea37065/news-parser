param(
    [string]$TargetPrefix = "NewsParser"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$source = @"
using System;
using System.Runtime.InteropServices;

public class WinCred
{
    public const UInt32 CRED_TYPE_GENERIC = 1;
    public const UInt32 CRED_PERSIST_LOCAL_MACHINE = 2;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Credential
    {
        public UInt32 Flags;
        public UInt32 Type;
        public string TargetName;
        public string Comment;
        public Int64 LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    [DllImport("advapi32.dll", EntryPoint = "CredWriteW", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool CredWrite(ref Credential userCredential, UInt32 flags);
}
"@

if (-not ("WinCred" -as [type])) {
    Add-Type -TypeDefinition $source
}

function Set-NewsParserCredential {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [SecureString]$Secret
    )

    $targetName = "$TargetPrefix/$Name"
    $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
    $blobPointer = [IntPtr]::Zero

    try {
        $plainText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
        if ([string]::IsNullOrWhiteSpace($plainText)) {
            Write-Host "Skipped $targetName"
            return
        }

        $bytes = [Text.Encoding]::Unicode.GetBytes($plainText)
        $blobPointer = [Runtime.InteropServices.Marshal]::AllocHGlobal($bytes.Length)
        [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $blobPointer, $bytes.Length)

        $credential = New-Object WinCred+Credential
        $credential.Type = [WinCred]::CRED_TYPE_GENERIC
        $credential.TargetName = $targetName
        $credential.CredentialBlobSize = $bytes.Length
        $credential.CredentialBlob = $blobPointer
        $credential.Persist = [WinCred]::CRED_PERSIST_LOCAL_MACHINE
        $credential.UserName = "NewsParser"

        if (-not [WinCred]::CredWrite([ref]$credential, 0)) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "CredWrite failed for $targetName with Windows error $errorCode"
        }

        Write-Host "Stored $targetName"
    }
    finally {
        if ($blobPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::FreeHGlobal($blobPointer)
        }
        if ($secretPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
        }
    }
}

$credentialNames = @(
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "LINKEDIN_ACCESS_TOKEN",
    "GROQ_API_KEY"
)

Write-Host "Storing credentials under prefix '$TargetPrefix'."
Write-Host "Run this as the same Windows account that will run the service."
Write-Host "Press Enter on an empty prompt to skip a value."
Write-Host ""

foreach ($name in $credentialNames) {
    $secret = Read-Host -AsSecureString -Prompt $name
    Set-NewsParserCredential -Name $name -Secret $secret
}
