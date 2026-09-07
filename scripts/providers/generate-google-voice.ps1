[CmdletBinding()]
param(
    [string]$ConfigPath = "content\audio\voice_audition_es_es.json",
    [string]$OutputRoot = "artifacts\voice-auditions",
    [ValidateRange(1, 1)]
    [int]$MaxAttempts = 1,
    [ValidateRange(30, 600)]
    [int]$TimeoutSeconds = 180,
    [switch]$ValidateOnly,
    [switch]$OpenPreview,
    [switch]$UseEnvironmentApiKeyForCI
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$previewTemplatePath = Join-Path $PSScriptRoot "voice_audition_preview.html"
$secretModulePath = Join-Path $PSScriptRoot "Lumen.SecretStore.psm1"
Import-Module -Name $secretModulePath -Force -ErrorAction Stop

function Resolve-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([IO.Path]::IsPathRooted($Path)) {
        return [IO.Path]::GetFullPath($Path)
    }

    return [IO.Path]::GetFullPath((Join-Path $projectRoot $Path))
}

function Get-Utf8Sha256 {
    param([Parameter(Mandatory = $true)][string]$Text)

    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-PropertyValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($Object -is [Collections.IDictionary]) {
        if ($Object.Contains($Name)) {
            return $Object[$Name]
        }
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -ne $property) {
        return $property.Value
    }

    return $null
}

function Find-FirstAudioBlock {
    param($Node)

    if ($null -eq $Node -or $Node -is [string] -or $Node -is [ValueType]) {
        return $null
    }

    $data = Get-PropertyValue -Object $Node -Name "data"
    $type = Get-PropertyValue -Object $Node -Name "type"
    $mimeType = Get-PropertyValue -Object $Node -Name "mime_type"
    if ([string]::IsNullOrWhiteSpace([string]$mimeType)) {
        $mimeType = Get-PropertyValue -Object $Node -Name "mimeType"
    }

    $looksLikeAudio = ([string]$type -eq "audio") -or ([string]$mimeType).StartsWith("audio/")
    if ($looksLikeAudio -and -not [string]::IsNullOrWhiteSpace([string]$data)) {
        return $Node
    }

    if ($Node -is [Collections.IDictionary]) {
        foreach ($value in $Node.Values) {
            $found = Find-FirstAudioBlock -Node $value
            if ($null -ne $found) {
                return $found
            }
        }
        return $null
    }

    if ($Node -is [Collections.IEnumerable]) {
        foreach ($item in $Node) {
            $found = Find-FirstAudioBlock -Node $item
            if ($null -ne $found) {
                return $found
            }
        }
        return $null
    }

    foreach ($property in $Node.PSObject.Properties) {
        $found = Find-FirstAudioBlock -Node $property.Value
        if ($null -ne $found) {
            return $found
        }
    }

    return $null
}

function Test-RiffWave {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    if ($Bytes.Length -lt 12) {
        return $false
    }

    $riff = [Text.Encoding]::ASCII.GetString($Bytes, 0, 4)
    $wave = [Text.Encoding]::ASCII.GetString($Bytes, 8, 4)
    return $riff -eq "RIFF" -and $wave -eq "WAVE"
}

