using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace HavcManager.Core.Bootstrap;

/// <summary>
/// Runs the bootstrap as a child process and streams its --json-progress events
/// (PHASE1_SPEC §5). Standard invocation:
///   runtime\python -m havc.install --install-dir ... --wheel ... --assets-dir ...
///   --with-dinov2 --models-dir ... --json-progress
/// Exit codes: 0 = ok (all-skip counts as ok), 1 = step failed, 2 = usage error.
/// The working directory is always the install folder (never a source checkout).
/// </summary>
public sealed class BootstrapRunner
{
    /// <summary>
    /// Sentinel file checked by the bootstrap between steps: when present it
    /// aborts before starting the next step (manager Cancel button, §6.2/§8).
    /// </summary>
    public const string StopRequestFileName = ".stop-request";

    private static readonly JsonSerializerOptions JsonOptions = new() { AllowTrailingCommas = true };

    /// <summary>Raised for every progress event emitted by the bootstrap.</summary>
    public event EventHandler<BootstrapEvent>? EventReceived;

    internal void RaiseEvent(BootstrapEvent bootstrapEvent) => EventReceived?.Invoke(this, bootstrapEvent);

    /// <summary>Requests a graceful stop: the bootstrap aborts after the current step.</summary>
    public static void RequestStop(string installDir)
    {
        string cacheDir = Path.Combine(installDir, "cache");
        Directory.CreateDirectory(cacheDir);
        File.WriteAllText(Path.Combine(cacheDir, StopRequestFileName), "1");
    }

    /// <summary>Removes a stale stop-request file.</summary>
    public static void ClearStopRequest(string installDir)
    {
        try
        {
            File.Delete(Path.Combine(installDir, "cache", StopRequestFileName));
        }
        catch (DirectoryNotFoundException)
        {
        }
        catch (FileNotFoundException)
        {
        }
    }

    /// <summary>
    /// Runs the bootstrap and returns the final result. Raw stdout events are
    /// also written to <install>\logs\bootstrap-&lt;timestamp&gt;.jsonl (§9).
    /// A run succeeds only with exit code 0 <b>and</b> a result event with ok=true.
    /// </summary>
    public async Task<BootstrapResult> RunAsync(
        BootstrapInvocation invocation,
        CancellationToken cancellationToken = default)
    {
        ClearStopRequest(invocation.InstallDir);

        var psi = new ProcessStartInfo(invocation.PythonExe)
        {
            WorkingDirectory = invocation.InstallDir,
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (string argument in BuildArguments(invocation))
            psi.ArgumentList.Add(argument);

        string logDir = Path.Combine(invocation.InstallDir, "logs");
        Directory.CreateDirectory(logDir);
        string logPath = Path.Combine(logDir, $"bootstrap-{DateTime.Now:yyyyMMdd-HHmmss}.jsonl");

        bool? resultOk = null;
        using var logWriter = new StreamWriter(logPath, append: true, Encoding.UTF8) { AutoFlush = true };
        object logGate = new();

        using var process = new Process { StartInfo = psi };
        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is null)
                return;
            lock (logGate)
            {
                logWriter.WriteLine(e.Data);
            }
            BootstrapEvent? parsed = TryParse(e.Data);
            if (parsed is null)
            {
                RaiseEvent(new BootstrapEvent { Kind = "log", Message = e.Data });
                return;
            }
            if (parsed.Kind == "result")
                resultOk = parsed.Ok ?? false;
            RaiseEvent(parsed);
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
                RaiseEvent(new BootstrapEvent { Kind = "log", Message = e.Data });
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        using var registration = cancellationToken.Register(() => TryKill(process));
        await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false);
        process.WaitForExit(); // flush the async output handlers

        bool ok = process.ExitCode == 0 && resultOk == true;
        return new BootstrapResult(process.ExitCode, ok);
    }

    private static IEnumerable<string> BuildArguments(BootstrapInvocation invocation)
    {
        yield return "-m";
        yield return "havc.install";
        yield return "--install-dir";
        yield return invocation.InstallDir;
        if (invocation.WheelPath is not null)
        {
            yield return "--wheel";
            yield return invocation.WheelPath;
        }
        if (invocation.AssetsDir is not null)
        {
            yield return "--assets-dir";
            yield return invocation.AssetsDir;
        }
        if (invocation.WithDinov2)
            yield return "--with-dinov2";
        if (invocation.ModelsDir is not null)
        {
            yield return "--models-dir";
            yield return invocation.ModelsDir;
        }
        foreach (string extra in invocation.ExtraArgs)
            yield return extra;
        yield return "--json-progress";
    }

    private static BootstrapEvent? TryParse(string line)
    {
        if (line.Length == 0 || line[0] != '{')
            return null;
        try
        {
            return JsonSerializer.Deserialize<BootstrapEvent>(line, JsonOptions);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static void TryKill(Process process)
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
    }
}
