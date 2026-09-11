/*
 ViewerController+ROIEnhancement.h
 Horos

 Sample the open 4D series with computeROI, matching ROI Enhancement II 2.3.1.
 The curve lives in ROIEnhancement.swift; this category only reads DCMPix
 pixels / acquisition times and the current-slice ROIs.
*/

#import "ViewerController.h"

@interface ViewerController (ROIEnhancement)

- (NSDictionary *)roiEnhancementProcessCurrentSeries;

@end
