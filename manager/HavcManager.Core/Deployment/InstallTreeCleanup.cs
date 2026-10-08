using System.IO;

namespace HavcManager.Core.Deployment;

/// <summary>
/// Removal of an install folder (PHASE1_SPEC §6.5, 2026-10-05; user files
/// 2026-10-08): everything goes — except the *user files*, which are
/// preserved unless the user explicitly asks to delete them:
/// `<install>\comfy_bridge\models` (the model weights: they live inside the
/// install folder because that is what the runtime reads, and a reinstall to
/// the same path reuses them without re-downloading),
/// `<install>\gui\gui_cmnet2_settings.json` (the GUI settings the user
/// configured — a reinstall resumes from them) and `<install>\config` (the
/// pipeline configuration files, including configs the user added or edited —
/// a reinstall compares them against the packaged ones and asks before
/// replacing any).
/// </summary>
public static class InstallTreeCleanup
{
    private const int Retries = 40;
    private static readonly TimeSpan RetryDelay = TimeSpan.FromMilliseconds(500);

    public static void Delete(string installDir, bool keepUserFiles)
    {
        if (!Directory.Exists(installDir))
            return;
        for (int attempt = 0; ; attempt++)
        {
            try
            {
                DeleteCore(installDir, keepUserFiles);
                return;
            }
            catch (IOException) when (attempt < Retries)
            {
                Thread.Sleep(RetryDelay);
            }
            catch (UnauthorizedAccessException) when (attempt < Retries)
            {
                Thread.Sleep(RetryDelay);
            }
        }
    }

    private static void DeleteCore(string installDir, bool keepUserFiles)
    {
        if (!keepUserFiles)
        {
            Directory.Delete(installDir, recursive: true);
            return;
        }

        string comfyDir = Path.Combine(installDir, "comfy_bridge");
        string guiDir = Path.Combine(installDir, "gui");
        string configDir = Path.Combine(installDir, "config");
        string keepModels = Path.Combine(installDir, "comfy_bridge", "models");
        string keepSettings = Path.Combine(installDir, "gui", "gui_cmnet2_settings.json");
        foreach (string entry in Directory.GetFileSystemEntries(installDir))
        {
            string full = Path.GetFullPath(entry);
            if (string.Equals(full, Path.GetFullPath(comfyDir), StringComparison.OrdinalIgnoreCase))
            {
                DeleteChildrenExcept(comfyDir, keepModels);
            }
            else if (string.Equals(full, Path.GetFullPath(guiDir), StringComparison.OrdinalIgnoreCase))
            {
                DeleteChildrenExcept(guiDir, keepSettings);
            }
            else if (string.Equals(full, Path.GetFullPath(configDir), StringComparison.OrdinalIgnoreCase))
            {
                // <install>\config — pipeline configurations, kept whole.
            }
            else
            {
                DeleteEntry(entry);
            }
        }
    }

    private static void DeleteChildrenExcept(string dir, string keep)
    {
        foreach (string child in Directory.GetFileSystemEntries(dir))
        {
            if (string.Equals(Path.GetFullPath(child), Path.GetFullPath(keep), StringComparison.OrdinalIgnoreCase))
                continue;
            DeleteEntry(child);
        }
    }

    private static void DeleteEntry(string path)
    {
        if (Directory.Exists(path))
            Directory.Delete(path, recursive: true);
        else if (File.Exists(path))
            File.Delete(path);
    }
}
