#!/usr/bin/env python3
"""Check production ApplySettings commits edits before rendering/persistence."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/SRController.mm']) if len(sys.argv)>1 else (root/'Horos/Sources/SRController.mm').read_bytes()).decode('latin1')
a=s.index('-(IBAction) ApplySettings:');b=s.index('\n- (void)renderSurfaces',a)
code=r'''
#import <Foundation/Foundation.h>
@interface Sheet:NSObject
@property(copy) BOOL (^commit)(void);
@property BOOL hidden, discarded;
-(void)endEditingFor:(id)value;
-(BOOL)makeFirstResponder:(id)value;
-(void)orderOut:(id)sender;
@end
@implementation Sheet
-(void)endEditingFor:(id)value{self.discarded=YES;}
-(BOOL)makeFirstResponder:(id)value{return self.commit();}
-(void)orderOut:(id)sender{self.hidden=YES;}
@end
@interface App:NSObject
@property BOOL ended;
-(void)endSheet:(id)sheet returnCode:(NSInteger)code;
@end
@implementation App
-(void)endSheet:(id)sheet returnCode:(NSInteger)code{self.ended=YES;}
@end
static App *NSApp;
@interface Sender:NSObject
@property NSInteger tag;
@end
@implementation Sender
@end
@interface Controller:NSObject {
@public Sheet *SRSettingsWindow; BOOL fusionSettingsWindow;
 NSMutableDictionary *settings,*blendingSettings;
}
@property float resolution,firstSurface,secondSurface,firstTransparency,secondTransparency,decimate,smooth;
@property BOOL shouldDecimate,shouldSmooth,useFirstSurface,useSecondSurface,shouldRenderFusion;
@property(retain) id firstColor,secondColor;
@property float rendered;
-(void)renderSurfaces;-(void)renderFusionSurfaces;
@end
@implementation Controller
-(void)renderSurfaces{self.rendered=self.firstSurface;}
-(void)renderFusionSurfaces{self.rendered=self.firstSurface;}
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 for(int fusion=0;fusion<2;fusion++)for(int mode=0;mode<3;mode++){
  NSApp=[App new];Controller*c=[Controller new];c->SRSettingsWindow=[Sheet new];
  c->settings=[@{@"firstSurface":@300} mutableCopy];c->blendingSettings=[@{@"firstSurface":@300} mutableCopy];
  c->fusionSettingsWindow=fusion;c.firstSurface=300;c.rendered=-1;c.firstColor=@"white";c.secondColor=@"pink";
  __block int commits=0;
  c->SRSettingsWindow.commit=^{commits++;if(mode==2)return NO;c.firstSurface=50;return YES;};
  Sender*button=[Sender new];button.tag=mode==0?0:1;
  [c ApplySettings:button];
  NSDictionary*d=fusion?c->blendingSettings:c->settings;
  if(mode==1){check(commits==1 && c.rendered==50 && [d[@"firstSurface"] intValue]==50);check(NSApp.ended && c->SRSettingsWindow.hidden);}
  else{check(c.rendered==-1 && [d[@"firstSurface"] intValue]==300);check(commits==(mode==2));check(NSApp.ended==(mode==0));check(c->SRSettingsWindow.hidden==(mode==0));check(c->SRSettingsWindow.discarded==(mode==0));}
 }
 NSLog(@"PASS: pending edit commit, cancellation, rejected validation, primary and fusion settings");
}}
'''.replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-surface-settings-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fblocks','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
