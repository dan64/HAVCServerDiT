using System.Windows;
using HavcManager.App.Wizard;

namespace HavcManager.App;

/// <summary>Wizard shell: hosts the current page and drives the view-model.</summary>
public partial class MainWindow : Window
{
    private readonly WizardViewModel _vm;

    public MainWindow(AppOptions options)
    {
        InitializeComponent();
        _vm = new WizardViewModel(options);
        _vm.PageChanged += ShowCurrentPage;
        _vm.UninstallRequestedFromArgs += () => Dispatcher.InvokeAsync(
            () => _ = UninstallFlow.RequestAsync(this, _vm));
        _vm.Initialize();
        ShowCurrentPage();
    }

    internal WizardViewModel ViewModel => _vm;

    private void ShowCurrentPage()
    {
        FrameworkElement page = _vm.CurrentPage switch
        {
            WizardPage.Preflight => new Pages.PreflightPage(),
            WizardPage.Folders => new Pages.FoldersPage(),
            WizardPage.Components => new Pages.ComponentsPage(),
            WizardPage.Summary => new Pages.SummaryPage(),
            WizardPage.Progress => new Pages.ProgressPage(),
            WizardPage.Finish => new Pages.FinishPage(),
            WizardPage.Installed => new Pages.InstalledPage(),
            _ => new Pages.WelcomePage(),
        };
        page.DataContext = _vm;
        Root.Content = page;
    }
}
