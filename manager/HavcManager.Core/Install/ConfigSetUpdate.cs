using System.IO;
using System.IO.Compression;

namespace HavcManager.Core.Install;

/// <summary>
/// Compares the pipeline configs packaged in a wheel (`havc/configs/*.json`)
/// with the installed copies (`&lt;install&gt;\config`, 2026-10-06). Only files
/// that exist on both sides and differ are reported: missing files are created
/// by the bootstrap without asking, and files the user added locally are never
/// touched. The manager asks for confirmation when this list is non-empty and
/// passes `--update-configs` to the bootstrap on "yes" (the bootstrap keeps
/// the previous file as `&lt;name&gt;.json.bak`).
/// </summary>
public static class ConfigSetUpdate
{
    public const string WheelPrefix = "havc/configs/";

    /// <summary>File names (no directory) of the installed configs that differ from the wheel.</summary>
    public static IReadOnlyList<string> DifferingConfigs(string wheelPath, string installDir)
    {
        var differing = new List<string>();
        if (!File.Exists(wheelPath))
            return differing;
        string configDir = Path.Combine(installDir, "config");
        using var zip = ZipFile.OpenRead(wheelPath);
        foreach (ZipArchiveEntry entry in zip.Entries)
        {
            if (!entry.FullName.StartsWith(WheelPrefix, StringComparison.OrdinalIgnoreCase))
                continue;
            string name = entry.Name;
            if (name.Length == 0 || !name.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
                continue;
            string local = Path.Combine(configDir, name);
            if (!File.Exists(local))
                continue; // new config: the bootstrap copies it, no confirmation needed
            using Stream stream = entry.Open();
            using var memory = new MemoryStream();
            stream.CopyTo(memory);
            if (!memory.ToArray().AsSpan().SequenceEqual(File.ReadAllBytes(local)))
                differing.Add(name);
        }
        differing.Sort(StringComparer.OrdinalIgnoreCase);
        return differing;
    }
}
