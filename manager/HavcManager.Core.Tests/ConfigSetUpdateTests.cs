using System.IO.Compression;
using HavcManager.Core.Install;

namespace HavcManager.Core.Tests;

public class ConfigSetUpdateTests
{
    [Fact]
    public void Differing_configs_are_reported()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string wheel = WriteWheel(dir, ("qwen_gguf_q3.json", "{\"a\": 1}\n"));
            Directory.CreateDirectory(Path.Combine(dir, "config"));
            File.WriteAllText(Path.Combine(dir, "config", "qwen_gguf_q3.json"), "{\"a\": 2}\n");

            IReadOnlyList<string> differing = ConfigSetUpdate.DifferingConfigs(wheel, dir);

            Assert.Equal(new[] { "qwen_gguf_q3.json" }, differing);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Identical_configs_are_not_reported()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string wheel = WriteWheel(dir, ("longcat_gguf_q3.json", "{\"b\": true}\n"));
            Directory.CreateDirectory(Path.Combine(dir, "config"));
            File.WriteAllText(Path.Combine(dir, "config", "longcat_gguf_q3.json"), "{\"b\": true}\n");

            IReadOnlyList<string> differing = ConfigSetUpdate.DifferingConfigs(wheel, dir);

            Assert.Empty(differing);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Missing_installed_configs_are_not_reported()
    {
        // New configs are copied by the bootstrap without confirmation.
        string dir = TestPaths.NewTempDir();
        try
        {
            string wheel = WriteWheel(dir, ("qwen_nunchaku_fp4.json", "{\"c\": 3}\n"));

            IReadOnlyList<string> differing = ConfigSetUpdate.DifferingConfigs(wheel, dir);

            Assert.Empty(differing);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Local_only_configs_are_not_reported()
    {
        // Files the user added locally are never touched.
        string dir = TestPaths.NewTempDir();
        try
        {
            string wheel = WriteWheel(dir, ("qwen_gguf_q3.json", "{\"a\": 1}\n"));
            Directory.CreateDirectory(Path.Combine(dir, "config"));
            File.WriteAllText(Path.Combine(dir, "config", "qwen_gguf_q3.json"), "{\"a\": 1}\n");
            File.WriteAllText(Path.Combine(dir, "config", "my_custom.json"), "{\"mine\": true}\n");

            IReadOnlyList<string> differing = ConfigSetUpdate.DifferingConfigs(wheel, dir);

            Assert.Empty(differing);
            Assert.True(File.Exists(Path.Combine(dir, "config", "my_custom.json")));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    private static string WriteWheel(string dir, params (string Name, string Content)[] files)
    {
        string wheel = Path.Combine(dir, "havc-test-py3-none-any.whl");
        using var zip = ZipFile.Open(wheel, ZipArchiveMode.Create);
        foreach ((string name, string content) in files)
        {
            ZipArchiveEntry entry = zip.CreateEntry("havc/configs/" + name);
            using var writer = new StreamWriter(entry.Open());
            writer.Write(content);
        }
        return wheel;
    }
}
