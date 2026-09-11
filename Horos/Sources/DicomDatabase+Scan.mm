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

#import "DicomDatabase+Scan.h"
#import "HorosBoundedTask.h"
#import "NSThread+N2.h"
#import "NSDate+N2.h"
#import <dcmtk/dcmdata/dcdicdir.h>
#import "NSString+N2.h"
#import "NSFileManager+N2.h"
#import "DicomImage.h"
#import "N2Debug.h"
#import "DicomFile.h"
#import "MutableArrayCategory.h"
#import "BrowserController.h"
#import "DCMPix.h"
#import "ThreadsManager.h"
#import "DiscMountedAskTheUserDialogController.h"
#import "Horos-Swift.h"
#import "DCMAbstractSyntaxUID.h"
#import "N2Stuff.h"
#import "DICOMToNSString.h"
#import "DicomDirParser.h"

@interface _DicomDatabaseScanDcmElement : NSObject {
	DcmElement* _element;
}

+(id)elementWithElement:(DcmElement*)element;
-(id)initWithElement:(DcmElement*)element;
-(DcmElement*)element;
-(NSString*)stringValue;
-(NSString*)stringValueWithEncodings: (NSStringEncoding*) encodings;
-(NSInteger)integerValue;
-(NSNumber*)integerNumberValue;
-(NSString*)name;

@end


@interface NSMutableDictionary (DicomDatabaseScan)

@end

@implementation NSMutableDictionary (DicomDatabaseScan)

-(id)objectForKeyRemove:(id)key {
	id temp = [[self objectForKey:key] retain];
	[self removeObjectForKey:key];
	return [temp autorelease];
}

-(void)conditionallySetObject:(id)obj forKey:(id)key {
	if (obj)
		[self setObject:obj forKey:key];
//	else NSLog(@"Not setting %@", key);
}

@end





@implementation DicomDatabase (Scan)

/*-(NSString*)describeObject:(DcmObject*)obj {
	const DcmTagKey& key = obj->getTag();
	DcmTag dcmtag(key);
	DcmVR dcmev(obj->ident());
	
	return [NSString stringWithFormat:@"%s %s %s %s", dcmev.getVRName(), key.toString().c_str(), dcmtag.getTagName(), dcmtag.getVRName()];
}

-(NSArray*)describeElementValues:(DcmElement*)obj {
	NSMutableArray* v = [NSMutableArray array];
	
	unsigned int vm = obj->getVM();
	if (vm)
		for (int i = 0; i < vm; ++i) {
			OFString value;
			if (((DcmByteString*)obj)->getOFString(value,i).good())
				[v addObject:[NSString stringWithFormat:@"[%d] %s", i, value.c_str()]];
		}
	
	return v;
}*/

/*-(_DicomDatabaseScanDcmElement*)_dcmElementForKey:(NSString*)key inContext:(NSArray*)context {
	for (NSInteger i = (long)context.count-1; i >= 0; --i) {
		NSDictionary* elements = [context objectAtIndex:i];
		_DicomDatabaseScanDcmElement* ddsde = [elements objectForKey:key];
		if (ddsde) return ddsde;
	}
	
	return nil;
}*/

static NSString* _dcmElementKey(Uint16 group, Uint16 element) {
	return [NSString stringWithFormat:@"%04X,%04X", group, element];
}

static NSString* _dcmElementKey(DcmElement* element) {
    if( element == nil)
        return _dcmElementKey(0x0, 0x0);
    
	const DcmTagKey& key = element->getTag();
	return _dcmElementKey(key.getGroup(), key.getElement());
}

+(NSImage*)_nsImageForElement:(DcmItem*)thumb {
    // ftp://medical.nema.org/medical/dicom/2011/11_03pu.pdf F.7 ICON IMAGE KEY DEFINITION
    
    // Pixel samples have a Value of either 1 or 8 for Bits Allocated (0028,0100) and Bits Stored (0028,0101)
    Uint16 bitsAllocated, bitsStored;
    if (!thumb->findAndGetUint16(DcmTagKey(0x0028,0x0100), bitsAllocated).good()) return nil;
    if (!thumb->findAndGetUint16(DcmTagKey(0x0028,0x0101), bitsStored).good()) return nil;
    if (bitsAllocated != 1 && bitsAllocated != 8) return nil;
    if (bitsStored != 1 && bitsStored != 8) return nil;
    
    Uint16 width, height;
    if (!thumb->findAndGetUint16(DcmTagKey(0x0028,0x0010), height).good()) return nil; // Rows must be defined
    if (!thumb->findAndGetUint16(DcmTagKey(0x0028,0x0011), width).good()) return nil; // Columns must be defined
    
    const Uint8* data = nil;
    if (!thumb->findAndGetUint8Array(DcmTagKey(0x7fe0,0x0010), data).good()) return nil; // PixelRepresentation must be defined
    
    NSBitmapImageRep* rep = nil;
    if( data) {
        // Photometric Interpretation (0028,0004) shall have a Value of either MONOCHROME 1, MONOCHROME 2 or PALETTE COLOR
        OFString spi;
        if (!thumb->findAndGetOFString(DcmTagKey(0x0028,0x0004), spi).good()) return nil;
        
        if (spi == "MONOCHROME1") {
            rep = [[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:nil pixelsWide:width pixelsHigh:height bitsPerSample:bitsStored samplesPerPixel:1 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceWhiteColorSpace bytesPerRow:0 bitsPerPixel:bitsAllocated] autorelease];
            unsigned char* bitmapData = rep.bitmapData;
            // invert data
            for (NSUInteger i = 0; i < width*height*bitsAllocated/8; ++i) {
                if (bitsAllocated == 1)
                    bitmapData[i] = data[i]^0xff;
                else bitmapData[i] = 0xff-data[i];
            }
        } else
        if (spi == "MONOCHROME2") {
            rep = [[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:nil pixelsWide:width pixelsHigh:height bitsPerSample:bitsStored samplesPerPixel:1 hasAlpha:NO isPlanar:NO colorSpaceName:NSDeviceWhiteColorSpace bytesPerRow:width*8/bitsAllocated bitsPerPixel:bitsAllocated] autorelease];
            memcpy(rep.bitmapData, data, ceilf(1.0*width*height*bitsAllocated/8));
        } else
        if (spi == "PALETTE COLOR") {
            return nil; // TODO: this type of thumbnail should be read too...
        } else
            return nil;
    }
    else
        return nil;
    
    if( rep)
    {
        NSImage* im = [[[NSImage alloc] init] autorelease];
        [im addRepresentation:rep];
        return im;
    }
    
    return nil;
}