function New-PcmWave {
    param(
        [Parameter(Mandatory = $true)][byte[]]$Pcm,
        [Parameter(Mandatory = $true)][int]$SampleRate,
        [Parameter(Mandatory = $true)][int]$Channels,
        [Parameter(Mandatory = $true)][int]$BitsPerSample
    )

    if ($Pcm.Length -eq 0 -or ($Pcm.Length % 2) -ne 0) {
        throw "The PCM payload is empty or has an odd byte count."
    }
    if ($BitsPerSample -ne 16) {
        throw "Only 16-bit PCM is supported by this audition pipeline."
    }

    $blockAlign = $Channels * ($BitsPerSample / 8)
    $byteRate = $SampleRate * $blockAlign
    $stream = New-Object IO.MemoryStream
    $writer = New-Object IO.BinaryWriter($stream, [Text.Encoding]::ASCII, $true)
    try {
        $writer.Write([Text.Encoding]::ASCII.GetBytes("RIFF"))
        $writer.Write([int](36 + $Pcm.Length))
        $writer.Write([Text.Encoding]::ASCII.GetBytes("WAVE"))
        $writer.Write([Text.Encoding]::ASCII.GetBytes("fmt "))
        $writer.Write([int]16)
        $writer.Write([int16]1)
        $writer.Write([int16]$Channels)
        $writer.Write([int]$SampleRate)
        $writer.Write([int]$byteRate)
        $writer.Write([int16]$blockAlign)
        $writer.Write([int16]$BitsPerSample)
        $writer.Write([Text.Encoding]::ASCII.GetBytes("data"))
        $writer.Write([int]$Pcm.Length)
        $writer.Write($Pcm)
        $writer.Flush()
        return ,([byte[]]$stream.ToArray())
    }
    finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

function Get-WaveInfo {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    if (-not (Test-RiffWave -Bytes $Bytes)) {
        throw "The output is not a RIFF/WAVE file."
    }

    $formatTag = $null
    $channels = $null
    $sampleRate = $null
    $bitsPerSample = $null
    $dataOffset = $null
    $dataSize = $null
    $offset = 12

    while (($offset + 8) -le $Bytes.Length) {
        $chunkId = [Text.Encoding]::ASCII.GetString($Bytes, $offset, 4)
        $chunkSize = [BitConverter]::ToUInt32($Bytes, $offset + 4)
        $chunkDataOffset = $offset + 8
        if (($chunkDataOffset + $chunkSize) -gt $Bytes.Length) {
            throw "A WAV chunk extends beyond the file boundary."
        }

        if ($chunkId -eq "fmt " -and $chunkSize -ge 16) {
            $formatTag = [BitConverter]::ToUInt16($Bytes, $chunkDataOffset)
            $channels = [BitConverter]::ToUInt16($Bytes, $chunkDataOffset + 2)
            $sampleRate = [BitConverter]::ToUInt32($Bytes, $chunkDataOffset + 4)
            $bitsPerSample = [BitConverter]::ToUInt16($Bytes, $chunkDataOffset + 14)
        }
        elseif ($chunkId -eq "data") {
            $dataOffset = $chunkDataOffset
            $dataSize = [int]$chunkSize
        }

        $offset = $chunkDataOffset + [int]$chunkSize
        if (($chunkSize % 2) -ne 0) {
            $offset++
        }
    }

    if ($null -eq $formatTag -or $null -eq $dataOffset -or $null -eq $dataSize) {
        throw "The WAV file is missing its fmt or data chunk."
    }
    if ($formatTag -ne 1 -or $channels -ne 1 -or $sampleRate -ne 24000 -or $bitsPerSample -ne 16) {
        throw "Unexpected WAV format: tag=$formatTag channels=$channels rate=$sampleRate bits=$bitsPerSample."
    }

    $peak = 0
    $sumSquares = [double]0
    $sampleCount = 0
    $dataEnd = $dataOffset + $dataSize
    for ($index = $dataOffset; ($index + 1) -lt $dataEnd; $index += 2) {
        $sample = [int][BitConverter]::ToInt16($Bytes, $index)
        $absolute = [Math]::Abs($sample)
        if ($absolute -gt $peak) {
            $peak = $absolute
        }
        $sumSquares += [double]$sample * [double]$sample
        $sampleCount++
    }

    if ($sampleCount -eq 0 -or $peak -eq 0) {
        throw "The WAV file contains no audible PCM samples."
    }

    $rms = [Math]::Sqrt($sumSquares / $sampleCount)
    $duration = $dataSize / [double]($sampleRate * $channels * ($bitsPerSample / 8))

    return [pscustomobject]@{
        FormatTag = $formatTag
        Channels = $channels
        SampleRate = $sampleRate
        BitsPerSample = $bitsPerSample
        DataOffset = $dataOffset
        DataSize = $dataSize
        DurationSeconds = [Math]::Round($duration, 6)
        Peak = $peak
        Rms = [Math]::Round($rms, 3)
    }
}

function Convert-AudioBlockToWave {
    param([Parameter(Mandatory = $true)]$AudioBlock)

    $encoded = [string](Get-PropertyValue -Object $AudioBlock -Name "data")
    if ($encoded.StartsWith("data:")) {
        $commaIndex = $encoded.IndexOf(",")
        if ($commaIndex -lt 0) {
            throw "Invalid audio data URI."
        }
        $encoded = $encoded.Substring($commaIndex + 1)
    }

    [byte[]]$payload = [Convert]::FromBase64String($encoded)
    if (Test-RiffWave -Bytes $payload) {
        return ,$payload
    }

    $mimeType = [string](Get-PropertyValue -Object $AudioBlock -Name "mime_type")
    if ([string]::IsNullOrWhiteSpace($mimeType)) {
        $mimeType = [string](Get-PropertyValue -Object $AudioBlock -Name "mimeType")
    }
    if ([string]::IsNullOrWhiteSpace($mimeType)) {
        $mimeType = "audio/l16"
    }
    $mimeParts = @($mimeType -split ';' | ForEach-Object { $_.Trim() })
    $baseMimeType = $mimeParts[0].ToLowerInvariant()
    if ($baseMimeType -notin @("audio/l16", "audio/pcm", "application/octet-stream")) {
        throw "Unexpected raw audio MIME type: $mimeType."
    }

    $sampleRate = Get-PropertyValue -Object $AudioBlock -Name "sample_rate"
    if ($null -eq $sampleRate) {
        $sampleRate = Get-PropertyValue -Object $AudioBlock -Name "sampleRate"
    }
    if ($null -eq $sampleRate) {
        $rateParameter = $mimeParts | Where-Object { $_ -match '^rate\s*=\s*(\d+)$' } | Select-Object -First 1
        $sampleRate = if ($rateParameter -and $rateParameter -match '^rate\s*=\s*(\d+)$') { [int]$Matches[1] } else { 24000 }
    }

    $channels = Get-PropertyValue -Object $AudioBlock -Name "channels"
    if ($null -eq $channels) {
        $channelParameter = $mimeParts | Where-Object { $_ -match '^channels\s*=\s*(\d+)$' } | Select-Object -First 1
        $channels = if ($channelParameter -and $channelParameter -match '^channels\s*=\s*(\d+)$') { [int]$Matches[1] } else { 1 }
    }

    return New-PcmWave -Pcm $payload -SampleRate ([int]$sampleRate) -Channels ([int]$channels) -BitsPerSample 16
}

function Get-HttpStatusCode {
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    try {
        if ($ErrorRecord.Exception.Data.Contains("HttpStatusCode")) {
            return [int]$ErrorRecord.Exception.Data["HttpStatusCode"]
        }
        if ($null -ne $ErrorRecord.Exception.Response) {
            return [int]$ErrorRecord.Exception.Response.StatusCode
        }
    }
    catch {
    }
    return $null
}

function Get-HttpErrorBody {
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    try {
        $response = $ErrorRecord.Exception.Response
        if ($null -eq $response) {
            return $null
        }
        $stream = $response.GetResponseStream()
        if ($null -eq $stream) {
            return $null
        }
        $reader = New-Object IO.StreamReader($stream)
        try {
            return $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
    }
    catch {
        return $null
    }
}

function Save-Manifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )

    $partialPath = "$Path.partial"
    $Value |
        ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $partialPath -Encoding UTF8
    Move-Item -LiteralPath $partialPath -Destination $Path -Force
}

