#!/usr/bin/env python3
"""Exercise production drag updates with the locally built VTK point arrays."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
path='Horos/Sources/VRView.mm'
source=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
a=source.index('pts->SetPoint( pts->GetNumberOfPoints()-1',source.index('- (void)mouseDragged:'))
b=source.index('[self computeLength];',a)
block=source[a:b].replace('[self captureCurrentLineProjection];', '') # Projection anchoring has its own real-VTK test.
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#include <vtkPoints.h>
#include <vtkPolyData.h>
#include <vtkCellArray.h>
#include <vtkDataArray.h>
#include <cassert>
#include <cstdio>
void update(vtkPolyData *Line2DData,double *tempPoint) {
 vtkPoints *pts=Line2DData->GetPoints();long i;
 BLOCK
}
int main(){
 auto data=vtkPolyData::New();auto pts=vtkPoints::New();
 pts->InsertNextPoint(0,0,0);pts->InsertNextPoint(0,0,0);data->SetPoints(pts);pts->Delete();
 for(int i=1;i<=20;i++){
  auto previous=pts->GetData()->GetMTime();
  double target[3]={double(20*i),double(10*i),0};update(data,target);
  if(pts->GetData()->GetMTime()<=previous){std::fprintf(stderr,"FAIL: production drag did not invalidate point array at step %d\n",i);return 1;}
  double p[3];pts->GetPoint(1,p);assert(p[0]==target[0] && p[1]==target[1]);
 }
 data->Delete();std::puts("PASS: 20 production drag updates invalidate real VTK point buffers and retain endpoint coordinates");
}
'''.replace('BLOCK',block)
with tempfile.TemporaryDirectory(prefix='horos-vr-points-') as d:
    p=Path(d);(p/'test.cxx').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    libs+=list((install/'lib').glob('libvtksys*.a'))+list((install/'lib').glob('libvtkdoubleconversion*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-I'+str(install/'include'),str(p/'test.cxx'),*[str(x) for x in libs],'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
