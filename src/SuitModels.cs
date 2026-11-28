using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using UnityEngine;

namespace BoobeesSuits;

internal sealed class SuitModels
{
    private readonly Dictionary<string, (Mesh Stand, Mesh Crouch)> meshes = new(StringComparer.Ordinal);
    private readonly Material patterned;
    private readonly Material sleeve;
    private readonly Material sock;

    internal SuitModels(Shader shader)
    {
        using var compressed = new GZipStream(Resource("Outfit.bin.gz"), CompressionMode.Decompress);
        using var reader = new BinaryReader(compressed);
        if (reader.ReadUInt32() != 0x31534242 || reader.ReadByte() != 10)
            throw new InvalidDataException("Invalid Boobees outfit mesh pack.");

        for (int i = 0; i < 10; i++)
        {
            string name = reader.ReadString();
            bool usesAtlas = !name.EndsWith("Sleeve", StringComparison.Ordinal) &&
                !name.EndsWith("Sock", StringComparison.Ordinal);
            meshes.Add(name, (ReadMesh(reader, name, usesAtlas, compressed: false),
                ReadMesh(reader, name, usesAtlas, compressed: true)));
        }
        if (compressed.ReadByte() != -1)
            throw new InvalidDataException("Unexpected data after the outfit meshes.");

        patterned = Fabric(shader, "Fabric.png");
        patterned.SetTexture("_BumpMap", LoadTexture("FabricNormal.png", linear: true));
        patterned.SetFloat("_BumpScale", 0.75f);
        patterned.EnableKeyword("_NORMALMAP");
        sleeve = Fabric(shader, "SleeveFabric.png");
        sock = Fabric(shader, "SockFabric.png");
    }

    internal void Add(Transform parent, string name)
    {
        var pair = meshes[name];
        var piece = new GameObject(name);
        piece.transform.SetParent(parent, false);
        piece.AddComponent<OutfitPose>().Configure(pair.Stand, pair.Crouch);
        if (name == "Bodice")
        {
            AddSpringBodice(piece, pair.Stand, pair.Crouch);
            return;
        }
        if (name is "Hood Lower" or "Hem")
        {
            AddSeam(piece, pair.Stand, pair.Crouch, name == "Hood Lower");
            return;
        }

        var filter = piece.AddComponent<MeshFilter>();
        filter.sharedMesh = pair.Stand;
        piece.AddComponent<MeshRenderer>().sharedMaterial = name.EndsWith("Sleeve", StringComparison.Ordinal)
            ? sleeve
            : name.EndsWith("Sock", StringComparison.Ordinal) ? sock : patterned;
    }

    private void AddSpringBodice(GameObject piece, Mesh stand, Mesh crouch)
    {
        var root = piece.transform;
        var left = new GameObject("Left Cloth Spring").transform;
        var right = new GameObject("Right Cloth Spring").transform;
        left.SetParent(root, false);
        right.SetParent(root, false);

        var renderer = piece.AddComponent<SkinnedMeshRenderer>();
        renderer.rootBone = root;
        renderer.bones = new[] { root, left, right };
        renderer.quality = SkinQuality.Bone4;
        renderer.sharedMesh = stand;
        renderer.sharedMaterial = patterned;
        Bounds bounds = stand.bounds;
        bounds.Encapsulate(crouch.bounds);
        renderer.localBounds = bounds;
        piece.AddComponent<BodiceMotion>().Configure(left, right);
    }

    private void AddSeam(GameObject piece, Mesh stand, Mesh crouch, bool lowerHood)
    {
        var edge = new GameObject("Cloth overlap").transform;
        edge.SetParent(piece.transform, false);
        var renderer = piece.AddComponent<SkinnedMeshRenderer>();
        renderer.rootBone = piece.transform;
        renderer.bones = new[] { piece.transform, edge };
        renderer.sharedMesh = stand;
        renderer.sharedMaterial = patterned;
        Bounds bounds = stand.bounds;
        bounds.Encapsulate(crouch.bounds);
        renderer.localBounds = bounds;
        piece.AddComponent<ClothSeam>().Configure(edge, lowerHood);
    }

    internal static Mesh ReadMesh(BinaryReader reader, string name, bool usesAtlas, bool compressed)
    {
        int count = reader.ReadInt32();
        int indexCount = reader.ReadInt32();
        if (count < 3 || count > ushort.MaxValue || indexCount < 3 || indexCount > 240000 || indexCount % 3 != 0)
            throw new InvalidDataException($"Invalid mesh dimensions for {name}.");

        var positions = new Vector3[count];
        var normals = new Vector3[count];
        var uvs = new Vector2[count];
        for (int i = 0; i < count; i++)
        {
            positions[i] = ReadVector(reader);
            normals[i] = ReadVector(reader);
            uvs[i] = new Vector2(reader.ReadSingle(), reader.ReadSingle());
        }
        var triangles = new int[indexCount];
        for (int i = 0; i < indexCount; i++)
        {
            triangles[i] = reader.ReadUInt16();
            if (triangles[i] >= count)
                throw new InvalidDataException($"Invalid triangle index in {name}.");
        }

        var mesh = new Mesh { name = name + (compressed ? " · Crouch" : " · Stand"),
            vertices = positions, normals = normals, uv = uvs };
        mesh.SetTriangles(triangles, 0);
        if (usesAtlas)
            mesh.RecalculateTangents();
        if (name == "Bodice")
            BindCloth(mesh, positions);
        if (name is "Hood Lower" or "Hem")
            BindSeam(mesh, positions, name == "Hood Lower", compressed);
        mesh.UploadMeshData(true);
        return mesh;
    }

