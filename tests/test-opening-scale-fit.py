#!/usr/bin/env python3
"""Execute production fit geometry and deferred-opening lifecycle with real run-loop delivery."""
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
view = (root/'Horos/Sources/DCMView.m').read_text()
controller = (root/'Horos/Sources/ViewerController.m').read_text()

def method(source, signature):
    start = source.index(signature)
    end = re.search(r'\n[-+]\s*\(', source[start+len(signature):])
    return source[start:start+len(signature)+end.start()]

geometry = '\n'.join(method(view, s) for s in (
    '- (float) scaleToFitForDCMPix:', '- (void) scaleToFit\n', '- (void) prepareForWorkspacePresentation', '- (void) applyOpeningScaleToFit'))
analysis_method = method(controller, '+ (NSDictionary*) openingContentBoundsForPixLists:')
policy = '\n'.join(method(controller, s) for s in (
    '- (void) cancelOpeningScaleToFit\n', '- (void) requestOpeningScaleToFit\n', '- (void) finishOpeningScaleToFit\n'))
# Wiring guards accompany behavioral execution below.
for signature in ['keyDown:', 'mouseDown:', 'rightMouseDown:', 'otherMouseDown:', 'scrollWheel:', 'magnifyWithEvent:', 'rotateWithEvent:']:
    match = re.search(r'(?m)^-\s*\(void\)\s*'+signature+r'[^\n]*', view)
    assert match and 'cancelOpeningScaleToFitForInteraction' in method(view, match[0]), signature
assert 'if (!sameSeries)\n                        [self requestOpeningScaleToFit];' in controller
browser = (root/'Horos/Sources/BrowserController.m').read_text()
a=browser.index('[v setImageRows: rows columns: columns];')
assert '[v cancelOpeningScaleToFit];' in browser[a:browser.index('[v setScaleValue: scale];',a)]
for language in ('Base','ja-JP'):
    tree = ET.parse(root/f'Preference Panes/OSIViewerPreferencePane/{language}.lproj/OSIViewerPreferencePanePref.xib')
    for key in ('ScaleToFitOnOpen','AlwaysScaleToFit'):
        assert len(tree.findall(f'.//binding[@keyPath="values.{key}"]')) == 1
assert 'setObject: @"1" forKey: @"ScaleToFitOnOpen"' in (root/'Horos/Sources/DefaultsOsiriX.m').read_text()

