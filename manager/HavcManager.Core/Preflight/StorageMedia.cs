using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace HavcManager.Core.Preflight;

public enum StorageKind
{
    Unknown,
    Ssd,
    Hdd,
}

/// <summary>
/// Tells whether the volume holding a path lives on a solid-state drive or on
/// a rotating disk. The signal is the device's seek-penalty property
/// (IOCTL_STORAGE_QUERY_PROPERTY), the same one the embedded ComfyUI core
/// uses on Windows to decide its "fast disk" storage policy — so a warning
/// given here matches what the server will actually do with the models.
/// No administrator rights are needed; on any failure the answer is Unknown
/// (the caller stays silent rather than guessing).
/// </summary>
public static class StorageMedia
{
    private const uint IoctlStorageGetDeviceNumber = 0x002D1080;
    private const uint IoctlStorageQueryProperty = 0x002D1400;
    private const uint StorageDeviceSeekPenaltyProperty = 7;
    private const uint PropertyStandardQuery = 0;
    private const uint OpenExisting = 3;
    private const uint ShareReadWrite = 3;

    public static StorageKind KindForPath(string path)
    {
        string root;
        try
        {
            root = Path.GetPathRoot(Path.GetFullPath(path)) ?? "";
        }
        catch (Exception)
        {
            return StorageKind.Unknown;
        }

        // Only mounted drive letters: UNC shares and unrooted paths have no
        // local device to ask about.
        if (root.Length < 2 || !char.IsLetter(root[0]) || root[1] != ':')
            return StorageKind.Unknown;

        string volume = @"\\.\" + char.ToUpperInvariant(root[0]) + ":";
        using SafeFileHandle handle = CreateFileW(
            volume, 0, ShareReadWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
        if (handle.IsInvalid)
            return StorageKind.Unknown;

        if (!DeviceIoControl(
                handle, IoctlStorageGetDeviceNumber,
                IntPtr.Zero, 0, out uint diskNumber, out _))
        {
            return StorageKind.Unknown;
        }

        using SafeFileHandle physical = CreateFileW(
            @"\\.\PhysicalDrive" + diskNumber, 0, ShareReadWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
        if (physical.IsInvalid)
            return StorageKind.Unknown;

        return DeviceIoControl(
            physical, IoctlStorageQueryProperty,
            StorageDeviceSeekPenaltyProperty, PropertyStandardQuery, out bool seekPenalty, out _)
            ? (seekPenalty ? StorageKind.Hdd : StorageKind.Ssd)
            : StorageKind.Unknown;
    }

    /// <summary>STORAGE_DEVICE_NUMBER: only DeviceNumber is read.</summary>
    private static bool DeviceIoControl(
        SafeFileHandle device,
        uint code,
        IntPtr input,
        uint inputSize,
        out uint diskNumber,
        out uint returned)
    {
        IntPtr output = Marshal.AllocHGlobal(32);
        try
        {
            bool ok = DeviceIoControl(device, code, input, inputSize, output, 32, out returned, IntPtr.Zero);
            diskNumber = ok ? (uint)Marshal.ReadInt32(output, 4) : 0;
            return ok;
        }
        finally
        {
            Marshal.FreeHGlobal(output);
        }
    }

    /// <summary>DEVICE_SEEK_PENALTY_DESCRIPTOR: IncursSeekPenalty at offset 8.</summary>
    private static bool DeviceIoControl(
        SafeFileHandle device,
        uint code,
        uint propertyId,
        uint queryType,
        out bool seekPenalty,
        out uint returned)
    {
        IntPtr input = Marshal.AllocHGlobal(12);
        IntPtr output = Marshal.AllocHGlobal(32);
        try
        {
            Marshal.WriteInt32(input, 0, (int)propertyId);
            Marshal.WriteInt32(input, 4, (int)queryType);
            bool ok = DeviceIoControl(device, code, input, 12, output, 32, out returned, IntPtr.Zero);
            seekPenalty = ok && Marshal.ReadByte(output, 8) != 0;
            return ok;
        }
        finally
        {
            Marshal.FreeHGlobal(input);
            Marshal.FreeHGlobal(output);
        }
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern SafeFileHandle CreateFileW(
        string name,
        uint access,
        uint share,
        IntPtr securityAttributes,
        uint disposition,
        uint flags,
        IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeviceIoControl(
        SafeFileHandle device,
        uint code,
        IntPtr input,
        uint inputSize,
        IntPtr output,
        uint outputSize,
        out uint returned,
        IntPtr overlapped);
}
