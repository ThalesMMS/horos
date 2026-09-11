#!/usr/bin/env python3
"""Exercise production intersection/conversion methods with known physical planes."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
def source(name):
    path = 'Horos/Sources/' + name
    return (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
            if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')

def block(text, start):
    a = text.index(start)
    opening = text.index('{', a)
    depth = 1
    i = opening + 1
    while depth:
        depth += (text[i] == '{') - (text[i] == '}')
        i += 1
    return text[a:i]

view = source('DCMView.m')
pix = source('DCMPix.m')
code = r'''
#import <Foundation/Foundation.h>
#include <math.h>
#include <string.h>
#define SMALL_NUM 0.00000001
#define DOT(a,b) (a[0]*b[0]+a[1]*b[1]+a[2]*b[2])
INTERSECTION
@interface DCMPix : NSObject {
@public float orientation[9], originX, originY, originZ, pixelSpacingX, pixelSpacingY;
}
@property(readonly) float pixelSpacingX, pixelSpacingY;
@property(readonly) int pwidth, pheight;
@end
@implementation DCMPix
-(float)pixelSpacingX{return pixelSpacingX;}
-(float)pixelSpacingY{return pixelSpacingY;}
-(int)pwidth{return 32;}
-(int)pheight{return 32;}
PIX_TO_DICOM
DICOM_TO_SLICE
@end
@interface DCMView : NSObject
@property(retain) DCMPix *curDCM;
@end
@implementation DCMView
SLICE_INTERSECTION
@end
static void rotate(float *v, float angle) {
    // Rotate about a non-axis-aligned unit vector (1,1,1)/sqrt(3).
    float c=cosf(angle), s=sinf(angle), q=(1-c)*(v[0]+v[1]+v[2])/3;
    float r[3]={c*v[0]+s*(v[2]-v[1])/sqrtf(3)+q,
                c*v[1]+s*(v[0]-v[2])/sqrtf(3)+q,
                c*v[2]+s*(v[1]-v[0])/sqrtf(3)+q};
    memcpy(v,r,sizeof(r));
}
static DCMPix *makePix(int axis, float angle, float position) {
    DCMPix *p=[DCMPix new];
    float bases[3][9]={{1,0,0,0,1,0,0,0,1}, {0,1,0,0,0,1,1,0,0}, {1,0,0,0,0,1,0,-1,0}};
    memcpy(p->orientation,bases[axis],sizeof(p->orientation));
    for(int i=0;i<9;i+=3)rotate(p->orientation+i,angle);
    p->originX=position*p->orientation[6];
    p->originY=position*p->orientation[7];
    p->originZ=position*p->orientation[8];
    p->pixelSpacingX=0.7;p->pixelSpacingY=1.3;
    return p;
}
#define check(...) do {if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
    DCMView *v=[DCMView new];
    for(int a=0;a<3;a++)for(int b=0;b<3;b++)if(a!=b)
    for(int rot=0;rot<3;rot++) {
        float angle=rot*0.37;
        DCMPix *src=makePix(a,angle,0), *dst=makePix(b,angle,0);
        v.curDCM=dst;
        float origin[3]={dst->originX,dst->originY,dst->originZ}, original[3];
        memcpy(original,origin,sizeof(origin));
        float previous[2][3];
        for(int repeat=0;repeat<4;repeat++) {
            float line[2][3];
            [v computeSliceIntersection:src sliceFromTo:line vector:dst->orientation origin:origin];
            for(int end=0;end<2;end++) {
                check(isfinite(line[end][0]) && isfinite(line[end][1]));
                check(fabsf(line[end][2])<1e-4); // Must lie on the actual target plane.
                float physical[3];
                [dst convertPixX:line[end][0]/dst.pixelSpacingX pixY:line[end][1]/dst.pixelSpacingY toDICOMCoords:physical pixelCenter:YES];
                check(fabsf(DOT(physical,(src->orientation+6)))<1e-4);
            }
            check(memcmp(origin,original,sizeof(origin))==0);
            if(repeat)for(int i=0;i<2;i++)for(int j=0;j<3;j++)check(fabsf(line[i][j]-previous[i][j])<1e-4);
            memcpy(previous,line,sizeof(line));
        }
    }
    // Known fixture: sagittal x=8 projects to axial column center 8.5 mm.
    DCMPix *src=makePix(1,0,8), *dst=makePix(0,0,0);v.curDCM=dst;
    src->pixelSpacingX=src->pixelSpacingY=dst->pixelSpacingX=dst->pixelSpacingY=1;
    float origin[3]={0,0,0}, line[2][3];
    [v computeSliceIntersection:src sliceFromTo:line vector:dst->orientation origin:origin];
    check(fabsf(line[0][0]-8.5f)<1e-5 && fabsf(line[1][0]-8.5f)<1e-5);
    NSLog(@"PASS: orthogonal/oblique planes, anisotropic spacing, repeat stability and pixel-center convention");
}}
'''
for key, value in {
    'INTERSECTION': block(view, 'int intersect3D_SegmentPlane('),
    'PIX_TO_DICOM': block(pix, '-(void) convertPixX: (float) x pixY: (float) y toDICOMCoords: (float*) d pixelCenter:'),
    'DICOM_TO_SLICE': block(pix, '-(void) convertDICOMCoords: (float*) dc toSliceCoords: (float*) sc pixelCenter:'),
    'SLICE_INTERSECTION': block(view, '- (void) computeSliceIntersection:'),
}.items():
    code = code.replace('\n' + key + '\n', '\n' + value + '\n')
with tempfile.TemporaryDirectory(prefix='horos-cross-reference-') as directory:
    path=Path(directory)
    (path/'test.m').write_text(code)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Foundation',str(path/'test.m'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
