namespace HavcManager.Core.Log;

/// <summary>
/// Append-only manager log: <install>\logs\manager-&lt;yyyyMMdd&gt;.log
/// (PHASE1_SPEC §9). One file per day.
/// TODO: retention of the last 10 files.
/// </summary>
public sealed class ManagerLog
{
    private readonly string _filePath;
    private readonly object _gate = new();

    public ManagerLog(string installDir)
        => _filePath = Path.Combine(installDir, "logs", $"manager-{DateTime.Now:yyyyMMdd}.log");

    public void Info(string message) => Write("INFO", message);

    public void Warn(string message) => Write("WARN", message);

    public void Error(string message) => Write("ERROR", message);

    private void Write(string level, string message)
    {
        string line = $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss} {level} {message}";
        lock (_gate)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_filePath)!);
            File.AppendAllText(_filePath, line + Environment.NewLine);
        }
    }
}
