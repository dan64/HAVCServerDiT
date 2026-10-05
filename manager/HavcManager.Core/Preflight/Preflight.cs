namespace HavcManager.Core.Preflight;

/// <summary>
/// First-run environment checks (PHASE1_SPEC §6.2 step 1): OS, nvidia-smi
/// (name/driver/VRAM), disk space (install ~15 GB; models warn below ~50 GB),
/// manifest reachability. Suggests the default backend from the detected GPU.
/// </summary>
public sealed class Preflight
{
    public Task<PreflightReport> RunAsync(CancellationToken cancellationToken = default)
        => throw new NotImplementedException("M2: environment checks.");
}

/// <summary>One check outcome.</summary>
public sealed record PreflightCheck(string Name, bool Ok, string? Detail);

/// <summary>Full outcome, with the suggested default backend (e.g. "fp4").</summary>
public sealed record PreflightReport(IReadOnlyList<PreflightCheck> Checks, string? SuggestedBackend);
