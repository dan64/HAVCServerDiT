using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Runtime.CompilerServices;
using System.Windows;
using HavcManager.App.Resources;
using HavcManager.App.Windows;
using HavcManager.Core.Bootstrap;
using HavcManager.Core.Install;
using HavcManager.Core.Manifest;
using HavcManager.Core.Preflight;
using HavcManager.Core.State;

namespace HavcManager.App.Wizard;

public enum WizardPage
{
    Welcome,
    Preflight,
    Folders,
    Components,
    Summary,
    Progress,
    Finish,
    Installed,
}

/// <summary>
/// State machine and data of the wizard (PHASE1_SPEC §6.1–§6.2, §8).
/// All user-visible strings are in English (spec §2); UI text is centralized
/// in Resources/Strings.resx.
/// </summary>
public sealed class WizardViewModel : INotifyPropertyChanged
{
    private readonly AppOptions _options;
    private readonly StateStore _stateStore = new();

    private ReleaseManifest? _manifest;
    private InstallFlow? _flow;
    private CancellationTokenSource? _cts;
    private PreflightReport? _preflightReport;
    private string? _failureDetail;
    private string? _failureRemediation;
    private int _stopStage;

    private string _installDir = "";
    private string _modelsDir = "";
    private bool _desktopShortcut;
    private string _statusText = "";
    private bool _isRunning;
    private bool _isBusy;
    private bool _preflightDone;
    private string? _suggestedBackend;

    public WizardViewModel(AppOptions options) => _options = options;

    public string ManagerVersion { get; } = typeof(WizardViewModel).Assembly
        .GetName().Version?.ToString(3) ?? "0.1.0";

    public WizardPage CurrentPage { get; private set; } = WizardPage.Welcome;

    public ExistingInstall? Existing { get; private set; }

    public event PropertyChangedEventHandler? PropertyChanged;
    public event Action? PageChanged;
    public event Action? UninstallRequestedFromArgs;

    // ------------------------------------------------------------ bound state --
    public string InstallDir
    {
        get => _installDir;
        set => Set(ref _installDir, value);
    }

    public string ModelsDir
    {
        get => _modelsDir;
        set => Set(ref _modelsDir, value);
    }

    public bool DesktopShortcut
    {
        get => _desktopShortcut;
        set => Set(ref _desktopShortcut, value);
    }

    public string StatusText
    {
        get => _statusText;
        private set => Set(ref _statusText, value);
    }

    public bool IsRunning
    {
        get => _isRunning;
        private set
        {
            if (Set(ref _isRunning, value))
                Notify(nameof(IsNotRunning));
        }
    }

