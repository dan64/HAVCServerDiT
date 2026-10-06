namespace HavcManager.Core.Manifest;

/// <summary>
/// One artifact the manager fetches before the bootstrap run
/// (PHASE1_SPEC §6.2 step 4): runtime archive, project wheel, asset wheels.
/// </summary>
public sealed record PlannedDownload(
    string Name,
    string Url,
    string Sha256,
    long Size,
    string CacheSubfolder);

public static class DownloadPlan
{
    /// <summary>
    /// Runtime archive and wheels go to the cache root (the bootstrap reuses
    /// the archive from <install>\cache), asset wheels go to cache\assets
    /// which is passed to the bootstrap as --assets-dir.
    /// (weights/tools lists are not fetched by the manager: the bootstrap
    /// downloads them itself with the same cache.)
    /// </summary>
    public static IReadOnlyList<PlannedDownload> FromManifest(ReleaseManifest manifest)
    {
        var downloads = new List<PlannedDownload>();
        if (manifest.Runtime is { } runtime && runtime.Url.Length > 0)
            downloads.Add(new PlannedDownload(runtime.Name, runtime.Url, runtime.Sha256, 0, ""));
        foreach (var wheel in manifest.Wheels)
            downloads.Add(new PlannedDownload(wheel.Name, wheel.Url, wheel.Sha256, wheel.Size, ""));
        foreach (var asset in manifest.Assets)
            downloads.Add(new PlannedDownload(asset.Name, asset.Url, asset.Sha256, asset.Size, "assets"));
        return downloads;
    }
}
