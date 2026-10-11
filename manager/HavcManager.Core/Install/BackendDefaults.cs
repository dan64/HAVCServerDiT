namespace HavcManager.Core.Install;

/// <summary>
/// HAVC-Server.cmd arguments used by "Start server" (2026-10-11). The
/// launcher resolves its argument with file-first precedence
/// (<c>config\&lt;name&gt;.json</c> wins over the historical aliases), so the
/// nominal default model is addressed by its config name directly.
/// </summary>
public static class BackendDefaults
{
    /// <summary>Launcher argument of the nominal default model (turbo config).</summary>
    public const string DefaultArg = "qwen21_turbo_int8";

    /// <summary>Launcher argument of the lighter model (below the RAM threshold).</summary>
    public const string LighterArg = "longcat3";

    /// <summary>HAVC-Server.cmd argument for a --default-model value (launcher mapping).</summary>
    public static string ArgFor(string? guiModelName) => guiModelName switch
    {
        "longcat-gguf" => LighterArg,
        _ => DefaultArg,
    };

    /// <summary>
    /// Argument to pass to HAVC-Server.cmd for the stored <c>backend_default</c>:
    /// empty falls back to the nominal default. The historical alias "qwen21"
    /// meant "the nominal default" as well (the launcher maps it to
    /// qwen21_viggle.json), so it is translated to today's default instead of
    /// starting the previous model; any other stored value passes through.
    /// </summary>
    public static string Resolve(string? storedBackend)
    {
        if (string.IsNullOrEmpty(storedBackend))
            return DefaultArg;
        return storedBackend == "qwen21" ? DefaultArg : storedBackend;
    }
}
