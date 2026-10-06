using System.Diagnostics;
using System.Text;
using HavcManager.Core.Bootstrap;
using HavcManager.Core.Download;
using HavcManager.Core.Log;
using HavcManager.Core.Manifest;
using HavcManager.Core.Runtime;

namespace HavcManager.Core.Install;

/// <summary>Progress notification emitted by the manager-side flow.</summary>
/// <param name="Kind">"phase" | "download" | "log".</param>
public sealed record FlowEvent(string Kind, string Message, long Done = 0, long Total = 0);

/// <summary>Everything the fresh-install / update flow needs (PHASE1_SPEC §6.2–§6.3).</summary>
public sealed record InstallPlan(
    ReleaseManifest Manifest,
    string InstallDir,
    bool WithDinov2 = true,
    string? DefaultModel = null,
    Func<IReadOnlyList<string>, bool>? ConfirmConfigUpdates = null,
    Func<bool>? ConfirmGuiSettings = null);

/// <summary>Parameters of a repair run (§6.4): cached wheel, no downloads.</summary>
public sealed record RepairPlan(
    string InstallDir,
    string PythonExe,
    string WheelPath,
    string? RuntimeArchive = null,
    bool WithDinov2 = true,
    string? DefaultModel = null,
    Func<IReadOnlyList<string>, bool>? ConfirmConfigUpdates = null,
    Func<bool>? ConfirmGuiSettings = null);

public sealed record InstallOutcome(bool Ok, int BootstrapExitCode, string? Error);

/// <summary>
/// Manager-side orchestration (PHASE1_SPEC §6.2–§6.4):
/// fresh install = folders → downloads → stage 1 → stage 2;
/// update = the same flow (the per-file sha256 check in the cache makes it
/// incremental, §6.3 step 3); repair = stage 1 + stage 2 on the cached wheel
/// with no downloads. Bootstrap progress events are raised through
/// <see cref="Runner"/>.
/// </summary>
public sealed class InstallFlow
{
    private readonly Downloader _downloader;

    public BootstrapRunner Runner { get; } = new();

    public InstallFlow(Downloader? downloader = null)
        => _downloader = downloader ?? new Downloader();

