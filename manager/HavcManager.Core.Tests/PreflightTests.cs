using static HavcManager.Core.Preflight.Preflight;

namespace HavcManager.Core.Tests;

public class PreflightTests
{
    private const long GiB = 1024L * 1024 * 1024;

    [Fact]
    public void DecideDefaultModel_switches_to_longcat_below_32_gb()
    {
        Assert.Equal("longcat-gguf", DecideDefaultModel(16 * GiB));
        Assert.Equal("longcat-gguf", DecideDefaultModel(32 * GiB - 1));
    }

    [Fact]
    public void DecideDefaultModel_keeps_qwen21_at_or_above_32_gb()
    {
        Assert.Equal("qwen21-viggle", DecideDefaultModel(32 * GiB));
        Assert.Equal("qwen21-viggle", DecideDefaultModel(128 * GiB));
    }

    [Fact]
    public void DecideDefaultModel_keeps_qwen21_when_ram_is_unknown()
    {
        Assert.Equal("qwen21-viggle", DecideDefaultModel(null));
    }
}
