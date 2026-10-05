using System.Diagnostics;

namespace HavcManager.Core.Processes;

/// <summary>
/// Verifies that no server/GUI instance is running from the install folder
/// before touching the venv (PHASE1_SPEC §6.6): enumerates python.exe /
/// pythonw.exe processes whose executable lives under <install> and can
/// terminate them on request.
/// </summary>
public sealed class ProcessGuard
{
    /// <summary>Processes running from inside <paramref name="installDir"/>.</summary>
    public IReadOnlyList<ProcessInfo> FindRunning(string installDir)
    {
        string root = Path.GetFullPath(installDir)
            .TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var found = new List<ProcessInfo>();
        foreach (string name in new[] { "python", "pythonw" })
        {
            foreach (Process process in Process.GetProcessesByName(name))
            {
                try
                {
                    if (process.Id == Environment.ProcessId)
                        continue;
                    string? path = process.MainModule?.FileName;
                    if (path is not null && path.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        found.Add(new ProcessInfo(process.Id, path));
                }
                catch (InvalidOperationException)
                {
                }
                catch (System.ComponentModel.Win32Exception)
                {
                    // access denied (other user / elevated): not ours to inspect
                }
                finally
                {
                    process.Dispose();
                }
            }
        }
        return found;
    }

    /// <summary>Terminates the given processes, whole tree, best effort.</summary>
    public static void Terminate(IEnumerable<ProcessInfo> processes)
    {
        foreach (ProcessInfo info in processes)
        {
            try
            {
                using Process process = Process.GetProcessById(info.Pid);
                process.Kill(entireProcessTree: true);
            }
            catch (ArgumentException)
            {
                // already exited
            }
            catch (InvalidOperationException)
            {
            }
            catch (System.ComponentModel.Win32Exception)
            {
            }
        }
    }
}

/// <summary>Minimal process reference (pid + executable path).</summary>
public sealed record ProcessInfo(int Pid, string ExecutablePath);
