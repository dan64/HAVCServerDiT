using System.IO;

namespace HavcManager.Core.Deployment;

/// <summary>
/// Removal of an install folder (PHASE1_SPEC §6.5, 2026-10-05): everything
/// goes — except `<install>\comfy_bridge\models`, which is preserved unless
/// the user explicitly asks to delete the model files. The models live inside
/// the install folder (they are what the runtime reads); a reinstall to the
/// same path reuses them without re-downloading.
/// </summary>
public static class InstallTreeCleanup
{
    private const int Retries = 40;
    private static readonly TimeSpan RetryDelay = TimeSpan.FromMilliseconds(500);

    public static void Delete(string installDir, bool keepComfyModels)
    {
        if (!Directory.Exists(installDir))
            return;
        for (int attempt = 0; ; attempt++)
        {
            try
            {
                DeleteCore(installDir, keepComfyModels);
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

    private static void DeleteCore(string installDir, bool keepComfyModels)
    {
        if (!keepComfyModels)
        {
            Directory.Delete(installDir, recursive: true);
            return;
        }

        string comfyDir = Path.Combine(installDir, "comfy_bridge");
        string keepDir = Path.Combine(comfyDir, "models");
        foreach (string entry in Directory.GetFileSystemEntries(installDir))
        {
            if (string.Equals(Path.GetFullPath(entry), Path.GetFullPath(comfyDir), StringComparison.OrdinalIgnoreCase))
            {
                foreach (string child in Directory.GetFileSystemEntries(comfyDir))
                {
                    if (string.Equals(Path.GetFullPath(child), Path.GetFullPath(keepDir), StringComparison.OrdinalIgnoreCase))
                        continue;
                    DeleteEntry(child);
                }
            }
            else
            {
                DeleteEntry(entry);
            }
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
