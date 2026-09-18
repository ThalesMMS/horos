#!/usr/bin/env python3
"""A retrieve waits for the threads it started until they have finished (#634).

-[DCMTKQueryNode move:retrieveMode:] hands its IMAGE-level associations to
threads and waited for them by asking whether any was still executing. A thread
just started has not begun executing, so the first look found none, the wait
ended after one pause and the move carried on - judging the IMAGE level, closing
the inventory, releasing its association slot - while images still arrived.

The source must no longer wait on isExecuting in DCMTKQueryNode.mm (the C-FIND
workers of the IMAGE and WADO retrieves included), and must use
HorosRetrieveThreadGroup for its thread groups. The compiled helper is then
exercised, next to the loop it replaces:

- threads that take 300 ms and report not executing for their first 100 ms, as a
  thread just started does: the old loop returns before they finish; the helper
  returns after every one has, and not much later (how often the old loop returns
  early on a plain thread is printed, not asserted);
- a cancellation of the waiting thread reaches threads still running, which stop;
- a thread that cancels itself (a failed association) is reported;
- the Objective-C names DCMTKQueryNode.mm calls exist in the generated header.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []

source = (root / "Horos/Sources/DCMTKQueryNode.mm").read_bytes().decode("utf-8", errors="replace")
code = "\n".join(line.split("//")[0] for line in source.split("\n"))
if re.search(r"\.isExecuting\b|isExecuting\]", code):
    failures.append("DCMTKQueryNode.mm still waits on isExecuting")
calls = code.count("[HorosRetrieveThreadGroup waitForThreads:")
if calls != 2:
    failures.append(f"{calls} thread groups wait through HorosRetrieveThreadGroup, not 2")
if "WADOCFind.isFinished" not in code:
    failures.append("the C-FIND workers are not waited on until they finish")
helper = root / "Horos/Sources/RetrieveThreadGroup.swift"
if not helper.exists():
    failures.append("Horos/Sources/RetrieveThreadGroup.swift is missing")
project = (root / "Horos.xcodeproj/project.pbxproj").read_text(errors="replace")
if "RetrieveThreadGroup.swift in Sources" not in project:
    failures.append("RetrieveThreadGroup.swift is not compiled by the project")
for failure in failures:
    print("FAIL:", failure)
if failures or not helper.exists():
    raise SystemExit(1)

if subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True).returncode != 0:
    print("skipped: needs swiftc")
    raise SystemExit(2)

DRIVER = r'''
import Foundation

func now() -> TimeInterval { ProcessInfo.processInfo.systemUptime }
func report(_ name: String, _ ok: Bool, _ detail: String) { print("\(ok ? "PASS" : "FAIL") \(name): \(detail)") }

// The loop DCMTKQueryNode.mm had, as it was.
func oldWait(_ threads: [Thread]) {
    var executing = false
    repeat {
        executing = false
        for t in threads where t.isExecuting { executing = true }
        Thread.sleep(forTimeInterval: 0.05)
    } while executing
}

// A thread the scheduler starts late: it reports not executing for its first
// 100 ms, as a thread just started does until it is running. isFinished is left
// as Foundation keeps it.
final class LateStartingThread: Thread {
    private let created = ProcessInfo.processInfo.systemUptime
    override var isExecuting: Bool {
        ProcessInfo.processInfo.systemUptime - created < 0.1 ? false : super.isExecuting
    }
}

func slowThreads(_ count: Int) -> [Thread] {
    (0..<count).map { _ in
        let t = LateStartingThread { Thread.sleep(forTimeInterval: 0.3) }
        t.start()
        return t
    }
}

do {
    let threads = slowThreads(1)
    let start = now()
    oldWait(threads)
    let unfinished = threads.filter { !$0.isFinished }.count
    report("old loop (reference)", unfinished > 0, "returned after \(Int((now() - start) * 1000)) ms with \(unfinished) of 1 thread unfinished")
    RetrieveThreadGroup.wait(for: threads, propagatingCancellationOf: nil)
}
do {
    // Without the model: one thread, looked at right after it is started, as the
    // retrieve does. Reported, not asserted - it depends on the scheduler.
    var early = 0
    for _ in 0..<50 {
        let t = Thread { Thread.sleep(forTimeInterval: 0.08) }
        t.start()
        oldWait([t])
        if !t.isFinished { early += 1 }
        while !t.isFinished { Thread.sleep(forTimeInterval: 0.01) }
    }
    print("INFO old loop on a plain thread: returned before it finished \(early) times in 50")
}
do {
    let threads = slowThreads(8)
    let start = now()
    RetrieveThreadGroup.wait(for: threads, propagatingCancellationOf: nil)
    let elapsed = now() - start
    let unfinished = threads.filter { !$0.isFinished }.count
    report("helper waits", unfinished == 0 && elapsed >= 0.29 && elapsed < 1.0,
           "returned after \(Int(elapsed * 1000)) ms with \(unfinished) unfinished")
}
do {
    let stopped = NSLock()
    var stoppedCount = 0
    let children: [Thread] = (0..<4).map { _ in
        let t = Thread {
            while !Thread.current.isCancelled { Thread.sleep(forTimeInterval: 0.01) }
            stopped.lock(); stoppedCount += 1; stopped.unlock()
        }
        t.start()
        return t
    }
    let owner = Thread {
        RetrieveThreadGroup.wait(for: children, propagatingCancellationOf: Thread.current)
    }
    owner.start()
    Thread.sleep(forTimeInterval: 0.2)
    let start = now()
    owner.cancel()
    while !owner.isFinished { Thread.sleep(forTimeInterval: 0.01) }
    let elapsed = now() - start
    report("cancellation reaches the threads", stoppedCount == 4 && elapsed < 0.5,
           "\(stoppedCount) of 4 stopped, the wait ended \(Int(elapsed * 1000)) ms after the cancel")
}
do {
    let failing = Thread { Thread.current.cancel() }
    let fine = Thread { Thread.sleep(forTimeInterval: 0.05) }
    failing.start(); fine.start()
    RetrieveThreadGroup.wait(for: [failing, fine], propagatingCancellationOf: nil)
    report("a failed association is seen", RetrieveThreadGroup.anyCancelled([failing, fine]), "anyCancelled")
    let clean = Thread { }
    clean.start()
    RetrieveThreadGroup.wait(for: [clean], propagatingCancellationOf: nil)
    report("a clean group is not failed", !RetrieveThreadGroup.anyCancelled([clean]), "anyCancelled")
}
'''

with tempfile.TemporaryDirectory(prefix="horos-retrieve-wait-") as temporary:
    work = Path(temporary)
    (work / "main.swift").write_text(DRIVER)
    header = work / "RetrieveThreadGroup-Swift.h"
    built = subprocess.run(["xcrun", "swiftc", "-O", "-swift-version", "5", str(helper), str(work / "main.swift"),
                            "-module-name", "Horos",
                            "-emit-objc-header-path", str(header), "-o", str(work / "driver")],
                           capture_output=True, text=True)
    if built.returncode != 0:
        print(built.stderr[-3000:])
        raise SystemExit(1)
    ran = subprocess.run([str(work / "driver")], capture_output=True, text=True, timeout=60)
    print(ran.stdout.strip())
    failures += [line for line in ran.stdout.splitlines() if line.startswith("FAIL")]
    if ran.returncode != 0:
        failures.append(f"the driver exited {ran.returncode}: {ran.stderr[-500:]}")
    names = header.read_text()
    for selector in ("waitForThreads:(NSArray<NSThread *> * _Nonnull)threads propagatingCancellationOf:(NSThread * _Nullable)owner;",
                     "anyCancelled:(NSArray<NSThread *> * _Nonnull)threads"):
        if selector not in names:
            failures.append(f"the generated header lacks {selector.split('(')[0]}")
    if "SWIFT_CLASS_NAMED(\"RetrieveThreadGroup\")" not in names or "@interface HorosRetrieveThreadGroup" not in names:
        failures.append("the class is not HorosRetrieveThreadGroup to Objective-C")

for failure in failures:
    if not failure.startswith("FAIL"):
        print("FAIL:", failure)
raise SystemExit(1 if failures else 0)
