namespace HavcManager.Core.State;

/// <summary>
/// Reads and writes <install>\install.json (PHASE1_SPEC §4).
/// </summary>
public sealed class StateStore
{
    public const string FileName = "install.json";

    /// <summary>Returns the stored state, or null when no installation is present.</summary>
    public InstallState? Load(string installDir)
        => throw new NotImplementedException("M2: read + parse install.json.");

    /// <summary>Writes the state (atomic replace).</summary>
    public void Save(string installDir, InstallState state)
        => throw new NotImplementedException("M2: write install.json.");
}
