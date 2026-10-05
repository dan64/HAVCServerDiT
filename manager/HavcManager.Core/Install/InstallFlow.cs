using System.Diagnostics;
using System.Text;
using HavcManager.Core.Bootstrap;
using HavcManager.Core.Download;
using HavcManager.Core.Log;
using HavcManager.Core.Manifest;
using HavcManager.Core.Runtime;

namespace HavcManager.Core.Install;

/// <summary>Progress notification emitted by the manager-side install flow.</summary>
/// <param name="Kind">"phase" | "download" | "log".</param>
public sealed record FlowEvent(string Kind, string Message, long Done = 0, long Total = 0);

/// <summary>Everything the fresh-install flow needs (PHASE1_SPEC §6.2).</summary>
public sealed record InstallPlan(
    ReleaseManifest Manifest,
    string InstallDir,
    string ModelsDir,
    bool WithDinov2 = true);

public sealed record InstallOutcome(bool Ok, int BootstrapExitCode, string? Error);

/// <summary>
/// Fresh-install orchestration (PHASE1_SPEC §6.2): folders → downloads →
/// stage 1 (runtime extraction + wheel into the runtime) → stage 2 (bootstrap
/// with live --json-progress events, exposed through <see cref="Runner"/>).
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
                         plan.ModelsDir,
                         Path.Combine(plan.ModelsDir, "hf-cache"),
                         Path.Combine(plan.ModelsDir, "comfy"),
                     })
            {
                Directory.CreateDirectory(dir);
            }
            log.Info($"install started: havc {plan.Manifest.AppVersion} -> {plan.InstallDir}");

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
            var stage1Lines = new List<string>();
            int pipExit = await RunCapturedAsync(
                pythonExe,
                new[] { "-m", "pip", "install", "--force-reinstall", "--no-deps", wheelPath },
                plan.InstallDir,
                line =>
                {
                    stage1Lines.Add(line);
                    if (stage1Lines.Count > 200)
                        stage1Lines.RemoveAt(0);
                    observe?.Invoke(new FlowEvent("log", line));
                },
                cancellationToken).ConfigureAwait(false);
            if (pipExit != 0)
            {
                foreach (string line in stage1Lines)
                    log.Error("stage1: " + line);
                return new InstallOutcome(false, pipExit, $"pip install failed (exit {pipExit})");
            }
            cancellationToken.ThrowIfCancellationRequested();

            observe?.Invoke(new FlowEvent("phase", "Running the installer"));
            var invocation = new BootstrapInvocation
            {
                PythonExe = pythonExe,
                InstallDir = plan.InstallDir,
                WheelPath = wheelPath,
                AssetsDir = Path.Combine(cacheDir, "assets"),
                ModelsDir = plan.ModelsDir,
                WithDinov2 = plan.WithDinov2,
            };
            BootstrapResult result = await Runner.RunAsync(invocation, cancellationToken).ConfigureAwait(false);
            log.Info($"bootstrap exit {result.ExitCode}, ok={result.Ok}");
            return result.Ok
                ? new InstallOutcome(true, result.ExitCode, null)
                : new InstallOutcome(false, result.ExitCode, $"the installer failed (exit {result.ExitCode})");
        }
        catch (OperationCanceledException)
        {
            log.Warn("install canceled");
            return new InstallOutcome(false, -1, "canceled");
        }
        catch (Exception ex)
        {
            log.Error($"install failed: {ex}");
            return new InstallOutcome(false, -1, ex.Message);
        }
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
