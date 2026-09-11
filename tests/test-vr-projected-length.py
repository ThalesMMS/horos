#!/usr/bin/env python3
"""Validate production length math using real VTK projection and known phantom spacing."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
a=s.index('        double point1[ 4], point2[ 4];',s.index('- (void) computeLength'))
b=s.index('        pts->GetPoint( 0, point1);',s.index('double length = sqrt',a))
block=s[a:b]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#include <vtkPoints.h>
#include <vtkRenderer.h>
#include <vtkRenderWindow.h>
#include <vtkCocoaRenderWindow.h>
#include <vtkOpenGLRenderer.h>
#include <vtkCamera.h>
#include <vtkOpenGLCamera.h>
#include <cmath>
#include <cstdio>
double measuredCM(vtkRenderer *aRenderer,vtkPoints *pts,double factor) {
 BLOCK
 return length/(10.*factor);
}
int main(){
 auto window=vtkCocoaRenderWindow::New();auto renderer=vtkOpenGLRenderer::New();window->AddRenderer(renderer);
 auto camera=vtkOpenGLCamera::New();renderer->SetActiveCamera(camera);camera->SetParallelProjection(true);camera->SetClippingRange(.01,10000);
 auto points=vtkPoints::New();points->SetDataTypeToDouble();points->SetNumberOfPoints(2);
 struct Fixture {double spacing[3];double delta[3];};
 Fixture fixtures[]={{{1,1,1},{31,0,0}},{{1,1,1},{12,16,0}},{{1,1,1},{.3,.4,0}},{{.7,1.2,2.5},{20,10,4}}};
 int sizes[][2]={{800,600},{1695,938},{512,512},{2100,400}};int count=0;
 for(auto fixture:fixtures)for(int axis=0;axis<3;axis++)for(int backing=1;backing<=2;backing++)for(auto size:sizes)for(double sampling:{1.,2.}) {
  double factor=sampling/fixture.spacing[0];window->SetSize(size[0]*backing,size[1]*backing);
  double position[3]={0,0,0};position[axis]=100*factor;camera->SetPosition(position);camera->SetFocalPoint(0,0,0);
  camera->SetViewUp(0,axis==2?1:0,axis==2?0:1);camera->SetParallelScale(40*factor);
  double expectedSquared=0;
  for(int endpoint=0;endpoint<2;endpoint++) {
   double world[3];for(int j=0;j<3;j++)world[j]=endpoint*fixture.delta[j]*fixture.spacing[j]*factor;
   renderer->SetWorldPoint(world[0],world[1],world[2],1);renderer->WorldToDisplay();
   double *display=renderer->GetDisplayPoint();points->SetPoint(endpoint,display[0],display[1],0);
  }
  for(int j=0;j<3;j++)if(j!=axis)expectedSquared+=std::pow(fixture.delta[j]*fixture.spacing[j],2);
  double expected=std::sqrt(expectedSquared)/10;double actual=measuredCM(renderer,points,factor);
  if(!std::isfinite(actual)||std::abs(actual-expected)>1e-8){std::fprintf(stderr,"FAIL: case %d expected %.12g cm, got %.12g cm\n",count,expected,actual);return 1;}
  count++;
 }
 points->Delete();camera->Delete();renderer->Delete();window->Delete();
 std::printf("PASS: %d real VTK orthographic cases: isotropic/anisotropic spacing, three camera axes, submillimeter/diagonal lengths, viewport/backing/sampling changes\n",count);
}
'''.replace('BLOCK',block)
with tempfile.TemporaryDirectory(prefix='horos-vr-length-') as d:
    p=Path(d);(p/'test.cxx').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkRenderingCore','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtksys','vtkdoubleconversion']:
        libs+=list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-I'+str(install/'include'),str(p/'test.cxx'),*[str(x) for x in libs],'-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
