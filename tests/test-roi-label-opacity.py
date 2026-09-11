#!/usr/bin/env python3
"""Check that a ROI's text label is painted at the ROI's opacity.

Case R254 covers a colour or opacity change that has no effect. The geometry
of a ROI is drawn with `glColor4f(colour…, opacity)` at every site, but the
label that names it and carries its measurement is drawn by `-[ROI glStr::::]`,
which took its colour from the ROI and its alpha from a literal. A ROI at half
opacity therefore faded except for its text, which is the reported symptom.

`drawTextualData` composites the label with `glBlendFunc(GL_ONE,
GL_ONE_MINUS_SRC_ALPHA)` over a premultiplied StringTexture bitmap, so the
colour has to carry the opacity as well as the alpha channel: an alpha alone
leaves the source at full strength and only lightens what is behind it, which
comes out brighter than the opaque label rather than fainter.

This compiles the shipped body of `glStr` against a peer that records every
colour it emits, and requires the shadow pass and the text pass to be the
premultiplied form of the ROI's colour at its opacity. Compare
`tests/test-roi-draw-color.py`, which covers the geometry and the blend itself.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accelerated_opengl
accelerated_opengl.require()

root = Path(__file__).resolve().parents[1]


def source(name):
    path = 'Horos/Sources/' + name
    return (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
            if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')


roi = source('ROI.m')
start = roi.index('- (void) glStr: (NSString*) str :(float) x :(float) y :(float) line')
body = roi[roi.index('{', start) + 1:roi.index('\n}\n', start)]
# The peer supplies the view, the texture and the font metrics; the colour
# calls are the subject.
for unwanted in ('CGLContextObj cgl_ctx = [[NSOpenGLContext currentContext] CGLContextObj];',
                 'if( cgl_ctx == nil)\n        return;'):
    body = body.replace(unwanted, '')

code = r'''
#import <Cocoa/Cocoa.h>
#import <OpenGL/gl.h>
#import <OpenGL/glext.h>
typedef struct { unsigned short red, green, blue; } RGBColorProbe;
static GLfloat emitted[8][4];
static int emissions;
static void Cap4(GLfloat r, GLfloat g, GLfloat b, GLfloat a) {
 if(emissions < 8) { emitted[emissions][0]=r; emitted[emissions][1]=g; emitted[emissions][2]=b; emitted[emissions][3]=a; }
 emissions++;
}
#define glColor4f Cap4
#define glEnable(x) ((void)0)
#define glDisable(x) ((void)0)
@interface StringTexture:NSObject
@end
@implementation StringTexture
- (NSSize) texSize { return NSMakeSize( 40, 12); }
- (void) drawAtPoint:(NSPoint)p { (void)p; }
@end
@interface FakeWindow:NSObject
@property CGFloat backingScaleFactor;
@end
@implementation FakeWindow
@end
@interface FakeView:NSObject
@property(retain) FakeWindow *window;
@end
@implementation FakeView
@end
// The ivar names are the ones the body reads.
@interface Peer:NSObject {@public RGBColorProbe color; float opacity; float fontHeight; FakeView *curView;}
- (StringTexture*) stringTextureForString:(NSString*)s;
- (void) glStr: (NSString*) str :(float) x :(float) y :(float) line;
@end
@implementation Peer
- (StringTexture*) stringTextureForString:(NSString*)s { (void)s; return [[[StringTexture alloc] init] autorelease]; }
- (void) glStr: (NSString*) str :(float) x :(float) y :(float) line
GLSTR_BODY
@end
int main() {@autoreleasepool{
 Peer *p = [[Peer alloc] init];
 p->fontHeight = 12;
 FakeWindow *window = [[FakeWindow alloc] init];
 window.backingScaleFactor = 2;
 FakeView *view = [[FakeView alloc] init];
 view.window = window;
 p->curView = view;
 const unsigned short cases[][3] = {{65535,0,0},{0,65535,0},{0,0,65535},{65535,65535,0},{32768,32768,32768}};
 const float opacities[] = {1.0f, 0.5f, 0.25f, 0.0f};
 int failures = 0;
 for( unsigned c = 0; c < sizeof(cases)/sizeof(cases[0]); c++)
  for( unsigned o = 0; o < sizeof(opacities)/sizeof(opacities[0]); o++) {
   p->color.red = cases[c][0]; p->color.green = cases[c][1]; p->color.blue = cases[c][2];
   p->opacity = opacities[o];
   emissions = 0;
   [p glStr: @"Area: 1.440 cm2" :10 :20 :0];
   if( emissions != 2) {
    NSLog(@"FAIL: %d colour calls, expected a shadow and a text pass", emissions);
    return 1;
   }
   // The label is composited premultiplied, so the colour carries the opacity
   // as well as the alpha. Premultiplied black is black.
   const float a = opacities[o];
   const GLfloat wanted[2][4] = {
    {0, 0, 0, a},
    {a * cases[c][0]/65535.f, a * cases[c][1]/65535.f, a * cases[c][2]/65535.f, a}};
   const char *pass[2] = {"shadow", "text"};
   for( int which = 0; which < 2; which++)
    for( int channel = 0; channel < 4; channel++)
     if( fabsf( emitted[which][channel] - wanted[which][channel]) > 1e-6f) {
      NSLog(@"FAIL %s pass, colour %u opacity %.2f: channel %d is %.5f, expected %.5f",
            pass[which], c, opacities[o], channel, emitted[which][channel], wanted[which][channel]);
      failures++;
     }
  }
 if( failures) { NSLog(@"FAIL: %d wrong channels", failures); return 1; }
 NSLog(@"PASS: ROI label shadow and text carry the ROI opacity across five colours and four opacities");
}}
'''.replace('GLSTR_BODY', '{' + body + '}')

with tempfile.TemporaryDirectory(prefix='horos-roi-label-opacity-') as name:
    directory = Path(name)
    (directory / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-deprecated-declarations',
                    '-Wno-objc-method-access', '-framework', 'Cocoa', '-framework', 'OpenGL',
                    str(directory / 'test.m'), '-o', str(directory / 'test')], check=True)
    subprocess.run([str(directory / 'test')], check=True)
