namespace HavcManager.Core.Bootstrap;

/// <summary>
/// Runs the bootstrap as a child process and streams its --json-progress events
/// (PHASE1_SPEC §5). Standard invocation:
///   runtime\python -m havc.install --install-dir ... --wheel ... --assets-dir ...
///   --with-dinov2 --models-dir ... --json-progress
/// Exit codes: 0 = ok (all-skip counts as ok), 1 = step failed, 2 = usage error.
/// The working directory must stay neutral (never a source checkout).
/// </summary>
public sealed class BootstrapRunner
{
    /// <summary>Raised for every progress event emitted by the bootstrap.</summary>
    public event EventHandler<BootstrapEvent>? EventReceived;

    /// <summary>Raises <see cref="EventReceived"/> (called by the M2 run loop).</summary>
    internal void RaiseEvent(BootstrapEvent bootstrapEvent)
        => EventReceived?.Invoke(this, bootstrapEvent);

    /// <summary>
    /// Runs the bootstrap and returns the final result. Raw events are also
    /// written to a jsonl log under <install>\logs\ (PHASE1_SPEC §9).
    /// TODO(M2): process plumbing, stdout/stderr capture, exit-code mapping.
    /// </summary>
    public Task<BootstrapResult> RunAsync(
        BootstrapInvocation invocation,
        CancellationToken cancellationToken = default)
        => throw new NotImplementedException("M2: run + stream events.");
}
