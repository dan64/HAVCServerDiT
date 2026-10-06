using System.Diagnostics;
using System.Formats.Tar;
using System.IO.Compression;
using System.Text;

namespace HavcManager.Core.Runtime;

/// <summary>
/// Stage 1 of the two-stage install (PHASE1_SPEC §6.2 step 5): extracts the
/// pinned python-build-standalone archive (tar.gz with a 'python/' root) into
/// <install>\runtime, so that <install>\runtime\python\python.exe exists.
/// </summary>
public static class PythonRuntime
{
    public static string PythonExePath(string installDir) =>
        Path.Combine(installDir, "runtime", "python", "python.exe");

    public static bool IsProvisioned(string installDir) => File.Exists(PythonExePath(installDir));

    /// <summary>
    /// Extracts the runtime archive unless already provisioned.
    /// Returns true when extraction happened, false when it was skipped.
    /// </summary>
    public static async Task<bool> EnsureExtractedAsync(
        string archivePath,
        string installDir,
        CancellationToken cancellationToken = default)
    {
        if (IsProvisioned(installDir))
            return false;

        string target = Path.GetFullPath(Path.Combine(installDir, "runtime"));
        Directory.CreateDirectory(target);

        await using var file = File.OpenRead(archivePath);
        await using var gzip = new GZipStream(file, CompressionMode.Decompress);
        using var reader = new TarReader(gzip);
        bool sawRoot = false;
        TarEntry? entry;
        while ((entry = await reader
                   .GetNextEntryAsync(cancellationToken: cancellationToken)
                   .ConfigureAwait(false)) is not null)
        {
            string name = entry.Name.Replace('\\', '/').TrimStart('/');
            if (name.Length == 0)
                continue;
            if (!sawRoot)
            {
                sawRoot = true;
                if (name != "python" && !name.StartsWith("python/", StringComparison.Ordinal))
                    throw new InvalidDataException(
                        $"unexpected runtime archive layout (missing 'python/' root): {name}");
            }

            string destination = Path.GetFullPath(Path.Combine(target, name));
            if (destination.Length <= target.Length ||
                !destination.StartsWith(target + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"archive entry escapes the target folder: {name}");
            }

            switch (entry.EntryType)
            {
                case TarEntryType.Directory:
                    Directory.CreateDirectory(destination);
                    break;
                case TarEntryType.RegularFile:
                case TarEntryType.V7RegularFile:
                    Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                    entry.ExtractToFile(destination, overwrite: true);
                    break;
                default:
                    throw new InvalidDataException(
                        $"unsupported entry in the runtime archive ({entry.EntryType}): {name}");
            }
        }

        if (!sawRoot)
            throw new InvalidDataException("the runtime archive is empty");
        if (!IsProvisioned(installDir))
            throw new InvalidDataException("extraction finished but python.exe was not found");
        return true;
    }

    /// <summary>Version reported by the provisioned interpreter, or null when unavailable.</summary>
    public static async Task<string?> ProbeVersionAsync(string installDir, CancellationToken cancellationToken = default)
    {
        string python = PythonExePath(installDir);
        if (!File.Exists(python))
            return null;
        try
        {
            var psi = new ProcessStartInfo(python)
            {
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
                WorkingDirectory = installDir,
            };
            psi.ArgumentList.Add("-c");
            psi.ArgumentList.Add("import sys;print(sys.version.split()[0])");
            using var process = Process.Start(psi);
            if (process is null)
                return null;
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(60));
            string output = await process.StandardOutput.ReadToEndAsync(timeout.Token).ConfigureAwait(false);
            await process.StandardError.ReadToEndAsync(timeout.Token).ConfigureAwait(false);
            await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
            string version = output.Trim();
            return process.ExitCode == 0 && version.Length > 0 ? version : null;
        }
        catch (OperationCanceledException)
        {
            return null;
        }
        catch (Exception)
        {
            return null;
        }
    }
}
