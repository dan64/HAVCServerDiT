using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Media;

namespace HavcManager.App.Wizard;

/// <summary>One row of the 21-step progress list (status: pending/running/skipped/ok/error).</summary>
public sealed class StepItem : INotifyPropertyChanged
{
    private string _status = "pending";
    private string? _detail;

    public StepItem(string id, string title)
    {
        Id = id;
        Title = title;
    }

    public string Id { get; }
    public string Title { get; }

    public string Status
    {
        get => _status;
        set
        {
            if (_status == value)
                return;
            _status = value;
            Notify();
            Notify(nameof(Glyph));
            Notify(nameof(StatusBrush));
        }
    }

    public string? Detail
    {
        get => _detail;
        set
        {
            if (_detail == value)
                return;
            _detail = value;
            Notify();
        }
    }

    public string Glyph => _status switch
    {
        "running" => "\u25B6",
        "ok" => "\u2714",
        "skipped" => "\u2192",
        "error" => "\u2716",
        _ => "\u00B7",
    };

    public Brush StatusBrush => _status switch
    {
        "ok" => Brushes.Green,
        "skipped" => Brushes.Gray,
        "error" => Brushes.Firebrick,
        "running" => Brushes.SteelBlue,
        _ => Brushes.DimGray,
    };

    public event PropertyChangedEventHandler? PropertyChanged;

    private void Notify([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
