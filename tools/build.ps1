[CmdletBinding()]
param(
    [string]$GameRoot = 'C:/Program Files (x86)/Steam/steamapps/common/REPO',
    [string]$BepInExCore = (Join-Path $GameRoot 'BepInEx/core'),
    [Parameter(Mandatory)][string]$RepoLibPath
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$game = (Resolve-Path -LiteralPath $GameRoot).Path
$core = (Resolve-Path -LiteralPath $BepInExCore).Path
$repolib = (Resolve-Path -LiteralPath $RepoLibPath).Path
$output = Join-Path $project '.local/build'
$env:DOTNET_CLI_HOME = Join-Path $project '.local/dotnet'
$env:DOTNET_NOLOGO = '1'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'

$manifestPath = Join-Path $project 'packaging/manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
& dotnet build (Join-Path $project 'src/BoobeesSuits.csproj') -c Release --artifacts-path $output `
    "-p:GameRoot=$game" "-p:BepInExCore=$core" "-p:RepoLibPath=$repolib" '-p:NuGetAudit=false' --ignore-failed-sources
if ($LASTEXITCODE -ne 0) { throw 'Could not build Boobees Suits.' }

$assembly = Join-Path $output 'bin/BoobeesSuits/release/BoobeesSuits.dll'
if ([System.Reflection.AssemblyName]::GetAssemblyName($assembly).Version.ToString(3) -ne $manifest.version_number) {
    throw 'Assembly and manifest versions differ.'
}

$dist = Join-Path $project 'dist'
New-Item -ItemType Directory -Path $dist -Force | Out-Null
$package = Join-Path $dist ('BoobeesSuits-' + $manifest.version_number + '.zip')
$files = [ordered]@{
    'manifest.json' = $manifestPath
    'README.md' = (Join-Path $project 'packaging/README.md')
    'icon.png' = (Join-Path $project 'packaging/icon.png')
    'plugins/BoobeesSuits/BoobeesSuits.dll' = $assembly
}
$stream = [IO.File]::Open($package, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($name in $files.Keys) {
            $entry = $archive.CreateEntry($name, [IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = [DateTimeOffset]::Parse('2000-01-01T00:00:00+00:00')
            $entryStream = $entry.Open()
            try { $entryStream.Write([IO.File]::ReadAllBytes($files[$name])) }
            finally { $entryStream.Dispose() }
        }
    } finally { $archive.Dispose() }
} finally { $stream.Dispose() }
Get-FileHash -LiteralPath $package
