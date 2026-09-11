#!/usr/bin/env python3
"""Check production ROI overlay colors against calibrated RGBY/alpha and GPU blend readback."""
from pathlib import Path
import subprocess
import sys
import tempfile

# These render with OpenGL and read the pixels back, so a machine with no
# window server session has nothing to draw into. That is a missing
# prerequisite, not a defect: skip, the way the rest of the suite does.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import accelerated_opengl
accelerated_opengl.require()

root = Path(__file__).resolve().parents[1]


def source(name):
    path = 'Horos/Sources/' + name
    return (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
            if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')


def slice_between(text, start, end):
    a = text.index(start)
    return text[a:text.index(end, a)]


def slice_first(text, pairs):
    last = None
    for start, end in pairs:
        try:
            return slice_between(text, start, end)
        except ValueError as error:
            last = error
    raise last


roi = source('ROI.m')
geometry_blend = slice_first(roi, [
    ('\t\tglEnable(GL_POINT_SMOOTH);\n\t\tglEnable(GL_LINE_SMOOTH);\n\t\tglEnable(GL_POLYGON_SMOOTH);\n\t\tglEnable(GL_BLEND);\n\t\tglBlendEquation(GL_FUNC_ADD);\n\t\tglBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);',
     '\n\t\t\n\t\tswitch( type)'),
    ('\t\tglEnable(GL_POINT_SMOOTH);\n\t\tglEnable(GL_LINE_SMOOTH);\n\t\tglEnable(GL_POLYGON_SMOOTH);\n\t\tglEnable(GL_BLEND);\n\t\tglBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);',
     '\n\t\t\n\t\tswitch( type)'),
])
geometry_color = slice_between(
    roi,
    '			case t2DPoint:\n			{\n				float angle;\n				\n				glColor4f (color.red / 65535., color.green / 65535., color.blue / 65535., opacity);',
    '\n\n				glBegin(GL_LINE_LOOP);')
extrusion = source('OSIPathExtrusionROI.m')
extrusion_color = slice_first(extrusion, [
    ('    NSColor *deviceStrokeColor = [self.strokeColor colorUsingColorSpaceName:NSCalibratedRGBColorSpace];',
     '\n    \n    if (self.strokeThickness != 0 && self.strokeColor != nil) {'),
    ('    NSColor *deviceStrokeColor = [self.strokeColor colorUsingColorSpaceName:NSDeviceRGBColorSpace];',
     '\n    \n    if (self.strokeThickness != 0 && self.strokeColor != nil) {'),
])
extrusion_gl = slice_between(
    extrusion,
    '        glColor4f((float)[deviceStrokeColor redComponent], (float)[deviceStrokeColor greenComponent], (float)[deviceStrokeColor blueComponent], (float)[deviceStrokeColor alphaComponent]);',
    '\n\n        N3AffineTransformGetOpenGLMatrixd')
mask = source('OSIMaskROI.m')
mask_color = slice_first(mask, [
    ('    NSColor *deviceColor = [self.fillColor colorUsingColorSpaceName:NSCalibratedRGBColorSpace];',
     '\n    \n    double dicomToPixGLTransform[16];'),
    ('    NSColor *deviceColor = [self.fillColor colorUsingColorSpaceName:NSDeviceRGBColorSpace];',
     '\n    \n    double dicomToPixGLTransform[16];'),
])
mask_gl = slice_between(
    mask,
    '    glColor4f((float)[deviceColor redComponent], (float)[deviceColor greenComponent], (float)[deviceColor blueComponent], (float)[deviceColor alphaComponent]);',
    '\n//    glColor4f(1, 0, 1, .5);')
path = source('OSIPlanarPathROI.m')
path_color = slice_first(path, [
    ('    glLineWidth(3.0);\n    NSColor *drawColor = [self.strokeColor colorUsingColorSpaceName:NSCalibratedRGBColorSpace];',
     '\n    glBegin(GL_LINE_STRIP);'),
    ('    glLineWidth(3.0);\n    glColor3f(1, 0, 0);', '\n    glBegin(GL_LINE_STRIP);'),
])
path_mask = slice_first(path, [
    ('    NSColor *maskColor = [self.fillColor colorUsingColorSpaceName:NSCalibratedRGBColorSpace];',
     '\n    glBegin(GL_LINES);'),
    ('    glColor3f(1, 0, 1);', '\n    glBegin(GL_LINES);'),
])
brush = source('OSIPlanarBrushROI.m')
try:
    brush_setup = slice_between(
        brush,
        '    glLineWidth(3.0);\n    NSColor *drawColor = [self.fillColor colorUsingColorSpaceName:NSCalibratedRGBColorSpace];',
        '\n    \n    // let\'s try drawing some the mask')
except ValueError:
    brush_setup = '    glLineWidth(3.0);\n'
brush_gl = slice_first(brush, [
    ('    glColor4f((float)[drawColor redComponent], (float)[drawColor greenComponent], (float)[drawColor blueComponent], (float)[drawColor alphaComponent]);',
     '\n    glBegin(GL_LINES);'),
    ('    glColor3f(1, 0, 1);', '\n    glBegin(GL_LINES);'),
])
coalesced = source('OSICoalescedPlanarROI.m')
coalesced_color = slice_first(coalesced, [
    ('    glLineWidth(3.0);\n    NSColor *drawColor = [self.fillColor colorUsingColorSpaceName:NSCalibratedRGBColorSpace];',
     '\n    glBegin(GL_QUADS);'),
    ('    glLineWidth(3.0);    \n\n    glColor4f(1, 0, 0, .4);', '\n    glBegin(GL_QUADS);'),
])

code = r'''
#import <Cocoa/Cocoa.h>
#import <OpenGL/gl.h>
#import <OpenGL/glext.h>
static GLfloat captured[4], firstCaptured[4];
static int captures;
static void Cap4(GLfloat r, GLfloat g, GLfloat b, GLfloat a) {
 if(captures==0){firstCaptured[0]=r; firstCaptured[1]=g; firstCaptured[2]=b; firstCaptured[3]=a;}
 captured[0]=r; captured[1]=g; captured[2]=b; captured[3]=a; captures++;
 glColor4f(r,g,b,a);
}
static void Cap3(GLfloat r, GLfloat g, GLfloat b) { Cap4(r,g,b,1); }
#define glColor4f Cap4
#define glColor3f Cap3
@interface Peer:NSObject {@public RGBColor color; float opacity;}
@property(retain) NSColor *strokeColor;
@property(retain) NSColor *fillColor;
@property CGFloat strokeThickness;
-(void)applyGeometry;
-(void)applyExtrusion;
-(void)applyMask;
-(void)applyPath;
-(void)applyBrush;
-(void)applyCoalesced;
@end
@implementation Peer
-(void)applyGeometry { GEOMETRY_BLEND GEOMETRY_COLOR }
-(void)applyExtrusion { EXTRUSION_COLOR EXTRUSION_GL }
-(void)applyMask { MASK_COLOR MASK_GL }
-(void)applyPath { PATH_COLOR PATH_MASK }
-(void)applyBrush { BRUSH_SETUP BRUSH_GL }
-(void)applyCoalesced { COALESCED_COLOR }
@end
#undef glColor4f
#undef glColor3f
#define check(...) do {if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
static BOOL near4(const GLfloat *got, CGFloat r, CGFloat g, CGFloat b, CGFloat a) {
 return fabs(got[0]-r)<1.1/65535 && fabs(got[1]-g)<1.1/65535 && fabs(got[2]-b)<1.1/65535 && fabs(got[3]-a)<1e-5;
}
static int expect(Peer *p, SEL sel, CGFloat r, CGFloat g, CGFloat b, CGFloat a, const char *name) {
 captures=0; captured[0]=captured[1]=captured[2]=captured[3]=-1;
 [p performSelector:sel];
 if(captures<1 || !near4(firstCaptured,r,g,b,a) || !near4(captured,r,g,b,a)) {
  NSLog(@"FAIL %s: expected %.5f,%.5f,%.5f,%.5f first %.5f,%.5f,%.5f,%.5f last %.5f,%.5f,%.5f,%.5f captures=%d",
        name,r,g,b,a,firstCaptured[0],firstCaptured[1],firstCaptured[2],firstCaptured[3],captured[0],captured[1],captured[2],captured[3],captures);
  return 1;
 }
 return 0;
}
int main() {@autoreleasepool{
 [NSApplication sharedApplication];
 NSOpenGLPixelFormatAttribute attrs[]={NSOpenGLPFAAccelerated,NSOpenGLPFAColorSize,32,NSOpenGLPFAAlphaSize,8,0};
 NSOpenGLContext *context=[[NSOpenGLContext alloc] initWithFormat:[[NSOpenGLPixelFormat alloc] initWithAttributes:attrs] shareContext:nil];
 check(context!=nil); [context makeCurrentContext];
 RGBColor cases[]={{32768,32768,32768},{65535,0,0},{0,65535,0},{0,0,65535},{65535,65535,0},{12345,45678,23456}};
 float opacities[]={1.0f,0.5f};
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) for(int o=0;o<2;o++) {
  RGBColor rgb=cases[i]; float opacity=opacities[o];
  CGFloat r=rgb.red/65535.0, g=rgb.green/65535.0, b=rgb.blue/65535.0;
  NSColor *selected=[NSColor colorWithCalibratedRed:r green:g blue:b alpha:opacity];
  Peer *p=[Peer new]; p->color=rgb; p->opacity=opacity;
  p.strokeColor=selected; p.fillColor=selected; p.strokeThickness=1;
  if(expect(p,@selector(applyGeometry),r,g,b,opacity,"2D geometry")) return 1;
  if(expect(p,@selector(applyExtrusion),r,g,b,opacity,"OSI extrusion")) return 1;
  if(expect(p,@selector(applyMask),r,g,b,opacity,"OSI mask")) return 1;
  if(expect(p,@selector(applyPath),r,g,b,opacity,"OSI path")) return 1;
  if(expect(p,@selector(applyBrush),r,g,b,opacity,"OSI brush")) return 1;
  if(expect(p,@selector(applyCoalesced),r,g,b,opacity,"OSI coalesced")) return 1;
  [p release];
 }
 GLuint fbo=0, tex=0, depth=0;
 glGenFramebuffersEXT(1,&fbo); glGenTextures(1,&tex); glGenRenderbuffersEXT(1,&depth);
 glBindTexture(GL_TEXTURE_2D,tex);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,32,16,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
 glBindFramebufferEXT(GL_FRAMEBUFFER_EXT,fbo);
 glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT0_EXT,GL_TEXTURE_2D,tex,0);
 glBindRenderbufferEXT(GL_RENDERBUFFER_EXT,depth);
 glRenderbufferStorageEXT(GL_RENDERBUFFER_EXT,GL_DEPTH_COMPONENT16,32,16);
 glFramebufferRenderbufferEXT(GL_FRAMEBUFFER_EXT,GL_DEPTH_ATTACHMENT_EXT,GL_RENDERBUFFER_EXT,depth);
 check(glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT)==GL_FRAMEBUFFER_COMPLETE_EXT);
 glViewport(0,0,32,16);
 glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0,32,0,16,-1,1);
 glMatrixMode(GL_MODELVIEW); glLoadIdentity();
 glDisable(GL_TEXTURE_2D); glDisable(GL_TEXTURE_RECTANGLE_EXT);
 const int dest=64;
 for(unsigned i=0;i<5;i++) for(int o=0;o<2;o++) {
  RGBColor rgb=cases[i]; float opacity=opacities[o];
  Peer *p=[Peer new]; p->color=rgb; p->opacity=opacity;
  glBlendEquation(GL_FUNC_REVERSE_SUBTRACT);
  glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
  glColor4f(0,1,0,1);
  glClearColor(dest/255.0, dest/255.0, dest/255.0, 1);
  glClear(GL_COLOR_BUFFER_BIT);
  [p applyGeometry];
  glBegin(GL_QUADS);
  glVertex2f(8,4); glVertex2f(24,4); glVertex2f(24,12); glVertex2f(8,12);
  glEnd();
  unsigned char pixel[4]={0,0,0,0};
  glReadPixels(16,8,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
  check(glGetError()==GL_NO_ERROR);
  int expected[3];
  expected[0]=(int)lrint(rgb.red/65535.0*opacity*255 + dest*(1-opacity));
  expected[1]=(int)lrint(rgb.green/65535.0*opacity*255 + dest*(1-opacity));
  expected[2]=(int)lrint(rgb.blue/65535.0*opacity*255 + dest*(1-opacity));
  for(int c=0;c<3;c++) if(abs(pixel[c]-expected[c])>1) {
   NSLog(@"FAIL GPU %u opacity %.1f channel %d expected %d actual %d",i,opacity,c,expected[c],pixel[c]);
   return 1;
  }
  [p release];
 }
 glDeleteFramebuffersEXT(1,&fbo); glDeleteTextures(1,&tex); glDeleteRenderbuffersEXT(1,&depth);
 NSLog(@"PASS: overlay draw colors match calibrated RGBY/midgray/mixed at opacity 1 and 0.5; 2D geometry readback isolates inherited blend");
}}
'''
for key, value in {
    'GEOMETRY_BLEND': geometry_blend,
    'GEOMETRY_COLOR': geometry_color.replace('			case t2DPoint:\n			{\n				float angle;\n				\n				', ''),
    'EXTRUSION_COLOR': extrusion_color,
    'EXTRUSION_GL': extrusion_gl,
    'MASK_COLOR': mask_color,
    'MASK_GL': mask_gl,
    'PATH_COLOR': path_color,
    'PATH_MASK': path_mask,
    'BRUSH_SETUP': brush_setup,
    'BRUSH_GL': brush_gl,
    'COALESCED_COLOR': coalesced_color,
}.items():
    code = code.replace(key, value)

with tempfile.TemporaryDirectory(prefix='horos-roi-draw-color-') as d:
    p = Path(d)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-deprecated-declarations',
                    '-fsanitize=undefined', '-framework', 'Cocoa', '-framework', 'OpenGL',
                    str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
