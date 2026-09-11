#ifndef Horos_SEGSurfaceVTK_h
#define Horos_SEGSurfaceVTK_h

#import <Foundation/Foundation.h>
#include <vtkCellArray.h>
#include <vtkCutter.h>
#include <vtkPlane.h>
#include <vtkPoints.h>
#include <vtkPolyData.h>
#include <vtkSmartPointer.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

// The bridge only transfers the shared Swift mesh. In particular it does not
// triangulate a hull, fill holes, smooth, weld components or reorient cavities.
inline vtkSmartPointer<vtkPolyData> HorosSEGSurfacePolyData(NSData *vertices, NSData *triangles)
{
    auto data = vtkSmartPointer<vtkPolyData>::New();
    if (!vertices || !triangles || vertices.length % (3 * sizeof(double)) ||
        triangles.length % (3 * sizeof(uint64_t))) return data;
    const NSUInteger count = vertices.length / (3 * sizeof(double));
    if (count > static_cast<NSUInteger>(std::numeric_limits<vtkIdType>::max())) return data;
    auto points = vtkSmartPointer<vtkPoints>::New();
    points->SetDataTypeToDouble();
    for (NSUInteger index = 0; index < count; ++index) {
        double p[3];
        memcpy(p, static_cast<const char *>(vertices.bytes) + index * sizeof(p), sizeof(p));
        if (!std::isfinite(p[0]) || !std::isfinite(p[1]) || !std::isfinite(p[2])) return data;
        points->InsertNextPoint(p);
    }
    auto cells = vtkSmartPointer<vtkCellArray>::New();
    for (NSUInteger offset = 0; offset < triangles.length; offset += 3 * sizeof(uint64_t)) {
        uint64_t source[3];
        memcpy(source, static_cast<const char *>(triangles.bytes) + offset, sizeof(source));
        if (source[0] >= count || source[1] >= count || source[2] >= count ||
            source[0] == source[1] || source[1] == source[2] || source[2] == source[0]) return data;
        vtkIdType face[3] = {static_cast<vtkIdType>(source[0]), static_cast<vtkIdType>(source[1]),
                             static_cast<vtkIdType>(source[2])};
        cells->InsertNextCell(3, face);
    }
    data->SetPoints(points);
    data->SetPolys(cells);
    return data;
}

// Cuts the shared mesh with a viewer plane. Voxel-face meshes have every face
// on a half-voxel plane, and the MPR's default planes through the volume
// centre land exactly there; a coplanar cut yields no lines (#377, found on
// the native run). The plane is moved by a fixed, invisible 1e-4 mm along its
// normal so the section is the voxel row just past the face.
inline vtkSmartPointer<vtkPolyData> HorosSEGSurfaceCut(vtkPolyData *mesh, const double origin[3], const double normal[3])
{
    const double nudge = 1e-4;
    double length = std::sqrt(normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2]);
    auto plane = vtkSmartPointer<vtkPlane>::New();
    if (!mesh || !(length > 0) || !std::isfinite(length)) return vtkSmartPointer<vtkPolyData>::New();
    plane->SetOrigin(origin[0] + nudge * normal[0] / length, origin[1] + nudge * normal[1] / length,
                     origin[2] + nudge * normal[2] / length);
    plane->SetNormal(normal[0], normal[1], normal[2]);
    auto cutter = vtkSmartPointer<vtkCutter>::New();
    cutter->SetCutFunction(plane); cutter->SetInputData(mesh); cutter->Update();
    vtkSmartPointer<vtkPolyData> output = cutter->GetOutput();
    return output;
}
#endif
