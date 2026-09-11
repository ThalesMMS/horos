#!/usr/bin/env python3
"""Verify production projected overlays follow pan/zoom and hide/restore by direction."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
functions=source[source.index('static bool HorosCaptureLineProjection'):source.index('// Each inactive overlay')]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingFreeType);
#include <vtkPolyData.h>
#include <vtkTextActor.h>
#include <vtkCoordinate.h>
#include <vtkPoints.h>
#include <vtkRenderer.h>
#include <vtkCamera.h>
#include <vtkRenderWindow.h>
#include <cassert>
#include <cmath>
FUNCTIONS
int main(){
 auto window=vtkRenderWindow::New();auto renderer=vtkRenderer::New();window->AddRenderer(renderer);
 auto camera=renderer->GetActiveCamera();camera->ParallelProjectionOn();camera->SetPosition(0,0,100);camera->SetFocalPoint(0,0,0);camera->SetViewUp(0,1,0);camera->SetParallelScale(40);window->SetSize(800,600);
 auto data=vtkPolyData::New();auto pts=vtkPoints::New();pts->SetDataTypeToDouble();pts->InsertNextPoint(250,300,0);pts->InsertNextPoint(475,375,0);data->SetPoints(pts);pts->Delete();
 auto text=vtkTextActor::New();double world[2][3],direction[3];
 assert(HorosCaptureLineProjection(renderer,camera,data,world,direction));
 // Original plane endpoints have x/y (-20,0) and (10,10), independent of depth.
 assert(std::abs(world[0][0]+20)<1e-9 && std::abs(world[1][1]-10)<1e-9);
 for(int width: {512,1600})for(double zoom: {20.,40.,80.})for(double pan: {-15.,0.,10.}){
  window->SetSize(width,600);camera->SetParallelScale(zoom);camera->SetPosition(pan,5,100);camera->SetFocalPoint(pan,5,0);
  assert(HorosUpdateLineProjection(renderer,camera,data,text,world,direction));
  for(int i=0;i<2;i++){
   double p[3];data->GetPoint(i,p);
   assert(std::abs(p[0]-((world[i][0]-pan)*600/(2*zoom)+width/2))<1e-8);
   assert(std::abs(p[1]-((world[i][1]-5)*600/(2*zoom)+300))<1e-8);
  }
 }
 double before[3];data->GetPoint(0,before);
 camera->SetPosition(100,0,0);camera->SetFocalPoint(0,0,0);
 assert(!HorosUpdateLineProjection(renderer,camera,data,text,world,direction));
 double after[3];data->GetPoint(0,after);assert(after[0]==before[0] && after[1]==before[1]);
 camera->SetPosition(0,0,100);camera->SetFocalPoint(0,0,0);
 assert(HorosUpdateLineProjection(renderer,camera,data,text,world,direction));
 camera->ParallelProjectionOff();
 assert(!HorosUpdateLineProjection(renderer,camera,data,text,world,direction));
 assert(!HorosCaptureLineProjection(renderer,camera,data,world,direction));
 camera->ParallelProjectionOn();assert(HorosUpdateLineProjection(renderer,camera,data,text,world,direction));
 text->Delete();data->Delete();renderer->Delete();window->Delete();
 puts("PASS: production projection capture, 18 pan/zoom/viewport cases, hidden-direction preservation and parallel restoration");
}
'''.replace('FUNCTIONS',functions)
with tempfile.TemporaryDirectory(prefix='horos-vr-projection-') as d:
    p=Path(d);(p/'test.cxx').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
        libs+=list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-I'+str(install/'include'),str(p/'test.cxx'),*[str(x) for x in libs],'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
