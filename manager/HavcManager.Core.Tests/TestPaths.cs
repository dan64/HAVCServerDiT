namespace HavcManager.Core.Tests;

internal static class TestPaths
{
    public static string NewTempDir()
    {
        string dir = Path.Combine(Path.GetTempPath(), "havc-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        return dir;
    }

    public static void Delete(string dir)
    {
        try
        {
            Directory.Delete(dir, recursive: true);
        }
        catch (IOException)
        {
            // best effort cleanup
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}