function Invoke-GeminiTts {
    param(
        [Parameter(Mandatory = $true)][Security.SecureString]$SecureApiKey,
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [Parameter(Mandatory = $true)][string]$ApiRevision,
        [Parameter(Mandatory = $true)][hashtable]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 12 -Compress
    [byte[]]$body = [Text.Encoding]::UTF8.GetBytes($json)
    $retryableCodes = @(408, 429, 500, 502, 503, 504)

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            $response = Invoke-LumenWithSecureStringPlainText `
                -SecureString $SecureApiKey `
                -ScriptBlock {
                    param([string]$PlainApiKey)

                    $headers = @{
                        "x-goog-api-key" = $PlainApiKey
                        "Api-Revision" = $ApiRevision
                    }
                    return Invoke-RestMethod `
                        -Uri $Endpoint `
                        -Method Post `
                        -Headers $headers `
                        -ContentType "application/json; charset=utf-8" `
                        -Body $body `
                        -TimeoutSec $TimeoutSeconds
                }

            return [pscustomobject]@{
                Response = $response
                Attempts = $attempt
            }
        }
        catch {
            $statusCode = Get-HttpStatusCode -ErrorRecord $_
            $isRetryable = ($null -eq $statusCode) -or ($retryableCodes -contains $statusCode)
            if (-not $isRetryable -or $attempt -eq $MaxAttempts) {
                $message = [string]$_.Exception.Message
                $responseBody = Get-HttpErrorBody -ErrorRecord $_
                if (-not [string]::IsNullOrWhiteSpace($responseBody)) {
                    $message = "$message | Google response: $responseBody"
                }
                if ($message.Length -gt 1200) {
                    $message = $message.Substring(0, 1200)
                }
                throw "Gemini TTS request failed (HTTP $statusCode, attempt $attempt): $message"
            }

            $baseDelay = [Math]::Min(30, [Math]::Pow(2, $attempt - 1))
            $jitter = Get-Random -Minimum 0 -Maximum 1000
            Start-Sleep -Milliseconds ([int]($baseDelay * 1000 + $jitter))
        }
    }
}

