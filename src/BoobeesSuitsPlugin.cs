using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using BepInEx;
using HarmonyLib;
using REPOLib.Modules;
using UnityEngine;

namespace BoobeesSuits;

[BepInPlugin("BooBees.BoobeesSuits", "Boobees Suits", "0.5.6")]
[BepInDependency("REPOLib", "4.5.1")]
public sealed class BoobeesSuitsPlugin : BaseUnityPlugin
{
    private readonly List<CosmeticAsset> outfit = new();
    private Harmony? patches;

    private void Awake()
    {
        // Populate the game's cached sprite so unlock screens and presets use the same art.
        var iconField = typeof(CosmeticAsset).GetField("icon", BindingFlags.NonPublic | BindingFlags.Instance);
        var shader = Shader.Find("Standard");
        if (iconField?.FieldType != typeof(Sprite) || shader == null || !shader.isSupported)
        {
            Logger.LogError("Boobees Suits needs the R.E.P.O. 0.5.3 cosmetic icon and Standard shader.");
            return;
        }

        var inventory = new GameObject("Boobees Suits Templates");
        inventory.SetActive(false);
        DontDestroyOnLoad(inventory);

        var models = new SuitModels(shader);
        patches = new Harmony("BooBees.BoobeesSuits");
        patches.CreateClassProcessor(typeof(UpperBodyMount)).Patch();
        patches.CreateClassProcessor(typeof(RemoteBodiceMotion)).Patch();
        AddPiece("Antennae", SemiFunc.CosmeticType.Hat, inventory.transform, p => models.Add(p, "Antennae"), iconField);
        AddPiece("Hood", SemiFunc.CosmeticType.HeadTopOverlay, inventory.transform, p => models.Add(p, "Hood"), iconField);
        AddPiece("Hood Lower", SemiFunc.CosmeticType.HeadBottomOverlay, inventory.transform,
            p => models.Add(p, "Hood Lower"), iconField, "HoodLower");
        AddPiece("Bodice", SemiFunc.CosmeticType.BodyTop, inventory.transform, p => models.Add(p, "Bodice"), iconField);
        AddPiece("Wings", SemiFunc.CosmeticType.BodyBottomOverlay, inventory.transform,
            p => models.Add(p, "Wings"), iconField, mountOnUpperBody: true);
        AddPiece("Left Sleeve", SemiFunc.CosmeticType.ArmLeft, inventory.transform,
            p => models.Add(p, "Left Sleeve"), iconField, "SleeveLeft");
        AddPiece("Right Sleeve", SemiFunc.CosmeticType.ArmRight, inventory.transform,
            p => models.Add(p, "Right Sleeve"), iconField, "Sleeve");
        // BodyBottom is hidden in the native crouch, so the hem follows BodyTopOverlay.
        AddPiece("Mantle", SemiFunc.CosmeticType.BodyTopOverlay, inventory.transform, p => models.Add(p, "Hem"), iconField);
        AddPiece("Left Sock", SemiFunc.CosmeticType.FootLeft, inventory.transform, p => models.Add(p, "Left Sock"), iconField, "SockLeft");
        AddPiece("Right Sock", SemiFunc.CosmeticType.FootRight, inventory.transform, p => models.Add(p, "Right Sock"), iconField, "Sock");

        var sneakers = new CostumeModels(shader, "Sneaker", 8);
        void AddSneaker(string piece, string key, SemiFunc.CosmeticType slot, bool mountOnUpperBody = false)
        {
            AddPiece(piece, slot, inventory.transform, parent => sneakers.Add(parent, key),
                iconField, $"Sneaker-{key}", mountOnUpperBody, "Sneaker Bee");
        }

        AddSneaker("Antennae", "antennae", SemiFunc.CosmeticType.Hat);
        AddSneaker("Sweater", "sweater", SemiFunc.CosmeticType.BodyTop);
        AddSneaker("Abdomen", "abdomen", SemiFunc.CosmeticType.BodyTopOverlay);
        AddSneaker("Wings", "wings", SemiFunc.CosmeticType.BodyBottomOverlay, mountOnUpperBody: true);
        AddSneaker("Left Sleeve", "sleeve-left", SemiFunc.CosmeticType.ArmLeft);
        AddSneaker("Right Sleeve", "sleeve-right", SemiFunc.CosmeticType.ArmRight);
        AddSneaker("Left Sneaker", "shoe-left", SemiFunc.CosmeticType.FootLeft);
        AddSneaker("Right Sneaker", "shoe-right", SemiFunc.CosmeticType.FootRight);

        var winter = new CostumeModels(shader, "Winter", 9);
        void AddWinter(string piece, string key, SemiFunc.CosmeticType slot, bool mountOnUpperBody = false,
            bool coversPanel = true)
        {
            AddPiece(piece, slot, inventory.transform, parent => winter.Add(parent, key), iconField,
                $"Winter-{key}", mountOnUpperBody, "New Year Bee", coversPanel);
        }

        AddWinter("Hat and Lights", "hat", SemiFunc.CosmeticType.Hat);
        AddWinter("Scarf", "scarf", SemiFunc.CosmeticType.HeadBottomOverlay, mountOnUpperBody: true, coversPanel: false);
        AddWinter("Sweater", "sweater", SemiFunc.CosmeticType.BodyTop);
        AddWinter("Left Sleeve", "sleeve-left", SemiFunc.CosmeticType.ArmLeft);
        AddWinter("Right Sleeve", "sleeve-right", SemiFunc.CosmeticType.ArmRight);
        AddWinter("Abdomen", "abdomen", SemiFunc.CosmeticType.BodyTopOverlay);
        AddWinter("Wings", "wings", SemiFunc.CosmeticType.BodyBottomOverlay, mountOnUpperBody: true);
        AddWinter("Left Boot", "boot-left", SemiFunc.CosmeticType.FootLeft);
        AddWinter("Right Boot", "boot-right", SemiFunc.CosmeticType.FootRight);
    }

