#!/usr/bin/env python3
"""Exercise the actual Camera/Point3D/N3Geometry plist codec (#595)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = r'''
#import "Camera.h"
#include <math.h>
static int failures = 0;
#define CHECK(c, m) do { if (!(c)) { fprintf(stderr, "FAIL: %s\n", m); failures++; } } while (0)

static BOOL samePlane(N3Plane a, N3Plane b) {
    return N3VectorDistance(a.point, b.point) < 1e-12 &&
           N3VectorDistance(a.normal, b.normal) < 1e-12;
}

int main(void) { @autoreleasepool {
    Camera *original = [[[Camera alloc] init] autorelease];
    original.position = [Point3D pointWithX:12.25 y:-19.5 z:450.75];
    original.focalPoint = [Point3D pointWithX:1.5 y:2.25 z:3.75];
    original.viewUp = [Point3D pointWithX:0 y:0 z:1];
    original.clippingRangeNear = 2.25;
    original.clippingRangeFar = 512.5;
    original.viewAngle = 30;
    original.eyeAngle = 2;
    original.parallelScale = 74.25;
    original.wl = -40.25;
    original.ww = 350.5;
    original.fusionPercentage = 63.75;
    N3Vector normals[6] = {{.6,.8,0}, {-.6,-.8,0}, {-.8,.6,0},
                           {.8,-.6,0}, {0,0,1}, {0,0,-1}};
    N3Plane expected[6];
    NSMutableDictionary *independent = [NSMutableDictionary dictionary];
    CHECK(original.croppingPlanes.count == 6, "default plane count");
    for (int i=0; i<6; ++i) {
        CHECK(samePlane([original.croppingPlanes[i] N3PlaneValue], N3PlaneInvalid),
              "default plane must be invalid");
        expected[i] = N3PlaneMake(N3VectorMake(-11.5+i*7.25, 23.125-i, 5.25+i*2), normals[i]);
        original.croppingPlanes[i] = [NSValue valueWithN3Plane:expected[i]];
        independent[[NSString stringWithFormat:@"croppingPlanes %d", i]] =
            [(id)N3PlaneCreateDictionaryRepresentation(expected[i]) autorelease];
    }
    NSDictionary *exported = [original exportToXML];
    NSUInteger planeKeys = 0;
    for (NSString *key in exported) if ([key hasPrefix:@"croppingPlanes "]) ++planeKeys;
    CHECK(planeKeys == 6, "export must contain six distinct plane keys");
    for (int i=0; i<6; ++i) {
        NSString *key = [NSString stringWithFormat:@"croppingPlanes %d", i];
        CHECK([exported[key] isEqual:independent[key]], "exported plane order/value");
    }

    // Independently populated input catches the loader even if the exporter is broken.
    Camera *loaded = [[[Camera alloc] initWithDictionary:independent] autorelease];
    CHECK(loaded.croppingPlanes.count == 6, "loader must initialize its plane collection");
    if (loaded.croppingPlanes.count == 6) for (int i=0; i<6; ++i)
        CHECK(samePlane([loaded.croppingPlanes[i] N3PlaneValue], expected[i]), "loaded plane");

    // The real flythrough wire format is a plist array under Step Cameras.
    NSDictionary *wire = @{@"Step Cameras": @[exported, exported]};
    NSError *error = nil;
    NSData *xml = [NSPropertyListSerialization dataWithPropertyList:wire
        format:NSPropertyListXMLFormat_v1_0 options:0 error:&error];
    CHECK(xml != nil && error == nil, "serialize flythrough XML plist");
    NSDictionary *decoded = [NSPropertyListSerialization propertyListWithData:xml
        options:NSPropertyListImmutable format:NULL error:&error];
    CHECK([decoded[@"Step Cameras"] count] == 2, "decode two keyframes");
    for (NSDictionary *step in decoded[@"Step Cameras"]) {
        Camera *roundtrip = [[[Camera alloc] initWithDictionary:step] autorelease];
        CHECK([[roundtrip exportToXML] isEqual:exported], "all supported camera fields round-trip");
    }

    // Old exports only kept the last plane in key 0; missing planes stay invalid.
    NSDictionary *legacy = @{@"croppingPlanes 0": independent[@"croppingPlanes 5"]};
    Camera *old = [[[Camera alloc] initWithDictionary:legacy] autorelease];
    CHECK(old.croppingPlanes.count == 6, "legacy collection must have six slots");
    if (old.croppingPlanes.count == 6) {
        CHECK(samePlane([old.croppingPlanes[0] N3PlaneValue], expected[5]), "retain legacy key as stored");
        for (int i=1; i<6; ++i)
            CHECK(samePlane([old.croppingPlanes[i] N3PlaneValue], N3PlaneInvalid), "do not invent missing planes");
    }
    for (NSDictionary *partial in @[@{}, @{@"croppingPlanes 2": @{}},
                                   @{@"croppingPlanes 4": @"invalid"}]) {
        Camera *empty = [[[Camera alloc] initWithDictionary:partial] autorelease];
        CHECK(empty.croppingPlanes.count == 6, "empty/incomplete input slots");
        for (NSValue *v in empty.croppingPlanes)
            CHECK(samePlane(v.N3PlaneValue, N3PlaneInvalid), "incomplete plane is invalid");
    }
    if (!failures) puts("PASS: six ordered planes, independent loader, two-keyframe plist round-trip, legacy defaults");
    return failures ? 1 : 0;
} }
'''

with tempfile.TemporaryDirectory(prefix="horos-camera-roundtrip-") as temp:
    folder = Path(temp)
    (folder / "main.m").write_text(main)
    executable = folder / "test"
    subprocess.run([
        "xcrun", "clang", "-fno-objc-arc", "-fsanitize=address", "-g",
        "-Wno-deprecated-declarations", "-include", "Cocoa/Cocoa.h",
        "-I", str(root / "Horos/Sources"), "-I", str(root / "Nitrogen/Sources"),
        str(root / "Horos/Sources/Camera.m"), str(root / "Horos/Sources/Point3D.m"),
        str(root / "Nitrogen/Sources/N3Geometry.m"), str(folder / "main.m"),
        "-framework", "Cocoa", "-framework", "QuartzCore", "-framework", "Accelerate",
        "-o", str(executable),
    ], check=True)
    subprocess.run([str(executable)], check=True)
