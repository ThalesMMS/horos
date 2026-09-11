#import "ViewerController.h"
#import "ViewerVolumeSession.h"
#import "Horos-Swift.h"
#import "ROIVolumeView.h"
#import "DCMView.h"
#import "DicomImage.h"
#import "Notifications.h"
#import "VRController.h"
#import "VRView.h"
#import <objc/runtime.h>
#import <OpenGL/gl.h>
#include "SEGSurfaceVTK.h"
#include <vtkCutter.h>
#include <vtkPlane.h>
#include <map>
#include <vector>

static char SEGSessionKey, SEGControllerKey;

@protocol HorosSEGViewerOwner <NSObject>
- (ViewerController *)viewerController;
- (ViewerController *)viewer;
- (ViewerController *)viewer2D;
@end

@interface ViewerController (SEGSurface)
- (IBAction)showSEGSurfaces:(id)sender;
@end

@interface HorosSEGSurfaceController : NSWindowController <NSTableViewDataSource, NSTableViewDelegate>
{
    ViewerController *_viewer; // owner; cleared by its close notification
    HorosVolumeSession *_volume;
    HorosSEGViewerSession *_session;
    NSTableView *_table;
    NSTextField *_name;
    NSColorWell *_color;
    NSSlider *_opacity;
    NSButton *_visible;
    ROIVolumeView *_surfaceView;
    BOOL _cameraInitialized;
    std::vector<vtkSmartPointer<vtkActor>> _actors;
    std::vector<vtkSmartPointer<vtkRenderer>> _externalRenderers;
    std::map<unsigned short, vtkSmartPointer<vtkPolyData>> _meshes;
}
- (id)initWithViewer:(ViewerController *)viewer volume:(HorosVolumeSession *)volume;
- (BOOL)usesVolume:(HorosVolumeSession *)volume;
- (void)sourceClosed:(NSNotification *)note;
@end

