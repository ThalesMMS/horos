#!/usr/bin/env python3
"""Compile the production cell delegate and check contrast/styling across AppKit appearances.
Optional git revision reproduces pre-fix contrast failures. No DICOM files are needed.
"""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parent.parent
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/XMLController.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/XMLController.m').read_bytes().decode('latin1'));a=s.index('- (void)outlineView:(NSOutlineView *)outlineView willDisplayCell:');method=s[a:s.index('- (void) traverse:',a)]
source=r'''
#import <AppKit/AppKit.h>
#include <math.h>
#define check(v) NSCAssert((v), @"failed: %s", #v)
@interface OutlineFixture:NSObject
@property BOOL selected;
-(NSInteger)rowForItem:(id)item;
-(NSIndexSet*)selectedRowIndexes;
@end
@implementation OutlineFixture
-(NSInteger)rowForItem:(id)item{return 0;}
-(NSIndexSet*)selectedRowIndexes{return self.selected ? [NSIndexSet indexSetWithIndex:0] : [NSIndexSet indexSet];}
@end
@interface MetadataFixture:NSObject { @public NSTextField *search; NSMutableSet *modifiedFields; }
-(BOOL)item:(id)item containsString:(NSString*)text;
-(NSString*)getPath:(id)item;
-(void)outlineView:(NSOutlineView*)view willDisplayCell:(id)cell forTableColumn:(NSTableColumn*)column item:(id)item;
@end
@implementation MetadataFixture
-(BOOL)item:(id)item containsString:(NSString*)text{return [item containsString:text];}
-(NSString*)getPath:(id)item{return item;}
METHOD
@end
static double luminance(NSColor *color) {
 NSColor *rgb=[color colorUsingColorSpace:NSColorSpace.sRGBColorSpace];
 double values[]={rgb.redComponent,rgb.greenComponent,rgb.blueComponent};
 for(int i=0;i<3;i++) values[i]=values[i]<=0.04045 ? values[i]/12.92 : pow((values[i]+0.055)/1.055,2.4);
 return .2126*values[0]+.7152*values[1]+.0722*values[2];
}
static void checkReadable(NSColor *foreground) {
 for(NSColor *background in NSColor.alternatingContentBackgroundColors) {
  NSColor *fg=[foreground colorUsingColorSpace:NSColorSpace.sRGBColorSpace];
  NSColor *bg=[background colorUsingColorSpace:NSColorSpace.sRGBColorSpace];
  NSColor *base=[NSColor.textBackgroundColor colorUsingColorSpace:NSColorSpace.sRGBColorSpace];
  CGFloat ba=bg.alphaComponent;
  bg=[NSColor colorWithSRGBRed:bg.redComponent*ba+base.redComponent*(1-ba) green:bg.greenComponent*ba+base.greenComponent*(1-ba) blue:bg.blueComponent*ba+base.blueComponent*(1-ba) alpha:1];
  CGFloat a=fg.alphaComponent;
  NSColor *composite=[NSColor colorWithSRGBRed:fg.redComponent*a+bg.redComponent*(1-a) green:fg.greenComponent*a+bg.greenComponent*(1-a) blue:fg.blueComponent*a+bg.blueComponent*(1-a) alpha:1];
  double x=luminance(composite),y=luminance(bg),ratio=(MAX(x,y)+.05)/(MIN(x,y)+.05);
  NSLog(@"row contrast %.2f",ratio);check(ratio>=4.5);
 }
}
int main(void) { @autoreleasepool {
 MetadataFixture *fixture=[MetadataFixture new];fixture->search=[NSTextField new];fixture->modifiedFields=[NSMutableSet set];
 OutlineFixture *outline=[OutlineFixture new];NSTextFieldCell *cell=[NSTextFieldCell new];
 for(NSString *theme in @[NSAppearanceNameAqua,NSAppearanceNameDarkAqua,NSAppearanceNameAccessibilityHighContrastAqua,NSAppearanceNameAccessibilityHighContrastDarkAqua]) {
  [[NSAppearance appearanceNamed:theme] performAsCurrentDrawingAppearance:^{
   fixture->search.stringValue=@"";outline.selected=NO;[fixture->modifiedFields removeAllObjects];
   [fixture outlineView:(id)outline willDisplayCell:cell forTableColumn:nil item:@"PatientName"];
   double text=luminance(cell.textColor), bg=luminance(NSColor.textBackgroundColor);
   check((MAX(text,bg)+.05)/(MIN(text,bg)+.05)>=4.5);
   fixture->search.stringValue=@"Patient";
   [fixture outlineView:(id)outline willDisplayCell:cell forTableColumn:nil item:@"PatientName"];
   check(([NSFontManager.sharedFontManager traitsOfFont:cell.font]&NSBoldFontMask)!=0);
   [fixture outlineView:(id)outline willDisplayCell:cell forTableColumn:nil item:@"Modality"];
   checkReadable(cell.textColor);
   [fixture->modifiedFields addObject:@"Modality"];
   [fixture outlineView:(id)outline willDisplayCell:cell forTableColumn:nil item:@"Modality"];
   checkReadable(cell.textColor);
   outline.selected=YES;
   [fixture outlineView:(id)outline willDisplayCell:cell forTableColumn:nil item:@"Modality"];
   check([cell.textColor isEqual:NSColor.selectedControlTextColor]);
   check(([NSFontManager.sharedFontManager traitsOfFont:cell.font]&NSBoldFontMask)!=0);
  }];
 }
 NSLog(@"PASS: actual metadata cell delegate uses readable primary colors in light/dark/high-contrast appearances, preserves search emphasis and modified/selected state");
} }
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-metadata-colors-') as directory:
 p=Path(directory);(p/'test.m').write_text(source)
 subprocess.run(['xcrun','clang','-fobjc-arc','-fblocks','-framework','AppKit',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
