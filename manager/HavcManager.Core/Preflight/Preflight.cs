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
/// the lighter longcat-gguf, Q3), disk space (indicative thresholds), storage
/// media for the install folder (an HDD is called out below 64 GB of RAM,
/// since the models are then streamed from disk while running),
/// manifest reachability (with a fallback to a `release.json` next to the app).
/// </summary>
public sealed class Preflight
{
    // The install folder also holds the model files (comfy_bridge\models,
    // 2026-10-05): the threshold covers runtime + tools + ~15 GB of weights.
    private const long MinInstallBytes = 30L * 1024 * 1024 * 1024;  // ~30 GB (indicative)

    /// <summary>
    /// Nominal default model (--default-model value; the bootstrap maps it to
    /// the viggle soft int8 config since 2026-10-11).
    /// </summary>
    public const string DefaultModelName = "qwen21-viggle";
    private const string LighterModelName = "longcat-gguf";         // below the thresholds
    private const long MinDefaultModelVramMiB = 12 * 1024;          // 12 GiB
    private const long MinDefaultModelRamBytes = 32L * 1024 * 1024 * 1024;  // 32 GiB

    /// <summary>
    /// Below this much system RAM the lighter longcat-gguf (Q3) becomes the
    /// default model (2026-10-18: the author lowered the switch from 32 GB to
    /// 24 GB, and added the VRAM side of the same rule).
    /// </summary>
    private const long LighterModelRamBytes = 24L * 1024 * 1024 * 1024;  // 24 GiB

    /// <summary>
    /// What the lighter model itself needs: longcat-gguf Q3 runs on an 8 GB
    /// card with 16 GB of RAM (author's field test, 2026-10-18). Quoted in the
    /// wizard so a user below the thresholds knows what the fallback buys.
    /// </summary>
    private const long LighterModelMinVramMiB = 8 * 1024;                  // 8 GiB
    private const long LighterModelMinRamBytes = 16L * 1024 * 1024 * 1024;  // 16 GiB

    /// <summary>"8.0 GB of VRAM and 16.0 GB of RAM" — the fallback's own minimums.</summary>
    public static string LighterModelRequirementsText()
        => $"{FormatBytes(LighterModelMinVramMiB * 1024 * 1024)} of VRAM and "
           + $"{FormatBytes(LighterModelMinRamBytes)} of RAM";

    /// <summary>
    /// At or above this much system RAM the model files stay cached in memory
    /// across phases, so a rotating disk only costs the first load. Below it
    /// they are streamed from disk while running (measured on an RTX 3060 with
    /// 32 GB of RAM and an HDD: ~65 s/image on the single-frame path against
    /// ~4 s on the paired split), hence the SSD suggestion in the wizard.
    /// </summary>
    public const long MinRamForHddBytes = 64L * 1024 * 1024 * 1024;  // 64 GiB

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
        long? vramMiB = null;
        (string? gpu, bool gpuOk) = await RunNvidiaSmiAsync(cancellationToken).ConfigureAwait(false);
        if (gpuOk && gpu is not null)
        {
            checks.Add(new PreflightCheck("NVIDIA GPU", PreflightStatus.Ok, gpu));
            // The wizard no longer offers a model choice: check the fixed
            // default model's VRAM requirement (non-blocking warning below).
            if (ParseVramMiB(gpu) is { } detectedVram)
            {
                vramMiB = detectedVram;
                bool enough = detectedVram >= MinDefaultModelVramMiB;
                string requirement = FormatBytes(MinDefaultModelVramMiB * 1024 * 1024);
                checks.Add(new PreflightCheck(
                    "VRAM (default model)",
                    enough ? PreflightStatus.Ok : PreflightStatus.Warning,
                    $"{FormatBytes(detectedVram * 1024 * 1024)} in total — "
                    + (enough
                        ? $"meets the default model ({DefaultModelName}) requirement of at least {requirement}"
                        : $"below the {requirement} required by {DefaultModelName}; the installer will "
                          + $"use {LighterModelName} (Q3) as the default model instead, which runs from "
                          + $"{LighterModelRequirementsText()} — you can still pick another model in the HAVC GUI")));
            }
        }
        else
        {
            checks.Add(new PreflightCheck(
                "NVIDIA GPU", PreflightStatus.Warning,
                "nvidia-smi not available — install or update the NVIDIA driver"));
        }

