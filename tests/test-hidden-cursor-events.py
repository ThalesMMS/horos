#!/usr/bin/env python3
"""Exercise the production cursor gate for all four viewer mouse handlers."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
path='Horos/Sources/DCMView.m'
s=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
helper=''
if '- (BOOL) shouldIgnoreHiddenCursorEvent:' in s:
 a=s.index('- (BOOL) shouldIgnoreHiddenCursorEvent:');b=s.index('- (void)mouseUp:',a);helper=s[a:b]
handlers=[]
for i,marker in enumerate(['- (void)mouseUp:','-(void) mouseMoved:','- (void) mouseDown:','- (void)mouseDragged:']):
 a=s.index(marker);gate=next(line for line in s[a:].splitlines() if 'CGCursorIsVisible() == NO' in line or 'if( [self shouldIgnoreHiddenCursorEvent:' in line)
 handlers.append(f'-(void)handler{i}:(Event*)event {{Event*theEvent=event;{gate}\n delivered++;}}')
code=r'''
#import <Foundation/Foundation.h>
@interface Event:NSObject
@property(retain) NSObject*window;
@end
@implementation Event
@end
#define NSEvent Event
#define NSWindow NSObject
static BOOL cursorVisible;
#define CGCursorIsVisible() cursorVisible
@interface View:NSObject {
@public void*lensTexture;int delivered;
}
@property(retain) NSObject*window;
@end
@implementation View
HELPER
HANDLERS
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 for(int visible=0;visible<2;visible++)for(int lens=0;lens<2;lens++)for(int receiver=0;receiver<2;receiver++)for(int destination=0;destination<3;destination++){
  View*v=[View new];v.window=receiver?[NSObject new]:nil;
  Event*e=[Event new];e.window=destination==0?nil:(destination==1?v.window:[NSObject new]);
  cursorVisible=visible;v->lensTexture=lens?(void*)1:NULL;
  BOOL accept=visible || lens || (receiver && destination==1);
  [v handler0:e];[v handler1:e];[v handler2:e];[v handler3:e];
  check(v->delivered==(accept?4:0));
 }
 NSLog(@"PASS: down/up/move/drag, visible/hidden cursor, matching/foreign/missing windows, loupe compatibility");
}}
'''.replace('HELPER',helper).replace('HANDLERS','\n'.join(handlers))
with tempfile.TemporaryDirectory(prefix='horos-cursor-events-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
