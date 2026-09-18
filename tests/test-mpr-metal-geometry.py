#!/usr/bin/env python3
"""MPR geometry without ray casting agrees with VTK, rejects actual crops unless the caller clips them, and says why it refused."""
from pathlib import Path
import subprocess, tempfile, sys
root = Path(__file__).resolve().parents[1]
install = root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built Release VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code = r'''

#import <Cocoa/Cocoa.h>
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingVolumeOpenGL2);
#include "vtkHorosFixedPointVolumeRayCastMapper.h"
#include <vtkCocoaRenderWindow.h>
#include <vtkRenderer.h>
#include <vtkCamera.h>
#include <vtkVolume.h>
#include <vtkVolumeProperty.h>
#include <vtkImageData.h>
#include <vtkPointData.h>
#include <vtkFixedPointRayCastImage.h>
#include <vtkPiecewiseFunction.h>
#include <vtkPlane.h>
#include <vtkCallbackCommand.h>
#include <vtkNew.h>
#include <cassert>
#include <cmath>

int main(){@autoreleasepool{
 [NSApplication sharedApplication];
 vtkNew<vtkCocoaRenderWindow> window; window->SetOffScreenRendering(1); window->SetSize(240,160);
 vtkNew<vtkRenderer> renderer; window->AddRenderer(renderer);
 vtkNew<vtkImageData> data; data->SetDimensions(24,28,32);data->SetSpacing(.7,1.2,1.5);
 data->AllocateScalars(VTK_UNSIGNED_SHORT,1);
 auto values=static_cast<unsigned short*>(data->GetScalarPointer());
 for(int i=0;i<24*28*32;++i) values[i]=i%1000;
 vtkNew<vtkHorosFixedPointVolumeRayCastMapper> mapper;mapper->SetInputData(data);
 mapper->SetBlendModeToMaximumIntensity();mapper->AutoAdjustSampleDistancesOff();
 vtkNew<vtkVolume> volume;volume->SetMapper(mapper);renderer->AddVolume(volume);
 vtkNew<vtkPiecewiseFunction> opacity;opacity->AddPoint(0,0);opacity->AddPoint(1000,1);
 volume->GetProperty()->SetScalarOpacity(opacity);volume->GetProperty()->SetInterpolationTypeToLinear();
 auto camera=renderer->GetActiveCamera();camera->ParallelProjectionOn();camera->SetParallelScale(35);
 camera->SetPosition(8,16,120);camera->SetFocalPoint(8,16,20);
 window->Render();
 int raycasts=0;
 vtkNew<vtkCallbackCommand> counter;counter->SetClientData(&raycasts);
 counter->SetCallback([](vtkObject*,unsigned long,void* p,void*){++*static_cast<int*>(p);});
 mapper->AddObserver(vtkCommand::VolumeMapperRenderStartEvent,counter);
 for(int iteration=0;iteration<12;++iteration){
  double lod=iteration%2+1; mapper->SetMinimumImageSampleDistance(lod);mapper->SetImageSampleDistance(lod);
  window->SetSize(iteration%3?241:320,iteration%3?161:180);
  camera->Roll(17);camera->Azimuth(5);renderer->ResetCameraClippingRange();
  int before=raycasts;
  assert(mapper->PrepareMPRGeometry(renderer,volume));
  assert(raycasts==before);
  int size[2],origin[2];auto image=mapper->GetRayCastImage();
  image->GetImageInUseSize(size);image->GetImageOrigin(origin);
  assert(image->GetImageSampleDistance()==lod);
  mapper->Render(renderer,volume);
  assert(raycasts==before+1);
  for(int axis=0;axis<2;++axis){
   assert(size[axis]==image->GetImageInUseSize()[axis]);
   assert(origin[axis]==image->GetImageOrigin()[axis]);
  }
 }
 double bounds[6];data->GetBounds(bounds);
 for(int axis=0;axis<3;++axis)for(int high=0;high<2;++high){
  vtkNew<vtkPlane> plane;double n[3]={0,0,0},o[3]={0,0,0};
  n[axis]=high?-1:1;o[axis]=bounds[2*axis+high];plane->SetNormal(n);plane->SetOrigin(o);mapper->AddClippingPlane(plane);
 }
 typedef vtkHorosFixedPointVolumeRayCastMapper Mapper;
 assert(mapper->PrepareMPRGeometry(renderer,volume));
 assert(mapper->GetGeometryRefusal()==Mapper::GeometryAccepted);
 vtkNew<vtkPlane> crop;crop->SetNormal(1,0,0);crop->SetOrigin(5,0,0);mapper->AddClippingPlane(crop);
 assert(!mapper->PrepareMPRGeometry(renderer,volume));
 assert(mapper->GetGeometryRefusal()==Mapper::GeometryClippingPlane);
 // A caller that clips its rays takes the crop, with the very planes VTK's
 // own rays are clipped against when it casts them (#664).
 assert(mapper->PrepareMPRGeometry(renderer,volume,true));
 assert(mapper->GetGeometryRefusal()==Mapper::GeometryAccepted);
 const float *prepared=nullptr;
 assert(mapper->GetVoxelClippingPlanes(&prepared)==7);
 float kept[28];for(int i=0;i<28;++i) kept[i]=prepared[i];
 // x >= 5 mm on a 0.7 mm grid: x >= 7.142857 voxels.
 assert(std::fabs(kept[24]-1)<1e-6 && std::fabs(kept[25])<1e-6 && std::fabs(kept[26])<1e-6 && std::fabs(kept[27]+5/.7)<1e-4);
 mapper->Render(renderer,volume);
 const float *cast=nullptr;
 assert(mapper->GetVoxelClippingPlanes(&cast)==7);
 for(int i=0;i<28;++i) assert(kept[i]==cast[i]);
 mapper->RemoveAllClippingPlanes();assert(mapper->PrepareMPRGeometry(renderer,volume));
 const float *none=nullptr;assert(mapper->GetVoxelClippingPlanes(&none)==0);
 // A volume far outside the view is not refused: VTK seeds its bounds at the
 // image edges, so it still casts a strip of a few rows there, which the
 // geometry accepts as it is (#664).
 double position[3],focal[3],up[3];camera->GetPosition(position);camera->GetFocalPoint(focal);camera->GetViewUp(up);
 camera->SetPosition(position[0]+2000*up[0],position[1]+2000*up[1],position[2]+2000*up[2]);
 camera->SetFocalPoint(focal[0]+2000*up[0],focal[1]+2000*up[1],focal[2]+2000*up[2]);
 renderer->ResetCameraClippingRange();
 assert(mapper->PrepareMPRGeometry(renderer,volume));
 assert(mapper->GetRayCastImage()->GetImageInUseSize()[1]<=4 && mapper->GetRayCastImage()->GetImageOrigin()[1]==0);
 camera->SetPosition(position);camera->SetFocalPoint(focal);renderer->ResetCameraClippingRange();
 assert(mapper->PrepareMPRGeometry(renderer,volume));
 struct External { int calls=0; bool accepted=true; } external;
 mapper->SetImageRenderer([](void* p,vtkHorosFixedPointVolumeRayCastMapper* m,vtkRenderer* r,vtkVolume* v){
  auto state=static_cast<External*>(p);++state->calls;
  if(!state->accepted || !m->PrepareMPRGeometry(r,v)) return false;
  m->GetRayCastImage()->ClearImage();return true;
 },&external);
 int beforeExternal=raycasts;
 mapper->Render(renderer,volume);
 assert(external.calls==1 && raycasts==beforeExternal && mapper->GetExternalImageValid());
 extern int dontRenderVolumeRenderingOsiriX;
 dontRenderVolumeRenderingOsiriX=1;
 mapper->Render(renderer,volume);
 assert(external.calls==1 && raycasts==beforeExternal && mapper->GetExternalImageValid());
 dontRenderVolumeRenderingOsiriX=0;external.accepted=false;
 mapper->Render(renderer,volume);
 assert(external.calls==2 && raycasts==beforeExternal+1 && !mapper->GetExternalImageValid());
 external.accepted=true;mapper->Render(renderer,volume);
 assert(mapper->GetExternalImageValid());
 mapper->SetImageRenderer(nullptr,nullptr);
 assert(!mapper->GetExternalImageValid());
 mapper->Render(renderer,volume);assert(raycasts==beforeExternal+2);
 mapper->ReleaseGraphicsResources(window);
 puts("PASS: 12 planes match CPU geometry; clipping refusal and its reasons, the accepted crop with VTK's own voxel planes, external image, cached display, CPU fallback and renderer switch verified");
}}

'''
with tempfile.TemporaryDirectory(prefix='horos-mpr-geometry-') as d:
 p=Path(d);(p/'test.mm').write_text(code)
 libs=sorted((install/'lib').glob('libvtkCommon*.a'))
 for name in ['vtkRenderingVolumeOpenGL2','vtkRenderingVolume','vtkRenderingCore','vtkRenderingFreeType','vtkfreetype','vtkRenderingOpenGL2','vtkglew','vtkFiltersCore','vtkFiltersGeneral','vtkFiltersSources','vtkImagingCore','vtkImagingMath','vtkRenderingUI','vtkFiltersGeometry','vtksys','vtkdoubleconversion']:
  libs+=list((install/'lib').glob('lib'+name+'-*.a'))
 subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),'-I'+str(root/'Horos/Sources'),str(p/'test.mm'),str(root/'Horos/Sources/vtkHorosFixedPointVolumeRayCastMapper.cxx'),str(root/'Horos/Sources/vtkHorosFixedPointVolumeRayCastMIPHelper.cxx'),*map(str,libs),'-lz','-framework','Cocoa','-framework','OpenGL','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
