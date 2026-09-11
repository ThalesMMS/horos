#!/usr/bin/env python3
"""Exercise main-bundle fallback with the production development-region setting."""
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
raw=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Info.plist'])
     if len(sys.argv)>1 else (root/'Horos/Info.plist').read_bytes())
info=plistlib.loads(raw)
code=r'''
#import <Foundation/Foundation.h>
int main(){@autoreleasepool{
 NSBundle*b=[NSBundle mainBundle];
 if(![b.preferredLocalizations.firstObject isEqualToString:@"it-IT"]){NSLog(@"FAIL language: %@",b.preferredLocalizations);return 1;}
 NSString *menu=[b pathForResource:@"MainMenu" ofType:@"nib"];
 NSString *viewer=[b pathForResource:@"Viewer" ofType:@"nib"];
 if(![menu hasSuffix:@"it-IT.lproj/MainMenu.nib"] || ![viewer hasSuffix:@"en.lproj/Viewer.nib"]){
  NSLog(@"FAIL development language %@: menu=%@ viewer=%@",b.developmentLocalization,menu,viewer);return 1;
 }
 NSLog(@"PASS: Italian main menu and English fallback viewer with production development-region setting");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-localization-fallback-') as d:
    p=Path(d);contents=p/'Test.app/Contents';resources=contents/'Resources'
    (contents/'MacOS').mkdir(parents=True)
    for lang,name in [('en','Viewer'),('it-IT','MainMenu')]:
        (resources/f'{lang}.lproj').mkdir(parents=True)
        (resources/f'{lang}.lproj/{name}.nib').write_text('resource lookup fixture')
    info.update(CFBundleExecutable='test',CFBundleIdentifier='org.horos.qa.localization-fallback')
    (contents/'Info.plist').write_bytes(plistlib.dumps(info))
    (p/'test.m').write_text(code)
    executable=contents/'MacOS/test'
    subprocess.run(['xcrun','clang','-framework','Foundation',str(p/'test.m'),'-o',str(executable)],check=True)
    subprocess.run([str(executable),'-AppleLanguages','(it-IT)'],check=True)
