using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class WelcomePage : UserControl
{
    public WelcomePage() => InitializeComponent();

    private async void OnStartClick(object sender, RoutedEventArgs e)
        => await ((WizardViewModel)DataContext).StartPreflightAsync();
}
