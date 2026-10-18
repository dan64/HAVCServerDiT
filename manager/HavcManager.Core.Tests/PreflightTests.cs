using HavcManager.Core.Preflight;
using static HavcManager.Core.Preflight.Preflight;

namespace HavcManager.Core.Tests;

public class PreflightTests
{
    private const long GiB = 1024L * 1024 * 1024;

    [Fact]
    public void Rounding_reads_a_nominal_size_as_itself()
    {
        // A 32 GB machine reports ~31.9 GB, a 24 GB one ~23.9 GB and a 12 GB
        // card 12282 MiB: none may be read as just below its own threshold.
        Assert.Equal(32, RoundToGiB((long)(31.9 * GiB)));
        Assert.Equal(24, RoundToGiB((long)(23.9 * GiB)));
        Assert.Equal(12, RoundMibToGiB(12282));
        Assert.Equal(16, RoundMibToGiB(16303));
    }

    [Fact]
    public void DecideDefaultModel_switches_to_longcat_below_12_gb_of_vram()
    {
        // Low VRAM alone is enough, even with plenty of RAM.
        Assert.Equal("longcat-gguf", DecideDefaultModel(64 * GiB, 8 * 1024));
        Assert.Equal("longcat-gguf", DecideDefaultModel(128 * GiB, 11 * 1024));
    }

    [Fact]
    public void DecideDefaultModel_switches_to_longcat_on_a_midrange_gpu_with_low_ram()
    {
        // VRAM <= 16 GB and RAM < 24 GB (the author's rule of 2026-10-18).
        Assert.Equal("longcat-gguf", DecideDefaultModel(16 * GiB, 16 * 1024));
        Assert.Equal("longcat-gguf", DecideDefaultModel(23 * GiB, 12 * 1024));
        Assert.Equal("longcat-gguf", DecideDefaultModel((long)(23.4 * GiB), 16303));
    }

    [Fact]
    public void DecideDefaultModel_keeps_qwen2509_nunchaku_otherwise()
    {
        // The whole point of the GB rounding: a 24 GB machine and a 12 GB card
        // stay above their thresholds.
        Assert.Equal("qwen25-nunchaku-int4", DecideDefaultModel((long)(23.9 * GiB), 12 * 1024));
        Assert.Equal("qwen25-nunchaku-int4", DecideDefaultModel((long)(31.9 * GiB), 12282));
        Assert.Equal("qwen25-nunchaku-int4", DecideDefaultModel(64 * GiB, 24 * 1024));
    }

    [Fact]
    public void DecideDefaultModel_picks_fp4_on_blackwell_and_int4_elsewhere()
    {
        Assert.Equal("qwen25-nunchaku-fp4", DecideDefaultModel(128 * GiB, 16303, blackwell: true));
        Assert.Equal("qwen25-nunchaku-int4", DecideDefaultModel(32 * GiB, 12282, blackwell: false));
        // A 24 GB card with 16 GB of RAM keeps the model: the 24 GB RAM clause
        // only applies to GPUs up to 16 GB.
        Assert.Equal("qwen25-nunchaku-int4", DecideDefaultModel(16 * GiB, 24 * 1024));
    }

    [Fact]
    public void DecideDefaultModel_uses_longcat_without_a_gpu_reading()
    {
        // Without VRAM the fp4/int4 half cannot be chosen: the lighter model.
        Assert.Equal("longcat-gguf", DecideDefaultModel(null));
        Assert.Equal("longcat-gguf", DecideDefaultModel(null, null));
        Assert.Equal("longcat-gguf", DecideDefaultModel(64 * GiB, null));
        Assert.Equal("longcat-gguf", DecideDefaultModel(null, 6 * 1024));
    }

    [Fact]
    public void DecideDefaultModel_matches_the_field_machines()
    {
        // RTX 3060 12 GB / 32 GB RAM: int4, the config tested at ~4.3 s/frame.
        Assert.Equal("qwen25-nunchaku-int4", DecideDefaultModel((long)(31.9 * GiB), 12288));
        // RTX 5070 Ti 16 GB / 112 GB RAM: fp4.
        Assert.Equal("qwen25-nunchaku-fp4", DecideDefaultModel(112 * GiB, 16303, blackwell: true));
        // The 8 GB / 16 GB machine: LongCat Q3 runs there.
        Assert.Equal("longcat-gguf", DecideDefaultModel(16 * GiB, 8 * 1024));
    }

    [Theory]
    [InlineData("NVIDIA GeForce RTX 5070 Ti", true)]
    [InlineData("NVIDIA GeForce RTX 5080 Laptop GPU", true)]
    [InlineData("NVIDIA GeForce RTX 5050", true)]
    [InlineData("NVIDIA RTX PRO 6000 Blackwell", true)]
    [InlineData("NVIDIA GeForce RTX 3060", false)]
    [InlineData("NVIDIA GeForce RTX 4080", false)]
    [InlineData("NVIDIA RTX 5000 Ada Generation", false)]
    public void LooksLikeBlackwell_reads_the_product_name(string name, bool expected)
        => Assert.Equal(expected, LooksLikeBlackwell(name));

    [Fact]
    public void LighterModelRequirementsText_quotes_the_field_tested_minimums()
    {
        string text = LighterModelRequirementsText();
        Assert.Contains("8 GB", text);
        Assert.Contains("16 GB", text);
        Assert.Contains("VRAM", text);
        Assert.Contains("RAM", text);
    }

    [Fact]
    public void DescribeStorage_warns_on_an_hdd_below_64_gb_of_ram()
    {
        var check = DescribeStorage(StorageKind.Hdd, 32 * GiB);
        Assert.NotNull(check);
        Assert.Equal(PreflightStatus.Warning, check!.Status);
        Assert.Contains("32 GB", check.Detail!);
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
