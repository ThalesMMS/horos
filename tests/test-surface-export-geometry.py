#!/usr/bin/env python3
"""Compare real STL/OBJ vertices for asymmetric, transformed surface actors."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
install=root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code=r'''
#include "SRSurfaceExport.h"
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
#include <vtkCellArray.h>
#include <vtkPoints.h>
#include <vtkSTLWriter.h>
#include <vtkSTLReader.h>
#include <vtkOBJExporter.h>
#include <vtkRenderer.h>
#include <vtkRenderWindow.h>
#include <array>
#include <set>
#include <fstream>
#include <sstream>
#include <cassert>
#include <cmath>
using Point=std::array<long,3>;
Point key(double x,double y,double z){return {{lround(x*10000),lround(y*10000),lround(z*10000)}};}
int main(int argc,char **argv){
 auto data=vtkSmartPointer<vtkPolyData>::New();
 auto points=vtkSmartPointer<vtkPoints>::New();
 points->InsertNextPoint(0,0,0);points->InsertNextPoint(2,0,0);points->InsertNextPoint(0,3,0);points->InsertNextPoint(0,0,5);
 auto cells=vtkSmartPointer<vtkCellArray>::New();
 vtkIdType faces[4][3]={{0,2,1},{0,1,3},{1,2,3},{2,0,3}};
 for(auto &face:faces)cells->InsertNextCell(3,face);
 data->SetPoints(points);data->SetPolys(cells);
 auto mapper=vtkSmartPointer<vtkPolyDataMapper>::New();mapper->SetInputData(data);
 auto a=vtkSmartPointer<vtkActor>::New();a->SetMapper(mapper);a->SetOrigin(1,2,3);a->RotateZ(90);a->SetPosition(-40,-20,-10);
 auto b=vtkSmartPointer<vtkActor>::New();b->SetMapper(mapper);b->SetScale(2,3,1);b->SetPosition(-70,-50,-30);
 auto user=vtkSmartPointer<vtkTransform>::New();user->RotateX(30);b->SetUserTransform(user);
 auto hidden=vtkSmartPointer<vtkActor>::New();hidden->SetMapper(mapper);hidden->SetVisibility(0);
 vtkActor *actors[]={a,b,hidden,nullptr};
 auto geometry=HorosSurfaceExportGeometry(actors,4);
 assert(geometry->GetNumberOfPolys()==8);
 auto renderer=vtkSmartPointer<vtkRenderer>::New();renderer->AddActor(a);renderer->AddActor(b);renderer->AddActor(hidden);
 auto window=vtkSmartPointer<vtkRenderWindow>::New();window->AddRenderer(renderer);
 std::string prefix=argv[1],stl=prefix+".stl";
 auto sw=vtkSmartPointer<vtkSTLWriter>::New();sw->SetInputData(geometry);sw->SetFileName(stl.c_str());sw->Write();
 auto ow=vtkSmartPointer<vtkOBJExporter>::New();ow->SetInput(window);ow->SetFilePrefix(prefix.c_str());ow->Write();
 std::set<Point> objVertices,stlVertices,expected;
 std::ifstream in(prefix+".obj");std::string line;
 while(std::getline(in,line)){std::istringstream row(line);std::string tag;double x,y,z;row>>tag;if(tag=="v" && row>>x>>y>>z)objVertices.insert(key(x,y,z));}
 auto reader=vtkSmartPointer<vtkSTLReader>::New();reader->SetFileName(stl.c_str());reader->Update();
 assert(reader->GetOutput()->GetNumberOfPolys()==8);
 for(vtkIdType i=0;i<reader->GetOutput()->GetNumberOfPoints();i++){auto p=reader->GetOutput()->GetPoint(i);stlVertices.insert(key(p[0],p[1],p[2]));}
 for(auto actor:{a,b})for(int i=0;i<4;i++){double p[4],q[4];points->GetPoint(i,p);p[3]=1;actor->GetMatrix()->MultiplyPoint(p,q);expected.insert(key(q[0],q[1],q[2]));}
 assert(expected.size()==8 && objVertices==expected && stlVertices==expected);
 assert((*stlVertices.begin())[0]<0);
 assert(HorosSurfaceExportGeometry(nullptr,0)->GetNumberOfPoints()==0);
 b->SetVisibility(0);assert(HorosSurfaceExportGeometry(actors,4)->GetNumberOfPolys()==4);
 double original[3];points->GetPoint(0,original);assert(original[0]==0 && original[1]==0 && original[2]==0);
 puts("PASS: STL and OBJ preserve both asymmetric actors, negative coordinates, origin/rotation/scale/user transform; hidden actors excluded and source unmodified");
}
'''
with tempfile.TemporaryDirectory(prefix='horos-surface-export-') as folder:
 p=Path(folder);(p/'test.cpp').write_text(code)
 libs=sorted((install/'lib').glob('libvtkCommon*.a'))
 for name in ['vtkIOImage','vtkpng','vtkjpeg','vtktiff','vtkFiltersSources','vtkImagingCore','vtkIOExport','vtkIOGeometry','vtkIOCore','vtkRenderingCore','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersGeometry','vtkRenderingUI','vtksys','vtkdoubleconversion']:
  libs+=list((install/'lib').glob('lib'+name+'-*.a'))
 subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),'-I'+str(root/'Horos/Sources'),str(p/'test.cpp'),*[str(x) for x in libs],'-L/opt/homebrew/lib','-lpng','-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'model')],check=True)