code = r'''
#import <Cocoa/Cocoa.h>
#include "HorosContentBounds.h"
#include <math.h>
#include <assert.h>
static NSCondition *contentGate;
static BOOL releaseContent;
static int contentReaders;
@interface DCMPix:NSObject
@property double pwidth,pheight,pixelRatio;
@property BOOL shutterEnabled;
@property NSRect shutterRect;
@property(nonatomic) float *fImage;
@property BOOL isRGB;
@property BOOL isLoaded;
@property(copy) NSString *modalityString, *rescaleType;
@end
@implementation DCMPix
@synthesize fImage;
-(float *)fImage {
 if(contentGate){[contentGate lock];contentReaders++;[contentGate broadcast];while(!releaseContent)[contentGate wait];[contentGate unlock];}
 return fImage;
}
@end
@interface FitWorker:NSObject
+(NSDictionary*)openingContentBoundsForPixLists:(NSArray*)lists loadThread:(NSThread*)thread;
@end
@implementation FitWorker
ANALYSIS
@end
@interface DCMView:NSObject {
@public BOOL firstTimeDisplay,scaleToFitNoReentry; NSPoint origin; float scaleValue;
}
@property(retain) DCMPix *curDCM;
@property(retain) NSArray *dcmPixList;
@property NSRect bounds;
@property double backing;
@property float rotation,storedRotation;
@property NSInteger fits,restores;
@property float scaleValue;
@end
@implementation DCMView
@synthesize scaleValue;
-(NSRect)convertRectToBacking:(NSRect)r {return NSMakeRect(0,0,r.size.width*self.backing,r.size.height*self.backing);}
-(void)setNeedsDisplay:(BOOL)b {self.fits++;}
-(void)updatePresentationStateFromSeries {self.restores++;self.rotation=self.storedRotation;self.scaleValue=.1;origin=NSMakePoint(70,20);}
GEOMETRY
@end
@interface Series:NSObject
@property(retain) NSArray *imageViews;
@end
@implementation Series
@end
@interface Content:NSObject
-(void)layoutSubtreeIfNeeded;
@end
@implementation Content
-(void)layoutSubtreeIfNeeded {}
@end
@interface Window:NSObject
@property(retain) Content *contentView;
@end
@implementation Window
@end
static BOOL delayedTileWindows;
@interface Controller:NSObject {
@public BOOL openingScaleToFitRequested,windowWillClose; Series *seriesView;
 NSThread *loadingThread; NSDictionary *openingContentBoundsByPixels;
}
@property(retain) Window *window;
@property BOOL updateTilingViewsValue;
@end
@implementation Controller
POLICY
@end
static void tick(void) { [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.12]]; }
#define check(...) do { if(!(__VA_ARGS__)) { NSLog(@"FAIL %s",#__VA_ARGS__); return 1; } } while(0)
int main(){@autoreleasepool{
 DCMView *v=[DCMView new];v.curDCM=[DCMPix new];v.curDCM.isLoaded=YES;v.dcmPixList=@[v.curDCM];v.curDCM.pwidth=640;v.curDCM.pheight=240;
 v.bounds=NSMakeRect(0,0,901,511);v.backing=1;
 int cases=0;
 for(int retina=1;retina<=2;retina++) for(int shutter=0;shutter<2;shutter++)
 for(int ratio=1;ratio<=3;ratio++) for(int angle=0;angle<360;angle+=15) {
  v.backing=retina;v.curDCM.pixelRatio=ratio*.5;v.rotation=angle;
  v.curDCM.shutterEnabled=shutter;v.curDCM.shutterRect=NSMakeRect(37,19,310,170);
  [v scaleToFit];
  double w=shutter?310:640,h=shutter?170:240,cx=shutter?192:320,cy=shutter?104:120;
  double maxX=0,maxY=0;
  for(int ix=0;ix<2;ix++)for(int iy=0;iy<2;iy++) {
   double x=(cx+(ix-.5)*w-320)*v.scaleValue+v->origin.x;
   double y=(cy+(iy-.5)*h-120)*v.scaleValue*v.curDCM.pixelRatio-v->origin.y;
   double r=angle*M_PI/180,xx=x*cos(r)-y*sin(r),yy=x*sin(r)+y*cos(r);
   maxX=fmax(maxX,fabs(xx));maxY=fmax(maxY,fabs(yy));
  }
  check(maxX<=901*retina/2.+.001 && maxY<=511*retina/2.+.001);
  check(fabs(maxX-901*retina/2.)<.001 || fabs(maxY-511*retina/2.)<.001);
  cases++;
 }
 v.curDCM.shutterEnabled=NO;v.curDCM.pixelRatio=1;v.backing=1;v.storedRotation=37;v->firstTimeDisplay=NO;
 v.fits=0;
 Controller *c=[Controller new];c->seriesView=[Series new];c->seriesView.imageViews=@[v];
 c.window=[Window new];c.window.contentView=[Content new];
 NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
 [defaults setBool:NO forKey:@"ScaleToFitOnOpen"];
 [c requestOpeningScaleToFit];tick();check(v.fits==0);
 [defaults setBool:YES forKey:@"ScaleToFitOnOpen"];
 [c requestOpeningScaleToFit];[c cancelOpeningScaleToFit];tick();check(v.fits==0); // manual/workspace cancellation
 delayedTileWindows=YES;[c requestOpeningScaleToFit];tick();check(v.fits==0);
 delayedTileWindows=NO;v.bounds=NSMakeRect(0,0,450,800); // final layout differs
 [c finishOpeningScaleToFit];check(v.fits==1 && v.restores==1 && v.rotation==37);
 check(fabs(v.scaleValue-[v scaleToFitForDCMPix:v.curDCM])<.0001);
 [c finishOpeningScaleToFit];check(v.fits==1); // consumed once
 v.scaleValue=.3;v->origin=NSMakePoint(4,5);tick();check(v.fits==1 && v.scaleValue==.3f && v->origin.x==4);
 // Workspace values written after preparation must survive the first draw.
 [v prepareForWorkspacePresentation];v.scaleValue=.4;v->origin=NSMakePoint(9,11);
 [v prepareForWorkspacePresentation];check(v.scaleValue==.4f && v->origin.x==9 && v.restores==1);
 // A replacement cancels old deferred callbacks and fits only the new tiles.
 DCMView *second=[DCMView new];second.curDCM=v.curDCM;second.bounds=NSMakeRect(0,0,300,200);second.backing=2;
 [c requestOpeningScaleToFit];[c cancelOpeningScaleToFit];c->seriesView.imageViews=@[second];
 [c requestOpeningScaleToFit];tick();check(second.fits==1 && v.fits==1);
 [c requestOpeningScaleToFit];[defaults setBool:NO forKey:@"ScaleToFitOnOpen"];tick();check(second.fits==1);
 [defaults setBool:YES forKey:@"ScaleToFitOnOpen"];
 [c requestOpeningScaleToFit];c->windowWillClose=YES;tick();check(second.fits==1);
 [c cancelOpeningScaleToFit];
 // Content inside the matrix: off-centre body, disconnected arm, isolated
 // bright marker, table line and noisy air. Exercise the production detector
 // and opening method, not a duplicate geometry calculation.
 float *pixels=malloc(512*512*sizeof(float));
 for(int y=0;y<512;y++)for(int x=0;x<512;x++) {
  double body=pow((x-280)/120.,2)+pow((y-210)/70.,2);
  double arm=pow((x-80)/20.,2)+pow((y-210)/22.,2);
  pixels[y*512+x]=(body<=1||arm<=1)?40:-1000+(x*7+y*3)%5;
  if(y==470 && x>10 && x<500)pixels[y*512+x]=500;
 }
 pixels[35*512+490]=3000;
 HorosContentRect box;
 check(HorosFindContentBounds(pixels,false,false,512,512,&box));
 check(box.x<60 && box.x+box.width>400 && box.y<140 && box.y+box.height>280);
 check(box.y+box.height<400 && box.x+box.width<480); // no table / marker zoom-out
 v.curDCM.pwidth=v.curDCM.pheight=512;v.curDCM.fImage=pixels;v->firstTimeDisplay=YES;
 v.curDCM.shutterEnabled=NO;v.bounds=NSMakeRect(0,0,901,511);
 for(int retina=1;retina<=2;retina++)for(int angle=0;angle<180;angle+=30) {
  v.backing=retina;v.rotation=angle;v.curDCM.pixelRatio=1.5;
  [v applyOpeningScaleToFit:NSMakeRect(box.x,box.y,box.width,box.height)];
  check(v.scaleValue>[v scaleToFitForDCMPix:v.curDCM]*1.05);
  for(int ix=0;ix<2;ix++)for(int iy=0;iy<2;iy++) {
   double x=(box.x+ix*box.width-256)*v.scaleValue+v->origin.x;
   double y=(box.y+iy*box.height-256)*v.scaleValue*1.5-v->origin.y;
   double r=angle*M_PI/180,xx=x*cos(r)-y*sin(r),yy=x*sin(r)+y*cos(r);
   check(fabs(xx)<=901*retina/2.+.01 && fabs(yy)<=511*retina/2.+.01);
  }
 }
 for(int i=0;i<512*512;i++)pixels[i]=-pixels[i];
 HorosContentRect inverted;check(HorosFindContentBounds(pixels,false,false,512,512,&inverted));
 check(fabs(inverted.x-box.x)<.01 && fabs(inverted.height-box.height)<.01);
 // A curved, hollow table has a large bounding box; a padded straight support
 // has real area. Neither should pull the body/arm fit down. Rotate the source
 // pixels too, so rejection is not tied to the bottom of an axial picture.
 for(int i=0;i<512*512;i++)pixels[i]=-pixels[i];
 float *tablePixels=malloc(512*512*sizeof(float));
 for(int table=0;table<2;table++)for(int turn=0;turn<4;turn++) {
  for(int y=0;y<512;y++)for(int x=0;x<512;x++) {
   double curve=440-.002*(x-256)*(x-256);
   BOOL support=table ? (y>=430 && y<=445) :
       (fabs(y-curve)<=3.5 || fabs(y-curve-18)<=3.5 ||
        ((x<=27 || x>=485) && y>=curve && y<=curve+18));
   float value=(support && x>=24 && x<=488)?500:pixels[y*512+x];
   int xx=x,yy=y;
   for(int r=0;r<turn;r++){int oldX=xx;xx=511-yy;yy=oldX;}
   tablePixels[yy*512+xx]=value;
  }
  HorosContentRect actual,expected=box;
  for(int r=0;r<turn;r++)expected=(HorosContentRect){512-expected.y-expected.height,expected.x,expected.height,expected.width};
  check(HorosFindContentBounds(tablePixels,false,false,512,512,&actual));
  check(fabs(actual.x-expected.x)<6 && fabs(actual.y-expected.y)<6);
  check(fabs(actual.width-expected.width)<6 && fabs(actual.height-expected.height)<6);
 }
 // CT padding/air can form a low-density bridge from the body to table rails.
 // Raw HU, not the displayed WL/WW, must break that bridge. Keep a hollow
 // chest wall enclosing aerated lungs as well as the detached arm.
 for(int y=0;y<512;y++)for(int x=0;x<512;x++) {
  double body=pow((x-280)/120.,2)+pow((y-210)/70.,2);
  double curve=440-.002*(x-256)*(x-256);
  float value=pixels[y*512+x];
  if(body<.7)value=-850;
  if(y>280 && y<curve && x>=24 && x<=488)value=-800+(x*7+y*3)%50;
  if(x>=24 && x<=488 && (fabs(y-curve)<=3.5 || fabs(y-curve-18)<=3.5 ||
     ((x<=27 || x>=485) && y>=curve && y<=curve+18)))value=500;
  tablePixels[y*512+x]=value;
 }
 HorosContentRect ct,relative;
 check(HorosFindContentBounds(tablePixels,false,true,512,512,&ct));
 check(HorosFindContentBounds(tablePixels,false,false,512,512,&relative));
 check(fabs(ct.x-box.x)<6 && fabs(ct.y-box.y)<6 && fabs(ct.width-box.width)<6 && fabs(ct.height-box.height)<6);
 check(relative.y+relative.height>450); // bridge reproduces the old fit
 v.curDCM.fImage=tablePixels;v.curDCM.modalityString=@"CT";v.curDCM.rescaleType=@"HU";
 v.rotation=0;v.curDCM.pixelRatio=1;v.backing=1;
 [v applyOpeningScaleToFit:NSMakeRect(ct.x,ct.y,ct.width,ct.height)];float ctZoom=v.scaleValue;
 check(fabs((ct.x+ct.width*.5-256)*ctZoom+v->origin.x)<.01);
 check(fabs((ct.y+ct.height*.5-256)*ctZoom-v->origin.y)<.01);
 [v applyOpeningScaleToFit:NSMakeRect(relative.x,relative.y,relative.width,relative.height)];check(v.scaleValue<ctZoom);

 v.curDCM.fImage=pixels;v.curDCM.modalityString=nil;v.curDCM.rescaleType=nil;
 // A compact component below the body and an elongated, solid detached limb
 // are anatomy candidates, not supports to remove because of their location.
 for(int y=0;y<512;y++)for(int x=0;x<512;x++) {
  double leg=pow((x-350)/45.,2)+pow((y-400)/55.,2);
  double limb=pow((x-80)/20.,2)+pow((y-210)/110.,2);
  tablePixels[y*512+x]=(leg<=1 || limb<=1)?40:pixels[y*512+x];
 }
 HorosContentRect anatomy;
 check(HorosFindContentBounds(tablePixels,false,false,512,512,&anatomy));
 check(anatomy.x<60 && anatomy.y<100 && anatomy.y+anatomy.height>455);
 free(tablePixels);
 for(int i=0;i<512*512;i++)pixels[i]=0;
 check(!HorosFindContentBounds(pixels,false,false,512,512,&box));
 pixels[210*512+280]=3000;check(!HorosFindContentBounds(pixels,false,false,512,512,&box));
 [v applyOpeningScaleToFit:NSZeroRect];check(v.scaleValue==[v scaleToFitForDCMPix:v.curDCM] && v->origin.x==0 && v->origin.y==0);
 for(int i=0;i<512*512;i++)pixels[i]=(i*7)%101;
 check(!HorosFindContentBounds(pixels,false,false,512,512,&box));
 for(int i=0;i<512*512;i++)pixels[i]=NAN;
 check(!HorosFindContentBounds(pixels,false,false,512,512,&box));
 unsigned char *rgb=(unsigned char*)pixels;
 for(int y=0;y<512;y++)for(int x=0;x<512;x++) {
  unsigned char *p=rgb+4*(y*512+x);p[0]=255;p[1]=p[2]=p[3]=0;
  if(x<300 && y>=180 && y<300){p[1]=140;p[2]=220;p[3]=80;}
 }
 check(HorosFindContentBounds(pixels,true,false,512,512,&box));check(box.x==0 && box.y<180 && box.y+box.height>=300);
 // The opening slice and the last slice are small; only an interior slice
 // spans the full anatomy. Execute the real series worker, then fit all its
 // cuts with a single stable presentation.
 NSMutableArray *stack=[NSMutableArray array];
 NSRect expected=NSZeroRect, firstBounds=NSZeroRect, middleBounds=NSZeroRect;
 for(int slice=0;slice<3;slice++) {
  DCMPix *p=[DCMPix new];p.pwidth=p.pheight=512;p.pixelRatio=1;p.isLoaded=YES;
  p.modalityString=@"CT";p.rescaleType=@"HU";p.fImage=malloc(512*512*sizeof(float));
  for(int y=0;y<512;y++)for(int x=0;x<512;x++) {
   double ellipse=slice==1 ? pow((x-290)/150.,2)+pow((y-300)/150.,2) : pow((x-200)/35.,2)+pow((y-120)/40.,2);
   p.fImage[y*512+x]=ellipse<=1?40:-1000;
  }
  HorosContentRect r;check(HorosFindContentBounds(p.fImage,false,true,512,512,&r));
  NSRect frame=NSMakeRect(r.x,r.y,r.width,r.height);expected=NSUnionRect(expected,frame);
  if(slice==0)firstBounds=frame;if(slice==1)middleBounds=frame;
  [stack addObject:p];
 }
 check(!NSContainsRect(firstBounds,middleBounds)); // regression in single-cut fit
 contentGate=[NSCondition new];releaseContent=NO;contentReaders=0;
 __block NSDictionary *envelopes=nil;__block BOOL heartbeat=NO;
 NSOperationQueue *worker=[NSOperationQueue new];
 [worker addOperationWithBlock:^{envelopes=[[FitWorker openingContentBoundsForPixLists:@[stack] loadThread:NSThread.currentThread] retain];}];
 NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:5];
 BOOL entered=NO;
 while(!entered && deadline.timeIntervalSinceNow>0){tick();[contentGate lock];entered=contentReaders>0;[contentGate unlock];}
 check(entered && worker.operationCount>0);
 [[NSOperationQueue mainQueue] addOperationWithBlock:^{heartbeat=YES;}];tick();
 check(heartbeat && worker.operationCount>0); // blocked pixel analysis leaves main loop usable
 [contentGate lock];releaseContent=YES;[contentGate broadcast];[contentGate unlock];
 while(worker.operationCount && deadline.timeIntervalSinceNow>0)tick();check(worker.operationCount==0);
 [contentGate release];contentGate=nil;
 NSRect envelope=[envelopes[[NSValue valueWithNonretainedObject:stack]] rectValue];
 check(NSEqualRects(envelope,expected));
 v.curDCM=stack.firstObject;v.dcmPixList=stack;v.backing=1;v.bounds=NSMakeRect(0,0,901,511);
 for(int angle=0;angle<180;angle+=30) {
  v.rotation=angle;[v applyOpeningScaleToFit:envelope];
  for(NSValue *r in @[[NSValue valueWithRect:firstBounds],[NSValue valueWithRect:middleBounds]]) {
   NSRect rect=r.rectValue;
   for(int ix=0;ix<2;ix++)for(int iy=0;iy<2;iy++) {
    double x=(rect.origin.x+ix*rect.size.width-256)*v.scaleValue+v->origin.x;
    double y=(rect.origin.y+iy*rect.size.height-256)*v.scaleValue-v->origin.y;
    double angleR=angle*M_PI/180,xx=x*cos(angleR)-y*sin(angleR),yy=x*sin(angleR)+y*cos(angleR);
    check(fabs(xx)<=901/2.+.01 && fabs(yy)<=511/2.+.01);
   }
  }
 }
 // A loading request first displays the full matrix. Manual interaction then
 // cancels the pending fit even if the completed envelope arrives later.
 c->windowWillClose=NO;c->seriesView.imageViews=@[v];c->loadingThread=[NSThread new];
 [c requestOpeningScaleToFit];tick();check(c->openingScaleToFitRequested);
 check(v.scaleValue==[v scaleToFitForDCMPix:v.curDCM]);
 [c cancelOpeningScaleToFit];v.scaleValue=.7;v->origin=NSMakePoint(31,47);
 c->openingContentBoundsByPixels=envelopes;c->loadingThread=nil;[c finishOpeningScaleToFit];
 check(v.scaleValue==.7f && v->origin.x==31 && v->origin.y==47);
 [c requestOpeningScaleToFit];tick();check(!c->openingScaleToFitRequested);
 // Uncertain slices and incompatible geometry must not produce a tight fit.
 DCMPix *uncertain=stack.lastObject;
 for(int i=0;i<512*512;i++)uncertain.fImage[i]=-1000;
 [worker addOperationWithBlock:^{envelopes=[[FitWorker openingContentBoundsForPixLists:@[stack] loadThread:NSThread.currentThread] retain];}];
 [worker waitUntilAllOperationsAreFinished];
 check(NSEqualRects([envelopes[[NSValue valueWithNonretainedObject:stack]] rectValue],NSMakeRect(0,0,512,512)));
 uncertain.pixelRatio=2;
 [worker addOperationWithBlock:^{envelopes=[[FitWorker openingContentBoundsForPixLists:@[stack] loadThread:NSThread.currentThread] retain];}];
 [worker waitUntilAllOperationsAreFinished];check(envelopes.count==0);
 NSThread *cancelled=[NSThread new];[cancelled cancel];
 [worker addOperationWithBlock:^{envelopes=[[FitWorker openingContentBoundsForPixLists:@[stack] loadThread:cancelled] retain];}];
 [worker waitUntilAllOperationsAreFinished];check(envelopes==nil);
 for(DCMPix *p in stack)free(p.fImage);
 free(pixels);
 puts("PASS: complete-series envelope, interior extrema, background analysis, responsive main loop and cancelled late delivery");
 printf("PASS: %d rotated/shutter/anisotropic/Retina fits; deferred layout, cancellation, replacement and workspace policy\n",cases);
 puts("PASS: content bounds, detached anatomy, curved/padded/rotated table rejection, auto-zoom/centering, polarity, RGB and conservative fallback");
}}
'''.replace('GEOMETRY',geometry).replace('POLICY',policy).replace('ANALYSIS',analysis_method)
with tempfile.TemporaryDirectory(prefix='horos-opening-fit-') as temp:
    path=Path(temp)/'check.m';path.write_text(code);binary=path.with_suffix('')
    subprocess.run(['xcrun','clang','-I',str(root/'Horos/Sources'),'-Wno-deprecated-declarations','-framework','Cocoa',str(path),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
