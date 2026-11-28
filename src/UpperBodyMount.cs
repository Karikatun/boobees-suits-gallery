using HarmonyLib;
using UnityEngine;

namespace BoobeesSuits;

[HarmonyPatch(typeof(PlayerCosmetics), "InstantiateCosmetic")]
internal sealed class UpperBodyMount : MonoBehaviour
{
    [HarmonyPostfix]
    private static void FollowUpperBody(PlayerCosmetics __instance, GameObject? __result)
    {
        if (__result == null || !__result.TryGetComponent<UpperBodyMount>(out _))
            return;

        // Keep torso-mounted accessories inside their equipped item so the game removes them together.
        var slot = __instance.cosmeticParents.Find(p => p.cosmeticType == SemiFunc.CosmeticType.BodyTop);
        if (slot?.parent != null)
            __result.transform.SetParent(slot.parent, false);
    }
}
