#!/usr/bin/env python3
"""Run the VR crop-capture block and flythrough import loop with controlled peers.

Actual Camera/Point3D/N3Geometry implementations are linked with ASan. Minimal
VTK peers distinguish applied planes from a stale editing box without a build
dependency. Native rendering/file-panel validation is recorded separately.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def block(path, method, anchor):
    source = (root / path).read_bytes().decode("latin1")
    start = source.index(anchor, source.index(method))
    opening = source.index("{", start)
    depth = 0
    for end in range(opening, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return source[start:end + 1]
    raise AssertionError("unterminated source block")


capture = block("Horos/Sources/VRView.mm", "- (Camera*) cameraWithThumbnail:", "if( croppingBox)")
imports = block("Horos/Sources/FlyThruStepsArrayController.m", "//IMPORT",
                "for (NSDictionary *cam in stepsXML)")
add = block("Horos/Sources/FlyThruStepsArrayController.m", "- (void)addObject:", "- (void)addObject:")
main = r'''
#import "Camera.h"
#include <vector>
#include <cassert>
struct vtkPlane {
    double point[3] = {}, normal[3] = {1,0,0};
    double *GetOrigin() { return point; }
    double *GetNormal() { return normal; }
};
struct vtkPlanes {
    std::vector<vtkPlane> data = std::vector<vtkPlane>(6);
    static vtkPlanes *New() { return new vtkPlanes; }
    void Delete() { delete this; }
    int GetNumberOfPlanes() { return (int)data.size(); }
    vtkPlane *GetPlane(int i) { return &data.at(i); }
};
struct vtkPlaneCollection : vtkPlanes {
    int GetNumberOfItems() { return GetNumberOfPlanes(); }
    vtkPlane *GetItem(int i) { return GetPlane(i); }
};
struct Box : vtkPlanes { void GetPlanes(vtkPlanes *p) { p->data = data; } };
struct Mapper {
    vtkPlaneCollection *planes = nullptr;
    vtkPlaneCollection *GetClippingPlanes() { return planes; }
};
struct Volume { Mapper mapper; Mapper *GetMapper() { return &mapper; } };
static Camera *capture(Box *croppingBox, Volume *volume) {
    Camera *cam = [[[Camera alloc] init] autorelease];
    CAPTURE_BLOCK
    return cam;
}
@interface Adapter : NSObject
- (void)setCurrentViewToCamera:(Camera*)camera;
- (NSImage*)getCurrentCameraImage:(BOOL)flag;
@end
@implementation Adapter
- (void)setCurrentViewToCamera:(Camera*)camera { }
- (NSImage*)getCurrentCameraImage:(BOOL)flag { return nil; }
@end
@interface Controller : NSObject
@property(retain) Adapter *FTAdapter;
@property(retain) Camera *currentCamera;
@end
@implementation Controller
- (void)dealloc { [_FTAdapter release]; [_currentCamera release]; [super dealloc]; }
@end
@interface Importer : NSArrayController {
@public Controller *flyThruController;
    NSTableView *tableview;
}
- (void)resetCameraIndexes;
- (void)loadSteps:(NSArray*)stepsXML;
@end
@implementation Importer
ADD_METHOD
- (void)resetCameraIndexes { }
- (void)loadSteps:(NSArray*)stepsXML { int count = 1; IMPORT_LOOP }
@end
int main() { @autoreleasepool {
    Box stale;
    Volume volume;
    vtkPlaneCollection applied;
    for (int i=0; i<6; ++i) {
        stale.data[i].point[0] = -100-i;
        applied.data[i].point[0] = 10+i*7;
        applied.data[i].normal[0] = i%2 ? -1 : 1;
    }
    volume.mapper.planes = &applied;
    Camera *current = capture(&stale, &volume);
    for (int i=0; i<6; ++i) {
        N3Plane p = [current.croppingPlanes[i] N3PlaneValue];
        assert(p.point.x == 10+i*7 && p.normal.x == (i%2 ? -1 : 1));
    }
    volume.mapper.planes = nullptr;
    Camera *fallback = capture(&stale, &volume);
    for (int i=0; i<6; ++i)
        assert([fallback.croppingPlanes[i] N3PlaneValue].point.x == -100-i);

    Controller *controller = [[[Controller alloc] init] autorelease];
    controller.FTAdapter = [[[Adapter alloc] init] autorelease];
    controller.currentCamera = fallback;
    Importer *importer = [[[Importer alloc] initWithContent:[NSMutableArray array]] autorelease];
    importer->flyThruController = controller;
    [importer loadSteps:@[[current exportToXML], [fallback exportToXML]]];
    NSArray *steps = [importer arrangedObjects];
    assert(steps.count == 2);
    assert([[steps[0] exportToXML] isEqual:[current exportToXML]]);
    assert([[steps[1] exportToXML] isEqual:[fallback exportToXML]]);
    assert([(Camera*)steps[0] index] == 1 && [(Camera*)steps[1] index] == 2);
    assert(steps[0] != current && steps[1] != fallback);
    // The Add button must still capture the current view, not an empty object.
    [importer addObject:[[[NSObject alloc] init] autorelease]];
    assert([[importer arrangedObjects] lastObject] == fallback);
    puts("PASS: applied crop beats stale widget, fallback works, import keeps decoded cameras, Add still captures");
} }
'''.replace("CAPTURE_BLOCK", capture).replace("ADD_METHOD", add).replace("IMPORT_LOOP", imports)

with tempfile.TemporaryDirectory(prefix="horos-camera-consumers-") as temp:
    folder = Path(temp)
    (folder / "main.mm").write_text(main)
    objects = []
    common = ["-fno-objc-arc", "-fsanitize=address", "-g", "-Wno-deprecated-declarations",
              "-include", "Cocoa/Cocoa.h", "-I", str(root / "Horos/Sources"),
              "-I", str(root / "Nitrogen/Sources")]
    for name in ("Horos/Sources/Camera.m", "Horos/Sources/Point3D.m",
                 "Nitrogen/Sources/N3Geometry.m"):
        obj = folder / (Path(name).stem + ".o")
        subprocess.run(["xcrun", "clang", *common, "-c", str(root / name), "-o", str(obj)], check=True)
        objects.append(str(obj))
    executable = folder / "test"
    subprocess.run(["xcrun", "clang++", "-std=c++14", *common, str(folder / "main.mm"),
                    *objects, "-framework", "Cocoa", "-framework", "QuartzCore",
                    "-framework", "Accelerate", "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
