function Get-PublicBuildReferences {
    param([Parameter(Mandatory)][string]$CacheRoot)

    $ProgressPreference = 'SilentlyContinue'
    $packages = @(
        @{
            Name = 'R.E.P.O.GameLibs.Steam-0.4.4-ngd.0'
            Url = 'https://api.nuget.org/v3-flatcontainer/r.e.p.o.gamelibs.steam/0.4.4-ngd.0/r.e.p.o.gamelibs.steam.0.4.4-ngd.0.nupkg'
            Sha256 = '6DB2E05B1FF27FC97E458FA01E2560F31B20193964C988F9DFD3CAFB64CDC3E4'
            Entries = @{
                'ref/netstandard2.1/Assembly-CSharp.dll' = 'managed/Assembly-CSharp.dll'
            }
        }
        @{
            Name = 'UnityEngine.Modules-6000.3.26'
            Url = 'https://nuget.bepinex.dev/v3/package/unityengine.modules/6000.3.26/unityengine.modules.6000.3.26.nupkg'
            Sha256 = 'DC156387BFD2288FB466C38A5A0F2EC992DD39F0BB2B38E9EDEE82E711EDDCA2'
            Entries = @{
                'lib/netstandard2.0/UnityEngine.dll' = 'managed/UnityEngine.dll'
                'lib/netstandard2.0/UnityEngine.CoreModule.dll' = 'managed/UnityEngine.CoreModule.dll'
                'lib/netstandard2.0/UnityEngine.ImageConversionModule.dll' = 'managed/UnityEngine.ImageConversionModule.dll'
            }
        }
        @{
            Name = 'BepInExPack-5.4.2305'
            Url = 'https://thunderstore.io/package/download/BepInEx/BepInExPack/5.4.2305/'
            Sha256 = 'F99B6302B6BDCA5BAB26F275C261CCA448B29BBAC34EAA5CBEBB42C4246FB244'
            Entries = @{
                'BepInExPack/BepInEx/core/BepInEx.dll' = 'bepinex/BepInEx.dll'
                'BepInExPack/BepInEx/core/0Harmony.dll' = 'bepinex/0Harmony.dll'
            }
        }
        @{
            Name = 'REPOLib-4.5.1'
            Url = 'https://thunderstore.io/package/download/Zehs/REPOLib/4.5.1/'
            Sha256 = '4F547B3F2B3D0241D0CF8AABFADCE0A890D716CDF209D12031D90418D3C5ECB1'
            Entries = @{
                'plugins/REPOLib.dll' = 'REPOLib.dll'
            }
        }
    )

    $managed = Join-Path $CacheRoot 'managed'
    $bepInEx = Join-Path $CacheRoot 'bepinex'
    New-Item -ItemType Directory -Path $CacheRoot, $managed, $bepInEx -Force | Out-Null
    foreach ($package in $packages) {
        $archivePath = Join-Path $CacheRoot ($package.Name + '.zip')
        if (!(Test-Path -LiteralPath $archivePath -PathType Leaf) -or
            (Get-FileHash -LiteralPath $archivePath).Hash -ne $package.Sha256) {
            $download = Join-Path $CacheRoot ([IO.Path]::GetRandomFileName())
            try {
                Write-Host "Downloading $($package.Name)"
                Invoke-WebRequest -Uri $package.Url -OutFile $download -TimeoutSec 60
                $actual = (Get-FileHash -LiteralPath $download).Hash
                if ($actual -ne $package.Sha256) {
                    throw "Expected SHA-256 $($package.Sha256), received $actual."
                }
                Move-Item -LiteralPath $download -Destination $archivePath -Force
            } catch {
                throw "Could not obtain $($package.Name) from $($package.Url). $($_.Exception.Message)"
            } finally {
                if (Test-Path -LiteralPath $download) {
                    Remove-Item -LiteralPath $download -Force
                }
            }
        }

        $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
        try {
            foreach ($file in $package.Entries.GetEnumerator()) {
                $entry = $archive.GetEntry($file.Key)
                if ($null -eq $entry) {
                    throw "Missing reference $($file.Key) in $($package.Name)."
                }
                $destination = Join-Path $CacheRoot $file.Value
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $true)
            }
        } finally {
            $archive.Dispose()
        }
    }

    [pscustomobject]@{
        Managed = $managed
        BepInExCore = $bepInEx
        RepoLib = Join-Path $CacheRoot 'REPOLib.dll'
    }
}
