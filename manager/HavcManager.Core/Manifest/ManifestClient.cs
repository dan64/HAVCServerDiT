using System.Text.Json;

namespace HavcManager.Core.Manifest;

/// <summary>
/// Fetches and parses the release manifest. Accepts an https URL (releases) or
/// a local file path (tests: --manifest / --release-tag, PHASE1_SPEC §11).
/// </summary>
public sealed class ManifestClient
{
    /// <summary>Default manifest URL (latest release of the public repo).</summary>
    public const string DefaultUrl =
        "https://github.com/dan64/HAVCServerDiT/releases/latest/download/release.json";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        AllowTrailingCommas = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
    };

    private readonly HttpClient _http;

    public ManifestClient(HttpClient? http = null) => _http = http ?? new HttpClient();

    /// <summary>
    /// Loads the manifest from <paramref name="urlOrPath"/> (https:// URL or local file)
    /// and validates the fields the manager relies on (schema, app_version,
    /// project wheel, artifact name/url/sha256) with friendly errors.
    /// </summary>
    public async Task<ReleaseManifest> FetchAsync(string urlOrPath, CancellationToken cancellationToken = default)
    {
        string json = Uri.TryCreate(urlOrPath, UriKind.Absolute, out var uri) &&
                      (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps)
            ? await _http.GetStringAsync(uri, cancellationToken).ConfigureAwait(false)
            : await File.ReadAllTextAsync(urlOrPath, cancellationToken).ConfigureAwait(false);

        ReleaseManifest manifest = JsonSerializer.Deserialize<ReleaseManifest>(json, JsonOptions)
               ?? throw new InvalidDataException($"Empty or invalid manifest: {urlOrPath}");
        Validate(manifest, urlOrPath);
        return manifest;
    }

    private static void Validate(ReleaseManifest manifest, string source)
    {
        if (manifest.Schema != 1)
            throw new InvalidDataException(
                $"unsupported manifest schema {manifest.Schema} ({source}) — update the manager.");
        if (string.IsNullOrWhiteSpace(manifest.AppVersion))
            throw new InvalidDataException($"the manifest has no app_version ({source}).");
        if (manifest.Wheels.Count == 0)
            throw new InvalidDataException($"the manifest lists no wheels ({source}).");
        if (manifest.Wheels.All(w => !string.Equals(w.Kind, "project", StringComparison.OrdinalIgnoreCase)))
            throw new InvalidDataException($"the manifest has no project wheel ({source}).");
        foreach (ArtifactEntry entry in manifest.Wheels.Concat(manifest.Assets))
        {
            if (string.IsNullOrWhiteSpace(entry.Name) || string.IsNullOrWhiteSpace(entry.Url) ||
                string.IsNullOrWhiteSpace(entry.Sha256))
                throw new InvalidDataException(
                    $"the manifest has an artifact with missing name/url/sha256 ({source}).");
        }
    }
}
