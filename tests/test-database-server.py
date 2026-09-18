#!/usr/bin/env python3
"""The shared-database server's Network.framework listener, compiled on its own (#615).

Builds Horos/Sources/HorosDatabaseServer.swift with a driver whose handler does what
the first byte of a request says, and talks to it over loopback:

  * a request sent one byte at a time is read whole; an answer of 48 MiB arrives
    whole, in order, and ends the stream;
  * against a client that stops reading for 2 s while 256 MiB are on their way, the
    writer is held back: the server's physical footprint grows by less than 32 MiB,
    and the whole answer arrives once the client reads again;
  * a client that sends nothing is dropped after the idle limit (1 s here), from a
    monotonic clock, and its handler ends with a timeout;
  * with 2 workers and 4 connections, no more than 2 handlers run at once, the 5th
    and 6th connections are closed without an answer, and once the others finish a
    new one is served;
  * stop() wakes a handler waiting for data and closes its connection; the server
    starts again on the same port and serves; a stopped server's listener never
    reports into the restarted one;
  * a port another socket holds fails the listener with EADDRINUSE, and the server
    stops;
  * while a main-queue block turns the run loop itself, as the app's modal alerts
    do, the server still accepts and answers, and its owner hears from it on the
    main thread.

Exit 2 (skipped) without swiftc.
"""
import json
import os
import queue
import select
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]

DRIVER = r'''
import Foundation
import Darwin

func emit(_ event: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: event)
    FileHandle.standardOutput.write(data + Data("\n".utf8))
}

func footprint() -> UInt64 {
    var info = task_vm_info_data_t()
    var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
    let result = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count) }
    }
    return result == KERN_SUCCESS ? info.phys_footprint : 0
}

final class Delegate: NSObject, HorosDatabaseServerDelegate {
    func databaseServerDidStart(_ server: HorosDatabaseServer) {
        emit(["event": "ready", "port": server.port, "main": Thread.isMainThread])
    }
    func databaseServer(_ server: HorosDatabaseServer, didFailWithPOSIXError posixError: Int32, description: String) {
        emit(["event": "failed", "errno": Int(posixError)])
    }
    func databaseServer(_ server: HorosDatabaseServer, isWaitingWithPOSIXError posixError: Int32, description: String) {
        emit(["event": "waiting", "errno": Int(posixError)])
    }
}

let lock = NSLock()
var running = 0, maximum = 0

func readExactly(_ peer: HorosDatabasePeer, _ count: Int, _ buffer: inout Data) throws {
    while buffer.count < count {
        let data = try peer.receiveData()
        if data.isEmpty { throw POSIXError(.ECONNRESET) }
        buffer.append(data)
    }
}

@main
struct Check {
    static func main() {
        let arguments = CommandLine.arguments
        let port = UInt16(arguments[1])!, connections = Int(arguments[2])!, workers = Int(arguments[3])!
        let chunk = Int(arguments[4])!, idle = Double(arguments[5])!
        let delegate = Delegate()
        let server = HorosDatabaseServer(port: port, maximumConnections: connections, maximumWorkers: workers,
                                         chunkSize: chunk, idleTimeout: idle) { peer in
            lock.lock(); running += 1; maximum = max(maximum, running); lock.unlock()
            defer { lock.lock(); running -= 1; lock.unlock() }
            var buffer = Data()
            var kind = "?"
            let started = ProcessInfo.processInfo.systemUptime
            do {
                try readExactly(peer, 5, &buffer)
                kind = String(UnicodeScalar(buffer[0]))
                let value = Int(UInt32(buffer[1]) << 24 | UInt32(buffer[2]) << 16 | UInt32(buffer[3]) << 8 | UInt32(buffer[4]))
                buffer.removeFirst(5)
                switch kind {
                case "W":   // answer `value` bytes of i % 251
                    var remaining = value, offset = 0
                    while remaining > 0 {
                        let size = min(remaining, 4 << 20)
                        var block = Data(count: size)
                        block.withUnsafeMutableBytes { raw in
                            let bytes = raw.bindMemory(to: UInt8.self)
                            for i in 0..<size { bytes[i] = UInt8((offset + i) % 251) }
                        }
                        try peer.writeData(block)
                        remaining -= size; offset += size
                    }
                case "R":   // read `value` more bytes, answer their sum
                    try readExactly(peer, value, &buffer)
                    var sum: UInt64 = 0
                    for byte in buffer.prefix(value) { sum += UInt64(byte) }
                    var big = sum.bigEndian
                    try peer.writeData(Data(bytes: &big, count: 8))
                case "H":   // hold the worker for `value` ms, answer "ok"
                    Thread.sleep(forTimeInterval: Double(value) / 1000)
                    try peer.writeData(Data("ok".utf8))
                case "I":   // wait for bytes that never come
                    _ = try peer.receiveData()
                default:
                    break
                }
                try peer.finish()
                emit(["event": "handler", "kind": kind, "error": NSNull(), "ms": (ProcessInfo.processInfo.systemUptime - started) * 1000])
            } catch {
                let code = (error as? POSIXError)?.code.rawValue ?? -1
                emit(["event": "handler", "kind": kind, "error": String(describing: error), "errno": Int(code),
                      "ms": (ProcessInfo.processInfo.systemUptime - started) * 1000])
            }
        }
        server.delegate = delegate
        DispatchQueue.main.async { server.start() }
        Thread.detachNewThread {
            while let line = readLine() {
                if line == "hold" {
                    // What a modal alert started from a main-queue block does in the app: the run loop
                    // turns, and no other main-queue block runs until it returns.
                    DispatchQueue.main.async {
                        emit(["event": "holding"])
                        let end = Date(timeIntervalSinceNow: 3)
                        while Date() < end { _ = RunLoop.current.run(mode: .default, before: end) }
                        emit(["event": "released"])
                    }
                    continue
                }
                DispatchQueue.main.sync {
                    switch line {
                    case "count": emit(["event": "count", "connections": server.connectionCount])
                    case "maximum": lock.lock(); emit(["event": "maximum", "handlers": maximum]); lock.unlock()
                    case "footprint": emit(["event": "footprint", "bytes": footprint()])
                    case "stop": server.stop(); emit(["event": "stopped"])
                    case "start": server.start()
                    case "quit": exit(0)
                    default: break
                    }
                }
            }
            exit(0)
        }
        withExtendedLifetime(delegate) { RunLoop.main.run() }
    }
}
'''