function Get-SecureApiKeyContext {
    if ($UseEnvironmentApiKeyForCI) {
        $processKey = [Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "Process")
        if ([string]::IsNullOrWhiteSpace($processKey)) {
            throw "Se activó -UseEnvironmentApiKeyForCI, pero GEMINI_API_KEY no existe en el entorno del proceso."
        }

        try {
            $secureKey = ConvertTo-SecureString -String $processKey.Trim() -AsPlainText -Force
            $secureKey.MakeReadOnly()
            return [pscustomobject]@{
                SecureString = $secureKey
                Source = "process_environment_explicit_ci"
                PersistedEncrypted = $false
            }
        }
        finally {
            $processKey = $null
        }
    }

    $secureKey = Get-LumenGeminiApiKeySecureString
    return [pscustomobject]@{
        SecureString = $secureKey
        Source = "dpapi_current_user"
        PersistedEncrypted = $true
    }
}

function Invoke-SelfTest {
    [byte[]]$pcm = New-Object byte[] 4800
    $pcm[0] = 1
    $mock = [pscustomobject]@{
        steps = @(
            [pscustomobject]@{
                type = "model_output"
                content = @(
                    [pscustomobject]@{
                        type = "audio"
                        data = [Convert]::ToBase64String($pcm)
                        mime_type = "audio/l16"
                        channels = 1
                        sample_rate = 24000
                    }
                )
            }
        )
    }

    $block = Find-FirstAudioBlock -Node $mock
    if ($null -eq $block) {
        throw "Self-test could not locate the audio block."
    }
    [byte[]]$wave = Convert-AudioBlockToWave -AudioBlock $block
    $info = Get-WaveInfo -Bytes $wave
    if ($info.DurationSeconds -le 0) {
        throw "Self-test produced an invalid duration."
    }
}

$resolvedConfigPath = Resolve-ProjectPath -Path $ConfigPath
$resolvedOutputRoot = Resolve-ProjectPath -Path $OutputRoot

