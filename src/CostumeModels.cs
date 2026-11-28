using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using UnityEngine;

namespace BoobeesSuits;

internal sealed class CostumeModels
{
    private readonly struct Shape
    {
        internal readonly Mesh Mesh;
        internal readonly Material Material;

        internal Shape(Mesh mesh, Material material)
        {
            Mesh = mesh;
            Material = material;
        }
    }
    private readonly Dictionary<string, (Shape Stand, Shape Crouch)> pieces = new(StringComparer.Ordinal);
    private readonly string prefix;

    internal CostumeModels(Shader shader, string resourcePrefix, int count)
    {
        prefix = resourcePrefix;
        using var compressed = new GZipStream(SuitModels.Resource($"{prefix}.bin.gz"), CompressionMode.Decompress);
        using var reader = new BinaryReader(compressed);
        if (reader.ReadUInt32() != 0x32534242 || reader.ReadByte() != count)
            throw new InvalidDataException($"Invalid {prefix} mesh pack.");

        var textures = new Dictionary<string, Texture2D>(StringComparer.Ordinal);
        for (int i = 0; i < count; i++)
        {
            string name = reader.ReadString();
            bool hasCrouch = reader.ReadBoolean();
            var stand = ReadShape(reader, shader, textures, name, compressed: false);
            var crouch = hasCrouch ? ReadShape(reader, shader, textures, name, compressed: true) : stand;
            pieces.Add(name, (stand, crouch));
        }
        if (compressed.ReadByte() != -1)
            throw new InvalidDataException($"Unexpected data after the {prefix} meshes.");
    }

    internal void Add(Transform parent, string name)
    {
        var (stand, crouch) = pieces[name];
        var piece = new GameObject($"{prefix} {name}");
        piece.transform.SetParent(parent, false);
        piece.AddComponent<MeshFilter>().sharedMesh = stand.Mesh;
        piece.AddComponent<MeshRenderer>().sharedMaterial = stand.Material;
        if (stand.Mesh != crouch.Mesh)
            piece.AddComponent<OutfitPose>().Configure(stand.Mesh, crouch.Mesh, stand.Material, crouch.Material);
    }

    private Shape ReadShape(
        BinaryReader reader, Shader shader, Dictionary<string, Texture2D> textures, string name, bool compressed)
    {
        var mesh = SuitModels.ReadMesh(reader, $"{prefix} {name}", usesAtlas: true, compressed: compressed);
        string materialName = $"{prefix}-{name}{(compressed ? "-crouch" : "")}.jpg";
        string textureName = (prefix, name) switch
        {
            ("Sneaker", "shoe-right") => "Sneaker-shoe-left.jpg",
            ("Winter", "sweater" or "abdomen") => $"Winter-{name}.jpg",
            ("Winter", "sleeve-right") => "Winter-sleeve-left.jpg",
            ("Winter", "boot-right") => "Winter-boot-left.jpg",
            _ => materialName
        };
        if (!textures.TryGetValue(textureName, out var texture))
        {
            texture = SuitModels.LoadTexture(textureName, linear: false);
            if (prefix == "Winter" && (name is "sweater" or "abdomen" || name.StartsWith("sleeve-", StringComparison.Ordinal)))
                texture.wrapMode = TextureWrapMode.Repeat;
            textures.Add(textureName, texture);
        }
        var material = SuitModels.Fabric(shader, materialName, texture);
        if (prefix == "Winter" && name == "hat")
        {
            material.SetTexture("_EmissionMap", SuitModels.LoadTexture("Winter-hat-emission.png", linear: true));
            material.SetColor("_EmissionColor", Color.white * 1.25f);
            material.EnableKeyword("_EMISSION");
        }
        return new Shape(mesh, material);
    }
}
