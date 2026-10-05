using HavcManager.Core.State;

namespace HavcManager.Core.Tests;

public class StateStoreTests
{
    [Fact]
    public void Load_returns_null_when_no_installation_is_present()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            Assert.Null(new StateStore().Load(dir));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Roundtrip_preserves_the_schema_v1_fields()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            var store = new StateStore();
            var state = new InstallState
            {
                ManagerVersion = "0.1.0",
                AppVersion = "0.1.1",
                InstalledAt = "2026-10-05T12:00:00Z",
                InstallDir = dir,
                ModelsDir = @"C:\models",
                Runtime = new RuntimeState { Name = "rt", Sha256 = "aa", Python = "3.12.15" },
                Dinov2 = true,
                BackendDefault = "fp4",
                LastVerify = new LastVerifyState { Ts = "2026-10-05T12:00:00Z", Ok = true, AppVersion = "0.1.1" },
            };
            store.Save(dir, state);

            var loaded = store.Load(dir)!;
            Assert.Equal("0.1.0", loaded.ManagerVersion);
            Assert.Equal("0.1.1", loaded.AppVersion);
            Assert.Equal(@"C:\models", loaded.ModelsDir);
            Assert.Equal("fp4", loaded.BackendDefault);
            Assert.True(loaded.Dinov2);
            Assert.Equal("3.12.15", loaded.Runtime!.Python);
            Assert.True(loaded.LastVerify!.Ok);
            Assert.Equal(new[] { "server", "gui" }, loaded.Components);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Additive_unknown_fields_do_not_break_loading()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            File.WriteAllText(Path.Combine(dir, StateStore.FileName),
                """{"schema": 1, "app_version": "0.2.0", "lock_hash": "abc", "future": {"nested": true}}""");
            var loaded = new StateStore().Load(dir)!;
            Assert.Equal("0.2.0", loaded.AppVersion);
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }
}
