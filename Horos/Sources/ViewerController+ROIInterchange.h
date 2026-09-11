/*
 ViewerController+ROIInterchange.h
 Horos

 Export and import of ROIs in the open JSON interchange format
 (see docs/roi-interchange-json.md). The schema, validation and image
 matching live in ROIInterchange.swift; this category converts between
 the interchange records and ROI/DCMPix objects and drives the UI.
*/

#import "ViewerController.h"

@interface ViewerController (ROIInterchange)

/** Adds "Export ROIs as JSON..." to the ROI menu, after "Save All ROIs of this Series...". */
+ (void) installROIInterchangeMenuItems;

/** Menu action: asks for a destination and writes every ROI of the series. */
- (IBAction) roiExportInterchange:(id) sender;

/** Writes every ROI of the series (all temporal positions) to url. */
- (BOOL) exportROIInterchangeToURL:(NSURL*) url error:(NSError**) error;

/** Reads a document, matches it against the open series and creates the ROIs.
    Returns NO with a reason in error when the file is invalid or does not belong to this series;
    in that case nothing is added. */
- (BOOL) importROIInterchangeFromPath:(NSString*) path error:(NSError**) error;

/** Classifies JSON / .roi / .rois_series, matches by identity and imports.
    A failed or incomplete match adds nothing. */
- (BOOL) importROIArchiveFromPath:(NSString*) path error:(NSError**) error;

/** Batch-imports .roi files by identity. File order and ROI names are not used as keys. */
- (BOOL) importROIFiles:(NSArray<NSString*>*) paths error:(NSError**) error;

/** importROIInterchangeFromPath:error: followed by an alert on failure. */
- (void) roiLoadFromInterchangeFile:(NSString*) path;

- (void) presentROIImportErrorForPath:(NSString*) path error:(NSError*) error;

@end
