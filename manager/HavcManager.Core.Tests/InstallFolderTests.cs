using HavcManager.Core.Install;
using HavcManager.Core.State;

namespace HavcManager.Core.Tests;

public class InstallFolderTests
{
    [Fact]
    public void Complete_appends_the_product_folder_to_a_drive_root()
    {
        // The reported bug (2026-10-18): picking drive E: installed into "E:\".
        Assert.Equal(@"E:\HAVCServerDiT", InstallFolder.Complete(@"E:\"));
        Assert.Equal(@"E:\HAVCServerDiT", InstallFolder.Complete("E:"));
        Assert.Equal(@"E:\HAVCServerDiT", InstallFolder.Complete(@"  ""E:\""  "));
    }

    [Theory]
    [InlineData(@"D:\Apps\HAVC")]
    [InlineData(@"D:\Apps\HAVC\")]
    [InlineData(@"D:\HAVCServerDiT")]
    public void Complete_keeps_a_folder_the_user_picked(string picked)
        => Assert.Equal(picked.TrimEnd('\\'), InstallFolder.Complete(picked));

    [Fact]
    public void Complete_rejects_nothing_but_an_empty_value()
    {
        Assert.Equal("", InstallFolder.Complete(null));
        Assert.Equal("", InstallFolder.Complete("   "));
        Assert.Equal("", InstallFolder.Complete("\"\""));
    }

    [Fact]
    public void Normalize_drops_a_trailing_separator_but_keeps_a_root()
    {
        Assert.Equal(@"D:\Apps\HAVC", InstallFolder.Normalize(@"D:\Apps\HAVC\"));
        Assert.Equal(@"E:\", InstallFolder.Normalize("E:"));
        Assert.Equal(@"E:\", InstallFolder.Normalize(@"E:\"));
    }

    [Fact]
    public void IsRoot_tells_a_drive_root_from_a_folder()
    {
        Assert.True(InstallFolder.IsRoot(@"E:\"));
        Assert.False(InstallFolder.IsRoot(@"E:\HAVCServerDiT"));
        Assert.False(InstallFolder.IsRoot(@"D:\Apps\HAVC"));
    }

    [Fact]
    public void IsAbsolute_rejects_relative_paths()
    {
        Assert.True(InstallFolder.IsAbsolute(@"D:\HAVCServerDiT"));
        Assert.False(InstallFolder.IsAbsolute("HAVCServerDiT"));
        Assert.False(InstallFolder.IsAbsolute(@"..\HAVCServerDiT"));
    }

    [Fact]
    public void CountEntries_counts_files_and_folders_and_zero_when_missing()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            Assert.Equal(0, InstallFolder.CountEntries(dir));
            File.WriteAllText(Path.Combine(dir, "a.txt"), "x");
            Directory.CreateDirectory(Path.Combine(dir, "sub"));
            Assert.Equal(2, InstallFolder.CountEntries(dir));
            Assert.Equal(0, InstallFolder.CountEntries(Path.Combine(dir, "does-not-exist")));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void ContainsInstallation_reads_install_json_and_its_version()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            Assert.False(InstallFolder.ContainsInstallation(dir));
            Assert.Equal("", InstallFolder.InstallationVersion(dir));

            new StateStore().Save(dir, new InstallState
            {
                ManagerVersion = "2.7.1",
                AppVersion = "2.7.0",
                InstallDir = dir,
            });

            Assert.True(InstallFolder.ContainsInstallation(dir));
            Assert.Equal("2.7.0", InstallFolder.InstallationVersion(dir));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }
}
