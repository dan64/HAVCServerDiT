using System.Globalization;
using System.Windows.Data;
using System.Windows.Media;
using HavcManager.Core.Preflight;

namespace HavcManager.App;

/// <summary>Glyph for a preflight check status.</summary>
public sealed class PreflightStatusGlyphConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value switch
        {
            PreflightStatus.Ok => "OK",
            PreflightStatus.Warning => "!",
            PreflightStatus.Error => "X",
            _ => "?",
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>Brush for a preflight check status.</summary>
public sealed class PreflightStatusBrushConverter : IValueConverter
{
    private static readonly Brush OkBrush = new SolidColorBrush(Color.FromRgb(0x1B, 0x7F, 0x3B));
    private static readonly Brush WarningBrush = new SolidColorBrush(Color.FromRgb(0xB5, 0x6A, 0x00));
    private static readonly Brush ErrorBrush = new SolidColorBrush(Color.FromRgb(0xB0, 0x1B, 0x1B));

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value switch
        {
            PreflightStatus.Ok => OkBrush,
            PreflightStatus.Warning => WarningBrush,
            PreflightStatus.Error => ErrorBrush,
            _ => Brushes.Gray,
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
