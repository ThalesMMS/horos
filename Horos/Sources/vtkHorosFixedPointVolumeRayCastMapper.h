/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation,  version 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE.  See the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos.  If not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program:   OsiriX
  Copyright (c) OsiriX Team
  All rights reserved.
  Distributed under GNU - LGPL
  
  See http://www.osirix-viewer.com/copyright.html for details.
     This software is distributed WITHOUT ANY WARRANTY; without even
     the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
     PURPOSE.
 ============================================================================*/

#ifndef __vtkHorosFixedPointVolumeRayCastMapper_h
#define __vtkHorosFixedPointVolumeRayCastMapper_h

#include <vtkFixedPointVolumeRayCastMapper.h>

class  VTKRENDERINGVOLUME_EXPORT vtkHorosFixedPointVolumeRayCastMapper : public vtkFixedPointVolumeRayCastMapper {
    
public:
    
    static vtkHorosFixedPointVolumeRayCastMapper *New();
    void Render( vtkRenderer *, vtkVolume * );
    // Why PrepareMPRGeometry last said no, for the host's fallback reason (#664).
    enum GeometryRefusal { GeometryAccepted = 0, GeometryNoInput, GeometryNoViewport, GeometryClippingPlane, GeometryNoRows };
    // Sets up the ray-cast image and matrices as a CPU render would, without
    // casting a ray. A clipping plane that cuts into the voxel centres refuses
    // unless the caller clips rays against the planes itself (#664).
    bool PrepareMPRGeometry(vtkRenderer *, vtkVolume *, bool acceptClippingPlanes = false);
    GeometryRefusal GetGeometryRefusal() const { return this->LastGeometryRefusal; }
    // After PrepareMPRGeometry: the clipping planes in voxel index coordinates,
    // exactly as VTK clips its rays against them - four floats per plane, the
    // kept side where a*x + b*y + c*z + d >= 0 (#664).
    int GetVoxelClippingPlanes(const float **planes) const
    {
        *planes = this->TransformedClippingPlanes;
        return this->TransformedClippingPlanes ? this->NumTransformedClippingPlanes : 0;
    }
    typedef bool (*ImageRenderer)(void *, vtkHorosFixedPointVolumeRayCastMapper *, vtkRenderer *, vtkVolume *);
    void SetImageRenderer(ImageRenderer renderer, void *context)
    {
        this->RenderImage = renderer;
        this->RenderImageContext = context;
        this->ExternalImageValid = false;
    }
    bool GetExternalImageValid() const { return this->ExternalImageValid; }
    // A minimum-intensity blend that averages instead: the mean projection. A
    // mode of this mapper, which its view sets; it used to be a process-wide
    // flag that any MPR or CPR window changed for every mapper (#665).
    void SetMeanIntensity(bool on) { this->MeanIntensity = on; }
    bool GetMeanIntensity() const { return this->MeanIntensity; }
    
protected:
    
    vtkHorosFixedPointVolumeRayCastMapper();
    void DisplayRenderedImage( vtkRenderer *ren, vtkVolume   *vol );
    void SanitizeRayCastZBuffer();
    
private:
    ImageRenderer RenderImage = nullptr;
    void *RenderImageContext = nullptr;
    bool ExternalImageValid = false;
    GeometryRefusal LastGeometryRefusal = GeometryAccepted;
    bool MeanIntensity = false;
    
    vtkHorosFixedPointVolumeRayCastMapper(const vtkHorosFixedPointVolumeRayCastMapper&);  // Not implemented.
    void operator=(const vtkHorosFixedPointVolumeRayCastMapper&);  // Not implemented.
    
};

#endif
