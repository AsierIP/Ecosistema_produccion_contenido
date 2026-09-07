Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($null -eq ("System.Security.Cryptography.ProtectedData" -as [type])) {
    Add-Type -AssemblyName System.Security -ErrorAction Stop
}

$script:SecretSchemaVersion = 1
$script:SecretKind = "lumen.gemini-api-key"
$script:ProtectionName = "dpapi-current-user"
$script:Entropy = [Text.Encoding]::UTF8.GetBytes("LUMEN|GeminiApiKey|v1")

function Assert-LumenWindowsDpapi {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw "El almacén de secretos de LUMEN requiere Windows DPAPI."
    }
}

function Get-LumenGeminiSecretPath {
    [CmdletBinding()]
    param()

    $localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        throw "No se pudo resolver LOCALAPPDATA para el usuario actual."
    }

    return [IO.Path]::GetFullPath(
        (Join-Path $localAppData "LUMEN\secrets\gemini-api-key.v1.dpapi.json")
    )
}

function Set-LumenPrivateAcl {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )

    Assert-LumenWindowsDpapi

    $item = Get-Item -LiteralPath $LiteralPath -Force
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if ($null -eq $identity -or $null -eq $identity.User) {
        throw "No se pudo identificar al usuario de Windows actual."
    }

    if ($item.PSIsContainer) {
        $acl = Get-Acl -LiteralPath $item.FullName
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $identity.User,
            [Security.AccessControl.FileSystemRights]::FullControl,
            ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit),
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
    }
    else {
        $acl = Get-Acl -LiteralPath $item.FullName
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $identity.User,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        )
    }

    $acl.SetAccessRuleProtection($true, $false)
    $existingRules = @(
        $acl.GetAccessRules(
            $true,
            $false,
            [Security.Principal.SecurityIdentifier]
        )
    )
    foreach ($existingRule in $existingRules) {
        [void]$acl.RemoveAccessRuleSpecific($existingRule)
    }
    [void]$acl.AddAccessRule($rule)
    if ($item.PSIsContainer) {
        [IO.Directory]::SetAccessControl($item.FullName, $acl)
    }
    else {
        [IO.File]::SetAccessControl($item.FullName, $acl)
    }
}

