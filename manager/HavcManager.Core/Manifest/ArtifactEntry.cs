using System.Text.Json.Serialization;

namespace HavcManager.Core.Manifest;

/// <summary>
/// One downloadable artifact listed in the manifest (wheel, asset, weight, tool).
/// Every download is verified against <see cref="Sha256"/> before use (PHASE1_SPEC §10).
/// </summary>
public sealed record ArtifactEntry
{
    [JsonPropertyName("name")] public string Name { get; init; } = "";
    [JsonPropertyName("url")] public string Url { get; init; } = "";
    [JsonPropertyName("sha256")] public string Sha256 { get; init; } = "";
    [JsonPropertyName("size")] public long Size { get; init; }
    [JsonPropertyName("kind")] public string? Kind { get; init; }
    [JsonPropertyName("install")] public string? Install { get; init; }
    [JsonPropertyName("target")] public string? Target { get; init; }
}
