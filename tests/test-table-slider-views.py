#!/usr/bin/env python3
"""Exercise the app's ROI/compression table controls with real AppKit and nibs."""
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from object_probe import app_object, link_probe

# Audit every tracked interface: slider cells must never be drawn by a cell table.
for name in subprocess.check_output(["git", "ls-files", "*.xib"], cwd=ROOT, text=True).splitlines():
    document = ET.parse(ROOT / name)
    for table in document.iter("tableView"):
        if table.find("./tableColumns/tableColumn/sliderCell") is not None:
            assert table.get("viewBased") == "YES", f"{name}: cell-based slider table"

objects = [app_object(name) for name in
           ("ROIVolumeManagerController", "Notifications", "OSIGeneralPreferencePanePref")]
vtk = ROOT / "build/Build/Intermediates.noindex/Horos.build/Debug/VTK.build/Install/lib"
objects += [vtk / "libvtkCommonCore-8.2.a", vtk / "libvtksys-8.2.a"]
if any(obj is None or not obj.exists() for obj in objects):
    print("SKIP: build Debug with script/build_and_run.sh --verify first")
    sys.exit(2)

SOURCE = r'''
#import <Cocoa/Cocoa.h>
#import <PreferencePanes/PreferencePanes.h>
#define CHECK(test) do { if (!(test)) { NSLog(@"FAIL line %d: %s", __LINE__, #test); exit(1); } } while(0)
@interface NSWindowController (ROITest)
- (id)initWithViewer:(id)viewer;
@end
@interface AppController : NSObject @end
@implementation AppController
+ (NSUInteger)isKDUEngineAvailable { return 0; }
@end
@interface DefaultsOsiriX : NSObject @end
@implementation DefaultsOsiriX @end
void _N2LogExceptionImpl(NSException *exception, BOOL stack, const char *function) { @throw exception; }

// Only the model/renderer boundary is replaced; both table controllers are the
// exact objects linked into Horos. Each setter records the controller's routing.
@interface ROIVolume : NSObject
@property(retain) NSMutableDictionary *properties;
@property NSUInteger writes;
@end
@implementation ROIVolume
- (id)init { if ((self = [super init])) self.properties = [@{
    @"name":@"ROI", @"volume":@12.5, @"visible":@NO, @"texture":@YES,
    @"red":@0, @"green":@1, @"blue":@1, @"opacity":@1} mutableCopy]; return self; }
- (void)setVisible:(BOOL)v { self.writes++; [self.properties setObject:@(v) forKey:@"visible"]; }
- (void)setTexture:(BOOL)v { self.writes++; [self.properties setObject:@(v) forKey:@"texture"]; }
- (void)setRed:(float)v { self.writes++; [self.properties setObject:@(v) forKey:@"red"]; }
- (void)setGreen:(float)v { self.writes++; [self.properties setObject:@(v) forKey:@"green"]; }
- (void)setBlue:(float)v { self.writes++; [self.properties setObject:@(v) forKey:@"blue"]; }
- (void)setOpacity:(float)v { self.writes++; [self.properties setObject:@(v) forKey:@"opacity"]; }
@end
@interface Viewer : NSObject
@property(retain) NSMutableArray *roiVolumes;
@property(retain) NSView *view;
@property NSUInteger shown, hidden;
@end
@implementation Viewer
- (void)displayROIVolume:(id)volume { self.shown++; }
- (void)hideROIVolume:(id)volume { self.hidden++; }
@end

static void settle(void) {
    [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
}
static NSControl *control(NSTableView *table, NSString *identifier, NSInteger row) {
    NSInteger column = [table columnWithIdentifier:identifier];
    NSView *cell = [table viewAtColumn:column row:row makeIfNecessary:YES];
    CHECK(cell);
    [cell layoutSubtreeIfNeeded];
    for (NSView *view in cell.subviews) if ([view isKindOfClass:NSControl.class]) return (NSControl *)view;
    CHECK(NO); return nil;
}
static void geometry(NSTableView *table, NSString *identifier, NSInteger row) {
    NSSlider *slider = (NSSlider *)control(table, identifier, row);
    CHECK([slider isKindOfClass:NSSlider.class]);
    CHECK(slider.cell.controlView == slider);
    NSRect frame = [slider convertRect:slider.bounds toView:table];
    NSRect cell = [table frameOfCellAtColumn:[table columnWithIdentifier:identifier] row:row];
    CHECK(NSContainsRect(NSInsetRect(cell, -1, -1), frame));
    NSRect bar = [(NSSliderCell *)slider.cell barRectFlipped:slider.flipped];
    CHECK(NSContainsRect(NSInsetRect(slider.bounds, -1, -1), bar));
    CHECK(NSWidth(bar) < NSWidth(table.bounds) / 2);
}
static void testROI(void) {
    Viewer *viewer = [Viewer new];
    viewer.view = [[[NSView alloc] initWithFrame:NSMakeRect(0,0,100,100)] autorelease];
    viewer.roiVolumes = [NSMutableArray array];
    for (int i=0; i<40; i++) {
        ROIVolume *volume = [ROIVolume new];
        volume.properties[@"name"] = [NSString stringWithFormat:@"ROI %02d",i];
        [viewer.roiVolumes addObject:volume];
    }
    NSWindowController *manager = [[NSClassFromString(@"ROIVolumeManagerController") alloc] initWithViewer:viewer];
    [manager showWindow:nil]; settle();
    NSTableView *table = [manager valueForKey:@"tableView"];
    CHECK(table.numberOfRows == 40);
    ROIVolume *first = viewer.roiVolumes[0];
    for (NSString *key in @[@"red", @"green", @"blue", @"opacity"]) {
        geometry(table,key,0);
        NSSlider *slider = (NSSlider *)control(table,key,0);
        CHECK(slider.minValue == 0 && slider.maxValue == 1 && slider.continuous);
        slider.doubleValue = 0.35;
        [slider sendAction:slider.action to:slider.target];
        CHECK(fabs([first.properties[key] doubleValue] - 0.35) < 0.0001);
    }
    CHECK(first.writes == 4);
    NSButton *visible = (NSButton *)control(table,@"display",0);
    [visible performClick:nil]; CHECK(viewer.shown == 1 && [first.properties[@"visible"] boolValue]);
    [visible performClick:nil]; CHECK(viewer.hidden == 1 && ![first.properties[@"visible"] boolValue]);
    [(NSButton *)control(table,@"texture",0) performClick:nil]; CHECK(![first.properties[@"texture"] boolValue]);
    [table selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO];
    table.sortDescriptors = @[[NSSortDescriptor sortDescriptorWithKey:@"properties.name" ascending:NO]];
    settle(); CHECK(table.selectedRow == 39);
    [table scrollRowToVisible:39]; settle();
    geometry(table,@"opacity",39);
    NSSlider *opacity = (NSSlider *)control(table,@"opacity",39);
    opacity.doubleValue = 0.8; [opacity sendAction:opacity.action to:opacity.target];
    CHECK(fabs([first.properties[@"opacity"] doubleValue] - 0.8) < 0.0001);
    CHECK(((ROIVolume *)viewer.roiVolumes[39]).writes == 0);
    [manager.window setContentSize:NSMakeSize(800,350)]; settle(); geometry(table,@"red",39);
    [manager.window orderOut:nil];
    NSLog(@"PASS ROI: geometry, RGB/opacity, visibility, texture, sorting, scrolling and resize");
}
static void collectTables(NSView *view, NSMutableArray *tables) {
    if ([view isKindOfClass:NSTableView.class]) [tables addObject:view];
    for (NSView *child in view.subviews) collectTables(child,tables);
}
static void testCompression(void) {
    NSMutableArray *rows = [NSMutableArray array];
    for (int i=0; i<14; i++) [rows addObject:@{@"modality":[NSString stringWithFormat:@"TEST %d",i], @"compression":@3, @"quality":@(i%4)}];
    NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
    for (NSString *key in @[@"CompressionSettings", @"CompressionSettingsLowRes"]) [defaults setObject:rows forKey:key];
    // Load both real table definitions without the unrelated settings UI startup.
    id pane = [[NSClassFromString(@"OSIGeneralPreferencePanePref") alloc] init];
    NSArray *top;
    NSNib *nib = [[NSNib alloc] initWithNibNamed:@"OSIGeneralPreferencePanePref" bundle:nil];
    CHECK([nib instantiateWithOwner:pane topLevelObjects:&top]);
    NSWindow *window = [pane valueForKey:@"compressionSettingsWindow"];
    [window orderFront:nil]; settle();
    NSMutableArray *tables = [NSMutableArray array]; collectTables(window.contentView,tables);
    CHECK(tables.count == 2);
    for (NSTableView *table in tables) {
        CHECK(table.numberOfRows == 14);
        for (int row=0; row<4; row++) {
            geometry(table,@"quality",row);
            NSSlider *slider = (NSSlider *)control(table,@"quality",row);
            CHECK(slider.minValue == 0 && slider.maxValue == 3 && slider.numberOfTickMarks == 4 && slider.allowsTickMarkValuesOnly);
            CHECK(slider.integerValue == row);
        }
        NSPopUpButton *popup = (NSPopUpButton *)control(table,@"compression",0);
        [popup selectItemWithTag:1]; [popup sendAction:popup.action to:popup.target]; settle();
        CHECK(!control(table,@"quality",0).enabled);
        popup = (NSPopUpButton *)control(table,@"compression",0);
        [popup selectItemWithTag:4]; [popup sendAction:popup.action to:popup.target]; settle();
        NSSlider *slider = (NSSlider *)control(table,@"quality",0);
        CHECK(slider.enabled);
        slider.integerValue = 2; [slider sendAction:slider.action to:slider.target]; settle();
        NSDictionary *contentBinding = [table infoForBinding:NSContentBinding];
        NSArrayController *controller = contentBinding[NSObservedObjectKey];
        CHECK([controller.arrangedObjects[0][@"quality"] integerValue] == 2);
        NSString *path = [controller infoForBinding:NSContentArrayBinding][NSObservedKeyPathKey];
        NSString *key = [path substringFromIndex:@"values.".length];
        CHECK([[[defaults arrayForKey:key][0] objectForKey:@"quality"] integerValue] == 2);
        [table scrollRowToVisible:13]; settle(); geometry(table,@"quality",13);
        CHECK([(NSSlider *)control(table,@"quality",13) integerValue] == 1);
        [table scrollRowToVisible:0]; settle();
        CHECK([(NSSlider *)control(table,@"quality",0) integerValue] == 2);
    }
    [window orderOut:nil];
    NSLog(@"PASS compression: both nib tables, bounds, four levels, codec enablement, reuse and defaults persistence");
}
int main(void) { @autoreleasepool {
    [NSApplication sharedApplication];
    testROI(); testCompression();
    [NSUserDefaults.standardUserDefaults removePersistentDomainForName:NSBundle.mainBundle.bundleIdentifier];
} return 0; }
'''

