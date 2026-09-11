#!/usr/bin/env python3
"""Verify VR export readback covers the full drawable with correct orientation."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
# Whichever configuration has been built; Release first, since that is what a
# distribution build produces.
install=next((c for c in (root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install',
                          root/'build/Build/Intermediates.noindex/Horos.build/Debug/VTK.build/Install')
              if (c/'include').is_dir()),
             root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install')
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#include <vtk_glew.h>
#import <Cocoa/Cocoa.h>
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
#include <vtkCocoaRenderWindow.h>
#include <vtkRenderer.h>
#include <vtkOpenGLState.h>
#include "VRFramebufferCapture.h"
#include <cassert>
#include <cstdio>
// Offscreen targets have explicit pixel dimensions; avoid Cocoa rounding an
// odd requested pixel size while creating its hidden backing view on Retina.
class CaptureWindow:public vtkCocoaRenderWindow {
public:
 static CaptureWindow *New(){return new CaptureWindow;}
 int *GetSize() override {return this->Size;}
};
int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 int dimensions[][2]={{101,67},{120,80},{3,2},{1,1}};
 for(auto &d:dimensions)for(int scale=1;scale<=2;scale++){
  int w=d[0]*scale,h=d[1]*scale;
  auto window=CaptureWindow::New();window->SetSize(w,h);window->SetMultiSamples(0);window->SetOffScreenRendering(1);
  auto renderer=vtkRenderer::New();window->AddRenderer(renderer);window->Render();window->MakeCurrent();
  assert(window->GetSize()[0]==w && window->GetSize()[1]==h);
  glBindFramebuffer(GL_DRAW_FRAMEBUFFER,window->GetUseOffScreenBuffers()?window->GetFrameBufferObject():0);glDrawBuffer(window->GetFrontLeftBuffer());
  auto state=window->GetState();state->vtkglDisable(GL_SCISSOR_TEST);state->vtkglClearColor(0,0,1,1);glClear(GL_COLOR_BUFFER_BIT);
  state->vtkglEnable(GL_SCISSOR_TEST);
  state->vtkglScissor(0,0,w/2,h);state->vtkglClearColor(1,0,0,1);glClear(GL_COLOR_BUFFER_BIT);
  state->vtkglScissor(w/2,h/2,w-w/2,h-h/2);state->vtkglClearColor(0,1,0,1);glClear(GL_COLOR_BUFFER_BIT);
  state->vtkglDisable(GL_SCISSOR_TEST);assert(glGetError()==GL_NO_ERROR);
  long width=-1,height=-1;auto pixels=HorosCopyVRFramebuffer(window,&width,&height);
  assert(pixels && width==w && height==h);
  for(int y=0;y<h;y++)for(int x=0;x<w;x++){
   int glY=h-y-1;int channel=x<w/2?0:(glY>=h/2?1:2);
   for(int c=0;c<3;c++)if(pixels[3*(y*w+x)+c]!=(c==channel?255:0)){fprintf(stderr,"FAIL size %dx%d at %d,%d channel %d got %d expected %d\n",w,h,x,y,c,pixels[3*(y*w+x)+c],c==channel?255:0);return 1;}
  }
  free(pixels);renderer->Delete();window->Delete();
 }
 long w=1,h=1;assert(!HorosCopyVRFramebuffer(nullptr,&w,&h) && w==0 && h==0);
 puts("PASS: full top-down RGB capture across eight offscreen target sizes including odd widths; every pixel and declared dimension verified");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-framebuffer-capture-') as directory:
    p=Path(directory);(p/'test.mm').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkRenderingVolumeOpenGL2','vtkRenderingVolume','vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkImagingMath','vtkRenderingUI','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
     libs+=list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),'-I'+str(root/'Horos/Sources'),str(p/'test.mm'),*[str(x) for x in libs],'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
