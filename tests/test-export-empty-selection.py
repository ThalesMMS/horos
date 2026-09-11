#!/usr/bin/env python3
"""Execute actual export selection guards with controlled outline/matrix selection."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('- (void) exportDICOMFile: (id)sender\n{')+len('- (void) exportDICOMFile: (id)sender\n{')
prefix=s[a:s.index('    NSOpenPanel *sPanel',a)]
end=s.index('        NSMutableDictionary *d =',a)
start=s.rfind('        if( filesToExport.count == 0',a,end)
guard=s[start:end] if start!=-1 else ''
code=r'''
#import <Cocoa/Cocoa.h>
@interface Selection:NSObject { @public BOOL selected; }
- (NSArray*)selectedCells;
- (NSIndexSet*)selectedRowIndexes;
- (NSMenu*)menu;
@end
@implementation Selection
- (NSArray*)selectedCells{return selected?@[@1]:@[];}
- (NSIndexSet*)selectedRowIndexes{return selected?[NSIndexSet indexSetWithIndex:0]:[NSIndexSet indexSet];}
- (NSMenu*)menu{return nil;}
@end
@interface Peer:NSObject { @public Selection *oMatrix,*databaseOutline; id responder; int alerts,proceeded; }
- (void)run:(id)sender;
@end
@implementation Peer
- (id)window{return self;}
- (id)firstResponder{return responder;}
- (void)showEmptyDICOMExportSelection{alerts++;}
- (void)run:(id)sender {
 PREFIX
 proceeded++;
}
- (void)filtered:(NSArray*)filesToExport objects:(NSArray*)dicomFiles2Export {
 GUARD
 proceeded++;
}
@end
int main(){@autoreleasepool{
 for(int matrix=0;matrix<2;matrix++) for(int selected=0;selected<2;selected++) {
  Peer *p=[Peer new];p->oMatrix=[Selection new];p->databaseOutline=[Selection new];
  p->responder=matrix?p->oMatrix:p->databaseOutline;
  p->oMatrix->selected=matrix?selected:!selected;
  p->databaseOutline->selected=matrix?!selected:selected;
  [p run:nil];
  if(p->alerts!=!selected || p->proceeded!=selected){fprintf(stderr,"FAIL matrix %d selected %d: alerts %d proceeded %d\n",matrix,selected,p->alerts,p->proceeded);return 1;}
  [p->oMatrix release];[p->databaseOutline release];[p release];
 }
 for(int files=0;files<2;files++) for(int objects=0;objects<2;objects++) {
  Peer *p=[Peer new];[p filtered:files?@[@1]:@[] objects:objects?@[@1]:@[]];
  BOOL valid=files && objects;
  if(p->alerts!=!valid || p->proceeded!=valid){fputs("FAIL filtered selection\n",stderr);return 1;}[p release];
 }
 puts("PASS: outline/matrix guards use the active selection; filtered empty batches stop before worker creation");
}}
'''.replace('PREFIX',prefix).replace('GUARD',guard)
with tempfile.TemporaryDirectory(prefix='horos-empty-selection-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
