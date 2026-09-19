#import "DCMView.h"

@interface DCMView (HorosScrollPositionPreview)
- (void)horosShowScrollPreviewAtWindowPoint:(NSPoint)point;
- (void)horosMoveScrollPreviewAtWindowPoint:(NSPoint)point;
- (void)horosHideScrollPreview;
- (void)horosDiscardScrollPreview;
- (CGFloat)horosScrollPreviewAnnotationInset;
@end
