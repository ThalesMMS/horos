#!/usr/bin/env python3
"""Replacing the main VR mapper must not delete a preview's VAO in another context."""
from pathlib import Path
import subprocess, tempfile, sys
root = Path(__file__).resolve().parents[1]
source = (subprocess.check_output(['git', 'show', sys.argv[1]+':Horos/Sources/VRView.mm'])
          if len(sys.argv)>1 else (root/'Horos/Sources/VRView.mm').read_bytes()).decode('latin1')
a = source.index('        if( volumeMapper)\n', source.index('-(void) movieChangeSource:(float*) volumeData showWait'))
b = source.index('        if( textureMapper)', a)
block = source[a:b]
install = root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code = r'''
#include <vtk_glew.h>
#import <Cocoa/Cocoa.h>
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingVolumeOpenGL2);
#include "vtkHorosFixedPointVolumeRayCastMapper.h"
#include <vtkRayCastImageDisplayHelper.h>
#include <vtkCocoaRenderWindow.h>
#include <vtkRenderer.h>
#include <vtkVolume.h>
#include <vtkWeakPointer.h>
#include <vector>
#include <cassert>
class ProbeMapper: public vtkHorosFixedPointVolumeRayCastMapper {
public:
 static ProbeMapper *New(){return new ProbeMapper;}
 void Display(vtkVolume *v,vtkRenderer *r){
  std::vector<unsigned short> pixels(16*16*4,65535);
  for(int i=0;i<256;i++)for(int c=0;c<3;c++)pixels[4*i+c]=10000;
  int memory[2]={16,16},viewport[2]={120,120},use[2]={16,16},origin[2]={52,52};
  this->ImageDisplayHelper->SetPixelScale(2);
  this->ImageDisplayHelper->RenderTexture(v,r,memory,viewport,use,origin,.5,pixels.data());
 }
};
@interface Peer:NSObject { @public vtkHorosFixedPointVolumeRayCastMapper *volumeMapper; vtkVolume *volume; vtkRenderer *aRenderer; }
- (void)instantiateEngine:(int)engine;
- (void)replaceMapper;
@end
@implementation Peer
- (void)instantiateEngine:(int)engine { volumeMapper=ProbeMapper::New(); volume->SetMapper(volumeMapper); }
- (void)replaceMapper {
BLOCK
}
@end
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 for(int cycle=0;cycle<10;cycle++){
  vtkCocoaRenderWindow *windows[2]; vtkRenderer *renderers[2]; ProbeMapper *mappers[2]; vtkVolume *volumes[2];
  for(int k=0;k<2;k++){
   windows[k]=vtkCocoaRenderWindow::New();windows[k]->SetSize(120,120);windows[k]->SetOffScreenRendering(1);
   renderers[k]=vtkRenderer::New();renderers[k]->SetBackground(1,1,1);windows[k]->AddRenderer(renderers[k]);
   mappers[k]=ProbeMapper::New();volumes[k]=vtkVolume::New();volumes[k]->SetMapper(mappers[k]);
   windows[k]->Render();mappers[k]->Display(volumes[k],renderers[k]);
   auto initial=windows[k]->GetPixelData(0,0,119,119,0,0);assert(initial);
   assert(initial[3*(60*120+60)]>=76 && initial[3*(60*120+60)]<=80);delete[]initial;
  }
  Peer *peer=[Peer new];peer->volumeMapper=mappers[0];peer->volume=volumes[0];peer->aRenderer=renderers[0];
  vtkWeakPointer<vtkVolumeMapper> old=mappers[0];
  windows[1]->MakeCurrent();[peer replaceMapper];assert(old==nullptr);
  windows[1]->Render();assert(windows[1]->IsCurrent());mappers[1]->Display(volumes[1],renderers[1]);
  GLint program=0;glGetIntegerv(GL_CURRENT_PROGRAM,&program);assert(program && glIsProgram(program));
  auto pixels=windows[1]->GetPixelData(0,0,119,119,0,0);assert(pixels);
  int center=pixels[3*(60*120+60)];delete[]pixels;
  if(center<76 || center>80){fprintf(stderr,"FAIL: replacing main mapper damaged preview texture (center=%d, expected 78)\n",center);return 1;}
  assert(glGetError()==GL_NO_ERROR);
  mappers[0]=static_cast<ProbeMapper*>(peer->volumeMapper);
  for(int k=0;k<2;k++){mappers[k]->ReleaseGraphicsResources(windows[k]);mappers[k]->Delete();volumes[k]->Delete();renderers[k]->Delete();windows[k]->Delete();}
  [peer release];
 }
 puts("PASS: 10 main-mapper replacements with a preview context current preserve the preview pixels and release the old mapper");
}}
'''.replace('BLOCK',block)
with tempfile.TemporaryDirectory(prefix='horos-mapper-context-') as d:
 p=Path(d);(p/'test.mm').write_text(code)
 libs=sorted((install/'lib').glob('libvtkCommon*.a'))
 for name in ['vtkRenderingVolumeOpenGL2','vtkRenderingVolume','vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkImagingMath','vtkRenderingUI','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
  libs+=list((install/'lib').glob('lib'+name+'-*.a'))
 subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),'-I'+str(root/'Horos/Sources'),str(p/'test.mm'),str(root/'Horos/Sources/vtkHorosFixedPointVolumeRayCastMapper.cxx'),str(root/'Horos/Sources/vtkHorosFixedPointVolumeRayCastMIPHelper.cxx'),*map(str,libs),'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
