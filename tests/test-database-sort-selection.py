#!/usr/bin/env python3
"""Execute the production sort callback and preserve the restored selection."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
start = source.index('- (void)outlineView:(NSOutlineView *)outlineView sortDescriptorsDidChange:')
method = source[start:source.index('-(NSString*)outlineView:', start)]
code = r'''
#import <Cocoa/Cocoa.h>
@interface Outline : NSObject
@property NSInteger selectedRow;
@property NSInteger scrolledRow;
- (NSArray*)sortDescriptors;
- (void)selectRowIndexes:(NSIndexSet*)indexes byExtendingSelection:(BOOL)extend;
- (void)scrollRowToVisible:(NSInteger)row;
@end
@implementation Outline
@synthesize selectedRow,scrolledRow;
- (NSArray*)sortDescriptors {return @[[NSSortDescriptor sortDescriptorWithKey:@"date" ascending:NO]];}
- (void)selectRowIndexes:(NSIndexSet*)indexes byExtendingSelection:(BOOL)extend {self.selectedRow=indexes.firstIndex;}
- (void)scrollRowToVisible:(NSInteger)row {NSCAssert(row>=0,@"Invalid scroll row");self.scrolledRow=row;}
@end
@interface Browser : NSObject { @public Outline *databaseOutline; NSInteger restoredRow; }
- (void)outlineViewRefresh;
@end
@implementation Browser
- (void)outlineViewRefresh {databaseOutline.selectedRow=restoredRow;}
METHOD
@end
int main(void) { @autoreleasepool {
 Browser *browser=[Browser new];browser->databaseOutline=[Outline new];browser->restoredRow=7;
 [browser outlineView:nil sortDescriptorsDidChange:@[]];
 NSCAssert(browser->databaseOutline.selectedRow==7,@"Sort replaced the restored selected item with the first row");
 NSCAssert(browser->databaseOutline.scrolledRow==7,@"Selected item must remain visible");
 browser->restoredRow=-1;browser->databaseOutline.scrolledRow=99;
 [browser outlineView:nil sortDescriptorsDidChange:@[]];
 NSCAssert(browser->databaseOutline.selectedRow==-1,@"Empty selection must remain empty");
 NSCAssert(browser->databaseOutline.scrolledRow==99,@"Empty selection must not scroll");
 NSLog(@"PASS: sorting preserves restored item and handles empty selection");
}}
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-sort-') as tmp:
    path = Path(tmp)
    (path / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-framework', 'Cocoa', str(path/'test.m'), '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
