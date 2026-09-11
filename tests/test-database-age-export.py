#!/usr/bin/env python3
"""Run actual database-list export with the actual age-display preference branch."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('- (NSString*) exportDBListOnlySelected:');b=s.index('\n#ifndef OSIRIX_LIGHT',a);export=s[a:b]
a=s.index('        switch ( [[NSUserDefaults standardUserDefaults] integerForKey: @"yearOldDatabaseDisplay"])');b=s.index('\n    if( [[tableColumn identifier] isEqualToString:@"noSeries"])',a);display=s[a:b].rsplit('    }',1)[0]
code=r'''
#import <Cocoa/Cocoa.h>
#import <CoreData/CoreData.h>
#define N2LogException(e) abort()
@interface Outline:NSObject
@property(retain) NSArray *tableColumns;
@property(retain) NSDictionary *study;
- (NSIndexSet*)selectedRowIndexes;
- (NSInteger)numberOfRows;
- (id)itemAtRow:(NSInteger)row;
@end
@implementation Outline
- (NSIndexSet*)selectedRowIndexes{return [NSIndexSet indexSetWithIndex:0];}
- (NSInteger)numberOfRows{return 1;}
- (id)itemAtRow:(NSInteger)row{return self.study;}
- (void)dealloc{[_tableColumns release];[_study release];[super dealloc];}
@end
@interface Browser:NSObject { @public Outline *databaseOutline; }
- (id)outlineView:(id)view objectValueForTableColumn:(id)column byItem:(id)item;
- (NSString*)exportDBListOnlySelected:(BOOL)selected;
@end
@implementation Browser
- (id)outlineView:(id)view objectValueForTableColumn:(id)column byItem:(id)item {
DISPLAY
}
EXPORT
@end
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 Outline *outline=[Outline new];NSTableColumn *col=[[[NSTableColumn alloc] initWithIdentifier:@"yearOld"] autorelease];col.headerCell.stringValue=@"Age";outline.tableColumns=@[col];
 Browser *browser=[Browser new];browser->databaseOutline=outline;
 NSArray *cases=@[@[@"36 y",@"30 y",@"36/30 y"],@[@"6 d",@"2 d",@"6 d/2 d"],@[@"5 m",@"2 m",@"5 m/2 m"],@[@"1 y 3 m",@"7 m",@"1 y 3 m/7 m"],@[@"",@"",@""],@[@"20 y",@"20 y",@"20 y"]];
 for(NSArray *values in cases)for(int mode=0;mode<3;mode++){
  [[NSUserDefaults standardUserDefaults] setInteger:mode forKey:@"yearOldDatabaseDisplay"];
  outline.study=@{@"type":@"Study",@"yearOld":values[0],@"yearOldAcquisition":values[1]};
  NSString *visible=[browser outlineView:outline objectValueForTableColumn:col byItem:outline.study];
  if(![visible isEqual:values[mode]])abort();
  for(int selected=0;selected<2;selected++){
   NSString *result=[browser exportDBListOnlySelected:selected];
   if(![result isEqual:[@"Age\r" stringByAppendingString:visible]]){fprintf(stderr,"FAIL: export differs from displayed age in mode %d\n",mode);return 1;}
  }
 }
 [browser release];[outline release];
 puts("PASS: actual export matches actual age display for all three preferences, years/days/months/mixed units/missing birth date/equal ages and selected/all rows");
}}
'''.replace('DISPLAY',display).replace('EXPORT',export)
with tempfile.TemporaryDirectory(prefix='horos-age-export-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Cocoa','-framework','CoreData','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
