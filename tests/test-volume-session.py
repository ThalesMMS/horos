#!/usr/bin/env python3
"""One identity per volume, one owner per session (#373).

#373 owns the shared volume/session layer that #374 and #375 must reuse rather
than reimplement. The invariants are small and each exists because breaking it
produces a specific wrong behaviour:

* identity is derived from the stored DICOM identifiers, so two viewers cannot
  invent different names for the same volume, and a blank identifier is refused
  instead of colliding;
* a different frame of reference or time point is a different volume, which is
  what stops a crosshair pretending two series are registered;
* one owner at a time, so invalidation and cancellation still mean something;
* a cancelled load never delivers, and cancelling after delivery does not
  rewrite history;
* closing cancels outstanding work; a closed session issues no more.

The shipped source is compiled and run, not paraphrased.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/VolumeSession.swift'
assert source.is_file(), 'FAIL: VolumeSession.swift is missing'

driver = r'''
import Foundation

@main struct Check {
    static func identity(_ study: String = "1.2.3", _ series: String = "4.5.6",
                         frame: String = "", time: Int = 0, generation: Int = 0) -> VolumeIdentity {
        VolumeIdentity(studyInstanceUID: study, seriesInstanceUID: series,
                       frameOfReferenceUID: frame, timeIndex: time, generation: generation)!
    }

    static func main() {
        // Identity comes from the stored identifiers; nothing is invented.
        precondition(VolumeIdentity(studyInstanceUID: "", seriesInstanceUID: "4.5.6") == nil)
        precondition(VolumeIdentity(studyInstanceUID: "1.2.3", seriesInstanceUID: "   ") == nil)
        precondition(VolumeIdentity(studyInstanceUID: " 1.2.3 ", seriesInstanceUID: "4.5.6")!
                        .studyInstanceUID == "1.2.3")
        precondition(VolumeIdentity(studyInstanceUID: "1.2.3", seriesInstanceUID: "4.5.6",
                                    frameOfReferenceUID: "", timeIndex: -1, generation: 0) == nil)

        // A different frame of reference or time point is a different volume.
        precondition(identity() == identity())
        precondition(identity(frame: "9.9") != identity())
        precondition(identity(time: 1) != identity())
        precondition(!identity(frame: "9.9").refersToSameVolume(as: identity()))
        precondition(!identity(time: 1).refersToSameVolume(as: identity()))
        precondition(Set([identity(), identity()]).count == 1)
        precondition(Set([identity(), identity(time: 1)]).count == 2)

        // A generation change is a different identity but the same volume: a
        // cache must miss, a "is the viewer still here" check must not.
        let first = identity()
        let second = first.nextGeneration()
        precondition(first != second)
        precondition(first.refersToSameVolume(as: second))
        precondition(second.generation == first.generation + 1)

        let registry = VolumeSessionRegistry()

        // One owner at a time; the same owner reopening gets the same session.
        let planar = registry.open(identity: first, owner: "planar")!
        precondition(registry.open(identity: first, owner: "planar") === planar)
        precondition(registry.open(identity: first, owner: "mpr") == nil)
        precondition(registry.ownerOfVolume(first) == "planar")
        // A different volume is free.
        let other = registry.open(identity: identity(time: 1), owner: "mpr")!
        precondition(other.sessionID != planar.sessionID)
        precondition(registry.openSessionCount == 2)

        // A cancelled load never delivers.
        let token = registry.makeLoadToken(for: planar)!
        precondition(!token.isCancelled && !token.hasDelivered)
        precondition(token.cancel())
        precondition(token.isCancelled)
        precondition(!token.deliver())

        // Delivery happens once, and cancelling afterwards does not rewrite it.
        let delivered = registry.makeLoadToken(for: planar)!
        precondition(delivered.deliver())
        precondition(!delivered.deliver())
        precondition(!delivered.cancel())
        precondition(!delivered.isCancelled)
        precondition(delivered.hasDelivered)

        // The series changed underneath: open sessions go stale, their work is
        // cancelled, and they carry the new generation.
        let inFlight = registry.makeLoadToken(for: planar)!
        let advanced = registry.invalidateVolume(first)
        precondition(advanced.generation == first.generation + 1)
        precondition(planar.isStale)
        precondition(inFlight.isCancelled)
        precondition(!inFlight.deliver())
        precondition(planar.identity == advanced)
        precondition(planar.isOpen)
        // The untouched volume is not disturbed.
        precondition(!other.isStale)

        // Closing cancels what is outstanding and issues nothing more.
        let pending = registry.makeLoadToken(for: planar)!
        registry.close(planar)
        precondition(pending.isCancelled)
        precondition(!planar.isOpen)
        precondition(registry.makeLoadToken(for: planar) == nil)
        precondition(registry.session(withID: planar.sessionID) == nil)
        precondition(registry.ownerOfVolume(advanced) == nil)
        // ...and the volume is free for the next owner.
        let reopened = registry.open(identity: advanced, owner: "mpr")!
        precondition(reopened.owner == "mpr")
        precondition(reopened.sessionID != planar.sessionID)

        registry.closeAll()
        precondition(registry.openSessionCount == 0)

        print("PASS: #373 one identity per volume, one owner per session, cancellation and invalidation")
    }
}
'''

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
for needle in ('VolumeSession.swift in Sources', 'path = VolumeSession.swift'):
    if needle not in project:
        print('FAIL: the shared session layer is not in the Horos target (%s)' % needle,
              file=sys.stderr)
        raise SystemExit(1)

with tempfile.TemporaryDirectory(prefix='horos-volume-session-') as folder:
    directory = Path(folder)
    # Not main.swift: that name makes the file top-level code, which @main rejects.
    (directory / 'Check.swift').write_text(driver)
    built = subprocess.run(['xcrun', 'swiftc', '-O', str(source), str(directory / 'Check.swift'),
                            '-o', str(directory / 'check')], capture_output=True, text=True)
    if built.returncode != 0:
        print(built.stderr or built.stdout, file=sys.stderr)
        raise SystemExit(built.returncode)
    subprocess.run([str(directory / 'check')], check=True)
