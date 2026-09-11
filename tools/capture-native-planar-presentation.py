#!/usr/bin/env python3
"""Read synthetic A111 presentation inputs, uploaded textures and native output.

All interaction happens through the UI. LLDB only reads state/GL buffers and
restores the GL readback state before detaching. Captures must remain local.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('label')
parser.add_argument('--pid',required=True,type=int)
parser.add_argument('--title-prefix',required=True,
                    choices=('A111 NM low contrast','A111 PT low contrast','Fusion CT Primary','Fusion PT Secondary'))
parser.add_argument('--output',required=True,type=Path)
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+',args.label):
    parser.error('Use a positive PID and lowercase snapshot label')
args.output.mkdir(parents=True,exist_ok=True)
prefix = (args.output/args.label).resolve()
if prefix.with_suffix('.json').exists():
    parser.error('Capture already exists; choose a new label to preserve evidence')
staged = prefix.with_suffix('.'+uuid.uuid4().hex+'.partial')
expression = r'''
id a111Owner=nil; int a111Matches=0;
for (id candidate in (NSArray*)(id)[(id)objc_getClass("ViewerController") get2DViewers]) {
 if ([(NSWindow*)(id)[candidate window] title] && [[(NSWindow*)(id)[candidate window] title] hasPrefix:TITLE]) { a111Owner=candidate; a111Matches++; }
}
id a111Main=(id)[a111Owner imageView]; id a111Blend=(id)[a111Main blendingView];
NSArray *a111Views=a111Blend ? @[a111Main,a111Blend] : (a111Main ? @[a111Main] : @[]);
BOOL a111Synthetic=a111Matches==1;
for (id a111View in a111Views) {
 id a111Vc=(id)[a111View windowController];
 NSString *a111Patient=(id)[(NSObject*)a111Vc valueForKeyPath:@"currentStudy.patientID"];
 if (![@[@"QA-A111-ONLY",@"LOCAL-FUSION-CT-PT"] containsObject:a111Patient]) a111Synthetic=NO;
}
if (a111Synthetic) {
 NSRect a111Bounds=[(NSView*)a111Main bounds];
 NSRect a111Backing=[(NSView*)a111Main convertRectToBacking:a111Bounds];
 NSMutableDictionary *a111State=[NSMutableDictionary dictionaryWithDictionary:@{
  @"viewSize":@[@(a111Backing.size.width),@(a111Backing.size.height)],
  @"viewPointSize":@[@(a111Bounds.size.width),@(a111Bounds.size.height)],
  @"metalEnabled":@((BOOL)[a111Owner horosPlanarMetalEnabled]),
  @"fallback":(id)[a111Main horosPlanarFallbackReason] ?: @"",
  @"blendingFactor":[(NSObject*)a111Main valueForKey:@"blendingFactor"],
  @"blendingMode":[(NSObject*)a111Main valueForKey:@"blendingMode"],
  @"blendingClutMode":[[NSUserDefaults standardUserDefaults] stringForKey:@"PET Clut Mode"] ?: @"",
  @"applicationActive":@([(NSApplication*)NSApp isActive]),
  @"keyWindow":[(NSApplication*)NSApp keyWindow].title ?: @""
 }];
 NSOpenGLContext *a111Previous=[NSOpenGLContext currentContext];
 NSOpenGLContext *a111Context=(id)[a111Main openGLContext]; [a111Context makeCurrentContext];
 GLint a111SubpixelBits=0;glGetIntegerv(GL_SUBPIXEL_BITS,&a111SubpixelBits);
 a111State[@"subpixelBits"]=@(a111SubpixelBits);
 glPushClientAttrib(GL_CLIENT_PIXEL_STORE_BIT); glPushAttrib(GL_TEXTURE_BIT|GL_PIXEL_MODE_BIT);
 GLint a111ReadBuffer=0,a111Active=0; glGetIntegerv(GL_READ_BUFFER,&a111ReadBuffer); glGetIntegerv(GL_ACTIVE_TEXTURE,&a111Active);
 glActiveTexture(GL_TEXTURE0); glPixelStorei(GL_PACK_ALIGNMENT,1); glPixelStorei(GL_PACK_ROW_LENGTH,0);
 glPixelStorei(GL_PACK_SKIP_PIXELS,0); glPixelStorei(GL_PACK_SKIP_ROWS,0);
 GLenum a111Scales[4]={GL_RED_SCALE,GL_GREEN_SCALE,GL_BLUE_SCALE,GL_ALPHA_SCALE};
 GLenum a111Biases[4]={GL_RED_BIAS,GL_GREEN_BIAS,GL_BLUE_BIAS,GL_ALPHA_BIAS};
 for(int i=0;i<4;i++) { glPixelTransferf(a111Scales[i],1);glPixelTransferf(a111Biases[i],0); }
 NSMutableArray *a111Layers=[NSMutableArray array];
 for (NSUInteger a111Index=0;a111Index<a111Views.count;a111Index++) {
  id a111View=a111Views[a111Index]; id a111Pix=(id)[a111View curDCM];
  id a111Vc=(id)[a111View windowController];
  NSUInteger a111W=(NSUInteger)[[(NSObject*)a111Pix valueForKey:@"pwidth"] unsignedIntegerValue];
  NSUInteger a111H=(NSUInteger)[[(NSObject*)a111Pix valueForKey:@"pheight"] unsignedIntegerValue];
  NSString *a111File=[NSString stringWithFormat:@"%@-layer-%lu",PREFIX,(unsigned long)a111Index];
  NSMutableDictionary *a111Layer=[NSMutableDictionary dictionaryWithDictionary:@{
   @"width":@(a111W),@"height":@(a111H),@"modality":[(NSObject*)a111Pix valueForKey:@"modalityString"],
   @"patient":[(NSObject*)a111Vc valueForKeyPath:@"currentStudy.patientID"],
   @"series":[(NSObject*)a111Vc valueForKeyPath:@"currentSeries.seriesInstanceUID"],
   @"level":[(NSObject*)a111View valueForKey:@"curWL"],@"widthWindow":[(NSObject*)a111View valueForKey:@"curWW"],
   @"hasTransferFunction":@((void*)[a111Pix transferFunctionPtr]!=NULL),
   @"hasSubtraction":@((void*)[a111Pix subtractedfImage]!=NULL),
   @"hasFilter":@((BOOL)[a111Pix horosPlanarHasPresentationFilter]),
   @"legacyFailure":(id)[(id)[a111View horosScalarCLUTState] failureReason] ?: @"",
   @"softwareInterpolation":@((BOOL)[a111View softwareInterpolation]),
   @"prefix":a111File.lastPathComponent
  }];
  for(NSString *a111Key in @[@"scaleValue",@"rotation",@"xFlipped",@"yFlipped",@"curImage"])
   a111Layer[a111Key]=[(NSObject*)a111View valueForKey:a111Key];
  for(NSString *a111Key in @[@"stackMode",@"stack",@"stackDirection",@"shutterEnabled",@"thickSlabVRActivated",@"isRGB"])
   a111Layer[a111Key]=[(NSObject*)a111Pix valueForKey:a111Key];
  NSRect a111Local=[(NSView*)a111View bounds];
  NSMutableArray *a111Transform=[NSMutableArray array];
  for (int corner=0;corner<3;corner++) {
   NSPoint point={a111Local.size.width/2+(corner==1 ? .5 : -.5)*a111Bounds.size.width,
                  a111Local.size.height/2+(corner==2 ? -.5 : .5)*a111Bounds.size.height};
   NSPoint mapped=(NSPoint)[a111View ConvertFromNSView2GL:point];
   [a111Transform addObject:@(mapped.x)];[a111Transform addObject:@(mapped.y)];
  }
  a111Layer[@"screenToPixel"]=a111Transform;
  NSRect a111Shutter=(NSRect)[a111Pix shutterRect];
  a111Layer[@"shutterRect"]=@[@(a111Shutter.origin.x),@(a111Shutter.origin.y),@(a111Shutter.size.width),@(a111Shutter.size.height)];
  if ((BOOL)[a111Pix horosPlanarHasPresentationFilter]) {
   NSUInteger n=(unsigned short)[a111Pix kernelsize];
   if(n<1 || n>5) { a111Synthetic=NO; break; }
   float *kernel=(float*)[a111Pix kernel];NSMutableArray *values=[NSMutableArray array];
   for(NSUInteger i=0;i<n*n;i++) [values addObject:@(kernel[i])];
   a111Layer[@"kernel"]=values;a111Layer[@"kernelSize"]=@(n);
   a111Layer[@"kernelNormalization"]=@((float)[a111Pix normalization]);
  }
  NSMutableArray *a111Rois=[NSMutableArray array];
  for(NSObject *roi in (NSArray*)(id)[(NSObject*)a111View valueForKey:@"curRoiList"])
   [a111Rois addObject:@{@"type":[roi valueForKey:@"type"],@"mean":[roi valueForKey:@"mean"],@"min":[roi valueForKey:@"min"],@"max":[roi valueForKey:@"max"]}];
  a111Layer[@"rois"]=a111Rois;
  if (!a111W || !a111H || a111W>1024 || a111H>1024) { a111Synthetic=NO; break; }
  [[NSData dataWithBytes:(void*)[a111Pix fImage] length:a111W*a111H*4]writeToFile:[a111File stringByAppendingString:@".f32"] atomically:YES];
  if (!(BOOL)[a111Pix isRGB] && !(BOOL)[a111Pix thickSlabVRActivated])
   [[NSData dataWithBytes:(void*)[a111Pix baseAddr] length:a111W*a111H]writeToFile:[a111File stringByAppendingString:@".u8"] atomically:YES];
  NSMutableData *a111Volume=[NSMutableData data];
  NSArray *a111Slices=(NSArray*)(id)[a111Vc pixList];
  if(a111Slices.count>32) { a111Synthetic=NO; break; }
  for (id slice in a111Slices) {
   NSUInteger sw=(NSUInteger)[[(NSObject*)slice valueForKey:@"pwidth"] unsignedIntegerValue],sh=(NSUInteger)[[(NSObject*)slice valueForKey:@"pheight"] unsignedIntegerValue];
   if(sw!=a111W || sh!=a111H) { a111Synthetic=NO; break; }
   [a111Volume appendBytes:(void*)[slice fImage] length:sw*sh*4];
  }
  [a111Volume writeToFile:[a111File stringByAppendingString:@".volume.f32"] atomically:YES];
  unsigned char *a111A,*a111R,*a111G,*a111B;
  if(a111Index) {
   (void)[a111Main blendingColorTables:&a111A :&a111R :&a111G :&a111B];
   /* PET colours can come from the primary's shared PET table, but
      loadTextureIn:blending:YES consumes the secondary view's alphaTable. */
   unsigned char *unusedR,*unusedG,*unusedB;
   (void)[a111View colorTables:&a111A :&unusedR :&unusedG :&unusedB];
  }
  else (void)[a111View colorTables:&a111A :&a111R :&a111G :&a111B];
  NSMutableData *a111Palette=[NSMutableData dataWithLength:1024]; unsigned char *a111RGBA=(unsigned char*)a111Palette.mutableBytes;
  for(NSUInteger i=0;i<256;i++){a111RGBA[4*i]=a111R[i];a111RGBA[4*i+1]=a111G[i];a111RGBA[4*i+2]=a111B[i];a111RGBA[4*i+3]=a111Index ? a111A[i] : 255;}
  [a111Palette writeToFile:[a111File stringByAppendingString:@".rgba"] atomically:YES];
  const char *a111Name=a111Index ? "blendingTextureName" : "pTextureName";
  Ivar a111Ivar=class_getInstanceVariable((Class)objc_getClass("DCMView"),a111Name);
  if(!a111Ivar) { a111Synthetic=NO; break; }
  GLuint *a111Textures=*(GLuint**)((char*)a111Main+ivar_getOffset(a111Ivar));
  a111Layer[@"scalarDraw"]=@((id)[(id)[a111View horosScalarCLUTState] drawForArray:(NSUInteger)a111Textures]!=nil);
  a111Layer[@"textureCount"]=[(NSObject*)a111Main valueForKey:a111Index ? @"blendingTextureX" : @"textureX"];
  a111Layer[@"textureRows"]=[(NSObject*)a111Main valueForKey:a111Index ? @"blendingTextureY" : @"textureY"];
  if(a111Textures && (NSInteger)[a111Layer[@"textureCount"] integerValue]==1 && (NSInteger)[a111Layer[@"textureRows"] integerValue]==1) {
   glBindTexture(GL_TEXTURE_RECTANGLE_ARB,a111Textures[0]);
   GLint w=0,h=0,format=0; glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_ARB,0,GL_TEXTURE_WIDTH,&w);
   glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_ARB,0,GL_TEXTURE_HEIGHT,&h);
   glGetTexLevelParameteriv(GL_TEXTURE_RECTANGLE_ARB,0,GL_TEXTURE_INTERNAL_FORMAT,&format);
   if(w<1 || h<1 || w>4096 || h>4096) { a111Synthetic=NO; break; }
   a111Layer[@"textureSize"]=@[@(w),@(h)];a111Layer[@"textureFormat"]=@(format);
   NSMutableData *tex=[NSMutableData dataWithLength:(NSUInteger)w*h*4];
   glGetTexImage(GL_TEXTURE_RECTANGLE_ARB,0,GL_RED,GL_FLOAT,tex.mutableBytes);
   [tex writeToFile:[a111File stringByAppendingString:@".texture.f32"] atomically:YES];
  }
  [a111Layers addObject:a111Layer];
 }
 a111State[@"layers"]=a111Layers;
 glReadBuffer(GL_FRONT);
 NSMutableData *a111Output=[NSMutableData dataWithLength:(NSUInteger)a111Backing.size.width*(NSUInteger)a111Backing.size.height*4];
 glReadPixels(0,0,(int)a111Backing.size.width,(int)a111Backing.size.height,GL_BGRA,GL_UNSIGNED_BYTE,a111Output.mutableBytes);
 a111State[@"glError"]=@(glGetError()); glReadBuffer(a111ReadBuffer); glPopAttrib();glPopClientAttrib();glActiveTexture(a111Active);
 if(a111Previous) [a111Previous makeCurrentContext]; else [NSOpenGLContext clearCurrentContext];
 if(a111Synthetic) {
  [a111Output writeToFile:[PREFIX stringByAppendingString:@".bgra"] atomically:YES];
  [[NSJSONSerialization dataWithJSONObject:a111State options:3 error:nil]writeToFile:OUTPUT atomically:YES];
 }
}
'''
expression = expression.replace('TITLE','@'+json.dumps(args.title_prefix)).replace('PREFIX','@'+json.dumps(str(prefix))).replace('OUTPUT','@'+json.dumps(str(staged)))
commands = prefix.with_suffix('.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import OpenGL.GL\nexpression -l objc++ -- @import ObjectiveC\n'
                    'expression -l objc++ -- { '+' '.join(expression.splitlines())+' }\nprocess detach\n')
result = subprocess.run(['xcrun','lldb','--batch','-p',str(args.pid),'-s',str(commands)],capture_output=True,text=True)
prefix.with_suffix('.lldb.log').write_text(result.stdout+result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Capture failed or synthetic guard refused it; inspect the local LLDB log')
state = json.loads(staged.read_text());staged.replace(prefix.with_suffix('.json'))
print(args.label, 'layers',len(state['layers']),'Metal',state['metalEnabled'],'fallback',bool(state['fallback']),'GL',state['glError'])
for layer in state['layers']:
    print({k:layer.get(k) for k in ('modality','curImage','hasTransferFunction','hasFilter','stackMode','stack','hasSubtraction','shutterEnabled','scalarDraw','textureSize','textureFormat')})
