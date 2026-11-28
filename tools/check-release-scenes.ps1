[CmdletBinding()]
param([string]$Blender = 'blender')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$run = Join-Path $root ('.local/scene-check/' + [guid]::NewGuid())
$cases = @(
    @{ Name = 'Outfit'; Script = 'export_release_assets.py'; Scene = 'dist/semibot-runtime-fit/Boobees-bending-fit.blend' }
    @{ Name = 'Sneaker'; Script = 'export_sneaker_release_assets.py' }
    @{ Name = 'Winter'; Script = 'export_winter_release_assets.py' }
)
foreach ($case in $cases) {
    $folder = Join-Path $run $case.Name
    $assets = Join-Path $folder 'assets'
    $report = Join-Path $folder 'report.json'
    $arguments = @('--background')
    if ($case.Scene) { $arguments += Join-Path $root $case.Scene }
    $arguments += @('--python-exit-code', '1', '--python', (Join-Path $PSScriptRoot $case.Script), '--', $assets)
    if (!$case.Scene) { $arguments += Join-Path $folder 'icons' }
    & $Blender @arguments $report
    if ($LASTEXITCODE) { throw "Blender export failed for $($case.Name)" }
    $file = $case.Name + '.bin.gz'
    $actual = (Get-FileHash -LiteralPath (Join-Path $assets $file)).Hash
    $expected = (Get-FileHash -LiteralPath (Join-Path $root "src/Assets/$file")).Hash
    if ($expected -ne $actual) { throw "$file differs from the embedded mesh. Inspect $folder" }
    Write-Output "$file SHA-256 $actual"
}
Write-Output "Verified three mesh packs. Exports and reports are in $run"
