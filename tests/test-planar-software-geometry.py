#!/usr/bin/env python3
"""Execute the production tile call and vertex emitter against full coverage.

Upsampling changes texture dimensions, not the image's position or extent. Test
scalar and fixed-function callers, even/odd dimensions, and multiple tiles.
No GPU or DICOM fixture is needed for this geometry contract.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
start = source.index('static void DrawGLImageTile (')
end = source.index('\n}',start)+2
function = source[start:end]
# Replace only the Cocoa context-access precondition with a test context.
function = function.replace('CGLContextObj cgl_ctx = [[NSOpenGLContext currentContext] CGLContextObj];',
                            'void *cgl_ctx = (void *)1;').replace('cgl_ctx == nil','cgl_ctx == NULL')
start = source.index('DrawGLImageTile (GL_TRIANGLE_STRIP,',end)
end = source.index(';',start)+1
call = source[start:end].replace('self.curDCM.pwidth','imageWidth').replace('self.curDCM.pheight','imageHeight')
driver = r'''
#include <stdbool.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
typedef bool Boolean;
#define GL_TRIANGLE_STRIP 5
static double vertices[4][4], tx, ty;
static int count;
static void glBegin(unsigned long kind) { count=0; }
static void glTexCoord2f(float x,float y) { tx=x;ty=y; }
static void glVertex3d(double x,double y,double z) {
    if(count>=4) abort();
    vertices[count][0]=x;vertices[count][1]=y;
    vertices[count][2]=tx;vertices[count++][3]=ty;
}
static void glEnd(void) {}
FUNCTION
int main(void) {
    const int sizes[][2]={{32,32},{33,35},{256,256},{512,513}};
    int cases=0;
    for(int shape=0;shape<4;shape++) for(int factor=1;factor<=3;factor++)
    for(int scalar=0;scalar<2;scalar++) for(int tiled=0;tiled<2;tiled++) {
        float imageWidth=sizes[shape][0],imageHeight=sizes[shape][1],scaleValue=1.833984375f;
        long tW=imageWidth*factor,tH=imageHeight*factor;
        bool scalarDraw=scalar,zoomIsSoftwareInterpolated=factor!=1,f_ext_texture_rectangle=true;
        int maximum=tiled ? 128 : 4096;
        for(long offsetY=0;offsetY<tH;offsetY+=maximum)
        for(long offsetX=0;offsetX<tW;offsetX+=maximum) {
            long currTextureWidth=fmin(maximum,tW-offsetX),currTextureHeight=fmin(maximum,tH-offsetY);
            CALL
            // The output quad must cover exactly the source-image portion of
            // this tile and sample every uploaded texel, without cropping.
            for(int corner=0;corner<4;corner++) {
                bool right=corner&1,bottom=corner&2;
                double expectedX=((offsetX+(right?currTextureWidth:0))/(double)factor-imageWidth/2)*scaleValue;
                double expectedY=((offsetY+(bottom?currTextureHeight:0))/(double)factor-imageHeight/2)*scaleValue;
                double expectedU=right?currTextureWidth:0,expectedV=bottom?currTextureHeight:0;
                if(fabs(vertices[corner][0]-expectedX)>0.0001 || fabs(vertices[corner][1]-expectedY)>0.0001 ||
                   vertices[corner][2]!=expectedU || vertices[corner][3]!=expectedV) {
                    fprintf(stderr,"FAIL: %gx%g factor %d scalar %d tile %ld,%ld corner %d tex %.1f,%.1f expected %.1f,%.1f\n",
                        imageWidth,imageHeight,factor,scalar,offsetX,offsetY,corner,
                        vertices[corner][2],vertices[corner][3],expectedU,expectedV);
                    return 1;
                }
            }
            cases++;
        }
    }
    printf("PASS: %d actual production tile calls preserve image coverage and all uploaded texels\n",cases);
}
'''.replace('FUNCTION',function).replace('CALL',call)
with tempfile.TemporaryDirectory(prefix='horos-planar-geometry-') as directory:
    path=Path(directory)/'check.c';path.write_text(driver)
    binary=path.with_suffix('')
    subprocess.run(['xcrun','clang','-std=c11',str(path),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
