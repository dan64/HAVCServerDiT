namespace HavcManager.Core.Update;

/// <summary>
/// Classifies an update as incremental or env rebuild, coordinates download,
/// bootstrap run and rollback after a failed verification (PHASE1_SPEC §6.3–§6.4).
/// v0: requires_env_rebuild blocks with the manual procedure (§6.7).
/// </summary>
public sealed class UpdateEngine
{
    // TODO(M3): plan / run / rollback, together with the update UI flow.
}
