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

Import the ZIP as a local mod in your R.E.P.O. mod manager. The target setup is R.E.P.O. 0.5.3 with BepInExPack 5.4.2305 and REPOLib 4.5.1. For manual installation, copy `plugins/BoobeesSuits/BoobeesSuits.dll` under `BepInEx/plugins/BoobeesSuits/` after installing the dependencies. Boobees Valuables is an art reference and a separate download.

## Build

Run `./tools/build.ps1` from the repository root with PowerShell 7 and .NET SDK 8 or later. The first build downloads and verifies pinned public compile-time dependencies. The build embeds the outfit meshes, textures and icons, then writes the Thunderstore ZIP to `dist/`. To build against an installed copy of the game, see the local build command in [AGENTS.md](AGENTS.md).

To rebuild the mesh data, open the approved outfit in Blender and run `tools/export_release_assets.py` with `src/Assets` and a JSON receipt path. The exporter uses the checked Semibot anchor measurements for the standing and crouching variants.

Run `tools/export_sneaker_release_assets.py` in Blender with the asset, icon and receipt output paths to export the Sneaker Bee costume.

Run `tools/export_winter_release_assets.py` in Blender with the same three output paths to export the New Year Bee costume, including the hat's emission map.
