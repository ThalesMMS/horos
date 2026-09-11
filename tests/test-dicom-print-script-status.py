#!/usr/bin/env python3
"""Execute the actual generated print script with controlled DCMTK executables."""
from pathlib import Path
import os
import subprocess
import tempfile
import sys
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--real-tools',type=Path,help='Optional DCMTK resource directory for a missing-configuration failure check')
args=parser.parse_args()
root=Path(__file__).resolve().parent.parent
source=(root/'DICOMPrint/AYDicomPrintWindowController.mm').read_bytes().decode('latin1')
start=source.index('            NSMutableString* printScript =')
prefix=source[start:source.index('            int ipp =',start)]
start=source.index('                for( int i = 0; i <= ([images count] - 1) / ipp; i++)')
end=source.index('                if (![loggerConfig writeToFile:',start)
commands=source[start:end]
constants='\n'.join(line for line in source.splitlines() if line.startswith('NSString *') and 'Tag[] =' in line)
program=r'''
#import <Foundation/Foundation.h>
static NSString *resources;
@interface TestBundle : NSObject
+ (id)mainBundle;
- (NSString*)resourcePath;
@end
@implementation TestBundle
+ (id)mainBundle { return [self new]; }
- (NSString*)resourcePath { return resources; }
@end
#define NSBundle TestBundle
CONSTANTS
int main(int argc,char **argv) { @autoreleasepool {
 resources=[NSString stringWithUTF8String:argv[1]];
 NSString *printJobDir=[NSString stringWithUTF8String:argv[2]];
 NSString *logPath=[NSString stringWithUTF8String:argv[3]];
 NSString *printJobID=@"synthetic QA";
 NSString *printConfigPath=[printJobDir stringByAppendingPathComponent:@"print.cfg"];
 NSString *loggerConfigPath=[printJobDir stringByAppendingPathComponent:@"logger.cfg"];
 int columns=6, rows=4, ipp=24, copies=1;
 NSString *filmSize=@"14INX17IN";
 NSDictionary *dict=@{@"magnificationTypeTag":@1,@"configurationInformation":@"",@"borderDensityTag":@0,@"emptyImageDensityTag":@0,@"trimTag":@0,@"filmOrientationTag":@0,@"priorityTag":@1,@"filmDestinationTag":@0,@"mediumTag":@0};
 NSMutableArray *images=[NSMutableArray array];
 for(int i=0;i<25;i++) [images addObject:[printJobDir stringByAppendingPathComponent:[NSString stringWithFormat:@"image-%d.dcm",i]]];
 PREFIX
 COMMANDS
 if(![printScript writeToFile:[printJobDir stringByAppendingPathComponent:@"print.sh"] atomically:YES encoding:NSUTF8StringEncoding error:NULL]) return 1;
} }
'''.replace('CONSTANTS',constants).replace('PREFIX',prefix).replace('COMMANDS',commands)
with tempfile.TemporaryDirectory(prefix='horos-print-status-') as directory:
    p=Path(directory);(p/'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-framework','Foundation',str(p/'test.m'),'-o',str(p/'generate')],check=True)
    binaries=p/'mock tools';binaries.mkdir()
    mock='#!'+sys.executable+r'''
import os, sys
from pathlib import Path
name=Path(__file__).name
trace=Path(os.environ['QA_TRACE'])
previous=trace.read_text().splitlines() if trace.exists() else []
with trace.open('a') as f: f.write(name+'\n')
if name=='dcmpsprt':
    count=previous.count(name)+1
    raise SystemExit(23 if count==int(os.environ.get('QA_FAIL_PREPARE_AT','0')) else 0)
assert sys.argv[sys.argv.index('--medium-type')+1] == 'BLUE FILM', sys.argv
assert sys.argv[-1].endswith('/database/SP_*'), sys.argv
raise SystemExit(int(os.environ.get('QA_SEND_STATUS','0')))
'''
    for name in ['dcmpsprt','dcmprscu']:
        tool=binaries/name;tool.write_text(mock);tool.chmod(0o700)
    for name,fail,send,expected,sequence in [
        ('first-page-fails',1,0,23,['dcmpsprt']),
        ('second-page-fails',2,0,23,['dcmpsprt','dcmpsprt']),
        ('printer-refuses',0,41,41,['dcmpsprt','dcmpsprt','dcmprscu']),
        ('success',0,0,0,['dcmpsprt','dcmpsprt','dcmprscu'])]:
        job=p/name;job.mkdir();logs=p/(name+' logs');logs.mkdir()
        subprocess.run([str(p/'generate'),str(binaries),str(job),str(logs)],check=True)
        env=os.environ.copy();env.update(QA_TRACE=str(job/'calls'),QA_FAIL_PREPARE_AT=str(fail),QA_SEND_STATUS=str(send))
        result=subprocess.run(['/bin/bash',str(job/'print.sh')],env=env,capture_output=True,text=True)
        assert result.returncode==expected,(name,result.returncode,result.stderr)
        assert (job/'calls').read_text().splitlines()==sequence,name
        text=(logs/'print.log').read_text()
        assert ('End print job' in text)==(expected==0),name
        print('PASS:',name)
    if args.real_tools:
        job=p/'real-missing-config';job.mkdir();logs=p/'real-logs';logs.mkdir()
        subprocess.run([str(p/'generate'),str(args.real_tools.resolve()),str(job),str(logs)],check=True)
        result=subprocess.run(['/bin/bash',str(job/'print.sh')],capture_output=True,text=True)
        assert result.returncode != 0, 'Real dcmpsprt failure was hidden'
        assert 'End print job' not in (logs/'print.log').read_text()
        print('PASS: real DCMTK missing configuration propagates failure, status',result.returncode)