class Driver:
    def __init__(self, binary, port, connections=32, workers=8, chunk=128 * 1024, idle=45.0):
        self.process = subprocess.Popen([str(binary), str(port), str(connections), str(workers), str(chunk), str(idle)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.events = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.process.stdout:
            try:
                self.events.put(json.loads(line))
            except ValueError:
                pass

    def next(self, kind, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if event["event"] == kind:
                return event
        return None

    def ask(self, command, kind):
        self.process.stdin.write((command + "\n").encode())
        self.process.stdin.flush()
        return self.next(kind)

    def stop(self):
        try:
            self.process.stdin.write(b"quit\n")
            self.process.stdin.flush()
        except OSError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def connect(port):
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s


def read_all(s, limit=None):
    chunks, total = [], 0
    while True:
        data = s.recv(1 << 20)
        if not data:
            return b"".join(chunks)
        chunks.append(data)
        total += len(data)
        if limit is not None and total > limit:
            return b"".join(chunks)


def closed_without_answer(s, timeout=3.0):
    s.settimeout(timeout)
    try:
        return s.recv(16) == b""
    except (ConnectionResetError, BrokenPipeError):
        return True
    except socket.timeout:
        return False


def main():
    if subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True).returncode != 0:
        print("skipped: needs swiftc")
        return 2
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    with tempfile.TemporaryDirectory(prefix="horos-database-server-") as directory:
        work = Path(directory)
        (work / "Check.swift").write_text(DRIVER)
        binary = work / "check"
        subprocess.run(["xcrun", "swiftc", "-O", "-parse-as-library", "-suppress-warnings",
                        str(root / "Horos/Sources/HorosDatabaseServer.swift"), str(work / "Check.swift"), "-o", str(binary)],
                       check=True)

        # Fragmented request, large answer.
        port = free_port()
        server = Driver(binary, port)
        try:
            ready = server.next("ready")
            check(ready is not None and ready["main"] is True, f"the listener became ready as {ready}")
            s = connect(port)
            payload = os.urandom(3000)
            for byte in b"R" + struct.pack(">I", len(payload)) + payload:
                s.sendall(bytes([byte]))
            answer = read_all(s)
            s.close()
            check(answer == struct.pack(">Q", sum(payload)), f"a request sent byte by byte was answered {answer!r}")
            size = 48 << 20
            s = connect(port)
            s.sendall(b"W" + struct.pack(">I", size))
            answer = read_all(s)
            s.close()
            expected = bytes(i % 251 for i in range(251)) * (size // 251 + 1)
            check(len(answer) == size and answer == expected[:size], f"a 48 MiB answer arrived as {len(answer)} bytes")

            # A reader that stops holds the writer back.
            before = server.ask("footprint", "footprint")["bytes"]
            size = 256 << 20
            s = connect(port)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 64 * 1024)
            s.sendall(b"W" + struct.pack(">I", size))
            received = len(s.recv(1 << 20))
            peak = before
            for _ in range(4):
                time.sleep(0.5)
                peak = max(peak, server.ask("footprint", "footprint")["bytes"])
            while received < size:
                data = s.recv(1 << 20)
                if not data:
                    break
                received += len(data)
            s.close()
            growth = (peak - before) / (1 << 20)
            check(received == size, f"the stopped reader got {received} of {size} bytes once it read again")
            check(growth < 32, f"the server grew by {growth:.1f} MiB while its reader stopped for 2 s")
        finally:
            server.stop()

        # Idle limit.
        port = free_port()
        server = Driver(binary, port, idle=1.0)
        try:
            server.next("ready")
            s = connect(port)
            started = time.monotonic()
            closed = closed_without_answer(s, timeout=5)
            elapsed = time.monotonic() - started
            s.close()
            event = server.next("handler")
            check(closed and 0.8 < elapsed < 3.5, f"an idle client was closed={closed} after {elapsed:.2f} s")
            check(event is not None and event.get("errno") == 60, f"the idle handler ended with {event}")
        finally:
            server.stop()

        # Saturation: 2 workers, 4 connections.
        port = free_port()
        server = Driver(binary, port, connections=4, workers=2)
        try:
            server.next("ready")
            held = []
            for _ in range(4):
                s = connect(port)
                s.sendall(b"H" + struct.pack(">I", 1500))
                held.append(s)
            time.sleep(0.3)
            extra = [connect(port) for _ in range(2)]
            check(all(closed_without_answer(s, timeout=3) for s in extra), "connections above the limit were not closed")
            for s in extra:
                s.close()
            answers = [read_all(s) for s in held]
            for s in held:
                s.close()
            check(answers == [b"ok"] * 4, f"the held connections were answered {answers}")
            maximum = server.ask("maximum", "maximum")["handlers"]
            check(maximum <= 2, f"{maximum} handlers ran at once with 2 workers")
            time.sleep(0.3)
            s = connect(port)
            s.sendall(b"H" + struct.pack(">I", 1))
            check(read_all(s) == b"ok", "the server did not serve a new connection once the others finished")
            s.close()
            # A finished connection leaves the table on the server's queue, just after its handler.
            count = None
            for _ in range(20):
                count = server.ask("count", "count")["connections"]
                if count == 0:
                    break
                time.sleep(0.1)
            check(count == 0, f"{count} connections left after every client finished")
        finally:
            server.stop()

        # Stop wakes a waiting handler; the server starts again on the same port.
        port = free_port()
        server = Driver(binary, port)
        try:
            server.next("ready")
            s = connect(port)
            s.sendall(b"I" + struct.pack(">I", 0))
            time.sleep(0.3)
            started = time.monotonic()
            server.ask("stop", "stopped")
            event = server.next("handler", timeout=5)
            elapsed = time.monotonic() - started
            check(event is not None and event.get("errno") == 89 and elapsed < 2,
                  f"stop left a waiting handler: {event} after {elapsed:.2f} s")
            check(closed_without_answer(s, timeout=3), "stop did not close the waiting connection")
            s.close()
            check(server.ask("count", "count")["connections"] == 0, "stop left connections in the table")
            server.process.stdin.write(b"start\n")
            server.process.stdin.flush()
            ready = server.next("ready")
            check(ready is not None and ready["port"] == port, f"the server did not start again on {port}: {ready}")
            s = connect(port)
            s.sendall(b"H" + struct.pack(">I", 1))
            check(read_all(s) == b"ok", "the restarted server did not serve")
            s.close()
            check(server.next("failed", timeout=1) is None, "the stopped listener reported into the restarted server")
        finally:
            server.stop()

        # A port another socket holds.
        holder = socket.socket()
        holder.bind(("0.0.0.0", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        server = Driver(binary, port)
        try:
            event = server.next("failed")
            check(event is not None and event.get("errno") == 48, f"a taken port gave {event}")
            check(server.ask("count", "count") is not None, "the driver stopped answering after the failure")
        finally:
            server.stop()
            holder.close()

        # A main queue held by a block that turns the run loop: the report-import alert did this to the
        # listener when it lived on the main queue, and the app stopped accepting until it was dismissed.
        port = free_port()
        server = Driver(binary, port)
        try:
            server.next("ready")
            server.process.stdin.write(b"hold\n")
            server.process.stdin.flush()
            check(server.next("holding") is not None, "the main queue was not held")
            s = connect(port)
            s.sendall(b"H" + struct.pack(">I", 1))
            s.settimeout(2)
            try:
                answer = read_all(s)
            except socket.timeout:
                answer = None
            s.close()
            check(answer == b"ok" and server.next("released", timeout=0.01) is None,
                  f"with the main queue held the server answered {answer!r}")
            check(server.next("released", timeout=5) is not None, "the main queue was never released")
        finally:
            server.stop()

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        return 1
    print("PASS: fragmented request and 48 MiB answer, stopped reader bounded, idle limit, 2 workers of 4 connections "
          "with the rest refused, stop and restart, taken port, main queue held")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
