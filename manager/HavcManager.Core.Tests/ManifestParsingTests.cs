using System.Text.Json;
using HavcManager.Core.Manifest;

namespace HavcManager.Core.Tests;

public class ManifestParsingTests
{
    private const string SampleManifest = """
    {
      "schema": 1,
      "channel": "stable",
      "app": "havc",
      "app_version": "0.1.0",
      "published_at": "2026-10-04T12:00:00Z",
      "requires_python": "3.12",
      "requires_env_rebuild": false,
      "bootstrap_min_version": "0.1.0",
      "runtime": {
        "name": "cpython-3.12.15+20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
        "url": "https://example.invalid/runtime.tar.gz",
        "sha256": "6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402",
        "python": "3.12.15",
        "kind": "python-build-standalone",
        "mirror_of": "https://example.invalid/upstream.tar.gz"
      },
      "wheels": [
        {
          "name": "havc-0.1.0-py3-none-any.whl",
          "url": "https://example.invalid/havc-0.1.0-py3-none-any.whl",
          "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
          "size": 1,
          "kind": "project",
          "install": "no-deps"
        }
      ],
      "assets": [
        {
          "name": "diffusers-0.37.0.dev0-py3-none-any.whl",
          "url": "https://example.invalid/diffusers.whl",
          "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
          "size": 2,
          "kind": "python-wheel",
          "target": "diffusers"
        }
      ],
      "weights": [],
      "tools": [],
      "notes_url": "https://example.invalid/tag"
    }
    """;

    [Fact]
    public void Parses_the_full_manifest()
    {
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>(SampleManifest)!;
        Assert.Equal(1, manifest.Schema);
        Assert.Equal("stable", manifest.Channel);
        Assert.Equal("0.1.0", manifest.AppVersion);
        Assert.Equal("3.12", manifest.RequiresPython);
        Assert.False(manifest.RequiresEnvRebuild);
        Assert.Equal("3.12.15", manifest.Runtime!.Python);
        Assert.Equal("project", manifest.Wheels[0].Kind);
        Assert.Equal("no-deps", manifest.Wheels[0].Install);
        Assert.Equal("diffusers", manifest.Assets[0].Target);
        Assert.Empty(manifest.Weights);
    }

    [Fact]
    public void Unknown_fields_are_ignored()
    {
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>(
            """{"app_version": "9.9", "future_field": {"x": 1}, "schema": 1}""")!;
        Assert.Equal("9.9", manifest.AppVersion);
    }

    [Fact]
    public void Missing_optional_fields_get_defaults()
    {
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>("{}")!;
        Assert.Equal(1, manifest.Schema);
        Assert.Equal("stable", manifest.Channel);
        Assert.Null(manifest.Runtime);
        Assert.Empty(manifest.Wheels);
        Assert.Empty(manifest.Assets);
    }

    [Fact]
    public async Task ManifestClient_reads_a_local_file()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string path = Path.Combine(dir, "release.json");
            await File.WriteAllTextAsync(path, SampleManifest);
            var client = new ManifestClient();
            var manifest = await client.FetchAsync(path);
            Assert.Equal("0.1.0", manifest.AppVersion);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void DownloadPlan_orders_runtime_wheels_and_assets()
    {
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>(SampleManifest)!;
        var plan = DownloadPlan.FromManifest(manifest);
        Assert.Equal(3, plan.Count);
        Assert.Equal(manifest.Runtime!.Name, plan[0].Name);
        Assert.Equal("", plan[0].CacheSubfolder);
        Assert.Equal("havc-0.1.0-py3-none-any.whl", plan[1].Name);
        Assert.Equal("", plan[1].CacheSubfolder);
        Assert.Equal("assets", plan[2].CacheSubfolder);
    }

    [Fact]
    public async Task Rejects_a_manifest_without_app_version()
    {
        var ex = await FetchInvalidAsync(
            """{"schema": 1, "wheels": [{"name": "a.whl", "url": "u", "sha256": "s", "kind": "project"}]}""");
        Assert.Contains("app_version", ex.Message);
    }

    [Fact]
    public async Task Rejects_a_manifest_without_a_project_wheel()
    {
        var ex = await FetchInvalidAsync(
            """{"schema": 1, "app_version": "1.0", "wheels": [{"name": "a.whl", "url": "u", "sha256": "s", "kind": "python-wheel"}]}""");
        Assert.Contains("project wheel", ex.Message);
    }

    [Fact]
    public async Task Rejects_an_artifact_with_missing_sha256()
    {
        var ex = await FetchInvalidAsync(
            """{"schema": 1, "app_version": "1.0", "wheels": [{"name": "a.whl", "url": "u", "kind": "project"}]}""");
        Assert.Contains("name/url/sha256", ex.Message);
    }

    [Fact]
    public async Task Rejects_an_unsupported_schema()
    {
        var ex = await FetchInvalidAsync(
            """{"schema": 2, "app_version": "1.0", "wheels": [{"name": "a.whl", "url": "u", "sha256": "s", "kind": "project"}]}""");
        Assert.Contains("schema", ex.Message);
    }

    private static async Task<InvalidDataException> FetchInvalidAsync(string json)
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string path = Path.Combine(dir, "release.json");
            await File.WriteAllTextAsync(path, json);
            return await Assert.ThrowsAsync<InvalidDataException>(
                () => new ManifestClient().FetchAsync(path));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }
}
