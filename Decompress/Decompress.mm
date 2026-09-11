/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation, Êversion 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE. ÊSee the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos. ÊIf not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program: Ê OsiriX
 ÊCopyright (c) OsiriX Team
 ÊAll rights reserved.
 ÊDistributed under GNU - LGPL
 Ê
 ÊSee http://www.osirix-viewer.com/copyright.html for details.
 Ê Ê This software is distributed WITHOUT ANY WARRANTY; without even
 Ê Ê the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
 Ê Ê PURPOSE.
 ============================================================================*/

#import <Foundation/Foundation.h>
//#import "DCMObject.h"
//#import "DCM.h"
//#import "DCMTransferSyntax.h"
//#import "DCMPixelDataAttribute.h"
//#import "DCMAbstractSyntaxUID.h"
#import "DefaultsOsiriX.h"
#import "AppController.h"
//#import "QTKit/QTMovie.h"
#import "DCMPix.h"
#import <WebKit/WebKit.h>
#if defined(HOROS_SUPPORT_SWF)
# include <mingpp.h>
#endif
#import "N2Debug.h"
#import <Quartz/Quartz.h>

#undef verify
#include "HorosDCMTKCompatibility.h"
#include "HorosDICOMRepresentation.h"
#include <dcmtk/config/osconfig.h> /* make sure OS specific configuration is included first */
#include <dcmtk/dcmjpeg/djdecode.h>  /* for dcmjpeg decoders */
#include <dcmtk/dcmjpeg/djencode.h>  /* for dcmjpeg encoders */
#include <dcmtk/dcmdata/dcrledrg.h>  /* for DcmRLEDecoderRegistration */
#include <dcmtk/dcmdata/dcrleerg.h>  /* for DcmRLEEncoderRegistration */
#include <dcmtk/dcmjpeg/djrploss.h>
#include <dcmtk/dcmjpeg/djrplol.h>
#include <dcmtk/dcmdata/dcpixel.h>
#include <dcmtk/dcmdata/dcrlerp.h>
#include <dcmtk/dcmdata/dcdicdir.h>
#include <dcmtk/dcmdata/dcdatset.h>
#include <dcmtk/dcmdata/dcmetinf.h>
#include <dcmtk/dcmdata/dcfilefo.h>
#include "HorosDCMTKCompatibility.h"
#include <dcmtk/dcmdata/dcuid.h>
#include <dcmtk/dcmdata/dcdict.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmjpls/djdecode.h> //JPEG-LS
#include <dcmtk/dcmjpls/djencode.h> //JPEG-LS

#include "options.h"
#include "url.h"

extern "C"
{
    void exitOsiriX(void)
    {
        [NSException raise: @"JPEG error exception raised" format: @"JPEG error exception raised - See Console.app for error message"];
    }
}

enum DCM_CompressionQuality {DCMLosslessQuality = 0, DCMHighQuality, DCMMediumQuality, DCMLowQuality};

NSLock					*PapyrusLock = 0L;
NSThread				*mainThread = 0L;
BOOL					NEEDTOREBUILD = NO;
NSMutableDictionary		*DATABASECOLUMNS = 0L;
//short					Altivec = 0;
short					UseOpenJpeg = 1, Use_kdu_IfAvailable = 0;



/*
void myunlink(const char * path) {
    NSLog(@"Unlinking %s", path);
    unlink(path);
    NSLog(@"... Unlinked %s", path);
}
*/
#define myunlink unlink

// WHY THIS EXTERNAL APPLICATION FOR COMPRESS OR DECOMPRESSION?

// Because if a file is corrupted, it will not crash the OsiriX application, but only this small task.

// Always modify this function in sync with compressionForModality in Decompress.mm / BrowserController.m
int compressionForModality( NSArray *array, NSArray *arrayLow, int limit, NSString* mod, int* quality, int resolution)
{
	NSArray *s;
	if( resolution < limit)
		s = arrayLow;
	else
		s = array;
	
	if( [mod isEqualToString: @"SR"]) // No compression for DICOM SR
		return compression_none;
	
	for( NSDictionary *dict in s)
	{
		if( [mod rangeOfString: [dict valueForKey: @"modality"]].location != NSNotFound)
		{
			int compression = compression_none;
			if( [[dict valueForKey: @"compression"] intValue] == compression_sameAsDefault)
				dict = [s objectAtIndex: 0];
			
			compression = [[dict valueForKey: @"compression"] intValue];
			
			if( quality)
			{
				if( compression == compression_JPEG2000 || compression == compression_JPEGLS)
					*quality = [[dict valueForKey: @"quality"] intValue];
				else
					*quality = 0;
			}
			
			return compression;
		}
	}
	
	if( [s count] == 0)
		return compression_none;
	
	if( quality)
		*quality = [[[s objectAtIndex: 0] valueForKey: @"quality"] intValue];
	
	return [[[s objectAtIndex: 0] valueForKey: @"compression"] intValue];
}

#if defined(HOROS_SUPPORT_SWF)
void createSwfMovie(NSArray* inputFiles, NSString* path, float frameRate);
#endif

typedef NS_ENUM(NSInteger, HorosArchiveExtraction)
{
    HorosArchiveExtracted,           // the contents are in place and the archive is gone
    HorosArchiveNotExpanded,         // the archive itself is at fault; nothing came out of it
    HorosArchiveNotExpandedForNow,   // the destination is at fault - no room, no permission
    HorosArchiveExpandedNotCleared   // the contents are in place; the archive itself could not be removed
};

