#import <Foundation/Foundation.h>

/// An identifier for an object that arrived without one.
///
/// A file with no `SeriesInstanceUID` was indexed with an **empty** series
/// identifier, and one with no `StudyInstanceUID` was indexed under the
/// patient's name — which the C-FIND SCP then answers with, as a `UI`. Neither
/// is a UID: `UI` allows 64 characters of digits and dots.
///
/// The identifier is **derived**, not generated: the same file, imported twice,
/// yields the same UID, so a re-import lands in the series it landed in before.
/// That is why this is not `dcmGenerateUniqueIdentifier`, which is what the
/// exporter uses when it is creating something genuinely new.
///
/// The root is the one this application already mints under elsewhere: DCMTK's
/// `SITE_UID_ROOT`, OFFIS's `1.2.276.0.7230010.3`, with the `.1.2` and `.1.3`
/// arcs `DICOMExport` uses for studies and series.
///
/// This is Objective-C rather than Swift because the file that needs it is
/// compiled into the Decompress helper as well as the application, and that
/// target has no Swift.
@interface HorosDerivedUID : NSObject

+ (NSString*) studyRoot;
+ (NSString*) seriesRoot;

/// A UID under `root`, determined entirely by `key`.
+ (NSString*) uidForKey:(NSString*) key root:(NSString*) root;

/// A `SeriesInstanceUID` for a file that carries none, from the key the importer
/// groups that series on.
+ (NSString*) seriesUIDForKey:(NSString*) key;

/// A `StudyInstanceUID` for a file that carries none.
+ (NSString*) studyUIDForKey:(NSString*) key;

/// Whether a string is something `UI` can hold: at most 64 characters, only
/// digits and dots, no empty component, no leading zero in a component.
+ (BOOL) isConformantUID:(NSString*) value;

@end
