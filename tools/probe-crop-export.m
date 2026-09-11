// Diagnostic-only probe for #120: write a cropped, derived instance and stop.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-crop-export.m \
//     -o local-validation/work/crop120/probe.dylib
//
// HOROS_CROP_SOURCE, HOROS_CROP_DESTINATION and HOROS_CROP_RECT="col,row,w,h".
// It calls +[DicomFile writeCropOfFile:...], which is what a crop command would
// call, and reports. It does not touch the source file or the database.
#import <Cocoa/Cocoa.h>

@interface NSObject (CropProbe)
+ (BOOL)writeCropOfFile:(NSString*)source toPath:(NSString*)destination
                 column:(int)column row:(int)row width:(int)width height:(int)height
              seriesUID:(NSString*)seriesUID seriesNumber:(int)seriesNumber
                  error:(NSError**)error;
@end

__attribute__((constructor)) static void install(void) {
    const char *source = getenv("HOROS_CROP_SOURCE");
    const char *destination = getenv("HOROS_CROP_DESTINATION");
    const char *rect = getenv("HOROS_CROP_RECT");
    if (!source || !destination || !rect) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
    NSArray *parts = [[NSString stringWithUTF8String:rect] componentsSeparatedByString:@","];
    if (parts.count != 4) return;
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *n) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 8 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            Class file = NSClassFromString(@"DicomFile");
            if (![file respondsToSelector:@selector(writeCropOfFile:toPath:column:row:width:height:seriesUID:seriesNumber:error:)]) {
                NSLog(@"CROP120 DicomFile does not answer the crop writer");
                return;
            }
            NSError *error = nil;
            BOOL ok = [file writeCropOfFile:[NSString stringWithUTF8String:source]
                                     toPath:[NSString stringWithUTF8String:destination]
                                     column:[parts[0] intValue] row:[parts[1] intValue]
                                      width:[parts[2] intValue] height:[parts[3] intValue]
                                  seriesUID:@"1.2.826.0.1.3680043.8.498.120120120120120120120120120120120120"
                               seriesNumber:120 error:&error];
            NSLog(@"CROP120 wrote=%d %@", ok, error.localizedDescription ?: @"");
            NSLog(@"CROP120 done");
        });
    }];
}
