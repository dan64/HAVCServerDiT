using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Wizard;

namespace HavcManager.App;

public partial class UninstallConfirmWindow : Window
{
    public UninstallConfirmWindow() => InitializeComponent();

    public bool DeleteModels => DeleteModelsCheck.IsChecked == true;

    private void OnRemoveClick(object sender, RoutedEventArgs e) => DialogResult = true;
}

/// <summary>Shared confirm-and-uninstall flow (button on the Installed page, --uninstall).</summary>
internal static class UninstallFlow
{
    public static async Task RequestAsync(Window owner, WizardViewModel vm)
    {
        var dialog = new UninstallConfirmWindow { Owner = owner };
        if (dialog.ShowDialog() == true)
            await vm.UninstallAsync(dialog.DeleteModels);
    }
}