        // System RAM / VRAM: the nominal default model wants >= 32 GB of RAM
        // and >= 12 GB of VRAM; below either threshold the default switches to
        // the lighter longcat-gguf (Q3), the only family that runs there.
        ulong? ramBytes = TotalPhysicalMemoryBytes();
        string defaultModel = DecideDefaultModel(
            ramBytes is { } ram ? (long)ram : null, vramMiB);
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
                    : $"below the {ramRequirement} required by {DefaultModelName}"
                      + (defaultModel == LighterModelName
                          ? $"; the installer will use {LighterModelName} (Q3) as the default model instead, "
                            + $"which runs from {LighterModelRequirementsText()}"
                          : ""))));
        }

        checks.Add(SpaceCheck("Disk space (install)", installDir, MinInstallBytes));
        if (DescribeStorage(StorageMedia.KindForPath(installDir), RamBytes(ramBytes)) is { } storage)
            checks.Add(storage);

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
    /// is below 24 GB **or** the GPU has less than 12 GB of VRAM, else
    /// qwen21-viggle (also when the values cannot be measured). Used by the
    /// wizard at preflight and by update/repair runs so the GUI settings seed
    /// stays consistent.
    /// </summary>
    public static string DefaultModelForThisMachine()
        => DecideDefaultModel(TotalRamBytesForThisMachine(), TotalVramMiBForThisMachine());

    /// <summary>Total physical memory in bytes, or null when it cannot be read.</summary>
    public static long? TotalRamBytesForThisMachine()
        => TotalPhysicalMemoryBytes() is { } bytes ? (long)bytes : null;

    /// <summary>Total VRAM in MiB via nvidia-smi, or null when it is missing.</summary>
    public static long? TotalVramMiBForThisMachine()
    {
        try
        {
            (string? gpu, bool ok) = RunNvidiaSmiAsync(CancellationToken.None)
                .ConfigureAwait(false).GetAwaiter().GetResult();
            return ok && gpu is not null ? ParseVramMiB(gpu) : null;
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static long? RamBytes(ulong? bytes) => bytes is { } value ? (long)value : null;

    /// <summary>Machine-readable decision (see <see cref="DefaultModelForThisMachine"/>).</summary>
    public static string DecideDefaultModel(long? totalRamBytes, long? vramMiB = null)
    {
        if (totalRamBytes is { } ram && ram < LighterModelRamBytes)
            return LighterModelName;
        if (vramMiB is { } vram && vram < MinDefaultModelVramMiB)
            return LighterModelName;
        return DefaultModelName;
    }

    /// <summary>
    /// Storage advice for the install folder: a warning only when the folder
    /// is on a rotating disk and the machine has less than 64 GB of RAM — the
    /// condition under which the models are streamed from disk while running.
    /// Unknown media produce no line at all (nothing is claimed).
    /// </summary>
    public static PreflightCheck? DescribeStorage(StorageKind kind, long? totalRamBytes)
    {
        switch (kind)
        {
            case StorageKind.Ssd:
                return new PreflightCheck(
                    "Storage (install folder)", PreflightStatus.Ok,
                    "solid-state drive — the recommended choice for the model files");
            case StorageKind.Hdd when totalRamBytes is { } ram && ram < MinRamForHddBytes:
                return new PreflightCheck(
                    "Storage (install folder)", PreflightStatus.Warning,
                    $"hard disk, and this machine has {FormatBytes(ram)} of RAM — below the "
                    + $"{FormatBytes(MinRamForHddBytes)} at which the models stay cached in memory. "
                    + "The model files (comfy_bridge\\models) are then streamed from disk while running: "
                    + "measured on an HDD ~65 s per image on the single-frame path against ~4 s on the "
                    + "paired split. Consider installing on an SSD.");
            case StorageKind.Hdd:
                return new PreflightCheck(
                    "Storage (install folder)", PreflightStatus.Ok,
                    "hard disk — with 64 GB or more of RAM the models stay in memory; "
                    + "the very first load still takes a few minutes");
            default:
                return null;
        }
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
