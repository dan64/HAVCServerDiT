namespace HavcManager.Core.Processes;

/// <summary>
/// Verifies that no server/GUI instance is running from the install folder
/// before touching the venv (PHASE1_SPEC §6.6): enumerate python.exe /
/// pythonw.exe under <install> and let the UI offer Retry / Terminate.
/// </summary>
public sealed class ProcessGuard
{
    /// <summary>Processes running from inside <paramref name="installDir"/>.</summary>
    public IReadOnlyList<ProcessInfo> FindRunning(string installDir)
        => throw new NotImplementedException("M3: enumerate processes under the install folder.");
}

/// <summary>Minimal process reference (pid + executable path).</summary>
public sealed record ProcessInfo(int Pid, string ExecutablePath);