static HorosArchiveExtraction extractDICOMArchive(NSString *source, NSString *destination)
{
    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *staging = [[destination stringByDeletingLastPathComponent] stringByAppendingPathComponent:[@".horos-extract-" stringByAppendingString:[[NSUUID UUID] UUIDString]]];
    if (![manager createDirectoryAtPath:staging withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:NULL])
    {
        // Nothing here says the archive is bad: the place it would go is.
        NSLog(@"---- decompress: %@ could not be expanded: no working directory beside %@", [source lastPathComponent], [destination stringByDeletingLastPathComponent]);
        return HorosArchiveNotExpandedForNow;
    }
    @try
    {
        NSString *output = [staging stringByAppendingPathComponent:@"contents"];
        NSTask *task = [[[NSTask alloc] init] autorelease];
        [task setLaunchPath:@"/usr/bin/unzip"];
        [task setArguments:@[@"-o", @"-d", output, source]];
        [task setStandardInput:[NSFileHandle fileHandleWithNullDevice]];
        [task launch];
        while ([task isRunning]) [NSThread sleepForTimeInterval:0.1];
        int status = [task terminationStatus];
        // 1 means unzip finished and warned about something, so the contents are
        // there and throwing them away would be the loss this is meant to avoid.
        // 50 is "the disk is (or was) full": the archive is fine and the
        // destination is not, which is a different answer. Everything else means
        // the archive itself is at fault.
        if (status != 0 && status != 1)
        {
            NSLog(@"---- decompress: %@ could not be expanded: unzip exited with %d", [source lastPathComponent], status);
            return status == 50 ? HorosArchiveNotExpandedForNow : HorosArchiveNotExpanded;
        }
        // Swap an existing destination into staging; never pre-delete it.
        if (renamex_np([output fileSystemRepresentation], [destination fileSystemRepresentation], RENAME_SWAP) != 0)
        {
            if (errno != ENOENT || renamex_np([output fileSystemRepresentation], [destination fileSystemRepresentation], RENAME_EXCL) != 0)
            {
                NSLog(@"---- decompress: %@ was expanded but its contents could not be put in place: %s", [source lastPathComponent], strerror(errno));
                return HorosArchiveNotExpandedForNow;
            }
        }
        if ([[source stringByStandardizingPath] isEqualToString:[destination stringByStandardizingPath]]) return HorosArchiveExtracted;
        if ([manager removeItemAtPath:source error:NULL]) return HorosArchiveExtracted;
        NSLog(@"---- decompress: %@ was expanded but the archive itself could not be removed", [source lastPathComponent]);
        return HorosArchiveExpandedNotCleared;
    }
    @catch (NSException *exception)
    {
        NSLog(@"Archive extraction failed: %@", exception);
        return HorosArchiveNotExpanded;
    }
    @finally
    {
        [manager removeItemAtPath:staging error:NULL];
    }
}

// Nothing ever rescans the decompression folder, so an archive left in it is
// neither imported nor mentioned again. Hand it back to the folder it came from
// under a name that no longer reads as an archive - kept as it is, it would be
// sent straight back here on the next scan - and let the importer report and
// dispose of it the way it does with any other file it cannot read, which is
// also what makes DELETEFILELISTENER apply to it.
static BOOL surrenderUnreadableArchive(NSString *source, NSString *destination)
{
    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *handBack = [destination stringByAppendingPathExtension:@"horos-unexpanded"];
    for (int attempt = 1; [manager fileExistsAtPath:handBack] && attempt < 1000; attempt++)
        handBack = [[destination stringByAppendingFormat:@"-%d", attempt] stringByAppendingPathExtension:@"horos-unexpanded"];
    if (![manager moveItemAtPath:source toPath:handBack error:NULL])
    {
        NSLog(@"---- decompress: %@ could not be handed back for import; it stays in the decompression folder", [source lastPathComponent]);
        return NO;
    }
    NSLog(@"---- decompress: %@ handed back as %@ so the import folder can report it", [source lastPathComponent], [handBack lastPathComponent]);
    return YES;
}

// An archive that could not be expanded because of the destination - no room,
// no permission - is not a bad archive, and disposing of it the way an unreadable
// file is disposed of would destroy something the next attempt could read
// perfectly well. Put it back where it came from, under its own name, so the
// next scan tries again once the cause is gone.
static BOOL returnArchiveForRetry(NSString *source, NSString *destination)
{
    NSFileManager *manager = [NSFileManager defaultManager];
    if ([[source stringByStandardizingPath] isEqualToString:[destination stringByStandardizingPath]])
        return YES;
    [manager removeItemAtPath:destination error:NULL]; // a partial from a previous attempt
    if (![manager moveItemAtPath:source toPath:destination error:NULL])
    {
        NSLog(@"---- decompress: %@ could not be put back for another attempt; it stays in the decompression folder", [source lastPathComponent]);
        return NO;
    }
    NSLog(@"---- decompress: %@ put back for another attempt once there is room for it", [source lastPathComponent]);
    return YES;
}

// Copy beside the destination before committing, including moves across volumes.
static BOOL relocateDICOMFile(NSString *source, NSString *destination)
{
    if ([[source stringByStandardizingPath] isEqualToString:[destination stringByStandardizingPath]])
        return [[NSFileManager defaultManager] fileExistsAtPath:source];
    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *staging = [[destination stringByDeletingLastPathComponent] stringByAppendingPathComponent:[@".horos-move-" stringByAppendingString:[[NSUUID UUID] UUIDString]]];
    if (![manager createDirectoryAtPath:staging withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:NULL])
        return NO;
    @try
    {
        NSString *temporary = [staging stringByAppendingPathComponent:@"file"];
        if (![manager copyItemAtPath:source toPath:temporary error:NULL]) return NO;
        if (rename([temporary fileSystemRepresentation], [destination fileSystemRepresentation]) != 0) return NO;
        return [manager removeItemAtPath:source error:NULL];
    }
    @finally
    {
        [manager removeItemAtPath:staging error:NULL];
    }
}

