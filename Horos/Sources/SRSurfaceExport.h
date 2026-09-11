#pragma once
#include <vtkActor.h>
#include <vtkAppendPolyData.h>
#include <vtkPolyData.h>
#include <vtkPolyDataMapper.h>
#include <vtkSmartPointer.h>
#include <vtkTransform.h>
#include <vtkTransformPolyDataFilter.h>

// STL has no actor transform: bake the same world coordinates used by OBJ.
inline vtkSmartPointer<vtkPolyData> HorosSurfaceExportGeometry(vtkActor *const *actors, int count)
{
    auto combined = vtkSmartPointer<vtkAppendPolyData>::New();
    int inputs = 0;
    for (int i = 0; i < count; ++i) {
        auto actor = actors[i];
        if (!actor || !actor->GetVisibility()) continue;
        auto mapper = vtkPolyDataMapper::SafeDownCast(actor->GetMapper());
        if (!mapper) continue;
        mapper->Update();
        if (!mapper->GetInput()) continue;
        auto transform = vtkSmartPointer<vtkTransform>::New();
        transform->SetMatrix(actor->GetMatrix());
        auto geometry = vtkSmartPointer<vtkTransformPolyDataFilter>::New();
        geometry->SetTransform(transform);
        geometry->SetInputData(mapper->GetInput());
        combined->AddInputConnection(geometry->GetOutputPort());
        ++inputs;
    }
    auto result = vtkSmartPointer<vtkPolyData>::New();
    if (inputs) {
        combined->Update();
        result->DeepCopy(combined->GetOutput());
    }
    return result;
}
