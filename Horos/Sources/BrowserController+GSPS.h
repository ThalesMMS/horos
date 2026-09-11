#import "BrowserController.h"

@class DicomSeries;
@class ViewerController;

@interface BrowserController (GSPS)

/// If `series` is a Softcopy Presentation State, opens the referenced images
/// (when they are in the same study) and applies the documented GSPS subset.
/// Returns YES when the series was handled as a presentation state, even if
/// every reference is missing — in that case no empty viewer is opened.
- (BOOL)horos_tryOpenGSPSSeries:(DicomSeries *)series
                         viewer:(ViewerController *)viewer
                  keyImagesOnly:(BOOL)keyImages
                  openedViewer:(ViewerController **)outViewer;

@end
