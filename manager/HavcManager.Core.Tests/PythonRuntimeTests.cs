using System.Formats.Tar;
using System.IO.Compression;
using System.Text;
using HavcManager.Core.Runtime;

namespace HavcManager.Core.Tests;

public class PythonRuntimeTests
{
    [Fact]
    public async Task Extracts_an_archive_with_a_python_root()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string archive = CreateArchive(dir, withPythonRoot: true);
            string installDir = Path.Combine(dir, "install");

            Assert.False(PythonRuntime.IsProvisioned(installDir));
            bool extracted = await PythonRuntime.EnsureExtractedAsync(archive, installDir);
            Assert.True(extracted);
            Assert.True(PythonRuntime.IsProvisioned(installDir));
            Assert.Equal("MZfake", File.ReadAllText(PythonRuntime.PythonExePath(installDir)));
            Assert.True(File.Exists(Path.Combine(installDir, "runtime", "python", "Lib", "os.py")));

            // already provisioned: second call is a no-op
            bool again = await PythonRuntime.EnsureExtractedAsync(archive, installDir);
            Assert.False(again);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public async Task Rejects_an_archive_without_a_python_root()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string archive = CreateArchive(dir, withPythonRoot: false);
            await Assert.ThrowsAsync<InvalidDataException>(
                () => PythonRuntime.EnsureExtractedAsync(archive, Path.Combine(dir, "install")));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    private static string CreateArchive(string dir, bool withPythonRoot)
    {
        string path = Path.Combine(dir, "runtime.tar.gz");
        string root = withPythonRoot ? "python/" : "lib/";
        using var file = File.Create(path);
        using var gzip = new GZipStream(file, CompressionLevel.Optimal);
        using var writer = new TarWriter(gzip, TarEntryFormat.Pax, leaveOpen: false);
        writer.WriteEntry(new PaxTarEntry(TarEntryType.Directory, root));
        writer.WriteEntry(new PaxTarEntry(TarEntryType.RegularFile, root + "python.exe")
        {
            DataStream = new MemoryStream(Encoding.ASCII.GetBytes("MZfake")),
        });
        writer.WriteEntry(new PaxTarEntry(TarEntryType.RegularFile, root + "Lib/os.py")
        {
            DataStream = new MemoryStream(new byte[] { 1, 2, 3 }),
        });
        return path;
    }
}
