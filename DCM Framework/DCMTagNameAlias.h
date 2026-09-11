#import <Foundation/Foundation.h>

/// The other 2011 spelling of a DICOM keyword, or nil when the name has only
/// one form. `PatientName` <-> `PatientsName`. Keep in lockstep with
/// `HorosDICOMKeyword`.
FOUNDATION_EXPORT NSString *DCMTagNameOtherSpelling(NSString *name);
