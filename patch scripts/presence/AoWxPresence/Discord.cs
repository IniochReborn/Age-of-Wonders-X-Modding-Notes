// Discord Rich Presence over the local Discord client's IPC pipe (\\.\pipe\discord-ipc-N).
// Frame = int32 opcode + int32 length (little-endian) + UTF-8 JSON.  op 0 HANDSHAKE, 1 FRAME, 2 CLOSE.
using System;
using System.IO;
using System.IO.Pipes;
using System.Text;

namespace AoWxPresence
{
    internal sealed class Discord : IDisposable
    {
        readonly string clientId;
        NamedPipeClientStream pipe;

        internal Discord(string clientId) { this.clientId = clientId; }

        internal bool Connected { get { return pipe != null && pipe.IsConnected; } }

        internal bool Connect()
        {
            Close();
            for (int i = 0; i < 10; i++)
            {
                NamedPipeClientStream p = new NamedPipeClientStream(".", "discord-ipc-" + i, PipeDirection.InOut, PipeOptions.None);
                try
                {
                    p.Connect(200);
                    pipe = p;
                    Write(0, "{\"v\":1,\"client_id\":\"" + clientId + "\"}");
                    string ready = Read();            // DISPATCH READY, or an error frame (bad client id)
                    if (ready != null && ready.Contains("\"READY\"")) return true;
                    Program.Log("discord handshake refused: " + ready);
                }
                catch (Exception e) { if (pipe != null) Program.Log("discord pipe " + i + ": " + e.Message); }
                Close();
                p.Dispose();
            }
            return false;
        }

        // activity == null clears the presence
        internal bool SetActivity(int pid, string activityJson)
        {
            if (!Connected) return false;
            try
            {
                Write(1, "{\"cmd\":\"SET_ACTIVITY\",\"args\":{\"pid\":" + pid + ",\"activity\":" + (activityJson ?? "null") +
                         "},\"nonce\":\"" + Guid.NewGuid().ToString("N") + "\"}");
                string r = Read();
                if (r != null && r.Contains("\"ERROR\"")) Program.Log("SET_ACTIVITY error: " + r);
                return r != null;
            }
            catch (Exception e) { Program.Log("discord write: " + e.Message); Close(); return false; }
        }

        void Write(int op, string json)
        {
            byte[] body = Encoding.UTF8.GetBytes(json);
            byte[] f = new byte[8 + body.Length];
            BitConverter.GetBytes(op).CopyTo(f, 0);
            BitConverter.GetBytes(body.Length).CopyTo(f, 4);
            body.CopyTo(f, 8);
            pipe.Write(f, 0, f.Length);
            pipe.Flush();
        }

        string Read()
        {
            byte[] h = ReadN(8);
            if (h == null) return null;
            int len = BitConverter.ToInt32(h, 4);
            if (len < 0 || len > 1 << 20) return null;
            byte[] b = ReadN(len);
            return b == null ? null : Encoding.UTF8.GetString(b);
        }

        byte[] ReadN(int n)
        {
            byte[] b = new byte[n];
            int got = 0;
            while (got < n)
            {
                int r = pipe.Read(b, got, n - got);
                if (r <= 0) return null;
                got += r;
            }
            return b;
        }

        internal static string Str(string s)
        {
            StringBuilder sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                else if (c < 0x20) sb.AppendFormat("\\u{0:x4}", (int)c);
                else sb.Append(c);
            }
            return sb.Append('"').ToString();
        }

        void Close()
        {
            if (pipe != null) { try { pipe.Dispose(); } catch { } pipe = null; }
        }

        public void Dispose() { Close(); }
    }
}
