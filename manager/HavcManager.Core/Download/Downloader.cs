using System.Buffers;
using System.Security.Cryptography;

namespace HavcManager.Core.Download;

/// <summary>
/// Downloads artifacts into the install cache (<install>\cache\, original file
/// names) and verifies the SHA-256 digest before use; existing files are
/// reused when the digest matches (PHASE1_SPEC §6.2 step 4, §10).
/// Accepts https URLs and local file:// URLs (staged/offline tests).
/// </summary>
public sealed class Downloader
{
    private readonly HttpClient _http;

    public Downloader(HttpClient? http = null)
        => _http = http ?? new HttpClient { Timeout = TimeSpan.FromMinutes(30) };

    /// <summary>
    /// Returns the local path of <paramref name="fileName"/> inside <paramref name="cacheDir"/>,
    /// downloading it from <paramref name="url"/> when missing or mismatching.
    /// On success the destination is guaranteed to match sha256 (and size, when known).
    /// </summary>
    public async Task<string> GetAsync(
        string url,
        string fileName,
        string cacheDir,
        string expectedSha256,
        long expectedSize,
        IProgress<long>? bytesReceived = null,
        CancellationToken cancellationToken = default)
    {
        string destination = Path.Combine(cacheDir, fileName);
        if (await HasExpectedContentAsync(destination, expectedSha256, expectedSize, cancellationToken).ConfigureAwait(false))
            return destination;

        Directory.CreateDirectory(cacheDir);
        string temporary = destination + ".part";
        try
        {
            if (Uri.TryCreate(url, UriKind.Absolute, out var uri) && uri.IsFile)
            {
                File.Copy(uri.LocalPath, temporary, overwrite: true);
                bytesReceived?.Report(new FileInfo(temporary).Length);
            }
            else
            {
                using var response = await _http
                    .GetAsync(url, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
                    .ConfigureAwait(false);
                response.EnsureSuccessStatusCode();
                await using var source = await response.Content
                    .ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
                await using var target = new FileStream(
                    temporary, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20, useAsync: true);
                byte[] buffer = ArrayPool<byte>.Shared.Rent(1 << 20);
                try
                {
                    long done = 0;
                    int read;
                    while ((read = await source.ReadAsync(buffer, cancellationToken).ConfigureAwait(false)) > 0)
                    {
                        await target.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
                        done += read;
                        bytesReceived?.Report(done);
                    }
                }
                finally
                {
                    ArrayPool<byte>.Shared.Return(buffer);
                }
            }

            string actual = await Sha256Async(temporary, cancellationToken).ConfigureAwait(false);
            long size = new FileInfo(temporary).Length;
            if (!actual.Equals(expectedSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(
                    $"{fileName}: sha256 mismatch (expected {expectedSha256}, got {actual})");
            if (expectedSize > 0 && size != expectedSize)
                throw new InvalidDataException(
                    $"{fileName}: size mismatch (expected {expectedSize}, got {size})");

            File.Move(temporary, destination, overwrite: true);
            return destination;
        }
        catch
        {
            TryDelete(temporary);
            throw;
        }
    }

    /// <summary>Lowercase hex SHA-256 of a file.</summary>
    public static async Task<string> Sha256Async(string path, CancellationToken cancellationToken = default)
    {
        await using var stream = File.OpenRead(path);
        byte[] hash = await SHA256.HashDataAsync(stream, cancellationToken).ConfigureAwait(false);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static async Task<bool> HasExpectedContentAsync(
        string path, string sha256, long size, CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
            return false;
        if (size > 0 && new FileInfo(path).Length != size)
            return false;
        return (await Sha256Async(path, cancellationToken).ConfigureAwait(false))
            .Equals(sha256, StringComparison.OrdinalIgnoreCase);
    }

    private static void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (IOException)
        {
            // best effort: the .part file is overwritten on the next attempt
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}
