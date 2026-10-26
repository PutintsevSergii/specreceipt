param([string]$Destination)
$ErrorActionPreference = 'Stop'

function Install-HarnessUv([string]$Target) {
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Native uv bootstrap supports Windows x64.' }
    $Target = [IO.Path]::GetFullPath($Target)
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    $binary = Join-Path $Target 'uv.exe'
    if (Test-Path -LiteralPath $binary) { throw 'Managed uv already exists; inspect it before retrying.' }
    $version = '0.13.5'
    $expected = 'a38b8d1902b7cfbc76b423ba1bb456f623f42064cdc72628b6075b89afd1019a'
    $asset = 'uv-x86_64-pc-windows-msvc.zip'
    $stage = Join-Path $Target ('.uv-stage-' + [Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $stage | Out-Null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $archivePath = Join-Path $stage 'uv.zip'
        $downloaded = $false
        foreach ($origin in @('https://github.com/astral-sh/uv/releases/download/', 'https://releases.astral.sh/github/uv/releases/download/')) {
            try {
                Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri ($origin + $version + '/' + $asset) -OutFile $archivePath
                $downloaded = $true
                break
            } catch {
                Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
                Write-Warning ('uv download unavailable from ' + $origin)
            }
        }
        if (-not $downloaded) { throw 'uv download failed from both official release origins. Install native uv manually and retry.' }
        if ((Get-Item -LiteralPath $archivePath).Length -gt 100MB) { throw 'uv archive exceeds size limit.' }
        $stream = [IO.File]::OpenRead($archivePath)
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $actual = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose(); $stream.Dispose() }
        if ($actual -ne $expected) { throw 'uv archive checksum mismatch.' }
        [void][Reflection.Assembly]::LoadWithPartialName('System.IO.Compression.FileSystem')
        $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
        try {
            $names = @($archive.Entries | ForEach-Object { $_.FullName })
            if ($names.Count -ne 3 -or @($names | Select-Object -Unique).Count -ne 3 -or
                @($names | Where-Object { $_ -cnotin @('uv.exe', 'uvw.exe', 'uvx.exe') }).Count -ne 0) { throw 'Unsafe uv archive layout.' }
            $entry = $archive.GetEntry('uv.exe')
            if ($entry.Length -gt 100MB) { throw 'uv binary exceeds size limit.' }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $stage 'uv.exe'), $false)
        } finally { $archive.Dispose() }
        # Same-volume move without overwrite publishes only a verified binary.
        [IO.File]::Move((Join-Path $stage 'uv.exe'), $binary)
    } finally { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not $Destination) { throw 'A user-local destination is required.' }
    Install-HarnessUv $Destination
}
