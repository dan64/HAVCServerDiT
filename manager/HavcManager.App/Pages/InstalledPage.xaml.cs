using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class InstalledPage : UserControl
{
    public InstalledPage() => InitializeComponent();

    private WizardViewModel ViewModel => (WizardViewModel)DataContext;

    private void OnOpenGuiClick(object sender, RoutedEventArgs e) => ViewModel.OpenGui();

    private void OnOpenFolderClick(object sender, RoutedEventArgs e) => ViewModel.OpenWorkFolder();

    private async void OnUninstallClick(object sender, RoutedEventArgs e)
        => await UninstallFlow.RequestAsync(Window.GetWindow(this), ViewModel);

    private void OnCloseClick(object sender, RoutedEventArgs e) => Application.Current.Shutdown();
}
