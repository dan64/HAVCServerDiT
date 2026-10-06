using HavcManager.Core.Log;

namespace HavcManager.Core.Tests;

public class ManagerLogTests
{
    [Fact]
    public void Keeps_only_the_newest_ten_log_files()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string logsDir = Path.Combine(dir, "logs");
            Directory.CreateDirectory(logsDir);
            for (int day = 1; day <= 12; day++)
                File.WriteAllText(Path.Combine(logsDir, $"manager-202609{day:00}.log"), "x");

            _ = new ManagerLog(dir);

            string[] remaining = Directory.GetFiles(logsDir, "manager-*.log")
                .Select(Path.GetFileName)
                .OrderBy(n => n, StringComparer.Ordinal)
                .ToArray()!;
            Assert.Equal(10, remaining.Length);
            Assert.DoesNotContain("manager-20260901.log", remaining);
            Assert.DoesNotContain("manager-20260902.log", remaining);
            Assert.Contains("manager-20260912.log", remaining);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Appends_a_line_to_todays_file()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            var log = new ManagerLog(dir);
            log.Info("hello");

            string today = Path.Combine(dir, "logs", $"manager-{DateTime.Now:yyyyMMdd}.log");
            Assert.Contains("INFO hello", File.ReadAllText(today));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }
}
