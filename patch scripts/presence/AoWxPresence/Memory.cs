// Read-only access to the running (32-bit) game: module bases via Toolhelp, values via ReadProcessMemory.
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace AoWxPresence
{
    internal sealed class Memory : IDisposable
    {
        const uint PROCESS_VM_READ = 0x10, PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        const uint TH32CS_SNAPMODULE = 0x8, TH32CS_SNAPMODULE32 = 0x10;

        [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
        [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int read);
        [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags, int pid);
        [DllImport("kernel32.dll", CharSet = CharSet.Ansi)] static extern bool Module32First(IntPtr snap, ref MODULEENTRY32 me);
        [DllImport("kernel32.dll", CharSet = CharSet.Ansi)] static extern bool Module32Next(IntPtr snap, ref MODULEENTRY32 me);

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        struct MODULEENTRY32
        {
            public uint dwSize, th32ModuleID, th32ProcessID, GlblcntUsage, ProccntUsage;
            public IntPtr modBaseAddr;
            public uint modBaseSize;
            public IntPtr hModule;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string szModule;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string szExePath;
        }

        readonly int pid;
        IntPtr h;

        internal Memory(int pid)
        {
            this.pid = pid;
            h = OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION, false, pid);
            if (h == IntPtr.Zero) Program.Log("OpenProcess failed: " + Marshal.GetLastWin32Error());
        }

        internal bool Ok { get { return h != IntPtr.Zero; } }

        internal uint ModuleBase(string name)
        {
            IntPtr snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
            if (snap == IntPtr.Zero || snap == new IntPtr(-1)) return 0;
            try
            {
                MODULEENTRY32 me = new MODULEENTRY32();
                me.dwSize = (uint)Marshal.SizeOf(typeof(MODULEENTRY32));
                for (bool ok = Module32First(snap, ref me); ok; ok = Module32Next(snap, ref me))
                    if (string.Equals(me.szModule, name, StringComparison.OrdinalIgnoreCase))
                        return (uint)me.modBaseAddr.ToInt64();
                return 0;
            }
            finally { CloseHandle(snap); }
        }

        internal byte[] Bytes(uint addr, int n)
        {
            if (h == IntPtr.Zero || addr < 0x10000) return null;
            byte[] b = new byte[n];
            int got;
            return ReadProcessMemory(h, new IntPtr(addr), b, n, out got) && got == n ? b : null;
        }

        internal uint U32(uint addr) { byte[] b = Bytes(addr, 4); if (b == null) throw new InvalidOperationException(); return BitConverter.ToUInt32(b, 0); }
        internal int I32(uint addr) { return (int)U32(addr); }
        internal byte U8(uint addr) { byte[] b = Bytes(addr, 1); if (b == null) throw new InvalidOperationException(); return b[0]; }

        // Delphi AnsiString: pointer to the chars, int32 length at [p-4]
        internal string AnsiStr(uint p)
        {
            if (p == 0) return "";
            int len = I32(p - 4);
            if (len <= 0 || len > 1024) return "";
            byte[] b = Bytes(p, len);
            return b == null ? "" : Encoding.GetEncoding(1252).GetString(b);
        }

        // Delphi ShortString: length byte + chars
        internal string ShortStr(uint addr)
        {
            int len = U8(addr);
            byte[] b = len == 0 ? new byte[0] : Bytes(addr + 1, len);
            return b == null ? "" : Encoding.GetEncoding(1252).GetString(b);
        }

        public void Dispose() { if (h != IntPtr.Zero) { CloseHandle(h); h = IntPtr.Zero; } }
    }
}
