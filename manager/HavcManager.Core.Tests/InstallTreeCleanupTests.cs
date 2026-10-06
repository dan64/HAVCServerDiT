using System.Diagnostics;
using HavcManager.Core.Deployment;

namespace HavcManager.Core.Tests;

public class InstallTreeCleanupTests
{
    [Fact]
    public void Delete_keeps_comfy_models_when_requested()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            File.WriteAllText(Path.Combine(dir, "HAVCManager.exe"), "x");
            string keep = Path.Combine(dir, "comfy_bridge", "models", "unet");
            Directory.CreateDirectory(keep);
            File.WriteAllText(Path.Combine(keep, "model.safetensors"), "data");
            Directory.CreateDirectory(Path.Combine(dir, "comfy_bridge", "comfy"));
            File.WriteAllText(Path.Combine(dir, "comfy_bridge", "folder_paths.py"), "code");

            InstallTreeCleanup.Delete(dir, keepComfyModels: true);

            Assert.False(File.Exists(Path.Combine(dir, "HAVCManager.exe")));
            Assert.False(File.Exists(Path.Combine(dir, "comfy_bridge", "folder_paths.py")));
            Assert.False(Directory.Exists(Path.Combine(dir, "comfy_bridge", "comfy")));
            Assert.True(File.Exists(Path.Combine(keep, "model.safetensors")));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Delete_removes_everything_when_models_are_not_kept()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            Directory.CreateDirectory(Path.Combine(dir, "comfy_bridge", "models"));
            File.WriteAllText(Path.Combine(dir, "comfy_bridge", "models", "m.bin"), "data");
            File.WriteAllText(Path.Combine(dir, "file.txt"), "x");

            InstallTreeCleanup.Delete(dir, keepComfyModels: false);

            Assert.False(Directory.Exists(dir));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Delete_is_a_noop_when_the_folder_is_gone()
    {
        string dir = Path.Combine(Path.GetTempPath(), $"havc-missing-{Guid.NewGuid():N}");
        InstallTreeCleanup.Delete(dir, keepComfyModels: true);
        Assert.False(Directory.Exists(dir));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Delete_handles_the_venv_junction(bool keepComfyModels)
    {
        // The bootstrap creates `<install>\.venv` as a junction to `venv`
        // (the dev-layout path the HAVC GUI probes for its managed server).
        // The uninstaller must remove the link (and the tree) without
        // tripping on the reparse point.
        string dir = TestPaths.NewTempDir();
        try
        {
            Directory.CreateDirectory(Path.Combine(dir, "venv", "Scripts"));
            File.WriteAllText(Path.Combine(dir, "venv", "Scripts", "python.exe"), "x");
            Directory.CreateDirectory(Path.Combine(dir, "comfy_bridge", "models"));
            File.WriteAllText(Path.Combine(dir, "comfy_bridge", "models", "m.bin"), "data");
            string link = Path.Combine(dir, ".venv");
            CreateJunction(link, Path.Combine(dir, "venv"));
            Assert.True(File.Exists(Path.Combine(link, "Scripts", "python.exe")));

            InstallTreeCleanup.Delete(dir, keepComfyModels);

            if (keepComfyModels)
            {
                Assert.True(File.Exists(Path.Combine(dir, "comfy_bridge", "models", "m.bin")));
                Assert.False(Directory.Exists(Path.Combine(dir, "venv")));
                Assert.DoesNotContain(
                    Directory.GetFileSystemEntries(dir),
                    e => Path.GetFileName(e).Equals(".venv", StringComparison.OrdinalIgnoreCase));
            }
            else
            {
                Assert.False(Directory.Exists(dir));
            }
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    private static void CreateJunction(string link, string target)
    {
        var psi = new ProcessStartInfo("cmd.exe", $"/c mklink /J \"{link}\" \"{target}\"")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        using var proc = Process.Start(psi)!;
        proc.WaitForExit();
        Assert.Equal(0, proc.ExitCode);
    }
}