-(NSMutableArray*)_itemsInRecord:(DcmDirectoryRecord*)record context:(NSMutableArray*)context basePath:(NSString*)basepath {
//	NSString* tabs = [NSString stringByRepeatingString:@" " times:context.count*4];
	NSMutableArray* items = [NSMutableArray array];
	NSMutableDictionary* elements = [NSMutableDictionary dictionary];
	[context addObject:elements];
	
	//NSLog(@"%@Record %@", tabs, [self describeObject:record]);
	
	for (unsigned int i = 0; i < record->card(); ++i) {
		DcmElement* element = record->getElement(i);
		
		/*NSLog(@"%@Element %@", tabs, [self describeObject:element]);
		NSArray* values = [self describeElementValues:element];
		for (NSString* s in values)
			NSLog(@"%@%@", tabs, s);*/
		
		[elements setObject:[_DicomDatabaseScanDcmElement elementWithElement:element] forKey:_dcmElementKey(element)];
	}
	
	_DicomDatabaseScanDcmElement* elementReferencedFileID = [elements objectForKey: @"0004,1500"];
	if (elementReferencedFileID)
    {
		NSString* path = [elementReferencedFileID stringValue];
		path = [path stringByReplacingOccurrencesOfString:@"\\" withString:@"/"];
		path = [basepath stringByAppendingPathComponent:path];
		NSString* temp;
		NSInteger tempi;
		
        if( path.length < MAXPATHLEN)
        {
            NSMutableDictionary* item = [NSMutableDictionary dictionaryWithObject:path forKey:@"filePath"];

            NSMutableDictionary* elements = [NSMutableDictionary dictionary];
            for (NSDictionary* e in context)
                [elements addEntriesFromDictionary:e];
            
            //NSLog(@"\n\n%@\nDICOMDIR info:%@", path, elements);
            
            // Both MPEG-2 syntaxes, Main Level and High Level: the viewer decodes
            // neither, and only the first was being recognised.
            NSString *dicomdirTransferSyntax = [[elements objectForKeyRemove: @"0004,1512"] stringValue];
            if ([dicomdirTransferSyntax isEqualToString:@"1.2.840.10008.1.2.4.100"] ||
                [dicomdirTransferSyntax isEqualToString:@"1.2.840.10008.1.2.4.101"])
                [item setObject:@"DICOMMPEG2" forKey:@"fileType"];
            else [item setObject:@"DICOM" forKey:@"fileType"];
            
            [item conditionallySetObject:[NSNumber numberWithBool:YES] forKey:@"hasDICOM"];
            
            temp = [[elements objectForKeyRemove: @"0008,0016"] stringValue];
            if (!temp) temp = [[elements objectForKey: @"0004,1510"] stringValue];
            [item conditionallySetObject:temp forKey:@"SOPClassUID"];
            [elements removeObjectForKey: @"0004,1510"];
            
            temp = [[elements objectForKeyRemove: @"0008,0018"] stringValue];
            if (!temp) temp = [[elements objectForKey: @"0004,1511"] stringValue];
            [item conditionallySetObject:temp forKey:@"SOPUID"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0004,1511"] stringValue] forKey:@"referencedSOPInstanceUID"];
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,0005"] stringValue] forKey:@"specificCharacterSet"];
            
            NSStringEncoding encodings[ 10];
            NSArray	*c = [[[elements objectForKeyRemove: @"0008,0005"] stringValue] componentsSeparatedByString:@"\\"];
            
            if( [c count] >= 10) NSLog( @"Encoding number >= 10 ???");
            
            if( [c count] < 10)
            {
                for( int i = 0; i < [c count]; i++) encodings[ i] = [NSString encodingForDICOMCharacterSet: [c objectAtIndex: i]];
                for( int i = [c count]; i < 10; i++) encodings[ i] = [NSString encodingForDICOMCharacterSet: [c lastObject]];
            }
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0020,000D"] stringValue] forKey:@"studyID"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0020,0010"] stringValue] forKey:@"studyNumber"];
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,1030"] stringValueWithEncodings: encodings] forKey:@"studyDescription"];
            
            [item conditionallySetObject:[NSDate dateWithYYYYMMDD:[[elements objectForKeyRemove: @"0008,0020"] stringValue] HHMMss:[[elements objectForKeyRemove: @"0008,0030"] stringValue]] forKey:@"studyDate"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,0060"] stringValue] forKey:@"modality"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0010,0020"] stringValue] forKey:@"patientID"];
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0010,0010"] stringValueWithEncodings: encodings] forKey:@"patientName"];

            [item conditionallySetObject:[NSDate dateWithYYYYMMDD:[[elements objectForKeyRemove: @"0010,0030"] stringValue] HHMMss:nil] forKey:@"patientBirthDate"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0010,0040"] stringValue] forKey:@"patientSex"];
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,0050"] stringValue] forKey:@"accessionNumber"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0004,1511"] stringValue] forKey:@"referencedSOPInstanceUID"];
            
            [item conditionallySetObject:[DicomFile patientUID: item] forKey:@"patientUID"];
            
            [item conditionallySetObject:[NSNumber numberWithInteger:1] forKey:@"numberOfSeries"];
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0028,0008"] integerNumberValue] forKey:@"numberOfFrames"];
            if( [[item objectForKey:@"numberOfFrames"] integerValue] > 1) // SERIES ID MUST BE UNIQUE!!!!!
            {
                NSString *newSerieID = [NSString stringWithFormat:@"%@-%@", [[elements objectForKeyRemove: @"0020,000E"] stringValue], [item objectForKey: @"SOPUID"]];
                [item conditionallySetObject:newSerieID forKey:@"seriesDICOMUID"]; // SeriesInstanceUID
            }
            else
                [item conditionallySetObject:[[elements objectForKeyRemove: @"0020,000E"] stringValue] forKey:@"seriesDICOMUID"]; // SeriesInstanceUID
            
            id seriesNumberAttribute = [elements objectForKeyRemove:@"0020,0011"];
            NSString *seriesNumber = [seriesNumberAttribute stringValue];
            if( seriesNumber)
            {
                NSString *n = [NSString stringWithFormat:@"%8.8d %@", [seriesNumber intValue] , [item objectForKey: @"seriesDICOMUID"]];
                [item conditionallySetObject: n forKey:@"seriesID"];
            }
            else
                [item conditionallySetObject: [item objectForKey: @"seriesDICOMUID"] forKey:@"seriesID"];
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,103E"] stringValueWithEncodings: encodings] forKey:@"seriesDescription"];
            [item conditionallySetObject:[seriesNumberAttribute integerNumberValue] forKey:@"seriesNumber"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0020,0013"] integerNumberValue] forKey:@"imageID"];
            
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,0080"] stringValueWithEncodings: encodings] forKey:@"institutionName"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,0090"] stringValueWithEncodings: encodings] forKey:@"referringPhysiciansName"];
            [item conditionallySetObject:[[elements objectForKeyRemove: @"0008,1050"] stringValueWithEncodings: encodings] forKey:@"performingPhysiciansName"];
            
            tempi = [[elements objectForKeyRemove: @"0028,0010"] integerValue];
            [item conditionallySetObject:[NSNumber numberWithInteger:tempi? tempi : OsirixDicomImageSizeUnknown] forKey:@"height"];
            tempi = [[elements objectForKeyRemove: @"0028,0011"] integerValue];
            [item conditionallySetObject:[NSNumber numberWithInteger:tempi? tempi : OsirixDicomImageSizeUnknown] forKey:@"width"];
            
            // thumbnail
            _DicomDatabaseScanDcmElement* thumbnailElement = [elements objectForKeyRemove: @"0088,0200"]; // IconImageSequence
            if (thumbnailElement && thumbnailElement.element->ident() == EVR_SQ && ((DcmSequenceOfItems*)thumbnailElement.element)->card() == 1) {
                DcmItem* thumb = ((DcmSequenceOfItems*)thumbnailElement.element)->getItem(0);
                NSImage* im = [[self class] _nsImageForElement:thumb];
                if (im)
                    [item setObject:im forKey:@"NSImageThumbnail"];
            }
            
    /*		[item setObject:path forKey:@"date"];
            [item setObject:path forKey:@"seriesDICOMUID"];
            [item setObject:path forKey:@"protocolName"];
            [item setObject:path forKey:@"numberOfFrames"];
            [item setObject:path forKey:@"SOPUID* ()"];
            [item setObject:path forKey:@"imageID* ()"];
            [item setObject:path forKey:@"sliceLocation"];
            [item setObject:path forKey:@"numberOfSeries"];
            [item setObject:path forKey:@"numberOfROIs"];
            [item setObject:path forKey:@"commentsAutoFill"];
            [item setObject:path forKey:@"seriesComments"];
            [item setObject:path forKey:@"studyComments"];
            [item setObject:path forKey:@"stateText"];
            [item setObject:path forKey:@"keyFrames"];
            [item setObject:path forKey:@"album"];*/
            
            [elements removeObjectForKey: @"0004,1500"]; // ReferencedFileID = IMAGES\IM000000
            [elements removeObjectForKey: @"0004,1400"]; // OffsetOfTheNextDirectoryRecord = 0
            [elements removeObjectForKey: @"0004,1410"]; // RecordInUseFlag = 65535
            [elements removeObjectForKey: @"0004,1420"]; // OffsetOfReferencedLowerLevelDirectoryEntity = 0
            [elements removeObjectForKey: @"0004,1430"]; // DirectoryRecordType = IMAGE
            [elements removeObjectForKey: @"0008,0005"]; // SpecificCharacterSet = ISO_IR 100
            [elements removeObjectForKey: @"0008,0008"]; // ImageType = ORIGINAL\PRIMARY
            [elements removeObjectForKey: @"0008,0081"]; // InstitutionAddress =
            [elements removeObjectForKey: @"0859,0010"]; // PrivateCreator = ETIAM DICOMDIR
            [elements removeObjectForKey: @"0859,1040"]; // Unknown Tag & Data = 13156912
            
            //if (elements.count) NSLog(@"\nUnused DICOMDIR info for %@: %@", path, elements);
            if (elements.count) [item setObject:elements forKey:@"DEBUG"];

            [items addObject:item];
        }
        else
            N2LogStackTrace( @"path > MAXPATHLEN : %d characters, %@", (int) path.length, path);
	}
	
	for (unsigned long i = 0; i < record->cardSub(); ++i)
		[items addObjectsFromArray:[self _itemsInRecord:record->getSub(i) context:context basePath:basepath]];
	
	[context removeLastObject];
	return items;
}

