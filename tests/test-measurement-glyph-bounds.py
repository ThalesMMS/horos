#!/usr/bin/env python3
"""Rasterize R251 measurement labels with production StringTexture and check ink."""
from pathlib import Path
import sys
import subprocess, sys, tempfile

# These render with OpenGL and read the pixels back, so a machine with no
# window server session has nothing to draw into. That is a missing
# prerequisite, not a defect: skip, the way the rest of the suite does.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import accelerated_opengl
accelerated_opengl.require()

root = Path(__file__).resolve().parents[1]
production = (subprocess.check_output(['git', 'show', sys.argv[1] + ':Horos/Sources/StringTexture.m'])
              if len(sys.argv) > 1 else (root / 'Horos/Sources/StringTexture.m').read_bytes()).decode('latin1')
production = production.replace('#import "N2Debug.h"',
                                'static void N2LogStackTrace(NSString *message) { NSLog(@"%@", message); }')
code = r'''
#import <Cocoa/Cocoa.h>
#import "StringTexture.h"
#include <math.h>
static BOOL inkTouchesEdge(const unsigned char *p, GLint w, GLint h, int *count, int *maxx, int *maxy) {
 *count=0; *maxx=-1; *maxy=-1;
 int minx=w, miny=h;
 for(int y=0;y<h;y++)for(int x=0;x<w;x++){
  const unsigned char *px=p+(y*w+x)*4;
  if(px[0]>8||px[1]>8||px[2]>8||px[3]>8){
   (*count)++; if(x<minx)minx=x; if(y<miny)miny=y; if(x>*maxx)*maxx=x; if(y>*maxy)*maxy=y;
  }
 }
 return *count==0 || minx==0 || miny==0 || *maxx>=w-1 || *maxy>=h-1;
}
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 NSOpenGLPixelFormatAttribute attrs[]={NSOpenGLPFAAccelerated,NSOpenGLPFAColorSize,32,NSOpenGLPFAAlphaSize,8,0};
 NSOpenGLContext *ctx=[[NSOpenGLContext alloc] initWithFormat:[[NSOpenGLPixelFormat alloc] initWithAttributes:attrs] shareContext:nil];
 if(!ctx){NSLog(@"needs accelerated OpenGL"); return 2;}
 [ctx makeCurrentContext];
 NSArray *names=@[@"Geneva",@"Helvetica",@"Courier",@"Menlo"];
 NSArray *sizes=@[@6,@12,@16,@20];
   NSArray *texts=@[@"Length: 5.298 cm",@"Length: 5.501 cm",@"Length: 2.15 cm",
                  @"Length: 1.94 cm",@"Length: 2.000 cm",@"Length: 0.50 mm "];
 int cases=0;
 for(NSString *name in names){
  if(![NSFont fontWithName:name size:12]) continue;
  for(NSNumber *size in sizes){
   NSFont *font=[NSFont fontWithName:name size:size.doubleValue];
   NSDictionary *attr=@{NSFontAttributeName:font,NSForegroundColorAttributeName:NSColor.whiteColor};
   for(NSString *text in texts){
    GLint widthAt1=0,heightAt1=0;
    for(int scale=1;scale<=2;scale++){
     StringTexture *t=[[StringTexture alloc] initWithString:text withAttributes:attr];
     [t setAntiAliasing:YES];
     GLuint tex=[t genTextureWithBackingScaleFactor:scale];
     CGLContextObj cgl_ctx=ctx.CGLContextObj;
     glBindTexture(GL_TEXTURE_RECTANGLE_EXT, tex);
     GLint w=0,h=0;
     glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_EXT,0,GL_TEXTURE_WIDTH,&w);
     glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_EXT,0,GL_TEXTURE_HEIGHT,&h);
     check(w>0 && h>0);
     check(fabs(t.texSize.width-w)<0.001 && fabs(t.texSize.height-h)<0.001);
     check(w==(GLint)(t.frameSize.width*scale) && h==(GLint)(t.frameSize.height*scale));
     NSMutableData *d=[NSMutableData dataWithLength:w*h*4];
     glGetTexImage(GL_TEXTURE_RECTANGLE_EXT,0,GL_RGBA,GL_UNSIGNED_BYTE,d.mutableBytes);
     check(glGetError()==GL_NO_ERROR);
     int count=0,maxx=-1,maxy=-1;
     if(inkTouchesEdge(d.bytes,w,h,&count,&maxx,&maxy)){
      NSLog(@"FAIL: clipped font=%@ size=%@ scale=%d text='%@' tex=%dx%d inkMax=%d,%d n=%d",
            name,size,scale,text,w,h,maxx,maxy,count); return 1;
     }
     NSSize typo=[text sizeWithAttributes:@{NSFontAttributeName:font}];
     NSSize predicted=NSMakeSize(ceil(typo.width+8),ceil(typo.height+4));
     check(t.frameSize.width>=predicted.width-0.001 && t.frameSize.height>=predicted.height-0.001);
     if(scale==1){widthAt1=w; heightAt1=h;}
     else check(w==widthAt1*2 && h==heightAt1*2);
     [t setString:text withAttributes:attr];
     tex=[t genTextureWithBackingScaleFactor:scale];
     glBindTexture(GL_TEXTURE_RECTANGLE_EXT, tex);
     glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_EXT,0,GL_TEXTURE_WIDTH,&w);
     glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_EXT,0,GL_TEXTURE_HEIGHT,&h);
     d=[NSMutableData dataWithLength:w*h*4];
     glGetTexImage(GL_TEXTURE_RECTANGLE_EXT,0,GL_RGBA,GL_UNSIGNED_BYTE,d.mutableBytes);
     if(inkTouchesEdge(d.bytes,w,h,&count,&maxx,&maxy)){
      NSLog(@"FAIL: clipped after setString font=%@ size=%@ scale=%d",name,size,scale); return 1;
     }
     [t release];
     cases++;
    }
   }
  }
 }
 check(cases>=48);
 NSLog(@"PASS: %d R251 measurement textures, fonts/sizes 6/12/16/20, 1x/2x backing, ink inside predicted StringTexture boxes", cases);
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-glyph-bounds-') as d:
    p = Path(d)
    (p / 'StringTexture.m').write_text('#import <Cocoa/Cocoa.h>\n' + production)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-deprecated-declarations',
                    '-fsanitize=undefined', '-I', str(root / 'Horos/Sources'),
                    '-framework', 'Cocoa', '-framework', 'OpenGL',
                    str(p / 'StringTexture.m'), str(p / 'test.m'), '-o', str(p / 'test')],
                   check=True)
    subprocess.run([str(p / 'test')], check=True)
