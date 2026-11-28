using HarmonyLib;

namespace BoobeesSuits;

[HarmonyPatch]
internal static class RemoteBodiceMotion
{
    // These game events already reach observers through the native avatar.
    // Position deltas on the receiving client are interpolated and cannot reliably detect impacts.
    [HarmonyPostfix, HarmonyPatch(typeof(PlayerCosmetics), nameof(PlayerCosmetics.CosmeticSpringJump))]
    private static void Jump(PlayerCosmetics __instance) => Impulse(__instance, -1.45f, -1.45f);

    [HarmonyPostfix, HarmonyPatch(typeof(PlayerCosmetics), nameof(PlayerCosmetics.CosmeticSpringLand))]
    private static void Land(PlayerCosmetics __instance) => Impulse(__instance, -1.85f, -1.85f);

    [HarmonyPostfix, HarmonyPatch(typeof(PlayerCosmetics), nameof(PlayerCosmetics.CosmeticSpringStandToCrouch))]
    private static void Crouch(PlayerCosmetics __instance) => Impulse(__instance, .75f, .75f);

    [HarmonyPostfix, HarmonyPatch(typeof(PlayerCosmetics), nameof(PlayerCosmetics.CosmeticSpringCrouchToStand))]
    private static void Stand(PlayerCosmetics __instance) => Impulse(__instance, -.75f, -.75f);

    [HarmonyPostfix, HarmonyPatch(typeof(PlayerCosmetics), nameof(PlayerCosmetics.CosmeticSpringFootLeftDown))]
    private static void LeftStep(PlayerCosmetics __instance) => Impulse(__instance, -.28f, -.14f);

    [HarmonyPostfix, HarmonyPatch(typeof(PlayerCosmetics), nameof(PlayerCosmetics.CosmeticSpringFootRightDown))]
    private static void RightStep(PlayerCosmetics __instance) => Impulse(__instance, -.14f, -.28f);

    private static void Impulse(PlayerCosmetics owner, float left, float right)
    {
        var rig = owner.playerAvatarVisuals?.animBotRoot;
        if (rig != null)
            rig.GetComponentInChildren<BodiceMotion>()?.RemoteImpulse(left, right);
    }
}
