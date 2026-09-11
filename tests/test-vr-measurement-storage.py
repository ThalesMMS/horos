#!/usr/bin/env python3
"""Exercise the production stored-overlay owner against real VTK objects."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
a=source.index('@interface HorosVRStoredMeasurement :')
b=source.index('@implementation VRView\n',a)
owner=source[a:b]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#import <Cocoa/Cocoa.h>
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingFreeType);
#include <vtkPolyData.h>
#include <vtkPolyDataMapper2D.h>
#include <vtkActor2D.h>
#include <vtkTextActor.h>
#include <vtkTextProperty.h>
#include <vtkProperty2D.h>
#include <vtkCoordinate.h>
#include <vtkPoints.h>
#include <vtkCellArray.h>
#include <cassert>
#include <cstring>
OWNER
int main(){ @autoreleasepool {
 auto data=vtkPolyData::New();auto points=vtkPoints::New();
 points->InsertNextPoint(20,30,0);points->InsertNextPoint(120,80,0);data->SetPoints(points);points->Delete();
 auto cells=vtkCellArray::New();cells->InsertNextCell(2);cells->InsertCellPoint(0);cells->InsertCellPoint(1);data->SetLines(cells);cells->Delete();
 auto text=vtkTextActor::New();text->SetInput("Length: 1.12 cm");text->SetPosition(120,80);text->GetTextProperty()->SetColor(1,1,0);
 for(int i=0;i<100;i++) {
  HorosVRStoredMeasurement *entry=[[HorosVRStoredMeasurement alloc] initWithData:data text:text];
  assert(entry->data!=data && entry->data->GetPoints()!=points);
  assert(entry->text->GetTextProperty()!=text->GetTextProperty());
  entry->data->GetPoints()->SetPoint(0,900,900,0);entry->data->GetPoints()->Modified();
  double original[3];data->GetPoint(0,original);assert(original[0]==20 && original[1]==30);
  entry->text->SetInput("edited");assert(!strcmp(text->GetInput(),"Length: 1.12 cm"));
  assert(text->GetTextProperty()->GetColor()[0]==1 && entry->text->GetTextProperty()->GetColor()[0]==0);
  assert(entry->actor->GetMapper()==entry->mapper);
  assert(entry->text->GetPosition()[0]==120 && entry->text->GetPosition()[1]==80);
  [entry release];
 }
 text->Delete();data->Delete();
 puts("PASS: 100 stored-overlay lifecycles retain independent geometry, labels, styles and mapper ownership");
}}
'''.replace('OWNER',owner)
with tempfile.TemporaryDirectory(prefix='horos-vr-storage-') as d:
    p=Path(d);(p/'test.mm').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkzlib','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkRenderingUI','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
        libs+=list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),str(p/'test.mm'),*[str(x) for x in libs],'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
