/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation,  version 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE.  See the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos.  If not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program:   OsiriX
  Copyright (c) OsiriX Team
  All rights reserved.
  Distributed under GNU - LGPL
  
  See http://www.osirix-viewer.com/copyright.html for details.
     This software is distributed WITHOUT ANY WARRANTY; without even
     the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
     PURPOSE.
 ============================================================================*/


#import <Cocoa/Cocoa.h>
#import "DicomFile.h"

/** \brief  C++ calls for DicomFile 
*
*  Some C++ header from DCMTK and other C++ libs can conflict with Objective C during compilation.
*  Putting them in a separate category prevents compilation errors.
*/

@interface DicomFile (DicomFileDCMTKCategory)

+ (NSArray*) getEncodingArrayForFile: (NSString*) file;
+ (BOOL) isDICOMFileDCMTK:(NSString *) file; /**< Check for validity of DICOM using DCMTK */
+ (BOOL) isNRRDFile:(NSString *) file; /**< Test for NRRD file format */
+ (NSString*) getDicomField: (NSString*) field forFile: (NSString*) path;
+ (NSDictionary*) acquisitionTimingForFile: (NSString*) path;
+ (NSString*) getDicomFieldForGroup:(int) gr element: (int) el forDcmFileFormat: (void*) ff;
/** Several fields from one file, opened once, decoded with the file's own
    character set. A field that is absent is absent from the dictionary, so a
    caller can tell "not there" from "there and empty". Each specification is a
    DICOM keyword (PatientName) or a tag written (gggg,eeee). */
+ (NSDictionary*) valuesForDicomFields: (NSArray*) fields forFile: (NSString*) path;
/** A fresh Series Instance UID, for a series this application derives. */
+ (NSString*) newSeriesUID;

#if __has_include("Horos-Swift.h")
/** Write a rectangle of an image as a new, derived instance: Rows and Columns
    become the rectangle, the pixels are exactly that rectangle of the original,
    Image Position (Patient) moves to the new first pixel, and the result carries
    its own SOP Instance UID with the original in its Source Image Sequence. The
    original file is not touched. Refuses encapsulated pixel data. */
+ (BOOL) writeCropOfFile: (NSString*) source
                  toPath: (NSString*) destination
                  column: (int) column row: (int) row
                   width: (int) width height: (int) height
               seriesUID: (NSString*) seriesUID
            seriesNumber: (int) seriesNumber
                   error: (NSError**) error;
#endif

- (short) getDicomFileDCMTK; /**< Decode DICOM using DCMTK.  Returns 0 on success -1 on failure. */
- (short) getNRRDFile; /**< decode NRRD file format.  Returns 0 on success -1 on failure. */
@end
