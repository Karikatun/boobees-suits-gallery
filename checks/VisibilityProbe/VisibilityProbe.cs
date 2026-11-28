using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Linq;
using System.Reflection;
using BepInEx;
using HarmonyLib;
using REPOLib.Modules;
using UnityEngine;

[BepInPlugin("BooBees.VisibilityProbe", "Boobees Visibility Probe", "1.0.0")]
[BepInDependency("BooBees.BoobeesSuits", "0.5.6")]
public sealed class VisibilityProbe : BaseUnityPlugin
{
    private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    private static string fixture = null!;

    private void Awake()
    {
        Application.runInBackground = true;
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        fixture = Path.Combine(Paths.GameRootPath, "save-fixture");
        if (!File.Exists(Path.Combine(fixture, "MetaSave.es3")) ||
            !File.Exists(Path.Combine(fixture, "MetaSaveModded.es3")))
            throw new InvalidOperationException("Missing isolated metadata fixture");
        var harmony = new Harmony("BooBees.VisibilityProbe");
        var redirect = new HarmonyMethod(typeof(VisibilityProbe).GetMethod(nameof(RedirectSavePath), All))
            { priority = Priority.First };
        var skip = new HarmonyMethod(typeof(VisibilityProbe).GetMethod(nameof(SkipWrite), All))
            { priority = Priority.First };
        foreach (var method in new[] {
            typeof(DataDirector).GetMethod("TutorialPlayed", All),
            typeof(DataDirector).GetMethod("SaveSettings", All),
            typeof(StatsManager).GetMethod("SaveGame", All) })
            harmony.Patch(method, prefix: skip);
        Type modded = typeof(Cosmetics).Assembly.GetType("REPOLib.Patches.MetaManagerPatch", true)!;
        foreach (string method in new[] { "get_SavePathFull", "get_SavePathLegacyBackup" })
            harmony.Patch(typeof(MetaManager).GetMethod(method, All), prefix: redirect);
        foreach (string method in new[] { "get_SavePathVanilla", "get_SavePathFull", "get_SavePathLegacyBackup", "get_SavePathLegacyTemp" })
            harmony.Patch(modded.GetMethod(method, All), prefix: redirect);
        foreach (var method in new[] { typeof(MetaManager).GetMethod("Save", All),
                     typeof(MetaManager).GetMethod("CreateBackup", All), modded.GetMethod("CreateModdedBackup", All) })
            harmony.Patch(method, prefix: skip);
    }

    private static bool RedirectSavePath(MethodBase __originalMethod, ref string __result)
    {
        string file = __originalMethod.Name.Contains("Legacy") ? "unused-legacy.es3"
            : __originalMethod.DeclaringType == typeof(MetaManager) || __originalMethod.Name.EndsWith("Vanilla")
                ? "MetaSave.es3" : "MetaSaveModded.es3";
        __result = Path.Combine(fixture, file);
        return false;
    }

    private static bool SkipWrite() => false;

    private static readonly string[] Boo = {
        "Antennae", "Hood", "Hood Lower", "Bodice", "Wings",
        "Left Sleeve", "Right Sleeve", "Hem", "Left Sock", "Right Sock"
    };

    private static readonly string[] Sneaker = {
        "Sneaker antennae", "Sneaker sweater", "Sneaker abdomen", "Sneaker wings",
        "Sneaker sleeve-left", "Sneaker sleeve-right", "Sneaker shoe-left", "Sneaker shoe-right"
    };

    private static readonly string[] Winter = {
        "Winter hat", "Winter scarf", "Winter sweater", "Winter abdomen", "Winter wings",
        "Winter sleeve-left", "Winter sleeve-right", "Winter boot-left", "Winter boot-right"
    };