// Save beside the final destination, then replace it without removing the source first.
static BOOL saveConvertedDICOM(DcmFileFormat& fileformat, E_TransferSyntax syntax,
                               NSString *source, NSString *destination)
{
    NSString *pattern = [[destination stringByDeletingLastPathComponent] stringByAppendingPathComponent:@".horos-codec-XXXXXX"];
    char *temporary = strdup([pattern fileSystemRepresentation]);
    if (!temporary) return NO;
    int descriptor = mkstemp(temporary);
    if (descriptor < 0) { free(temporary); return NO; }
    close(descriptor);
    BOOL succeeded = NO;
    try
    {
        OFCondition condition = fileformat.saveFile(temporary, syntax);
        if (condition.good() && rename(temporary, [destination fileSystemRepresentation]) == 0)
        {
            succeeded = YES;
            if (![source isEqualToString:destination] && unlink([source fileSystemRepresentation]) != 0)
                succeeded = NO;
        }
    }
    catch (...)
    {
        unlink(temporary);
        free(temporary);
        throw;
    }
    unlink(temporary);
    free(temporary);
    return succeeded;
}

int main(int argc, const char *argv[])
{
	[[NSAutoreleasePool alloc] init]; // yes, the Decompress tool will exit anyway
    
	// To avoid:
	// http://lists.apple.com/archives/quicktime-api/2007/Aug/msg00008.html
	// _NXCreateWindow: error setting window property (1002)
	// _NXTermWindow: error releasing window (1002)
	[NSApplication sharedApplication];
	

	//	argv[ 1] : in path
	//	argv[ 2] : what
	
	if( argv[ 1] && argv[ 2])
	{
		// register global JPEG decompression codecs
		// JPEG decoders are registered below, after reading the color policy.
        DJLSDecoderRegistration::registerCodecs();
        
		// register global JPEG compression codecs
		DJEncoderRegistration::registerCodecs(
			ECC_lossyRGB,
			EUC_never,
			OFFalse,
			0,
			0,
			0,
			OFTrue,
			ESS_444,
			OFFalse,
			OFFalse,
			0,
			0,
			0.0,
			0.0,
			0,
			0,
			0,
			0,
			OFTrue,
			OFTrue,
			OFFalse,
			OFFalse,
			OFTrue);
        
        DJLSEncoderRegistration::registerCodecs();
        
		// register RLE compression codec
		DcmRLEEncoderRegistration::registerCodecs();

		// register RLE decompression codec
		DcmRLEDecoderRegistration::registerCodecs();
		
		NSString	*path = [NSString stringWithUTF8String:argv[1]];
		NSString	*what = [NSString stringWithUTF8String:argv[2]];
		NSInteger fileListFirstItemIndex = 3;
		
		NSMutableDictionary* dict = [DefaultsOsiriX getDefaults];
		[dict addEntriesFromDictionary: [[NSUserDefaults standardUserDefaults] persistentDomainForName:@BUNDLE_IDENTIFIER]];
		
		if ([what isEqualToString:@"SettingsPlist"])
		{
			@try
			{
				[dict addEntriesFromDictionary:[NSMutableDictionary dictionaryWithContentsOfFile:[NSString stringWithUTF8String:argv[fileListFirstItemIndex]]]];
				what = [NSString stringWithUTF8String:argv[4]];
				fileListFirstItemIndex += 2;
			}
			@catch (NSException* e)
			{ // ignore evtl failures
				NSLog(@"Decompress failed reading settings plist at %s: %@", argv[fileListFirstItemIndex], e);
			}
		}
		
		DJDecoderRegistration::registerCodecs(
            [[dict objectForKey:@"UseJPEGColorSpace"] boolValue] ? EDC_guess : EDC_photometricInterpretation, EUC_never);
		
//		BOOL useDCMTKForJP2K = [[dict objectForKey:@"useDCMTKForJP2K"] intValue];
		
#pragma mark compress
		if( [what isEqualToString:@"compress"])
		{
            BOOL conversionSucceeded = YES;
			UseOpenJpeg = [[dict objectForKey:@"UseOpenJpegForJPEG2000"] intValue];
			Use_kdu_IfAvailable = [[dict objectForKey:@"UseKDUForJPEG2000"] intValue];
			
			NSArray *compressionSettings = [dict valueForKey: @"CompressionSettings"];
			NSArray *compressionSettingsLowRes = [dict valueForKey: @"CompressionSettingsLowRes"];
			
			int limit = [[dict objectForKey: @"CompressionResolutionLimit"] intValue];
			
			NSString *destDirec;
			if( [path isEqualToString: @"sameAsDestination"])
				destDirec = nil;
			else
				destDirec = path;
			
			for (int i = (int)fileListFirstItemIndex; i < argc; i++)
			{
				NSString *curFile = [NSString stringWithUTF8String:argv[ i]];
				OFBool status = YES;
				NSString *curFileDest;
				
				if( destDirec)
					curFileDest = [destDirec stringByAppendingPathComponent: [curFile lastPathComponent]];
				else
					curFileDest = [curFile stringByAppendingString: @" temp"];
				
				if( [[curFile pathExtension] isEqualToString: @"zip"] ||
                [[curFile pathExtension] isEqualToString: @"osirixzip"])
                {
                    HorosArchiveExtraction outcome = extractDICOMArchive(curFile, curFileDest);
                    if (outcome != HorosArchiveExtracted)
                    {
                        conversionSucceeded = NO;
                        if (outcome == HorosArchiveNotExpanded)
                            surrenderUnreadableArchive(curFile, curFileDest);
                        else if (outcome == HorosArchiveNotExpandedForNow)
                            returnArchiveForRetry(curFile, curFileDest);
                    }
				}
				else
				{
					DcmFileFormat fileformat;
					OFCondition cond = fileformat.loadFile( [curFile UTF8String]);
                    if (!cond.good())
                        conversionSucceeded = NO;
					// if we can't read it stop
					if( cond.good())
					{
						DcmDataset *dataset = fileformat.getDataset();
//						DcmItem *metaInfo = fileformat.getMetaInfo();
						DcmXfer original_xfer(dataset->getOriginalXfer());
						
						const char *string = NULL;
						
//						NSString *sopClassUID = nil;
//						if (dataset->findAndGetString(DCM_SOPClassUID, string, OFFalse).good() && string != NULL)
//							sopClassUID = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
						
                        
						{
                            delete dataset->remove( DcmTagKey( 0x0009, 0x1110)); // "GEIIS" The problematic private group, containing a *always* JPEG compressed PixelData
                            
							NSString *modality;
							if (dataset->findAndGetString(DCM_Modality, string, OFFalse).good() && string != NULL)
								modality = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
							else
								modality = @"OT";
							
							int resolution = 0;
							unsigned short rows = 0;
							if (dataset->findAndGetUint16( DCM_Rows, rows, OFFalse).good())
							{
								if( resolution == 0 || resolution > rows)
									resolution = rows;
							}
							unsigned short columns = 0;
							if (dataset->findAndGetUint16( DCM_Columns, columns, OFFalse).good())
							{
								if( resolution == 0 || resolution > columns)
									resolution = columns;
							}
							
							int quality, compression = compressionForModality( compressionSettings, compressionSettingsLowRes, limit, modality, &quality, resolution);
							
                            BOOL alreadyCompressed = NO;
                            
                            if (original_xfer.isEncapsulated())
                            {
                                switch( compression)
                                {
                                    case compression_JPEGLS:
                                        if( original_xfer.getXfer() == EXS_JPEGLSLossless ||
                                           original_xfer.getXfer() == EXS_JPEGLSLossy)
                                            alreadyCompressed = YES;
                                    break;
                                    
                                    case compression_JPEG2000:
                                        if( original_xfer.getXfer() == EXS_JPEG2000 ||
                                           original_xfer.getXfer() == EXS_JPEG2000LosslessOnly)
                                            alreadyCompressed = YES;
                                    break;
                                    
                                    case compression_JPEG:
                                        if( original_xfer.getXfer() == EXS_JPEGProcess14SV1TransferSyntax)
                                            alreadyCompressed = YES;
                                    break;
                                }
                            }
                            
                            if( alreadyCompressed == NO)
                            {
//                                if( useDCMTKForJP2K == NO && compression == compression_JPEG2000)
//                                {
//                                    [DCMPixelDataAttribute setUse_kdu_IfAvailable: [[dict objectForKey:@"UseKDUForJPEG2000"] intValue]];
//                                    DCMObject *dcmObject = [[DCMObject alloc] initWithContentsOfFile: curFile decodingPixelData: NO];
//                                    
//                                    BOOL succeed = NO;
//                                    
//                                    // See - (BOOL) needToCompressFile: (NSString*) path in BrowserControllerDCMTKCategory for these exceptions
//                                    if( [DCMAbstractSyntaxUID isImageStorage: [dcmObject attributeValueWithName:@"SOPClassUID"]] == YES && [[dcmObject attributeValueWithName:@"SOPClassUID"] isEqualToString:[DCMAbstractSyntaxUID pdfStorageClassUID]] == NO && [DCMAbstractSyntaxUID isStructuredReport: [dcmObject attributeValueWithName:@"SOPClassUID"]] == NO)
//                                    {
//                                        @try
//                                        {
//                                            DCMTransferSyntax *tsx = [DCMTransferSyntax JPEG2000LossyTransferSyntax];
//                                            succeed = [dcmObject writeToFile: curFileDest withTransferSyntax: tsx quality: quality AET:@"Horos" atomically:YES];
//                                        }
//                                        @catch (NSException *e)
//                                        {
//                                            NSLog( @"dcmObject writeToFile failed: %@", e);
//                                        }
//                                    }
//                                    else
//                                    {
//                                        succeed = [[NSData dataWithContentsOfFile: curFile] writeToFile: curFileDest atomically: YES];
//                                    }
//                                    
//                                    [dcmObject release];
//                                    
//                                    if( succeed)
//                                    {
//                                        myunlink([curFile fileSystemRepresentation]);
//                                        if( destDirec == nil)
//                                            [[NSFileManager defaultManager] moveItemAtPath: curFileDest toPath: curFile error: nil];
//                                    }
//                                    else
//                                    {
//                                        myunlink([curFileDest fileSystemRepresentation]);
//                                        
//                                        if ([[dict objectForKey: @"DecompressMoveIfFail"] boolValue])
//                                        {
//                                            [[NSFileManager defaultManager] moveItemAtPath: curFile toPath: curFileDest error: nil];
//                                        }
//                                        else if( destDirec)
//                                        {
//                                            myunlink([curFile fileSystemRepresentation]);
//                                            NSLog( @"failed to compress file: %@, the file is deleted", curFile);
//                                        }
//                                        else
//                                            NSLog( @"failed to compress file: %@", curFile);
//                                    }
//                                }
//                                else
                                    if( compression == compression_JPEG ||
                                       compression == compression_JPEG2000 ||
                                       compression == compression_JPEGLS)
                                {
                                    DcmRepresentationParameter *params = nil;
                                    E_TransferSyntax tSyntax;
                                    DJ_RPLossless losslessParams(6,0);
                                    DJ_RPLossy JP2KParams( quality);
                                    DJ_RPLossy JP2KParamsLossLess( DCMLosslessQuality);
                                    
                                    if( compression == compression_JPEG)
                                    {
                                        params = &losslessParams;
                                        tSyntax = EXS_JPEGProcess14SV1TransferSyntax;
                                    }
                                    else if( compression == compression_JPEGLS)
                                    {
                                        if( quality == DCMLosslessQuality)
                                        {
                                            params = &JP2KParamsLossLess;
                                            tSyntax = EXS_JPEGLSLossless;
                                        }
                                        else
                                        {
                                            params = &JP2KParams;
                                            tSyntax = EXS_JPEGLSLossy;
                                        }
                                    }
                                    else if( compression == compression_JPEG2000)
                                    {
                                        if( quality == DCMLosslessQuality)
                                        {
                                            params = &JP2KParamsLossLess;
                                            tSyntax = EXS_JPEG2000LosslessOnly;
                                        }
                                        else
                                        {
                                            params = &JP2KParams;
                                            tSyntax = EXS_JPEG2000;
                                        }
                                    }
                                    else
                                    {
                                        params = &JP2KParamsLossLess;
                                        tSyntax = EXS_JPEG2000LosslessOnly;
                                        
                                        NSLog( @" ****** UNKNOW compression Decompress.mm");
                                    }
                                    
                                    // this causes the lossless JPEG version of the dataset to be created
                                    DcmXfer oxferSyn( tSyntax);
                                    HorosChooseDICOMRepresentation(fileformat, tSyntax, params, quality);
                                    
                                    // check if everything went well
                                    if (dataset->canWriteXfer(tSyntax))
                                    {
                                        // force the meta-header UIDs to be re-generated when storing the file 
                                        // since the UIDs in the data set may have changed 
                                        
                                        //only need to do this for lossy
                                        //delete metaInfo->remove(DCM_MediaStorageSOPClassUID);
                                        //delete metaInfo->remove(DCM_MediaStorageSOPInstanceUID);
                                        
                                        // store in lossless JPEG format
                                        fileformat.loadAllDataIntoMemory();
                                        
                                        status = saveConvertedDICOM(fileformat, tSyntax, curFile, destDirec ? curFileDest : curFile);
                                        if (!status) conversionSucceeded = NO;
                                    }
                                    else conversionSucceeded = NO;
                                }
                                else
                                {
                                    if( destDirec)
                                    {
                                        if (!relocateDICOMFile(curFile, curFileDest))
                                            conversionSucceeded = NO;
                                    }
                                }
                            }
                            else
                            {
                                if( destDirec)
                                {
                                    if (!relocateDICOMFile(curFile, curFileDest))
                                        conversionSucceeded = NO;
                                }
                            }
						}
					}
					else if ([[dict objectForKey: @"DecompressMoveIfFail"] boolValue])
                    {
                        if (!relocateDICOMFile(curFile, curFileDest))
                            conversionSucceeded = NO;
                    }
                    else NSLog( @"compress : cannot read file: %@", curFile);
				}
			}
            return conversionSucceeded ? EXIT_SUCCESS : EXIT_FAILURE;
		}
		
        if( [what isEqualToString: @"testDICOMDIR"])
        {
            NSLog( @"-- Testing DICOMDIR: %@", [NSString stringWithUTF8String: argv[ 1]]);
            
            DcmDicomDir dcmdir( [[NSString stringWithUTF8String: argv[ 1]] fileSystemRepresentation]);
            DcmDirectoryRecord& record = dcmdir.getRootRecord();
            
            for (unsigned int i = 0; i < record.card();)
            {
                DcmElement* element = record.getElement(i);
                OFString ofstr;
                element->getOFStringArray(ofstr).good();
                
                i += 10;
            }
            
            NSLog( @"-- Testing DICOMDIR done");
                  
//            *(long*) 0x00 = 0xDEADBEEF;
        }
        
# pragma mark testFiles
		if( [what isEqualToString: @"testFiles"])
		{			
			//[DCMPixelDataAttribute setUse_kdu_IfAvailable: [[dict objectForKey:@"UseKDUForJPEG2000"] intValue]];
			
			UseOpenJpeg = [[dict objectForKey:@"UseOpenJpegForJPEG2000"] intValue];
			Use_kdu_IfAvailable = [[dict objectForKey:@"UseKDUForJPEG2000"] intValue];
			
			for(int i = (int)fileListFirstItemIndex; i < argc ; i++)
			{
				NSString *curFile = [NSString stringWithUTF8String: argv[ i]];
				
				// Simply try to load and generate the image... will it crash?
				
				DCMPix *dcmPix = [[DCMPix alloc] initWithPath: curFile :0 :1 :nil :0 :0 isBonjour: NO imageObj: nil];
				
				if( dcmPix)
				{
					[dcmPix CheckLoad];
					
					//*(long*)0 = 0xDEADBEEF; // Dead Beef ? WTF ??? Will it unlock the matrix....
					
					[dcmPix release];
				}
				else NSLog( @"dcmPix == nil");
			}
		}
		
# pragma mark decompressList
		if( [what isEqualToString:@"decompressList"])
		{
            BOOL conversionSucceeded = YES;
			NSString *destDirec;
			if( [path isEqualToString: @"sameAsDestination"])
				destDirec = nil;
			else
				destDirec = path;
			
			UseOpenJpeg = [[dict objectForKey:@"UseOpenJpegForJPEG2000"] intValue];
			Use_kdu_IfAvailable = [[dict objectForKey:@"UseKDUForJPEG2000"] intValue];
			
			for(int i = (int)fileListFirstItemIndex; i < argc ; i++)
			{
				NSString *curFile = [NSString stringWithUTF8String:argv[ i]];
				NSString *curFileDest;
				
				if( destDirec)
					curFileDest = [destDirec stringByAppendingPathComponent: [curFile lastPathComponent]];
				else
					curFileDest = [curFile stringByAppendingString: @" temp"];
				
				OFBool status = NO;
				
				if( [[curFile pathExtension] isEqualToString: @"zip"] || [[curFile pathExtension] isEqualToString: @"osirixzip"])
				{
                    HorosArchiveExtraction outcome = extractDICOMArchive(curFile, curFileDest);
                    if (outcome != HorosArchiveExtracted)
                    {
                        conversionSucceeded = NO;
                        if (outcome == HorosArchiveNotExpanded)
                            surrenderUnreadableArchive(curFile, curFileDest);
                        else if (outcome == HorosArchiveNotExpandedForNow)
                            returnArchiveForRetry(curFile, curFileDest);
                    }
				}
                else
                {
                    DcmFileFormat fileformat;
                    OFCondition condition = fileformat.loadFile([curFile fileSystemRepresentation]);
                    if (condition.good())
                    {
                        DcmDataset *dataset = fileformat.getDataset();
                        // GEIIS may contain JPEG PixelData in this private group.
                        delete dataset->remove(DcmTagKey(0x0009, 0x1110));
                        HorosChooseDICOMRepresentation(fileformat, EXS_LittleEndianExplicit);
                        if (dataset->canWriteXfer(EXS_LittleEndianExplicit))
                        {
                            fileformat.loadAllDataIntoMemory();
                            status = saveConvertedDICOM(fileformat, EXS_LittleEndianExplicit, curFile, destDirec ? curFileDest : curFile);
                        }
                    }
                    if (!status) conversionSucceeded = NO;
                }
            }
            return conversionSucceeded ? EXIT_SUCCESS : EXIT_FAILURE;
		}
		
# pragma mark writeMovie
		if( [what isEqualToString: @"writeMovie"])
		{
#if !defined(HOROS_SUPPORT_SWF)
            NSLog( @"******** writeMovie Decompress - not available");
#else
			if( ![path hasSuffix:@".swf"])
			{
                NSLog( @"******** writeMovie Decompress - not available");
			}
			else
			{ // SWF!!
				NSString* inputDir = [NSString stringWithUTF8String:argv[fileListFirstItemIndex++]];
				NSArray* inputFiles = [inputDir stringsByAppendingPaths:[[NSFileManager defaultManager] contentsOfDirectoryAtPath:inputDir error:NULL]];
                
                float frameRate = 0;
                
                if( fileListFirstItemIndex < argc)
                    frameRate = [[NSString stringWithUTF8String: argv[ fileListFirstItemIndex]] floatValue];
                
				createSwfMovie(inputFiles, path, frameRate);
                
                [[NSFileManager defaultManager] removeItemAtPath: inputDir error: nil];
			}
#endif
		}
				
# pragma mark pdfFromURL
		if( [what isEqualToString: @"pdfFromURL"])
		{
			@try
			{
				WebView *webView = [[[WebView alloc] initWithFrame: NSMakeRect(0,0,1,1) frameName: @"myFrame" groupName: @"myGroup"] autorelease];
				NSWindow *w = [[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,1,1) styleMask:NSBorderlessWindowMask backing:NSBackingStoreNonretained defer:NO] autorelease];
				[w setContentView:webView];
				
				WebPreferences *webPrefs = [WebPreferences standardPreferences];
				
				[webPrefs setLoadsImagesAutomatically: YES];
				[webPrefs setAllowsAnimatedImages: YES];
				[webPrefs setAllowsAnimatedImageLooping: NO];
				[webPrefs setJavaEnabled: NO];
				[webPrefs setPlugInsEnabled: NO];
				[webPrefs setJavaScriptEnabled: YES];
				[webPrefs setJavaScriptCanOpenWindowsAutomatically: NO];
				[webPrefs setShouldPrintBackgrounds: YES];
				
				[webView setApplicationNameForUserAgent: @"OsiriX"];
				[webView setPreferences: webPrefs];
				[webView setMaintainsBackForwardList: NO];
				
				NSURL *theURL = [NSURL fileURLWithPath: path];
				if( theURL)
				{
					NSURLRequest *request = [NSURLRequest requestWithURL: theURL];
					
					[[webView mainFrame] loadRequest: request];
					
					NSTimeInterval timeout = [NSDate timeIntervalSinceReferenceDate] + 10;
					
					while( [[webView mainFrame] dataSource] == nil || [[[webView mainFrame] dataSource] isLoading] == YES || [[[webView mainFrame] provisionalDataSource] isLoading] == YES)
					{
						[[NSRunLoop currentRunLoop] runUntilDate: [NSDate dateWithTimeIntervalSinceNow: 0.1]];
						
						if( [NSDate timeIntervalSinceReferenceDate] > timeout)
							break;
					}
					
					NSPrintInfo *sharedInfo = [NSPrintInfo sharedPrintInfo];
					NSMutableDictionary *sharedDict = [sharedInfo dictionary];
					NSMutableDictionary *printInfoDict = [NSMutableDictionary dictionaryWithDictionary: sharedDict];
					
					[printInfoDict setObject: NSPrintSaveJob forKey: NSPrintJobDisposition];
					
					[[NSFileManager defaultManager] removeItemAtPath:[path stringByAppendingPathExtension: @"pdf"] error:NULL];
					[printInfoDict setObject:[NSURL fileURLWithPath:[path stringByAppendingPathExtension:@"pdf"]] forKey: NSPrintJobSavingURL];
					
					NSPrintInfo *printInfo = [[NSPrintInfo alloc] initWithDictionary: printInfoDict];
					
                    [printInfo setBottomMargin: 30];
                    [printInfo setTopMargin: 30];
                    [printInfo setLeftMargin: 24];
                    [printInfo setRightMargin: 24];
                    
					[printInfo setHorizontalPagination: NSAutoPagination];
					[printInfo setVerticalPagination: NSAutoPagination];
					[printInfo setVerticallyCentered:NO];
					
					NSView *viewToPrint = [[[webView mainFrame] frameView] documentView];
					NSPrintOperation *printOp = [NSPrintOperation printOperationWithView: viewToPrint printInfo: printInfo];
					[printOp setShowsPrintPanel: NO];
					[printOp setShowsProgressPanel: NO];
					[printOp runOperation];
                    
                    //jf remove empty last PDF page
                    @try
                    {
                        NSURL *pdfURL = [theURL URLByAppendingPathExtension:@"pdf"];
                        PDFDocument *pdf = [[[PDFDocument alloc]initWithURL:pdfURL]autorelease];
                        NSUInteger pdfPageCount = [pdf pageCount];
                        if (pdfPageCount > 1)
                        {
                            NSUInteger pdfLastPageIndex = pdfPageCount - 1;
                            PDFPage *pdfLastPage = [pdf pageAtIndex:pdfLastPageIndex];
                            NSUInteger pdfLastPageCharCount = [pdfLastPage numberOfCharacters];
                            if (pdfLastPageCharCount < 2)
                            {
                                [pdf removePageAtIndex:pdfLastPageIndex];
                                [pdf writeToURL:pdfURL];
                            }
                        }
                    }
                    @catch ( NSException *e) {
                        N2LogException( e);
                    }
				}
			}
			@catch (NSException * e)
			{
                N2LogExceptionWithStackTrace(e);
			}
			return 0;
		}
		
	    // deregister JPEG codecs
		//DJDecoderRegistration::cleanup();	We dont care: we are just a small app : our memory will be killed by the system. Dont loose time here !
		//DJEncoderRegistration::cleanup();	We dont care: we are just a small app : our memory will be killed by the system. Dont loose time here !

		// deregister RLE codecs
		//DcmRLEDecoderRegistration::cleanup();	We dont care: we are just a small app : our memory will be killed by the system. Dont loose time here !
		//DcmRLEEncoderRegistration::cleanup();	We dont care: we are just a small app : our memory will be killed by the system. Dont loose time here !
	}
	
