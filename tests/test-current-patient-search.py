#!/usr/bin/env python3
"""Run the production patient command with prior search modes and both row types."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
start = source.index('- (IBAction)searchForCurrentPatient:')
method = source[start:source.index('- (void)setFilterPredicate:', start)]
code = r'''
#import <Foundation/Foundation.h>
#import <CoreData/CoreData.h>
@interface SearchFixture : NSObject
@property NSInteger tag;
- (id)cell;
- (id)searchMenuTemplate;
- (id)itemWithTag:(NSInteger)tag;
@end
@implementation SearchFixture
@synthesize tag;
- (id)cell { return self; }
- (id)searchMenuTemplate { return self; }
- (id)itemWithTag:(NSInteger)value { self.tag=value; return self; }
@end
@interface OutlineFixture : NSObject
@property NSInteger selectedRow;
@property(retain) id object;
- (id)itemAtRow:(NSInteger)row;
@end
@implementation OutlineFixture
@synthesize selectedRow,object;
- (id)itemAtRow:(NSInteger)row { return self.object; }
@end
@interface BrowserFixture:NSObject {
 @public OutlineFixture *databaseOutline; SearchFixture *searchField;
 NSInteger searchType; NSString *query;
}
- (void)setSearchType:(id)sender;
- (void)setSearchString:(NSString*)value;
@end
@implementation BrowserFixture
- (void)setSearchType:(id)sender {searchType=[sender tag];[self setSearchString:nil];databaseOutline.selectedRow=-1;}
- (void)setSearchString:(NSString*)value {[query release];query=[value copy];}
METHOD
@end
int main(void) { @autoreleasepool {
 BrowserFixture *browser=[BrowserFixture new];
 browser->databaseOutline=[OutlineFixture new];browser->searchField=[SearchFixture new];
 for (NSNumber *mode in @[@0,@1,@4,@11]) {
  for (NSDictionary *row in @[@{@"type":@"Study",@"name":@"QA Patient"},@{@"type":@"Series",@"study":@{@"name":@"QA Patient"}}]) {
   browser->searchType=mode.integerValue;browser->databaseOutline.selectedRow=0;browser->databaseOutline.object=row;
   [browser searchForCurrentPatient:nil];
   NSCAssert(browser->searchType==0,@"Patient name must not be searched as an ID or description");
   NSCAssert([browser->query isEqualToString:@"QA Patient"],@"Keep selected patient's name across the field change");
  }
 }
 browser->searchType=4;[browser setSearchString:@"original"];browser->databaseOutline.selectedRow=-1;
 [browser searchForCurrentPatient:nil];NSCAssert(browser->searchType==4 && [browser->query isEqualToString:@"original"],@"No selection must not clear unrelated search");
 NSLog(@"PASS: patient command selects name mode for study/series and preserves no-selection search");
} }
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-patient-search-') as tmp:
    path = Path(tmp)
    (path / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-framework', 'Foundation', '-framework', 'CoreData', str(path / 'test.m'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
