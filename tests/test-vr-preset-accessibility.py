#!/usr/bin/env python3
"""Exercise production thumbnail accessibility methods with controlled selection."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
s = (root/'Horos/Sources/VRPresetPreview.mm').read_bytes().decode('latin1')
a = s.index('- (BOOL)isAccessibilityElement')
b = s.index('- (void)setSelected;', a)
c = (root/'Horos/Sources/VRController.mm').read_bytes().decode('latin1')
a2 = c.index('- (void)setSelectedPresetPreview:')
b2 = c.index('- (void)selectGroupWithName:', a2)
code = r'''
#import <Cocoa/Cocoa.h>
#include <assert.h>
@class Controller;
@interface VRPresetPreview:NSView { @public BOOL isEmpty, isSelected; Controller *owner; }
- (void)setSelected;
- (void)setSelectedState:(BOOL)value;
@end
@interface Controller:NSObject { @public VRPresetPreview *selectedPresetPreview; int updates; }
- (void)setSelectedPresetPreview:(VRPresetPreview*)preview;
- (void)updatePresetInfoPanel;
@end
@implementation VRPresetPreview
METHODS
- (void)setSelected { [owner setSelectedPresetPreview:self]; }
@end
@implementation Controller
CONTROLLER
- (void)updatePresetInfoPanel {updates++;}
@end
int main(){ @autoreleasepool {
 Controller *c=[Controller new]; VRPresetPreview *a=[VRPresetPreview new],*b=[VRPresetPreview new],*empty=[VRPresetPreview new];
 a->owner=b->owner=empty->owner=c; empty->isEmpty=YES;
 [a setAccessibilityLabel:@"Bone + Skin"];[b setAccessibilityLabel:@"Black & White"];
 assert([a isAccessibilityElement] && ![empty isAccessibilityElement]);
 assert([[a accessibilityRole] isEqual:NSAccessibilityRadioButtonRole]);
 assert([[a accessibilityLabel] isEqual:@"Bone + Skin"]);
 assert(![[a accessibilityValue] boolValue]);
 assert([a accessibilityPerformPress]); assert(c->selectedPresetPreview==a && [[a accessibilityValue] boolValue]);
 assert([b accessibilityPerformPress]); assert(c->selectedPresetPreview==b && [[b accessibilityValue] boolValue] && ![[a accessibilityValue] boolValue]);
 assert(![empty accessibilityPerformPress]); assert(c->selectedPresetPreview==b && c->updates==2);
 assert([a accessibilityPerformPress]); assert(![[b accessibilityValue] boolValue] && [[a accessibilityValue] boolValue]);
 [a release];[b release];[empty release];[c release];
 puts("PASS: named radio role, selection switching and empty-slot rejection");
}}
'''.replace('METHODS',s[a:b]).replace('CONTROLLER',c[a2:b2])
with tempfile.TemporaryDirectory(prefix='horos-preset-ax-') as d:
    p=Path(d);(p/'test.m').write_text(code)
    subprocess.run(['xcrun','clang',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