@implementation ViewerController (SEGSurface)
- (IBAction)showSEGSurfaces:(id)sender
{
    HorosVolumeSession *volume = [self horosVolumeSession];
    if (!volume || volume.isStale) return;
    HorosSEGSurfaceController *controller = objc_getAssociatedObject(self, &SEGControllerKey);
    if (controller && ![controller usesVolume:volume]) { [controller sourceClosed:nil]; controller = nil; }
    if (!controller) {
        controller = [[[HorosSEGSurfaceController alloc] initWithViewer:self volume:volume] autorelease];
        objc_setAssociatedObject(self, &SEGControllerKey, controller, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    [controller showWindow:sender];
    [controller.window makeKeyAndOrderFront:sender];
}
@end

@implementation HorosSEGSurfaceController
- (NSButton *)button:(NSString *)title action:(SEL)action frame:(NSRect)frame parent:(NSView *)parent
{
    NSButton *button = [[[NSButton alloc] initWithFrame:frame] autorelease];
    [button setTitle:title]; [button setBezelStyle:NSBezelStyleRounded];
    [button setTarget:self]; [button setAction:action]; [parent addSubview:button];
    return button;
}
- (id)initWithViewer:(ViewerController *)viewer volume:(HorosVolumeSession *)volume
{
    NSWindow *window = [[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,1040,650)
        styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered defer:NO] autorelease];
    self = [super initWithWindow:window];
    if (!self) return nil;
    _viewer = viewer; _volume = [volume retain];
    _session = [objc_getAssociatedObject(volume, &SEGSessionKey) retain];
    if (!_session) {
        NSMutableArray *references = [NSMutableArray array];
        for (DicomImage *image in viewer.fileList) {
            NSInteger count = image.numberOfFrames.integerValue;
            HorosSEGSourceFrame *frame = [[[HorosSEGSourceFrame alloc]
                initWithSopInstanceUID:image.sopInstanceUID ?: @""
                frameNumber:count > 1 ? image.frameID.integerValue + 1 : 1
                frameCount:count] autorelease];
            if (frame) [references addObject:frame];
        }
        _session = [[HorosSEGViewerSession alloc] initWithVolume:volume sourceFrames:references];
        objc_setAssociatedObject(volume, &SEGSessionKey, _session, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    window.title = NSLocalizedString(@"SEG Surfaces", nil);
    window.releasedWhenClosed = NO;
    [window center];
    NSView *content = window.contentView;
    _surfaceView = [[[ROIVolumeView alloc] initWithFrame:NSMakeRect(280,60,760,590)] autorelease];
    _surfaceView.autoresizingMask = NSViewWidthSizable|NSViewHeightSizable;
    [content addSubview:_surfaceView];
    NSScrollView *scroll = [[[NSScrollView alloc] initWithFrame:NSMakeRect(10,235,255,405)] autorelease];
    scroll.hasVerticalScroller = YES; scroll.autoresizingMask = NSViewHeightSizable;
    _table = [[[NSTableView alloc] initWithFrame:scroll.bounds] autorelease];
    NSTableColumn *column = [[[NSTableColumn alloc] initWithIdentifier:@"label"] autorelease];
    column.title = NSLocalizedString(@"Segments", nil); column.width = 235;
    [_table addTableColumn:column]; _table.delegate = self; _table.dataSource = self;
    scroll.documentView = _table; [content addSubview:scroll];
    _name = [[[NSTextField alloc] initWithFrame:NSMakeRect(10,200,255,26)] autorelease];
    _name.target = self; _name.action = @selector(rename:); [content addSubview:_name];
    _color = [[[NSColorWell alloc] initWithFrame:NSMakeRect(10,157,55,30)] autorelease];
    _color.target = self; _color.action = @selector(recolor:); [content addSubview:_color];
    _visible = [self button:NSLocalizedString(@"Visible", nil) action:@selector(visibility:) frame:NSMakeRect(75,157,180,30) parent:content];
    [_visible setButtonType:NSButtonTypeSwitch];
    _opacity = [[[NSSlider alloc] initWithFrame:NSMakeRect(10,123,255,24)] autorelease];
    _opacity.minValue = 0; _opacity.maxValue = 1; _opacity.doubleValue = 1;
    _opacity.target = self; _opacity.action = @selector(opacity:); _opacity.continuous = NO;
    _opacity.accessibilityLabel = NSLocalizedString(@"Surface opacity", nil); [content addSubview:_opacity];
    [self button:NSLocalizedString(@"Duplicate", nil) action:@selector(duplicate:) frame:NSMakeRect(10,84,120,30) parent:content];
    [self button:NSLocalizedString(@"Delete", nil) action:@selector(remove:) frame:NSMakeRect(140,84,120,30) parent:content];
    [self button:NSLocalizedString(@"Undo", nil) action:@selector(undo:) frame:NSMakeRect(10,45,120,30) parent:content];
    [self button:NSLocalizedString(@"Redo", nil) action:@selector(redo:) frame:NSMakeRect(140,45,120,30) parent:content];
    [self button:NSLocalizedString(@"Import SEG...", nil) action:@selector(importSEG:) frame:NSMakeRect(280,12,150,32) parent:content];
    [self button:NSLocalizedString(@"Export Derived SEG...", nil) action:@selector(exportSEG:) frame:NSMakeRect(435,12,210,32) parent:content];
    NSNotificationCenter *nc = [NSNotificationCenter defaultCenter];
    [nc addObserver:self selector:@selector(changed:) name:HorosSEGViewerSession.changedNotification object:_session];
    [nc addObserver:self selector:@selector(drawOverlay:) name:OsirixDrawObjectsNotification object:nil];
    [nc addObserver:self selector:@selector(sourceClosed:) name:OsirixCloseViewerNotification object:viewer];
    [nc addObserver:self selector:@selector(sourceClosed:) name:OsirixViewerWillChangeNotification object:viewer];
    [nc addObserver:self selector:@selector(sourceVolumeChanged:) name:OsirixUpdateVolumeDataNotification object:nil];
    [nc addObserver:self selector:@selector(windowWillClose:) name:NSWindowWillCloseNotification object:nil];
    [nc addObserver:self selector:@selector(windowChanged:) name:NSWindowDidBecomeMainNotification object:nil];
    [self changed:nil];
    return self;
}
- (void)dealloc
{
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    [NSObject cancelPreviousPerformRequestsWithTarget:self];
    [self detachActors];
    [_surfaceView prepareForRelease];
    [_volume release]; [_session release];
    [super dealloc];
}
- (BOOL)usesVolume:(HorosVolumeSession *)volume { return volume == _volume && _session.isCurrent; }
- (void)sourceClosed:(NSNotification *)note
{
    if (!_viewer) return;
    [[self retain] autorelease];
    [_session close]; [self detachActors]; [self.window close];
    // Also release VTK's view/window bindings when the panel was already closed.
    [_surfaceView prepareForRelease];
    objc_setAssociatedObject(_volume, &SEGSessionKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    objc_setAssociatedObject(_viewer, &SEGControllerKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    _viewer = nil;
}
- (void)sourceVolumeChanged:(NSNotification *)note
{
    if (![NSThread isMainThread]) {
        [self performSelectorOnMainThread:@selector(sourceVolumeChanged:) withObject:note waitUntilDone:NO];
        return;
    }
    if (_viewer && note.object == [_viewer pixList]) [self sourceClosed:note];
}
- (void)windowWillClose:(NSNotification *)note
{
    if (note.object == self.window) {
        // ROIVolumeView removes its own close observer on the first close.
        // This controller is reusable, so every close must break the VTK retain cycle.
        [_surfaceView prepareForRelease];
    } else {
        id controller = [note.object windowController];
        if (![controller isKindOfClass:[VRController class]] || ![self ownsWindowController:controller]) return;
        vtkRenderer *closingRenderer = [[controller view] renderer];
        for (auto actor : _actors) closingRenderer->RemoveActor(actor);
        for (auto iterator = _externalRenderers.begin(); iterator != _externalRenderers.end();) {
            if (iterator->GetPointer() == closingRenderer) iterator = _externalRenderers.erase(iterator);
            else ++iterator;
        }
    }
}
- (void)showError:(NSString *)message
{
    NSAlert *alert = [[[NSAlert alloc] init] autorelease];
    alert.messageText = NSLocalizedString(@"SEG Surfaces", nil); alert.informativeText = message;
    [alert beginSheetModalForWindow:self.window completionHandler:nil];
}
- (void)importSEG:(id)sender
{
    NSOpenPanel *panel = [NSOpenPanel openPanel]; panel.canChooseDirectories = NO; panel.allowsMultipleSelection = NO;
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
        if (response != NSModalResponseOK) return;
        NSError *error = nil;
        NSData *data = [NSData dataWithContentsOfURL:panel.URL options:NSDataReadingMappedIfSafe error:&error];
        NSString *diagnosis = data ? [_session loadData:data] : error.localizedDescription;
        if (diagnosis) [self showError:diagnosis];
        else { [_surfaceView renderer]->ResetCamera(); [_surfaceView setNeedsDisplay:YES]; }
    }];
}
- (void)exportSEG:(id)sender
{
    NSError *error = nil; NSData *data = [_session exportDerivedAndReturnError:&error];
    if (!data) { [self showError:error.localizedDescription]; return; }
    NSSavePanel *panel = [NSSavePanel savePanel]; panel.nameFieldStringValue = @"Derived-SEG.dcm";
    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
        if (response != NSModalResponseOK) return;
        NSError *writeError = nil;
        if (![data writeToURL:panel.URL options:NSDataWritingAtomic error:&writeError]) [self showError:writeError.localizedDescription];
    }];
}
- (HorosSEGViewerSurface *)selected
{
    NSInteger row = _table.selectedRow;
    return row >= 0 && row < _session.snapshots.count ? [_session.snapshots objectAtIndex:row] : nil;
}
- (NSInteger)numberOfRowsInTableView:(NSTableView *)view { return _session.snapshots.count; }
- (id)tableView:(NSTableView *)view objectValueForTableColumn:(NSTableColumn *)column row:(NSInteger)row
{
    HorosSEGViewerSurface *surface = [_session.snapshots objectAtIndex:row];
    return [NSString stringWithFormat:@"%@ (%.3f cm³)", surface.label, surface.mesh.maskVolumeCm3];
}
- (void)tableViewSelectionDidChange:(NSNotification *)note { [self updateSelection]; }
- (void)updateSelection
{
    HorosSEGViewerSurface *surface = [self selected];
    _name.stringValue = surface.label ?: @"";
    _color.color = [NSColor colorWithSRGBRed:surface.red green:surface.green blue:surface.blue alpha:1];
    _visible.state = surface.visible ? NSControlStateValueOn : NSControlStateValueOff;
    _opacity.doubleValue = surface.opacity;
}
- (void)rename:(id)sender { if ([self selected]) [_session rename:[self selected].number label:_name.stringValue]; }
- (void)recolor:(id)sender {
    NSColor *color = [_color.color colorUsingColorSpace:[NSColorSpace sRGBColorSpace]];
    if ([self selected]) [_session recolor:[self selected].number red:color.redComponent green:color.greenComponent blue:color.blueComponent];
}
- (void)visibility:(id)sender { if ([self selected]) [_session setVisible:[self selected].number visible:_visible.state == NSControlStateValueOn]; }
- (void)opacity:(id)sender { if ([self selected]) [_session setOpacity:[self selected].number opacity:_opacity.doubleValue]; }
- (void)duplicate:(id)sender { if ([self selected]) [_session duplicate:[self selected].number]; }
- (void)remove:(id)sender { if ([self selected]) [_session remove:[self selected].number]; }
- (void)undo:(id)sender { [_session undo]; }
- (void)redo:(id)sender { [_session redo]; }
- (BOOL)ownsWindowController:(id<HorosSEGViewerOwner>)controller
{
    if ((id)controller == _viewer) return YES;
    if ([controller respondsToSelector:@selector(viewerController)] && [controller viewerController] == _viewer) return YES;
    if ([controller respondsToSelector:@selector(viewer)] && [controller viewer] == _viewer) return YES;
    if ([controller respondsToSelector:@selector(viewer2D)] && [controller viewer2D] == _viewer) return YES;
    return NO;
}
- (void)detachActors
{
    for (auto actor : _actors) {
        [_surfaceView renderer]->RemoveActor(actor);
        for (auto renderer : _externalRenderers) renderer->RemoveActor(actor);
    }
    _actors.clear(); _externalRenderers.clear(); _meshes.clear();
}
- (void)windowChanged:(NSNotification *)note { [self changed:nil]; }
- (void)changed:(NSNotification *)note
{
    if (![NSThread isMainThread]) return;
    NSInteger selected = _table.selectedRow;
    [self detachActors];
    if (_session.isCurrent) {
        for (HorosSEGViewerSurface *surface in _session.snapshots) {
            auto data = HorosSEGSurfacePolyData(surface.mesh.vertices, surface.mesh.triangles);
            _meshes[surface.number] = data;
            auto mapper = vtkSmartPointer<vtkPolyDataMapper>::New(); mapper->SetInputData(data); mapper->ScalarVisibilityOff();
            auto actor = vtkSmartPointer<vtkActor>::New(); actor->SetMapper(mapper);
            actor->GetProperty()->SetColor(surface.red, surface.green, surface.blue);
            actor->GetProperty()->SetOpacity(surface.opacity); actor->SetVisibility(surface.visible);
            [_surfaceView renderer]->AddActor(actor); _actors.push_back(actor);
        }
    }
    // Existing VR windows use patient coordinates scaled by their volume factor.
    // Each renderer gets its own actors: one view cannot change another's scale.
    for (NSWindow *window in [NSApp windows]) {
        id controller = window.windowController;
        if (!window.isVisible || ![controller isKindOfClass:[VRController class]] || ![self ownsWindowController:controller]) continue;
        VRView *view = [controller view];
        auto renderer = [view renderer]; _externalRenderers.push_back(renderer);
        for (HorosSEGViewerSurface *surface in _session.snapshots) {
            if (!_session.isCurrent) break;
            auto mapper = vtkSmartPointer<vtkPolyDataMapper>::New(); mapper->SetInputData(_meshes[surface.number]); mapper->ScalarVisibilityOff();
            auto actor = vtkSmartPointer<vtkActor>::New(); actor->SetMapper(mapper);
            actor->SetScale([view factor]); actor->GetProperty()->SetColor(surface.red, surface.green, surface.blue);
            actor->GetProperty()->SetOpacity(surface.opacity); actor->SetVisibility(surface.visible);
            renderer->AddActor(actor); _actors.push_back(actor);
        }
        [view setNeedsDisplay:YES];
    }
    if (!_cameraInitialized && !_actors.empty()) { [_surfaceView renderer]->ResetCamera(); _cameraInitialized = YES; }
    [_surfaceView setNeedsDisplay:YES];
    [_table reloadData];
    if (_session.snapshots.count) [_table selectRowIndexes:[NSIndexSet indexSetWithIndex:MAX(0, MIN(selected, (NSInteger)_session.snapshots.count - 1))] byExtendingSelection:NO];
    [self updateSelection];
    for (NSWindow *window in [NSApp windows]) if ([self ownsWindowController:window.windowController]) [window.contentView setNeedsDisplay:YES];
}
- (void)drawOverlay:(NSNotification *)note
{
    if (![NSThread isMainThread] || ![note.object isKindOfClass:[DCMView class]]) return;
    DCMView *view = note.object;
    if (![self ownsWindowController:view.window.windowController]) return;
    if (!_session.isCurrent || [_viewer horosVolumeSession] != _volume) {
        dispatch_async(dispatch_get_main_queue(), ^{ [self sourceClosed:nil]; });
        return;
    }
    DCMPix *pix = view.curDCM;
    if (pix.pixelSpacingX <= 0 || pix.pixelSpacingY <= 0) return;
    double orientation[9]; [pix orientationDouble:orientation];
    double planeOrigin[3] = {pix.originX, pix.originY, pix.originZ};
    double planeNormal[3] = {orientation[6], orientation[7], orientation[8]};
    double scale = [[note.userInfo objectForKey:@"scaleValue"] doubleValue];
    double offsetX = [[note.userInfo objectForKey:@"offsetx"] doubleValue];
    double offsetY = [[note.userInfo objectForKey:@"offsety"] doubleValue];
    CGLContextObj cgl_ctx = CGLGetCurrentContext();
    if (!cgl_ctx) return;
    glPushAttrib(GL_ENABLE_BIT|GL_LINE_BIT|GL_CURRENT_BIT|GL_COLOR_BUFFER_BIT);
    glDisable(GL_TEXTURE_2D); glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glLineWidth(2 * view.window.backingScaleFactor);
    for (HorosSEGViewerSurface *surface in _session.snapshots) {
        if (!surface.visible || surface.opacity <= 0) continue;
        auto cut = HorosSEGSurfaceCut(_meshes[surface.number], planeOrigin, planeNormal);
        vtkIdType count, *ids; cut->GetLines()->InitTraversal();
        glColor4d(surface.red,surface.green,surface.blue,surface.opacity);
        while (cut->GetLines()->GetNextCell(count,ids)) {
            glBegin(GL_LINE_STRIP);
            for (vtkIdType index=0; index<count; ++index) {
                double patient[3], point[3]; cut->GetPoint(ids[index],patient);
                [pix convertDICOMCoordsDouble:patient toSliceCoords:point pixelCenter:YES];
                glVertex2d((point[0]/pix.pixelSpacingX-offsetX)*scale,(point[1]/pix.pixelSpacingY-offsetY)*scale);
            }
            glEnd();
        }
    }
    glPopAttrib();
}
@end
