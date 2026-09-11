#!/usr/bin/env python3
"""Time the related-studies fetch with and without the published limit (#380 C).

Runs, inside the running development build and on its own database, the same
fetch the browser's comparative search runs — same predicate, same descending
date order — once unlimited and once at the limit the contract publishes,
`--iterations` times each, and reports how many studies each returns and how
long it takes. Nothing is displayed and no panel is raised: this is the fetch,
not the window.

    python3 tools/measure-native-related-studies.py --pid N --patient SYNTHETIC-380-01
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--patient', required=True, help='patient ID whose history is measured')
parser.add_argument('--iterations', type=int, default=20)
parser.add_argument('--label', default='related-studies')
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-380-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label) or not 1 <= args.iterations <= 200:
    parser.error('positive PID, a lowercase label and 1-200 iterations')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

expression = r'''
NSMutableDictionary *m380 = [NSMutableDictionary dictionary];
id br380 = (id)[(id)objc_getClass("BrowserController") currentBrowser];
id db380 = (id)[br380 database];
NSString *uid380 = nil;
long total380 = 0;
for (id st380 in (NSArray*)[db380 objectsForEntity:(id)[db380 studyEntity] predicate:[NSPredicate predicateWithValue:YES]]) {
  if ([(NSString*)[(NSObject*)st380 valueForKey:@"patientID"] isEqualToString:PATIENT]) {
    total380++;
    if (uid380 == nil) uid380 = (NSString*)[(NSObject*)st380 valueForKey:@"patientUID"];
  }
}
m380[@"patientUID"] = uid380 ?: @"";
m380[@"studiesInDatabase"] = @(total380);
m380[@"contract"] = (NSString*)[(Class)objc_getClass("HorosAssociationContract") summary];
m380[@"limit"] = @((long)[(Class)objc_getClass("HorosAssociationContract") relatedStudiesLimitIn:[NSUserDefaults standardUserDefaults]]);
mach_timebase_info_data_t tb380; (void)mach_timebase_info(&tb380);
NSArray *limits380 = @[@0, @((long)[(Class)objc_getClass("HorosAssociationContract") relatedStudiesLimitIn:[NSUserDefaults standardUserDefaults]]), @10];
NSMutableArray *runs380 = [NSMutableArray array];
for (NSNumber *limit380 in limits380) {
  NSMutableArray *times380 = [NSMutableArray array];
  long count380 = 0;
  NSString *firstDate380 = @"", *lastDate380 = @"";
  for (int i380 = 0; i380 < ITERATIONS; i380++) {
    NSFetchRequest *rq380 = [[NSFetchRequest alloc] init];
    (void)[rq380 setEntity:(id)[db380 studyEntity]];
    (void)[rq380 setPredicate:[NSPredicate predicateWithFormat:@"(patientUID ==[cd] %@)", uid380]];
    (void)[rq380 setSortDescriptors:@[[NSSortDescriptor sortDescriptorWithKey:@"date" ascending:NO]]];
    if ([limit380 longValue] > 0) (void)[rq380 setFetchLimit:[limit380 longValue]];
    uint64_t t0 = mach_absolute_time();
    NSArray *rows380 = [(NSManagedObjectContext*)[db380 managedObjectContext] executeFetchRequest:rq380 error:nil];
    for (id row380 in rows380) (void)[(NSObject*)row380 valueForKey:@"studyInstanceUID"];
    uint64_t t1 = mach_absolute_time();
    (void)[times380 addObject:@((double)(t1 - t0) * tb380.numer / tb380.denom / 1e6)];
    count380 = (long)[rows380 count];
    if (count380) {
      firstDate380 = [(NSDate*)[(NSObject*)[rows380 firstObject] valueForKey:@"date"] description] ?: @"";
      lastDate380 = [(NSDate*)[(NSObject*)[rows380 lastObject] valueForKey:@"date"] description] ?: @"";
    }
  }
  (void)[runs380 addObject:@{@"limit": limit380, @"returned": @(count380), @"milliseconds": times380,
                             @"newest": firstDate380, @"oldest": lastDate380}];
}
m380[@"runs"] = runs380;
'''.replace('ITERATIONS', str(args.iterations)).replace('PATIENT', '@' + json.dumps(args.patient))
expression += '(void)[[NSJSONSerialization dataWithJSONObject:m380 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import Darwin\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
data = json.loads(report.read_text())


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


print('patient has %d studies in the database; contract limit %d' % (data['studiesInDatabase'], data['limit']))
for run in data['runs']:
    times = run['milliseconds']
    print('limit %-4d returned %-4d  p50 %6.2f ms  p95 %6.2f ms  newest %s' %
          (run['limit'], run['returned'], percentile(times, 0.5), percentile(times, 0.95), run['newest'][:19]))