with tempfile.TemporaryDirectory(prefix="horos-table-sliders-") as folder:
    folder = Path(folder)
    app = folder / "TableSliders.app/Contents"
    (app / "MacOS").mkdir(parents=True)
    (app / "Resources").mkdir()
    bundle_id = "org.horosproject.test-table-sliders." + folder.name
    (app / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": bundle_id,
        "CFBundleExecutable": "TableSliders", "CFBundlePackageType": "APPL"}))
    source = folder / "probe.m"
    source.write_text(SOURCE)
    executable = link_probe(source, objects, app / "MacOS/TableSliders", frameworks=("Cocoa", "PreferencePanes"))
    for roi_locale, prefs_locale in (("en", "Base"), ("ja-JP", "ja-JP")):
        for nib, path in (
            ("ROIVolumeManager", ROOT / f"Horos/Resources/{roi_locale}.lproj/ROIVolumeManager.xib"),
            ("OSIGeneralPreferencePanePref", ROOT / f"Preference Panes/OSIGeneralPreferencePane/{prefs_locale}.lproj/OSIGeneralPreferencePanePref.xib"),
        ):
            subprocess.run(["ibtool", "--compile", str(app / f"Resources/{nib}.nib"), str(path)], check=True, capture_output=True)
        try:
            subprocess.run([str(executable)], check=True, timeout=40)
        finally:
            subprocess.run(["defaults", "delete", bundle_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"PASS table sliders: {roi_locale}/{prefs_locale}")
