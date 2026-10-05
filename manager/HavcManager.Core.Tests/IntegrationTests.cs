using System.Diagnostics;
using System.Text;
using HavcManager.Core.Bootstrap;
using HavcManager.Core.Download;
using HavcManager.Core.Manifest;
using HavcManager.Core.Runtime;

namespace HavcManager.Core.Tests;

/// <summary>
/// Integration tests against real artifacts. Disabled by default; run with
/// HAVC_RUN_INTEGRATION=1 (and HAVC_TEST_WHEEL pointing at a freshly built
/// havc wheel for the scratch bootstrap test).
/// </summary>
public class IntegrationTests
{
    private const string TestInstall = @"D:\HAVCServerDiT_Test";
    private const string RuntimeArchiveName =
        "cpython-3.12.15+20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz";

    private static bool Enabled => Environment.GetEnvironmentVariable("HAVC_RUN_INTEGRATION") == "1";

    [Fact]
    public async Task Scratch_runtime_extract_and_bootstrap_plan()
    {
        if (!Enabled)
            return;
        string archive = Path.Combine(TestInstall, "cache", RuntimeArchiveName);
        string? wheel = Environment.GetEnvironmentVariable("HAVC_TEST_WHEEL");
        if (!File.Exists(archive) || string.IsNullOrEmpty(wheel) || !File.Exists(wheel))
            return; // environment not ready: keep the suite green on dev machines

        string scratch = TestPaths.NewTempDir();
        try
        {
            // stage 1: extract the pinned runtime and check the interpreter
            bool extracted = await PythonRuntime.EnsureExtractedAsync(archive, scratch);
            Assert.True(extracted);
            string? version = await PythonRuntime.ProbeVersionAsync(scratch);
            Assert.StartsWith("3.12", version ?? "");

            // stage 1 (pip): install the freshly built wheel into the scratch runtime
            int pipExit = await RunAsync(
                PythonRuntime.PythonExePath(scratch),
                new[] { "-m", "pip", "install", "--force-reinstall", "--no-deps", wheel },
                scratch);
            Assert.Equal(0, pipExit);

            // stage 2 (plan): the manager runner against the new code, with --models-dir
            Directory.CreateDirectory(Path.Combine(scratch, "gui"));
            var runner = new BootstrapRunner();
            var events = new List<BootstrapEvent>();
            runner.EventReceived += (_, e) =>
            {
                lock (events)
                    events.Add(e);
            };
            var result = await runner.RunAsync(new BootstrapInvocation
            {
                PythonExe = PythonRuntime.PythonExePath(scratch),
                InstallDir = scratch,
                WheelPath = wheel,
                AssetsDir = Path.Combine(scratch, "cache", "assets"),
                ModelsDir = Path.Combine(scratch, "models"),
                WithDinov2 = true,
                ExtraArgs = new[] { "--plan" },
            });

            Assert.Equal(0, result.ExitCode);
            Assert.Contains(events, e => e.Kind == "plan");
            Assert.True(Directory.GetFiles(Path.Combine(scratch, "logs"), "bootstrap-*.jsonl").Length >= 1);
        }
        finally
        {
            TestPaths.Delete(scratch);
        }
    }

    [Fact]
    public async Task Downloads_a_published_wheel_and_verifies_sha256()
    {
        if (!Enabled)
            return;
        const string manifestUrl =
            "https://github.com/dan64/HAVCServerDiT/releases/download/v0.1.0-alpha/release.json";
        var manifest = await new ManifestClient().FetchAsync(manifestUrl);
        var wheel = manifest.Wheels.FirstOrDefault();
        if (wheel is null)
            return;

        string cache = TestPaths.NewTempDir();
        try
        {
            string path = await new Downloader()
                .GetAsync(wheel.Url, wheel.Name, cache, wheel.Sha256, wheel.Size);
            Assert.True(File.Exists(path));
            Assert.Equal(wheel.Sha256, await Downloader.Sha256Async(path));
        }
        finally
        {
            TestPaths.Delete(cache);
        }
    }

    private static async Task<int> RunAsync(string exe, IReadOnlyList<string> arguments, string workingDirectory)
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
        using var process = Process.Start(psi)!;
        await process.WaitForExitAsync();
        return process.ExitCode;
    }
}
