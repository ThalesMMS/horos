#!/usr/bin/env python3
"""Unfusing a 3D view leaves the crop callback no deleted volume to reach (#673).

When a series is fused, `setBlendingPixSource:` hands the fused `vtkVolume` to
the crop callback, which then clips that volume's mapper with the crop planes
too. Unfusing (the fused 2D viewer closes) deleted the volume but left the
callback holding it, and the next run of the callback - every engine switch
runs it - read the mapper of freed memory: `EXC_BAD_ACCESS` in
`vtkMyCallbackVR::Execute`.

The production callback class and the production unfuse block are compiled
here against stand-in VTK types whose deleted volume fails the test when its
mapper is asked for. The run fuses, crops (both mappers take the planes),
unfuses and crops again, as the engine switch does: the primary mapper still
takes the planes and nothing reaches the deleted volume.

`<git revision>` as an optional argument reads the source from that revision,
the negative control.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/VRView.mm'
source = (subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]) if len(sys.argv) > 1
          else (root / path).read_bytes()).decode('latin1')


def braced(text, start):
    """The text from `start` to the brace that closes the first one after it."""
    depth, index = 0, text.index('{', start)
    while True:
        if text[index] == '{': depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0: return text[start:index + 1]
        index += 1


callback_start = source.index('class vtkMyCallbackVR : public vtkCommand')
callback = source[callback_start:source.index('\n};', callback_start) + 3]
setter = source.index('-(void) setBlendingPixSource:(ViewerController*) bC')
unfuse = braced(source, source.index('if( blendingVolume)', source.index('    else\n    {', setter)))

harness = r'''
#import <Foundation/Foundation.h>
#include <cstdio>
#include <cstdlib>
struct vtkObject { virtual ~vtkObject() {} };
struct vtkCommand : vtkObject { virtual void Execute(vtkObject *, unsigned long, void *) = 0; };
struct vtkPlanes : vtkObject { static vtkPlanes *New() { return new vtkPlanes; } void Delete() { delete this; } };
struct vtkVolumeMapper : vtkObject {
    int clipped = 0; bool deleted = false;
    void SetClippingPlanes(vtkPlanes *) { if (deleted) { fprintf(stderr, "FAIL: a deleted mapper was clipped\n"); exit(1); } ++clipped; }
    void Delete() { deleted = true; }
};
typedef vtkVolumeMapper vtkHorosFixedPointVolumeRayCastMapper;
typedef vtkVolumeMapper vtkGPUVolumeRayCastMapper;
struct vtkVolume : vtkObject {
    vtkVolumeMapper *mapper = nullptr; bool deleted = false;
    vtkVolumeMapper *GetMapper() {
        if (deleted) { fprintf(stderr, "FAIL: the crop callback reached the deleted fused volume\n"); exit(1); }
        return mapper;
    }
    void Delete() { deleted = true; }
};
struct vtkBoxWidget : vtkObject {
    vtkVolume *prop = nullptr;
    vtkVolume *GetProp3D() { return prop; }
    void GetPlanes(vtkPlanes *) {}
    void SetHandleSize(double) {}
};
struct vtkRenderer { void RemoveVolume(vtkVolume *) {} };
struct Deletable { bool deleted = false; void Delete() { deleted = true; } };
typedef Deletable vtkPiecewiseFunction, vtkVolumeProperty, vtkColorTransferFunction, vtkImageImport;

CALLBACK

@interface Harness : NSObject {
@public
    vtkVolume *blendingVolume; vtkMyCallbackVR *cropcallback; vtkRenderer *aRenderer;
    vtkHorosFixedPointVolumeRayCastMapper *blendingVolumeMapper; vtkGPUVolumeRayCastMapper *blendingTextureMapper;
    vtkPiecewiseFunction *blendingOpacityTransferFunction; vtkVolumeProperty *blendingVolumeProperty;
    vtkColorTransferFunction *blendingColorTransferFunction; vtkImageImport *blendingReader;
    char *blendingData8; NSArray *blendingPixList;
}
- (void)unfuse;
@end
@implementation Harness
- (void)unfuse {
UNFUSE
}
@end

int main() { @autoreleasepool {
    vtkVolumeMapper primaryMapper, fusedMapper;
    vtkVolume primary, *fused = new vtkVolume;
    primary.mapper = &primaryMapper; fused->mapper = &fusedMapper;
    vtkBoxWidget widget; widget.prop = &primary;
    Harness *h = [Harness new];
    h->aRenderer = new vtkRenderer;
    h->cropcallback = vtkMyCallbackVR::New();
    h->cropcallback->setBlendingVolume(nullptr);
    h->blendingVolume = fused; h->blendingVolumeMapper = &fusedMapper; h->blendingTextureMapper = nullptr;
    h->blendingOpacityTransferFunction = new Deletable; h->blendingVolumeProperty = new Deletable;
    h->blendingColorTransferFunction = new Deletable; h->blendingReader = new Deletable;
    h->blendingData8 = (char *)malloc(16); h->blendingPixList = [[NSArray alloc] init];
    h->cropcallback->setBlendingVolume(h->blendingVolume);

    h->cropcallback->Execute(&widget, 0, nullptr);
    if (primaryMapper.clipped != 1 || fusedMapper.clipped != 1) { fprintf(stderr, "FAIL: fused, the crop does not reach both mappers\n"); return 1; }
    [h unfuse];
    if (h->blendingVolume || !fused->deleted) { fprintf(stderr, "FAIL: the unfuse block no longer deletes the fused volume\n"); return 1; }
    h->cropcallback->Execute(&widget, 0, nullptr);
    if (primaryMapper.clipped != 2) { fprintf(stderr, "FAIL: after unfusing, the crop no longer reaches the primary mapper\n"); return 1; }
    printf("ok\n");
} return 0; }
'''.replace('CALLBACK', callback).replace('UNFUSE', unfuse)

with tempfile.TemporaryDirectory() as work:
    program = Path(work) / 'unfuse.mm'
    program.write_text(harness)
    binary = Path(work) / 'unfuse'
    built = subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fno-objc-arc', '-x', 'objective-c++', str(program),
                            '-framework', 'Foundation', '-o', str(binary)], capture_output=True, text=True)
    if built.returncode:
        sys.exit('FAIL: the harness does not build:\n' + built.stderr[-3000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    if run.returncode or run.stdout.strip() != 'ok':
        sys.exit((run.stderr or run.stdout).strip() or 'FAIL: the harness stopped with %d' % run.returncode)
print('ok: unfusing clears the crop callback before the fused volume is deleted (#673)')
