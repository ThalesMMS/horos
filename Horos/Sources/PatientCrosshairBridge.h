#import <Foundation/Foundation.h>
@class ViewerController, HorosPatientCrosshairPoint;

/// Main-thread adapters. Geometry and volume ownership remain with the host.
FOUNDATION_EXPORT BOOL HorosPublishPatientCrosshair(const float point[3], ViewerController *viewer, id owner);
FOUNDATION_EXPORT HorosPatientCrosshairPoint *HorosPatientCrosshairForViewer(ViewerController *viewer);
