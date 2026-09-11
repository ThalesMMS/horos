#import "PatientCrosshairBridge.h"
#import "ViewerVolumeSession.h"
#import "OrthogonalMPRViewer.h"
#import "Horos-Swift.h"

BOOL HorosPublishPatientCrosshair(const float point[3], ViewerController *viewer, id owner)
{
    if (!viewer || viewer.windowWillClose) return NO;
    HorosVolumeSession *session = [viewer horosVolumeSession];
    if (!session) return NO;
    return [[HorosPatientCrosshairController shared] publishX:point[0] y:point[1] z:point[2]
                                                    session:session owner:owner];
}

HorosPatientCrosshairPoint *HorosPatientCrosshairForViewer(ViewerController *viewer)
{
    if (!viewer || viewer.windowWillClose) return nil;
    HorosPatientCrosshairController *crosshair = [HorosPatientCrosshairController shared];
    if (!crosshair.currentPoint) return nil;
    id owner = crosshair.sourceOwner;
    ViewerController *source = nil;
    if ([owner isKindOfClass:[ViewerController class]]) source = owner;
    else if ([owner isKindOfClass:[OrthogonalMPRViewer class]]) source = [owner viewerController];
    BOOL registered = source && (viewer.registeredViewer == source || source.registeredViewer == viewer);
    HorosVolumeSession *session = [viewer horosVolumeSession];
    if (!session) return nil;
    return [crosshair pointForSession:session registered:registered
                 useFrameOfReference:[[NSUserDefaults standardUserDefaults]
                     boolForKey:HorosViewerReferenceLines.frameOfReferencePreferenceKey]];
}