if (-not (Test-Path -LiteralPath $resolvedConfigPath -PathType Leaf)) {
    throw "Missing audition config: $resolvedConfigPath"
}
if (-not (Test-Path -LiteralPath $previewTemplatePath -PathType Leaf)) {
    throw "Missing preview template: $previewTemplatePath"
}

$config = Get-Content -LiteralPath $resolvedConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$google = $config.google_gemini
if ([string]$google.endpoint -ne 'https://generativelanguage.googleapis.com/v1beta/interactions') {
    throw 'Unsupported provider endpoint.'
}
if ($google.voices.Count -ne 1) { throw 'Exactly one voice per durable request is required.' }
if ([string]$config.language -notmatch '^(?:es|en)-[A-Z]{2}$') {
    throw "This audition pipeline requires a supported regional language tag such as es-ES, es-CO, or en-US."
}
if ($google.voices.Count -lt 1) {
    throw "At least one Google voice is required."
}

Invoke-SelfTest
if ($ValidateOnly) {
    Write-Host "Validation OK"
    Write-Host "Model: $($google.model)"
    Write-Host "Voices: $(($google.voices.id) -join ', ')"
    Write-Host "No network request was made and no API key was read."
    exit 0
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$secretContext = $null
$secretSource = if ($UseEnvironmentApiKeyForCI) {
    "process_environment_explicit_ci"
}
else {
    "dpapi_current_user"
}
$secretPersistedEncrypted = -not $UseEnvironmentApiKeyForCI
$batchId = "google-gemini-tts-{0}" -f ([DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ"))
$batchDirectory = Join-Path $resolvedOutputRoot $batchId
New-Item -ItemType Directory -Path $batchDirectory -Force | Out-Null

$manifest = [ordered]@{
    schema_version = 1
    batch_id = $batchId
    created_utc = [DateTime]::UtcNow.ToString("o")
    provider = $google.provider
    api = $google.api
    api_revision = $google.api_revision
    endpoint = $google.endpoint
    model = [ordered]@{
        id = $google.model
        lifecycle = $google.model_lifecycle
    }
    comparison = [ordered]@{
        language = $config.language
        transcript = $config.transcript
        transcript_sha256 = Get-Utf8Sha256 -Text $config.transcript
        direction = $config.direction
        direction_sha256 = Get-Utf8Sha256 -Text $config.direction
        same_text_and_direction_for_all = $true
        sample_rate = $google.sample_rate
        channels = $google.channels
        bits_per_sample = $google.bits_per_sample
    }
    secret_handling = [ordered]@{
        api_key_source = $secretSource
        api_key_persisted_encrypted = [bool]$secretPersistedEncrypted
        provider_or_voice_substitution_allowed = $false
    }
    commercial_review = [ordered]@{
        status = "required_before_publication"
        note = "Preview/free-tier terms and data-use settings must be reviewed again before a commercial master is published."
    }
    run_status = "in_progress"
    failure = $null
    samples = @()
}

$manifestPath = Join-Path $batchDirectory "manifest.json"
Save-Manifest -Path $manifestPath -Value $manifest

try {
    $secretContext = Get-SecureApiKeyContext

    foreach ($voice in ($google.voices | Sort-Object order)) {
        Write-Host ("Generating {0}: {1}..." -f $voice.order, $voice.id)
        $payload = @{
            model = [string]$google.model
            input = [string]$config.direction
            response_format = @{
                type = "audio"
            }
            generation_config = @{
                speech_config = @(
                    @{
                        voice = [string]$voice.id
                    }
                )
            }
            store = $false
        }

        $result = Invoke-GeminiTts `
            -SecureApiKey $secretContext.SecureString `
            -Endpoint ([string]$google.endpoint) `
            -ApiRevision ([string]$google.api_revision) `
            -Payload $payload

        $audioBlock = Find-FirstAudioBlock -Node $result.Response
        if ($null -eq $audioBlock) {
            throw "Google returned no audio block for voice $($voice.id)."
        }

        [byte[]]$waveBytes = Convert-AudioBlockToWave -AudioBlock $audioBlock
        $waveInfo = Get-WaveInfo -Bytes $waveBytes
        $finalPath = Join-Path $batchDirectory ([string]$voice.file)
        $partialPath = "$finalPath.partial"
        [IO.File]::WriteAllBytes($partialPath, $waveBytes)
        Move-Item -LiteralPath $partialPath -Destination $finalPath

        $mimeType = [string](Get-PropertyValue -Object $audioBlock -Name "mime_type")
        if ([string]::IsNullOrWhiteSpace($mimeType)) {
            $mimeType = [string](Get-PropertyValue -Object $audioBlock -Name "mimeType")
        }
        $interactionId = [string](Get-PropertyValue -Object $result.Response -Name "id")
        $hash = (Get-FileHash -LiteralPath $finalPath -Algorithm SHA256).Hash.ToLowerInvariant()

        $manifest.samples += [ordered]@{
            order = [int]$voice.order
            provider = [string]$google.provider
            model = [string]$google.model
            voice = [string]$voice.id
            descriptor = [string]$voice.descriptor
            file = [string]$voice.file
            status = "ok"
            interaction_id = $interactionId
            attempts = [int]$result.Attempts
            received_mime_type = $mimeType
            duration_seconds = $waveInfo.DurationSeconds
            bytes = (Get-Item -LiteralPath $finalPath).Length
            sha256 = $hash
            peak_pcm16 = $waveInfo.Peak
            rms_pcm16 = $waveInfo.Rms
        }
        Save-Manifest -Path $manifestPath -Value $manifest
    }

    $manifest.run_status = "complete"
    Save-Manifest -Path $manifestPath -Value $manifest

    $previewData = [ordered]@{
        title = "Pruebas de voz graves"
        subtitle = "Google Gemini TTS - audicion controlada - $($config.language)"
        batch_id = $batchId
        transcript = $config.transcript
        direction_summary = if ($null -ne $config.PSObject.Properties["direction_summary"]) {
            [string]$config.direction_summary
        }
        else {
            "Voz masculina muy grave, natural y calida; locutor documental; ritmo muy pausado."
        }
        samples = @(
            foreach ($sample in $manifest.samples) {
                [ordered]@{
                    order = $sample.order
                    provider = $sample.provider
                    model = $sample.model
                    voice = $sample.voice
                    descriptor = $sample.descriptor
                    file = $sample.file
                    duration_seconds = $sample.duration_seconds
                }
            }
        )
    }
    $previewDataJson = $previewData | ConvertTo-Json -Depth 8 -Compress
    "window.AUDITION_DATA = $previewDataJson;" | Set-Content -LiteralPath (Join-Path $batchDirectory "auditions-data.js") -Encoding UTF8
    Copy-Item -LiteralPath $previewTemplatePath -Destination (Join-Path $batchDirectory "index.html")

    Write-Host ""
    Write-Host "Audition batch complete:"
    Write-Host $batchDirectory
    Write-Host "Preview:"
    Write-Host (Join-Path $batchDirectory "index.html")

    if ($OpenPreview) {
        Start-Process -FilePath (Join-Path $batchDirectory "index.html")
    }
}
catch {
    $safeMessage = [string]$_.Exception.Message
    if ($safeMessage.Length -gt 1400) {
        $safeMessage = $safeMessage.Substring(0, 1400)
    }
    $manifest.run_status = "failed"
    $manifest.failure = [ordered]@{
        recorded_utc = [DateTime]::UtcNow.ToString("o")
        message = $safeMessage
        api_key_redacted = $true
    }
    Save-Manifest -Path $manifestPath -Value $manifest
    throw
}
finally {
    if ($null -ne $secretContext -and $null -ne $secretContext.SecureString) {
        $secretContext.SecureString.Dispose()
    }
    $secretContext = $null
}
