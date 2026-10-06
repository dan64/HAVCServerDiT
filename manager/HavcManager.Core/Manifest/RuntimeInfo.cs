using System.Text.Json.Serialization;

namespace HavcManager.Core.Manifest;

/// <summary>The pinned Python runtime provisioned by the bootstrap (decision D5).</summary>
public sealed record RuntimeInfo
{
    [JsonPropertyName("name")] public string Name { get; init; } = "";
    [JsonPropertyName("url")] public string Url { get; init; } = "";
    [JsonPropertyName("sha256")] public string Sha256 { get; init; } = "";
    [JsonPropertyName("python")] public string Python { get; init; } = "";
    [JsonPropertyName("kind")] public string? Kind { get; init; }
    [JsonPropertyName("mirror_of")] public string? MirrorOf { get; init; }
}
