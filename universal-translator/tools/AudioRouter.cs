using System;
using System.Runtime.InteropServices;

namespace UltAudio {

    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceEnumerator {
        int EnumAudioEndpoints(uint dataFlow, uint dwStateMask, out IntPtr ppDevices);
        int GetDefaultAudioEndpoint(uint dataFlow, uint role, out IntPtr ppEndpoint);
        int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string pwstrId, out IntPtr ppDevice);
        int RegisterEndpointNotificationCallback(IntPtr pClient);
        int UnregisterEndpointNotificationCallback(IntPtr pClient);
    }

    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDevice {
        int Activate(ref Guid iid, uint dwClsCtx, IntPtr pActivationParams, out IntPtr ppInterface);
        int OpenPropertyStore(uint stgmAccess, out IntPtr ppProperties);
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string ppstrId);
        int GetState(out uint pdwState);
    }

    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceCollection {
        int GetCount(out uint pcDevices);
        int Item(uint nDevice, out IntPtr ppDevice);
    }

    [ComImport, Guid("F8679F50-850A-41CF-9C72-430F290290C8"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPolicyConfig {
        int GetMixFormat([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr ppFormat);
        int GetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string dev, bool bDefault, IntPtr ppFormat);
        int ResetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string dev);
        int SetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr pEndpointFormat, IntPtr MixFormat);
        int GetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string dev, bool bDefault, IntPtr a, IntPtr b);
        int SetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr pmftPeriod);
        int GetShareMode([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr pMode);
        int SetShareMode([MarshalAs(UnmanagedType.LPWStr)] string dev, IntPtr mode);
        int GetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string dev, bool bFxStore, IntPtr key, IntPtr pv);
        int SetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string dev, bool bFxStore, IntPtr key, IntPtr pv);
        int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string dev, uint role);
        int SetEndpointVisibility([MarshalAs(UnmanagedType.LPWStr)] string dev, bool bVisible);
    }

    public static class AudioRouter {

        static readonly Guid CLSID_MMDeviceEnumerator = new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E");
        static readonly Guid IID_IMMDeviceEnumerator   = new Guid("A95664D2-9614-4F35-A746-DE8DB63617E6");
        static readonly Guid CLSID_PolicyConfig        = new Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9");
        static readonly Guid IID_IPolicyConfig         = new Guid("F8679F50-850A-41CF-9C72-430F290290C8");

        [DllImport("ole32.dll")]
        static extern int CoCreateInstance(ref Guid clsid, IntPtr pUnk, uint ctx, ref Guid iid, out IntPtr ppv);

        static IMMDeviceEnumerator GetEnumerator() {
            IntPtr ppv;
            var clsid = CLSID_MMDeviceEnumerator;
            var iid   = IID_IMMDeviceEnumerator;
            int hr = CoCreateInstance(ref clsid, IntPtr.Zero, 1, ref iid, out ppv);
            if (hr != 0) throw new Exception("IMMDeviceEnumerator hr=0x" + hr.ToString("X8"));
            return (IMMDeviceEnumerator)Marshal.GetObjectForIUnknown(ppv);
        }

        static IPolicyConfig GetPolicyConfig() {
            IntPtr ppv;
            var clsid = CLSID_PolicyConfig;
            var iid   = IID_IPolicyConfig;
            int hr = CoCreateInstance(ref clsid, IntPtr.Zero, 1, ref iid, out ppv);
            if (hr != 0) throw new Exception("IPolicyConfig hr=0x" + hr.ToString("X8"));
            return (IPolicyConfig)Marshal.GetObjectForIUnknown(ppv);
        }

        public static string GetDefaultId() {
            var e = GetEnumerator();
            IntPtr pDev;
            e.GetDefaultAudioEndpoint(0, 1, out pDev);
            var dev = (IMMDevice)Marshal.GetObjectForIUnknown(pDev);
            string id; dev.GetId(out id);
            Marshal.ReleaseComObject(dev);
            Marshal.ReleaseComObject(e);
            return id;
        }

        public static string[] GetAllIds() {
            var e = GetEnumerator();
            IntPtr pCol;
            e.EnumAudioEndpoints(0, 1, out pCol);
            var col = (IMMDeviceCollection)Marshal.GetObjectForIUnknown(pCol);
            uint count; col.GetCount(out count);
            var ids = new string[count];
            for (uint i = 0; i < count; i++) {
                IntPtr pDev; col.Item(i, out pDev);
                var dev = (IMMDevice)Marshal.GetObjectForIUnknown(pDev);
                string id; dev.GetId(out id);
                ids[i] = id;
                Marshal.ReleaseComObject(dev);
            }
            Marshal.ReleaseComObject(col);
            Marshal.ReleaseComObject(e);
            return ids;
        }

        public static void SetDefault(string deviceId) {
            var p = GetPolicyConfig();
            p.SetDefaultEndpoint(deviceId, 0);
            p.SetDefaultEndpoint(deviceId, 1);
            p.SetDefaultEndpoint(deviceId, 2);
            Marshal.ReleaseComObject(p);
        }
    }
}
