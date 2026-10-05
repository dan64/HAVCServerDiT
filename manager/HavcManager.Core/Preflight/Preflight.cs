using System.Diagnostics;
using System.Globalization;
using HavcManager.Core.Manifest;

namespace HavcManager.Core.Preflight;

public enum PreflightStatus
{
    Ok,
    Warning,
    Error,
}

/// <summary>One check outcome.</summary>
public sealed record PreflightCheck(string Name, PreflightStatus Status, string? Detail);

/// <summary>Full outcome, with the suggested default backend (e.g. "fp4").</summary>
public sealed record PreflightReport(IReadOnlyList<PreflightCheck> Checks, string? SuggestedBackend)
{
    public bool HasErrors => Checks.Any(c => c.Status == PreflightStatus.Error);
}

/// <summary>
/// First-run environment checks (PHASE1_SPEC §6.2 step 1): OS, nvidia-smi
/// (name/driver/VRAM — missing GPU is a non-blocking warning), disk space
/// (indicative thresholds), manifest reachability.
/// </summary>
public sealed class Preflight
{
    private const long MinInstallBytes = 15L * 1024 * 1024 * 1024;  // ~15 GB (indicative)
    private const long MinModelsBytes = 50L * 1024 * 1024 * 1024;   // ~50 GB (indicative)

    public async Task<PreflightReport> RunAsync(
        string installDir,
        string modelsDir,
        string manifestUrl,
        CancellationToken cancellationToken = default)
    {
        var checks = new List<PreflightCheck>();
        string? suggestedBackend = null;

        // OS: Windows 10 1809+ / Windows 11.
        var version = Environment.OSVersion.Version;
        bool osOk = OperatingSystem.IsWindowsVersionAtLeast(10, 0, 17763);
        checks.Add(new PreflightCheck(
            "Windows version",
            osOk ? PreflightStatus.Ok : PreflightStatus.Error,
            $"Windows {version.Major}.{version.Minor} build {version.Build} (10.0.17763 or later required)"));

        // GPU: nvidia-smi, non-blocking when absent.
        (string? gpu, bool gpuOk) = await RunNvidiaSmiAsync(cancellationToken).ConfigureAwait(false);
        if (gpuOk && gpu is not null)
        {
            checks.Add(new PreflightCheck("NVIDIA GPU", PreflightStatus.Ok, gpu));
            // Indicative default (PHASE1_SPEC §6.2): mirrors the GUI default;
            // refine when the real backend/VRAM requirements are documented.
            suggestedBackend = "fp4";
        }
        else
        {
            checks.Add(new PreflightCheck(
                "NVIDIA GPU", PreflightStatus.Warning,
                "nvidia-smi not available — install or update the NVIDIA driver"));
        }

        checks.Add(SpaceCheck("Disk space (install)", installDir, MinInstallBytes));
        checks.Add(SpaceCheck("Disk space (models)", modelsDir, MinModelsBytes));

        bool isRemote = Uri.TryCreate(manifestUrl, UriKind.Absolute, out var manifestUri)
                        && (manifestUri.Scheme == Uri.UriSchemeHttp || manifestUri.Scheme == Uri.UriSchemeHttps);
        bool online = !isRemote
                      || await CheckManifestReachabilityAsync(manifestUrl, cancellationToken).ConfigureAwait(false);
        checks.Add(new PreflightCheck(
            "Release manifest",
            online ? PreflightStatus.Ok : PreflightStatus.Warning,
            online ? manifestUrl : $"cannot reach {manifestUrl} — you can use a local manifest"));

        return new PreflightReport(checks, suggestedBackend);
    }

    private static PreflightCheck SpaceCheck(string name, string path, long minimumBytes)
    {
        try
        {
            string root = Path.GetPathRoot(Path.GetFullPath(path)) ?? "";
            var drive = new DriveInfo(root);
            long free = drive.AvailableFreeSpace;
            return new PreflightCheck(
                name,
                free >= minimumBytes ? PreflightStatus.Ok : PreflightStatus.Warning,
                $"{FormatBytes(free)} free on {drive.Name.TrimEnd('\\')} (recommended: at least {FormatBytes(minimumBytes)})");
        }
        catch (ArgumentException ex)
        {
            return new PreflightCheck(name, PreflightStatus.Warning, ex.Message);
        }
        catch (IOException ex)
        {
            return new PreflightCheck(name, PreflightStatus.Warning, ex.Message);
        }
    }

    private static async Task<(string? Line, bool Ok)> RunNvidiaSmiAsync(CancellationToken cancellationToken)
    {
        string exe = Path.Combine(Environment.SystemDirectory, "nvidia-smi.exe");
        if (!File.Exists(exe))
            exe = "nvidia-smi";
        try
        {
            var psi = new ProcessStartInfo(exe)
            {
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = System.Text.Encoding.UTF8,
                StandardErrorEncoding = System.Text.Encoding.UTF8,
            };
            psi.ArgumentList.Add("--query-gpu=name,driver_version,memory.total");
            psi.ArgumentList.Add("--format=csv,noheader");
            using var process = Process.Start(psi);
            if (process is null)
                return (null, false);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(15));
            var outputTask = process.StandardOutput.ReadToEndAsync(timeout.Token);
            var errorTask = process.StandardError.ReadToEndAsync(timeout.Token);
            string output = await outputTask.ConfigureAwait(false);
            await errorTask.ConfigureAwait(false);
            await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
            string line = output
                .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .FirstOrDefault() ?? "";
            return process.ExitCode == 0 && line.Length > 0 ? (line, true) : (null, false);
        }
        catch (OperationCanceledException)
        {
            return (null, false);
        }
        catch (Exception)
        {
            // nvidia-smi missing/unusable: non-blocking warning
            return (null, false);
        }
    }

    private static async Task<bool> CheckManifestReachabilityAsync(string manifestUrl, CancellationToken cancellationToken)
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
            using var response = await http
                .GetAsync(manifestUrl, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
                .ConfigureAwait(false);
            return response.IsSuccessStatusCode;
        }
        catch (Exception)
        {
            return false;
        }
    }

    private static string FormatBytes(long bytes)
    {
        if (bytes >= 1L << 30)
            return string.Format(CultureInfo.InvariantCulture, "{0:0.0} GB", bytes / (double)(1L << 30));
        return string.Format(CultureInfo.InvariantCulture, "{0:0.0} MB", bytes / (double)(1L << 20));
    }
}
