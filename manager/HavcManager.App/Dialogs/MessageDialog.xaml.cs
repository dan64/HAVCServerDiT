using System.Windows;
using System.Windows.Controls;
using HavcManager.App.Resources;
using HavcManager.App.Windows;

namespace HavcManager.App.Dialogs;

/// <summary>
/// Small English UI dialog used across the manager (deterministic captions and
/// buttons, unlike the OS-localized MessageBox — PHASE1_SPEC §2, §8).
/// </summary>
public partial class MessageDialog : Window
{
    private string? _linkUrl;

    private MessageDialog() => InitializeComponent();

    /// <summary>Shows the dialog; returns true for OK/Yes, false for No/close.</summary>
    public static bool Show(
        Window? owner,
        string title,
        string message,
        bool yesNo = false,
        string? linkText = null,
        string? linkUrl = null)
    {
        var dialog = new MessageDialog { Title = title };
        if (owner is not null)
            dialog.Owner = owner;
        dialog.MessageText.Text = message;
        if (!string.IsNullOrEmpty(linkText) && !string.IsNullOrEmpty(linkUrl))
        {
            dialog._linkUrl = linkUrl;
            dialog.LinkRun.Text = linkText;
            dialog.LinkBlock.Visibility = Visibility.Visible;
        }

        var ok = new Button
        {
            Content = yesNo ? Strings.YesButton : "OK",
            Padding = new Thickness(14, 7, 14, 7),
            IsDefault = true,
        };
        ok.Click += (_, _) => dialog.DialogResult = true;
        dialog.ButtonsPanel.Children.Add(ok);
        if (yesNo)
        {
            var no = new Button
            {
                Content = Strings.NoButton,
                Padding = new Thickness(14, 7, 14, 7),
                IsCancel = true,
                Margin = new Thickness(0, 0, 8, 0),
            };
            no.Click += (_, _) => dialog.DialogResult = false;
            dialog.ButtonsPanel.Children.Insert(0, no);
        }

        return dialog.ShowDialog() == true;
    }

    private void OnLinkClick(object sender, RoutedEventArgs e)
    {
        if (_linkUrl is not null)
            ShellIntegration.OpenUrl(_linkUrl);
    }
}
