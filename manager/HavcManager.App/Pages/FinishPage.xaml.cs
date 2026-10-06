using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class FinishPage : UserControl
{
    public FinishPage() => InitializeComponent();

    private WizardViewModel ViewModel => (WizardViewModel)DataContext;

    private void OnOpenGuiClick(object sender, RoutedEventArgs e) => ViewModel.OpenGui();

    private void OnStartServerClick(object sender, RoutedEventArgs e) => ViewModel.StartServer();

    private void OnOpenFolderClick(object sender, RoutedEventArgs e) => ViewModel.OpenWorkFolder();

    private void OnShowLogClick(object sender, RoutedEventArgs e) => ViewModel.OpenLogs();

    private void OnCloseClick(object sender, RoutedEventArgs e) => Application.Current.Shutdown();
}