-(NSMutableArray*)_itemsInRecord:(DcmDirectoryRecord*)record basePath:(NSString*)basepath {
	return [self _itemsInRecord:record context:[NSMutableArray array] basePath:basepath];
}

-(NSString*)_fixedPathForPath:(NSString*)path withPaths:(NSArray*)allpaths { // path was listed in DICOMDIR and [NSFileManager.defaultManager fileExistsAtPath:path] says NO
	NSString* cutpath = [path stringByDeletingPathExtension];
	NSString* returnString = nil;
    
    @autoreleasepool
    {
        @try {
            for (NSString* ipath in allpaths)
                if ([[ipath stringByDeletingPathExtension] compare:cutpath options:NSCaseInsensitiveSearch] == NSOrderedSame)
                {
                    returnString = [ipath copy];
                    break;
                }
        }
        @catch (NSException *exception) {
            N2LogException( exception);
        }
	}
    
	return [returnString autorelease];
}

+(BOOL)_item:(NSDictionary*)item isOnlyEntryForItsSeriesInItems:(NSArray*)items {
    NSString* seriesInstanceUID = [item objectForKey:@"seriesID"];
    for (NSDictionary* i2 in items)
        if (i2 != item && [[i2 objectForKey:@"seriesID"] isEqualToString:seriesInstanceUID])
            return NO;
    return YES;
}

