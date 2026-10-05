namespace HavcManager.App;

/// <summary>
/// Command-line options of the manager (PHASE1_SPEC §6.1, §11):
///   --install-dir &lt;dir&gt;      explicit install folder
///   --manifest &lt;file|url&gt;    manifest override for tests
///   --release-tag &lt;tag&gt;      manifest URL from an explicit release tag
///   --uninstall               open in uninstall mode
///   --uninstall-run &lt;dir&gt;    internal: self-removal worker (deletes the folder)
/// </summary>
public sealed class AppOptions
{
    public string? InstallDir { get; private set; }
    public string? ManifestSource { get; private set; }
    public string? ReleaseTag { get; private set; }
    public bool Uninstall { get; private set; }
    public string? UninstallRunDir { get; private set; }

    public static AppOptions Parse(string[] args)
    {
        var options = new AppOptions();
        for (int i = 0; i < args.Length; i++)
        {
            string TakeValue()
            {
                if (i + 1 >= args.Length)
                    throw new ArgumentException($"Missing value for {args[i]}");
                return args[++i];
            }

            switch (args[i])
            {
                case "--install-dir":
                    options.InstallDir = TakeValue();
                    break;
                case "--manifest":
                    options.ManifestSource = TakeValue();
                    break;
                case "--release-tag":
                    options.ReleaseTag = TakeValue();
                    break;
                case "--uninstall":
                    options.Uninstall = true;
                    break;
                case "--uninstall-run":
                    options.UninstallRunDir = TakeValue();
                    break;
                default:
                    throw new ArgumentException($"Unknown argument: {args[i]}");
            }
        }
        return options;
    }
}
