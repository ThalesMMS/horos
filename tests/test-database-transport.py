#!/usr/bin/env python3
"""The shared-database client on NWConnection (#607), against a controlled server.

Compiles `Horos/Sources/DatabaseTransport.swift` with a driver that talks to a
Python server speaking the shape of the legacy protocol: a six-byte command, a
payload, and a response ended by closing the connection. What it checks:

* a whole request reaches the server byte for byte, and the whole response
  comes back;
* a streaming consumer is handed the buffer on the calling thread and its
  unconsumed bytes survive into the next receive;
* a response that ends inside a header is an error, not a short success;
* a consumer that refuses reports its own error, and one that claims more bytes
  than it was given is refused;
* a server that accepts and then says nothing hits the idle timeout instead of
  waiting forever;
* cancellation stops a transfer in progress;
* a large payload moves in bounded chunks;
* commands are classified: reads may be sent again, mutations may not, and a
  mutation that failed says what the operator has to do.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/DatabaseTransport.swift'
failures = []
if 'DatabaseTransport.swift in Sources' not in (root / 'Horos.xcodeproj/project.pbxproj').read_text():
    failures.append('DatabaseTransport.swift is not in the Horos target')

SERVER = r'''
import socket, sys, threading, time

mode = sys.argv[1]
listener = socket.socket(); listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(("127.0.0.1", 0)); listener.listen(4)
print(listener.getsockname()[1], flush=True)

def serve():
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        threading.Thread(target=handle, args=(client,), daemon=True).start()

def handle(client):
    client.settimeout(20)
    request = b""
    try:
        while len(request) < 6:
            chunk = client.recv(65536)
            if not chunk: break
            request += chunk
        # Drain whatever else the request carries, briefly.
        client.settimeout(0.3)
        try:
            while True:
                chunk = client.recv(65536)
                if not chunk: break
                request += chunk
        except OSError:
            pass
        command = request[:5].decode("ascii", "replace")
        if mode == "echo":
            client.sendall(b"%08d" % len(request) + request)
        elif mode == "records":
            for index in range(3):
                body = bytes([65 + index]) * (10 * (index + 1))
                client.sendall(len(body).to_bytes(4, "big") + body)
        elif mode == "truncated-header":
            client.sendall((99).to_bytes(4, "big")[:2])   # half a header, then close
        elif mode == "silent":
            time.sleep(120)
        elif mode == "slow":
            for _ in range(200):
                client.sendall(b"x" * 4096)
                time.sleep(0.05)
        elif mode == "large":
            client.sendall(len(request).to_bytes(4, "big") + request)
    except OSError:
        pass
    finally:
        try: client.shutdown(socket.SHUT_WR)
        except OSError: pass
        client.close()

threading.Thread(target=serve, daemon=True).start()
try:
    while True: time.sleep(0.5)
except KeyboardInterrupt:
    pass
'''

DRIVER = r'''
import Foundation

var failed = false
func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); failed = true } }
let port = Int(CommandLine.arguments[1])!
let mode = CommandLine.arguments[2]

func request(_ command: String, payload: Data = Data()) -> Data {
    var data = Data(command.utf8); data.append(0); data.append(payload); return data
}

switch mode {
case "echo":
    let sent = request("DBVER", payload: Data(repeating: 7, count: 100))
    let response = try! DatabaseTransport.sendRequest(sent, toHost: "127.0.0.1", port: port, receiving: nil, cancelled: { false })
    expect(response.count == 8 + sent.count, "the whole response came back: \(response.count)")
    expect(response.dropFirst(8) == sent, "the server received the request byte for byte")

case "records":
    // A length-prefixed consumer: it takes whole records only, so a partial
    // header must survive into the next receive.
    var records: [String] = []
    let response = try! DatabaseTransport.sendRequest(request("DATAB"), toHost: "127.0.0.1", port: port, receiving: { data, _ in
        guard let data else { return 0 }
        var consumed = 0
        while data.count - consumed >= 4 {
            let header = data.subdata(in: (data.startIndex + consumed)..<(data.startIndex + consumed + 4))
            let length = header.reduce(0) { ($0 << 8) | Int($1) }
            guard data.count - consumed - 4 >= length else { break }
            let body = data.subdata(in: (data.startIndex + consumed + 4)..<(data.startIndex + consumed + 4 + length))
            records.append("\(body.first.map { String(UnicodeScalar($0)) } ?? "?")\(body.count)")
            consumed += 4 + length
        }
        return consumed
    }, cancelled: { false })
    expect(records == ["A10", "B20", "C30"], "every record was consumed in order: \(records)")
    expect(response.isEmpty, "a fully consumed response leaves nothing buffered")

case "truncated-header":
    do {
        _ = try DatabaseTransport.sendRequest(request("DATAB"), toHost: "127.0.0.1", port: port, receiving: { _, _ in 0 }, cancelled: { false })
        expect(false, "a response that ends inside a header must fail")
    } catch {
        expect("\(error)".contains("ended inside a header"), "the error says the response ended inside a header: \(error)")
    }

case "refusing-consumer":
    do {
        _ = try DatabaseTransport.sendRequest(request("DATAB"), toHost: "127.0.0.1", port: port, receiving: { data, error in
            guard data != nil else { return 0 }
            error.pointee = NSError(domain: "Probe", code: 42, userInfo: [NSLocalizedDescriptionKey: "the consumer refused"])
            return -1
        }, cancelled: { false })
        expect(false, "a refusing consumer must fail the request")
    } catch {
        expect((error as NSError).code == 42, "the consumer's own error is reported: \(error)")
    }
    do {
        _ = try DatabaseTransport.sendRequest(request("DATAB"), toHost: "127.0.0.1", port: port, receiving: { data, _ in
            (data?.count ?? 0) + 1   // claims more than it was given
        }, cancelled: { false })
        expect(false, "a consumer claiming too many bytes must fail")
    } catch {
        expect("\(error)".contains("Invalid shared-database response consumption"), "an impossible consumption is refused: \(error)")
    }

case "silent":
    let started = Date()
    do {
        _ = try DatabaseTransport.sendRequest(request("DBVER"), toHost: "127.0.0.1", port: port, receiving: nil, cancelled: { false })
        expect(false, "a silent server must not succeed")
    } catch {
        let waited = Date().timeIntervalSince(started)
        expect((error as? URLError)?.code == .timedOut, "a silent server times out: \(error)")
        expect(waited >= DatabaseTransport.idleTimeout - 1 && waited < DatabaseTransport.idleTimeout + 15,
               "it waited about the contract's idle timeout: \(waited)s")
    }

case "cancel":
    var cancelled = false
    DispatchQueue.global().asyncAfter(deadline: .now() + 0.5) { cancelled = true }
    do {
        _ = try DatabaseTransport.sendRequest(request("DATAB"), toHost: "127.0.0.1", port: port,
                                              receiving: { data, _ in data?.count ?? 0 }, cancelled: { cancelled })
        expect(false, "a cancelled transfer must not succeed")
    } catch {
        expect((error as? URLError)?.code == .cancelled, "cancellation is reported as such: \(error)")
    }

case "large":
    let payload = Data(repeating: 0x5a, count: 900 * 1024)  // several chunks
    let sent = request("DICOM", payload: payload)
    let response = try! DatabaseTransport.sendRequest(sent, toHost: "127.0.0.1", port: port, receiving: nil, cancelled: { false })
    expect(response.count == 4 + sent.count, "a multi-chunk request arrived whole: \(response.count) of \(4 + sent.count)")
    expect(response.dropFirst(4) == sent, "every chunk arrived in order")

case "refused":
    // Nothing is listening on this port: the client must say so at once, not
    // spend the whole idle timeout waiting for a host that refused.
    let started = Date()
    do {
        _ = try DatabaseTransport.sendRequest(request("DBVER"), toHost: "127.0.0.1", port: port, receiving: nil, cancelled: { false })
        expect(false, "a refused connection must not succeed")
    } catch {
        let waited = Date().timeIntervalSince(started)
        expect(waited < 5, "a refused connection fails promptly: \(waited)s")
        expect(!"\(error)".isEmpty, "the refusal carries an error: \(error)")
    }

case "classification":
    expect(SharedDatabaseCommand.command(in: request("DBVER")) == "DBVER", "the command is read from the request")
    expect(SharedDatabaseCommand.command(in: Data([65, 66])) == nil, "a short request has no command")
    expect(SharedDatabaseCommand.command(in: Data("DBVERX".utf8)) == nil, "a command without its terminator is not a command")
    for read in ["DBVER", "ISPWD", "AUTHV", "PASWD", "DBSIZ", "DATAB", "VERSI", "GETDI", "MFILE", "DICOM"] {
        expect(SharedDatabaseCommand.isRetryable(request(read)), "\(read) is a read and may be sent again")
        expect(SharedDatabaseCommand.actionRequired(for: request(read)) == nil, "\(read) needs no operator action")
    }
    for mutation in ["SETVA", "NEWMS", "DCMSE"] {
        expect(!SharedDatabaseCommand.isRetryable(request(mutation)), "\(mutation) changes the other side and must not be replayed")
        expect(SharedDatabaseCommand.actionRequired(for: request(mutation))?.isEmpty == false, "\(mutation) tells the operator what to do")
    }
    expect(!SharedDatabaseCommand.isRetryable(request("XXXXX")), "an unknown command is not replayed")
    expect(SharedDatabaseCommand.mutatingCommands.isDisjoint(with: SharedDatabaseCommand.idempotentCommands),
           "a command is either a read or a mutation, never both")

default:
    expect(false, "unknown mode \(mode)")
}
print(failed ? "FAILED \(mode)" : "ok \(mode)")
exit(failed ? 1 : 0)
'''

if not failures:
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / 'main.swift'
        driver.write_text(DRIVER)
        server = Path(tmp) / 'server.py'
        server.write_text(SERVER)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'swiftc', '-O', str(source), str(driver), '-o', str(binary)], capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-3000:])
        else:
            import sys
            cases = [('echo', 'echo'), ('records', 'records'), ('truncated-header', 'truncated-header'),
                     ('records', 'refusing-consumer'), ('silent', 'silent'), ('slow', 'cancel'),
                     ('large', 'large'), ('echo', 'refused'), ('echo', 'classification')]
            for server_mode, case in cases:
                process = subprocess.Popen([sys.executable, str(server), server_mode], stdout=subprocess.PIPE, text=True)
                try:
                    port = process.stdout.readline().strip()
                    if case == 'refused':
                        # A port nothing listens on: the server above is stopped first.
                        process.terminate(); process.wait(timeout=10)
                    run = subprocess.run([str(binary), port, case], capture_output=True, text=True, timeout=120)
                    if run.returncode != 0:
                        failures.append('%s: %s' % (case, (run.stdout + run.stderr).strip()))
                    else:
                        print(run.stdout.strip())
                finally:
                    process.terminate()
                    process.wait(timeout=10)

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