    private static void BindSeam(Mesh mesh, Vector3[] positions, bool collar, bool compressed)
    {
        var weights = new BoneWeight[positions.Length];
        for (int i = 0; i < weights.Length; i++)
        {
            float y = positions[i].y;
            float edge = collar ? 1f - Ramp(-.197f, -.056f, y)
                : compressed ? 0f : 1f - Ramp(-.29f, -.105f, y);
            weights[i] = edge > .5f
                ? new BoneWeight { boneIndex0 = 1, weight0 = edge, boneIndex1 = 0, weight1 = 1f - edge }
                : new BoneWeight { boneIndex0 = 0, weight0 = 1f - edge, boneIndex1 = 1, weight1 = edge };
        }
        mesh.bindposes = new[] { Matrix4x4.identity, Matrix4x4.identity };
        mesh.boneWeights = weights;
        var bounds = mesh.bounds;
        bounds.Expand(.38f);
        mesh.bounds = bounds;
    }

    private static void BindCloth(Mesh mesh, Vector3[] positions)
    {
        Bounds original = mesh.bounds;
        var weights = new BoneWeight[positions.Length];
        for (int i = 0; i < positions.Length; i++)
        {
            Vector3 p = positions[i];
            float height = Mathf.InverseLerp(original.min.y, original.max.y, p.y);
            // Cast-Iron Boo-Bee uses squared compact ellipsoid weights. Fit those fields to
            // the bodice, tapering to zero at the neck and hem and behind the fabric front.
            float edge = Ramp(0.11f, 0.30f, height) * (1f - Ramp(0.74f, 0.94f, height)) *
                Ramp(0.258f, 0.326f, p.z);
            float left = edge * LobeWeight(p, height, -0.116f);
            float right = edge * LobeWeight(p, height, 0.116f);
            weights[i] = SkinWeight(left, right);
        }
        // Each spring's rest position and orientation is the bodice origin.
        mesh.bindposes = new[] { Matrix4x4.identity, Matrix4x4.identity, Matrix4x4.identity };
        mesh.boneWeights = weights;
        original.Expand(0.12f);
        mesh.bounds = original;
    }

    private static float LobeWeight(Vector3 vertex, float height, float center)
    {
        var distance = new Vector3((vertex.x - center) / 0.175f, (height - 0.62f) / 0.59f,
            (vertex.z - 0.361f) / 0.140f);
        float strength = Mathf.Max(0f, 1f - distance.sqrMagnitude);
        return strength * strength;
    }

    private static BoneWeight SkinWeight(float left, float right)
    {
        // Unity expects weights in descending order and the undriven remainder on the root.
        int first = 0, second = 1, third = 2;
        float a = 1f - left - right, b = left, c = right;
        if (a < b)
            (a, b, first, second) = (b, a, second, first);
        if (b < c)
            (b, c, second, third) = (c, b, third, second);
        if (a < b)
            (a, b, first, second) = (b, a, second, first);
        return new BoneWeight { boneIndex0 = first, boneIndex1 = second, boneIndex2 = third,
            weight0 = a, weight1 = b, weight2 = c };
    }

    private static float Ramp(float begin, float end, float value) =>
        Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(begin, end, value));

    private static Vector3 ReadVector(BinaryReader reader) =>
        new(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());

    internal static Material Fabric(Shader shader, string name) =>
        Fabric(shader, name, LoadTexture(name, linear: false));

    internal static Material Fabric(Shader shader, string name, Texture2D texture)
    {
        var material = new Material(shader) { name = name, mainTexture = texture };
        material.SetFloat("_Glossiness", 0.13f);
        return material;
    }

    internal static Texture2D LoadTexture(string name, bool linear)
    {
        using Stream input = Resource(name);
        using var buffer = new MemoryStream();
        input.CopyTo(buffer);
        var texture = new Texture2D(2, 2, TextureFormat.RGBA32, true, linear)
        {
            name = name,
            wrapMode = TextureWrapMode.Clamp,
            anisoLevel = 4
        };
        if (!ImageConversion.LoadImage(texture, buffer.ToArray(), true))
            throw new InvalidDataException($"Invalid outfit texture {name}.");
        return texture;
    }

    internal static Stream Resource(string name) =>
        typeof(SuitModels).Assembly.GetManifestResourceStream($"BoobeesSuits.Assets.{name}")
        ?? throw new InvalidDataException($"Missing outfit asset {name}.");
}
