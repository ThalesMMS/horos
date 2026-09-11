#import <Foundation/Foundation.h>

#ifdef __cplusplus
extern "C" {
#endif

/// Overlay a dicom.dic onto the process dictionary the application compiles.
/// Unknown VRs the 2005 parser cannot name are rewritten so the load stays quiet
/// and the keywords still resolve.
BOOL HorosLoadVendoredDicomDictionary(NSString *path);

/// The dicom.dic shipped with this process: the application bundle, or the file
/// sitting next to the executable (Decompress lives in Resources beside it).
NSString *HorosVendoredDicomDictionaryPath(void);

/// Resolve a keyword the way getDicomField:forFile: must: load the shipped
/// dictionary if it is there, then try the given spelling and the other 2011
/// spelling, and accept only a standard (even-group) tag.
BOOL HorosResolveDicomKeyword(NSString *keyword, unsigned *group, unsigned *element);

#ifdef __cplusplus
}
#endif
