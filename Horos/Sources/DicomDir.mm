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

#import "DicomDir.h"
#import "Horos-Swift.h"
#import "N2Debug.h"
#include <dcmtk/dcmdata/dcddirif.h>
#include "HorosDicomDirIcons.h"
#include <dcmtk/ofstd/ofstd.h>

#include <dcmtk/dcmjpeg/ddpiimpl.h>     /* for class DicomDirImageImplementation */


@implementation DicomDir

+(void)createDicomDirAtDir:(NSString*)path {
    [self createDicomDirAtDir:path error:NULL];
}

+(BOOL)createDicomDirAtDir:(NSString*)path error:(NSError**)error {
    if (error) *error = nil;
    HorosExportArchive *replacement = nil;

    
    try {
        @try {
            DicomDirInterface ddir;
        //  ddir.enableVerboseMode();
            ddir.disableConsistencyCheck(); // -W
            ddir.disableTransferSyntaxCheck(); // -Nxc
            ddir.enableInventMode(OFTrue); // +I
            
        //  ddir.enableIconImageMode(); // +X
            // One icon per series is added below through public directory records.
            ddir.setIconSize(128); // we let DicomDirInterface pick the icon size.. which, depending on the modality, will be either 128 or 64

            DicomDirImageImplementation imagePlugin;
            ddir.addImageSupport(&imagePlugin);
            
            OFList<OFString> fileNames;
            OFStandard::searchDirectoryRecursively("", fileNames, NULL, path.fileSystemRepresentation); // +r +id burnFolder
            
            NSString* dicomdirPath = [path stringByAppendingPathComponent:[NSString stringWithUTF8String:DEFAULT_DICOMDIR_NAME]];
            replacement = [[HorosExportArchive alloc] initWithDestinationPath:dicomdirPath error:error];
            if (!replacement) return NO;
            OFCondition result = ddir.createNewDicomDir(DicomDirInterface::AP_USBandFlashJPEG, [replacement.archivePath fileSystemRepresentation], DEFAULT_FILESETID); // -Pfl
            if (!result.good())
                [NSException raise:NSGenericException format:@"Couldn't create new DICOMDIR file: %s", result.text()];
                
            ddir.setFilesetDescriptor(NULL, DEFAULT_DESCRIPTOR_CHARSET); // UTF-8 ?
            
            for (OFListIterator(OFString) iter = fileNames.begin(); iter != fileNames.end(); ++iter) {
                NSString *relativePath = [NSString stringWithUTF8String:(*iter).c_str()];
                NSString *name = relativePath.lastPathComponent;
                // Index files and macOS metadata are not source DICOM instances.
                if ([relativePath isEqualToString:@"DICOMDIR"] || [relativePath isEqualToString:@"DICOMDIR.BAK"] ||
                    [name isEqualToString:@".DS_Store"] || [name hasPrefix:@"._"] ||
                    [[relativePath.pathComponents firstObject] hasPrefix:@".horos-zip-"])
                    continue;
                result = ddir.addDicomFile((*iter).c_str(), path.fileSystemRepresentation);
                if (result.bad())
                    [NSException raise:NSGenericException format:@"Couldn't add %s to DICOMDIR: %s", (*iter).c_str(), result.text()];
            }
            
            result = ddir.writeDicomDir(EET_ExplicitLength, EGL_withoutGL);
            if (!result.good())
                [NSException raise:NSGenericException format:@"Couldn't write DICOMDIR file: %s", result.text()];
            
            HorosDicomDirIcons icons;
            result = icons.addSeriesIcons(replacement.archivePath.fileSystemRepresentation, path.fileSystemRepresentation);
            if (result.bad())
                [NSException raise:NSGenericException format:@"Could not write DICOMDIR series icons: %s", result.text()];
            chmod([replacement.archivePath fileSystemRepresentation], 0755);
            return [replacement commitWithError:error];
        }
        @catch (NSException *exception) {
            N2LogException( exception);
            if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:
                @{NSLocalizedDescriptionKey: NSLocalizedString(@"DICOMDIR export could not be completed.", nil),
                  NSLocalizedFailureReasonErrorKey: exception.reason ?: @"",
                  NSFilePathErrorKey: path ?: @""}];
        }
        @finally {
            [replacement release];
        }
    } catch (std::exception &e) {
        std::cout << e.what() << std::endl;
        if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:
            @{NSLocalizedDescriptionKey: NSLocalizedString(@"DICOMDIR export could not be completed.", nil),
              NSLocalizedFailureReasonErrorKey: [NSString stringWithUTF8String:e.what()] ?: @"",
              NSFilePathErrorKey: path ?: @""}];
    }
    return NO;
}

@end
