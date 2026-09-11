#!/usr/bin/env python3
"""Exercise the complete StringTexture class in two independent GL contexts."""
from pathlib import Path
import sys
import subprocess, tempfile

# These render with OpenGL and read the pixels back, so a machine with no
# window server session has nothing to draw into. That is a missing
# prerequisite, not a defect: skip, the way the rest of the suite does.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import accelerated_opengl
accelerated_opengl.require()
root=Path(__file__).resolve().parents[1]
production=(root/'Horos/Sources/StringTexture.m').read_bytes().decode('latin1')
# Replace only the external diagnostic dependency; retain all renderer methods.
production=production.replace('#import "N2Debug.h"','static void N2LogStackTrace(NSString *message) { NSLog(@"%@",message); }')
code=r'''
#import <Cocoa/Cocoa.h>
#import "StringTexture.h"
static NSData *pixels(GLuint texture){
 CGLContextObj cgl_ctx=[NSOpenGLContext currentContext].CGLContextObj;
 glBindTexture(GL_TEXTURE_RECTANGLE_EXT,texture);GLint w=0,h=0;
 glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_EXT,0,GL_TEXTURE_WIDTH,&w);
 glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_EXT,0,GL_TEXTURE_HEIGHT,&h);
 if(w<=0||h<=0)return nil;
 NSMutableData*d=[NSMutableData dataWithLength:w*h*4];
 glGetTexImage(GL_TEXTURE_RECTANGLE_EXT,0,GL_RGBA,GL_UNSIGNED_BYTE,d.mutableBytes);
 return glGetError()==GL_NO_ERROR?d:nil;
}
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 NSOpenGLPixelFormatAttribute attrs[]={NSOpenGLPFAAccelerated,NSOpenGLPFAColorSize,32,NSOpenGLPFAAlphaSize,8,0};
 NSOpenGLPixelFormat*format=[[NSOpenGLPixelFormat alloc]initWithAttributes:attrs];
 NSOpenGLContext*a=[[NSOpenGLContext alloc]initWithFormat:format shareContext:nil];
 NSOpenGLContext*b=[[NSOpenGLContext alloc]initWithFormat:format shareContext:nil];check(a&&b);
 for(int scale=1;scale<=2;scale++){
  StringTexture*t=[[StringTexture alloc]initWithString:@"QA Texture 012345" withAttributes:@{NSFontAttributeName:[NSFont systemFontOfSize:16],NSForegroundColorAttributeName:NSColor.whiteColor}];
  [a makeCurrentContext];GLuint ta=[t genTextureWithBackingScaleFactor:scale];NSData*pa=[pixels(ta) copy];check(pa);
  [b makeCurrentContext];GLuint tb=[t genTextureWithBackingScaleFactor:scale];NSData*pb=[pixels(tb) copy];check(pb);
  for(int iteration=0;iteration<12;iteration++){
   @autoreleasepool{
    [b makeCurrentContext];tb=[t genTextureWithBackingScaleFactor:scale];check([pixels(tb) isEqual:pb]);
    [a makeCurrentContext];check([pixels(ta) isEqual:pa]);
    ta=[t genTextureWithBackingScaleFactor:scale];check([pixels(ta) isEqual:pa]);
    [b makeCurrentContext];check([pixels(tb) isEqual:pb]);
   }
  }
  [t release];
  [a makeCurrentContext];CGLContextObj cgl_ctx=a.CGLContextObj;check(!glIsTexture(ta));
  [b makeCurrentContext];cgl_ctx=b.CGLContextObj;check(!glIsTexture(tb));
  [pa release];[pb release];
 }
 NSLog(@"PASS: complete renderer, two independent contexts, alternating bitmap replacement at 1x/2x, stable texture pixels and cleanup");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-texture-contexts-') as d:
 p=Path(d);(p/'StringTexture.m').write_text('#import <Cocoa/Cocoa.h>\n'+production);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-Wno-deprecated-declarations','-fsanitize=undefined','-I',str(root/'Horos/Sources'),'-framework','Cocoa','-framework','OpenGL',str(p/'StringTexture.m'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