//	[pool release]; We dont care: we are just a small app : our memory will be killed by the system. Dont loose time here !
	
	return 0;
}

#if defined(HOROS_SUPPORT_SWF)
void createSwfMovie(NSArray* inputFiles, NSString* path, float frameRate) {
	if (path)
		[[NSFileManager defaultManager] removeItemAtPath:path error:NULL];
	
	Ming_init();
	Ming_setSWFCompression(9); // 9 = maximum compression
	SWFMovie* swf = new SWFMovie(7);
	swf->setBackground(0x88, 0x88, 0x88);
    
    if( frameRate < 1)
        frameRate = 10;
	swf->setRate(frameRate);
	
	BOOL sizeSet = NO;
	NSSize swfSize;
	
	NSString* as = [NSString stringWithContentsOfFile:[[NSBundle mainBundle] pathForResource:@"SWFInit" ofType:@"as"] encoding:NSUTF8StringEncoding error:NULL];
	//NSLog(@"AS:\n%@", as);
	SWFAction* action = new SWFAction([as cStringUsingEncoding:NSISOLatin1StringEncoding]);
	//		int len, res = action->compile(7, &len);
	//	NSLog(@"compile ret:%d len:%d", res, len);
	swf->add(action);
	
	const CGFloat ControllerHeight = 14, PlayPauseWidth = 0;
	const CGFloat ControllerPadTop = 1, ControllerPadBottom = 1;
	const CGFloat MarkHeight = ControllerHeight-ControllerPadTop-ControllerPadBottom, MarkWidth = MarkHeight-2;
	const CGFloat ControllerPadLeft = MarkWidth/2, ControllerPadRight = MarkWidth/2+PlayPauseWidth;
	NSRect ControllerRect;
	NSRect ControllerNavigationRect;
	const CGFloat ControllerBarThickness = 2, ControllerBarPadLeft = -ControllerBarThickness/2, ControllerBarPadRight = -ControllerBarThickness/2;
	
	// movie controller left of mark
	SWFShape* squareS = new SWFShape();
	squareS->setRightFillStyle(SWFFillStyle::SolidFillStyle(0,0,0,0));
	squareS->movePenTo(0,0);
	squareS->drawLine(1,0);
	squareS->drawLine(0,MarkHeight);
	squareS->drawLine(-1,0);
	squareS->drawLine(0,-MarkHeight);
	SWFButton* leftBarB = new SWFButton();
	leftBarB->addShape(squareS, SWFBUTTON_HIT|SWFBUTTON_UP|SWFBUTTON_DOWN|SWFBUTTON_OVER);
	leftBarB->addAction(new SWFAction("leftBarMouseDown();"), SWFBUTTON_MOUSEDOWN);
	SWFDisplayItem* leftBarDI = swf->add(leftBarB);
	leftBarDI->setName("leftBarDI");
	// movie controller right of mark
	squareS = new SWFShape();
	squareS->setRightFillStyle(SWFFillStyle::SolidFillStyle(0,0,0,0));
	squareS->movePenTo(0,0);
	squareS->drawLine(-1,0);
	squareS->drawLine(0,MarkHeight);
	squareS->drawLine(1,0);
	squareS->drawLine(0,-MarkHeight);
	SWFButton* rightBarB = new SWFButton();
	rightBarB->addShape(squareS, SWFBUTTON_HIT|SWFBUTTON_UP|SWFBUTTON_DOWN|SWFBUTTON_OVER);
	rightBarB->addAction(new SWFAction("rightBarMouseDown();"), SWFBUTTON_MOUSEDOWN);
	SWFDisplayItem* rightBarDI = swf->add(rightBarB);
	rightBarDI->setName("rightBarDI");
	
	// movie controller mark
	SWFShape* markS = new SWFShape();
	markS->setRightFillStyle(SWFFillStyle::SolidFillStyle(64,64,64,191));
	markS->movePenTo(-MarkWidth/2, -MarkHeight/2);
	markS->drawLine(MarkWidth,0);
	markS->drawLine(0,MarkHeight);
	markS->drawLine(-MarkWidth,0);
	markS->drawLine(0,-MarkHeight);
	SWFButton* markB = new SWFButton();
	markB->addShape(markS, SWFBUTTON_HIT|SWFBUTTON_UP|SWFBUTTON_DOWN|SWFBUTTON_OVER);
	markB->addAction(new SWFAction("markMouseDown();"), SWFBUTTON_MOUSEDOWN);
	SWFDisplayItem* markDI = swf->add(markB);
	markDI->setName("markDI");
	
	SWFBitmap* bitmap[inputFiles.count];
	SWFDisplayItem* displayItem[inputFiles.count];
//#pragma omp parallel for default(private)				
	for (int i = 0; i < inputFiles.count; ++i) {
		NSString* imgPath = [inputFiles objectAtIndex:i];
//		NSLog(@"%@", imgPath);
		
		bitmap[i] = new SWFBitmap(imgPath.UTF8String, NULL);
		if (!bitmap[i])
			NSLog(@"SWF creation FAILED: could not read %@", imgPath);
		NSSize bitmapSize = NSMakeSize(bitmap[i]->getWidth(), bitmap[i]->getHeight());
		
		if (!sizeSet) {
			swfSize = NSMakeSize(bitmapSize.width, bitmapSize.height+ControllerHeight); // 15 is the controller height
			swf->setDimension(swfSize.width, swfSize.height);
			sizeSet = YES;
		}
		
		SWFShape* shape = new SWFShape();
		shape->setRightFillStyle(SWFFillStyle::BitmapFillStyle(bitmap[i], SWFFILL_CLIPPED_BITMAP));
		shape->drawLine(bitmapSize.width,0);
		shape->drawLine(0,bitmapSize.height);
		shape->drawLine(-bitmapSize.width,0);
		shape->drawLine(0,-bitmapSize.height);
		
		displayItem[i] = swf->add(shape);
		displayItem[i]->moveTo(0,0);
		displayItem[i]->scaleTo(0);
	}
	
	// controller
	
	ControllerRect = NSMakeRect(0, swfSize.height-ControllerHeight, swfSize.width, ControllerHeight);
	ControllerNavigationRect = NSMakeRect(ControllerRect.origin.x+ControllerPadLeft, ControllerRect.origin.y+ControllerPadTop, ControllerRect.size.width-ControllerPadLeft-ControllerPadRight, ControllerRect.size.height-ControllerPadTop-ControllerPadBottom);
	swf->add(new SWFAction([[NSString stringWithFormat:@"_root.ControllerOriginX = %f; _root.ControllerWidth = %f;", ControllerNavigationRect.origin.x, ControllerNavigationRect.size.width] cStringUsingEncoding:NSISOLatin1StringEncoding]));
	NSRect ControllerBarRect = NSMakeRect(ControllerNavigationRect.origin.x+ControllerBarPadLeft, (ControllerNavigationRect.origin.y*2+ControllerNavigationRect.size.height-ControllerBarThickness)/2, ControllerNavigationRect.size.width-ControllerBarPadLeft-ControllerBarPadRight, ControllerBarThickness);
	
	SWFShape* controllerBar = new SWFShape();
	controllerBar->setRightFillStyle(SWFFillStyle::SolidFillStyle(191,191,191,127));
	controllerBar->movePenTo(0, 0);
	controllerBar->drawLine(1,0);
	controllerBar->drawLine(0,1);
	controllerBar->drawLine(-1,0);
	controllerBar->drawLine(0,-1);
	controllerBar->setRightFillStyle(SWFFillStyle::SolidFillStyle(191,191,191,127));
	SWFDisplayItem* controllerBarDisplayItem = swf->add(controllerBar);
	controllerBarDisplayItem->moveTo(ControllerBarRect.origin.x, ControllerBarRect.origin.y);
	controllerBarDisplayItem->scaleTo(ControllerBarRect.size.width, ControllerBarRect.size.height);	

    // Click in image to play/stop
    SWFShape* button = new SWFShape();
    button->setRightFillStyle(SWFFillStyle::SolidFillStyle(0,50,0,0));
    button->drawLine(swfSize.width,0);
    button->drawLine(0,swfSize.height-ControllerHeight);
    button->drawLine(-swfSize.width,0);
    button->drawLine(0,-swfSize.height-ControllerHeight);
    
    SWFButton* playStop = new SWFButton();
	playStop->addShape( button, SWFBUTTON_HIT|SWFBUTTON_UP|SWFBUTTON_DOWN|SWFBUTTON_OVER);
	playStop->addAction(new SWFAction("if( playing == 1) playing = 0; else playing = 1; if( playing) play(); else stop();"), SWFBUTTON_MOUSEDOWN);
    SWFDisplayItem* playItemDI = swf->add(playStop);
    playItemDI->setName("playItemDI");
    playItemDI->moveTo(0, 0);
    
	// animation
	
	for (int i = 0; i < inputFiles.count; ++i) {
		markDI->moveTo(ControllerNavigationRect.origin.x+ControllerNavigationRect.size.width/((long)inputFiles.count-1)*i, ControllerNavigationRect.origin.y+ControllerNavigationRect.size.height/2);
		leftBarDI->scaleTo(ControllerNavigationRect.size.width/((long)inputFiles.count-1)*i, 1);
		leftBarDI->moveTo(ControllerNavigationRect.origin.x, ControllerNavigationRect.origin.y);
		rightBarDI->scaleTo(ControllerNavigationRect.size.width/((long)inputFiles.count-1)*((long)inputFiles.count-1-i),1);
		rightBarDI->moveTo(ControllerNavigationRect.origin.x+ControllerNavigationRect.size.width, ControllerNavigationRect.origin.y);
		
		for (int d = MAX(0,i-1); d < MIN(inputFiles.count,i+1); ++d)
			if (d == i)
				displayItem[d]->scaleTo(1);
			else displayItem[d]->scaleTo(0);
		
		swf->nextFrame();
	}
	
	swf->save(path.UTF8String);
	
	for (int i = 0; i < inputFiles.count; ++i)
		delete bitmap[i];
	
	delete swf;
	Ming_cleanup();	
}
#endif
