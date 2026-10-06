using System.IO.Compression;
using System.Text.Json.Nodes;
using HavcManager.Core.Install;

namespace HavcManager.Core.Tests;

public class GuiSettingsUpdateTests
{
    [Fact]
    public void Packaged_defaults_with_install_values_do_not_differ()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string template = Template();
            string wheel = WriteWheel(dir, template);
            WriteInstalled(dir, WithInstallValues(template, dir, "qwen21-viggle"));

            Assert.False(GuiSettingsUpdate.Differs(wheel, dir, "qwen21-viggle"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void User_modified_value_is_reported()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string template = Template();
            string wheel = WriteWheel(dir, template);
            JsonObject installed = Parse(WithInstallValues(template, dir, "qwen21-viggle"));
            installed["fix_steps"] = "4";
            WriteInstalled(dir, installed.ToJsonString());

            Assert.True(GuiSettingsUpdate.Differs(wheel, dir, "qwen21-viggle"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Missing_installed_file_is_not_reported()
    {
        // Fresh installs seed the file without asking.
        string dir = TestPaths.NewTempDir();
        try
        {
            string wheel = WriteWheel(dir, Template());

            Assert.False(GuiSettingsUpdate.Differs(wheel, dir, "qwen21-viggle"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Unparseable_installed_file_is_reported()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string wheel = WriteWheel(dir, Template());
            WriteInstalled(dir, "{ not json");

            Assert.True(GuiSettingsUpdate.Differs(wheel, dir, "qwen21-viggle"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Stale_managed_values_are_reported()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string template = Template();
            string wheel = WriteWheel(dir, template);
            JsonObject installed = Parse(WithInstallValues(template, dir, "qwen21-viggle"));
            installed["base_dir"] = @"C:\old\work";
            WriteInstalled(dir, installed.ToJsonString());

            Assert.True(GuiSettingsUpdate.Differs(wheel, dir, "qwen21-viggle"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    [Fact]
    public void Longcat_default_applies_its_precision()
    {
        string dir = TestPaths.NewTempDir();
        try
        {
            string template = Template();
            string wheel = WriteWheel(dir, template);
            WriteInstalled(dir, WithInstallValues(template, dir, "longcat-gguf"));

            Assert.False(GuiSettingsUpdate.Differs(wheel, dir, "longcat-gguf"));
            Assert.True(GuiSettingsUpdate.Differs(wheel, dir, "qwen21-viggle"));
        }
        finally
        {
            TestPaths.Delete(dir);
        }
    }

    private static string Template() =>
        "{\"script_dir\": \"\", \"vspipe_path\": \"\", \"x265_path\": \"\", " +
        "\"mkv_path\": \"\", \"base_dir\": \"\", \"fixv_base_dir\": \"\", " +
        "\"model_name\": \"qwen21-viggle\", \"model_precision\": \"q3\", " +
        "\"fix_steps\": \"2\", \"window_w\": 926, \"window_h\": 814}";

    private static JsonObject Parse(string json) => JsonNode.Parse(json)!.AsObject();

    private static string WithInstallValues(string templateJson, string installDir, string model)
    {
        JsonObject node = Parse(templateJson);
        string guiDir = Path.Combine(installDir, "gui");
        string samples = Path.Combine(guiDir, "samples");
        node["script_dir"] = Path.Combine(guiDir, "scripts");
        node["vspipe_path"] = Path.Combine(installDir, "venv", "Scripts", "vspipe.exe");
        node["x265_path"] = Path.Combine(installDir, "tools", "x265", "x265.exe");
        node["mkv_path"] = Path.Combine(installDir, "tools", "MKVToolNix", "mkvmerge.exe");
        node["base_dir"] = samples;
        node["fixv_base_dir"] = samples;
        node["model_name"] = model;
        if (model == "longcat-gguf")
            node["model_precision"] = "q3";
        return node.ToJsonString();
    }

    private static string WriteWheel(string dir, string templateJson)
    {
        string wheel = Path.Combine(dir, "havc-test-py3-none-any.whl");
        using var zip = ZipFile.Open(wheel, ZipArchiveMode.Create);
        ZipArchiveEntry entry = zip.CreateEntry("havc/gui/gui_cmnet2_settings.json");
        using var writer = new StreamWriter(entry.Open());
        writer.Write(templateJson);
        return wheel;
    }

    private static void WriteInstalled(string dir, string json)
    {
        string guiDir = Path.Combine(dir, "gui");
        Directory.CreateDirectory(guiDir);
        File.WriteAllText(Path.Combine(guiDir, "gui_cmnet2_settings.json"), json);
    }
}
