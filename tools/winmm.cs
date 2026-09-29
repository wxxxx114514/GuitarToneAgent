using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Diagnostics;

public class WinMM
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct WAVEOUTCAPS { public ushort wMid; public ushort wPid; public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szPname;
        public uint dwFormats; public ushort wChannels; public ushort wReserved1; public uint dwSupport; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct WAVEINCAPS { public ushort wMid; public ushort wPid; public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szPname;
        public uint dwFormats; public ushort wChannels; public ushort wReserved1; }
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    public struct WAVEFORMATEX { public ushort wFormatTag; public ushort nChannels; public uint nSamplesPerSec;
        public uint nAvgBytesPerSec; public ushort nBlockAlign; public ushort wBitsPerSample; public ushort cbSize; }
    [StructLayout(LayoutKind.Sequential)]
    public struct WAVEHDR { public IntPtr lpData; public uint dwBufferLength; public uint dwBytesRecorded;
        public IntPtr dwUser; public uint dwFlags; public uint dwLoops; public IntPtr lpNext; public IntPtr reserved; }

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern uint waveOutGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern int waveOutGetDevCaps(IntPtr id, out WAVEOUTCAPS c, uint sz);
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern uint waveInGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern int waveInGetDevCaps(IntPtr id, out WAVEINCAPS c, uint sz);
    [DllImport("winmm.dll")] static extern int waveOutOpen(out IntPtr h, int id, ref WAVEFORMATEX f, IntPtr cb, IntPtr inst, int flags);
    [DllImport("winmm.dll")] static extern int waveOutPrepareHeader(IntPtr h, IntPtr hdr, uint sz);
    [DllImport("winmm.dll")] static extern int waveOutWrite(IntPtr h, IntPtr hdr, uint sz);
    [DllImport("winmm.dll")] static extern int waveOutUnprepareHeader(IntPtr h, IntPtr hdr, uint sz);
    [DllImport("winmm.dll")] static extern int waveOutClose(IntPtr h);
    [DllImport("winmm.dll")] static extern int waveInOpen(out IntPtr h, int id, ref WAVEFORMATEX f, IntPtr cb, IntPtr inst, int flags);
    [DllImport("winmm.dll")] static extern int waveInPrepareHeader(IntPtr h, IntPtr hdr, uint sz);
    [DllImport("winmm.dll")] static extern int waveInAddBuffer(IntPtr h, IntPtr hdr, uint sz);
    [DllImport("winmm.dll")] static extern int waveInStart(IntPtr h);
    [DllImport("winmm.dll")] static extern int waveInStop(IntPtr h);
    [DllImport("winmm.dll")] static extern int waveInUnprepareHeader(IntPtr h, IntPtr hdr, uint sz);
    [DllImport("winmm.dll")] static extern int waveInReset(IntPtr h);
    [DllImport("winmm.dll")] static extern int waveInClose(IntPtr h);
    [DllImport("winmm.dll")] static extern int waveOutGetVolume(IntPtr h, out uint vol);
    [DllImport("winmm.dll")] static extern int waveOutSetVolume(IntPtr h, uint vol);
    [DllImport("winmm.dll")] static extern int waveInGetID(IntPtr h, out uint id);

    public static string GetVolumes() {
        var sb = new System.Text.StringBuilder();
        uint n = waveOutGetNumDevs();
        for (uint i = 0; i < n; i++) {
            uint v; int e = waveOutGetVolume((IntPtr)i, out v);
            WAVEOUTCAPS c; waveOutGetDevCaps((IntPtr)i, out c, (uint)Marshal.SizeOf(typeof(WAVEOUTCAPS)));
            uint L = v & 0xFFFF, R = (v >> 16) & 0xFFFF;
            sb.AppendLine("  out#" + i + "  L=" + (L*100/65535) + "% R=" + (R*100/65535) + "%  err=" + e + "  | " + c.szPname);
        }
        return sb.ToString();
    }
    public static string SetVol(int dev, int percent) {
        uint v = (uint)(percent * 65535 / 100);
        uint both = v | (v << 16);
        int e = waveOutSetVolume((IntPtr)dev, both);
        return "waveOutSetVolume(dev=" + dev + ", " + percent + "%) -> err=" + e;
    }

    const uint WHDR_DONE = 1;
    static WAVEFORMATEX Fmt(int sr, int ch, int bits) {
        WAVEFORMATEX f = new WAVEFORMATEX();
        f.wFormatTag = 1; f.nChannels = (ushort)ch; f.nSamplesPerSec = (uint)sr;
        f.wBitsPerSample = (ushort)bits; f.nBlockAlign = (ushort)(ch * bits / 8);
        f.nAvgBytesPerSec = (uint)(sr * f.nBlockAlign); return f;
    }
    public static string[] ListOut() {
        uint n = waveOutGetNumDevs(); string[] r = new string[n];
        for (uint i = 0; i < n; i++) { WAVEOUTCAPS c;
            int e = waveOutGetDevCaps((IntPtr)i, out c, (uint)Marshal.SizeOf(typeof(WAVEOUTCAPS)));
            r[i] = e == 0 ? (i + " | " + c.szPname + " | ch=" + c.wChannels) : (i + " | err=" + e); }
        return r;
    }
    public static string[] ListIn() {
        uint n = waveInGetNumDevs(); string[] r = new string[n];
        for (uint i = 0; i < n; i++) { WAVEINCAPS c;
            int e = waveInGetDevCaps((IntPtr)i, out c, (uint)Marshal.SizeOf(typeof(WAVEINCAPS)));
            r[i] = e == 0 ? (i + " | " + c.szPname + " | ch=" + c.wChannels + " | fmt=0x" + c.dwFormats.ToString("X4")) : (i + " | err=" + e); }
        return r;
    }
    public class Res { public byte[] Data; public string Info; }

    public static Res RecordOnly(int inDev, int sr, int ch, int bits, double seconds, int nbuf) {
        Res res = new Res();
        WAVEFORMATEX f = Fmt(sr, ch, bits);
        int blockAlign = ch * bits / 8;
        int per = (int)(sr * seconds / nbuf) * blockAlign;
        uint hsz = (uint)Marshal.SizeOf(typeof(WAVEHDR));
        IntPtr hin;
        int e = waveInOpen(out hin, inDev, ref f, IntPtr.Zero, IntPtr.Zero, 0);
        if (e != 0) { res.Info = "waveInOpen err=" + e; return res; }
        IntPtr[] bufs = new IntPtr[nbuf]; IntPtr[] hdrs = new IntPtr[nbuf];
        for (int i = 0; i < nbuf; i++) {
            bufs[i] = Marshal.AllocHGlobal(per);
            for (int k = 0; k < per; k++) Marshal.WriteByte(bufs[i], k, 0);
            WAVEHDR hd = new WAVEHDR(); hd.lpData = bufs[i]; hd.dwBufferLength = (uint)per;
            hdrs[i] = Marshal.AllocHGlobal((int)hsz); Marshal.StructureToPtr(hd, hdrs[i], false);
            waveInPrepareHeader(hin, hdrs[i], hsz); waveInAddBuffer(hin, hdrs[i], hsz);
        }
        Stopwatch sw = Stopwatch.StartNew(); waveInStart(hin);
        int done = 0;
        while (true) {
            done = 0;
            for (int i = 0; i < nbuf; i++) { WAVEHDR cur = (WAVEHDR)Marshal.PtrToStructure(hdrs[i], typeof(WAVEHDR));
                if ((cur.dwFlags & WHDR_DONE) != 0) done++; }
            if (done == nbuf) break;
            if (sw.Elapsed.TotalSeconds > seconds + 10) break;
            Thread.Sleep(5);
        }
        waveInStop(hin); waveInReset(hin);
        byte[] all = new byte[per * nbuf]; int off = 0;
        for (int i = 0; i < nbuf; i++) {
            Marshal.Copy(bufs[i], all, off, per); off += per;
            waveInUnprepareHeader(hin, hdrs[i], hsz);
            Marshal.FreeHGlobal(bufs[i]); Marshal.FreeHGlobal(hdrs[i]);
        }
        waveInClose(hin);
        res.Data = all;
        res.Info = "recorded " + seconds.ToString("F1") + "s in " + sw.Elapsed.TotalSeconds.ToString("F2") + "s buffers=" + done + "/" + nbuf;
        return res;
    }

    public static Res Duplex(int outDev, int inDev, byte[] play, int sr, int ch, int bits, double recSeconds, int nbuf) {
        Res res = new Res();
        WAVEFORMATEX f = Fmt(sr, ch, bits);
        int blockAlign = ch * bits / 8;
        int per = (int)(sr * recSeconds / nbuf) * blockAlign;
        uint hsz = (uint)Marshal.SizeOf(typeof(WAVEHDR));
        IntPtr hin;
        int e = waveInOpen(out hin, inDev, ref f, IntPtr.Zero, IntPtr.Zero, 0);
        if (e != 0) { res.Info = "waveInOpen err=" + e; return res; }
        IntPtr[] bufs = new IntPtr[nbuf]; IntPtr[] hdrs = new IntPtr[nbuf];
        for (int i = 0; i < nbuf; i++) {
            bufs[i] = Marshal.AllocHGlobal(per);
            for (int k = 0; k < per; k++) Marshal.WriteByte(bufs[i], k, 0);
            WAVEHDR hd = new WAVEHDR(); hd.lpData = bufs[i]; hd.dwBufferLength = (uint)per;
            hdrs[i] = Marshal.AllocHGlobal((int)hsz); Marshal.StructureToPtr(hd, hdrs[i], false);
            waveInPrepareHeader(hin, hdrs[i], hsz); waveInAddBuffer(hin, hdrs[i], hsz);
        }
        waveInStart(hin);
        Thread.Sleep(120);
        IntPtr hout;
        e = waveOutOpen(out hout, outDev, ref f, IntPtr.Zero, IntPtr.Zero, 0);
        string oi = e == 0 ? "out=ok" : ("out=err" + e);
        double wall = 0;
        if (e == 0) {
            IntPtr p = Marshal.AllocHGlobal(play.Length);
            Marshal.Copy(play, 0, p, play.Length);
            IntPtr hp = Marshal.AllocHGlobal((int)hsz);
            WAVEHDR hd = new WAVEHDR(); hd.lpData = p; hd.dwBufferLength = (uint)play.Length;
            Marshal.StructureToPtr(hd, hp, false);
            waveOutPrepareHeader(hout, hp, hsz);
            Stopwatch sw = Stopwatch.StartNew();
            waveOutWrite(hout, hp, hsz);
            while (true) { WAVEHDR cur = (WAVEHDR)Marshal.PtrToStructure(hp, typeof(WAVEHDR));
                if ((cur.dwFlags & WHDR_DONE) != 0) break; Thread.Sleep(2); }
            sw.Stop(); wall = sw.Elapsed.TotalSeconds;
            waveOutUnprepareHeader(hout, hp, hsz);
            waveOutClose(hout);
            Marshal.FreeHGlobal(p); Marshal.FreeHGlobal(hp);
        }
        int done = 0; Stopwatch sw2 = Stopwatch.StartNew();
        while (true) {
            done = 0;
            for (int i = 0; i < nbuf; i++) { WAVEHDR cur = (WAVEHDR)Marshal.PtrToStructure(hdrs[i], typeof(WAVEHDR));
                if ((cur.dwFlags & WHDR_DONE) != 0) done++; }
            if (done == nbuf) break;
            if (sw2.Elapsed.TotalSeconds > recSeconds + 15) break;
            Thread.Sleep(5);
        }
        waveInStop(hin); waveInReset(hin);
        byte[] all = new byte[per * nbuf]; int off = 0;
        for (int i = 0; i < nbuf; i++) {
            Marshal.Copy(bufs[i], all, off, per); off += per;
            waveInUnprepareHeader(hin, hdrs[i], hsz);
            Marshal.FreeHGlobal(bufs[i]); Marshal.FreeHGlobal(hdrs[i]);
        }
        waveInClose(hin);
        res.Data = all;
        double audio = play.Length / (double)(sr * ch * bits / 8);
        res.Info = oi + " play=" + audio.ToString("F2") + "s wall=" + wall.ToString("F2") + "s ratio=" +
                   (wall > 0 ? (audio/wall).ToString("F2") : "-") + "x rec=" + done + "/" + nbuf;
        return res;
    }
}