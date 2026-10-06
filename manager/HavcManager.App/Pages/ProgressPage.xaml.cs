using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App.Pages;

public partial class ProgressPage : UserControl
{
    public ProgressPage() => InitializeComponent();

    private void OnCancelClick(object sender, RoutedEventArgs e)
        => ((WizardViewModel)DataContext).RequestCancel();

    private void OnCloseClick(object sender, RoutedEventArgs e)
        => Application.Current.Shutdown();
}
