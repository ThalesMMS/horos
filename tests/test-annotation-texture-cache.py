#!/usr/bin/env python3
"""Compile the production annotation cache path with AppKit fonts."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
path='Horos/Sources/DCMView.m'
s=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
a=s.index('#define STRCAPACITY',s.index('- (void)DrawNSStringGL:'));b=s.index('        if(align==DCMViewTextAlignRight)',a)
code=r'''
#import <Cocoa/Cocoa.h>
#import "AnnotationPresentation-Swift.h"
typedef unsigned int GLuint;
static NSMutableArray *globalStringTextureCache;
@interface Window:NSObject
@property CGFloat backingScaleFactor;
@end
@implementation Window
@end
@interface StringTexture:NSObject
@property(retain) NSFont*font;
@property NSSize texSize;
// The view asks its textures to anti-alias since 4c0d5b0; the stub has to
// answer, or the cache under test is never reached.
@property BOOL antiAliasing;
@end
@implementation StringTexture
-(id)initWithString:(NSString*)s withAttributes:(NSDictionary*)a {if((self=[super init])){self.font=a[NSFontAttributeName];self.texSize=[s sizeWithAttributes:a];}return self;}
-(void)genTextureWithBackingScaleFactor:(CGFloat)scale {self.texSize=NSMakeSize(self.texSize.width*scale,self.texSize.height*scale);}
@end
@interface View:NSObject {
@public NSMutableDictionary*stringTextureCache;NSFont*labelFont,*fontGL;GLuint labelFontListGL;
}
@property(retain) Window*window;
@end
@implementation View
-(StringTexture*)texture:(NSString*)str fontList:(GLuint)fontL {
BODY
return stringTex;
}
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 [NSApplication sharedApplication];View*v=[View new];v.window=[Window new];v->labelFontListGL=7;
 NSString*text=@"Point 1 / Zoom: 100%";
 for(NSNumber*scale in @[@1,@2,@1,@2])for(NSNumber*size in @[@12,@20,@12]){
  v.window.backingScaleFactor=scale.doubleValue;
  v->labelFont=[NSFont fontWithName:@"Helvetica" size:12];
  v->fontGL=[NSFont fontWithName:@"Courier" size:size.doubleValue];
  for(NSNumber*fontList in @[@7,@9]){
   NSFont*font=fontList.intValue==7?v->labelFont:v->fontGL;
   StringTexture*t=[v texture:text fontList:fontList.intValue];
   NSSize expected=[text sizeWithAttributes:@{NSFontAttributeName:font}];
   check([t.font isEqual:font]);
   check(fabs(t.texSize.width-expected.width*scale.doubleValue)<0.001);
   check(fabs(t.texSize.height-expected.height*scale.doubleValue)<0.001);
   check(t==[v texture:text fontList:fontList.intValue]);
  }
 }
 check(v->stringTextureCache.count<=STRCAPACITY+1);
 NSLog(@"PASS: identical text across annotation/label fonts, 12/20/12 sizes, 1x/2x pre-draw metrics and cache reuse");
}}
'''.replace('BODY',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-annotation-cache-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 (p/'AnnotationPresentation.swift').write_bytes((root/'Horos/Sources/AnnotationPresentation.swift').read_bytes())
 subprocess.run(['xcrun','swiftc',str(p/'AnnotationPresentation.swift'),'-emit-library','-module-name','AnnotationPresentation','-emit-objc-header-path',str(p/'AnnotationPresentation-Swift.h'),'-o',str(p/'libAnnotationPresentation.dylib')],check=True)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa','-I',d,str(p/'test.m'),'-L',d,'-lAnnotationPresentation','-Wl,-rpath,'+d,'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
