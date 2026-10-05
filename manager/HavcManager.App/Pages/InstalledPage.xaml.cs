using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class InstalledPage : UserControl
{
    public InstalledPage() => InitializeComponent();

    private WizardViewModel ViewModel => (WizardViewModel)DataContext;

    private void OnOpenGuiClick(object sender, RoutedEventArgs e) => ViewModel.OpenGui();

    private void OnStartServerClick(object sender, RoutedEventArgs e) => ViewModel.StartServer();

    private async void OnCheckUpdatesClick(object sender, RoutedEventArgs e)
        => await ViewModel.CheckForUpdatesAsync();

    private async void OnRepairClick(object sender, RoutedEventArgs e)
        => await ViewModel.StartRepairAsync();

    private async void OnUninstallClick(object sender, RoutedEventArgs e)
        => await UninstallFlow.RequestAsync(Window.GetWindow(this), ViewModel);

    private void OnShowLogClick(object sender, RoutedEventArgs e) => ViewModel.OpenLogs();

    private void OnProjectLinkClick(object sender, RoutedEventArgs e) => ViewModel.OpenProjectPage();

    private void OnCloseClick(object sender, RoutedEventArgs e) => Application.Current.Shutdown();
}
