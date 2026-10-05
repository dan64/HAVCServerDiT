using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class ComponentsPage : UserControl
{
    public ComponentsPage() => InitializeComponent();

    private void OnBackClick(object sender, RoutedEventArgs e)
        => ((WizardViewModel)DataContext).Navigate(WizardPage.Folders);

    private void OnContinueClick(object sender, RoutedEventArgs e)
        => ((WizardViewModel)DataContext).Navigate(WizardPage.Summary);
}
