using System.Diagnostics;
using System.IO;
using HavcManager.Core.Preflight;
using Microsoft.Win32;

namespace HavcManager.App.Windows;

/// <summary>
/// Windows shell integration (PHASE1_SPEC §6.2 step 7, §6.5): Start Menu /
/// desktop shortcuts, HKCU uninstall registration, launching the GUI/server,
/// copying the manager into the install folder.
/// </summary>
public static class ShellIntegration
{
    private const string ShortcutName = "HAVC.lnk";
    private const string ManagerShortcutName = "HAVC Manager.lnk";

    public static string StartMenuFolder =>
        Environment.GetFolderPath(Environment.SpecialFolder.Programs);

    public static string DesktopFolder =>
        Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);

    // ------------------------------------------------------------ shortcuts --
    public static void CreateStartMenuShortcuts(string installDir)
    {
        string icon = Path.Combine(installDir, "HAVCManager.exe");
        CreateShortcut(
            Path.Combine(StartMenuFolder, ShortcutName),
            Path.Combine(installDir, "HAVC.vbs"),
            installDir,
            icon);
        CreateShortcut(
            Path.Combine(StartMenuFolder, ManagerShortcutName),
            Path.Combine(installDir, "HAVCManager.exe"),
            installDir,
            icon);
    }

    public static void CreateDesktopShortcut(string installDir)
        => CreateShortcut(
            Path.Combine(DesktopFolder, ShortcutName),
            Path.Combine(installDir, "HAVC.vbs"),
            installDir,
            Path.Combine(installDir, "HAVCManager.exe"));

    public static void RemoveShortcuts()
    {
        foreach (string path in new[]
                 {
                     Path.Combine(StartMenuFolder, ShortcutName),
                     Path.Combine(StartMenuFolder, ManagerShortcutName),
                     Path.Combine(DesktopFolder, ShortcutName),
                 })
        {
            try
            {
                File.Delete(path);
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }

    // ----------------------------------------------------------- registration --
    public static void RegisterUninstall(string installDir, string version)
    {
        using var key = Registry.CurrentUser.CreateSubKey(@"Software\HAVCServerDiT");
        key?.SetValue("InstallDir", installDir);

        using var uninstall = Registry.CurrentUser.CreateSubKey(
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall\HAVCServerDiT");
        if (uninstall is null)
            return;
        string managerExe = Path.Combine(installDir, "HAVCManager.exe");
        uninstall.SetValue("DisplayName", "HAVC Server + GUI");
        uninstall.SetValue("DisplayIcon", managerExe);
        uninstall.SetValue("DisplayVersion", version);
        uninstall.SetValue("Publisher", "dan64");
        uninstall.SetValue("InstallLocation", installDir);
        uninstall.SetValue("UninstallString", $"\"{managerExe}\" --uninstall");
    }

    public static void UnregisterUninstall()
    {
        try
        {
            Registry.CurrentUser.DeleteSubKeyTree(
                @"Software\Microsoft\Windows\CurrentVersion\Uninstall\HAVCServerDiT",
                throwOnMissingSubKey: false);
        }
        catch (System.Security.SecurityException)
        {
        }
        try
        {
            Registry.CurrentUser.DeleteSubKeyTree(@"Software\HAVCServerDiT", throwOnMissingSubKey: false);
        }
        catch (System.Security.SecurityException)
        {
        }
    }

    // --------------------------------------------------------------- launching --
    /// <summary>
    /// Copies the manager application next to <paramref name="targetExePath"/> so
    /// the copy runs standalone (PHASE1_SPEC §6.2 step 7, §6.5). A
    /// framework-dependent build also needs its managed assemblies and host
    /// files next to the apphost; a single-file publish needs only the exe
    /// (Assembly.Location is empty, nothing external to copy).
    /// </summary>
    public static void CopyApplicationFiles(string sourceExePath, string targetExePath)
    {
        string target = Path.GetFullPath(targetExePath);
        if (string.Equals(Path.GetFullPath(sourceExePath), target, StringComparison.OrdinalIgnoreCase))
            return;
        string targetDir = Path.GetDirectoryName(target)!;
        Directory.CreateDirectory(targetDir);
        File.Copy(sourceExePath, target, overwrite: true);
        foreach (Type anchor in new[] { typeof(ShellIntegration), typeof(PreflightReport) })
        {
            string location = anchor.Assembly.Location;
            if (string.IsNullOrEmpty(location))
                continue;  // single-file publish: the exe is self-contained
            string baseName = Path.GetFileNameWithoutExtension(location);
            string sourceDir = Path.GetDirectoryName(location)!;
            foreach (string suffix in new[] { ".dll", ".deps.json", ".runtimeconfig.json" })
            {
                string source = Path.Combine(sourceDir, baseName + suffix);
                if (File.Exists(source))
                    File.Copy(source, Path.Combine(targetDir, baseName + suffix), overwrite: true);
            }
        }
    }

    public static void CopyManagerFiles(string targetExePath)
    {
        if (Environment.ProcessPath is { } self)
            CopyApplicationFiles(self, targetExePath);
    }

    public static void CopyManagerTo(string installDir)
        => CopyManagerFiles(Path.Combine(installDir, "HAVCManager.exe"));

    public static void LaunchGui(string installDir)
        => StartShell(Path.Combine(installDir, "HAVC.vbs"), "", installDir);

    public static void StartServer(string installDir, string backend)
        => StartShell(Path.Combine(installDir, "HAVC-Server.cmd"), backend, installDir);

    public static void OpenFolder(string path)
    {
        if (!Directory.Exists(path))
            Directory.CreateDirectory(path);
        Process.Start(new ProcessStartInfo("explorer.exe", $"\"{path}\"") { UseShellExecute = true });
    }

    public static void OpenUrl(string url)
        => Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });

    public static void OpenLogs(string installDir)
        => OpenFolder(Path.Combine(installDir, "logs"));

    // ---------------------------------------------------------------- helpers --
    private static void StartShell(string fileName, string arguments, string workingDirectory)
        => Process.Start(new ProcessStartInfo(fileName, arguments)
        {
            UseShellExecute = true,
            WorkingDirectory = workingDirectory,
        });

    private static void CreateShortcut(string linkPath, string targetPath, string workingDirectory, string iconPath)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(linkPath)!);
        Type? shellType = Type.GetTypeFromProgID("WScript.Shell")
            ?? throw new InvalidOperationException("WScript.Shell is not available");
        dynamic shell = Activator.CreateInstance(shellType)!;
        dynamic link = shell.CreateShortcut(linkPath);
        link.TargetPath = targetPath;
        link.WorkingDirectory = workingDirectory;
        link.IconLocation = iconPath;
        link.Save();
    }
}
