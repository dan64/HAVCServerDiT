namespace HavcManager.Core.Install;

/// <summary>
/// HAVC-Server.cmd arguments used by "Start server". The launcher resolves
/// its argument with file-first precedence (<c>config\&lt;name&gt;.json</c>
/// wins over the historical aliases), so the model chosen by the preflight
/// (2026-10-18: <c>qwen-2509-nunchaku</c> — fp4 on RTX 50, int4 on RTX 30/40 —
/// or <c>longcat_gguf_q3</c> on small machines) is addressed by its config
/// stem directly. The viggle value stays as the historical nominal default
/// for installs whose stored <c>backend_default</c> predates the new rule.
/// </summary>
public static class BackendDefaults
{
    /// <summary>Config stem of the qwen-2509-nunchaku int4 checkpoint (RTX 30/40).</summary>
    public const string Int4Arg = "qwen-2509-nunchaku_int4";

    /// <summary>Config stem of the qwen-2509-nunchaku fp4 checkpoint (RTX 50).</summary>
    public const string Fp4Arg = "qwen-2509-nunchaku_fp4";

    /// <summary>
    /// Last-resort default when no stored backend is available: the int4
    /// checkpoint runs on RTX 30/40 and on RTX 50 (slower there than fp4).
    /// </summary>
    public const string DefaultArg = Int4Arg;

    /// <summary>Historical default (viggle soft int8), kept for old state files.</summary>
    public const string ViggleArg = "qwen21_viggle-soft_int8";

    /// <summary>Launcher argument of the turbo family config (interim default).</summary>
    public const string TurboArg = "qwen21_turbo_int8";

    /// <summary>Launcher argument of the lighter model (below the thresholds).</summary>
    public const string LighterArg = "longcat3";

    /// <summary>HAVC-Server.cmd argument for a --default-model value (launcher mapping).</summary>
    public static string ArgFor(string? guiModelName) => guiModelName switch
    {
        "qwen25-nunchaku-fp4" => Fp4Arg,
        "qwen25-nunchaku-int4" => Int4Arg,
        "longcat-gguf" => LighterArg,
        "qwen21-viggle" => ViggleArg,
        "qwen21-turbo" => TurboArg,
        _ => DefaultArg,
    };

    /// <summary>
    /// Argument to pass to HAVC-Server.cmd for the stored <c>backend_default</c>.
    /// The historical alias "qwen21" (and an empty value) meant "the nominal
    /// default", not a specific checkpoint, so both are translated to the
    /// default of <paramref name="nominalDefault"/> — the per-machine value
    /// chosen by the preflight (2026-10-18) — instead of starting whichever
    /// model the alias mapped to before. Any other stored value passes through
    /// unchanged (an explicit choice, including a config name written by an
    /// interim build).
    /// </summary>
    public static string Resolve(string? storedBackend, string? nominalDefault = null)
        => MigrateLegacy(storedBackend, nominalDefault);

    /// <summary>
    /// Rewrites a legacy/empty <c>backend_default</c> to the argument of the
    /// machine's nominal default (fp4 on RTX 50, int4 on RTX 30/40, longcat Q3
    /// on small machines); an explicit stored value is kept. Used by update and
    /// repair so the saved state catches up with the per-GPU rule of
    /// 2026-10-18 without overriding a choice the user made.
    /// </summary>
    public static string MigrateLegacy(string? storedBackend, string? nominalDefault)
        => string.IsNullOrEmpty(storedBackend) || storedBackend == "qwen21"
            ? ArgFor(nominalDefault)
            : storedBackend;
}
