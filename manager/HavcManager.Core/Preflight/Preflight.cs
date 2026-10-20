using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
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
/// this machine (longcat-gguf on small machines, else qwen-2509-nunchaku —
/// fp4 on RTX 50, int4 on RTX 30/40).
/// </summary>
public sealed record PreflightReport(IReadOnlyList<PreflightCheck> Checks, string DefaultModelName)
{
    public bool HasErrors => Checks.Any(c => c.Status == PreflightStatus.Error);
}

/// <summary>
/// First-run environment checks (PHASE1_SPEC §6.2 step 1): OS, nvidia-smi
/// (name/driver/VRAM/compute capability — missing GPU is a non-blocking
/// warning), the default-model choice (see <see cref="DecideDefaultModel"/>:
/// longcat-gguf Q3 on small machines, else qwen-2509-nunchaku — fp4 on
/// RTX 50, int4 on RTX 30/40), disk space (indicative thresholds), storage
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
    /// Nominal default model (--default-model value) when nothing was
    /// measured: the int4 file works on RTX 30/40 and on RTX 50. The manager
    /// normally passes the machine-specific value chosen by
    /// <see cref="DecideDefaultModel"/>.
    /// </summary>
    public const string DefaultModelName = QwenNunchakuInt4ModelName;

    /// <summary>Nominal default on RTX 50 (Blackwell): the fp4 checkpoint.</summary>
    public const string QwenNunchakuFp4ModelName = "qwen25-nunchaku-fp4";

    /// <summary>Nominal default on RTX 30/40 (and the safe fallback): int4.</summary>
    public const string QwenNunchakuInt4ModelName = "qwen25-nunchaku-int4";

    /// <summary>Family label quoted in the wizard messages.</summary>
    public const string DefaultModelFamily = "qwen-2509-nunchaku";

    private const string LighterModelName = "flux2-klein-4b-int8";  // below the thresholds

    // Default-model rule (author decision, 2026-10-18; lighter model changed
    // to Flux.2 Klein 4B INT8 on 2026-10-20):
    //   VRAM < 12 GB, or (VRAM <= 16 GB and RAM < 24 GB) -> flux2-klein-4b-int8
    //   otherwise -> qwen-2509-nunchaku (fp4 on RTX 50, int4 on RTX 30/40)
    private const long MinDefaultModelVramGiB = 12;
    private const long MaxMidrangeVramGiB = 16;
    private const long MinDefaultModelRamGiB = 24;

    /// <summary>
    /// What the lighter model itself needs. The figures come from the field
    /// test of longcat-gguf Q3 on an 8 GB card with 16 GB of RAM (2026-10-18);
    /// Flux.2 Klein 4B INT8 replaced it on 2026-10-20 and is smaller (7.60 GB
    /// of weights against 8.83 GB, and 3.8 GB against 5.8 GB in phase A, where
    /// the text encoder is the only model resident), so the same minimums are
    /// kept as a deliberately conservative statement. Quoted in the wizard so
    /// a user below the thresholds knows what the fallback buys.
    /// </summary>
    private const long LighterModelMinVramMiB = 8 * 1024;                  // 8 GiB
    private const long LighterModelMinRamBytes = 16L * 1024 * 1024 * 1024;  // 16 GiB

    /// <summary>"8 GB of VRAM and 16 GB of RAM" — the fallback's own minimums.</summary>
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
        GpuInfo? gpu = await QueryGpuAsync(cancellationToken).ConfigureAwait(false);
        long? vramMiB = gpu?.VramMiB;
        if (gpu is not null)
        {
            checks.Add(new PreflightCheck(
                "NVIDIA GPU", PreflightStatus.Ok,
                $"{gpu.Name}, {gpu.Driver}"
                + (vramMiB is { } detected ? $", {FormatBytes(detected * 1024 * 1024)}" : "")));
            // The wizard no longer offers a model choice: check the fixed
            // default model's VRAM requirement (non-blocking warning below).
            if (vramMiB is { } detectedVram)
            {
                bool enough = RoundMibToGiB(detectedVram) >= MinDefaultModelVramGiB;
                string requirement = $"{MinDefaultModelVramGiB} GB";
                checks.Add(new PreflightCheck(
                    "VRAM (default model)",
                    enough ? PreflightStatus.Ok : PreflightStatus.Warning,
                    $"{FormatBytes(detectedVram * 1024 * 1024)} in total — "
                    + (enough
                        ? $"meets the {requirement} minimum of the default model ({DefaultModelFamily})"
                        : $"below the {requirement} minimum of the default model ({DefaultModelFamily}); "
                          + $"the installer will use {LighterModelName} as the default model instead, "
                          + $"which runs from {LighterModelRequirementsText()} — you can still pick another "
                          + "model in the HAVC GUI")));
            }
        }
        else
        {
            checks.Add(new PreflightCheck(
                "NVIDIA GPU", PreflightStatus.Warning,
                "nvidia-smi not available — install or update the NVIDIA driver"));
        }

        // System RAM / VRAM (rule of 2026-10-18, lighter model since
        // 2026-10-20): flux2-klein-4b-int8 when the card has less than 12 GB of
        // VRAM, or when a card up to 16 GB is paired with less than 24 GB of
        // RAM; otherwise qwen-2509-nunchaku.
        // Both sizes are rounded to whole GB first: a 32 GB machine reports
        // ~31.9 GB and a 12 GB card 12282 MiB, and neither may be read as
        // just below its own nominal threshold.
        ulong? ramBytes = TotalPhysicalMemoryBytes();
        long? totalRam = ramBytes is { } ram ? (long)ram : null;
        string defaultModel = DecideDefaultModel(totalRam, vramMiB, gpu?.Blackwell ?? false);
        if (totalRam is { } ramTotal)
        {
            long ramGiB = RoundToGiB(ramTotal);
            long? vramGiB = vramMiB is { } value ? RoundMibToGiB(value) : null;
            bool lighterByRam = vramGiB is { } card
                                && card <= MaxMidrangeVramGiB
                                && ramGiB < MinDefaultModelRamGiB;
            string ramRequirement = $"{MinDefaultModelRamGiB} GB";
            PreflightStatus status = lighterByRam || (vramGiB is null && ramGiB < MinDefaultModelRamGiB)
                ? PreflightStatus.Warning
                : PreflightStatus.Ok;
            string detail = $"{FormatBytes(ramTotal)} in total — "
                + (lighterByRam
                    ? $"below the {ramRequirement} the default model ({DefaultModelFamily}) needs on a GPU "
                      + $"with up to {MaxMidrangeVramGiB} GB of VRAM; the installer will use {LighterModelName} "
                      + $"as the default model instead, which runs from {LighterModelRequirementsText()}"
                    : vramGiB is null && ramGiB < MinDefaultModelRamGiB
                        ? $"below the {ramRequirement} requirement of the default model ({DefaultModelFamily}), "
                          + "and the GPU could not be measured; the installer will use "
                          + $"{LighterModelName} as the default model instead"
                        : ramGiB >= MinDefaultModelRamGiB
                            ? $"meets the {ramRequirement} minimum of the default model ({DefaultModelFamily})"
                            : $"the default model ({DefaultModelFamily}) is kept because the GPU has more "
                              + $"than {MaxMidrangeVramGiB} GB of VRAM; the {ramRequirement} minimum applies to "
                              + $"GPUs up to {MaxMidrangeVramGiB} GB");
            checks.Add(new PreflightCheck("System memory (default model)", status, detail));
        }

        checks.Add(SpaceCheck("Disk space (install)", installDir, MinInstallBytes));
        if (DescribeStorage(StorageMedia.KindForPath(installDir), totalRam) is { } storage)
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
    /// Default model for this machine (see <see cref="DecideDefaultModel"/>).
    /// Used by the wizard at preflight and by update/repair runs so the GUI
    /// settings seed stays consistent.
    /// </summary>
    public static string DefaultModelForThisMachine()
    {
        GpuInfo? gpu = GpuInfoForThisMachine();
        return DecideDefaultModel(
            TotalRamBytesForThisMachine(), gpu?.VramMiB, gpu?.Blackwell ?? false);
    }

    /// <summary>Total physical memory in bytes, or null when it cannot be read.</summary>
    public static long? TotalRamBytesForThisMachine()
        => TotalPhysicalMemoryBytes() is { } bytes ? (long)bytes : null;

    /// <summary>GPU information via nvidia-smi, or null when it is missing.</summary>
    public static GpuInfo? GpuInfoForThisMachine()
    {
        try
        {
            return QueryGpuAsync(CancellationToken.None)
                .ConfigureAwait(false).GetAwaiter().GetResult();
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>Total VRAM in MiB via nvidia-smi, or null when it is missing.</summary>
    public static long? TotalVramMiBForThisMachine() => GpuInfoForThisMachine()?.VramMiB;

    /// <summary>
    /// Machine-readable default-model decision (author rule, 2026-10-18;
    /// lighter model changed to Flux.2 Klein 4B INT8 on 2026-10-20):
    /// flux2-klein-4b-int8 when the GPU has less than 12 GB of VRAM, or when a
    /// GPU up to 16 GB is paired with less than 24 GB of RAM; otherwise
    /// qwen-2509-nunchaku — fp4 on RTX 50 (Blackwell), int4 on RTX 30/40.
    /// RAM and VRAM are rounded to whole GB first (a 32 GB machine reports
    /// ~31.9 GB, a 12 GB card 12282 MiB), so a nominal size is never read as
    /// just below its own threshold. With no GPU reading the lighter model is
    /// returned: without one the fp4/int4 half cannot be chosen.
    /// </summary>
    public static string DecideDefaultModel(long? totalRamBytes, long? vramMiB = null, bool blackwell = false)
    {
        long? ramGiB = totalRamBytes is { } ram ? RoundToGiB(ram) : null;
        long? vramGiB = vramMiB is { } mib ? RoundMibToGiB(mib) : null;
        if (vramGiB is not { } vram)
            return LighterModelName;
        if (vram < MinDefaultModelVramGiB
            || (vram <= MaxMidrangeVramGiB && ramGiB is { } r && r < MinDefaultModelRamGiB))
            return LighterModelName;
        return blackwell ? QwenNunchakuFp4ModelName : QwenNunchakuInt4ModelName;
    }

    /// <summary>Bytes rounded to whole GB, the way RAM sizes are sold and quoted.</summary>
    public static long RoundToGiB(long bytes)
        => (long)Math.Round(bytes / (double)(1L << 30), MidpointRounding.AwayFromZero);

    /// <summary>MiB rounded to whole GB (nvidia-smi reports e.g. 12282 MiB for a 12 GB card).</summary>
    public static long RoundMibToGiB(long mib)
        => (long)Math.Round(mib / 1024.0, MidpointRounding.AwayFromZero);

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

    /// <summary>
    /// GPU facts read from nvidia-smi. <paramref name="Blackwell"/> is the
    /// RTX 50 family: computed from `compute_cap` when the driver reports it
    /// (12.0/12.1 = SM 120/121), else from the product name.
    /// </summary>
    public sealed record GpuInfo(string Name, string Driver, long? VramMiB, bool Blackwell);

    /// <summary>
    /// Reads name, driver, VRAM and (when supported) compute capability.
    /// `compute_cap` is the reliable Blackwell signal; drivers that do not
    /// know the field make the whole query fail, so the call is retried
    /// without it and the generation is read from the product name.
    /// </summary>
    private static async Task<GpuInfo?> QueryGpuAsync(CancellationToken cancellationToken)
        => await RunNvidiaSmiAsync(
               "name,driver_version,memory.total,compute_cap", cancellationToken).ConfigureAwait(false)
           ?? await RunNvidiaSmiAsync(
               "name,driver_version,memory.total", cancellationToken).ConfigureAwait(false);

    private static async Task<GpuInfo?> RunNvidiaSmiAsync(string fields, CancellationToken cancellationToken)
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
            psi.ArgumentList.Add($"--query-gpu={fields}");
            psi.ArgumentList.Add("--format=csv,noheader");
            using var process = Process.Start(psi);
            if (process is null)
                return null;
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
            return process.ExitCode == 0 && line.Length > 0 ? ParseGpuLine(line) : null;
        }
        catch (OperationCanceledException)
        {
            return null;
        }
        catch (Exception)
        {
            // nvidia-smi missing/unusable: non-blocking warning
            return null;
        }
    }

    /// <summary>
    /// Parses one `name, driver, memory.total[, compute_cap]` CSV line; the
    /// memory field is `16384 MiB` (the unit suffix is dropped).
    /// </summary>
    private static GpuInfo? ParseGpuLine(string line)
    {
        string[] fields = line.Split(',', StringSplitOptions.TrimEntries);
        if (fields.Length < 3)
            return null;
        long? vramMiB = ParseLeadingInteger(fields[2]);
        bool? blackwell = fields.Length >= 4 && TryParseComputeMajor(fields[3], out int major)
            ? major >= 10
            : null;
        return new GpuInfo(fields[0], fields[1], vramMiB, blackwell ?? LooksLikeBlackwell(fields[0]));
    }

    private static long? ParseLeadingInteger(string field)
    {
        string[] tokens = field.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return tokens.Length > 0
               && long.TryParse(tokens[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out long value)
            ? value
            : null;
    }

    private static bool TryParseComputeMajor(string field, out int major)
    {
        major = 0;
        string[] parts = field.Split('.');
        return parts.Length > 0
               && int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out major);
    }

    /// <summary>
    /// True for the RTX 50 family (Blackwell) read from the product name —
    /// the fallback when the driver does not report `compute_cap`. Matches
    /// 5050–5090 (laptop and PRO names included) but not the Ada
    /// `RTX 5000`/`A5000` workstation cards.
    /// </summary>
    public static bool LooksLikeBlackwell(string gpuName)
        => gpuName.Contains("Blackwell", StringComparison.OrdinalIgnoreCase)
           || Regex.IsMatch(gpuName, @"\bRTX\s+(?:PRO\s+)?50[5-9]\d\b", RegexOptions.IgnoreCase);

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

    /// <summary>
    /// Human-readable size with no decimals: RAM and VRAM are sold in whole
    /// GB, and a 32 GB machine reporting ~31.9 GB must read "32 GB" (2026-10-18).
    /// </summary>
    private static string FormatBytes(long bytes)
    {
        if (bytes >= 1L << 30)
            return string.Format(CultureInfo.InvariantCulture, "{0:0} GB", RoundToGiB(bytes));
        return string.Format(CultureInfo.InvariantCulture, "{0:0} MB", bytes / (double)(1L << 20));
    }
}
