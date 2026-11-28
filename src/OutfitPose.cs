using UnityEngine;

namespace BoobeesSuits;

internal sealed class OutfitPose : MonoBehaviour
{
    [SerializeField] private Mesh stand = null!;
    [SerializeField] private Mesh crouch = null!;
    [SerializeField] private Material? standMaterial;
    [SerializeField] private Material? crouchMaterial;
    private MeshFilter? filter;
    private SkinnedMeshRenderer? skinned;
    private MeshRenderer? meshRenderer;
    private PlayerAvatarVisuals? avatar;

    internal void Configure(Mesh standing, Mesh crouching, Material? standingMaterial = null,
        Material? crouchingMaterial = null)
    {
        stand = standing;
        crouch = crouching;
        standMaterial = standingMaterial;
        crouchMaterial = crouchingMaterial;
    }

    private void Start()
    {
        avatar = GetComponentInParent<PlayerAvatarVisuals>();
        filter = GetComponent<MeshFilter>();
        skinned = GetComponent<SkinnedMeshRenderer>();
        if (standMaterial != null)
            meshRenderer = GetComponent<MeshRenderer>();
    }

    private void LateUpdate()
    {
        if (avatar == null)
            return;
        bool compressed = avatar.currentPose is PlayerAvatarVisuals.Pose.Crouch or PlayerAvatarVisuals.Pose.Crawl;
        Mesh pose = compressed ? crouch : stand;
        if (filter != null && filter.sharedMesh != pose)
            filter.sharedMesh = pose;
        if (skinned != null && skinned.sharedMesh != pose)
            skinned.sharedMesh = pose;
        if (meshRenderer != null)
        {
            Material? material = compressed ? crouchMaterial : standMaterial;
            if (meshRenderer.sharedMaterial != material)
                meshRenderer.sharedMaterial = material;
        }
    }
}
