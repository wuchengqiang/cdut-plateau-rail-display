using System;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

// Diagnostic transport only. Never connects to a LAN debug endpoint.
public sealed class RailDiagnosticCdp : IDisposable
{
    private readonly ClientWebSocket socket = new ClientWebSocket();
    private readonly Queue<string> events = new Queue<string>();
    private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 16777216 };
    public int DroppedEvents { get; private set; }

    public RailDiagnosticCdp(string address)
    {
        Uri uri = new Uri(address);
        if (uri.Scheme != "ws" || (uri.Host != "127.0.0.1" && uri.Host != "localhost" && uri.Host != "[::1]"))
            throw new ArgumentException("Only loopback browser debugging is permitted.");
        socket.Options.Proxy = null;
        using (var cancel = new CancellationTokenSource(5000))
            socket.ConnectAsync(uri, cancel.Token).GetAwaiter().GetResult();
    }

    public string Call(string message, int id)
    {
        using (var cancel = new CancellationTokenSource(8000))
        {
            byte[] outgoing = Encoding.UTF8.GetBytes(message);
            socket.SendAsync(new ArraySegment<byte>(outgoing), WebSocketMessageType.Text, true, cancel.Token).GetAwaiter().GetResult();
            while (true)
            {
                string incoming;
                using (var stream = new MemoryStream())
                {
                    var buffer = new byte[32768];
                    WebSocketReceiveResult received;
                    do
                    {
                        received = socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancel.Token).GetAwaiter().GetResult();
                        if (received.MessageType == WebSocketMessageType.Close)
                            throw new IOException("The diagnostic browser was closed.");
                        stream.Write(buffer, 0, received.Count);
                        if (stream.Length > 16777216) throw new IOException("Oversized CDP response.");
                    } while (!received.EndOfMessage);
                    incoming = Encoding.UTF8.GetString(stream.ToArray());
                }
                var parsed = json.Deserialize<Dictionary<string, object>>(incoming);
                if (parsed.ContainsKey("id") && Convert.ToInt32(parsed["id"]) == id) return incoming;
                if (events.Count >= 2000) { events.Dequeue(); DroppedEvents++; }
                events.Enqueue(incoming);
            }
        }
    }

    public string[] DrainEvents()
    {
        string[] result = events.ToArray();
        events.Clear();
        return result;
    }

    public void Dispose() { socket.Abort(); socket.Dispose(); }
}