    private IEnumerator Start()
    {
        string dir = Path.Combine(Paths.GameRootPath, "soft-light-final");
        Directory.CreateDirectory(dir);
        var waitEnd = Time.realtimeSinceStartup + 55f;
        while (MenuManager.instance == null || MenuPageMain.instance == null || MetaManager.instance == null ||
               MetaManager.instance.cosmeticAssets.Count(IsOurAsset) != 27)
        {
            if (Time.realtimeSinceStartup >= waitEnd)
                throw new TimeoutException("The game did not register 27 costume items.");
            yield return null;
        }
        yield return new WaitForSecondsRealtime(12f);

        var meta = MetaManager.instance;
        var boo = Indices(meta, "Boo-Bee ", 10);
        var sneaker = Indices(meta, "Sneaker Bee ", 8);
        var winter = Indices(meta, "New Year Bee ", 9);
        var sets = new[] { (boo, Boo, Sneaker.Concat(Winter).ToArray(), "boo"),
            (sneaker, Sneaker, Boo.Concat(Winter).ToArray(), "sneaker"),
            (winter, Winter, Boo.Concat(Sneaker).ToArray(), "winter") };
        typeof(MetaManager).GetField("cosmeticEquipped", All)!.SetValue(meta, winter);
        var main = MenuPageMain.instance;
        typeof(MenuPageMain).GetMethod("ButtonEventTutorial", All)!.Invoke(main, null);
        waitEnd = Time.realtimeSinceStartup + 45f;
        PlayerController? control = null;
        PlayerAvatar? avatar = null;
        var playerField = typeof(PlayerController).GetField("playerAvatarScript", All)!;
        while (avatar == null || control == null || !SemiFunc.RunIsTutorial())
        {
            if (Time.realtimeSinceStartup >= waitEnd)
                throw new TimeoutException("Tutorial avatar did not start.");
            yield return null;
            control = UnityEngine.Object.FindFirstObjectByType<PlayerController>();
            avatar = control != null ? (PlayerAvatar?)playerField.GetValue(control) : null;
        }
        yield return new WaitForSecondsRealtime(3f);
        var cosmetics = (PlayerCosmetics)typeof(PlayerAvatar).GetField("playerCosmetics", All)!.GetValue(avatar)!;
        var setup = typeof(PlayerCosmetics).GetMethod("SetupCosmetics", All)!;
        var crouch = typeof(PlayerController).GetMethod("CrouchOverride", All)!;
        var visual = cosmetics.playerAvatarVisuals;
        typeof(PlayerAvatarVisuals).GetMethod("ShowSelfOverride", All)!.Invoke(visual, new object[] { 75f });
        var gameCam = Camera.main;
        var cam = new GameObject("Outfit gallery camera").AddComponent<Camera>();
        if (gameCam != null)
            cam.CopyFrom(gameCam);
        cam.enabled = false;
        cam.orthographic = false;
        cam.allowHDR = true;
        cam.clearFlags = CameraClearFlags.Skybox;
        cam.nearClipPlane = .06f;
        cam.farClipPlane = 100f;
        cam.rect = new Rect(0, 0, 1, 1);
        var target = new RenderTexture(960, 1080, 24, RenderTextureFormat.ARGB32);
        cam.targetTexture = target;
        var image = new Texture2D(target.width, target.height, TextureFormat.RGB24, false);
        var position = visual.transform.position;
        var lights = FindObjectsByType<Light>(FindObjectsSortMode.None);
        var sceneLights = lights.Where(light => light.isActiveAndEnabled && light.intensity > 0)
            .OrderBy(light => (light.transform.position - position).sqrMagnitude)
            .Select(light => $"{light.name} {light.type} {light.transform.position:F2} range={light.range:F2} intensity={light.intensity:F2}");
        File.WriteAllLines(Path.Combine(dir, "lighting.txt"),
            new[] { $"Avatar spawn {position:F2}, forward {visual.transform.forward:F2}; main camera: {gameCam?.name}" }.Concat(sceneLights.Take(45)));

        foreach (var light in lights)
        {
            if (light.name == "Flashlight Light")
                light.enabled = false;
            else
                light.shadowStrength *= .45f;
        }
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
        RenderSettings.ambientIntensity = 1f;
        RenderSettings.ambientLight = new Color(.73f, .74f, .75f);
        var fill = new GameObject("Soft gallery fill").AddComponent<Light>();
        fill.type = LightType.Directional;
        fill.intensity = .48f;
        fill.shadows = LightShadows.None;
        var bounce = new GameObject("Soft gallery bounce").AddComponent<Light>();
        bounce.type = LightType.Directional;
        bounce.intensity = .24f;
        bounce.shadows = LightShadows.None;

        foreach (var item in sets.Where(item => item.Item4 == "winter"))
        {
            setup.Invoke(cosmetics, new object[] { false, false, item.Item1 });
            yield return new WaitForSecondsRealtime(1.5f);
            yield return new WaitForEndOfFrame();
            var pieces = VerifyOutfit(cosmetics, item.Item2, item.Item3);
            var leftSleeve = pieces.Single(renderer => renderer.name is "Left Sleeve" || renderer.name.EndsWith("sleeve-left", StringComparison.Ordinal));
            var rightSleeve = pieces.Single(renderer => renderer.name is "Right Sleeve" || renderer.name.EndsWith("sleeve-right", StringComparison.Ordinal));
            var leftShoe = pieces.Single(renderer => renderer.name == "Winter boot-left");
            var rightShoe = pieces.Single(renderer => renderer.name == "Winter boot-right");
            if (!ReferenceEquals(leftShoe.sharedMaterial.mainTexture, rightShoe.sharedMaterial.mainTexture))
                throw new InvalidOperationException("The mirrored shoes do not use the same source texture.");
            foreach (bool compressed in new[] { false, true })
            {
                crouch.Invoke(control, new object[] { compressed ? 5f : 0f });
                yield return new WaitForSecondsRealtime(1.3f);
                yield return new WaitForEndOfFrame();
                var expected = compressed ? PlayerAvatarVisuals.Pose.Crouch : PlayerAvatarVisuals.Pose.Stand;
                if (visual.currentPose != expected)
                    throw new InvalidOperationException($"Expected {expected}, got {visual.currentPose}.");
                foreach (int angle in new[] { -36, 0, 36 })
                    Capture(dir, compressed ? "crouch" : "stand", angle, new Vector3(-5f, 0f, 0f), Vector3.right,
                        cam, target, image, visual, fill, bounce, leftSleeve, rightSleeve, leftShoe, rightShoe, compressed);
            }
        }

        File.WriteAllText(Path.Combine(dir, "done.txt"), "PASS");
        Logger.LogInfo("Mirrored New Year Bee pair verified in standing and crouching poses.");
        Application.Quit();
    }

