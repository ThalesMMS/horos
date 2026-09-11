#!/usr/bin/env python3
"""Verify production VR orientation positions with actual VTK font bounds."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
import sys
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
source=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/VRView.mm']) if len(sys.argv)>1 else (root/'Horos/Sources/VRView.mm').read_bytes()).decode('latin1')
a=source.index('        oText[ 0]->GetPositionCoordinate()->SetValue( 0.01, 0.5);')
b=source.index('        aCamera = vtkCamera::New();',a)
positions=source[a:b]
code=r'''
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingFreeType);
#include <vtkRenderWindow.h>
#include <vtkRenderer.h>
#include <vtkTextActor.h>
#include <vtkTextProperty.h>
#include <vtkCoordinate.h>
#include <cstdio>
int main(){
 for(int size:{256,512,768})for(int dpi:{72,144,288}){
  auto window=vtkRenderWindow::New();window->SetSize(size,size);window->SetDPI(dpi);
  auto renderer=vtkRenderer::New();window->AddRenderer(renderer);
  vtkTextActor *oText[5];for(int i=0;i<5;i++){
   oText[i]=vtkTextActor::New();oText[i]->SetInput(i==2?"I":"S");
   oText[i]->SetTextScaleModeToNone();oText[i]->GetPositionCoordinate()->SetCoordinateSystemToNormalizedViewport();
   oText[i]->GetTextProperty()->SetBold(true);oText[i]->GetTextProperty()->SetShadow(true);oText[i]->GetTextProperty()->SetShadowOffset(1,1);
  }
POSITIONS
  for(int i:{2,3}){
   double box[4];oText[i]->GetBoundingBox(renderer,box);
   int *point=oText[i]->GetPositionCoordinate()->GetComputedDisplayValue(renderer);
   if(point[1]+box[2]<0 || point[1]+box[3]>=size){fprintf(stderr,"FAIL: orientation %d crosses %d-pixel viewport at DPI %d (y %.0f..%.0f)\n",i,size,dpi,point[1]+box[2],point[1]+box[3]);return 1;}
  }
  for(auto actor:oText)actor->Delete();renderer->Delete();window->Delete();
 }
 puts("PASS: superior/inferior label bounds remain inside 256/512/768 viewports at DPI 72/144/288");
}
'''.replace('POSITIONS',positions)
with tempfile.TemporaryDirectory(prefix='horos-orientation-bounds-') as directory:
    p=Path(directory);(p/'test.mm').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkRenderingVolumeOpenGL2','vtkRenderingVolume','vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkImagingMath','vtkRenderingUI','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
     libs+=list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),'-I'+str(root/'Horos/Sources'),str(p/'test.mm'),*[str(x) for x in libs],'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
