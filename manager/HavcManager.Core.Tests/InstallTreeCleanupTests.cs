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
}
