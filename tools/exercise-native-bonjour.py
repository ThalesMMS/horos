#!/usr/bin/env python3
"""Read the running app's Bonjour discovery and publication state (#606).

Steps, each an LLDB attach to the development process (a `--debug` build):

    python3 tools/exercise-native-bonjour.py sources   --pid P
    python3 tools/exercise-native-bonjour.py publish   --pid P --sharing YES
    python3 tools/exercise-native-bonjour.py advertise --pid P

`sources` reads the Sources helper's discovered services (name, type, resolved
address, port, interfaces, TXT) and the rows they produced. `publish` toggles
database sharing. `advertise` reads the publisher's own advertisement: the name
the daemon gave it, its port, whether it is published and what its TXT carries.
Nothing leaves local-validation and no secret is read.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['sources', 'publish', 'advertise'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--sharing', choices=['YES', 'NO'], default='YES')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-606-native'))
args = parser.parse_args()
label = args.label or args.step
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', label):
    parser.error('Use a positive PID and a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / ('bonjour-' + label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

bodies = {
    'sources': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        'id $b = (id)[(Class)objc_getClass("BrowserController") currentBrowser]',
        'id $helper = (id)[(NSObject*)$b valueForKey:@"_sourcesHelper"]',
        '$m[@"helper"] = @($helper != nil)',
        'NSMutableArray *$rows = [NSMutableArray array]',
        'for (id s in (NSArray*)[(NSObject*)$helper valueForKey:@"_bonjourServices"]) (void)[$rows addObject:@{@"class": NSStringFromClass((Class)[(NSObject*)s class]), @"name": (NSString*)[s name] ?: @"", @"type": (NSString*)[s type] ?: @"", @"domain": (NSString*)[s domain] ?: @"", @"port": @((long)[s port]), @"host": (NSString*)[s hostName] ?: @"", @"address": (NSString*)[s resolvedAddress] ?: @"", @"resolved": @((BOOL)[s isResolved]), @"interfaces": (NSArray*)[(NSObject*)s valueForKey:@"interfaceIndexes"] ?: @[], @"txt": [[NSString alloc] initWithData:(NSData*)[s TXTRecordData] ?: [NSData data] encoding:4] ?: @""}]',
        '$m[@"services"] = $rows',
        'NSMutableArray *$sources = [NSMutableArray array]',
        'for (id s in (NSArray*)[(NSObject*)$helper valueForKey:@"_bonjourSources"]) (void)[$sources addObject:@{@"description": (NSString*)[(NSObject*)s valueForKey:@"description"] ?: @"", @"class": NSStringFromClass((Class)[(NSObject*)s class]), @"detected": @((BOOL)[(NSNumber*)[(NSObject*)s valueForKey:@"detected"] boolValue])}]',
        '$m[@"sources"] = $sources',
        'id $osirix = (id)[(NSObject*)$helper valueForKey:@"_nsbOsirix"]',
        'id $dicom = (id)[(NSObject*)$helper valueForKey:@"_nsbDicom"]',
        '$m[@"browsers"] = @{@"osirixdb": NSStringFromClass((Class)[(NSObject*)$osirix class]) ?: @"", @"dicom": NSStringFromClass((Class)[(NSObject*)$dicom class]) ?: @"", @"osirixdbSearching": @((BOOL)[$osirix isSearching]), @"dicomSearching": @((BOOL)[$dicom isSearching])}',
    ],
    'publish': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        '(void)[[NSUserDefaults standardUserDefaults] setBool:SHARING forKey:@"bonjourSharing"]',
        'id $publisher = (id)[(id)[(Class)objc_getClass("AppController") sharedAppController] bonjourPublisher]',
        '(void)[$publisher toggleSharing: SHARING]',
        '$m[@"sharing"] = @((BOOL)[[NSUserDefaults standardUserDefaults] boolForKey:@"bonjourSharing"])',
        '$m[@"publisher"] = @($publisher != nil)',
    ],
    'advertise': [
        'NSMutableDictionary *$m = [NSMutableDictionary dictionary]',
        'id $publisher = (id)[(id)[(Class)objc_getClass("AppController") sharedAppController] bonjourPublisher]',
        'id $ad = (id)[$publisher advertisement]',
        '$m[@"advertisement"] = @($ad != nil)',
        '$m[@"name"] = (NSString*)[$ad name] ?: @""',
        '$m[@"type"] = (NSString*)[$ad type] ?: @""',
        '$m[@"port"] = @((long)[$ad port])',
        '$m[@"isPublished"] = @((BOOL)[$ad isPublished])',
        '$m[@"txt"] = (NSDictionary*)[$ad txtRecord] ?: @{}',
        '$m[@"listenerPort"] = @((long)[$publisher OsiriXDBCurrentPort])',
        '$m[@"legacyNetService"] = @((id)[$publisher netService] != nil)',
    ],
}

lines = [line.replace('SHARING', args.sharing) for line in bodies[args.step]]
lines.append('(void)[[NSJSONSerialization dataWithJSONObject:$m options:3 error:nil] writeToFile:@"%s" atomically:YES]' % staged)
commands = args.output / ('bonjour-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    + ''.join('expression -l objc++ -- ' + line + '\n' for line in lines) + 'process detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(args.output / ('bonjour-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print('\n'.join(sorted(set(re.findall(r'error: [^\\\n]{0,200}', run.stdout + run.stderr)))))
    raise SystemExit(1)
staged.replace(output)
print(json.dumps(json.loads(output.read_text()), indent=1, sort_keys=True))
