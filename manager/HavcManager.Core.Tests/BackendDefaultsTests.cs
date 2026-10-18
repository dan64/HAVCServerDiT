using HavcManager.Core.Install;

namespace HavcManager.Core.Tests;

public class BackendDefaultsTests
{
    [Fact]
    public void Fp4_nominal_maps_to_the_2509_fp4_config()
        => Assert.Equal("qwen-2509-nunchaku_fp4", BackendDefaults.ArgFor("qwen25-nunchaku-fp4"));

    [Fact]
    public void Int4_nominal_maps_to_the_2509_int4_config()
        => Assert.Equal("qwen-2509-nunchaku_int4", BackendDefaults.ArgFor("qwen25-nunchaku-int4"));

    [Fact]
    public void Historical_viggle_value_still_maps_to_the_viggle_config()
        => Assert.Equal("qwen21_viggle-soft_int8", BackendDefaults.ArgFor("qwen21-viggle"));

    [Fact]
    public void Turbo_family_maps_to_the_turbo_config()
        => Assert.Equal("qwen21_turbo_int8", BackendDefaults.ArgFor("qwen21-turbo"));

    [Fact]
    public void Lighter_model_maps_to_longcat3()
        => Assert.Equal("longcat3", BackendDefaults.ArgFor("longcat-gguf"));

    [Fact]
    public void Unknown_family_falls_back_to_the_default()
        => Assert.Equal(BackendDefaults.DefaultArg, BackendDefaults.ArgFor(null));

    [Fact]
    public void Empty_stored_backend_resolves_to_the_default()
    {
        Assert.Equal(BackendDefaults.DefaultArg, BackendDefaults.Resolve(null));
        Assert.Equal(BackendDefaults.DefaultArg, BackendDefaults.Resolve(""));
    }

    [Fact]
    public void Legacy_qwen21_alias_resolves_to_the_default()
        => Assert.Equal(BackendDefaults.DefaultArg, BackendDefaults.Resolve("qwen21"));

    [Fact]
    public void Legacy_values_resolve_to_the_machine_default()
    {
        // 2026-10-18: an install whose state still says "qwen21" (or nothing)
        // follows the per-GPU rule instead of the int4 fallback.
        Assert.Equal("qwen-2509-nunchaku_fp4",
            BackendDefaults.Resolve("qwen21", "qwen25-nunchaku-fp4"));
        Assert.Equal("qwen-2509-nunchaku_int4",
            BackendDefaults.Resolve("qwen21", "qwen25-nunchaku-int4"));
        Assert.Equal("longcat3", BackendDefaults.Resolve(null, "longcat-gguf"));
    }

    [Fact]
    public void An_explicit_choice_is_never_migrated()
    {
        // A stored config name or alias is the user's choice: it survives the
        // migration even when the machine default differs.
        Assert.Equal("qwen-2509-nunchaku_int4",
            BackendDefaults.Resolve("qwen-2509-nunchaku_int4", "qwen25-nunchaku-fp4"));
        Assert.Equal("longcat3", BackendDefaults.Resolve("longcat3", "qwen25-nunchaku-fp4"));
        Assert.Equal("qwen21_viggle-soft_int8",
            BackendDefaults.MigrateLegacy("qwen21_viggle-soft_int8", "qwen25-nunchaku-fp4"));
    }

    [Fact]
    public void Migration_writes_the_machine_default_when_the_alias_is_legacy()
    {
        Assert.Equal("qwen-2509-nunchaku_fp4",
            BackendDefaults.MigrateLegacy("qwen21", "qwen25-nunchaku-fp4"));
        Assert.Equal("qwen-2509-nunchaku_int4",
            BackendDefaults.MigrateLegacy("", "qwen25-nunchaku-int4"));
        // No machine reading: the safe fallback (int4) is written.
        Assert.Equal(BackendDefaults.DefaultArg, BackendDefaults.MigrateLegacy("qwen21", null));
    }

    [Fact]
    public void Stored_arguments_pass_through()
    {
        Assert.Equal("longcat3", BackendDefaults.Resolve("longcat3"));
        Assert.Equal("qwen-2509-nunchaku_fp4", BackendDefaults.Resolve("qwen-2509-nunchaku_fp4"));
        Assert.Equal("qwen-2509-nunchaku_int4", BackendDefaults.Resolve("qwen-2509-nunchaku_int4"));
        Assert.Equal("qwen21_viggle-soft_int8", BackendDefaults.Resolve("qwen21_viggle-soft_int8"));
        Assert.Equal("fp4", BackendDefaults.Resolve("fp4"));
    }
}
