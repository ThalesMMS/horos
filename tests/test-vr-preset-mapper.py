#!/usr/bin/env python3
"""Verify real VTK mapper isolation and shared input for preset previews."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
def read(path):
    return (subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
s=read('Horos/Sources/VRPresetPreview.mm')
if '- (void)setMapper:' not in s:s=read('Horos/Sources/VRView.mm')
a=s.index('- (void)setMapper:');b=s.index('\n- (',a+1)
method=s[a:b]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#import <Cocoa/Cocoa.h>
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingVolumeOpenGL2);
#include "vtkHorosFixedPointVolumeRayCastMapper.h"
#include <vtkVolume.h>
#include <vtkImageData.h>
#include <vtkTrivialProducer.h>
#include <vtkWeakPointer.h>
#include <cassert>
@interface Preview:NSObject { @public vtkHorosFixedPointVolumeRayCastMapper *volumeMapper; vtkVolume *volume; }
- (void)setMapper:(vtkVolumeMapper*)source;
@end
@implementation Preview
METHOD
@end
int main(){@autoreleasepool {
 auto image=vtkImageData::New();image->SetDimensions(4,4,4);image->AllocateScalars(VTK_UNSIGNED_SHORT,1);
 auto input=vtkTrivialProducer::New();input->SetOutput(image);image->Delete();
 auto main=vtkHorosFixedPointVolumeRayCastMapper::New();main->SetInputConnection(input->GetOutputPort());main->SetSampleDistance(.7);main->SetMinimumImageSampleDistance(1.2);main->SetMaximumImageSampleDistance(2.4);main->SetAutoAdjustSampleDistances(0);main->SetBlendModeToMaximumIntensity();
 for(int i=0;i<20;i++){
  Preview *a=[Preview new],*b=[Preview new];a->volume=vtkVolume::New();b->volume=vtkVolume::New();
  [a setMapper:main];[b setMapper:main];
  if(a->volumeMapper==main || b->volumeMapper==main || a->volumeMapper==b->volumeMapper){fprintf(stderr,"FAIL: preview shares context-owned mapper\n");return 1;}
  assert(a->volumeMapper->GetInputConnection(0,0)==main->GetInputConnection(0,0));
  assert(a->volumeMapper->GetBlendMode()==main->GetBlendMode());
  assert(a->volumeMapper->GetSampleDistance()==main->GetSampleDistance());
  assert(a->volumeMapper->GetMinimumImageSampleDistance()==main->GetMinimumImageSampleDistance());
  assert(a->volumeMapper->GetMaximumImageSampleDistance()==main->GetMaximumImageSampleDistance());
  assert(a->volumeMapper->GetAutoAdjustSampleDistances()==0);
  a->volumeMapper->SetBlendModeToComposite();assert(b->volumeMapper->GetBlendMode()==main->GetBlendMode());
  vtkWeakPointer<vtkVolumeMapper> previous=a->volumeMapper;
  [a setMapper:main];assert(previous==nullptr);assert(a->volume->GetMapper()==a->volumeMapper);
  [a setMapper:a->volumeMapper];assert(a->volume->GetMapper()==a->volumeMapper);
  for(Preview *p in @[a,b]){vtkWeakPointer<vtkVolumeMapper> owned=p->volumeMapper;p->volumeMapper->Delete();p->volume->Delete();assert(owned==nullptr);[p release];}
 }
 main->Delete();input->Delete();puts("PASS: 20 mapper pairs isolate rendering state, share input, preserve sampling and release ownership");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-preset-mapper-') as d:
 p=Path(d);(p/'test.mm').write_text(code)
 libs=sorted((install/'lib').glob('libvtkCommon*.a'))
 for name in ['vtkRenderingVolumeOpenGL2','vtkRenderingVolume','vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkImagingMath','vtkRenderingUI','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
  libs+=list((install/'lib').glob('lib'+name+'-*.a'))
 subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),'-I'+str(root/'Horos/Sources'),str(p/'test.mm'),str(root/'Horos/Sources/vtkHorosFixedPointVolumeRayCastMapper.cxx'),str(root/'Horos/Sources/vtkHorosFixedPointVolumeRayCastMIPHelper.cxx'),*[str(x) for x in libs],'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
