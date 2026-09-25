#!/usr/bin/env python3
"""Exercise the real native loupe crop with guarded original scalar buffers.

Compile computeMagnifyLens verbatim against small host stubs. ASan catches
reading the viewport's incompatible resampled bytes or stepping outside the
original image near an edge. No window, UI events or persistent preferences.
The companion GPU test checks the final masked fragment and discrete CLUT.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--viewer-source', type=Path, default=root/'Horos/Sources/DCMView.m')
args = parser.parse_args()
source = args.viewer_source.read_bytes().decode('latin1')
method = source.split('-(void) computeMagnifyLens:(NSPoint) p\n', 1)[1]
method = '-(void) computeMagnifyLens:(NSPoint) p\n'+method.split('\n- (void)makeTextureFromImage:', 1)[0]
driver = r'''
#import <AppKit/AppKit.h>
#import <Accelerate/Accelerate.h>
#include <assert.h>
static BOOL FULL32BITPIPELINE=NO;
@interface LensState:NSObject
@property BOOL lensIsScalar, lensIsWindowed;
- (void)markUnavailable;
@end
@implementation LensState
- (void)markUnavailable { abort(); }
@end
@interface Pixels:NSObject
@property long pwidth,pheight,stackMode;
@property BOOL isRGB,isLUT12Bit,thickSlabVRActivated,shutterEnabled;
@property double pixelRatio;
@property float *fImage,*transferFunctionPtr,*subtractedfImage;
@property char *baseAddr;
@property unsigned char *LUT12baseAddr;
- (float*)computefImage;
- (float*)computefImageForDisplay;
@end
@implementation Pixels
- (float*)computefImage { return self.fImage; }
- (float*)computefImageForDisplay { return self.fImage; }
@end
@interface View:NSResponder {
@public
    BOOL isKeyView,needToLoadTexture,colorTransfer,zoomIsSoftwareInterpolated,cursorhidden,f_ext_texture_rectangle;
    float scaleValue,lensSize,lensSizeFactor,LENSRATIO,redFactor,greenFactor,blueFactor;
    int textureWidth,textureHeight;
    char *lensTexture,*colorBuf,*resampledBaseAddr;
}
@property Pixels *curDCM;
@property LensState *horosScalarCLUTState;
- (NSWindow*)window;
- (void)loadTexturesCompute;
- (void)deleteLens;
- (void)setNeedsDisplay:(BOOL)flag;
- (void)computeMagnifyLens:(NSPoint)p;
@end
@implementation View
- (NSWindow*)window { abort(); }
- (void)loadTexturesCompute { abort(); }
- (void)deleteLens { free(lensTexture); lensTexture=NULL; self.horosScalarCLUTState.lensIsScalar=NO; }
- (void)setNeedsDisplay:(BOOL)flag {}
METHOD
@end
int main(void) { @autoreleasepool {
    [[NSUserDefaults standardUserDefaults] setVolatileDomain:@{@"magnifyingLens":@YES} forName:NSArgumentDomain];
    View *view=[View new];Pixels *pix=[Pixels new];view.curDCM=pix;view.horosScalarCLUTState=[LensState new];
    pix.pwidth=256;pix.pheight=128;pix.pixelRatio=1;
    pix.fImage=malloc(256*128*4);pix.baseAddr=malloc(256*128);
    for(int i=0;i<256*128;i++){pix.fImage[i]=2048+i%33;pix.baseAddr[i]=i%256;}
    NSData *original=[NSData dataWithBytes:pix.fImage length:256*128*4];
    view->isKeyView=YES;view->cursorhidden=YES;view->colorTransfer=YES;view->f_ext_texture_rectangle=YES;
    view->zoomIsSoftwareInterpolated=YES;view->textureWidth=768;view->textureHeight=384;
    view->redFactor=view->greenFactor=view->blueFactor=1;view->lensSizeFactor=1;view->scaleValue=3.125;
    // Guard allocations deliberately cannot hold an image: a wrong choice
    // of the old viewport colour/resampled source trips ASan immediately.
    view->colorBuf=malloc(1);view->resampledBaseAddr=malloc(1);
    int checked=0;
    NSPoint points[]={{80,80},{1,1},{255,127},{0,64},{128,0}};
    for(int windowed=0;windowed<2;windowed++) {
        pix.transferFunctionPtr=windowed ? pix.fImage : NULL;
        for(int p=0;p<5;p++) {
            [view computeMagnifyLens:points[p]];
            assert(view.horosScalarCLUTState.lensIsScalar && view.horosScalarCLUTState.lensIsWindowed==windowed);
            assert(view->LENSRATIO==1 && view->lensSize==32);
            int sx=(int)(points[p].x-16),sy=(int)(points[p].y-16);
            for(int y=0;y<32;y++)for(int x=0;x<32;x++) {
                int xx=sx+x,yy=sy+y;
                float expected=0;
                if(xx>=0&&xx<256&&yy>=0&&yy<128)
                    expected=windowed ? (unsigned char)pix.baseAddr[yy*256+xx]/255.f : pix.fImage[yy*256+xx];
                assert(((float*)view->lensTexture)[y*32+x]==expected);checked++;
            }
        }
    }
    assert([original isEqualToData:[NSData dataWithBytes:pix.fImage length:256*128*4]]);
    [view deleteLens];assert(!view.horosScalarCLUTState.lensIsScalar);
    free(view->colorBuf);free(view->resampledBaseAddr);free(pix.fImage);free(pix.baseAddr);
    printf("PASS: %d exact native loupe scalar samples; original/windowed crops, four edges, guarded buffers and source unchanged\n",checked);
}}
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-loupe-source-') as folder:
    work = Path(folder)
    (work/'Check.m').write_text(driver)
    subprocess.run(['xcrun','clang','-fobjc-arc','-O0','-g','-fsanitize=address',
                    '-Wno-deprecated-declarations',str(work/'Check.m'),'-framework','AppKit',
                    '-framework','Accelerate','-o',str(work/'check')],check=True)
    raise SystemExit(subprocess.run([str(work/'check')],timeout=30).returncode)
