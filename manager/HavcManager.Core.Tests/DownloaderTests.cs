using HavcManager.Core.Download;

namespace HavcManager.Core.Tests;

public class DownloaderTests
{
    [Fact]
    public async Task Sha256_matches_known_vector()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string file = Path.Combine(dir, "hello.txt");
            await File.WriteAllTextAsync(file, "hello");
            string hash = await Downloader.Sha256Async(file);
            Assert.Equal("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824", hash);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public async Task Reuses_a_matching_cache_file_without_fetching()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string cached = Path.Combine(dir, "artifact.bin");
            await File.WriteAllTextAsync(cached, "hello");
            string sha = await Downloader.Sha256Async(cached);

            // The URL points to a missing file: any fetch attempt would throw.
            string missingUrl = new Uri(Path.Combine(dir, "missing.bin")).AbsoluteUri;
            var downloader = new Downloader();
            string result = await downloader.GetAsync(missingUrl, "artifact.bin", dir, sha, 5);

            Assert.Equal(cached, result);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public async Task Mismatching_cache_entry_is_not_reused()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string cached = Path.Combine(dir, "artifact.bin");
            await File.WriteAllTextAsync(cached, "garbage");
            string shaOfHello = await Sha256OfAsync(dir, "hello");

            string missingUrl = new Uri(Path.Combine(dir, "missing.bin")).AbsoluteUri;
            var downloader = new Downloader();
            await Assert.ThrowsAsync<FileNotFoundException>(
                () => downloader.GetAsync(missingUrl, "artifact.bin", dir, shaOfHello, 5));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public async Task Copies_and_verifies_file_urls()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string source = Path.Combine(dir, "source.bin");
            await File.WriteAllTextAsync(source, "hello");
            string sha = await Downloader.Sha256Async(source);
            string cache = Path.Combine(dir, "cache");
            var downloader = new Downloader();

            string copied = await downloader.GetAsync(
                new Uri(source).AbsoluteUri, "copy.bin", cache, sha, 5);
            Assert.True(File.Exists(copied));
            Assert.Equal("hello", await File.ReadAllTextAsync(copied));

            await Assert.ThrowsAsync<InvalidDataException>(
                () => downloader.GetAsync(
                    new Uri(source).AbsoluteUri, "bad.bin", cache,
                    "0000000000000000000000000000000000000000000000000000000000000000", 5));

            // no .part leftovers on failure
            Assert.Empty(Directory.GetFiles(cache, "*.part"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    private static async Task<string> Sha256OfAsync(string dir, string content)
    {
        string file = Path.Combine(dir, "sha-probe.txt");
        await File.WriteAllTextAsync(file, content);
        return await Downloader.Sha256Async(file);
    }
}
