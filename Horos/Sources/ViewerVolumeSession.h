#import "ViewerController.h"
@class HorosVolumeSession;

/// Shared by planar, MPR and SEG consumers. Main-thread access only; the host
/// viewer owns the session, while consumers own cancellable load tokens.
@interface ViewerController (HorosVolumeSession)
- (HorosVolumeSession *)horosVolumeSession;
@end
