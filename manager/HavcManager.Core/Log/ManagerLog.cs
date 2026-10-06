namespace HavcManager.Core.Log;

/// <summary>
/// Append-only manager log: <install>\logs\manager-&lt;yyyyMMdd&gt;.log
/// (PHASE1_SPEC §9). One file per day; only the newest 10 files are kept
/// (simple rotation, pruned when a log is opened).
/// </summary>
public sealed class ManagerLog
{
    private const int Retention = 10;
    private readonly string _filePath;
    private readonly object _gate = new();

    public ManagerLog(string installDir)
    {
        string logsDir = Path.Combine(installDir, "logs");
        _filePath = Path.Combine(logsDir, $"manager-{DateTime.Now:yyyyMMdd}.log");
        PruneOlderFiles(logsDir);
    }

    public void Info(string message) => Write("INFO", message);

    public void Warn(string message) => Write("WARN", message);

    public void Error(string message) => Write("ERROR", message);

    /// <summary>Keeps only the newest <see cref="Retention"/> manager-*.log files.</summary>
    private static void PruneOlderFiles(string logsDir)
    {
        try
        {
            if (!Directory.Exists(logsDir))
                return;
            FileInfo[] files = new DirectoryInfo(logsDir).GetFiles("manager-*.log");
            if (files.Length <= Retention)
                return;
            foreach (FileInfo file in files
                         .OrderByDescending(f => f.Name, StringComparer.Ordinal)
                         .Skip(Retention))
            {
                file.Delete();
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

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
