#import <Foundation/Foundation.h>

// A category needs the class itself, not a forward declaration, and
// HorosGSPSDocument is a Swift class: its interface only exists in the
// generated header. The guard keeps this header readable by tooling that runs
// before the Swift half of the target is compiled.
#if __has_include("Horos-Swift.h")
#import "Horos-Swift.h"

@interface HorosGSPSDocument (FileReading)

/// Reads a DICOM Softcopy Presentation State with DCMObject and builds the
/// documented subset. Pixel Data is not decoded.
+ (instancetype)documentWithContentsOfFile:(NSString *)path;

+ (NSDictionary *)dictionaryWithContentsOfFile:(NSString *)path;

@end

#endif
