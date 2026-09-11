#import "ViewerController.h"

@class HorosGSPSApplicationResult;
@class HorosGSPSDocument;

@interface ViewerController (GSPS)

/// Adds "Apply Grayscale Presentation State…" to the 2D viewer ROI menu.
+ (void)installGSPSMenuItems;

/// Parses a GSPS file and applies the documented subset to matching images.
/// Missing referenced SOP Instance UIDs and unsupported modules are logged
/// (and shown) and Pixel Data / fImage is not rewritten.
- (HorosGSPSApplicationResult *)applyGrayscaleSoftcopyPresentationStateFromPath:(NSString *)path;

- (IBAction)applyGrayscaleSoftcopyPresentationState:(id)sender;

@end
