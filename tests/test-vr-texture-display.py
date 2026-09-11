#!/usr/bin/env python3
"""Exercise VTK texture display with real OpenGL; excludes Horos panel composition."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#include <vtk_glew.h>
#import <Cocoa/Cocoa.h>
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingVolumeOpenGL2);
#include <vtkCocoaRenderWindow.h>
#include <vtkRenderer.h>
#include <vtkVolume.h>
#include <vtkOpenGLRayCastImageDisplayHelper.h>
#include <vector>
#include <cstdio>
#include <cmath>
#include <cassert>
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 vtkCocoaRenderWindow *windows[2];vtkRenderer *renderers[2];vtkOpenGLRayCastImageDisplayHelper *helpers[2];
 auto volume=vtkVolume::New();
 for(int k=0;k<2;k++){
  windows[k]=vtkCocoaRenderWindow::New();windows[k]->SetSize(120,120);windows[k]->SetOffScreenRendering(1);
  renderers[k]=vtkRenderer::New();renderers[k]->SetBackground(k,k,k);windows[k]->AddRenderer(renderers[k]);
  helpers[k]=vtkOpenGLRayCastImageDisplayHelper::New();helpers[k]->PreMultipliedColorsOn();helpers[k]->SetPixelScale(1);
 }
 std::vector<unsigned short> pixels(16*16*4);
 int memory[2]={16,16},viewport[2]={120,120},use[2]={16,16},origin[2]={52,52};
 for(int iteration=0;iteration<20;iteration++)for(int k=0;k<2;k++){
  int value=8000+2000*((iteration+k)%3);for(int j=0;j<256;j++){pixels[4*j]=pixels[4*j+1]=pixels[4*j+2]=value;pixels[4*j+3]=65535;}
  auto w=windows[k];w->Render();w->MakeCurrent();assert(w->IsCurrent());
  if(iteration==0 && k==0)printf("OpenGL renderer: %s\n",glGetString(GL_RENDERER));
  helpers[k]->RenderTexture(volume,renderers[k],memory,viewport,use,origin,.5,pixels.data());
  assert(glGetError()==GL_NO_ERROR);
  auto result=w->GetPixelData(0,0,119,119,0,0);assert(result);
  int expected=std::lround(value*255./65535.);
  for(int c=0;c<3;c++){assert(std::abs((int)result[3*(60*120+60)+c]-expected)<=1);assert(result[c]==255*k);}
  delete[]result;
 }
 for(int k=0;k<2;k++){windows[k]->MakeCurrent();helpers[k]->ReleaseGraphicsResources(windows[k]);helpers[k]->Delete();renderers[k]->Delete();windows[k]->Delete();}
 volume->Delete();puts("PASS: 40 texture displays across two contexts preserve uploaded values and background without GL errors");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-texture-display-') as directory:
    p=Path(directory);(p/'test.mm').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkRenderingVolumeOpenGL2','vtkRenderingVolume','vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkImagingMath','vtkRenderingUI','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
     libs+=list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),'-I'+str(root/'Horos/Sources'),str(p/'test.mm'),*[str(x) for x in libs],'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
