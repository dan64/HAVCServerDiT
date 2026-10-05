using System.IO;
using HavcManager.Core.State;
using Microsoft.Win32;

namespace HavcManager.App.Windows;

/// <summary>Detected installation, with its install.json state.</summary>
public sealed record ExistingInstall(string InstallDir, InstallState State);

/// <summary>
/// Finds an existing installation (PHASE1_SPEC §6.1): explicit --install-dir,
/// then HKCU\Software\HAVCServerDiT\InstallDir, then the default folder —
/// each accepted only with a valid install.json.
/// </summary>
public static class InstallLocator
{
    public static string DefaultInstallDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "HAVCServerDiT");

    public static ExistingInstall? FindExisting(string? explicitDir)
    {
        foreach (string? candidate in Candidates(explicitDir))
        {
            if (string.IsNullOrWhiteSpace(candidate))
                continue;
            var state = new StateStore().Load(candidate);
            if (state is not null)
                return new ExistingInstall(candidate, state);
        }
        return null;
    }

    private static IEnumerable<string?> Candidates(string? explicitDir)
    {
        if (!string.IsNullOrWhiteSpace(explicitDir))
        {
            // An explicit folder is authoritative: do not look elsewhere.
            yield return explicitDir;
            yield break;
        }
        yield return RegistryInstallDir();
        yield return DefaultInstallDir;
    }

    private static string? RegistryInstallDir()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\HAVCServerDiT");
            return key?.GetValue("InstallDir") as string;
        }
        catch (System.Security.SecurityException)
        {
            return null;
        }
    }
}
