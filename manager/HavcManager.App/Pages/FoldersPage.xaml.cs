using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Resources;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class FoldersPage : UserControl
{
    public FoldersPage() => InitializeComponent();

    private WizardViewModel ViewModel => (WizardViewModel)DataContext;

    private void OnBrowseInstall(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = Strings.LabelInstallFolder,
            InitialDirectory = ViewModel.InstallDir,
        };
        if (dialog.ShowDialog() == true)
            ViewModel.InstallDir = dialog.FolderName;
    }

    private void OnBackClick(object sender, RoutedEventArgs e)
        => ViewModel.Navigate(WizardPage.Preflight);

    private async void OnContinueClick(object sender, RoutedEventArgs e)
        => await ViewModel.ContinueFromFoldersAsync();
}
