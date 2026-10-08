using System.Diagnostics;
using HavcManager.Core.Deployment;

namespace HavcManager.Core.Tests;

public class InstallTreeCleanupTests
{
    [Fact]
    public void Delete_keeps_the_user_files_when_requested()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            File.WriteAllText(Path.Combine(dir, "HAVCManager.exe"), "x");
            string keepModels = Path.Combine(dir, "comfy_bridge", "models", "unet");
            Directory.CreateDirectory(keepModels);
            File.WriteAllText(Path.Combine(keepModels, "model.safetensors"), "data");
            Directory.CreateDirectory(Path.Combine(dir, "comfy_bridge", "comfy"));
            File.WriteAllText(Path.Combine(dir, "comfy_bridge", "folder_paths.py"), "code");
            string guiDir = Path.Combine(dir, "gui");
            Directory.CreateDirectory(Path.Combine(guiDir, "scripts"));
            File.WriteAllText(Path.Combine(guiDir, "scripts", "encode.vpy"), "script");
            File.WriteAllText(Path.Combine(guiDir, "gui_cmnet2_settings.json"), "{}");
            string configDir = Path.Combine(dir, "config");
            Directory.CreateDirectory(configDir);
            File.WriteAllText(Path.Combine(configDir, "qwen_gguf_q4.json"), "{}");
            File.WriteAllText(Path.Combine(configDir, "my_custom_model.json"), "{}");

            InstallTreeCleanup.Delete(dir, keepUserFiles: true);

            Assert.False(File.Exists(Path.Combine(dir, "HAVCManager.exe")));
            Assert.False(File.Exists(Path.Combine(dir, "comfy_bridge", "folder_paths.py")));
            Assert.False(Directory.Exists(Path.Combine(dir, "comfy_bridge", "comfy")));
            Assert.True(File.Exists(Path.Combine(keepModels, "model.safetensors")));
            Assert.False(Directory.Exists(Path.Combine(guiDir, "scripts")));
            Assert.True(File.Exists(Path.Combine(guiDir, "gui_cmnet2_settings.json")));
            Assert.True(File.Exists(Path.Combine(configDir, "qwen_gguf_q4.json")));
            Assert.True(File.Exists(Path.Combine(configDir, "my_custom_model.json")));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Delete_removes_everything_when_the_user_files_are_not_kept()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            Directory.CreateDirectory(Path.Combine(dir, "comfy_bridge", "models"));
            File.WriteAllText(Path.Combine(dir, "comfy_bridge", "models", "m.bin"), "data");
            Directory.CreateDirectory(Path.Combine(dir, "gui"));
            File.WriteAllText(Path.Combine(dir, "gui", "gui_cmnet2_settings.json"), "{}");
            Directory.CreateDirectory(Path.Combine(dir, "config"));
            File.WriteAllText(Path.Combine(dir, "config", "qwen_gguf_q4.json"), "{}");
            File.WriteAllText(Path.Combine(dir, "file.txt"), "x");

            InstallTreeCleanup.Delete(dir, keepUserFiles: false);

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
        InstallTreeCleanup.Delete(dir, keepUserFiles: true);
        Assert.False(Directory.Exists(dir));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Delete_handles_the_venv_junction(bool keepUserFiles)
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
            Directory.CreateDirectory(Path.Combine(dir, "gui"));
            File.WriteAllText(Path.Combine(dir, "gui", "gui_cmnet2_settings.json"), "{}");
            Directory.CreateDirectory(Path.Combine(dir, "config"));
            File.WriteAllText(Path.Combine(dir, "config", "qwen_gguf_q4.json"), "{}");
            string link = Path.Combine(dir, ".venv");
            CreateJunction(link, Path.Combine(dir, "venv"));
            Assert.True(File.Exists(Path.Combine(link, "Scripts", "python.exe")));

            InstallTreeCleanup.Delete(dir, keepUserFiles);

            if (keepUserFiles)
            {
                Assert.True(File.Exists(Path.Combine(dir, "comfy_bridge", "models", "m.bin")));
                Assert.True(File.Exists(Path.Combine(dir, "gui", "gui_cmnet2_settings.json")));
                Assert.True(File.Exists(Path.Combine(dir, "config", "qwen_gguf_q4.json")));
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
