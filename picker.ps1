param(
    [string]$Title = "Select Folder",
    [string]$InitialFolder = ""
)

$code = @'
using System;
using System.Runtime.InteropServices;

public class NativeFolderPicker {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    public static extern void SHCreateItemFromParsingName(
        [MarshalAs(UnmanagedType.LPWStr)] string pszPath,
        IntPtr pbc,
        [MarshalAs(UnmanagedType.LPStruct)] Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out IShellItem ppv);

    [ComImport]
    [Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
    [CoClass(typeof(FileOpenDialogClass))]
    public interface FileOpenDialog : IFileOpenDialog {}

    [ComImport]
    [Guid("d57c7288-d4ad-4768-be02-9d969532d960")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IFileOpenDialog {
        // IModalWindow
        [PreserveSig] int Show(IntPtr parent);

        // IFileDialog
        void SetFileTypes(uint cFileTypes, IntPtr rgFilterSpec);
        void SetFileTypeIndex(uint iFileType);
        void GetFileTypeIndex(out uint piFileType);
        void Advise(IntPtr pfde, out uint pdwCookie);
        void Unadvise(uint dwCookie);
        void SetOptions(uint fos);
        void GetOptions(out uint fos);
        void SetDefaultFolder(IShellItem psi);
        void SetFolder(IShellItem psi);
        void GetFolder(out IShellItem ppsi);
        void GetCurrentSelection(out IShellItem ppsi);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string pszName);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
        void GetResult(out IShellItem ppsi);
        void AddPlace(IShellItem psi, uint fdap);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string pszDefaultExtension);
        void Close([MarshalAs(UnmanagedType.Error)] int hr);
        void SetClientGuid([In, MarshalAs(UnmanagedType.LPStruct)] Guid guid);
        void ClearClientData();
        void SetFilter(IntPtr pFilter);

        // IFileOpenDialog
        void GetResults(out IntPtr ppenum);
        void GetSelectedItems(out IntPtr ppsai);
    }

    [ComImport]
    [Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IShellItem {
        void BindToHandler(IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid bhid, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IntPtr ppv);
        void GetParent(out IShellItem ppsi);
        void GetDisplayName(uint sigdnName, [MarshalAs(UnmanagedType.LPWStr)] out string ppszName);
        void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
        void Compare(IShellItem psi, uint hint, out int piOrder);
    }

    [ComImport]
    [Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
    [ClassInterface(ClassInterfaceType.None)]
    [TypeLibType(TypeLibTypeFlags.FCanCreate)]
    public class FileOpenDialogClass {}

    public static string ShowPicker(string title, string initialFolder) {
        var dialog = (IFileOpenDialog)new FileOpenDialogClass();
        uint FOS_PICKFOLDERS = 0x00000020;
        uint FOS_FORCEFILESYSTEM = 0x00000040;
        dialog.SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM);
        if (!string.IsNullOrEmpty(title)) {
            dialog.SetTitle(title);
        }
        if (!string.IsNullOrEmpty(initialFolder)) {
            try {
                IShellItem item;
                Guid IID_IShellItem = new Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe");
                SHCreateItemFromParsingName(initialFolder, IntPtr.Zero, IID_IShellItem, out item);
                if (item != null) dialog.SetFolder(item);
            } catch {}
        }
        IntPtr parent = GetForegroundWindow();
        int hr = dialog.Show(parent);
        if (hr == 0) {
            IShellItem res;
            dialog.GetResult(out res);
            if (res != null) {
                string path;
                res.GetDisplayName(0x80058000, out path); // SIGDN_FILESYSPATH
                return path;
            }
        }
        return null;
    }
}
'@

try {
    Add-Type -TypeDefinition $code -ErrorAction Stop
} catch {}

$path = [NativeFolderPicker]::ShowPicker($Title, $InitialFolder)
if ($path) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $path
}
