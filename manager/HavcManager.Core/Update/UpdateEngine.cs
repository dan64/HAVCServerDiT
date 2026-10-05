using HavcManager.Core.Manifest;
using HavcManager.Core.State;

namespace HavcManager.Core.Update;

public enum UpdateClassification
{
    UpToDate,
    UpdateAvailable,
    RebuildRequired,
}

/// <summary>
/// Update classification and cache helpers (PHASE1_SPEC §6.3). The run and the
/// rollback reuse <see cref="Install.InstallFlow"/>: an update is the normal
/// flow (the per-file sha256 check makes it incremental) and the rollback is a
/// repair run with the previous wheel.
/// </summary>
public static class UpdateEngine
{
    /// <summary>
    /// Classifies a manifest against the local state (§6.3 step 2):
    /// requires_env_rebuild blocks with the manual procedure (§6.7).
    /// </summary>
    public static UpdateClassification Classify(ReleaseManifest manifest, InstallState state)
    {
        if (manifest.RequiresEnvRebuild)
            return UpdateClassification.RebuildRequired;
        return string.Equals(manifest.AppVersion, state.AppVersion, StringComparison.OrdinalIgnoreCase)
            ? UpdateClassification.UpToDate
            : UpdateClassification.UpdateAvailable;
    }

    /// <summary>
    /// Finds `havc-&lt;version&gt;-*.whl` in the cache (the wheels of the last
    /// two versions are kept there — PHASE1_SPEC §4). Null when missing.
    /// </summary>
    public static string? FindCachedWheel(string cacheDir, string? appVersion)
    {
        if (string.IsNullOrEmpty(appVersion) || !Directory.Exists(cacheDir))
            return null;
        return Directory
            .EnumerateFiles(cacheDir, $"havc-{appVersion}-*.whl")
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .FirstOrDefault();
    }
}
