#import "ViewerController.h"

/// The viewer's series list can dock on any edge (#380 D). The choice is one
/// preference, applied live to every open viewer and kept across relaunches;
/// the list itself, its cells, its selection and its accessibility are the
/// host's own — this only decides which edge it sits on.
@interface ViewerController (HorosSeriesListPlacement)
/// Adds "Series List Placement" to the 2D Viewer menu, under "Series List".
+ (void)installSeriesListPlacementMenuItems;
/// Menu action: the item's tag is a HorosSeriesListPlacement.
- (IBAction)setSeriesListPlacement:(id)sender;
@end