-(NSArray*)scanDicomdirAt:(NSString*)path withPaths:(NSArray*)allpaths pathsToScanAnyway:(NSMutableArray*)pathsToScanAnyway {
	NSThread* thread = [NSThread currentThread];
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"validateFilesBeforeImporting"])
    {
        // Test DICOMDIR validity on a separate process...
        if( [[NSFileManager defaultManager] fileExistsAtPath: [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/Decompress"]])
        {
            NSTask *aTask = [[[NSTask alloc] init] autorelease];
            [aTask setLaunchPath: [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/Decompress"]];
            [aTask setArguments: [NSArray arrayWithObjects: path, @"testDICOMDIR", nil]];
            
            // A DICOMDIR that cannot be validated is refused, which is what the
            // termination status below already did; a validator that will not
            // start, or will not finish, now reaches the same answer instead of
            // raising or waiting forever.
            NSError *taskError = nil;
            if( HorosRunTaskUntilExit( aTask, 60, &taskError) == NO)
            {
                NSLog( @"****** could not validate DICOMDIR %@: %@", path, taskError.localizedDescription);
                return nil;
            }
            
            if( [aTask terminationStatus] != 0)
            {
                NSLog( @"****** failed to read DICOMDIR: %@", path);
                return nil;
            }
        }
    }
    
	DcmDicomDir dcmdir([path fileSystemRepresentation]);
	DcmDirectoryRecord& record = dcmdir.getRootRecord();
	NSMutableArray* items = [self _itemsInRecord:&record basePath:[path stringByDeletingLastPathComponent]];
	
    BOOL notFoundFiles = NO;
    
	// file paths are sometimes wrong the DICOMDIR, see if these files exist
	for (NSInteger i = (long)items.count-1; i >= 0; --i)
    {
        NSMutableDictionary* item = [items objectAtIndex:i];
        
		NSString* filepath = [item objectForKey:@"filePath"];
		if (![NSFileManager.defaultManager fileExistsAtPath:filepath])
        { // reference invalid, try and find the file...
			filepath = [self _fixedPathForPath:filepath withPaths:allpaths];
            
			if( filepath) [item setObject:filepath forKey:@"filePath"];
            
            notFoundFiles = YES;
		}
        
        // some DICOMDIR files only list 1 image for 1 multiframe DICOM file
        NSString* scuid = [item objectForKey:@"SOPClassUID"];
        if( ([DCMAbstractSyntaxUID isMultiframe:scuid]) && [[self class] _item:item isOnlyEntryForItsSeriesInItems:items])
        {
            [pathsToScanAnyway addObject:filepath];
            [items removeObjectAtIndex:i];
        }
        
        if ([thread isCancelled]) 
            break;
	}
    
    // DUMP the DICOMDIR... did we miss some files??
    if( items.count <= 1 || notFoundFiles == YES)
    {
        NSLog( @"dcmdump DICOMDIR");
        @try
        {
            NSMutableArray *files = [NSMutableArray array];
            DicomDirParser *parsed = [[DicomDirParser alloc] init: path];
            [parsed parseArray: files];
            [parsed release];
            
            if( files.count > items.count * 2) //We found more than 50% more files... Let's use only the files discovered by the DicomDirParser
            {
                [items removeAllObjects];
                [pathsToScanAnyway addObjectsFromArray: files];
            }
            else
            {
                for( NSDictionary *item in items)
                    [files removeObject: [item objectForKey:@"filePath"]];
                
                [pathsToScanAnyway addObjectsFromArray: files];
            }
        }
        @catch (NSException *exception)
        {
            N2LogStackTrace( @"%@", exception);
        }
    }
    
    NSArray* objectIDs = nil;
    if (items.count) {
        thread.status = [NSString stringWithFormat:NSLocalizedString(@"Importing %@...", nil), N2LocalizedSingularPluralCount(items.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil))];
        objectIDs = [self addFilesDescribedInDictionaries:items postNotifications:NO rereadExistingItems:NO generatedByOsiriX:NO importedFiles:NO returnArray: YES];
    }
    
    return [self objectsWithIDs:objectIDs];
}

+(NSString*)_findDicomdirIn:(NSArray*)allpaths  {
	NSString* candidate = nil;
	
	for (NSString* path in allpaths) {
		NSString* filename = [path lastPathComponent];
		NSString* ucfilename = [filename uppercaseString];
		if ([ucfilename isEqualToString:@"DICOMDIR"] || [ucfilename isEqualToString:@"DICOMDIR."])
			if (!candidate || candidate.length > path.length)
				candidate = path;
	}
	
	return candidate;
}

-(void)_requestZipPassword:(NSArray*)args {
	[[BrowserController currentBrowser] askForZIPPassword:[args objectAtIndex:0] destination:[args objectAtIndex:1]];
}

-(void)_askUserDiscDataCopyOrBrowse:(NSArray*)a {
    NSString* path = [a objectAtIndex:0];
    NSInteger count = [[a objectAtIndex:1] integerValue];
    NSInteger* mode = (NSInteger*)[[a objectAtIndex:2] pointerValue];
    
    DiscMountedAskTheUserDialogController* dialog = [[DiscMountedAskTheUserDialogController alloc] initWithMountedPath:path dicomFilesCount:count];
    [dialog.window center];
    
    [NSApp runModalForWindow:dialog.window];
    
    *mode = dialog.choice;
    
    [dialog.window close];
    
    [dialog release];
    
}

-(BOOL)scanAtPath:(NSString*)path isVolume:(BOOL)isVolume
{
	NSThread* thread = [NSThread currentThread];
	[thread enterOperation];
	@try
    {
        NSArray* dicomImages = [NSArray array];

        // "Minutes per image" is the report, and one elapsed time cannot say which
        // part of the import spent them. Listing the medium, reading its index,
        // opening every file to see whether it is DICOM, parsing and indexing the
        // ones that are, and copying them into the database are five different
        // things, slow for five different reasons. They are timed apart.
        HorosMediaScanTiming *timing = [[[HorosMediaScanTiming alloc] initWithMedium: path.lastPathComponent] autorelease];
        
        thread.status = NSLocalizedString(@"Scanning directories...", nil);
        [timing begin: @"listing"];
        NSMutableArray* allpaths = [[[path stringsByAppendingPaths:[[NSFileManager.defaultManager enumeratorAtPath:path filesOnly:YES] allObjects]] mutableCopy] autorelease];
        [timing end: @"listing" count: allpaths.count noun: @"file"];
        NSMutableArray* pathsToScanAnyway = [NSMutableArray array];
        
        // first read the DICOMDIR file
        if ([NSUserDefaults.standardUserDefaults boolForKey:@"UseDICOMDIRFileCD"])
        {
            thread.status = NSLocalizedString(@"Looking for DICOMDIR...", nil);
            NSString* dicomdirPath = [[self class] _findDicomdirIn:allpaths];
            if (dicomdirPath)
            {
                NSLog(@"(scanAtPath): Scanning DICOMDIR at %@", dicomdirPath);
                thread.status = NSLocalizedString(@"Reading DICOMDIR...", nil);
                
                [timing begin: @"reading the index for"];
                @try {
                    dicomImages = [self scanDicomdirAt:dicomdirPath withPaths:allpaths pathsToScanAnyway:pathsToScanAnyway];
                }
                @catch (NSException *e) {
                    N2LogExceptionWithStackTrace( e);
                }
                [timing end: @"reading the index for" count: dicomImages.count noun: @"instance"];
            }
        }
        
        // What the index accounted for. A DICOMDIR is supposed to name every
        // instance on the medium; some name fewer. Trusting it and stopping there
        // left eight of twelve instances on a disc that was then ejected, with
        // nothing said - so the disc is read as well, and only the files the index
        // already brought in are skipped.
        NSMutableSet *indexedPaths = [NSMutableSet set];
        for( NSString *indexed in [dicomImages valueForKey: @"completePath"])
            if( [indexed isKindOfClass: NSString.class])
                [indexedPaths addObject: indexed];
        
        BOOL usedDicomdir = (dicomImages.count > 0);
        BOOL scanBeyondDicomdir = [NSUserDefaults.standardUserDefaults boolForKey:@"ScanDiskBeyondDICOMDIR"];
        
        BOOL doScan = (![NSUserDefaults.standardUserDefaults boolForKey:@"UseDICOMDIRFileCD"])
                   || (!dicomImages.count && [NSUserDefaults.standardUserDefaults boolForKey:@"ScanDiskIfDICOMDIRZero"])
                   || (usedDicomdir && scanBeyondDicomdir);
               
        NSUInteger namedByIndex = dicomImages.count;
        
        if (pathsToScanAnyway.count || doScan)
        {
            NSMutableArray* dicomFilePaths = [NSMutableArray arrayWithArray:pathsToScanAnyway];
            // Files the loop below actually opened. Saying it read everything on the
            // medium would be wrong on a disc whose index already named most of it,
            // and that is exactly the disc whose timing is in question.
            NSUInteger examined = 0;
            
            // And the ones it opened and would not take. This is where a damaged
            // medium loses its files: they never reach addFilesAtPaths:, because
            // isDICOMFile: has already said no. Measured on a disc carrying five
            // broken files, four were dropped here without a word.
            HorosImportRefusals *refusals = [[[HorosImportRefusals alloc] initWithConsidered: 0] autorelease];
            
            if (doScan)
            {
                thread.status = NSLocalizedString(@"Looking for DICOM files...", nil);
                thread.supportsCancel = YES;
                [timing begin: @"reading"];
                
                NSTimeInterval start = [NSDate timeIntervalSinceReferenceDate];
                for (NSInteger i = 0; i < allpaths.count; ++i)
                {
                    if( [NSDate timeIntervalSinceReferenceDate] - start > 0.5 || i == allpaths.count-1) {
                        thread.progress = 1.0*i/allpaths.count;
                        start = [NSDate timeIntervalSinceReferenceDate];
                    }
                    
                    NSString* path = [allpaths objectAtIndex:i];
                    
                    if ([dicomFilePaths containsObject:path])
                        continue;
                    
                    if ([indexedPaths containsObject:path])
                        continue;
                    
                    NSString *extension = path.pathExtension.lowercaseString;
                    
                    if ([extension isEqualToString: @"jpg"])
                        continue;
                    
                    if ([extension isEqualToString: @"tif"])
                        continue;
                    
                    if ([extension isEqualToString: @"jpeg"])
                        continue;
                    
                    if ([extension isEqualToString: @"tiff"])
                        continue;
                    
                    if ([extension isEqualToString: @"mp4"])
                        continue;
                    
                    if ([extension isEqualToString: @"mov"])
                        continue;
                    
                    if ([extension isEqualToString: @"avi"])
                        continue;
                    
                    if ([extension isEqualToString: @"html"])
                        continue;
                    
                    if ([extension isEqualToString: @"doc"])
                        continue;
                    
                    if ([extension isEqualToString: @"docx"])
                        continue;
                    
                    if ([extension isEqualToString: @"txt"])
                        continue;
                    
                    if ([extension isEqualToString: @"exe"])
                        continue;
                    
                    if ([path.lowercaseString rangeOfString:@"/weasis/"].location != NSNotFound) //Don't scan weasis
                        continue;
                    
                    if ([path.lowercaseString rangeOfString:@"/."].location != NSNotFound) //Don't scan hidden files
                        continue;
                    
                    if ([path.lowercaseString rangeOfString:@".app"].location != NSNotFound) //Don't scan the content of MacOS application: Horos Lite
                        continue;
                        
                    examined++;
                    
                    if ([DicomFile isDICOMFile:path])
                    {
                        // avoid DICOMDIR files
                        if ([path.lastPathComponent.lowercaseString rangeOfString:@"dicomdir"].length == 0)
                            [dicomFilePaths addObject:path];
                    }
                    else if ([path.pathExtension isEqualToString:@"zip"] || [path.pathExtension isEqualToString:@"osirixzip"])
                    {
                        [thread enterOperation];
                        thread.status = NSLocalizedString(@"Processing ZIP file...", @"");

                        // One archive must not be able to take the medium down with
                        // it. This asked tmpFilePathInDir: for a place to expand
                        // into and then made a directory there - and mkstemp creates
                        // the file, so confirmDirectoryAtPath: found a file in its
                        // way and raised. The exception left scanAtPath: through its
                        // @throw, so a disc carrying any ZIP imported nothing at all:
                        //   NSGenericException (in -[MountedDatabaseNodeIdentifier
                        //   volumeScanThread]): Cannot create directory: an existing
                        //   file occupies /private/var/folders/...
                        // A temporary directory is asked for now, and whatever else
                        // an archive manages to raise is caught here.
                        @try
                        {
                            NSString* tempPath = [NSFileManager.defaultManager tmpDirectoryPathInDir:self.tempDirPath];
                            
                            if ([BrowserController unzipFile:path withPassword:nil destination:tempPath] == NO)
                            { // needs password
                                [self performSelectorOnMainThread:@selector(_requestZipPassword:) withObject:[NSArray arrayWithObjects: path, tempPath, NULL] waitUntilDone:YES];
                            }
                            
                            [self scanAtPath:tempPath isVolume:NO];
                        }
                        @catch (NSException *e)
                        {
                            NSLog( @"(scanAtPath): %@ could not be expanded (%@); the rest of the medium is still read",
                                  path.lastPathComponent, e.reason);
                        }
                        [thread exitOperation];
                    }
                    else [refusals refuse: path];
                    
                    if (thread.isCancelled)
                        return NO;
                }
            }
            
            NSUInteger foundByScan = dicomFilePaths.count;
            [timing end: @"reading" count: examined noun: @"file"];
            
            refusals.considered = examined;
            if (refusals.count)
                NSLog( @"(scanAtPath): %@: %@", path.lastPathComponent, refusals.summary);
            
            [timing begin: @"indexing"];
            dicomImages = [dicomImages arrayByAddingObjectsFromArray: [self objectsWithIDs:[self addFilesAtPaths:dicomFilePaths postNotifications:NO dicomOnly:NO rereadExistingItems:NO generatedByOsiriX:NO importedFiles:YES returnArray:YES]]];
            [timing end: @"indexing" count: foundByScan noun: @"file"];
            
            // What the medium holds, what its index named, and what is actually
            // going to be taken off it. A disc is ejected after this, so the three
            // numbers are the only record of what was left behind.
            NSLog( @"(scanAtPath): %@: %lu file(s) on the medium, %lu named by the index, "
                  @"%lu more found by reading it, %lu instance(s) to take",
                  path.lastPathComponent, (unsigned long) allpaths.count,
                  (unsigned long) namedByIndex, (unsigned long) foundByScan,
                  (unsigned long) dicomImages.count);
        }
        
        if (!dicomImages.count)
            return NO;
        
        NSInteger mode = [NSUserDefaults.standardUserDefaults integerForKey:@"MOUNT"];
        
#ifdef OSIRIX_LIGHT
        mode = 0; //display the source
#endif
        
        if (mode == -1 || [[NSApp currentEvent] modifierFlags]&NSCommandKeyMask)
            [self performSelectorOnMainThread:@selector(_askUserDiscDataCopyOrBrowse:) withObject:[NSArray arrayWithObjects: path, [NSNumber numberWithInteger:dicomImages.count], [NSValue valueWithPointer:&mode], nil] waitUntilDone:YES];
        
        if (mode == 1)
        {
            // copy into database on mount
            
            NSMutableArray* paths = nil;
            
            @try {
                paths = [[[dicomImages valueForKey:@"completePath"] mutableCopy] autorelease];
            }
            @catch (NSException *e) {
                N2LogException( e);
            }
            
            [paths removeDuplicatedStrings];
            
            thread.supportsCancel = YES;
            [timing begin: @"copying"];
            
            NSThread* copyFilesThread = [NSThread performBlockInBackground:^{
                NSThread* cft = [NSThread currentThread];
                cft.name = NSLocalizedString(@"Importing images from media...", nil);
                
                [DicomDatabase.activeLocalDatabase.independentDatabase performSelector:@selector(copyFilesThread:)
                                                                            withObject:[NSDictionary dictionaryWithObjectsAndKeys:
                                                                                        paths, @"filesInput",
                                                                                        [NSNumber numberWithBool:YES], @"mountedVolume",
                                                                                        [NSNumber numberWithBool:YES], @"copyFiles",
                                                                                        [NSNumber numberWithBool: YES], @"addToAlbum",
                                                                                        [NSNumber numberWithBool: YES], @"selectStudy",
                                                                                        NULL]];
            }];
            
            float sleepInterval = 0.1f;
            
            // A thread that has not started yet is not a thread that is stuck. This
            // waited one second for isExecuting and then gave up - and what follows
            // the loop ejects the disc, so on a busy machine the medium could be
            // ejected before the copy had begun. It waits for the thread to start,
            // and then for it to finish, which is what "the copy is done" means:
            // progress reaching 1.0 is the copy's own report, not its end.
            NSTimeInterval waitedForStart = 0;
            
            while (copyFilesThread.isFinished == NO)
            {
                if (copyFilesThread.isExecuting == NO)
                {
                    waitedForStart += sleepInterval;
                    if (waitedForStart > 60.0)
                    {
                        NSLog( @"(scanAtPath): the copy did not start within a minute");
                        break;
                    }
                }
                
                if (thread.isCancelled && !copyFilesThread.isCancelled) {
                    [copyFilesThread cancel];
                }
                else
                {
                    if( [thread.status isEqualToString: copyFilesThread.status] == NO)
                        thread.status = copyFilesThread.status;
                    
                    if( [thread.name isEqualToString: copyFilesThread.name] == NO)
                        thread.name = copyFilesThread.name;
                    
                    if( thread.progress != copyFilesThread.progress)
                        thread.progress = copyFilesThread.progress;
                }
                
                [NSThread sleepForTimeInterval:sleepInterval];
            }
            
            thread.supportsCancel = NO; // why now?
            
            // A copy that was stopped part way did not copy the files it was given,
            // and saying "copying 1200 files" of it would be a claim. How many did
            // arrive is copyFilesThread's to report, and it does.
            if (copyFilesThread.isCancelled)
            {
                [timing end: @"copying"];
                NSLog( @"(scanAtPath): %@: the copy was stopped before it finished; what had "
                      @"already been copied was indexed", path.lastPathComponent);
            }
            else
                [timing end: @"copying" count: paths.count noun: @"file"];
            
            // Where the import spent its time, and what one instance of this medium
            // cost. Written before the eject, like the tally above it.
            NSLog( @"(scanAtPath): %@ (%@)", timing.summary, [timing perInstance: dicomImages.count]);
            
            // Only a copy that finished is a copy that can be ejected after.
            if (isVolume && [NSUserDefaults.standardUserDefaults boolForKey:@"CDDVDEjectAfterAutoCopy"]
                && ![copyFilesThread isCancelled] && copyFilesThread.isFinished)
            {
                NSLog(@"(scanAtPath): Ejecting...");
                thread.status = NSLocalizedString(@"Ejecting...", nil);
                thread.progress = -1;
                
                [DCMPix purgeCachedDictionaries]; // <- This is very important to 'unlink' all opened files, otherwise MacOS will display the famous 'The disk is in use and could not be ejected'
                
                int attempts = 0;
                BOOL success = NO;
                while( success == NO)
                {
                    success = [[NSWorkspace sharedWorkspace] unmountAndEjectDeviceAtPath:  path];
                    if( success == NO)
                    {
                        attempts++;
                        if( attempts < 5)
                        {
                            [NSThread sleepForTimeInterval: 1.0];
                        }
                        else success = YES;
                    }
                }
                
                return NO;
            }
        }
        else
        {
            // Nothing is copied when the medium is only being browsed, so the
            // report is written here instead.
            NSLog( @"(scanAtPath): %@ (%@)", timing.summary, [timing perInstance: dicomImages.count]);
        }
        
    //    if (![[[BrowserController currentBrowser] sourceForDatabase:self] isBeingEjected]) {
        if (!thread.isCancelled)
        {
            thread.status = NSLocalizedString(@"Generating series thumbnails...", nil);
            NSMutableArray* dicomSeries	= [NSMutableArray array];
            
            @try {
                for (DicomImage* di in dicomImages)
                    if (![dicomSeries containsObject:di.series])
                        [dicomSeries addObject:di.series];
            }
            @catch (NSException *e) {
                N2LogException( e);
            }
            
            for (NSInteger i = 0; i < dicomSeries.count; ++i)
                @try {
                    thread.progress = 1.0*i/dicomSeries.count;
                    [[dicomSeries objectAtIndex:i] thumbnail];
                } @catch (NSException* e) {
                    N2LogExceptionWithStackTrace(e);
                }
        }
        
        if (mode == 2) // ignore
            return NO;
    } @catch (NSException* e) {
        @throw;
    } @finally {
        [thread exitOperation];
    }
    
    return YES;
}

-(BOOL)scanAtPath:(NSString*)path {
	return [self scanAtPath:path isVolume:YES];
}

@end


@implementation _DicomDatabaseScanDcmElement

+(id)elementWithElement:(DcmElement*)element {
	return [[[[self class] alloc] initWithElement:element] autorelease];
}

-(id)initWithElement:(DcmElement*)element {
	if ((self = [super init])) {
		_element = element; // new DcmElement(element)
	}
	
	return self;
}

-(void)dealloc {
	//delete _element;
	[super dealloc];
}

-(DcmElement*)element {
	return _element;
}

-(NSString*)description {
	NSMutableString* str = [NSMutableString stringWithFormat:@"%@ = %@", self.name, self.stringValue];
/*	unsigned int vm = _element->getVM();
	if (vm > 1)
		for (unsigned int i = 0; i < vm; ++i) {
			OFString ofstr;
			if (_element->getOFString(ofstr,i).good())
				[str appendFormat:@"[%d][%s] ", i, ofstr.c_str()];
		}
	else {
		OFString ofstr;
		if (_element->getOFString(ofstr,0).good())
			[str appendFormat:@"%s", ofstr.c_str()];
	}
	*/
	return str;
}

-(NSString*)name {
	return [NSString stringWithUTF8String:DcmTag(_element->getTag()).getTagName()];
}

-(NSString*)stringValue {
	OFString ofstr;
	if (_element->getOFStringArray(ofstr).good())
		return [NSString stringWithCString:ofstr.c_str() encoding:NSISOLatin1StringEncoding];
	return nil;
}

-(NSString*)stringValueWithEncodings: (NSStringEncoding*) encodings{
	OFString ofstr;
	if (_element->getOFStringArray(ofstr).good())
    {
        return [DicomFile stringWithBytes: (char*) ofstr.c_str() encodings: encodings replaceBadCharacters: YES];
    }
	return nil;
}

-(NSInteger)integerValue {
	NSString* str = [self stringValue];
	return [str integerValue];
}

-(NSNumber*)integerNumberValue {
	return [NSNumber numberWithInteger:[self integerValue]];
}

@end



