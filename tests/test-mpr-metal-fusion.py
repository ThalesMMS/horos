#!/usr/bin/env python3
"""The 3D MPR reslices a fused series in Metal with the plane (#658).

An MPR opened from a fused viewer used to refuse Metal («Fusion keeps the
original renderer.»): VTK cast both planes. Now the fused series' plane is
resliced from its own volume, where VTK casts it, and handed to the host's
blending branch, which composes the two planes as before:

* the fused volume as VTK reads it - the float buffer it converts to 16 bits
  from, placed by the blending reader's origin and spacing through the blending
  volume's matrix, the loop of -mprVoxelToWorldTransform - and the value a ray
  that misses it reads back as (-blendingOFFSET16);
* the blending mapper's own ray-cast geometry (PrepareMPRGeometry on the
  blending volume), origin (getOrigin:... blendedView:YES) and sample distance;
* both planes in Metal or both with VTK, never mixed, with one reason;
* the plane handed over as the malloc-owned buffer VTK's path hands over, not
  copied through an intermediate NSData (#620); VTK renders the blended
  volume only when Metal did not reslice it;
* both reslices sample pixel (0, 0) at its centre. VTK casts each ray through
  the centre of its ray-cast pixel (ComputeRayInfo adds 1/viewport, "to center
  it"); -getOrigin: gives the image's upper-left corner. Checked here on those
  two formulas as the sources write them: the ray of pixel x lies at the corner
  plus (x + 0.5) pixels, for random viewports, image origins, sample distances
  and pixels. In the application the two engines' planes then match best
  unshifted, where they matched best half a pixel apart before
  (docs/issue-658-fusion.md).

`<git revision>` as an optional argument reads the sources from that revision,
the negative control.
"""
from pathlib import Path
import random
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
revision = sys.argv[1] if len(sys.argv) > 1 else None


def read(path):
    if revision:
        return subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1').replace('\r\n', '\n')


failures = []
bridge = read('Horos/Sources/MPRHostBridge.m')
view = read('Horos/Sources/MPRDCMView.m')
host = read('Horos/Sources/VRHostBridge.mm')
vr = read('Horos/Sources/VRView.mm')
vtk = read('VTK/Rendering/Volume/vtkFixedPointVolumeRayCastMapper.cxx')

# --- the bridge: fused plane, all or nothing, handed over -------------------
if 'Fusion keeps the original renderer' in bridge:
    failures.append('the MPR still refuses a fusion')
fused = bridge[bridge.find('horosMPRFusedPlane:(NSString **)reason {'):]
for piece, why in [('[vrView horosMPRFusedVolume]', 'the fused volume as VTK reads it'),
                   ('[vrView horosMPRFusedGeometryRefusalWidth:&width height:&height]', 'the blending mapper\'s geometry'),
                   ('[vrView getOrigin:position windowCentered:YES sliceMiddle:YES blendedView:YES]', 'the blended plane\'s origin'),
                   ('[vrView getResolution] * [vrView blendingImageSampleDistance]', 'the blended plane\'s spacing'),
                   ('thickness:[vrView getClippingRangeThicknessInMm]', 'the slab'),
                   ('projection:controller.clippingRangeMode', 'the mode'),
                   ('background:[volume[@"background"] floatValue]', 'the value of a missed ray')]:
    if not fused or piece not in fused[:fused.find('\n- (')]:
        failures.append('the fused plane does not take %s (%s)' % (why, piece))
copy = bridge[bridge.find('- (float *)horosMPRCopyImageWidth'):]
if 'if (self.blendingView && !fused) reslicer = nil;' not in copy:
    failures.append('a view may mix a Metal plane with a VTK fused plane')
success = copy[copy.find('into:image error:&error]) {'):copy.find('} else {')]
if 'objc_setAssociatedObject(self, &fusedPlaneKey, fused' not in success:
    failures.append('the fused plane is not kept for the blending branch once the plane succeeded')
take = bridge[bridge.find('- (float *)horosMPRTakeFusedImageWidth'):]
take = take[:take.find('\n}\n')]
if 'plane->pixels = NULL;' not in take or 'memcpy' in take or 'plane.bytes' in bridge:
    failures.append('the fused plane is copied on its way to the host instead of handed over (#620)')
if bridge.count('resliceWithOrigin:HorosMPRPixelCentre(position, cosines, spacing)') + \
        bridge.count('NSArray *origin = HorosMPRPixelCentre(position, cosines, spacing);') != 2:
    failures.append('a reslice does not sample pixel (0, 0) at its centre')
centre = re.search(r'static NSArray \*HorosMPRPixelCentre\(const float corner\[3\], const float cosines\[9\], double spacing\) \{\s*'
                   r'return @\[@\(corner\[0\] \+ 0\.5 \* spacing \* \(cosines\[0\] \+ cosines\[3\]\)\),\s*'
                   r'@\(corner\[1\] \+ 0\.5 \* spacing \* \(cosines\[1\] \+ cosines\[4\]\)\),\s*'
                   r'@\(corner\[2\] \+ 0\.5 \* spacing \* \(cosines\[2\] \+ cosines\[5\]\)\)\];', bridge)
if not centre:
    failures.append('the pixel centre is not the corner plus half a pixel along the row and the column')

