# Boobees Suits

Three bee outfits for R.E.P.O. The ghostly Boo-Bee is inspired by Cast-Iron Boo-Bee from [Boobees Valuables](https://thunderstore.io/c/repo/p/BooBees/BoobeesValuables/). Sneaker Bee has golden knitwear, a striped abdomen, wings and sneakers. New Year Bee has a Santa cap with glowing antenna lights, a scarf, snowflake knitwear, frosted wings and winter boots.

| Cosmetic | Slot |
| --- | --- |
| Boo-Bee Antennae | Hat |
| Boo-Bee Hood | Head Top Overlay |
| Boo-Bee Hood Lower | Head Bottom Overlay |
| Boo-Bee Bodice | Body Top |
| Boo-Bee Wings | Body Bottom Overlay |
| Boo-Bee Left Sleeve / Right Sleeve | Armwear Left / Right |
| Boo-Bee Mantle | Body Top Overlay |
| Boo-Bee Left Sock / Right Sock | Foot Left / Right |

Equip both hood pieces for the full hood, then save the outfit through Customize. For co-op, install the same version on all clients.

Sneaker Bee has eight separate pieces. Its sweater uses Body Top, its abdomen uses Body Top Overlay, and its antennae, wings, sleeves and footwear use the corresponding slots in the table.

New Year Bee has nine separate pieces. Its antenna lights are part of the hat. The scarf uses Head Bottom Overlay and the other pieces use the same categories as Sneaker Bee.

## Install

Import the ZIP as a local mod in your R.E.P.O. mod manager. Version 0.5.7 targets R.E.P.O. 0.5.4 (Unity 6000.3.28f1) with BepInExPack 5.4.2305 and REPOLib 4.5.1. The mod and its visibility probe compile against this game build. In-game testing is pending. For manual installation, copy `plugins/BoobeesSuits/BoobeesSuits.dll` under `BepInEx/plugins/BoobeesSuits/` after installing the dependencies. Boobees Valuables is an art reference and a separate download.

## Build

Run `./tools/build.ps1` from the repository root with PowerShell 7 and the .NET SDK 10 version pinned in `global.json` (10.0.404). The DLL targets .NET Standard 2.1 for Unity Mono. The first build downloads and verifies public compile-time dependencies, including the available R.E.P.O. 0.4.4 reference assembly and Unity 6000.3.26 modules. The build embeds the outfit meshes, textures and icons, then writes the Thunderstore ZIP to `dist/`. To compile against the exact 0.5.4 game assemblies, use the local build command in [AGENTS.md](AGENTS.md).

To rebuild the mesh data, open the approved outfit in Blender and run `tools/export_release_assets.py` with `src/Assets` and a JSON receipt path. The exporter uses the checked Semibot anchor measurements for the standing and crouching variants.

Run `tools/export_sneaker_release_assets.py` in Blender with the asset, icon and receipt output paths to export the Sneaker Bee costume.

Run `tools/export_winter_release_assets.py` in Blender with the same three output paths to export the New Year Bee costume, including the hat's emission map.
