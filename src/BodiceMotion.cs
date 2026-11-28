using UnityEngine;

namespace BoobeesSuits;

[DefaultExecutionOrder(1000)]
internal sealed class BodiceMotion : MonoBehaviour
{
    // Cast-Iron Boo-Bee's Statue profile from Boobees Valuables 0.2.15.
    private const float MaximumOffset = 0.060f;
    private const float VisualMultiplier = 1.35f;
    private const float LobeScale = 0.68f;
    private static readonly Vector3 LeftPoint = new(-0.120f, 0.12f, 0.35f);
    private static readonly Vector3 RightPoint = new(0.120f, 0.12f, 0.35f);

    [SerializeField] private Transform left = null!;
    [SerializeField] private Transform right = null!;
    private Vector3 previousLeftPoint;
    private Vector3 previousRightPoint;
    private Vector3 previousLeftVelocity;
    private Vector3 previousRightVelocity;
    private Vector2 offset;
    private Vector2 previousOffset;
    private Vector2 speed;
    private PlayerAvatar? avatar;
    private float remainder;
    private int samples;

    internal void Configure(Transform leftCloth, Transform rightCloth)
    {
        left = leftCloth;
        right = rightCloth;
    }

    private void OnDisable()
    {
        samples = 0;
        remainder = 0f;
        offset = previousOffset = speed = Vector2.zero;
        if (left != null)
            left.localPosition = Vector3.zero;
        if (right != null)
            right.localPosition = Vector3.zero;
    }

    private bool IsRemote
    {
        get
        {
            var local = SemiFunc.PlayerAvatarLocal();
            return avatar != null && local != null && avatar != local;
        }
    }

    private void Start() => avatar = GetComponentInParent<PlayerAvatarVisuals>()?.playerAvatar;

    private void LateUpdate()
    {
        if (IsRemote)
            Simulate(Time.deltaTime, Time.fixedDeltaTime);
        else
            Tick(transform.TransformPoint(LeftPoint), transform.TransformPoint(RightPoint),
                Time.deltaTime, Time.fixedDeltaTime);
    }

    internal void RemoteImpulse(float leftKick, float rightKick)
    {
        if (IsRemote && isActiveAndEnabled)
            speed += new Vector2(leftKick, rightKick);
    }

    internal void Tick(Vector3 leftPoint, Vector3 rightPoint, float seconds, float step)
    {
        if (seconds <= 0f || step <= 0f)
            return;
        Vector3 leftMovement = leftPoint - previousLeftPoint;
        Vector3 rightMovement = rightPoint - previousRightPoint;
        previousLeftPoint = leftPoint;
        previousRightPoint = rightPoint;
        // Treat the first frame and teleports as a fresh sample instead of an impact.
        if (samples == 0 || seconds > 0.12f ||
            Mathf.Max(leftMovement.sqrMagnitude, rightMovement.sqrMagnitude) > 0.85f * 0.85f)
        {
            ResetSpring();
            samples = 1;
            return;
        }

        Vector3 leftVelocity = leftMovement / seconds;
        Vector3 rightVelocity = rightMovement / seconds;
        if (samples == 2)
        {
            speed.x += MotionKick(transform.InverseTransformDirection(leftVelocity - previousLeftVelocity), -0.6f, seconds);
            speed.y += MotionKick(transform.InverseTransformDirection(rightVelocity - previousRightVelocity), 0.6f, seconds);
        }
        samples = 2;
        previousLeftVelocity = leftVelocity;
        previousRightVelocity = rightVelocity;
        Simulate(seconds, step);
    }

    private void Simulate(float seconds, float step)
    {
        if (seconds <= 0f || step <= 0f)
            return;
        remainder += Mathf.Min(seconds, 0.12f);
        while (remainder + 0.000001f >= step)
        {
            remainder = Mathf.Max(0f, remainder - step);
            previousOffset = offset;
            Advance(ref offset.x, ref speed.x, step);
            Advance(ref offset.y, ref speed.y, step);
        }
        Draw(Vector2.Lerp(previousOffset, offset, remainder / step));
    }

    private void ResetSpring()
    {
        remainder = 0f;
        offset = previousOffset = speed = Vector2.zero;
        Draw(Vector2.zero);
    }

    private void Draw(Vector2 pose)
    {
        pose *= VisualMultiplier * LobeScale;
        left.localPosition = Vector3.up * pose.x;
        right.localPosition = Vector3.up * pose.y;
    }

    private static float MotionKick(Vector3 change, float side, float elapsed)
    {
        float length = change.magnitude;
        float threshold = 11f * elapsed;
        if (length <= threshold || length > 18f)
            return 0f;
        // The statue faces -Z, while Semibot faces +Z.
        float vertical = -change.y - 0.6f * change.z + side * change.x;
        return vertical * (1f - threshold / length) * 0.45f;
    }

    internal static void Advance(ref float displacement, ref float velocity, float step)
    {
        velocity = Mathf.Clamp(velocity, -2f, 2f);
        velocity -= (250f * displacement + 15f * velocity) * step;
        displacement = Mathf.Clamp(displacement + velocity * step, -MaximumOffset, MaximumOffset);
        if (Mathf.Abs(displacement) < 0.00018f && Mathf.Abs(velocity) < 0.003f)
            displacement = velocity = 0f;
    }
}