    private static bool IsOurAsset(CosmeticAsset asset) =>
        asset != null && asset.name.StartsWith("BoobeesSuits_", StringComparison.Ordinal);

    private static List<int> Indices(MetaManager meta, string prefix, int count)
    {
        var found = meta.cosmeticAssets.Select((asset, index) => (asset, index))
            .Where(p => IsOurAsset(p.asset) && p.asset.assetName.StartsWith(prefix, StringComparison.Ordinal)).ToArray();
        if (found.Length != count || found.Select(p => p.asset.type).Distinct().Count() != count)
            throw new InvalidOperationException($"Missing or conflicting slots in {prefix}.");
        return found.Select(p => p.index).ToList();
    }

    private static Renderer[] VerifyOutfit(PlayerCosmetics cosmetics, string[] names, string[] other)
    {
        var renderers = cosmetics.playerAvatarVisuals.animBotRoot.GetComponentsInChildren<Renderer>(true);
        var active = renderers.Where(r => r.enabled && r.gameObject.activeInHierarchy && !r.forceRenderingOff).ToArray();
        var pieces = names.Select(name =>
        {
            var matching = active.Where(r => r.name == name).ToArray();
            if (matching.Length != 1 || matching[0].sharedMaterial?.mainTexture == null)
                throw new InvalidOperationException($"Expected one textured piece named {name}, found {matching.Length}.");
            return matching[0];
        }).ToArray();
        if (active.Any(r => other.Contains(r.name)))
            throw new InvalidOperationException("Previous costume stayed equipped during switch.");
        var upper = cosmetics.cosmeticParents.Find(p => p.cosmeticType == SemiFunc.CosmeticType.BodyTop).parent;
        if (!pieces.Single(r => r.name == "Wings" || r.name.EndsWith(" wings", StringComparison.Ordinal)).transform.IsChildOf(upper))
            throw new InvalidOperationException("Wings did not mount on the torso.");
        return pieces;
    }

