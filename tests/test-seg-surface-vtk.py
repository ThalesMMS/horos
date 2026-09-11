#!/usr/bin/env python3
"""Exercise the production Swift mask extractor and its VTK bridge, including borders."""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-root', type=Path, default=root)
parser.add_argument('--roi-source', type=Path, default=root/'Horos/Sources/ROIVolumeView.mm')
args = parser.parse_args()
install = next((args.build_root / f'build/Build/Intermediates.noindex/Horos.build/{mode}/VTK.build/Install'
                for mode in ('Debug', 'Release')
                if (args.build_root / f'build/Build/Intermediates.noindex/Horos.build/{mode}/VTK.build/Install/lib').is_dir()), None)
if install is None:
    print('needs built VTK libraries; optionally supply --build-root CHECKOUT')
    raise SystemExit(2)

# Bounds and the volume/topology tolerance are fixed before either extraction.
# All fixtures touch x/y/z image boundaries: the former Black 3D Frame lost them.
swift = r'''
import Foundation
import simd
func expect(_ ok: Bool, _ reason: String) { if !ok { fatalError(reason) } }
let out = URL(fileURLWithPath: CommandLine.arguments[1])
var expected = ""
for (name, size, expectedCount, components, euler) in [
    ("solid", 4, 64, 1, 2), ("tube", 4, 48, 1, 0),
    ("cavity", 4, 56, 2, 4), ("separate", 5, 16, 2, 4)] {
    var frames: [Data] = []
    for z in 0..<size {
        var plane = Data(repeating: 0, count: size * size)
        for y in 0..<size { for x in 0..<size {
            let inside: Bool
            switch name {
            case "tube": inside = x == 0 || y == 0 || x == size - 1 || y == size - 1
            case "cavity": inside = x == 0 || y == 0 || z == 0 || x == size - 1 || y == size - 1 || z == size - 1
            case "separate": inside = (x < 2 && y < 2 && z < 2) || (x >= 3 && y >= 3 && z >= 3)
            default: inside = true
            }
            if inside { plane[y * size + x] = 1 }
        }}
        frames.append(plane)
    }
    let offsets = (0..<size).map { NSNumber(value: Double($0) * 3) }
    let surface = HorosSEGSurface.mesh(binaryFrames: frames, rows: size, columns: size,
        spacingX: 1.5, spacingY: 2, frameOffsets: offsets, singleFrameThickness: 3)!
    expect(surface.closed, "closed \(name)")
    let volume = Double(expectedCount) * 1.5 * 2 * 3 / 1000
    expect(abs(surface.meshVolumeCm3 - volume) < 1e-12, "Swift volume \(name)")
    expect(abs(surface.maskVolumeCm3 - volume) < 1e-12, "mask volume \(name)")
    try surface.vertices.write(to: out.appendingPathComponent(name + ".points"))
    try surface.triangles.write(to: out.appendingPathComponent(name + ".faces"))
    expected += "\(name) \(volume * 1000) \(components) \(euler) \(size)\n"
}
try expected.write(to: out.appendingPathComponent("expected.txt"), atomically: true, encoding: .utf8)

// Oblique and translated patient coordinates, asymmetric voxel spacing, actual
// nonuniform plane centres: origin is a sample centre, never its lower corner.
let geometry = DicomSEGGeometry(rows: 1, columns: 1, frames: 3,
    spacingRow: 2, spacingCol: 1.5, sliceThickness: 3, origin: [100, -20, 8],
    orientation: [0, 1, 0, -1, 0, 0], frameOfReferenceUID: "synthetic",
    frameOrigins: [[100, -20, 8], [100, -20, 10], [100, -20, 15]])
let segment = DicomSEGSegment(number: 1, label: "oblique", trackingUID: "synthetic",
    color: (1,0,0), visible: true, kind: .binary, algorithm: "MANUAL", provenance: "synthetic",
    referencedSOPInstanceUIDs: [], frames: [Data([1]),Data([1]),Data([1])], maximumFractionalValue: 1)
let mesh = HorosSEGSurface.extract(segment: segment, geometry: geometry)
let minPoint = mesh.vertices.reduce(SIMD3<Double>(repeating: .infinity), simd_min)
let maxPoint = mesh.vertices.reduce(SIMD3<Double>(repeating: -.infinity), simd_max)
expect(simd_length(minPoint - SIMD3(99, -20.75, 7)) < 1e-12, "patient lower boundaries")
expect(simd_length(maxPoint - SIMD3(101, -19.25, 17.5)) < 1e-12, "patient upper boundaries")
expect(abs(HorosSEGSurface.maskVolumeCm3(segment: segment, geometry: geometry) - 0.0315) < 1e-12, "nonuniform mask volume")
expect(abs(ROISurfaceAlgorithm.volumeCm3(mesh)! - 0.0315) < 1e-12, "nonuniform mesh volume")
let pin = mesh.vertices[0]
expect(HorosSEGSurface.refine(mesh, keeping: [pin]).vertices.contains(pin), "pinned landmark unchanged")
expect(HorosSEGSurface.mesh(binaryFrames:[Data([1])], rows:1, columns:1,
    spacingX:1, spacingY:1, frameOffsets:[NSNumber(value: Double.nan)], singleFrameThickness:1) == nil, "invalid offset")
expect(HorosSEGSurface.mesh(binaryFrames:[Data([1]),Data([1])], rows:1, columns:1,
    spacingX:1, spacingY:1, frameOffsets:[0,0], singleFrameThickness:1) == nil, "coincident planes")
print("PASS: shared Swift mesh preserves patient boundaries, mask volume and pinned landmark")
'''
# No mesh reconstruction in this driver: exactly the header used by ROIVolumeView.
cpp = r'''
#import "SEGSurfaceVTK.h"
#include <vtkFeatureEdges.h>
#include <vtkCutter.h>
#include <vtkPlane.h>
#include <vtkPolyDataConnectivityFilter.h>
#include <vtkMassProperties.h>
#include <set>
#include <fstream>
#include <string>
#include <cassert>
int main(int argc, char **argv) { @autoreleasepool {
    std::string directory=argv[1], name; double volume; int components, euler, size;
    std::ifstream expected(directory+"/expected.txt");
    while(expected >> name >> volume >> components >> euler >> size) {
        auto points=[NSData dataWithContentsOfFile:@((directory+"/"+name+".points").c_str())];
        auto triangles=[NSData dataWithContentsOfFile:@((directory+"/"+name+".faces").c_str())];
        auto data=HorosSEGSurfacePolyData(points, triangles);
        assert(data->GetNumberOfPolys()>0);
        auto edges=vtkSmartPointer<vtkFeatureEdges>::New();
        edges->SetInputData(data);edges->BoundaryEdgesOn();edges->NonManifoldEdgesOn();
        edges->FeatureEdgesOff();edges->ManifoldEdgesOff();edges->Update();
        assert(edges->GetOutput()->GetNumberOfCells()==0);
        auto connectivity=vtkSmartPointer<vtkPolyDataConnectivityFilter>::New();
        connectivity->SetInputData(data);connectivity->SetExtractionModeToAllRegions();connectivity->Update();
        assert(connectivity->GetNumberOfExtractedRegions()==components);
        std::set<std::pair<vtkIdType,vtkIdType>> undirected;
        vtkIdType count,*ids;data->GetPolys()->InitTraversal();
        while(data->GetPolys()->GetNextCell(count,ids)) {
            assert(count==3);
            for(int i=0;i<3;++i) undirected.insert(std::minmax(ids[i],ids[(i+1)%3]));
        }
        assert(data->GetNumberOfPoints()-undirected.size()+data->GetNumberOfPolys()==euler);
        auto mass=vtkSmartPointer<vtkMassProperties>::New();mass->SetInputData(data);mass->Update();
        assert(fabs(mass->GetVolume()-volume)<1e-8);
        double bounds[6]; data->GetBounds(bounds);
        assert(fabs(bounds[0]+0.75)<1e-12 && fabs(bounds[1]-(size-0.5)*1.5)<1e-12);
        assert(fabs(bounds[2]+1)<1e-12 && fabs(bounds[3]-(size-0.5)*2)<1e-12);
        assert(fabs(bounds[4]+1.5)<1e-12 && fabs(bounds[5]-(size-0.5)*3)<1e-12);
        printf("PASS: VTK %s closed, components=%d, Euler=%d, volume=%.6f mm3\n",name.c_str(),components,euler,mass->GetVolume());
        auto plane=vtkSmartPointer<vtkPlane>::New();plane->SetOrigin(0,0,3);plane->SetNormal(0,0,1);
        auto cut=vtkSmartPointer<vtkCutter>::New();cut->SetInputData(data);cut->SetCutFunction(plane);cut->Update();
        auto contour=cut->GetOutput();contour->GetLines()->InitTraversal();double length=0;
        while(contour->GetLines()->GetNextCell(count,ids))for(vtkIdType i=1;i<count;++i) {
            double a[3],b[3];contour->GetPoint(ids[i-1],a);contour->GetPoint(ids[i],b);
            assert(fabs(a[2]-3)<1e-12 && fabs(b[2]-3)<1e-12);
            length+=hypot(hypot(a[0]-b[0],a[1]-b[1]),a[2]-b[2]);
        }
        double expectedLength=name=="solid"?28:(name=="separate"?14:42);
        assert(fabs(length-expectedLength)<1e-9);
        // The MPR's default planes sit on voxel faces (z=1.5 here); the shared cut
        // must still return the section of the row just past the face.
        double faceOrigin[3]={0,0,1.5}, faceNormal[3]={0,0,1};
        auto faceCut=HorosSEGSurfaceCut(data,faceOrigin,faceNormal);faceCut->GetLines()->InitTraversal();double faceLength=0;
        while(faceCut->GetLines()->GetNextCell(count,ids))for(vtkIdType i=1;i<count;++i) {
            double a[3],b[3];faceCut->GetPoint(ids[i-1],a);faceCut->GetPoint(ids[i],b);
            assert(fabs(a[2]-1.5)<1e-3 && fabs(b[2]-1.5)<1e-3);
            faceLength+=hypot(a[0]-b[0],a[1]-b[1]);
        }
        assert(fabs(faceLength-expectedLength)<1e-9);
        double zeroNormal[3]={0,0,0};
        assert(HorosSEGSurfaceCut(data,faceOrigin,zeroNormal)->GetNumberOfLines()==0);
        uint64_t invalid[]={UINT64_MAX,1,2};
        assert(HorosSEGSurfacePolyData(points,[NSData dataWithBytes:invalid length:sizeof(invalid)])->GetNumberOfPoints()==0);
        assert(HorosSEGSurfacePolyData([points subdataWithRange:NSMakeRange(0,points.length-1)],triangles)->GetNumberOfPoints()==0);
    }
    assert(HorosSEGSurfacePolyData(nil,nil)->GetNumberOfPoints()==0);
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-seg-vtk-') as folder:
    tmp = Path(folder)
    (tmp/'main.swift').write_text(swift)
    (tmp/'test.mm').write_text(cpp)
    subprocess.run(['xcrun', 'swiftc', *[str(root/'Horos/Sources'/name) for name in
        ('HorosSEGSurface.swift', 'DicomSEG.swift', 'ROISurfaceAlgorithm.swift')],
        str(tmp/'main.swift'), '-o', str(tmp/'extract')], check=True)
    subprocess.run([str(tmp/'extract'), str(tmp)], check=True)
    libs = sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ('vtkFiltersCore', 'vtksys', 'vtkdoubleconversion'):
        libs += list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun', 'clang++', '-std=c++11', '-fsanitize=address,undefined',
        '-I'+str(install/'include'), '-I'+str(root/'Horos/Sources'), str(tmp/'test.mm'),
        *map(str,libs), '-framework', 'Foundation', '-o', str(tmp/'test')], check=True)
    subprocess.run([str(tmp/'test'), str(tmp)], check=True)

source = args.roi_source.read_bytes().decode('latin1')
assert '// Iso Contour:' in source, 'legacy border-erasing Iso Contour must use the shared extractor'
iso = source.split('// Iso Contour:')[1].split('// Delaunay')[0]
assert 'HorosSEGSurface meshForBinaryFrames:' in iso
assert 'HorosSEGSurfacePolyData(surface.vertices, surface.triangles)' in iso
assert 'z = 1;' not in iso and 'count]-1' not in iso
assert 'clipMin:NSMakePoint(0, 0) clipMax:NSMakePoint(p.pwidth, p.pheight)' in iso
assert 'vtkTextureMapToSphere' not in iso and 'vtkDelaunay' not in iso
print('PASS: active ROIVolumeView uses the tested shared extractor and keeps all border voxels')
