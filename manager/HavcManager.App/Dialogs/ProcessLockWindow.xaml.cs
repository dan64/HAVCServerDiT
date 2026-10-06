using System.Windows;
using HavcManager.App.Resources;
using HavcManager.Core.Processes;

namespace HavcManager.App.Dialogs;

public enum LockChoice
{
    Retry,
    Terminate,
    Cancel,
}

/// <summary>
/// "Close the GUI/server to continue" dialog (PHASE1_SPEC §6.6): lists the
/// HAVC processes found under the install folder and lets the user retry,
/// terminate them, or cancel.
/// </summary>
public partial class ProcessLockWindow : Window
{
    private ProcessLockWindow() => InitializeComponent();

    public static LockChoice Show(Window? owner, IReadOnlyList<ProcessInfo> processes)
    {
        var dialog = new ProcessLockWindow { Title = Strings.LockDialogTitle };
        if (owner is not null)
            dialog.Owner = owner;
        dialog.ProcessList.ItemsSource = processes
            .Select(p => $"PID {p.Pid}  {p.ExecutablePath}")
            .ToList();
        return dialog.ShowDialog() switch
        {
            true => dialog._choice,
            _ => LockChoice.Cancel,
        };
    }

    private LockChoice _choice = LockChoice.Cancel;

    private void OnRetryClick(object sender, RoutedEventArgs e)
    {
        _choice = LockChoice.Retry;
        DialogResult = true;
    }

    private void OnTerminateClick(object sender, RoutedEventArgs e)
    {
        _choice = LockChoice.Terminate;
        DialogResult = true;
    }

    private void OnCancelClick(object sender, RoutedEventArgs e)
    {
        _choice = LockChoice.Cancel;
        DialogResult = false;
    }
}
