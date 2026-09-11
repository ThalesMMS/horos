/*
 ViewerController+T2FitMap.h
 Horos

 Apply the native T2 Fit Map to the open multi-echo series.
 The fit lives in T2FitMap.swift; this category only reads DCMPix
 echo times / pixels and opens the resulting map.
*/

#import "ViewerController.h"

@interface ViewerController (T2FitMap)

- (NSDictionary *)t2FitMapProcessCurrentSeries;

@end
