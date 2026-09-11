#!/usr/bin/env python3
"""XML-RPC reads windows and managed objects on the thread that owns them.

GetDisplayed2DViewerSeries used to call +[ViewerController getDisplayed2DViewers]
on the connection thread. That method asks [[w window] isKindOfClass:] and
[w windowWillClose] - AppKit, off the main thread. The same call then ran
+[XMLRPCInterface dictionaryForObject:] against the main-thread Core Data
context, and valueForKey:thumbnail locked that context and could generate an
NSImage. The Main Thread Checker and the N2ManagedDatabase warning both fired.

The hop belongs at the XML-RPC boundary. AppKit UI paths already run on main;
getDisplayed2DViewers itself must not start hopping for every caller. The
connection thread waits for the read, then answers the caller itself.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

helper = root / 'Horos/Sources/XMLRPCOwnedThreadRead.swift'
methods = (root / 'Horos/Sources/XMLRPCMethods.mm').read_bytes().decode('latin1')
viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


def method_body(source, signature):
    compact = re.sub(r'\s+', '', source)
    needle = re.sub(r'\s+', '', signature)
    compact_at = compact.find(needle)
    if compact_at < 0:
        at = source.find(signature)
    else:
        # Map the compacted index back by walking the original.
        seen = 0
        at = 0
        while at < len(source) and seen < compact_at:
            if not source[at].isspace():
                seen += 1
            at += 1
    if at < 0 or at >= len(source):
        return ''
    opening = source.find('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


# --- getDisplayed2DViewers stays a plain AppKit read --------------------------
displayed = method_body(strip(viewer), '+ (NSMutableArray*) getDisplayed2DViewers')
if not displayed:
    failures.append('+[ViewerController getDisplayed2DViewers] is gone')
else:
    if 'performSelectorOnMainThread' in displayed or 'onMainAndWait' in displayed:
        failures.append('getDisplayed2DViewers hops to main for every caller; the hop belongs '
                        'at the XML-RPC boundary so AppKit paths already on main stay put')
    if 'windowWillClose' not in displayed or 'isKindOfClass' not in displayed:
        failures.append('getDisplayed2DViewers no longer reads the window on the calling thread')

# --- the five XML-RPC methods that used to read off-thread --------------------
rpc = strip(methods)
for signature, needs_window_hop, label in (
        ('-(NSDictionary*)GetDisplayed2DViewerSeries:', True, 'GetDisplayed2DViewerSeries'),
        ('-(NSDictionary*)GetDisplayed2DViewerStudies:', True, 'GetDisplayed2DViewerStudies'),
        ('-(NSDictionary*)DisplayStudy:', False, 'DisplayStudy'),
        ('-(NSDictionary*)DisplaySeries:', False, 'DisplaySeries'),
        ('-(NSDictionary*)FindObject:', False, 'FindObject')):
    body = method_body(rpc, signature)
    if not body:
        failures.append('%s is gone' % label)
        continue
    if 'dictionaryForObject' not in body:
        failures.append('%s no longer serializes managed objects through dictionaryForObject'
                        % label)
    if needs_window_hop:
        if 'onMainAndWait' not in body:
            failures.append('%s still reads displayed viewers on the connection thread' % label)
        if 'getDisplayed2DViewers' not in body:
            failures.append('%s no longer asks getDisplayed2DViewers' % label)
        # The window read has to happen *inside* the hop, and the reply after it.
        hop = body.find('onMainAndWait')
        read = body.find('getDisplayed2DViewers')
        reply = body.find('ReturnWithErrorValueAndObjectForKey')
        if hop < 0 or read < hop:
            failures.append('%s reads getDisplayed2DViewers before hopping to main' % label)
        if reply < 0 or reply < hop:
            failures.append('%s no longer answers the caller after the main-thread read' % label)

# CloseAllWindows already hops; keep that pattern for the displayed-viewer reads.
if 'performSelectorOnMainThread' not in method_body(rpc, '-(NSDictionary*)CloseAllWindows:'):
    failures.append('CloseAllWindows no longer hops to main, so the pattern the new reads follow '
                    'is gone')

# dictionaryForObject itself must not touch thumbnail / binary attributes.
dictionary = method_body(rpc, '+(NSDictionary*)dictionaryForObject:')
if not dictionary:
    failures.append('+dictionaryForObject: is gone')
elif 'HorosXMLRPCOwnedThreadRead' not in dictionary and 'XMLRPCOwnedThreadRead' not in dictionary:
    failures.append('dictionaryForObject still reads every attribute, including thumbnail, '
                    'on whatever thread called it')

# --- the helper, compiled and run --------------------------------------------
if not helper.is_file():
    failures.append('Horos/Sources/XMLRPCOwnedThreadRead.swift is missing')
else:
    driver = r'''
import Foundation
import CoreData

final class Probe: NSManagedObject {
    override func value(forKey key: String) -> Any? {
        if key == "thumbnail" {
            fatalError("thumbnail was read off the owner-thread contract")
        }
        return super.value(forKey: key)
    }
}

let model = NSManagedObjectModel()
let entity = NSEntityDescription()
entity.name = "Series"
entity.managedObjectClassName = NSStringFromClass(Probe.self)
let name = NSAttributeDescription()
name.name = "name"
name.attributeType = .stringAttributeType
let count = NSAttributeDescription()
count.name = "numberOfImages"
count.attributeType = .integer32AttributeType
let thumb = NSAttributeDescription()
thumb.name = "thumbnail"
thumb.attributeType = .binaryDataAttributeType
entity.properties = [name, count, thumb]
model.entities = [entity]

let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
try! coordinator.addPersistentStore(ofType: NSInMemoryStoreType, configurationName: nil,
                                    at: nil, options: nil)
let context = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
context.persistentStoreCoordinator = coordinator
let object = Probe(entity: entity, insertInto: context)
object.setPrimitiveValue("CT", forKey: "name")
object.setPrimitiveValue(12, forKey: "numberOfImages")
object.setPrimitiveValue(Data([0xFF, 0xD8]), forKey: "thumbnail")

let dictionary = XMLRPCOwnedThreadRead.dictionary(for: object)
precondition(dictionary["name"] == "CT", "name: \(dictionary)")
precondition(dictionary["numberOfImages"] == "12", "count: \(dictionary)")
precondition(dictionary["thumbnail"] == nil, "thumbnail leaked: \(dictionary)")

// A value that would break XML is escaped the way the old helper escaped it.
object.setPrimitiveValue("a <b> & c", forKey: "name")
let escaped = XMLRPCOwnedThreadRead.dictionary(for: object)
precondition(escaped["name"] == "a &lt;b&gt; &amp; c", "escape: \(escaped)")

// Already on main: the work runs in place, so a UI path that calls through
// the helper does not deadlock.
var ranOnMain = false
let inPlace = XMLRPCOwnedThreadRead.onMainAndWait {
    ranOnMain = Thread.isMainThread
    return "main"
}
precondition(ranOnMain && (inPlace as? String) == "main", "in-place hop failed")

// From a connection-like thread: the work runs on main, the caller waits
// and keeps the result to answer itself.
// perform-on-main waits for the main run loop, the way the app's connection
// thread waits for NSApp. A semaphore on main would deadlock that hop.
final class HopState {
    var backgroundSawMain = false
    var backgroundKept = ""
    var callerWasBackground = false
    var finished = false
}
let hop = HopState()
Thread.detachNewThread {
    hop.callerWasBackground = !Thread.isMainThread
    let value = XMLRPCOwnedThreadRead.onMainAndWait {
        hop.backgroundSawMain = Thread.isMainThread
        return "from-main"
    }
    hop.backgroundKept = value as? String ?? ""
    hop.finished = true
}
let deadline = Date().addingTimeInterval(5)
while !hop.finished && Date() < deadline {
    RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.05))
}
precondition(hop.finished, "the connection thread never came back")
precondition(hop.callerWasBackground, "the connection thread was not a background thread")
precondition(hop.backgroundSawMain, "the read did not run on main")
precondition(hop.backgroundKept == "from-main", "the connection thread lost the result")

print("PASS: hop waits on main, reply stays with the caller, thumbnail is not read")
'''
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'],
                            capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-xmlrpc-owned-') as directory:
            main = Path(directory) / 'main.swift'
            main.write_text(driver)
            binary = Path(directory) / 'owned'
            built = subprocess.run(
                ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                 str(helper), str(main)],
                capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the owned-thread helper does not compile:\n%s'
                                % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the owned-thread helper failed: %s %s'
                                    % (run.stdout[-400:], run.stderr[-800:]))
                elif 'PASS:' not in run.stdout:
                    failures.append('the owned-thread helper printed nothing useful: %r'
                                    % run.stdout)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: XML-RPC hops displayed-viewer and Core Data reads to the owner thread, '
      'skips thumbnail, and answers on the connection thread; getDisplayed2DViewers '
      'is unchanged for AppKit callers')
