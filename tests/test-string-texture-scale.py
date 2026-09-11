#!/usr/bin/env python3
"""Run production text drawing against deterministic context/GL peers."""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/StringTexture.m'
s = (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
     if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')
a = s.index('- (void) drawWithBounds:')
b = s.index('- (void) setString:', a)
code = r'''
#import <Cocoa/Cocoa.h>
#import <OpenGL/gl.h>
@interface TestWindow:NSObject
@property float backingScaleFactor;
@end
@implementation TestWindow
@end
@interface TestView:NSObject
@property(retain) TestWindow *window;
@end
@implementation TestView
@end
@interface TestContext:NSObject
@property(retain) TestView *view;
+(id)currentContext;
-(CGLContextObj)CGLContextObj;
@end
static TestContext *activeContext;
@implementation TestContext
+(id)currentContext{return activeContext;}
-(CGLContextObj)CGLContextObj{return (CGLContextObj)self;}
@end
static NSPoint vertices[4];static int vertexCount;
static void vertex(float x,float y){vertices[vertexCount++]=NSMakePoint(x,y);}
#define NSOpenGLContext TestContext
#define glBindTexture(...) ((void)0)
#define glBegin(...) (vertexCount=0)
#define glTexCoord2f(...) ((void)0)
#define glVertex2f vertex
#define glEnd() ((void)0)
@interface StringTexture:NSObject {
 NSMutableArray *ctxArray,*textArray; NSSize texSize;float sf;BOOL xFlipped,yFlipped;
}
@property int generations;
-(void)deleteTexture:(id)c;
-(GLuint)genTextureWithBackingScaleFactor:(float)scale;
-(void)drawWithBounds:(NSRect)bounds;
@end
@implementation StringTexture
-(id)init{if((self=[super init])){ctxArray=[NSMutableArray new];textArray=[NSMutableArray new];}return self;}
-(void)deleteTexture:(id)c{
 NSUInteger i=[ctxArray indexOfObjectIdenticalTo:c];
 if(i!=NSNotFound){[ctxArray removeObjectAtIndex:i];[textArray removeObjectAtIndex:i];}
}
-(GLuint)genTextureWithBackingScaleFactor:(float)scale{
 [self deleteTexture:activeContext];sf=scale;texSize=NSMakeSize(100*scale,20*scale);
 [ctxArray addObject:activeContext];[textArray addObject:@1];self.generations++;return 1;
}
METHODS
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 TestContext*c=[TestContext new];c.view=[TestView new];c.view.window=[TestWindow new];activeContext=c;
 StringTexture*t=[StringTexture new];
 for(NSNumber *n in @[@1,@2,@1,@2]){
  float scale=n.floatValue;c.view.window.backingScaleFactor=scale;
  [t drawAtPoint:NSMakePoint(7,11) ratio:0.5];
  check(vertexCount==4);
  check(NSEqualPoints(vertices[0],NSMakePoint(7,11)));
  check(NSEqualPoints(vertices[2],NSMakePoint(7+100*scale,11+10*scale)));
  int generations=t.generations;
  [t drawAtPoint:NSMakePoint(7,11) ratio:0.5];
  check(t.generations==generations);
  // Explicit bounds must stay caller-controlled at every scale.
  [t drawWithBounds:NSMakeRect(3,4,42,17)];
  check(NSEqualPoints(vertices[2],NSMakePoint(45,21)));
 }
 check(t.generations==4);
 TestContext*other=[TestContext new];other.view=[TestView new];other.view.window=[TestWindow new];
 other.view.window.backingScaleFactor=1;activeContext=other;
 [t drawAtPoint:NSMakePoint(0,0)];
 check(NSEqualPoints(vertices[2],NSMakePoint(100,20)));
 activeContext=c;
 [t drawAtPoint:NSMakePoint(0,0)];
 check(NSEqualPoints(vertices[2],NSMakePoint(200,40)));
 check(t.generations==6);
 NSLog(@"PASS: first-frame 1x/2x transitions, ratio, unchanged-scale cache reuse, explicit bounds");
}}
'''.replace('METHODS', s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-texture-scale-') as d:
    p = Path(d)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=undefined',
                    '-framework', 'Cocoa', str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
