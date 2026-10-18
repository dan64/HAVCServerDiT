using HavcManager.Core.Preflight;
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

    [Fact]
    public void DescribeStorage_warns_on_an_hdd_below_64_gb_of_ram()
    {
        var check = DescribeStorage(StorageKind.Hdd, 32 * GiB);
        Assert.NotNull(check);
        Assert.Equal(PreflightStatus.Warning, check!.Status);
        Assert.Contains("32.0 GB", check.Detail!);
        Assert.Contains("SSD", check.Detail!);
    }

    [Fact]
    public void DescribeStorage_accepts_an_hdd_at_or_above_64_gb_of_ram()
    {
        var check = DescribeStorage(StorageKind.Hdd, 64 * GiB);
        Assert.NotNull(check);
        Assert.Equal(PreflightStatus.Ok, check!.Status);
    }

    [Fact]
    public void DescribeStorage_accepts_an_ssd_and_stays_silent_when_unknown()
    {
        Assert.Equal(PreflightStatus.Ok, DescribeStorage(StorageKind.Ssd, 16 * GiB)!.Status);
        Assert.Null(DescribeStorage(StorageKind.Unknown, 16 * GiB));
    }

    [Fact]
    public void DescribeStorage_does_not_warn_without_a_ram_reading()
    {
        Assert.Null(DescribeStorage(StorageKind.Unknown, null));
        // A known HDD with unknown RAM: the check still reports the medium but
        // cannot justify the warning, so it stays Ok rather than guessing.
        Assert.Equal(PreflightStatus.Ok, DescribeStorage(StorageKind.Hdd, null)!.Status);
    }

    [Fact]
    public void StorageMedia_returns_unknown_for_unc_and_missing_drives()
    {
        Assert.Equal(StorageKind.Unknown, StorageMedia.KindForPath(@"\\server\share\havc"));
        Assert.Equal(StorageKind.Unknown, StorageMedia.KindForPath(@"Q:\HAVCServerDiT"));
    }
}
