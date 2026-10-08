using System.Diagnostics;
using System.IO;
using HavcManager.Core.Deployment;

namespace HavcManager.App.Windows;

/// <summary>
/// Self-removal worker (PHASE1_SPEC §6.5): the manager copies itself to %TEMP%
/// and re-launches with --uninstall-run &lt;dir&gt;; this worker waits for the
/// original process to release the files, deletes the install folder (keeping
/// the user files — model weights and GUI settings — unless asked otherwise)
/// and removes its own temporary copy.
/// </summary>
internal static class UninstallWorker
{
    public static void Run(string installDir, bool keepUserFiles)
    {
        InstallTreeCleanup.Delete(installDir, keepUserFiles);

        string? self = Environment.ProcessPath;
        if (self is not null)
        {
            try
            {
                string? selfDir = Path.GetDirectoryName(self);
                string parentName = string.IsNullOrEmpty(selfDir) ? "" : Path.GetFileName(selfDir);
                string command = parentName.StartsWith("HAVCManager-uninstall-", StringComparison.OrdinalIgnoreCase)
                    // Dedicated temp folder: remove the whole copy (exe + companions).
                    ? $"ping -n 2 127.0.0.1 >nul & rmdir /s /q \"{selfDir}\""
                    : $"ping -n 2 127.0.0.1 >nul & del /f /q \"{self}\"";
                Process.Start(new ProcessStartInfo("cmd.exe", "/c " + command)
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                });
            }
            catch (System.ComponentModel.Win32Exception)
            {
            }
        }
    }
}
