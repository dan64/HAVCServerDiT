using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class SummaryPage : UserControl
{
    public SummaryPage() => InitializeComponent();

    private WizardViewModel ViewModel => (WizardViewModel)DataContext;

    private void OnBackClick(object sender, RoutedEventArgs e)
        => ViewModel.Navigate(WizardPage.Components);

    private async void OnInstallClick(object sender, RoutedEventArgs e)
        => await ViewModel.StartInstallAsync();

    private void OnNotesClick(object sender, RoutedEventArgs e)
        => ViewModel.OpenReleaseNotes();
}
