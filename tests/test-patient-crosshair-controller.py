#!/usr/bin/env python3
"""#373/A295: one patient point, existing world policy, source lifetime and toggle."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
driver = r'''
import AppKit

@MainActor final class Observer: NSObject {
    var moves: [Bool] = []
    @objc func changed(_ notification: Notification) {
        precondition(Thread.isMainThread)
        moves.append(notification.userInfo!["move"] as! Bool)
    }
}

@main struct Check {
    @MainActor static func main() {
        let registry = VolumeSessionRegistry()
        func session(_ series: String, frame: String = "frame-A", study: String = "study") -> VolumeSession {
            let identity = VolumeIdentity(studyInstanceUID: study, seriesInstanceUID: series,
                frameOfReferenceUID: frame, timeIndex: 0, generation: 0)!
            return registry.open(identity: identity, owner: series)!
        }
        let source = session("source"), destination = session("destination")
        let wrongFrame = session("wrong-frame", frame: "frame-B")
        let wrongStudy = session("wrong-study", study: "another-study")
        let suite = "horos-crosshair-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defaults.register(defaults: [ViewerReferenceLines.frameOfReferencePreferenceKey: true])
        defer { defaults.removePersistentDomain(forName: suite) }
        let controller = PatientCrosshairController(defaults: defaults)
        let owner = NSObject(), observer = Observer()
        NotificationCenter.default.addObserver(observer, selector: #selector(Observer.changed(_:)),
            name: Notification.Name(PatientCrosshairController.changeNotification), object: controller)
        defer { NotificationCenter.default.removeObserver(observer); registry.closeAll() }

        precondition(controller.currentPoint == nil && controller.isVisible)
        precondition(!controller.publish(x: .nan, y: 0, z: 0, session: source, owner: owner))
        precondition(!controller.publish(x: 0, y: .infinity, z: 0, session: source, owner: owner))
        precondition(observer.moves.isEmpty)
        precondition(controller.publish(x: 8, y: 12.5, z: -3, session: source, owner: owner))
        let point = controller.currentPoint!
        precondition(point.x == 8 && point.y == 12.5 && point.z == -3)
        precondition(point.identity === source.identity && controller.sourceOwner === owner)
        precondition(controller.point(for: destination, registered: false, useFrameOfReference: true) === point)
        precondition(controller.point(for: wrongFrame, registered: false, useFrameOfReference: true) == nil)
        precondition(controller.point(for: wrongFrame, registered: false, useFrameOfReference: false) === point)
        precondition(controller.point(for: wrongStudy, registered: false, useFrameOfReference: false) == nil)
        precondition(controller.point(for: wrongStudy, registered: true, useFrameOfReference: true) === point)

        controller.setVisible(false)
        precondition(!controller.isVisible && controller.currentPoint === point)
        controller.setVisible(false) // no repeated refresh for an unchanged toggle
        controller.setVisible(true)
        precondition(controller.currentPoint === point)
        precondition(observer.moves == [true, false, false])
        // Actual UserDefaults notifications refresh overlays, including an
        // inactive destination, without republishing/moving the patient point.
        let preference = ViewerReferenceLines.frameOfReferencePreferenceKey
        defaults.set(false, forKey: preference)
        RunLoop.main.run(until: Date().addingTimeInterval(0.02))
        precondition(observer.moves == [true, false, false, false])
        defaults.set(false, forKey: preference)
        defaults.set("unrelated", forKey: "OtherPreference")
        RunLoop.main.run(until: Date().addingTimeInterval(0.02))
        precondition(observer.moves.count == 4)
        defaults.set(true, forKey: preference)
        RunLoop.main.run(until: Date().addingTimeInterval(0.02))
        precondition(observer.moves == [true, false, false, false, false])
        precondition(controller.currentPoint === point)
        controller.clear(owner: NSObject())
        precondition(controller.currentPoint === point)

        registry.invalidateVolume(destination.identity)
        precondition(controller.point(for: destination, registered: true, useFrameOfReference: false) == nil)
        registry.close(source)
        precondition(controller.currentPoint == nil)
        precondition(!controller.publish(x: 1, y: 2, z: 3, session: source, owner: owner))
        controller.clear(owner: owner)
        precondition(controller.sourceOwner == nil && observer.moves.last == false)

        let next = session("next")
        precondition(controller.publish(x: 1, y: 2, z: 3, session: next, owner: owner))
        registry.invalidateVolume(next.identity)
        precondition(controller.currentPoint == nil)
        precondition(!controller.publish(x: 4, y: 5, z: 6, session: next, owner: owner))

        let invalidated = session("invalidated")
        precondition(controller.publish(x: 1, y: 2, z: 3, session: invalidated, owner: owner))
        controller.invalidate(session: destination)
        precondition(controller.currentPoint != nil)
        controller.invalidate(session: invalidated)
        precondition(controller.currentPoint == nil && controller.sourceOwner == nil && observer.moves.last == false)

        let transient = session("transient")
        weak var weakOwner: NSObject?
        autoreleasepool {
            let temporaryOwner = NSObject()
            weakOwner = temporaryOwner
            precondition(controller.publish(x: 1, y: 2, z: 3, session: transient, owner: temporaryOwner))
        }
        precondition(weakOwner == nil && controller.currentPoint == nil)
        print("PASS: finite patient point, frame/registration policy, visibility state, source/destination invalidation and weak owner")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-patient-crosshair-') as directory:
    directory = Path(directory)
    source = directory/'Check.swift'; source.write_text(driver)
    executable = directory/'check'
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                    *[str(root/'Horos/Sources'/name) for name in
                      ('VolumeSession.swift', 'ViewerReferenceLines.swift', 'PatientCrosshairController.swift')],
                    str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