function Protect-LumenSecureString {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [Security.SecureString]$SecureString
    )

    Assert-LumenWindowsDpapi
    if ($SecureString.Length -lt 1) {
        throw "El secreto está vacío."
    }

    $pointer = [IntPtr]::Zero
    [byte[]]$clearBytes = $null
    [byte[]]$protectedBytes = $null
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
        $clearBytes = New-Object byte[] ($SecureString.Length * 2)
        [Runtime.InteropServices.Marshal]::Copy($pointer, $clearBytes, 0, $clearBytes.Length)
        $protectedBytes = [Security.Cryptography.ProtectedData]::Protect(
            $clearBytes,
            $script:Entropy,
            [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        return [Convert]::ToBase64String($protectedBytes)
    }
    finally {
        if ($null -ne $clearBytes) {
            [Array]::Clear($clearBytes, 0, $clearBytes.Length)
        }
        if ($null -ne $protectedBytes) {
            [Array]::Clear($protectedBytes, 0, $protectedBytes.Length)
        }
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Unprotect-LumenSecureString {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$CiphertextBase64
    )

    Assert-LumenWindowsDpapi
    [byte[]]$protectedBytes = $null
    [byte[]]$clearBytes = $null
    try {
        $protectedBytes = [Convert]::FromBase64String($CiphertextBase64)
        $clearBytes = [Security.Cryptography.ProtectedData]::Unprotect(
            $protectedBytes,
            $script:Entropy,
            [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        if ($clearBytes.Length -lt 2 -or ($clearBytes.Length % 2) -ne 0) {
            throw "El contenido DPAPI descifrado no tiene un formato válido."
        }

        $secureString = New-Object Security.SecureString
        for ($offset = 0; $offset -lt $clearBytes.Length; $offset += 2) {
            $secureString.AppendChar([BitConverter]::ToChar($clearBytes, $offset))
        }
        $secureString.MakeReadOnly()
        return $secureString
    }
    catch [Security.Cryptography.CryptographicException] {
        throw "No se pudo descifrar la clave de Gemini. Debe abrirla el mismo usuario de Windows que la guardó."
    }
    catch [FormatException] {
        throw "El almacén cifrado de Gemini está dañado."
    }
    finally {
        if ($null -ne $clearBytes) {
            [Array]::Clear($clearBytes, 0, $clearBytes.Length)
        }
        if ($null -ne $protectedBytes) {
            [Array]::Clear($protectedBytes, 0, $protectedBytes.Length)
        }
    }
}

function Test-LumenGeminiSecretExists {
    [CmdletBinding()]
    param(
        [string]$SecretPath = (Get-LumenGeminiSecretPath)
    )

    return Test-Path -LiteralPath $SecretPath -PathType Leaf
}

function Get-LumenGeminiApiKeySecureString {
    [CmdletBinding()]
    param(
        [string]$SecretPath = (Get-LumenGeminiSecretPath)
    )

    Assert-LumenWindowsDpapi
    $resolvedPath = [IO.Path]::GetFullPath($SecretPath)
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) {
        throw "No existe una clave de Gemini guardada para LUMEN. Ejecuta tools\set_lumen_gemini_api_key.ps1."
    }

    try {
        $record = Get-Content -LiteralPath $resolvedPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "El almacén cifrado de Gemini no contiene JSON válido."
    }

    if (
        [int]$record.schema_version -ne $script:SecretSchemaVersion -or
        [string]$record.kind -ne $script:SecretKind -or
        [string]$record.protection -ne $script:ProtectionName -or
        [string]::IsNullOrWhiteSpace([string]$record.ciphertext_base64)
    ) {
        throw "El almacén cifrado de Gemini tiene un esquema incompatible o incompleto."
    }

    return Unprotect-LumenSecureString -CiphertextBase64 ([string]$record.ciphertext_base64)
}

function Set-LumenGeminiApiKeySecureString {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [Security.SecureString]$ApiKey,

        [string]$SecretPath = (Get-LumenGeminiSecretPath),

        [Parameter(Mandatory = $true)]
        [DateTime]$ValidatedUtc
    )

    Assert-LumenWindowsDpapi
    if ($ApiKey.Length -lt 1) {
        throw "La clave de Gemini está vacía."
    }

    $resolvedPath = [IO.Path]::GetFullPath($SecretPath)
    $directory = Split-Path -Parent $resolvedPath
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    Set-LumenPrivateAcl -LiteralPath $directory

    $ciphertext = Protect-LumenSecureString -SecureString $ApiKey
    $record = [ordered]@{
        schema_version = $script:SecretSchemaVersion
        kind = $script:SecretKind
        protection = $script:ProtectionName
        created_utc = [DateTime]::UtcNow.ToString("o")
        validated_utc = $ValidatedUtc.ToUniversalTime().ToString("o")
        ciphertext_base64 = $ciphertext
    }

    $temporaryPath = Join-Path $directory (".gemini-api-key.{0}.tmp" -f [Guid]::NewGuid().ToString("N"))
    try {
        $json = $record | ConvertTo-Json -Depth 4
        [IO.File]::WriteAllText($temporaryPath, $json, (New-Object Text.UTF8Encoding($false)))
        Set-LumenPrivateAcl -LiteralPath $temporaryPath

        if (Test-Path -LiteralPath $resolvedPath -PathType Leaf) {
            [IO.File]::Replace($temporaryPath, $resolvedPath, $null, $true)
        }
        else {
            [IO.File]::Move($temporaryPath, $resolvedPath)
        }
        Set-LumenPrivateAcl -LiteralPath $resolvedPath
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
        $ciphertext = $null
        $json = $null
    }

    return $resolvedPath
}

function Invoke-LumenWithSecureStringPlainText {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [Security.SecureString]$SecureString,

        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    $pointer = [IntPtr]::Zero
    $plainText = $null
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
        $plainText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ([string]::IsNullOrWhiteSpace($plainText)) {
            throw "El secreto está vacío."
        }

        try {
            return & $ScriptBlock $plainText
        }
        catch {
            $safeMessage = [string]$_.Exception.Message
            $statusCode = $null
            try {
                if ($null -ne $_.Exception.Response) {
                    $statusCode = [int]$_.Exception.Response.StatusCode
                }
            }
            catch {
                $statusCode = $null
            }
            if (-not [string]::IsNullOrEmpty($plainText)) {
                $safeMessage = $safeMessage.Replace($plainText, "[REDACTED]")
            }
            if ($safeMessage.Length -gt 1400) {
                $safeMessage = $safeMessage.Substring(0, 1400)
            }
            $safeException = [InvalidOperationException]::new($safeMessage)
            if ($null -ne $statusCode) {
                $safeException.Data["HttpStatusCode"] = $statusCode
            }
            throw $safeException
        }
    }
    finally {
        $plainText = $null
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Test-LumenGeminiApiKeyOnline {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [Security.SecureString]$ApiKey,

        [ValidateRange(10, 120)]
        [int]$TimeoutSeconds = 30,

        [scriptblock]$RequestInvoker
    )

    $endpoint = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
    $invoker = $RequestInvoker

    $result = Invoke-LumenWithSecureStringPlainText -SecureString $ApiKey -ScriptBlock {
        param([string]$PlainApiKey)

        $headers = @{
            "x-goog-api-key" = $PlainApiKey
        }
        if ($null -ne $invoker) {
            return & $invoker $endpoint $headers $TimeoutSeconds
        }

        return Invoke-RestMethod `
            -Uri $endpoint `
            -Method Get `
            -Headers $headers `
            -TimeoutSec $TimeoutSeconds
    }

    if ($null -eq $result) {
        throw "Google no devolvió una respuesta válida al comprobar la clave."
    }
    return $true
}

Export-ModuleMember -Function @(
    "Get-LumenGeminiSecretPath",
    "Test-LumenGeminiSecretExists",
    "Get-LumenGeminiApiKeySecureString",
    "Set-LumenGeminiApiKeySecureString",
    "Invoke-LumenWithSecureStringPlainText",
    "Test-LumenGeminiApiKeyOnline"
)
