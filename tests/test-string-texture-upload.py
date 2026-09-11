#!/usr/bin/env python3
"""Exercise actual StringTexture normalization/upload with GPU readback."""
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
source = (subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/StringTexture.m']) if len(sys.argv)>1 else (root/'Horos/Sources/StringTexture.m').read_bytes()).decode('latin1')
if 'static NSBitmapImageRep *TextureUploadBitmap' in source:
 helper=source[source.index('static NSBitmapImageRep *TextureUploadBitmap'):source.index('@implementation StringTexture')]
else:
 helper='static NSBitmapImageRep *TextureUploadBitmap(NSBitmapImageRep *source){return source;}'
a=source.index('            GLenum format = ([bitmap samplesPerPixel]')
b=source.index('            [ctxArray addObject:',a)
upload=source[a:b]
code=r'''
#import <Cocoa/Cocoa.h>
#import <OpenGL/gl.h>
static GLboolean borrowedPixels;
static void ObservedTexImage2D(GLenum target, GLint level, GLint internalFormat, GLsizei width, GLsizei height, GLint border, GLenum format, GLenum type, const GLvoid *pixels) {
 glGetBooleanv(GL_UNPACK_CLIENT_STORAGE_APPLE,&borrowedPixels);
 glTexImage2D(target,level,internalFormat,width,height,border,format,type,pixels);
}
#define glTexImage2D ObservedTexImage2D
HELPER
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 NSOpenGLPixelFormatAttribute attrs[]={NSOpenGLPFAAccelerated,NSOpenGLPFAColorSize,32,NSOpenGLPFAAlphaSize,8,0};
 NSOpenGLContext *context=[[NSOpenGLContext alloc]initWithFormat:[[NSOpenGLPixelFormat alloc]initWithAttributes:attrs] shareContext:nil];
 check(context!=nil);[context makeCurrentContext];
 const int colors[5][3]={{1,0,0},{0,1,0},{0,0,1},{1,1,0},{1,1,1}};
 for(int kind=0;kind<5;kind++)for(int scale=1;scale<=2;scale++){
  int bits=kind==1||kind==2?16:8;
  NSBitmapFormat flags=kind==2?NSFloatingPointSamplesBitmapFormat:(kind==3?NSAlphaFirstBitmapFormat:(kind==4?NSAlphaNonpremultipliedBitmapFormat:0));
  int w=5*scale,h=3*scale;
  NSBitmapImageRep *input=[[NSBitmapImageRep alloc]initWithBitmapDataPlanes:NULL pixelsWide:w pixelsHigh:h bitsPerSample:bits samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSCalibratedRGBColorSpace bitmapFormat:flags bytesPerRow:w*4*(bits/8)+16 bitsPerPixel:4*bits];
  check(input!=nil);memset(input.bitmapData,0,input.bytesPerRow*h);input.size=NSMakeSize(5,3);
  for(int y=0;y<h;y++)for(int x=0;x<w;x++){
   double alpha=y/scale==0?1:(y/scale==1?0.5:0);
   double components[4]={colors[x/scale][0]*(kind==4?1:alpha),colors[x/scale][1]*(kind==4?1:alpha),colors[x/scale][2]*(kind==4?1:alpha),alpha};
   unsigned char*p=input.bitmapData+y*input.bytesPerRow+x*4*(bits/8);
   for(int c=0;c<4;c++){
    double v=components[kind==3?(c==0?3:c-1):c];
    if(kind==2)((uint16_t*)p)[c]=v==1?0x3c00:(v==0.5?0x3800:0);
    else if(bits==16)((uint16_t*)p)[c]=(uint16_t)lrint(v*65535);
    else p[c]=(unsigned char)lrint(v*255);
   }
  }
  NSBitmapImageRep *bitmap=TextureUploadBitmap(input);check(bitmap!=nil);
  if(kind==0)check(bitmap==input); // already canonical: no pixel conversion
  check(NSEqualSizes(bitmap.size,input.size));
  // Simulate a prior renderer/plugin leaving non-default unpack state.
  GLuint unpackBuffer=0;glGenBuffers(1,&unpackBuffer);glBindBuffer(GL_PIXEL_UNPACK_BUFFER,unpackBuffer);
  glBufferData(GL_PIXEL_UNPACK_BUFFER,1024,NULL,GL_STATIC_DRAW);
  const GLenum unpackNames[]={GL_UNPACK_ALIGNMENT,GL_UNPACK_ROW_LENGTH,GL_UNPACK_SKIP_ROWS,GL_UNPACK_SKIP_PIXELS,GL_UNPACK_SWAP_BYTES,GL_UNPACK_LSB_FIRST,GL_UNPACK_CLIENT_STORAGE_APPLE};
  const GLint unpackValues[]={8,17,1,2,GL_TRUE,GL_TRUE,0};
  for(int i=0;i<7;i++)glPixelStorei(unpackNames[i],unpackValues[i]);
  NSSize texSize;float backingScaleFactor=scale;GLuint texName=0;
UPLOAD
  check(glGetError()==GL_NO_ERROR);
  // StringTexture replaces its one bitmap while textures in other contexts live.
  // Stop before mutation if the driver is allowed to retain this client memory.
  check(borrowedPixels==GL_FALSE);
  memset(bitmap.bitmapData,0,bitmap.bytesPerRow*bitmap.pixelsHigh);
  for(int i=0;i<7;i++){GLint value;glGetIntegerv(unpackNames[i],&value);check(value==unpackValues[i]);}
  GLint restoredBuffer=0;glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING,&restoredBuffer);check(restoredBuffer==unpackBuffer);
  glBindBuffer(GL_PIXEL_UNPACK_BUFFER,0);glDeleteBuffers(1,&unpackBuffer);
  unsigned char*out=calloc(w*h,4);glGetTexImage(GL_TEXTURE_RECTANGLE_EXT,0,GL_RGBA,GL_UNSIGNED_BYTE,out);
  check(glGetError()==GL_NO_ERROR);check(texSize.width==w&&texSize.height==h);
  for(int y=0;y<h;y++)for(int x=0;x<w;x++)for(int c=0;c<4;c++){
   double alpha=y/scale==0?1:(y/scale==1?0.5:0);
   int expected=(int)lrint((c==3?1:colors[x/scale][c])*alpha*255);
   int actual=out[(y*w+x)*4+c];
   if(abs(actual-expected)>1){NSLog(@"kind=%d scale=%d pixel=%d,%d channel=%d expected=%d actual=%d",kind,scale,x,y,c,expected,actual);return 1;}
  }
  free(out);glDeleteTextures(1,&texName);[input release];
 }
 NSLog(@"PASS: real GPU RGBA readback, canonical8/unsigned16/half16/alpha-first/straight-alpha, RGBYW, opaque/half/transparent, padded rows, 1x/2x and isolated/restored unpack state and independent texture storage");
}}
'''.replace('HELPER',helper).replace('UPLOAD','{\n'+upload+'\n}')
with tempfile.TemporaryDirectory(prefix='horos-texture-upload-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-Wno-deprecated-declarations','-fsanitize=undefined','-framework','Cocoa','-framework','OpenGL',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
