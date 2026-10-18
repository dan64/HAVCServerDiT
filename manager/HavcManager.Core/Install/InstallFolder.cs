using System.IO;
using HavcManager.Core.State;

namespace HavcManager.Core.Install;

/// <summary>
/// Install-folder handling for the wizard (2026-10-18). Two rules:
/// <list type="bullet">
/// <item>a folder picked at a drive root means "install on this drive", so the
/// product folder name is appended (<c>E:\</c> → <c>E:\HAVCServerDiT</c>);</item>
/// <item>a folder that already holds files is confirmed before the installer
/// writes into it, and an existing installation found there is called out
/// explicitly.</item>
/// </list>
/// </summary>
public static class InstallFolder
{
    /// <summary>Folder created under a drive root (and the product folder name).</summary>
    public const string FolderName = "HAVCServerDiT";

    /// <summary>
    /// Trimmed path without surrounding quotes and without a trailing separator
    /// (<c>D:\HAVC\</c> → <c>D:\HAVC</c>). A drive root keeps its separator
    /// (<c>E:</c> and <c>E:\</c> both become <c>E:\</c>), and an empty or
    /// whitespace-only value stays empty.
    /// </summary>
    public static string Normalize(string? input)
    {
        string path = (input ?? "").Trim().Trim('"').Trim();
        if (path.Length == 0)
            return "";
        if (path.Length == 2 && char.IsLetter(path[0]) && path[1] == ':')
            return path + Path.DirectorySeparatorChar;  // "E:" -> "E:\"
        string trimmed = path.TrimEnd(
            Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (trimmed.Length == 0)
            return path;  // a bare separator: leave it alone
        return trimmed.Length == 2 && trimmed[1] == ':'
            ? trimmed + Path.DirectorySeparatorChar  // "E:" after trimming
            : trimmed;
    }

    /// <summary>
    /// <see cref="Normalize"/> plus the product folder when the path is a drive
    /// root: <c>E:\</c> → <c>E:\HAVCServerDiT</c>. A folder the user picked
    /// explicitly is kept as-is.
    /// </summary>
    public static string Complete(string? input)
    {
        string path = Normalize(input);
        if (path.Length == 0)
            return "";
        return IsRoot(path) ? Path.Combine(path, FolderName) : path;
    }

    /// <summary>True when the path is a drive root (<c>C:\</c>) or a share root.</summary>
    public static bool IsRoot(string path)
    {
        try
        {
            string full = Path.GetFullPath(path);
            string root = Path.GetPathRoot(full) ?? "";
            return root.Length > 0
                   && string.Equals(TrimSeparator(root), TrimSeparator(full),
                                    StringComparison.OrdinalIgnoreCase);
        }
        catch (ArgumentException)
        {
            return false;
        }
        catch (NotSupportedException)
        {
            return false;
        }
        catch (PathTooLongException)
        {
            return false;
        }
    }

    /// <summary>True when the path is absolute (a drive path or a UNC path).</summary>
    public static bool IsAbsolute(string path)
    {
        try
        {
            return Path.IsPathFullyQualified(path);
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    /// <summary>
    /// Entry count in the folder (files + directories, hidden ones included);
    /// 0 when the folder does not exist or cannot be read.
    /// </summary>
    public static int CountEntries(string path)
    {
        try
        {
            if (!Directory.Exists(path))
                return 0;
            return Directory.EnumerateFileSystemEntries(path).Count();
        }
        catch (IOException)
        {
            return 0;
        }
        catch (UnauthorizedAccessException)
        {
            return 0;
        }
    }

    /// <summary>True when the folder holds an installation (install.json).</summary>
    public static bool ContainsInstallation(string path)
    {
        try
        {
            return File.Exists(Path.Combine(path, StateStore.FileName));
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    /// <summary>
    /// Version recorded in the folder's install.json, or empty when there is
    /// none (or the file cannot be read).
    /// </summary>
    public static string InstallationVersion(string path)
    {
        try
        {
            return new StateStore().Load(path)?.AppVersion ?? "";
        }
        catch (System.Text.Json.JsonException)
        {
            return "";
        }
        catch (IOException)
        {
            return "";
        }
        catch (UnauthorizedAccessException)
        {
            return "";
        }
    }

    /// <summary>
    /// True when the drive/share the path lives on is reachable. Missing local
    /// drives answer immediately; a dead network share may take a moment.
    /// </summary>
    public static bool RootExists(string path)
    {
        try
        {
            string? root = Path.GetPathRoot(Path.GetFullPath(path));
            return string.IsNullOrEmpty(root) || Directory.Exists(root);
        }
        catch (ArgumentException)
        {
            return false;
        }
        catch (NotSupportedException)
        {
            return false;
        }
        catch (PathTooLongException)
        {
            return false;
        }
    }

    private static string TrimSeparator(string path)
        => path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
}
