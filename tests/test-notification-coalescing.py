#!/usr/bin/env python3
"""A burst of import notifications reaches the Notification Center once (#696).

Each indexed batch used to post a notification under a new identifier, so one
study made hundreds, which usernoted kept and saved again at every arrival.
Compile the production -notificationTitle:description:name: with a short
interval and a recording delivery, then post a burst from the main thread and
from a worker thread.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
failures = []


def method(signature):
    at = source.find(signature)
    if at < 0:
        failures.append('%s is gone' % signature)
        return ''
    opening = source.index('{', at)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[at:index + 1]
    return ''


post = method('- (void) notificationTitle:(NSString*) title description:(NSString*) description name:(NSString*) name')
deliver = method('- (void) deliverNotificationTitle:(NSString*) title description:(NSString*) description name:(NSString*) name sound:(BOOL) sound')
if 'requestWithIdentifier: [NSUUID' in deliver or 'NSUUID UUID' in deliver:
    failures.append('each notification still gets a new identifier')
if 'stringByAppendingString: name' not in deliver:
    failures.append('the identifier does not come from the kind of notification')
if not re.search(r'if \(sound\) notification\.sound', deliver):
    failures.append('every notification still makes a sound')
if 'removeAllDeliveredNotifications' not in source:
    failures.append('notifications left by earlier versions are not cleared at launch')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
paused = database[database.find('NSLocalizedString(@"Import Paused", nil)'):][:400]
if 'name:@"newfiles"' in paused:
    failures.append('"Import Paused" shares its identifier with "Incoming Files" and would be replaced')

NATIVE = r'''
#import <Foundation/Foundation.h>
static const NSTimeInterval HorosNotificationInterval = 0.3, HorosNotificationQuietSound = 1;
@interface App : NSObject
@property(strong) NSMutableArray *log;
@end
@implementation App
POST
- (void) deliverNotificationTitle:(NSString*) title description:(NSString*) description name:(NSString*) name sound:(BOOL) sound
{
    [self.log addObject: [NSString stringWithFormat: @"%@|%@|%@|%d|%d", name, title, description, sound, NSThread.isMainThread]];
}
@end
static void spin(NSTimeInterval seconds) {
    [[NSRunLoop mainRunLoop] runUntilDate: [NSDate dateWithTimeIntervalSinceNow: seconds]];
}
int main(void) { @autoreleasepool {
    App *app = [App new]; app.log = [NSMutableArray array];
    for (int i = 1; i <= 50; i++)
        [app notificationTitle: @"Incoming Files" description: [NSString stringWithFormat: @"%d", i] name: @"newfiles"];
    [app notificationTitle: @"Import Paused" description: @"full" name: @"importpaused"];
    dispatch_async(dispatch_get_global_queue(0, 0), ^{
        [app notificationTitle: @"Incoming Files" description: @"worker" name: @"newfiles"];
    });
    spin(0.1);
    NSCAssert(app.log.count == 2, @"a burst delivers once at first, other kinds unaffected: %@", app.log);
    NSCAssert([app.log[0] isEqual: @"newfiles|Incoming Files|1|1|1"], @"first of a burst, with sound: %@", app.log[0]);
    NSCAssert([app.log[1] isEqual: @"importpaused|Import Paused|full|1|1"], @"Import Paused is delivered: %@", app.log[1]);
    spin(0.5);
    NSCAssert(app.log.count == 3, @"the rest of the burst is one delivery: %@", app.log);
    NSCAssert([app.log[2] isEqual: @"newfiles|Incoming Files|worker|0|1"], @"latest text, silent, on the main thread: %@", app.log[2]);
    spin(0.5);
    NSCAssert(app.log.count == 3, @"nothing more is delivered: %@", app.log);
    puts("PASS: 51 incoming notifications in a burst became 2 deliveries; Import Paused kept its own");
}}
'''.replace('POST', post)

if post and deliver:
    with tempfile.TemporaryDirectory(prefix='horos-notifications-') as directory:
        path = Path(directory)
        (path / 'test.m').write_text(NATIVE)
        built = subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation',
                                str(path / 'test.m'), '-o', str(path / 'test')],
                               capture_output=True, text=True)
        if built.returncode:
            failures.append('the notification method does not compile: ' + built.stderr[-3000:])
        else:
            run = subprocess.run([str(path / 'test')], capture_output=True, text=True, timeout=30)
            if run.returncode:
                failures.append('coalescing regression: ' + run.stderr[-2000:])
            else:
                print(run.stdout.strip())

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a burst of notifications of one kind is delivered once per interval under one identifier, '
      'with the latest text and a single sound')
