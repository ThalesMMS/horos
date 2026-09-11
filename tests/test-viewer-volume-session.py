#!/usr/bin/env python3
"""Run the actual viewer facade and Swift registry with lightweight host stubs.

No window, app build, pixels or database are needed. An optional source path
lets the regression run against the previous ViewerVolumeSession.m revision.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]) if len(sys.argv) > 1 else root/'Horos/Sources/ViewerVolumeSession.m'
headers = r'''
#import <Foundation/Foundation.h>
@interface DicomStudy : NSObject
@property(copy) NSString *studyInstanceUID;
@end
@interface DicomSeries : NSObject
@property(strong) DicomStudy *study;
@property(copy) NSString *seriesInstanceUID;
@property(copy) NSString *seriesDICOMUID;
@end
@interface DicomImage : NSObject
@property(strong) DicomSeries *series;
@end
@interface DCMPix : NSObject
@property(copy) NSString *frameofReferenceUID;
@end
@interface DCMView : NSObject
@property(strong) DCMPix *curDCM;
@end
@interface ViewerController : NSObject
@property(strong) DicomImage *currentImage;
@property(strong) DCMView *imageView;
@property(strong) NSMutableArray *pixList;
@property NSInteger curMovieIndex;
@property BOOL windowWillClose;
@end
extern NSString * const OsirixCloseViewerNotification;
extern NSString * const OsirixViewerWillChangeNotification;
extern NSString * const OsirixViewerDidChangeNotification;
extern NSString * const OsirixUpdateVolumeDataNotification;
'''
driver = r'''
#import "ViewerVolumeSession.h"
#import "Horos-Swift.h"
#include <assert.h>
@implementation DicomStudy @end
@implementation DicomSeries @end
@implementation DicomImage @end
@implementation DCMPix @end
@implementation DCMView @end
@implementation ViewerController @end
NSString * const OsirixCloseViewerNotification = @"CloseViewerNotification";
NSString * const OsirixViewerWillChangeNotification = @"ViewerWillChangeNotification";
NSString * const OsirixViewerDidChangeNotification = @"ViewerDidChangeNotification";
NSString * const OsirixUpdateVolumeDataNotification = @"UpdateVolumeDataNotification";
int main(void) { @autoreleasepool {
    ViewerController *viewer = [ViewerController new];
    viewer.currentImage = [DicomImage new];
    viewer.currentImage.series = [DicomSeries new];
    viewer.currentImage.series.seriesInstanceUID = @"00000001 1.2.3";
    viewer.currentImage.series.seriesDICOMUID = @"1.2.3";
    viewer.currentImage.series.study = [DicomStudy new];
    viewer.currentImage.series.study.studyInstanceUID = @"1.2";
    viewer.imageView = [DCMView new]; viewer.imageView.curDCM = [DCMPix new];
    viewer.imageView.curDCM.frameofReferenceUID = @"1.4";
    viewer.pixList = [NSMutableArray arrayWithObject:viewer.imageView.curDCM];
    HorosVolumeSessionRegistry *registry = HorosVolumeSessionRegistry.shared;
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    HorosVolumeSession *first = viewer.horosVolumeSession;
    assert(first && first.isOpen && !first.isStale && first.identity.generation == 0);
    assert([first.identity.seriesInstanceUID isEqual:@"1.2.3"]);
    assert(viewer.horosVolumeSession == first);
    HorosPatientCrosshairController *crosshair = HorosPatientCrosshairController.shared;
    assert([crosshair publishX:1 y:2 z:3 session:first owner:viewer]);
    HorosVolumeLoadToken *old = [registry makeLoadTokenFor:first];
    [nc postNotificationName:OsirixUpdateVolumeDataNotification object:[NSMutableArray array]];
    assert(!first.isStale && !old.isCancelled && crosshair.currentPoint != nil);
    [nc postNotificationName:OsirixUpdateVolumeDataNotification object:viewer.pixList];
    assert(first.isStale && first.identity.generation == 1 && old.isCancelled && ![old deliver]);
    assert(crosshair.currentPoint == nil && crosshair.sourceOwner == nil);
    HorosVolumeSession *second = viewer.horosVolumeSession;
    assert(second != first && !first.isOpen && second.isOpen && !second.isStale);
    assert(second.identity.generation == 1 && [second.owner isEqual:first.owner]);
    assert([registry makeLoadTokenFor:first] == nil);
    assert(viewer.horosVolumeSession == second && registry.openSessionCount == 1);
    HorosVolumeLoadToken *current = [registry makeLoadTokenFor:second];
    assert(current.identity.generation == 1 && [current deliver]);
    HorosVolumeLoadToken *pending = [registry makeLoadTokenFor:second];
    [nc postNotificationName:OsirixUpdateVolumeDataNotification object:viewer.pixList];
    [nc postNotificationName:OsirixUpdateVolumeDataNotification object:viewer.pixList];
    HorosVolumeSession *third = viewer.horosVolumeSession;
    assert(third != second && !second.isOpen && !third.isStale && third.identity.generation == 3);
    assert(![pending deliver] && ![old deliver]);
    // Time-point switches still retire the previous volume instead of carrying its generation.
    viewer.curMovieIndex = 1;
    HorosVolumeSession *fourth = viewer.horosVolumeSession;
    assert(!third.isOpen && fourth.identity.timeIndex == 1 && fourth.identity.generation == 0);
    assert([crosshair publishX:4 y:5 z:6 session:fourth owner:viewer]);
    HorosVolumeLoadToken *closing = [registry makeLoadTokenFor:fourth];
    [nc postNotificationName:OsirixCloseViewerNotification object:viewer];
    assert(!fourth.isOpen && ![closing deliver] && registry.openSessionCount == 0);
    assert(crosshair.currentPoint == nil && crosshair.sourceOwner == nil);
    viewer.windowWillClose = YES;
    assert(viewer.horosVolumeSession == nil && registry.openSessionCount == 0);
    // A retained plugin may query during replacement, before the old catalog
    // objects are removed. It must not recreate a session for those old pixels.
    viewer.windowWillClose = NO;
    HorosVolumeSession *beforeChange = viewer.horosVolumeSession;
    HorosVolumeLoadToken *changing = [registry makeLoadTokenFor:beforeChange];
    [nc postNotificationName:OsirixViewerWillChangeNotification object:viewer];
    assert(!beforeChange.isOpen && changing.isCancelled);
    assert(viewer.horosVolumeSession == nil && registry.openSessionCount == 0);
    [nc postNotificationName:OsirixCloseViewerNotification object:viewer userInfo:@{@"newStudyID":@"next"}];
    assert(viewer.horosVolumeSession == nil && registry.openSessionCount == 0);
    viewer.currentImage.series.seriesInstanceUID = @"00000002 1.2.4";
    viewer.currentImage.series.seriesDICOMUID = @"1.2.4";
    [nc postNotificationName:OsirixViewerDidChangeNotification object:viewer];
    HorosVolumeSession *afterChange = viewer.horosVolumeSession;
    assert(afterChange.isOpen && [afterChange.owner isEqual:beforeChange.owner]);
    assert([afterChange.identity.seriesInstanceUID isEqual:@"1.2.4"]);
    viewer.windowWillClose = YES;
    [nc postNotificationName:OsirixCloseViewerNotification object:viewer];
    assert(viewer.horosVolumeSession == nil && registry.openSessionCount == 0);
    puts("PASS: real viewer facade renews stale generations, rejects old loads and preserves owner/close semantics");
} return 0; }
'''
with tempfile.TemporaryDirectory(prefix='horos-viewer-volume-session-') as temporary:
    work = Path(temporary)
    (work/'Host.h').write_text('#pragma once\n'+headers)
    for name in ['ViewerController.h', 'DicomImage.h', 'DicomSeries.h', 'DicomStudy.h', 'DCMPix.h', 'Notifications.h']:
        (work/name).write_text('#import "Host.h"\n')
    (work/'ViewerVolumeSession.h').write_bytes((root/'Horos/Sources/ViewerVolumeSession.h').read_bytes())
    (work/'ViewerVolumeSession.m').write_bytes(source.read_bytes())
    (work/'Check.m').write_text(driver)
    subprocess.run(['xcrun','swiftc','-emit-library','-module-name','Horos',
                    '-emit-objc-header-path',str(work/'Horos-Swift.h'),
                    str(root/'Horos/Sources/VolumeSession.swift'),
                    str(root/'Horos/Sources/ViewerReferenceLines.swift'),
                    str(root/'Horos/Sources/PatientCrosshairController.swift'),'-o',str(work/'libHoros.dylib')],check=True)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-c',str(work/'ViewerVolumeSession.m'),
                    '-o',str(work/'facade.o')],check=True)
    subprocess.run(['xcrun','clang','-fobjc-arc',str(work/'Check.m'),str(work/'facade.o'),
                    '-framework','Foundation','-L'+str(work),'-lHoros','-o',str(work/'check')],check=True)
    subprocess.run([str(work/'check')],check=True)
