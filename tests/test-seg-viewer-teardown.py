#!/usr/bin/env python3
"""Run the real SEG close handler across reusable windows and retained VR renderers."""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline')
args = parser.parse_args()
path = 'Horos/Sources/ViewerSEGSurface.mm'
source = (subprocess.check_output(['git','show',f'{args.baseline}:{path}'],cwd=root).decode()
          if args.baseline else (root/path).read_text())
signature = '- (void)windowWillClose:(NSNotification *)note'
body = ''
if signature in source:
    start = source.index('{', source.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    body = source[start + 1:end - 1]

driver = r'''
#import <Foundation/Foundation.h>
#include <cassert>
#include <memory>
#include <vector>
struct vtkRenderer { int removals = 0; void RemoveActor(int) { removals++; } };
struct RendererPointer {
    std::shared_ptr<vtkRenderer> value;
    vtkRenderer *GetPointer() const { return value.get(); }
};
@interface Window : NSObject
@property(nonatomic,strong) id surface;
@property(nonatomic,strong) id windowController;
@end
@implementation Window @end
@interface Surface : NSObject
@property(nonatomic,strong) Window *boundWindow;
@property(nonatomic,strong) Surface *boundView;
- (void)prepareForRelease;
@end
@implementation Surface
- (void)prepareForRelease { self.boundWindow = nil; self.boundView = nil; }
@end
@interface VRView : NSObject { @public std::shared_ptr<vtkRenderer> backing; }
- (vtkRenderer *)renderer;
@end
@implementation VRView
- (vtkRenderer *)renderer { return backing.get(); }
@end
@interface VRController : NSObject
@property(nonatomic,strong) VRView *view;
@end
@implementation VRController @end
@interface Controller : NSObject {
@public Surface *_surfaceView;
    std::vector<int> _actors;
    std::vector<RendererPointer> _externalRenderers;
}
@property(nonatomic,strong) Window *window;
- (BOOL)ownsWindowController:(id)controller;
- (void)windowWillClose:(NSNotification *)note;
@end
@implementation Controller
- (BOOL)ownsWindowController:(id)controller { return YES; }
- (void)windowWillClose:(NSNotification *)note { BODY }
@end
int main() { @autoreleasepool {
    __weak Window *weakWindow;
    __weak Surface *weakSurface;
    @autoreleasepool {
        Controller *owner = [Controller new]; owner.window = [Window new];
        owner->_surfaceView = [Surface new]; owner.window.surface = owner->_surfaceView;
        weakWindow = owner.window; weakSurface = owner->_surfaceView;
        for (int close = 0; close < 3; close++) {
            owner->_surfaceView.boundWindow = owner.window;
            owner->_surfaceView.boundView = owner->_surfaceView;
            // ROIVolumeView unregisters its own observer at the first close.
            if (close == 0) [owner->_surfaceView prepareForRelease];
            [owner windowWillClose:[NSNotification notificationWithName:@"close" object:owner.window]];
            if (owner->_surfaceView.boundWindow || owner->_surfaceView.boundView) {
                fprintf(stderr,"FAIL: reused SEG window keeps VTK view/window bindings after close %d\n",close+1);
                return 1;
            }
        }
        VRController *vr = [VRController new]; vr.view = [VRView new];
        vr.view->backing = std::make_shared<vtkRenderer>();
        std::weak_ptr<vtkRenderer> weakRenderer = vr.view->backing;
        owner->_externalRenderers.push_back({vr.view->backing}); owner->_actors.push_back(1);
        Window *external = [Window new]; external.windowController = vr;
        [owner windowWillClose:[NSNotification notificationWithName:@"close" object:external]];
        assert(vr.view->backing->removals == 1 && owner->_externalRenderers.empty());
        vr.view->backing.reset(); assert(weakRenderer.expired());
    }
    assert(!weakWindow && !weakSurface);
    puts("PASS: actual close handler releases repeated VTK window bindings and closed VR renderer ownership");
} }
'''.replace('BODY',body)
with tempfile.TemporaryDirectory(prefix='horos-seg-teardown-') as folder:
    tmp = Path(folder); (tmp/'probe.mm').write_text(driver)
    subprocess.run(['xcrun','clang++','-std=c++11','-fobjc-arc','-framework','Foundation',
                    str(tmp/'probe.mm'),'-o',str(tmp/'probe')],check=True)
    subprocess.run([str(tmp/'probe')],check=True)

if not args.baseline:
    assert 'selector:@selector(sourceClosed:) name:OsirixViewerWillChangeNotification object:viewer' in source
    assert 'selector:@selector(sourceVolumeChanged:) name:OsirixUpdateVolumeDataNotification' in source
    assert 'image.frameID.integerValue + 1' in source and 'initWithVolume:volume sourceFrames:references' in source