    public bool IsNotRunning => !_isRunning;

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            if (Set(ref _isBusy, value))
                Notify(nameof(IsNotBusy));
        }
    }

    public bool IsNotBusy => !_isBusy;

    public bool PreflightDone => _preflightDone;

    public bool CanContinueFromPreflight => _preflightDone && _preflightReport is { HasErrors: false };

    public string SuggestedBackendText => _suggestedBackend is null
        ? ""
        : $"Suggested backend: {_suggestedBackend} (indicative)";

    public ObservableCollection<PreflightCheck> PreflightChecks { get; } = new();

    public ObservableCollection<StepItem> Steps { get; } = new();

    public ObservableCollection<string> LogLines { get; } = new();

    public ObservableCollection<string> SummaryLines { get; } = new();

    public int ProgressMaximum => Math.Max(Steps.Count, 1);

    public int ProgressValue => Steps.Count(s => s.Status is "ok" or "skipped" or "error");

    public string CancelButtonText => _stopStage == 0 ? Strings.Cancel : Strings.ForceStop;

    public string ManifestVersionText => _manifest is null
        ? ""
        : $"{Strings.SummaryVersionLabel}: {_manifest.AppVersion}";

    public string? ManifestNotesUrl => _manifest?.NotesUrl;

    public string FinishVersionText => _manifest is null
        ? ""
        : $"{Strings.FinishVersionLabel} {_manifest.AppVersion}";

    // ------------------------------------------------------------- lifecycle --
    public void Initialize()
    {
        InstallDir = _options.InstallDir ?? InstallLocator.DefaultInstallDir;
        ModelsDir = SuggestModelsDir();

        Existing = InstallLocator.FindExisting(_options.InstallDir);
        if (Existing is not null)
        {
            InstallDir = Existing.InstallDir;
            ModelsDir = Existing.State.ModelsDir ?? ModelsDir;
            Navigate(WizardPage.Installed);
            if (_options.Uninstall)
                UninstallRequestedFromArgs?.Invoke();
        }
        else
        {
            Navigate(WizardPage.Welcome);
        }
    }

    public void Navigate(WizardPage page)
    {
        CurrentPage = page;
        StatusText = "";
        PageChanged?.Invoke();
    }

    public async Task StartPreflightAsync()
    {
        Navigate(WizardPage.Preflight);
        PreflightChecks.Clear();
        _preflightDone = false;
        StatusText = Strings.PreflightRunning;
        Notify(nameof(PreflightDone));
        Notify(nameof(CanContinueFromPreflight));
        try
        {
            var report = await new Preflight()
                .RunAsync(InstallDir, ModelsDir, ResolveManifestSource());
            _preflightReport = report;
            _suggestedBackend = report.SuggestedBackend;
            foreach (PreflightCheck check in report.Checks)
                PreflightChecks.Add(check);
        }
        catch (Exception ex)
        {
            _preflightReport = null;
            PreflightChecks.Add(new PreflightCheck("Unexpected error", PreflightStatus.Error, ex.Message));
        }
        _preflightDone = true;
        StatusText = "";
        Notify(nameof(PreflightDone));
        Notify(nameof(CanContinueFromPreflight));
        Notify(nameof(SuggestedBackendText));
    }

    public async Task ContinueFromFoldersAsync()
    {
        if (string.IsNullOrWhiteSpace(InstallDir) || string.IsNullOrWhiteSpace(ModelsDir))
        {
            ShowError(Strings.ErrorTitle, "Choose both the install folder and the models folder.");
            return;
        }
        if (IsBusy)
            return;
        IsBusy = true;
        StatusText = Strings.StatusFetchingManifest;
        try
        {
            _manifest = await new ManifestClient().FetchAsync(ResolveManifestSource());
            SummaryLines.Clear();
            foreach (PlannedDownload item in DownloadPlan.FromManifest(_manifest))
            {
                SummaryLines.Add(item.Size > 0
                    ? $"{item.Name}  ({FormatBytes(item.Size)})"
                    : item.Name);
            }
            Notify(nameof(ManifestVersionText));
            Notify(nameof(ManifestNotesUrl));
            Navigate(WizardPage.Components);
        }
        catch (Exception ex)
        {
            ShowError(Strings.ErrorTitle, $"{Strings.StatusFetchingManifest}\n\n{ex.Message}");
        }
        finally
        {
            IsBusy = false;
            StatusText = "";
        }
    }

    // ----------------------------------------------------------- installation --
    public async Task StartInstallAsync()
    {
        if (_manifest is null || IsRunning)
            return;
        Steps.Clear();
        LogLines.Clear();
        _failureDetail = null;
        _failureRemediation = null;
        _stopStage = 0;
        Notify(nameof(CancelButtonText));
        Notify(nameof(ProgressMaximum));
        Notify(nameof(ProgressValue));

        _cts = new CancellationTokenSource();
        _flow = new InstallFlow();
        _flow.Runner.EventReceived += OnBootstrapEvent;
        IsRunning = true;
        Navigate(WizardPage.Progress);
        StatusText = Strings.StatusPreparing;

        InstallOutcome outcome;
        try
        {
            var plan = new InstallPlan(_manifest, InstallDir, ModelsDir, WithDinov2: true);
            outcome = await _flow.RunAsync(plan, ev => OnUi(() => ApplyFlowEvent(ev)), _cts.Token);
        }
        finally
        {
            _flow.Runner.EventReceived -= OnBootstrapEvent;
            IsRunning = false;
        }

        if (outcome.Ok)
        {
            StatusText = Strings.StatusFinishing;
            FinalizeInstall();
            StatusText = "";
            Navigate(WizardPage.Finish);
            return;
        }

        bool canceled = _stopStage > 0 || outcome.Error == "canceled";
        StatusText = canceled ? Strings.StatusStopped : Strings.StatusFailed;
        if (!canceled)
        {
            string message = _failureDetail ?? outcome.Error ?? Strings.StatusFailed;
            if (!string.IsNullOrEmpty(_failureRemediation))
                message += "\n\n" + _failureRemediation;
            ShowError(Strings.ErrorTitle, message);
        }
    }

    /// <summary>Cancel: first press stops after the current step, second kills the process.</summary>
    public void RequestCancel()
    {
        if (!IsRunning || _flow is null)
            return;
        _stopStage++;
        if (_stopStage == 1)
        {
            try
            {
                BootstrapRunner.RequestStop(InstallDir);
                StatusText = Strings.StatusStopping;
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
        else
        {
            _cts?.Cancel();
        }
        Notify(nameof(CancelButtonText));
    }

    private void FinalizeInstall()
    {
        try
        {
            ShellIntegration.CopyManagerTo(InstallDir);
        }
        catch (Exception ex)
        {
            LogLines.Add($"warning: could not copy the manager: {ex.Message}");
        }
        _stateStore.Save(InstallDir, new InstallState
        {
            ManagerVersion = ManagerVersion,
            AppVersion = _manifest!.AppVersion,
            InstalledAt = DateTimeOffset.UtcNow.ToString("o"),
            InstallDir = InstallDir,
            ModelsDir = ModelsDir,
            Runtime = _manifest.Runtime is { } runtime
                ? new RuntimeState { Name = runtime.Name, Sha256 = runtime.Sha256, Python = runtime.Python }
                : null,
            Dinov2 = true,
            BackendDefault = _suggestedBackend ?? "fp4",
            LastVerify = new LastVerifyState
            {
                Ts = DateTimeOffset.UtcNow.ToString("o"),
                Ok = true,
                AppVersion = _manifest.AppVersion,
            },
        });
        try
        {
            ShellIntegration.CreateStartMenuShortcuts(InstallDir);
            if (DesktopShortcut)
                ShellIntegration.CreateDesktopShortcut(InstallDir);
        }
        catch (Exception ex)
        {
            LogLines.Add($"warning: could not create the shortcuts: {ex.Message}");
        }
        try
        {
            ShellIntegration.RegisterUninstall(InstallDir, _manifest.AppVersion);
        }
        catch (Exception ex)
        {
            LogLines.Add($"warning: could not register the uninstall entry: {ex.Message}");
        }
    }

    // --------------------------------------------------------------- bootstrap --
    private void OnBootstrapEvent(object? sender, BootstrapEvent e)
        => OnUi(() => ApplyBootstrapEvent(e));

    private void ApplyBootstrapEvent(BootstrapEvent e)
    {
        switch (e.Kind)
        {
            case "plan":
                Steps.Clear();
                foreach (PlanStep step in e.PlanSteps ?? (IReadOnlyList<PlanStep>)Array.Empty<PlanStep>())
                {
                    Steps.Add(new StepItem(step.Id, step.Title)
                    {
                        Status = step.SkipReason is null ? "pending" : "skipped",
                        Detail = step.SkipReason,
                    });
                }
                Notify(nameof(ProgressMaximum));
                Notify(nameof(ProgressValue));
                break;
            case "step_begin":
                SetStep(e.StepId, "running", null);
                break;
            case "step_ok":
                SetStep(e.StepId, "ok", e.Detail);
                break;
            case "step_skip":
                SetStep(e.StepId, "skipped", e.Reason);
                break;
            case "step_error":
                _failureDetail = e.Error;
                _failureRemediation = e.Remediation;
                SetStep(e.StepId, "error", e.Error);
                break;
            case "log":
                AppendLog(e.Message);
                break;
        }
    }

    private void SetStep(string? id, string status, string? detail)
    {
        StepItem? item = Steps.FirstOrDefault(s => s.Id == id);
        if (item is null)
            return;
        item.Status = status;
        if (!string.IsNullOrEmpty(detail))
            item.Detail = detail;
        Notify(nameof(ProgressValue));
    }

    private void ApplyFlowEvent(FlowEvent ev)
    {
        switch (ev.Kind)
        {
            case "phase":
                StatusText = ev.Message + "\u2026";
                break;
            case "download":
                StatusText = ev.Total > 0
                    ? $"{ev.Message} \u2014 {FormatBytes(ev.Done)} / {FormatBytes(ev.Total)}"
                    : ev.Message;
                break;
            case "log":
                AppendLog(ev.Message);
                break;
        }
    }

    private void AppendLog(string? line)
    {
        if (string.IsNullOrEmpty(line))
            return;
        LogLines.Add(line);
        while (LogLines.Count > 5000)
            LogLines.RemoveAt(0);
    }

    // ----------------------------------------------------------------- actions --
    public void OpenGui() => ShellIntegration.LaunchGui(InstallDir);

    public void OpenWorkFolder() => ShellIntegration.OpenFolder(InstallDir);

    public void OpenLogs() => ShellIntegration.OpenLogs(InstallDir);

    public void StartServer() => ShellIntegration.StartServer(InstallDir, _suggestedBackend ?? "fp4");

    public void OpenReleaseNotes()
    {
        if (ManifestNotesUrl is { } url)
            ShellIntegration.OpenUrl(url);
    }

    public async Task UninstallAsync(bool deleteModels)
    {
        string installDir = Existing?.InstallDir ?? InstallDir;
        string? modelsDir = Existing?.State.ModelsDir;
        if (string.IsNullOrWhiteSpace(modelsDir))
            modelsDir = null;

        try
        {
            ShellIntegration.RemoveShortcuts();
        }
        catch (Exception)
        {
        }
        try
        {
            ShellIntegration.UnregisterUninstall();
        }
        catch (Exception)
        {
        }
        if (deleteModels && modelsDir is not null)
        {
            try
            {
                DeleteWithRetry(modelsDir);
            }
            catch (Exception ex)
            {
                ShowError(Strings.ErrorTitle, $"{Strings.UninstallPartialMessage}\n{modelsDir}\n\n{ex.Message}");
            }
        }

        string? self = Environment.ProcessPath;
        if (self is not null && IsUnder(self, installDir))
        {
            // The manager itself lives in the install folder: self-removal worker.
            string tempCopy = Path.Combine(
                Path.GetTempPath(), $"HAVCManager-uninstall-{Guid.NewGuid():N}.exe");
            File.Copy(self, tempCopy, overwrite: true);
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(
                tempCopy, $"--uninstall-run \"{installDir}\""));
            Application.Current.Shutdown();
            return;
        }

        try
        {
            DeleteWithRetry(installDir);
        }
        catch (Exception ex)
        {
            ShowError(Strings.ErrorTitle, $"{Strings.UninstallPartialMessage}\n{installDir}\n\n{ex.Message}");
        }
        MessageBox.Show(
            Application.Current.MainWindow, Strings.UninstallDoneMessage, Strings.AppTitle,
            MessageBoxButton.OK, MessageBoxImage.Information);
        Application.Current.Shutdown();
    }

    private static void DeleteWithRetry(string dir)
    {
        for (int attempt = 0; ; attempt++)
        {
            try
            {
                if (Directory.Exists(dir))
                    Directory.Delete(dir, recursive: true);
                return;
            }
            catch (IOException) when (attempt < 40)
            {
                Thread.Sleep(500);
            }
            catch (UnauthorizedAccessException) when (attempt < 40)
            {
                Thread.Sleep(500);
            }
        }
    }

    private static bool IsUnder(string file, string dir)
        => Path.GetFullPath(file).StartsWith(
            Path.GetFullPath(dir) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);

    // ---------------------------------------------------------------- helpers --
    private string ResolveManifestSource()
    {
        if (_options.ManifestSource is { } source)
            return source;
        if (_options.ReleaseTag is { } tag)
            return $"https://github.com/dan64/HAVCServerDiT/releases/download/{tag}/release.json";
        return ManifestClient.DefaultUrl;
    }

    private static string SuggestModelsDir()
    {
        try
        {
            string? bestRoot = null;
            long bestFree = -1;
            foreach (DriveInfo drive in DriveInfo.GetDrives())
            {
                if (drive.DriveType != DriveType.Fixed || !drive.IsReady)
                    continue;
                if (drive.AvailableFreeSpace > bestFree)
                {
                    bestFree = drive.AvailableFreeSpace;
                    bestRoot = drive.RootDirectory.FullName;
                }
            }
            if (bestRoot is not null)
                return Path.Combine(bestRoot, "HAVCModels");
        }
        catch (IOException)
        {
        }
        return Path.Combine(InstallLocator.DefaultInstallDir, "models");
    }

    internal static string FormatBytes(long bytes)
    {
        if (bytes >= 1L << 30)
            return string.Format(CultureInfo.InvariantCulture, "{0:0.0} GB", bytes / (double)(1L << 30));
        if (bytes >= 1L << 20)
            return string.Format(CultureInfo.InvariantCulture, "{0:0.0} MB", bytes / (double)(1L << 20));
        if (bytes >= 1L << 10)
            return string.Format(CultureInfo.InvariantCulture, "{0:0.0} KB", bytes / (double)(1L << 10));
        return bytes + " B";
    }

    private static void ShowError(string title, string message)
        => MessageBox.Show(
            Application.Current?.MainWindow, message, title,
            MessageBoxButton.OK, MessageBoxImage.Error);

    private static void OnUi(Action action)
    {
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.CheckAccess())
            action();
        else
            dispatcher.Invoke(action);
    }

    // ------------------------------------------------------------------- INPC --
    private bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
            return false;
        field = value;
        Notify(name);
        return true;
    }

    private void Notify([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