    private static void Capture(string dir, string outfit, int angle, Vector3 floor, Vector3 facing, Camera cam, RenderTexture target,
        Texture2D image, PlayerAvatarVisuals visual, Light fill, Light bounce, Renderer leftSleeve, Renderer rightSleeve,
        Renderer leftShoe, Renderer rightShoe, bool compressed)
    {
        var root = visual.transform;
        var model = visual.animBotRoot.GetComponentsInChildren<Renderer>(true);
        var original = model.Select(renderer => renderer.shadowCastingMode).ToArray();
        var previousTarget = RenderTexture.active;
        var originalPosition = root.position;
        var originalRotation = root.rotation;
        var transforms = visual.animBotRoot.GetComponentsInChildren<Transform>(true);
        var leftArm = transforms.Single(bone => bone.name == "code_arm_l");
        var rightArm = transforms.Single(bone => bone.name == "code_arm_r");
        var leftRotation = leftArm.localRotation;
        var rightRotation = rightArm.localRotation;
        try
        {
            root.SetPositionAndRotation(floor, Quaternion.LookRotation(facing, Vector3.up));
            var lowerLeft = -root.up - root.right * .29f + root.forward * .065f;
            var lowerRight = -root.up + root.right * .29f + root.forward * .065f;
            leftArm.rotation = Quaternion.FromToRotation(leftSleeve.bounds.center - leftArm.position, lowerLeft) * leftArm.rotation;
            rightArm.rotation = Quaternion.FromToRotation(rightSleeve.bounds.center - rightArm.position, lowerRight) * rightArm.rotation;
            if (leftSleeve.bounds.center.y >= leftArm.position.y - .12f || rightSleeve.bounds.center.y >= rightArm.position.y - .12f)
                throw new InvalidOperationException("The sleeve pose did not reach the lower arm position.");
            var center = root.position + root.up * (compressed ? .56f : .99f);
            var direction = Quaternion.AngleAxis(angle, root.up) * root.forward;
            var cameraDirection = (direction + root.up * .07f).normalized;
            float distance = 3.25f;
            if (Physics.Raycast(center, cameraDirection, out var wall, distance, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                distance = Mathf.Clamp(wall.distance - .14f, 1.05f, distance);
            cam.fieldOfView = 2f * Mathf.Atan((compressed ? .87f : 1.2f) / distance) * Mathf.Rad2Deg;
            cam.transform.position = center + cameraDirection * distance;
            cam.transform.rotation = Quaternion.LookRotation(center - cam.transform.position, root.up);
            if (angle == 0)
            {
                float left = cam.WorldToViewportPoint(leftShoe.bounds.center).x;
                float right = cam.WorldToViewportPoint(rightShoe.bounds.center).x;
                if (left <= .5f || right >= .5f)
                    throw new InvalidOperationException("The front view did not show the donor shoe on the right.");
                File.WriteAllText(Path.Combine(dir, $"{outfit}-shoe-positions.txt"), $"Donor FootLeft x={left:F4}; mirrored FootRight x={right:F4}");
            }
            fill.transform.rotation = Quaternion.LookRotation(-facing - root.up * .22f + root.right * .12f);
            bounce.transform.rotation = Quaternion.LookRotation(-facing - root.up * .05f - root.right * .5f);
            foreach (var renderer in model)
            {
                cam.cullingMask |= 1 << renderer.gameObject.layer;
                if (renderer.shadowCastingMode == UnityEngine.Rendering.ShadowCastingMode.ShadowsOnly)
                    renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
            }
            cam.Render();
            RenderTexture.active = target;
            image.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0);
            File.WriteAllBytes(Path.Combine(dir, $"{outfit}-{angle}.png"), ImageConversion.EncodeToPNG(image));
        }
        finally
        {
            root.SetPositionAndRotation(originalPosition, originalRotation);
            leftArm.localRotation = leftRotation;
            rightArm.localRotation = rightRotation;
            RenderTexture.active = previousTarget;
            for (int i = 0; i < model.Length; i++)
                model[i].shadowCastingMode = original[i];
        }
    }
}
