namespace HavcManager.Core.Bootstrap;

/// <summary>
/// Parameters of one bootstrap run (PHASE1_SPEC §5). The bootstrap is invoked as:
/// runtime\python -m havc.install --json-progress ...
/// </summary>
public sealed record BootstrapInvocation
{
    /// <summary>Path of the provisioned Python (python-build-standalone).</summary>
    public required string PythonExe { get; init; }

    public required string InstallDir { get; init; }

    /// <summary>Path of the havc wheel to install first (two-stage flow).</summary>
    public required string WheelPath { get; init; }

    /// <summary>Folder with the extra asset wheels (vscmnet2, spatial_correlation_sampler).</summary>
    public required string AssetsDir { get; init; }

    /// <summary>
    /// GUI default model (--default-model): "longcat-gguf" below the RAM
    /// threshold, else "qwen21-viggle"; seeds gui_cmnet2_settings.json when empty.
    /// </summary>
    public string? DefaultModel { get; init; }

    /// <summary>Always true for the manager (D10).</summary>
    public bool WithDinov2 { get; init; }

    /// <summary>
    /// True when the user confirmed replacing installed pipeline configs that
    /// differ from the packaged ones (--update-configs; the bootstrap keeps
    /// the previous file as &lt;name&gt;.json.bak).
    /// </summary>
    public bool UpdateConfigs { get; init; }

    public IReadOnlyList<string> ExtraArgs { get; init; } = [];
}

/// <summary>Result of a bootstrap run (exit code 0 = ok, including the all-skip case).</summary>
public sealed record BootstrapResult(int ExitCode, bool Ok);
