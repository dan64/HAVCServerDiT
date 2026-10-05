using System.Text.Json;
using System.Text.Json.Serialization;

namespace HavcManager.Core.State;

/// <summary>
/// Reads and writes <install>\install.json (PHASE1_SPEC §4).
/// </summary>
public sealed class StateStore
{
    public const string FileName = "install.json";

    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    /// <summary>Returns the stored state, or null when no installation is present.</summary>
    public InstallState? Load(string installDir)
    {
        string path = Path.Combine(installDir, FileName);
        if (!File.Exists(path))
            return null;
        return JsonSerializer.Deserialize<InstallState>(File.ReadAllText(path), Options);
    }

    /// <summary>Writes the state (write-to-temp + atomic replace).</summary>
    public void Save(string installDir, InstallState state)
    {
        Directory.CreateDirectory(installDir);
        string path = Path.Combine(installDir, FileName);
        string temporary = path + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(state, Options) + "\n");
        File.Move(temporary, path, overwrite: true);
    }
}