    private IEnumerator Start()
    {
        if (outfit.Count == 0)
            yield break;
        var unlocksField = typeof(MetaManager).GetField("cosmeticUnlocks", BindingFlags.NonPublic | BindingFlags.Instance);
        if (unlocksField?.FieldType != typeof(List<int>))
        {
            Logger.LogWarning("Could not find the cosmetic unlock list. The outfit is available through normal rewards.");
            yield break;
        }

        // REPOLib adds the modded assets and restores the unlocked IDs in the same callback.
        // Wait until our registered assets have their real game indices before making them available.
        MetaManager meta;
        while (true)
        {
            meta = MetaManager.instance;
            if (meta != null && outfit.TrueForAll(meta.cosmeticAssets.Contains))
                break;
            yield return null;
        }

        if (unlocksField.GetValue(meta) is not List<int> unlocked)
            yield break;
        int added = 0;
        foreach (var piece in outfit)
        {
            int index = meta.cosmeticAssets.IndexOf(piece);
            if (unlocked.Contains(index))
                continue;
            unlocked.Add(index);
            added++;
        }
        // The existing save flow persists modded unlocks when the player applies their outfit.
        Logger.LogInfo($"Boobees Suits available in Customize ({outfit.Count} pieces, {added} newly unlocked).");
    }

    private void OnDestroy() => patches?.UnpatchSelf();

    private void AddPiece(string piece, SemiFunc.CosmeticType slot, Transform inventory, Action<Transform> build,
        FieldInfo iconField, string? iconKey = null, bool mountOnUpperBody = false, string setName = "Boo-Bee",
        bool coversPanel = true)
    {
        string displayName = $"{setName} {piece}";
        // REPOLib derives the persistent cosmetic ID from this asset name.
        string internalName = $"BoobeesSuits_{displayName}";
        var template = new GameObject(internalName);
        template.transform.SetParent(inventory, false);
        var cosmetic = template.AddComponent<Cosmetic>();
        cosmetic.type = slot;
        cosmetic.meshParents = new List<Transform>();
        int geometryCount = !mountOnUpperBody && slot is (SemiFunc.CosmeticType.BodyTopOverlay
            or SemiFunc.CosmeticType.HeadBottomOverlay) ? 2 : 1;
        // The game reparents overlay roots to its spherical and flat mesh groups, respectively.
        for (int i = 0; i < geometryCount; i++)
        {
            var geometry = new GameObject(i == 0 ? "Geometry" : "Flat Geometry").transform;
            geometry.SetParent(template.transform, false);
            build(geometry);
            geometry.gameObject.SetActive(i == 0);
            if (!mountOnUpperBody)
                cosmetic.meshParents.Add(geometry);
        }
        if (mountOnUpperBody)
            template.AddComponent<UpperBodyMount>();
        if (coversPanel && slot is (SemiFunc.CosmeticType.BodyTop or SemiFunc.CosmeticType.HeadBottomOverlay
            or SemiFunc.CosmeticType.BodyTopOverlay))
            template.AddComponent<FabricCoverage>().Configure(slot);
        if (slot == SemiFunc.CosmeticType.Hat)
        {
            var crownTarget = new GameObject("Crown Anchor").transform;
            crownTarget.SetParent(template.transform, false);
            crownTarget.localPosition = new Vector3(0f, 0.55f, 0.25f);
            template.AddComponent<CosmeticPlayerCrown>().targetMain = crownTarget;
        }

        var asset = ScriptableObject.CreateInstance<CosmeticAsset>();
        asset.name = internalName;
        asset.assetName = displayName;
        asset.type = slot;
        asset.status = CosmeticAsset.Status.Finalized;
        asset.rarity = SemiFunc.Rarity.Common;
        asset.customTypeList = new List<CosmeticCustomCondition.Type>();
        asset.tintable = false;
        iconField.SetValue(asset, LoadIcon(iconKey ?? piece, displayName));
        asset.prefab = NetworkPrefabs.RegisterNetworkPrefab($"Cosmetics/{internalName}", template);
        if (asset.prefab == null || Cosmetics.RegisterCosmetic(asset) == null)
        {
            Destroy(template);
            Destroy(asset);
            Logger.LogError($"Failed to register {displayName}.");
            return;
        }

        outfit.Add(asset);
        Logger.LogInfo($"Queued {displayName} for the {slot} slot.");
    }

    private static Sprite LoadIcon(string piece, string displayName)
    {
        using Stream resource = typeof(BoobeesSuitsPlugin).Assembly.GetManifestResourceStream($"BoobeesSuits.{piece}.png")
            ?? throw new InvalidDataException($"Missing icon for {piece}.");
        using var image = new MemoryStream();
        resource.CopyTo(image);
        var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
        if (!ImageConversion.LoadImage(texture, image.ToArray(), true))
        {
            Destroy(texture);
            throw new InvalidDataException($"Invalid icon for {piece}.");
        }

        texture.name = displayName;
        return Sprite.Create(texture, new Rect(0, 0, texture.width, texture.height), new Vector2(0.5f, 0.5f));
    }
}