# --- the view: Metal's fused plane first, VTK's only without it --------------
branch = view[view.find('if( blendingView)\n        {\n            [blendingView getWLWW:'):]
branch = branch[:branch.find('float porigin[ 3];')]
if not re.search(r'float \*blendedImagePtr = moveCenter \? nil : \[self horosMPRTakeFusedImageWidth: &w height: &h\];\s*'
                 r'if\( blendedImagePtr\)\s*isRGB = NO;\s*else\s*\[vrView renderBlendedVolume\];', branch):
    failures.append('the blending branch renders the fused volume with VTK even when Metal resliced it')
if not re.search(r'else if\( blendedImagePtr == nil\)\s*blendedImagePtr = \[vrView imageInFullDepthWidth: &w height: &h isRGB: &isRGB blendingView: YES\];', branch):
    failures.append('the blending branch reads VTK\'s plane over Metal\'s')

# --- the fused volume, placed as VTK places it ------------------------------
primary = vr[vr.find('- (NSArray *)mprVoxelToWorldTransform'):]
primary = primary[:primary.find('\n}\n')]
volume = host[host.find('- (NSDictionary *)horosMPRFusedVolume'):]
volume = volume[:volume.find('\n}\n')]
loop = re.compile(r'for \(int column = 0; column < 4; \+\+column\).*?\[transform addObject:@\(value\)\];', re.S)
primary_loop, fused_loop = loop.search(primary), loop.search(volume)
normal = lambda text: re.sub(r'\s+', ' ', text)
if not primary_loop or not fused_loop or normal(primary_loop.group(0)) != normal(fused_loop.group(0)):
    failures.append('the fused transform is not -mprVoxelToWorldTransform\'s loop')
for piece, why in [('vtkImageData *input = blendingReader->GetOutput();', 'the blending reader'),
                   ('vtkMatrix4x4 *matrix = blendingVolume->GetMatrix();', 'the blending volume\'s matrix'),
                   ('@"background": @(-blendingOFFSET16)', 'the value of a missed ray'),
                   ('[blendingController volumeData:i].bytes == blendingData', 'the buffer VTK converts from')]:
    if piece not in volume:
        failures.append('the fused volume does not use %s' % why)
geometry = host[host.find('- (NSString *)horosMPRFusedGeometryRefusalWidth'):]
if 'blendingVolumeMapper->PrepareMPRGeometry(aRenderer, blendingVolume)' not in geometry[:geometry.find('\n}\n')]:
    failures.append('the fused plane does not take the blending mapper\'s geometry')

# --- the pixel centre, on the formulas as VTK and VRView write them ----------
if not re.search(r'float offsetX = 1\.0 / static_cast<float>\(imageViewportSize\[0\]\);', vtk) or \
        not re.search(r'viewRay\[0\] = \(\(static_cast<float>\(x\) \+\s*static_cast<float>\(imageOrigin\[0\]\)\) /\s*'
                      r'imageViewportSize\[0\]\) \* 2\.0 - 1\.0 \+ offsetX;', vtk):
    failures.append('VTK no longer casts through the ray pixel\'s centre as this test models it')
origin = vr[vr.find('- (void) getOrigin: (float *) origin windowCentered:(BOOL) wc sliceMiddle:(BOOL) sliceMiddle blendedView:(BOOL) blendedView'):]
if 'x1 = static_cast<int> ( viewport[0] * static_cast<double>(renWinSize[0]) + static_cast<double>(imageOrigin[0]) * sampleDistance);' not in origin \
        or 'double x = ((double) x1 - (double) renWinSize[ 0]/2.);' not in origin:
    failures.append('-getOrigin: no longer gives the image\'s corner as this test models it')
if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)

rng = random.Random(658)
checked = 0
for _ in range(20000):
    sample = rng.choice([1.0, 1.3, 1.6, 2.0, 2.5, 4.0, 7.0])
    viewport = rng.randint(16, 900)                   # ray pixels across the viewport
    window = viewport * sample                        # window pixels across it
    image_origin = rng.randint(0, viewport // 2)      # first in-use ray pixel
    x = rng.randint(0, viewport - image_origin - 1)
    # VTK: normalised device coordinate of pixel x's ray, then window pixels from the left edge.
    ndc = ((x + image_origin) / viewport) * 2.0 - 1.0 + 1.0 / viewport
    ray = (ndc + 1.0) / 2.0 * window
    # VRView: the corner, int(imageOrigin * sampleDistance) window pixels from the left edge.
    corner = int(image_origin * sample)
    # The reslicer samples pixel x at the corner plus (x + 0.5) pixels of `sample` window pixels.
    centre = corner + (x + 0.5) * sample
    if abs(ray - centre) > 1e-6 * window + abs(image_origin * sample - corner):
        print('FAIL: pixel %d of a %d-pixel viewport at %g: VTK casts at %.6f, the reslice samples %.6f' % (x, viewport, sample, ray, centre))
        raise SystemExit(1)
    checked += 1
print('PASS: the fused plane is resliced with the plane from the fused volume where VTK casts it, both or neither, handed over '
      'without a copy; %d ray positions at the pixel centre the reslice samples' % checked)
