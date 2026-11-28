using System.Collections.Generic;
using UnityEngine;

namespace BoobeesSuits;

internal sealed class FabricCoverage : MonoBehaviour
{
    [SerializeField] private SemiFunc.CosmeticType slot;
    private readonly List<Renderer> coveredPanels = new(2);
    private readonly List<Renderer> hiddenPanels = new(2);

    internal void Configure(SemiFunc.CosmeticType coveredSlot) => slot = coveredSlot;

    private void Start()
    {
        var avatar = GetComponentInParent<PlayerAvatarVisuals>();
        if (avatar == null || avatar.animBotRoot == null)
            return;

        foreach (var renderer in avatar.animBotRoot.GetComponentsInChildren<Renderer>(true))
        {
            if (Covers(renderer.name))
                coveredPanels.Add(renderer);
        }
        HidePanels();
    }

    private void OnEnable() => HidePanels();

    private bool Covers(string name) => slot switch
    {
        SemiFunc.CosmeticType.BodyTop => name is "mesh_body_top_sphere" or "mesh_body_top_flat",
        SemiFunc.CosmeticType.HeadBottomOverlay => name is "mesh_head_bot_sphere" or "mesh_head_bot_flat",
        SemiFunc.CosmeticType.BodyTopOverlay => name == "mesh_body_bot",
        _ => false
    };

    private void HidePanels()
    {
        foreach (var panel in coveredPanels)
        {
            if (panel != null && !panel.forceRenderingOff)
            {
                panel.forceRenderingOff = true;
                hiddenPanels.Add(panel);
            }
        }
    }

    private void OnDisable()
    {
        foreach (var panel in hiddenPanels)
            if (panel != null)
                panel.forceRenderingOff = false;
        hiddenPanels.Clear();
    }
}
