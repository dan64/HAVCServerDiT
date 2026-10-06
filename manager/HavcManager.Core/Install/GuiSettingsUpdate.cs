using System.IO.Compression;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace HavcManager.Core.Install;

/// <summary>
/// Compares the GUI settings template packaged in a wheel
/// (`havc/gui/gui_cmnet2_settings.json`) with the installed copy
/// (`&lt;install&gt;\gui\gui_cmnet2_settings.json`, 2026-10-06). The manager
/// asks for confirmation when the installed file differs from the packaged
/// defaults (with the install-specific values applied) and passes
/// `--update-gui-settings` to the bootstrap on "yes" (the bootstrap keeps the
/// previous file as gui_cmnet2_settings.json.bak). Mirrors the bootstrap logic
/// in havc/install.py (gui_settings_expected); a missing installed file is
/// seeded without asking, so it does not count as "differing".
/// </summary>
public static class GuiSettingsUpdate
{
    public const string WheelEntry = "havc/gui/gui_cmnet2_settings.json";

    /// <summary>True when the installed settings differ from the packaged defaults.</summary>
    public static bool Differs(string wheelPath, string installDir, string? defaultModel)
    {
        string installedPath = Path.Combine(installDir, "gui", "gui_cmnet2_settings.json");
        if (!File.Exists(installedPath) || !File.Exists(wheelPath))
            return false; // nothing to align (a missing file is seeded without asking)
        JsonNode? installed = TryParse(installedPath);
        if (installed is null)
            return true; // unreadable/not parseable: offer the packaged replacement
        JsonNode? template = TemplateFromWheel(wheelPath);
        if (template is not JsonObject templateObject)
            return false; // wheel without the template (old wheel): nothing to compare
        ApplyInstallValues(templateObject, installDir, defaultModel);
        return !JsonNode.DeepEquals(installed, templateObject);
    }

    private static JsonNode? TemplateFromWheel(string wheelPath)
    {
        try
        {
            using var zip = ZipFile.OpenRead(wheelPath);
            foreach (ZipArchiveEntry entry in zip.Entries)
            {
                if (!string.Equals(entry.FullName, WheelEntry, StringComparison.OrdinalIgnoreCase))
                    continue;
                using Stream stream = entry.Open();
                return JsonNode.Parse(stream);
            }
            return null;
        }
        catch (JsonException)
        {
            return null;
        }
        catch (InvalidDataException)
        {
            return null;
        }
        catch (IOException)
        {
            return null;
        }
    }

    private static JsonNode? TryParse(string path)
    {
        try
        {
            return JsonNode.Parse(File.ReadAllText(path));
        }
        catch (JsonException)
        {
            return null;
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    /// <summary>
    /// The install-specific values the bootstrap always rewrites
    /// (havc/install.py: gui_settings_expected).
    /// </summary>
    private static void ApplyInstallValues(JsonObject template, string installDir, string? defaultModel)
    {
        string guiDir = Path.Combine(installDir, "gui");
        string samples = Path.Combine(guiDir, "samples");
        template["script_dir"] = Path.Combine(guiDir, "scripts");
        template["vspipe_path"] = Path.Combine(installDir, "venv", "Scripts", "vspipe.exe");
        template["x265_path"] = Path.Combine(installDir, "tools", "x265", "x265.exe");
        template["mkv_path"] = Path.Combine(installDir, "tools", "MKVToolNix", "mkvmerge.exe");
        template["base_dir"] = samples;
        template["fixv_base_dir"] = samples;
        string model = defaultModel ?? "qwen21-viggle"; // --default-model default
        template["model_name"] = model;
        if (model == "longcat-gguf")
            template["model_precision"] = "q3"; // DEFAULT_MODEL_PRECISION in install.py
    }
}
