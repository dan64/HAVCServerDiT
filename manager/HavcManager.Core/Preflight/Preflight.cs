using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
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

/// <summary>
/// Full outcome of the preflight checks, plus the default model picked for
/// this machine (longcat-gguf below the RAM threshold, else qwen21-viggle).
/// </summary>
public sealed record PreflightReport(IReadOnlyList<PreflightCheck> Checks, string DefaultModelName)
{
    public bool HasErrors => Checks.Any(c => c.Status == PreflightStatus.Error);
}

/// <summary>
/// First-run environment checks (PHASE1_SPEC §6.2 step 1): OS, nvidia-smi
/// (name/driver/VRAM — missing GPU is a non-blocking warning), VRAM and
/// system RAM vs the default model requirements (qwen21-viggle: at least
/// 12 GB VRAM and 32 GB RAM; below the RAM threshold the default switches to
/// the lighter longcat-gguf, Q3), disk space (indicative thresholds),
/// manifest reachability (with a fallback to a `release.json` next to the app).
/// </summary>
public sealed class Preflight
{
    // The install folder also holds the model files (comfy_bridge\models,
    // 2026-10-05): the threshold covers runtime + tools + ~15 GB of weights.
    private const long MinInstallBytes = 30L * 1024 * 1024 * 1024;  // ~30 GB (indicative)
    private const string DefaultModelName = "qwen21-viggle";        // name in the GUI model list
    private const string LighterModelName = "longcat-gguf";         // below the RAM threshold
    private const long MinDefaultModelVramMiB = 12 * 1024;          // 12 GiB
    private const long MinDefaultModelRamBytes = 32L * 1024 * 1024 * 1024;  // 32 GiB

    public async Task<PreflightReport> RunAsync(
        string installDir,
        string manifestUrl,
        string? fallbackManifestPath = null,
        CancellationToken cancellationToken = default)
    {
        var checks = new List<PreflightCheck>();

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
            // The wizard no longer offers a model choice: check the fixed
            // default model's VRAM requirement (non-blocking warning below).
            if (ParseVramMiB(gpu) is { } vramMiB)
            {
                bool enough = vramMiB >= MinDefaultModelVramMiB;
                string requirement = FormatBytes(MinDefaultModelVramMiB * 1024 * 1024);
                checks.Add(new PreflightCheck(
                    "VRAM (default model)",
                    enough ? PreflightStatus.Ok : PreflightStatus.Warning,
                    $"{FormatBytes(vramMiB * 1024 * 1024)} in total — "
                    + (enough
                        ? $"meets the default model ({DefaultModelName}) requirement of at least {requirement}"
                        : $"the default model ({DefaultModelName}) requires at least {requirement}; you can install anyway and pick another model in the HAVC GUI")));
            }
        }
        else
        {
            checks.Add(new PreflightCheck(
                "NVIDIA GPU", PreflightStatus.Warning,
                "nvidia-smi not available — install or update the NVIDIA driver"));
        }

        // System RAM: the nominal default model needs >= 32 GB; below the
        // threshold the default switches to the lighter longcat-gguf (Q3).
        ulong? ramBytes = TotalPhysicalMemoryBytes();
        string defaultModel = DecideDefaultModel(ramBytes is { } ram ? (long)ram : null);
        if (ramBytes is { } bytes)
        {
            bool enoughRam = bytes >= (ulong)MinDefaultModelRamBytes;
            string ramRequirement = FormatBytes(MinDefaultModelRamBytes);
            checks.Add(new PreflightCheck(
                "System memory (default model)",
                enoughRam ? PreflightStatus.Ok : PreflightStatus.Warning,
                $"{FormatBytes((long)bytes)} in total — "
                + (enoughRam
                    ? $"meets the default model ({DefaultModelName}) requirement of at least {ramRequirement}"
                    : $"below the {ramRequirement} required by {DefaultModelName}; the installer will use {LighterModelName} (Q3) as the default model instead")));
        }

        checks.Add(SpaceCheck("Disk space (install)", installDir, MinInstallBytes));

        bool isRemote = Uri.TryCreate(manifestUrl, UriKind.Absolute, out var manifestUri)
                        && (manifestUri.Scheme == Uri.UriSchemeHttp || manifestUri.Scheme == Uri.UriSchemeHttps);
        bool online = !isRemote
                      || await CheckManifestReachabilityAsync(manifestUrl, cancellationToken).ConfigureAwait(false);
        if (online)
        {
            checks.Add(new PreflightCheck("Release manifest", PreflightStatus.Ok, manifestUrl));
        }
        else if (fallbackManifestPath is not null && File.Exists(fallbackManifestPath))
        {
            checks.Add(new PreflightCheck(
                "Release manifest", PreflightStatus.Warning,
                $"cannot reach {manifestUrl} — the local manifest next to the app will be used: {fallbackManifestPath}"));
        }
        else
        {
            checks.Add(new PreflightCheck(
                "Release manifest", PreflightStatus.Warning,
                $"cannot reach {manifestUrl} — you can use a local manifest"));
        }

        return new PreflightReport(checks, defaultModel);
    }

    /// <summary>
    /// Default model for this machine: longcat-gguf (Q3) when the system RAM
    /// is below the requirement, else qwen21-viggle (also when the RAM cannot
    /// be measured). Used by the wizard at preflight and by update/repair runs
    /// so the GUI settings seed stays consistent.
    /// </summary>
    public static string DefaultModelForThisMachine()
    {
        ulong? bytes = TotalPhysicalMemoryBytes();
        return DecideDefaultModel(bytes is { } b ? (long)b : null);
    }

    /// <summary>Machine-readable decision (see <see cref="DefaultModelForThisMachine"/>).</summary>
    public static string DecideDefaultModel(long? totalRamBytes)
        => totalRamBytes is { } ram && ram < MinDefaultModelRamBytes ? LighterModelName : DefaultModelName;

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

    /// <summary>Reads `memory.total` (last nvidia-smi CSV field, e.g. `16384 MiB`).</summary>
    private static long? ParseVramMiB(string nvidiaSmiLine)
    {
        string[] fields = nvidiaSmiLine.Split(',', StringSplitOptions.TrimEntries);
        if (fields.Length < 3)
            return null;
        string[] tokens = fields[^1].Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return tokens.Length > 0
               && long.TryParse(tokens[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out long mib)
            ? mib
            : null;
    }

    /// <summary>Total physical memory in bytes (via GlobalMemoryStatusEx).</summary>
    private static ulong? TotalPhysicalMemoryBytes()
    {
        try
        {
            var status = new MemoryStatusEx { Length = (uint)Marshal.SizeOf<MemoryStatusEx>() };
            return GlobalMemoryStatusEx(ref status) ? status.TotalPhys : null;
        }
        catch (Exception)
        {
            return null;
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MemoryStatusEx
    {
        public uint Length;
        public uint MemoryLoad;
        public ulong TotalPhys;
        public ulong AvailPhys;
        public ulong TotalPageFile;
        public ulong AvailPageFile;
        public ulong TotalVirtual;
        public ulong AvailVirtual;
        public ulong AvailExtendedVirtual;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GlobalMemoryStatusEx(ref MemoryStatusEx lpBuffer);

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
