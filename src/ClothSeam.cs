using UnityEngine;

namespace BoobeesSuits;

internal sealed class ClothSeam : MonoBehaviour
{
    [SerializeField] private Transform edge = null!;
    [SerializeField] private bool collar;
    private PlayerAvatarVisuals? avatar;
    private Transform? anchor;

    internal void Configure(Transform edgeBone, bool lowerHood)
    {
        edge = edgeBone;
        collar = lowerHood;
    }

    private void Start()
    {
        avatar = GetComponentInParent<PlayerAvatarVisuals>();
        var slot = collar ? SemiFunc.CosmeticType.BodyTop : SemiFunc.CosmeticType.BodyBottom;
        anchor = avatar?.playerCosmetics?.cosmeticParents.Find(p => p.cosmeticType == slot)?.parent;
    }

    private void LateUpdate()
    {
        if (avatar == null || anchor == null)
            return;

        bool compressed = avatar.currentPose is PlayerAvatarVisuals.Pose.Crouch or PlayerAvatarVisuals.Pose.Crawl;
        // The lower body vanishes in the flattened crouch rig. The short hem follows the torso there.
        if (!collar && (compressed || !anchor.gameObject.activeInHierarchy))
        {
            edge.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
            return;
        }
        // Neutral spacing from the native standing and crouching rigs.
        float height = collar ? (compressed ? .3624f : .3588f) : .2908f;
        edge.SetPositionAndRotation(anchor.TransformPoint(Vector3.up * height), anchor.rotation);
    }
}
