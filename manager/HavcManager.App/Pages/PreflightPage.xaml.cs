using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class PreflightPage : UserControl
{
    public PreflightPage() => InitializeComponent();

    private void OnBackClick(object sender, RoutedEventArgs e)
        => ((WizardViewModel)DataContext).Navigate(WizardPage.Welcome);

    private void OnContinueClick(object sender, RoutedEventArgs e)
        => ((WizardViewModel)DataContext).Navigate(WizardPage.Folders);
}
