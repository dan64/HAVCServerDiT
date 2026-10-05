using System.Windows;
using HavcManager.App.Resources;

namespace HavcManager.App;

/// <summary>
/// M1 shell: a single window with the wizard entry point. The full wizard
/// pages arrive with the M2 flow (PHASE1_SPEC §8).
/// </summary>
public partial class MainWindow : Window
{
    public MainWindow() => InitializeComponent();

    private void OnStartInstallationClick(object sender, RoutedEventArgs e)
        => MessageBox.Show(
            this,
            Strings.NotImplementedYet,
            Strings.AppTitle,
            MessageBoxButton.OK,
            MessageBoxImage.Information);
}
