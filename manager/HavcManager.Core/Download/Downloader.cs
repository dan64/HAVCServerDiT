namespace HavcManager.Core.Download;

/// <summary>
/// Downloads artifacts into the install cache (<install>\cache\, original file
/// names) and verifies the SHA-256 digest before use; existing cache files are
/// reused when the digest matches (PHASE1_SPEC §6.2 step 4, §10).
/// </summary>
public sealed class Downloader
{
    /// <summary>
    /// Returns the local path of <paramref name="fileName"/> inside <paramref name="cacheDir"/>,
    /// downloading it from <paramref name="url"/> when missing or mismatching.
    /// TODO(M2): download to a temp file, verify sha256 + size, then move into place.
    /// </summary>
    public Task<string> GetAsync(
        string url,
        string fileName,
        string cacheDir,
        string expectedSha256,
        long expectedSize,
        CancellationToken cancellationToken = default)
        => throw new NotImplementedException("M2: download + sha256 verify + cache reuse.");
}
