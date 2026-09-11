#!/usr/bin/env python3
"""Exercise the production fusion-frame branch with real vImage and VTK import."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
path='Horos/Sources/VRView.mm'
source=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
anchor=source.index('if( blendingData != [blendingController volumePtr])')
a=anchor+re.search(r'                if\( (?:isRGB|isBlendingRGB)\)',source[anchor:]).start()
b=source.index('                blendingReader->Update();',a)+len('                blendingReader->Update();')
block=source[a:b]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#import <Cocoa/Cocoa.h>
#import <Accelerate/Accelerate.h>
#include <vtkImageImport.h>
#include <vtkImageData.h>
#include <vector>
#include <cstdio>
#include <cassert>
static int conversions;
@interface BrowserController : NSObject
+ (void)multiThreadedImageConvert:(NSString *)what :(vImage_Buffer *)src :(vImage_Buffer *)dst :(float)offset :(float)scale;
@end
@implementation BrowserController
+ (void)multiThreadedImageConvert:(NSString *)what :(vImage_Buffer *)src :(vImage_Buffer *)dst :(float)offset :(float)scale {
 assert([what isEqualToString:@"FTo16U"]);conversions++;
 assert(vImageConvert_FTo16U(src,dst,offset,scale,kvImageDoNotTile)==kvImageNoError);
}
@end
int main(){ @autoreleasepool {
 int cases=0;
 for(bool isRGB: {false,true})for(bool isBlendingRGB: {false,true}) {
  std::vector<float> scalar(24);std::vector<unsigned char> rgba(96);std::vector<unsigned short> converted(24);
  auto blendingReader=vtkImageImport::New();blendingReader->SetWholeExtent(0,3,0,2,0,1);blendingReader->SetDataExtentToWholeExtent();
  if(isBlendingRGB){blendingReader->SetDataScalarTypeToUnsignedChar();blendingReader->SetNumberOfScalarComponents(4);blendingReader->SetImportVoidPointer(rgba.data());}
  else {blendingReader->SetDataScalarTypeToUnsignedShort();blendingReader->SetNumberOfScalarComponents(1);blendingReader->SetImportVoidPointer(converted.data());}
  blendingReader->Update();
  for(int frame=0;frame<3;frame++) {
   for(int i=0;i<24;i++)scalar[i]=100+frame*200+i;
   for(int i=0;i<96;i++)rgba[i]=(17*i+31*frame)%251;
   void *blendingData=isBlendingRGB?(void*)rgba.data():(void*)scalar.data();
   void *blendingData8=converted.data();
   float blendingOFFSET16=100,blendingValueFactor=2;
   vImage_Buffer blendingSrcf={blendingData,6,4,4*sizeof(float)};
   vImage_Buffer blendingDst8={blendingData8,6,4,4*sizeof(unsigned short)};
   conversions=0;
   BLOCK
   if(conversions!=(isBlendingRGB?0:1)) {std::fprintf(stderr,"FAIL: primary RGB=%d, fusion RGB=%d used wrong conversion path\n",isRGB,isBlendingRGB);return 1;}
   for(int z=0;z<2;z++)for(int y=0;y<3;y++)for(int x=0;x<4;x++)for(int c=0;c<(isBlendingRGB?4:1);c++) {
    int i=(z*3+y)*4+x;
    double expected=isBlendingRGB?rgba[4*i+c]:(scalar[i]+100)*2;
    double actual=blendingReader->GetOutput()->GetScalarComponentAsDouble(x,y,z,c);
    if(actual!=expected){std::fprintf(stderr,"FAIL: frame %d sample %d component %d expected %g got %g\n",frame,i,c,expected,actual);return 2;}
   }
   cases++;
  }
  blendingReader->Delete();
 }
 std::printf("PASS: %d fusion-frame imports across all primary/fusion scalar-RGBA combinations preserve every component\n",cases);
}}
'''.replace('BLOCK',block)
with tempfile.TemporaryDirectory(prefix='horos-vr-fusion-') as d:
    p=Path(d);(p/'test.mm').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkIOImage','vtkDICOMParser','vtkmetaio','vtkpng','vtkjpeg','vtktiff','vtksys','vtkdoubleconversion']:
        libs+=list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-I'+str(install/'include'),str(p/'test.mm'),*[str(x) for x in libs],'-lz','-framework','Cocoa','-framework','Accelerate','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
