//  Registered comparison GIF, #384 package B.
//
//  The animation is made of the captures the viewer already draws: the same
//  slice, the same window, the fusion blend moved from one series to the other
//  and put back where it was. The result goes to the clipboard as data; no file
//  is written. Fused DICOM export (#142), movie/codec export (#147), the
//  flythrough (#222) and the drag file promises (#270) keep their own routes.

#import "ViewerController.h"

@class HorosRegisteredGIFResult;

@interface ViewerController (HorosRegisteredGIF)

+ (void)installRegisteredGIFMenuItems;

/// Capture the comparison without touching the clipboard or any panel.
/// `refusal` is filled with the reason when the result is not usable.
- (HorosRegisteredGIFResult *)horosRegisteredComparisonGIFWithBlendStops:(NSArray<NSNumber *> *)blendStops
                                                           delaySeconds:(double)delaySeconds
                                                                refusal:(NSString **)refusal;

- (IBAction)copyRegisteredComparisonGIF:(id)sender;

@end
