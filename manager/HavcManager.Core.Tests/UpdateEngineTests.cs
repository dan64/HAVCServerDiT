using HavcManager.Core.Manifest;
using HavcManager.Core.State;
using HavcManager.Core.Update;

namespace HavcManager.Core.Tests;

public class UpdateEngineTests
{
    private static ReleaseManifest Manifest(string version, bool rebuild = false)
        => new() { AppVersion = version, RequiresEnvRebuild = rebuild };

    [Fact]
    public void Classifies_up_to_date_when_versions_match()
        => Assert.Equal(
            UpdateClassification.UpToDate,
            UpdateEngine.Classify(Manifest("0.1.3"), new InstallState { AppVersion = "0.1.3" }));

    [Fact]
    public void Classifies_update_when_versions_differ()
        => Assert.Equal(
            UpdateClassification.UpdateAvailable,
            UpdateEngine.Classify(Manifest("0.1.4"), new InstallState { AppVersion = "0.1.3" }));

    [Fact]
    public void Classifies_rebuild_required_when_the_manifest_asks_for_it()
        => Assert.Equal(
            UpdateClassification.RebuildRequired,
            UpdateEngine.Classify(Manifest("0.2.0", rebuild: true), new InstallState { AppVersion = "0.1.3" }));

    [Fact]
    public void Finds_the_cached_wheel_for_a_version()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            File.WriteAllText(Path.Combine(dir, "havc-0.1.3-py3-none-any.whl"), "x");
            File.WriteAllText(Path.Combine(dir, "havc-0.1.2-py3-none-any.whl"), "x");
            File.WriteAllText(Path.Combine(dir, "diffusers-0.37.0.dev0-py3-none-any.whl"), "x");

            Assert.EndsWith("havc-0.1.3-py3-none-any.whl", UpdateEngine.FindCachedWheel(dir, "0.1.3"));
            Assert.EndsWith("havc-0.1.2-py3-none-any.whl", UpdateEngine.FindCachedWheel(dir, "0.1.2"));
            Assert.Null(UpdateEngine.FindCachedWheel(dir, "0.9.9"));
            Assert.Null(UpdateEngine.FindCachedWheel(dir, null));
            Assert.Null(UpdateEngine.FindCachedWheel(Path.Combine(dir, "missing"), "0.1.3"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }
}
