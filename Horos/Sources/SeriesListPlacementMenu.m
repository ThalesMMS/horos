#import "SeriesListPlacementMenu.h"
#import "Horos-Swift.h"

@implementation ViewerController (HorosSeriesListPlacement)

+ (NSMenuItem *)horosFindSeriesListItemIn:(NSMenu *)menu owner:(NSMenu **)owner
{
    for (NSMenuItem *item in menu.itemArray) {
        if ([item.title isEqualToString:NSLocalizedString(@"Series List", nil)] || [item.title isEqualToString:@"Series List"]) {
            if (owner) *owner = menu;
            return item;
        }
        if (item.submenu) {
            NSMenuItem *found = [self horosFindSeriesListItemIn:item.submenu owner:owner];
            if (found) return found;
        }
    }
    return nil;
}

+ (void)installSeriesListPlacementMenuItems
{
    NSMenu *owner = nil;
    NSMenuItem *anchor = [self horosFindSeriesListItemIn:[NSApp mainMenu] owner:&owner];
    if (!anchor || !owner) { NSLog(@"Series list: 'Series List' menu item not found; placement submenu not installed"); return; }
    if ([owner indexOfItemWithTitle:NSLocalizedString(@"Series List Placement", nil)] != -1) return;

    NSMenu *submenu = [[[NSMenu alloc] initWithTitle:NSLocalizedString(@"Series List Placement", nil)] autorelease];
    NSArray *titles = @[NSLocalizedString(@"Left", nil), NSLocalizedString(@"Right", nil),
                        NSLocalizedString(@"Top", nil), NSLocalizedString(@"Bottom", nil)];
    for (NSInteger index = 0; index < (NSInteger)titles.count; index++) {
        NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:titles[index]
                                                       action:@selector(setSeriesListPlacement:) keyEquivalent:@""] autorelease];
        item.tag = index;
        item.target = nil; // first responder: the front 2D viewer
        [submenu addItem:item];
    }
    NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Series List Placement", nil)
                                                   action:nil keyEquivalent:@""] autorelease];
    item.submenu = submenu;
    [owner insertItem:item atIndex:[owner indexOfItem:anchor] + 1];
}

- (IBAction)setSeriesListPlacement:(id)sender
{
    HorosSeriesListPlacement placement = (HorosSeriesListPlacement)[sender tag];
    [HorosSeriesListLayout storePlacement:placement in:[NSUserDefaults standardUserDefaults]];
    [[NSNotificationCenter defaultCenter] postNotificationName:HorosSeriesListLayout.placementDidChangeNotification object:nil];
}

@end
