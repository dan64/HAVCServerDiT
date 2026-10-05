using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Runtime.CompilerServices;
using System.Windows;
using HavcManager.App.Dialogs;
using HavcManager.App.Resources;
using HavcManager.App.Windows;
using HavcManager.Core.Bootstrap;
using HavcManager.Core.Download;
using HavcManager.Core.Install;
using HavcManager.Core.Log;
using HavcManager.Core.Manifest;
using HavcManager.Core.Preflight;
using HavcManager.Core.Processes;
using HavcManager.Core.Runtime;
using HavcManager.Core.State;
using HavcManager.Core.Update;

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
    private ReleaseManifest? _updateManifest;
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
    private bool _dirtyWarningVisible;

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

    public ObservableCollection<PreflightCheck> PreflightChecks { get; } = new();

    public ObservableCollection<StepItem> Steps { get; } = new();

    public ObservableCollection<string> LogLines { get; } = new();

    public ObservableCollection<string> SummaryLines { get; } = new();

    public ObservableCollection<string> InstalledLines { get; } = new();

    /// <summary>
    /// Fixed default model for "Start server" (launcher argument; `qwen21`
    /// maps to qwen21_viggle.json). Other models are chosen in the HAVC GUI.
    /// </summary>
    public const string DefaultBackend = "qwen21";

    public bool DirtyWarningVisible
    {
        get => _dirtyWarningVisible;
        private set => Set(ref _dirtyWarningVisible, value);
    }

    public string AboutText => string.Format(CultureInfo.InvariantCulture, Strings.AboutLine, ManagerVersion);

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

        ReloadExisting();
        if (Existing is not null)
        {
            Navigate(WizardPage.Installed);
            if (_options.Uninstall)
                UninstallRequestedFromArgs?.Invoke();
        }
        else
        {
            Navigate(WizardPage.Welcome);
        }
    }

    /// <summary>Re-reads install.json and refreshes the Installed-page data.</summary>
    public void ReloadExisting()
    {
        Existing = InstallLocator.FindExisting(_options.InstallDir);
        if (Existing is not null)
        {
            InstallDir = Existing.InstallDir;
            ModelsDir = Existing.State.ModelsDir ?? ModelsDir;
        }
        RefreshInstalledLines();
        Notify(nameof(Existing));
    }

    private void RefreshInstalledLines()
    {
        InstalledLines.Clear();
        var state = Existing?.State;
        if (state is null)
        {
            DirtyWarningVisible = false;
            return;
        }
        InstalledLines.Add($"{Strings.SummaryVersionLabel}: {state.AppVersion}");
        InstalledLines.Add($"{Strings.LabelInstallFolder}: {Existing!.InstallDir}");
        InstalledLines.Add($"{Strings.LabelModelsFolder}: {state.ModelsDir ?? "—"}");
        InstalledLines.Add(LastVerifyText(state));
        InstalledLines.Add(string.Format(CultureInfo.InvariantCulture, Strings.FreeSpaceFormat, FreeSpace(state.ModelsDir)));
        DirtyWarningVisible = state.Dirty;
    }

    private static string LastVerifyText(InstallState state)
    {
        var verify = state.LastVerify;
        if (verify is null)
            return Strings.LastVerifyNever;
        string ts = DateTimeOffset.TryParse(verify.Ts, CultureInfo.InvariantCulture, DateTimeStyles.None, out var parsed)
            ? parsed.ToLocalTime().ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture)
            : verify.Ts;
        return string.Format(
            CultureInfo.InvariantCulture,
            verify.Ok ? Strings.LastVerifyOkFormat : Strings.LastVerifyFailedFormat,
            ts);
    }

    private static string FreeSpace(string? path)
    {
        try
        {
            if (!string.IsNullOrEmpty(path))
            {
                var drive = new DriveInfo(Path.GetPathRoot(Path.GetFullPath(path))!);
                return FormatBytes(drive.AvailableFreeSpace);
            }
        }
        catch (ArgumentException)
        {
        }
        catch (IOException)
        {
        }
        return "—";
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
        InstallOutcome outcome = await RunFlowOnProgressAsync(
            reset: true,
            (observe, ct) => _flow!.RunAsync(new InstallPlan(_manifest, InstallDir, ModelsDir, WithDinov2: true), observe, ct));
        if (outcome.Ok)
        {
            StatusText = Strings.StatusFinishing;
            FinalizeInstall();
            StatusText = "";
            Navigate(WizardPage.Finish);
            return;
        }
        HandleFailedRun(outcome);
    }

    public async Task CheckForUpdatesAsync()
    {
        if (IsBusy || IsRunning)
            return;
        IsBusy = true;
        StatusText = Strings.StatusCheckingUpdates;
        ReleaseManifest? manifest = null;
        string? error = null;
        try
        {
            manifest = await new ManifestClient().FetchAsync(ResolveManifestSource());
        }
        catch (Exception ex)
        {
            error = ex.Message;
        }
        IsBusy = false;
        StatusText = "";
        if (manifest is null)
        {
            MessageDialog.Show(Application.Current?.MainWindow, Strings.ErrorTitle, error ?? Strings.StatusFailed);
            return;
        }
        ReloadExisting();
        var state = Existing?.State;
        if (state is null)
        {
            MessageDialog.Show(Application.Current?.MainWindow, Strings.ErrorTitle, Strings.NoInstallationMessage);
            return;
        }
        var classification = UpdateEngine.Classify(manifest, state);
        new ManagerLog(InstallDir).Info(
            $"update check: manifest {manifest.AppVersion} vs installed {state.AppVersion} -> {classification}");
        switch (classification)
        {
            case UpdateClassification.UpToDate:
                MessageDialog.Show(
                    Application.Current?.MainWindow, Strings.AppTitle,
                    string.Format(CultureInfo.InvariantCulture, Strings.UpToDateMessage, manifest.AppVersion));
                break;
            case UpdateClassification.RebuildRequired:
                MessageDialog.Show(
                    Application.Current?.MainWindow, Strings.UpdateAvailableTitle, Strings.RebuildRequiredMessage);
                break;
            case UpdateClassification.UpdateAvailable:
                bool update = MessageDialog.Show(
                    Application.Current?.MainWindow, Strings.UpdateAvailableTitle,
                    string.Format(CultureInfo.InvariantCulture, Strings.UpdateAvailableMessage, state.AppVersion, manifest.AppVersion),
                    yesNo: true,
                    linkText: Strings.OpenReleaseNotes,
                    linkUrl: manifest.NotesUrl);
                if (update)
                {
                    _updateManifest = manifest;
                    await StartUpdateAsync();
                }
                break;
        }
    }

    public async Task StartUpdateAsync()
    {
        if (_updateManifest is null || IsRunning)
            return;
        ReloadExisting();
        var state = Existing?.State;
        if (state is null)
            return;
        if (!EnsureInstancesClosed())
            return;

        string cacheDir = Path.Combine(InstallDir, "cache");
        string? oldWheel = UpdateEngine.FindCachedWheel(cacheDir, state.AppVersion);
        InstallOutcome outcome = await RunFlowOnProgressAsync(
            reset: true,
            (observe, ct) => _flow!.RunAsync(new InstallPlan(_updateManifest, InstallDir, ModelsDir, WithDinov2: true), observe, ct));

        if (outcome.Ok)
        {
            string now = DateTimeOffset.UtcNow.ToString("o");
            var snapshot = new PreviousState
            {
                AppVersion = state.AppVersion,
                Wheel = oldWheel is null ? "" : Path.GetFileName(oldWheel),
                Sha256 = oldWheel is null ? "" : await Downloader.Sha256Async(oldWheel),
            };
            _stateStore.Save(InstallDir, state with
            {
                AppVersion = _updateManifest.AppVersion,
                UpdatedAt = now,
                Previous = snapshot,
                Dirty = false,
                LastVerify = new LastVerifyState { Ts = now, Ok = true, AppVersion = _updateManifest.AppVersion },
            });
            ReloadExisting();
            Navigate(WizardPage.Installed);
            MessageDialog.Show(
                Application.Current?.MainWindow, Strings.AppTitle,
                string.Format(CultureInfo.InvariantCulture, Strings.UpdateCompleteMessage, _updateManifest.AppVersion));
            return;
        }

        if (_stopStage > 0 || outcome.Error == "canceled")
        {
            StatusText = Strings.StatusStopped;
            return;
        }

        // FAIL → rollback (spec §6.3 step 6): stage 1 + stage 2 on the previous wheel.
        StatusText = Strings.StatusRollingBack;
        bool rolledBack = false;
        if (oldWheel is not null)
        {
            var repair = new RepairPlan(
                InstallDir, ModelsDir, PythonRuntime.PythonExePath(InstallDir), oldWheel,
                RuntimeArchive: RuntimeArchivePath(state, cacheDir),
                WithDinov2: true);
            InstallOutcome rollback = await RunFlowOnProgressAsync(
                reset: false,
                (observe, ct) => _flow!.RunRepairAsync(repair, observe, ct));
            rolledBack = rollback.Ok;
        }

        string failure = _failureDetail ?? outcome.Error ?? "";
        string share = string.IsNullOrEmpty(failure) ? "" : "\n\n" + failure;
        string rollbackTs = DateTimeOffset.UtcNow.ToString("o");
        if (rolledBack)
        {
            _stateStore.Save(InstallDir, state with
            {
                LastVerify = new LastVerifyState { Ts = rollbackTs, Ok = true, AppVersion = state.AppVersion },
            });
            ReloadExisting();
            Navigate(WizardPage.Installed);
            MessageDialog.Show(
                Application.Current?.MainWindow, Strings.ErrorTitle, Strings.UpdateRolledBackMessage + share);
        }
        else
        {
            _stateStore.Save(InstallDir, state with { Dirty = true });
            ReloadExisting();
            Navigate(WizardPage.Installed);
            MessageDialog.Show(
                Application.Current?.MainWindow, Strings.ErrorTitle,
                Strings.UpdateDirtyMessage + "\n" + Path.Combine(InstallDir, "logs") + share);
        }
    }

    public async Task StartRepairAsync()
    {
        if (IsRunning)
            return;
        ReloadExisting();
        var state = Existing?.State;
        if (state is null)
            return;
        string cacheDir = Path.Combine(InstallDir, "cache");
        string? wheel = UpdateEngine.FindCachedWheel(cacheDir, state.AppVersion);
        if (wheel is null)
        {
            MessageDialog.Show(
                Application.Current?.MainWindow, Strings.ErrorTitle,
                string.Format(CultureInfo.InvariantCulture, Strings.RepairNoWheelMessage, state.AppVersion));
            return;
        }
        if (!EnsureInstancesClosed())
            return;

        var plan = new RepairPlan(
            InstallDir, ModelsDir, PythonRuntime.PythonExePath(InstallDir), wheel,
            RuntimeArchive: RuntimeArchivePath(state, cacheDir),
            WithDinov2: true);
        InstallOutcome outcome = await RunFlowOnProgressAsync(
            reset: true,
            (observe, ct) => _flow!.RunRepairAsync(plan, observe, ct));
        if (outcome.Ok)
        {
            string now = DateTimeOffset.UtcNow.ToString("o");
            _stateStore.Save(InstallDir, state with
            {
                Dirty = false,
                LastVerify = new LastVerifyState { Ts = now, Ok = true, AppVersion = state.AppVersion },
            });
            ReloadExisting();
            Navigate(WizardPage.Installed);
            MessageDialog.Show(Application.Current?.MainWindow, Strings.AppTitle, Strings.RepairCompleteMessage);
            return;
        }
        HandleFailedRun(outcome);
    }

    private static string? RuntimeArchivePath(InstallState state, string cacheDir)
        => state.Runtime is { Name.Length: > 0 } runtime ? Path.Combine(cacheDir, runtime.Name) : null;

    /// <summary>Spec §6.6: no HAVC process may run from the install folder during a run.</summary>
    private bool EnsureInstancesClosed()
    {
        var guard = new ProcessGuard();
        while (true)
        {
            IReadOnlyList<ProcessInfo> running = guard.FindRunning(InstallDir);
            if (running.Count == 0)
                return true;
            switch (ProcessLockWindow.Show(Application.Current?.MainWindow, running))
            {
                case LockChoice.Cancel:
                    return false;
                case LockChoice.Terminate:
                    ProcessGuard.Terminate(running);
                    Thread.Sleep(800);
                    break;
                case LockChoice.Retry:
                    break;
            }
        }
    }

    private async Task<InstallOutcome> RunFlowOnProgressAsync(
        bool reset,
        Func<Action<FlowEvent>, CancellationToken, Task<InstallOutcome>> run)
    {
        if (reset)
        {
            Steps.Clear();
            LogLines.Clear();
            _failureDetail = null;
            _failureRemediation = null;
        }
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
        try
        {
            return await run(ev => OnUi(() => ApplyFlowEvent(ev)), _cts.Token);
        }
        finally
        {
            _flow.Runner.EventReceived -= OnBootstrapEvent;
            IsRunning = false;
            _cts.Dispose();
            _cts = null;
        }
    }

    private void HandleFailedRun(InstallOutcome outcome)
    {
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

    public void OpenProjectPage()
        => ShellIntegration.OpenUrl("https://github.com/dan64/HAVCServerDiT/releases");

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
            BackendDefault = DefaultBackend,
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
                SetStep(e.StepId, e.StepTitle, "running", null);
                break;
            case "step_ok":
                SetStep(e.StepId, null, "ok", e.Detail);
                break;
            case "step_skip":
                SetStep(e.StepId, null, "skipped", e.Reason);
                break;
            case "step_error":
                _failureDetail = e.Error;
                _failureRemediation = e.Remediation;
                SetStep(e.StepId, null, "error", e.Error);
                break;
            case "log":
                AppendLog(e.Message);
                break;
        }
    }

    private void SetStep(string? id, string? title, string status, string? detail)
    {
        if (string.IsNullOrEmpty(id))
            return;
        StepItem? item = Steps.FirstOrDefault(s => s.Id == id);
        if (item is null)
        {
            // Defensive: keep the run visible even if the plan was not received.
            item = new StepItem(id, title ?? id);
            Steps.Add(item);
            Notify(nameof(ProgressMaximum));
        }
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

    public void StartServer()
        => ShellIntegration.StartServer(
            InstallDir,
            Existing?.State.BackendDefault is { Length: > 0 } backend ? backend : DefaultBackend);

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
            // The manager itself lives in the install folder: self-removal
            // worker (copy the whole application so it runs standalone).
            string tempDir = Path.Combine(
                Path.GetTempPath(), $"HAVCManager-uninstall-{Guid.NewGuid():N}");
            string tempCopy = Path.Combine(tempDir, "HAVCManager.exe");
            ShellIntegration.CopyManagerFiles(tempCopy);
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
        MessageDialog.Show(Application.Current.MainWindow, Strings.AppTitle, Strings.UninstallDoneMessage);
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
        => MessageDialog.Show(Application.Current?.MainWindow, title, message);

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
