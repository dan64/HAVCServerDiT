using System.Text.Json.Serialization;

namespace HavcManager.Core.State;

/// <summary>
/// Local installation state (<install>\install.json, schema v1 — PHASE1_SPEC §4).
/// Written and read only by the manager; the bootstrap stays stateless.
/// The schema is additive: new fields must not break older managers.
/// </summary>
public sealed record InstallState
{
    [JsonPropertyName("schema")] public int Schema { get; init; } = 1;
    [JsonPropertyName("manager_version")] public string ManagerVersion { get; init; } = "";
    [JsonPropertyName("app_version")] public string AppVersion { get; init; } = "";
    [JsonPropertyName("installed_at")] public string? InstalledAt { get; init; }
    [JsonPropertyName("updated_at")] public string? UpdatedAt { get; init; }
    [JsonPropertyName("install_dir")] public string InstallDir { get; init; } = "";
    [JsonPropertyName("models_dir")] public string? ModelsDir { get; init; }
    [JsonPropertyName("runtime")] public RuntimeState? Runtime { get; init; }
    [JsonPropertyName("components")] public IReadOnlyList<string> Components { get; init; } = ["server", "gui"];
    [JsonPropertyName("dinov2")] public bool Dinov2 { get; init; }
    [JsonPropertyName("backend_default")] public string? BackendDefault { get; init; }
    [JsonPropertyName("last_verify")] public LastVerifyState? LastVerify { get; init; }
    [JsonPropertyName("previous")] public PreviousState? Previous { get; init; }
}

/// <summary>Runtime block of the state (as provisioned from the manifest).</summary>
public sealed record RuntimeState
{
    [JsonPropertyName("name")] public string Name { get; init; } = "";
    [JsonPropertyName("sha256")] public string Sha256 { get; init; } = "";
    [JsonPropertyName("python")] public string Python { get; init; } = "";
}

/// <summary>Outcome of the last havc-doctor verification.</summary>
public sealed record LastVerifyState
{
    [JsonPropertyName("ts")] public string Ts { get; init; } = "";
    [JsonPropertyName("ok")] public bool Ok { get; init; }
    [JsonPropertyName("app_version")] public string AppVersion { get; init; } = "";
}

/// <summary>Snapshot kept for rollback (previous wheel + digest).</summary>
public sealed record PreviousState
{
    [JsonPropertyName("app_version")] public string AppVersion { get; init; } = "";
    [JsonPropertyName("wheel")] public string Wheel { get; init; } = "";
    [JsonPropertyName("sha256")] public string Sha256 { get; init; } = "";
}
