#!/usr/bin/env python3
"""Drive the shared-database client against a controlled server (#607).

The controlled server is the development app's own `O2DatabaseConnection`
listener: enable database sharing, then ask the same process to open a
`RemoteDicomDatabase` on 127.0.0.1 and use it. The protocol crossed is the real
one; the peer is a real Horos server, in a process this validation controls.

    python3 tools/exercise-native-shared-database.py share   --pid P --sharing YES
    python3 tools/exercise-native-shared-database.py version --pid P --port 8780
    python3 tools/exercise-native-shared-database.py index   --pid P --port 8780
    python3 tools/exercise-native-shared-database.py image   --pid P --port 8780
    python3 tools/exercise-native-shared-database.py refused --pid P --port 9   (nothing listening)
    python3 tools/exercise-native-shared-database.py cancel  --pid P --port 8780

Each step is an LLDB attach; every read is written to a JSON file under
local-validation. Nothing leaves it and no credential is read.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['share', 'version', 'index', 'counts', 'image', 'refused', 'cancel'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--port', type=int, default=8780)
parser.add_argument('--sharing', choices=['YES', 'NO'], default='YES')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-607-native'))
args = parser.parse_args()
label = args.label or args.step
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', label) or not 1 <= args.port <= 65535:
    parser.error('Use a positive PID, a lowercase label and a real port')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / ('shared-' + label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

REMOTE = [
    'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
    'double $t0 = (double)[NSDate timeIntervalSinceReferenceDate]',
    'id $remote = (id)[(Class)objc_getClass("RemoteDicomDatabase") databaseForLocation:@"127.0.0.1" port:PORT name:@"controlled peer" update:NO]',
    '$m[@"openMs"] = @(((double)[NSDate timeIntervalSinceReferenceDate] - $t0) * 1000.0)',
    '$m[@"remote"] = @($remote != nil)',
    '$m[@"address"] = (NSString*)[$remote address] ?: @""',
    '$m[@"port"] = @((long)[$remote port])',
]
bodies = {
    'share': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        '(void)[[NSUserDefaults standardUserDefaults] setBool:SHARING forKey:@"bonjourSharing"]',
        'id $publisher = (id)[(id)[(Class)objc_getClass("AppController") sharedAppController] bonjourPublisher]',
        '(void)[$publisher toggleSharing: SHARING]',
        '$m[@"listenerPort"] = @((long)[$publisher OsiriXDBCurrentPort])',
        '$m[@"sharing"] = @((BOOL)[[NSUserDefaults standardUserDefaults] boolForKey:@"bonjourSharing"])',
    ],
    'version': REMOTE + [
        'double $t1 = (double)[NSDate timeIntervalSinceReferenceDate]',
        '$m[@"version"] = (NSString*)[$remote fetchDatabaseVersion] ?: @""',
        '$m[@"versionMs"] = @(((double)[NSDate timeIntervalSinceReferenceDate] - $t1) * 1000.0)',
        '$m[@"indexSize"] = @((long)[$remote fetchDatabaseIndexSize])',
        '$m[@"versiBytes"] = @((long)[(NSData*)[$remote synchronousRequest:[NSMutableData dataWithBytes:"VERSI" length:6] urgent:YES] length])',
    ],
    # Loading the fetched index happens on the main thread, which cannot run
    # while an attach is evaluating: `index` selects the remote database the way
    # the Sources list does and lets go, `counts` reads it in a later attach.
    'counts': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        'id $db = (id)[(id)[(Class)objc_getClass("BrowserController") currentBrowser] database]',
        '$m[@"class"] = NSStringFromClass((Class)[(NSObject*)$db class])',
        '$m[@"address"] = (NSString*)[(NSObject*)$db valueForKey:@"address"] ?: @""',
        '$m[@"studies"] = @((long)[(NSArray*)[$db objectsForEntity:(id)[$db entityForName:@"Study"]] count])',
        '$m[@"series"] = @((long)[(NSArray*)[$db objectsForEntity:(id)[$db entityForName:@"Series"]] count])',
        '$m[@"images"] = @((long)[(NSArray*)[$db objectsForEntity:(id)[$db entityForName:@"Image"]] count])',
    ],
    'index': REMOTE + [
        'double $t1 = (double)[NSDate timeIntervalSinceReferenceDate]',
        'NSThread *$thread = (NSThread*)[$remote initiateUpdate]',
        '$m[@"updateStarted"] = @($thread != nil)',
        'for (int i = 0; i < 900 && ![$thread isFinished]; i++) usleep(50000)',
        '$m[@"updateMs"] = @(((double)[NSDate timeIntervalSinceReferenceDate] - $t1) * 1000.0)',
        '$m[@"updateFinished"] = @((BOOL)[$thread isFinished])',
        '(void)[(id)[(Class)objc_getClass("BrowserController") currentBrowser] setDatabase: $remote]',
        '$m[@"selectedInBrowser"] = @YES',
    ],
    # Runs after `index` + a resume: the browser already holds the remote database.
    'image': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        'id $remote = (id)[(id)[(Class)objc_getClass("BrowserController") currentBrowser] database]',
        '$m[@"class"] = NSStringFromClass((Class)[(NSObject*)$remote class])',
        'NSArray *$images = (NSArray*)[$remote objectsForEntity:(id)[$remote entityForName:@"Image"]]',
        '$m[@"images"] = @((long)[$images count])',
        'id $image = [$images firstObject]',
        'double $t2 = (double)[NSDate timeIntervalSinceReferenceDate]',
        'NSString *$path = (NSString*)[$remote cacheDataForImage:$image maxFiles:1]',
        '$m[@"downloadMs"] = @(((double)[NSDate timeIntervalSinceReferenceDate] - $t2) * 1000.0)',
        '$m[@"path"] = $path ?: @""',
        '$m[@"exists"] = @((BOOL)[[NSFileManager defaultManager] fileExistsAtPath: $path ?: @""])',
        '$m[@"bytes"] = @((long)[(NSNumber*)[[[NSFileManager defaultManager] attributesOfItemAtPath:($path ?: @"") error:nil] objectForKey:NSFileSize] longLongValue])',
        '$m[@"isDICOM"] = @((BOOL)[(Class)objc_getClass("DicomFile") isDICOMFile: $path ?: @""])',
        '$m[@"remoteSOP"] = (NSString*)[(NSObject*)$image valueForKey:@"sopInstanceUID"] ?: @""',
    ],
    'refused': REMOTE + [
        'double $t1 = (double)[NSDate timeIntervalSinceReferenceDate]',
        'NSError *$err = nil',
        'NSData *$response = (NSData*)[(Class)objc_getClass("HorosDatabaseTransport") sendRequest:[NSMutableData dataWithBytes:"VERSI" length:6] toHost:@"127.0.0.1" port:PORT receiving:nil cancelled:^BOOL{ return NO; } error:&$err]',
        '$m[@"refusedMs"] = @(((double)[NSDate timeIntervalSinceReferenceDate] - $t1) * 1000.0)',
        '$m[@"bytes"] = @((long)[$response length])',
        '$m[@"reason"] = (NSString*)[$err localizedDescription] ?: @""',
    ],
    'cancel': REMOTE + [
        'NSThread *$thread = (NSThread*)[$remote initiateUpdate]',
        'usleep(120000)',
        '[$thread cancel]',
        'double $t1 = (double)[NSDate timeIntervalSinceReferenceDate]',
        'for (int i = 0; i < 600 && ![$thread isFinished]; i++) usleep(50000)',
        '$m[@"stopMs"] = @(((double)[NSDate timeIntervalSinceReferenceDate] - $t1) * 1000.0)',
        '$m[@"cancelled"] = @((BOOL)[$thread isCancelled])',
        '$m[@"stillExecuting"] = @((BOOL)[$thread isExecuting])',
    ],
}

lines = [line.replace('PORT', str(args.port)).replace('SHARING', args.sharing) for line in bodies[args.step]]
lines.append('(void)[[NSJSONSerialization dataWithJSONObject:$m options:3 error:nil] writeToFile:@"%s" atomically:YES]' % staged)
commands = args.output / ('shared-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    + ''.join('expression -l objc++ -- ' + line + '\n' for line in lines) + 'process detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(args.output / ('shared-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print('\n'.join(sorted(set(re.findall(r'error: [^\\\n]{0,200}', run.stdout + run.stderr)))))
    raise SystemExit(1)
staged.replace(output)
print(json.dumps(json.loads(output.read_text()), indent=1, sort_keys=True))