    public async Task<InstallOutcome> RunAsync(
        InstallPlan plan,
        Action<FlowEvent>? observe = null,
        CancellationToken cancellationToken = default)
    {
        var log = new ManagerLog(plan.InstallDir);
        try
        {
            observe?.Invoke(new FlowEvent("phase", "Preparing folders"));
            foreach (string dir in new[]
                     {
                         plan.InstallDir,
                         Path.Combine(plan.InstallDir, "cache"),
                         Path.Combine(plan.InstallDir, "cache", "assets"),
                         Path.Combine(plan.InstallDir, "logs"),
                     })
            {
                Directory.CreateDirectory(dir);
            }
            log.Info($"install/update started: havc {plan.Manifest.AppVersion} -> {plan.InstallDir}");

            observe?.Invoke(new FlowEvent("phase", "Downloading components"));
            string cacheDir = Path.Combine(plan.InstallDir, "cache");
            foreach (PlannedDownload item in DownloadPlan.FromManifest(plan.Manifest))
            {
                cancellationToken.ThrowIfCancellationRequested();
                string subdir = item.CacheSubfolder.Length == 0
                    ? cacheDir
                    : Path.Combine(cacheDir, item.CacheSubfolder);
                observe?.Invoke(new FlowEvent("download", item.Name, 0, item.Size));

                long lastReported = -1;
                var progress = new Progress<long>(done =>
                {
                    if (done - lastReported >= 1 << 20 || (item.Size > 0 && done >= item.Size))
                    {
                        lastReported = done;
                        observe?.Invoke(new FlowEvent("download", item.Name, done, item.Size));
                    }
                });
                string path = await _downloader
                    .GetAsync(item.Url, item.Name, subdir, item.Sha256, item.Size, progress, cancellationToken)
                    .ConfigureAwait(false);
                observe?.Invoke(new FlowEvent("download", item.Name, item.Size, item.Size));
                log.Info($"downloaded {item.Name} -> {path}");
            }

            var projectWheel = plan.Manifest.Wheels.FirstOrDefault(w => w.Kind == "project")
                               ?? plan.Manifest.Wheels.FirstOrDefault()
                               ?? throw new InvalidDataException("the manifest has no project wheel");
            string wheelPath = Path.Combine(cacheDir, projectWheel.Name);
            string pythonExe = PythonRuntime.PythonExePath(plan.InstallDir);

            observe?.Invoke(new FlowEvent("phase", "Preparing the Python runtime"));
            if (plan.Manifest.Runtime is { } runtime)
            {
                string archive = Path.Combine(cacheDir, runtime.Name);
                bool extracted = await PythonRuntime
                    .EnsureExtractedAsync(archive, plan.InstallDir, cancellationToken)
                    .ConfigureAwait(false);
                log.Info(extracted ? "runtime extracted" : "runtime already provisioned");
            }

            observe?.Invoke(new FlowEvent("phase", "Installing the havc wheel into the runtime"));
            int pipExit = await PipInstallWheelAsync(
                pythonExe, wheelPath, plan.InstallDir, observe, log, cancellationToken).ConfigureAwait(false);
            if (pipExit != 0)
                return new InstallOutcome(false, pipExit, $"pip install failed (exit {pipExit})");
            cancellationToken.ThrowIfCancellationRequested();

            return await RunStage2Async(
                plan.InstallDir, pythonExe, wheelPath, plan.WithDinov2, plan.DefaultModel,
                plan.ConfirmConfigUpdates, plan.ConfirmGuiSettings, observe, log,
                cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            log.Warn("run canceled");
            return new InstallOutcome(false, -1, "canceled");
        }
        catch (Exception ex)
        {
            log.Error($"run failed: {ex}");
            return new InstallOutcome(false, -1, ex.Message);
        }
    }

    /// <summary>Repair (§6.4): stage 1 + stage 2 on the cached wheel, no downloads.</summary>
    public async Task<InstallOutcome> RunRepairAsync(
        RepairPlan plan,
        Action<FlowEvent>? observe = null,
        CancellationToken cancellationToken = default)
    {
        var log = new ManagerLog(plan.InstallDir);
        try
        {
            log.Info($"repair started: wheel {Path.GetFileName(plan.WheelPath)} -> {plan.InstallDir}");
            string cacheDir = Path.Combine(plan.InstallDir, "cache");
            Directory.CreateDirectory(cacheDir);

            observe?.Invoke(new FlowEvent("phase", "Preparing the Python runtime"));
            if (!PythonRuntime.IsProvisioned(plan.InstallDir)
                && plan.RuntimeArchive is { } archive && File.Exists(archive))
            {
                await PythonRuntime
                    .EnsureExtractedAsync(archive, plan.InstallDir, cancellationToken)
                    .ConfigureAwait(false);
            }

            observe?.Invoke(new FlowEvent("phase", "Installing the havc wheel into the runtime"));
            int pipExit = await PipInstallWheelAsync(
                plan.PythonExe, plan.WheelPath, plan.InstallDir, observe, log, cancellationToken).ConfigureAwait(false);
            if (pipExit != 0)
                return new InstallOutcome(false, pipExit, $"pip install failed (exit {pipExit})");
            cancellationToken.ThrowIfCancellationRequested();

            return await RunStage2Async(
                plan.InstallDir, plan.PythonExe, plan.WheelPath, plan.WithDinov2, plan.DefaultModel,
                plan.ConfirmConfigUpdates, plan.ConfirmGuiSettings, observe, log,
                cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            log.Warn("repair canceled");
            return new InstallOutcome(false, -1, "canceled");
        }
        catch (Exception ex)
        {
            log.Error($"repair failed: {ex}");
            return new InstallOutcome(false, -1, ex.Message);
        }
    }

    private async Task<InstallOutcome> RunStage2Async(
        string installDir,
        string pythonExe,
        string wheelPath,
        bool withDinov2,
        string? defaultModel,
        Func<IReadOnlyList<string>, bool>? confirmConfigUpdates,
        Func<bool>? confirmGuiSettings,
        Action<FlowEvent>? observe,
        ManagerLog log,
        CancellationToken cancellationToken)
    {
        observe?.Invoke(new FlowEvent("phase", "Running the installer"));
        bool updateConfigs = false;
        if (confirmConfigUpdates is not null)
        {
            IReadOnlyList<string> differing = ConfigSetUpdate.DifferingConfigs(wheelPath, installDir);
            if (differing.Count > 0)
            {
                observe?.Invoke(new FlowEvent(
                    "phase", $"Pipeline configs differ: {string.Join(", ", differing)}"));
                updateConfigs = confirmConfigUpdates(differing);
                log.Info("config update confirmation: " +
                         (updateConfigs ? "replace" : "keep") + 
                         $" ({string.Join(", ", differing)})");
            }
        }
        bool updateGuiSettings = false;
        if (confirmGuiSettings is not null && GuiSettingsUpdate.Differs(wheelPath, installDir, defaultModel))
        {
            observe?.Invoke(new FlowEvent("phase", "GUI settings differ from the packaged defaults"));
            updateGuiSettings = confirmGuiSettings();
            log.Info("gui settings update confirmation: " + (updateGuiSettings ? "replace" : "keep"));
        }
        var invocation = new BootstrapInvocation
        {
            PythonExe = pythonExe,
            InstallDir = installDir,
            WheelPath = wheelPath,
            AssetsDir = Path.Combine(installDir, "cache", "assets"),
            WithDinov2 = withDinov2,
            DefaultModel = defaultModel,
            UpdateConfigs = updateConfigs,
            UpdateGuiSettings = updateGuiSettings,
        };
        BootstrapResult result = await Runner.RunAsync(invocation, cancellationToken).ConfigureAwait(false);
        log.Info($"bootstrap exit {result.ExitCode}, ok={result.Ok}");
        return result.Ok
            ? new InstallOutcome(true, result.ExitCode, null)
            : new InstallOutcome(false, result.ExitCode, $"the installer failed (exit {result.ExitCode})");
    }

    private static async Task<int> PipInstallWheelAsync(
        string pythonExe,
        string wheelPath,
        string installDir,
        Action<FlowEvent>? observe,
        ManagerLog log,
        CancellationToken cancellationToken)
    {
        var stage1Lines = new List<string>();
        int exit = await RunCapturedAsync(
            pythonExe,
            new[] { "-m", "pip", "install", "--force-reinstall", "--no-deps", wheelPath },
            installDir,
            line =>
            {
                stage1Lines.Add(line);
                if (stage1Lines.Count > 200)
                    stage1Lines.RemoveAt(0);
                observe?.Invoke(new FlowEvent("log", line));
            },
            cancellationToken).ConfigureAwait(false);
        if (exit != 0)
        {
            foreach (string line in stage1Lines)
                log.Error("stage1: " + line);
        }
        return exit;
    }

    private static async Task<int> RunCapturedAsync(
        string exe,
        IReadOnlyList<string> arguments,
        string workingDirectory,
        Action<string> onLine,
        CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo(exe)
        {
            WorkingDirectory = workingDirectory,
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (string argument in arguments)
            psi.ArgumentList.Add(argument);

        using var process = new Process { StartInfo = psi };
        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null)
                onLine(e.Data);
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null)
                onLine(e.Data);
        };
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        using var registration = cancellationToken.Register(() =>
        {
            try
            {
                if (!process.HasExited)
                    process.Kill(entireProcessTree: true);
            }
            catch (InvalidOperationException)
            {
            }
            catch (System.ComponentModel.Win32Exception)
            {
            }
        });
        await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false);
        process.WaitForExit();
        return process.ExitCode;
    }
}
