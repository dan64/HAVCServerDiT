using System.Windows;
using HavcManager.App.Resources;
using HavcManager.App.Windows;

namespace HavcManager.App;

/// <summary>Application entry point (arguments: see <see cref="AppOptions"/>).</summary>
public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // Surface unexpected errors instead of vanishing silently (debug aid).
        DispatcherUnhandledException += (_, args) =>
        {
            try
            {
                Dialogs.MessageDialog.Show(MainWindow, Strings.UnexpectedErrorTitle, args.Exception.ToString());
            }
            catch (Exception)
            {
                // the handler must never throw
            }
        };
        AppOptions options;
        try
        {
            options = AppOptions.Parse(e.Args);
        }
        catch (ArgumentException ex)
        {
            MessageBox.Show(ex.Message, "HAVC Setup", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(2);
            return;
        }

        if (options.UninstallRunDir is { } installDir)
        {
            UninstallWorker.Run(installDir, keepComfyModels: !options.UninstallRunDeleteModels);
            Shutdown();
            return;
        }

        var window = new MainWindow(options);
        MainWindow = window;
        window.Show();
    }
}
