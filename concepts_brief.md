# Boobees Suits

Working concept · 2026-11-24

## Overview

Give Semibots a ghost-bee outfit based on the fabric silhouette of Cast-Iron Boo-Bee from Boobees Valuables. A soft ivory hood, chest drape, sleeves and striped hem make one costume when worn together. Rounded antenna tips and black-and-honey socks carry the bee theme. The open hood frames the Semibot’s eyes and face.

## First playable set

| Piece | Game slot | Design |
| --- | --- | --- |
| Boo-Bee Antennae | Hat | Two dark stems with round honey-yellow tips. |
| Boo-Bee Hood | Head Top Overlay | Ivory cloth over the crown, sides and back of the head, with an open face. |
| Boo-Bee Bodice | Body Top | Draped ivory fabric shaped over the chest, continuing down to the hem. |
| Boo-Bee Left Sleeve / Right Sleeve | Arm Left / Right | Loose ivory fabric using the same weave and color as the cloak. |
| Boo-Bee Mantle | Body Bottom | A pleated skirt with a honey-and-charcoal stripe. |
| Boo-Bee Left Sock / Right Sock | Foot Left / Right | Matching black-and-honey socks that follow the feet independently. |

Players can mix pieces with other cosmetics or use all eight slots for the full outfit. The game’s preset menu can recall the equipped combination. The individual pieces use the normal unlock flow. The pack targets solo and co-op with the same version on both clients.

## Analysis

The separate head, torso and hem pieces follow different joints. Bounds and slot rules can be checked offline. Movement fit, including small gaps or clipping at the neckline and waist during crouch, crawl and tumble, needs in-game verification. Multiplayer visibility also needs a check from both clients.

REPOLib registers the pieces with the stock cosmetics menu. The offline check compares the selected slots with the installed game's attachment points and conflict rules. [REPOLib cosmetics guide](https://repomods.com/apis/repolib/sdk/cosmetics.html)

The 0.2.1 fit pass used the installed prefabs for Antennas, Beanie, Bandages, Basic Shirt, Hoodie, Wizard Bottom, Skirt, Knit Sleeve, Puff Sleeve Long, Tube Sock, and Sneaker. Their bounds informed the sleeve length, the join between body pieces, and the sock sole height. The reference models served as measurements. The package contains the original Boo-Bee meshes.

Use original wearable geometry based on the fabric and trim of the collectible. [Cast-Iron Boo-Bee gallery](https://thunderstore.io/c/repo/p/BooBees/BoobeesValuables/)
