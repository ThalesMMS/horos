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

#import "Anonymization.h"
#import "Horos-Swift.h"
#import "HorosAnonymizationSafety.h"
#import "DCMAttributeTag.h"
#import "AnonymizationViewController.h"
#import "AnonymizationSavePanelController.h"
#import "NSFileManager+N2.h"
#import "NSDictionary+N2.h"
#import "DCMObject.h"
#import "DicomImage.h"
#import "DCMCalendarDate.h"
#import "DicomStudy.h"
#import "DicomSeries.h"
#import "BrowserController.h"
#import "AppController.h"
#import "Wait.h"
#import "DicomFile.h"
#import "DICOMToNSString.h"
#import "XMLController.h"
#import "DicomFileDCMTKCategory.h"
#import "XMLControllerDCMTKCategory.h"
#import "N2Debug.h"
#import "NSUserDefaultsController+N2.h"
#include <GDCM/gdcmReader.h>
#include <GDCM/gdcmDefs.h>
#include <GDCM/gdcmAnonymizer.h>
#include <GDCM/gdcmWriter.h>

static NSString *templateDicomFile = nil;

@interface AnonymizationPanelRepresentation : NSObject {
	NSString* defaultsKey;
	id representedObject;
	id target;
	SEL action;
}

@property(retain) NSString* defaultsKey;
@property(retain) id representedObject;
@property(retain) id target;
@property SEL action;

@end
@implementation AnonymizationPanelRepresentation

@synthesize defaultsKey, representedObject, target, action;

-(void)dealloc {
	self.defaultsKey = NULL;
	self.representedObject = NULL;
	self.target = NULL;
	self.action = NULL;
	[super dealloc];
}

@end


@implementation Anonymization

+(DCMAttributeTag*)tagFromString:(NSString*)k {
	static NSDictionary* oldKeys = [[NSDictionary alloc] initWithObjectsAndKeys: 
									@"PatientsName", @"Patient's Name",
									@"PatientsSex", @"Patient's Sex",
									@"PatientID", @"Patient's ID",
									@"PatientsWeight", @"Patient's Weight",
									@"PatientsAge", @"Patient's Age",
									@"ClinicalTrialSponsorName", @"Trial Sponsor Name",
									@"PatientsBirthDate", @"Patient's Date of Birth",
									@"ClinicalTrialProtocolID", @"Trial Protocol ID",
									@"InstitutionName", @"Institution Name",
									@"ClinicalTrialProtocolName", @"Trial Protocol Name",
									@"StudyID", @"Study ID",
									@"ClinicalTrialSiteID", @"Trial Site ID",
									@"StudyDate", @"Study Date",
									@"ClinicalTrialSiteName", @"Trial Site Name",
									@"StudyTime", @"Study Time",
									@"ClinicalTrialSubjectReadingID", @"Trial Subject Reading ID",
									@"AcquisitionDatetime", @"Aquisition Date/Time",
									@"ClinicalTrialSubjectID", @"Trial Subject ID",
									@"SeriesDate", @"Series Date",
									@"ClinicalTrialTimePointID", @"Trial Time Point ID",
									@"SeriesTime", @"Series Time",
									@"ClinicalTrialTimePointDescription", @"Trial Time Point Description",
									@"InstanceCreationDate", @"Image Date",
									@"ClinicalTrialCoordinatingCenterName", @"Trial Coordinating Center Name",
									@"InstanceCreationTime", @"Image Time",
									@"PerformingPhysiciansName", @"Performing Physician",
									@"ReferringPhysiciansName", @"Referring Physician",
									@"PhysiciansofRecord", @"Physicians of Record",
									@"AccessionNumber", @"AccessionNumber",
									NULL];
	
	// older versions of Horos stored anonymization descriptors using the spaced keys and linked those with the DICOM tags through tags in the xib views and code.
	// here, through the oldKeys dictionary, we support these keys and directly translate them to standard dicom tag names.
	NSString* k2 = [oldKeys objectForKey:k];
	if (k2) k = k2;
	
	DCMAttributeTag* tag = [DCMAttributeTag tagWithName:k];
	if (!tag)
		tag = [DCMAttributeTag tagWithTagString:k];
	
	if (!tag)
		NSLog(@"Warning: unrecognized DICOM attribute tag %@", k);
	
	return tag;
}

+(NSArray*)tagsValuesArrayFromDictionary:(NSDictionary*)dic {
	NSMutableArray* out = [[NSMutableArray alloc] initWithCapacity:dic.count];
	
	for (NSString* k in dic) {
		id v = [dic objectForKey:k];
		
		DCMAttributeTag* tag = [self tagFromString:k];
		if (!tag)
			continue;
				
		if ([v isKindOfClass:[NSNull class]])
			v = NULL;
		
		[out addObject:[NSArray arrayWithObjects: tag, v, NULL]]; // if v is null then array contains only 1 object
	}
	
	return [out autorelease];
}

+(NSDictionary*)tagsValuesDictionaryFromArray:(NSArray*)arr {
	NSMutableDictionary* out = [[NSMutableDictionary alloc] initWithCapacity:arr.count];
	
	for (NSArray* a in arr) {
		DCMAttributeTag* tag = [a objectAtIndex:0];
		id v = a.count>1? [a objectAtIndex:1] : @"";
	
		NSString* k = tag.name;
		if (!k) k = tag.stringValue;
		
		[out setObject:v forKey:k];
	}
	
	return [out autorelease];
}

+(NSArray*)tagsArrayFromStringsArray:(NSArray*)strings {
	NSMutableArray* out = [NSMutableArray arrayWithCapacity:strings.count];
	
	for (NSString* s in strings) {
		DCMAttributeTag* tag = [self tagFromString:s];
		if (tag) 
			[out addObject:tag];
	}
	
	return [[out copy] autorelease];
}

+(NSArray*)stringArrayFromTagsArray:(NSArray*)tags {
	NSMutableArray* out = [NSMutableArray arrayWithCapacity:tags.count];
	
	for (DCMAttributeTag* tag in tags)
		[out addObject:tag.stringValue];
	
	return [[out copy] autorelease];
}

+(BOOL)tagsValues:(NSArray*)a1 isEqualTo:(NSArray*)a2 {
	if (a1.count != a2.count)
		return NO;
	for (NSArray* a in a1) {
		DCMAttributeTag* atag = [a objectAtIndex:0];
		BOOL found = NO;
		for (NSArray* b in a2) {
			DCMAttributeTag* btag = [b objectAtIndex:0];
			if ([atag isEqual:btag]) {
				id aval = a.count>1? [a objectAtIndex:1] : @"";
				id bval = b.count>1? [b objectAtIndex:1] : @"";
				
				found = YES;
				
				if (!(aval == bval || [aval isEqual:bval]))
					return NO;
			}
		}
		
		if (!found)
			return NO;
	}
	
	return YES;
}

#pragma mark Panel

+(NSString*) templateDicomFile
{
	return templateDicomFile;
}

+(id)showPanelClass:(Class)c forDefaultsKey:(NSString*)defaultsKey modalForWindow:(NSWindow*)window modalDelegate:(id)delegate didEndSelector:(SEL)sel representedObject:(id)representedObject  {
	
	@try
	{
		[templateDicomFile release];
		templateDicomFile = nil;
		
		templateDicomFile = [[[representedObject objectAtIndex: 0] objectAtIndex: [[representedObject objectAtIndex: 0] count]/2] retain];
	}
	@catch (NSException * e)
	{
		N2LogExceptionWithStackTrace(e);
	}
	
	NSArray* values = [Anonymization tagsValuesArrayFromDictionary:[[NSUserDefaultsController sharedUserDefaultsController] dictionaryForKey:defaultsKey]];
	NSArray* tags = [self tagsArrayFromStringsArray:[[NSUserDefaultsController sharedUserDefaultsController] arrayForKey:[NSString stringWithFormat:@"%@All", defaultsKey]]];
	
	AnonymizationPanelController* panelController = [[c alloc] initWithTags:tags values:values];
	AnonymizationPanelRepresentation* ro = [[[AnonymizationPanelRepresentation alloc] init] autorelease];
	ro.defaultsKey = defaultsKey;
	ro.representedObject = representedObject;
	ro.target = delegate;
	ro.action = sel;
	panelController.representedObject = ro;
	
	[NSApp beginSheet:panelController.window modalForWindow:window modalDelegate:self didEndSelector:@selector(panelDidEnd:returnCode:contextInfo:) contextInfo:panelController];
	[panelController.window orderFront:self];
	
	if (!delegate)
		[NSApp runModalForWindow:panelController.window];
	
	return panelController;
}

+(AnonymizationPanelController*)showPanelForDefaultsKey:(NSString*)defaultsKey modalForWindow:(NSWindow*)window modalDelegate:(id)delegate didEndSelector:(SEL)sel representedObject:(id)representedObject  {
	return [self showPanelClass:[AnonymizationPanelController class] forDefaultsKey:defaultsKey modalForWindow:window modalDelegate:delegate didEndSelector:sel representedObject:representedObject];
}

+(AnonymizationSavePanelController*)showSavePanelForDefaultsKey:(NSString*)defaultsKey modalForWindow:(NSWindow*)window modalDelegate:(id)delegate didEndSelector:(SEL)sel representedObject:(id)representedObject  {
	return [self showPanelClass:[AnonymizationSavePanelController class] forDefaultsKey:defaultsKey modalForWindow:window modalDelegate:delegate didEndSelector:sel representedObject:representedObject];
}

+(void)panelDidEnd:(NSPanel*)panel returnCode:(NSInteger)returnCode contextInfo:(void*)contextInfo {
	AnonymizationPanelController* panelController = (id)contextInfo;
	AnonymizationPanelRepresentation* ro = panelController.representedObject;
	
	if (panelController.end) { // save config
		[[NSUserDefaults standardUserDefaults] setObject:[self stringArrayFromTagsArray:panelController.anonymizationViewController.tags] forKey:[NSString stringWithFormat:@"%@All", ro.defaultsKey]];
		[[NSUserDefaults standardUserDefaults] setObject:[self tagsValuesDictionaryFromArray:panelController.anonymizationViewController.tagsValues] forKey:ro.defaultsKey];
	}
	
	[panel close];
	
	[ro retain];
	panelController.representedObject = ro.representedObject;
	if (ro.target)
		[ro.target performSelector:ro.action withObject:panelController];
	else if (panelController.end)
			[NSApp stopModal];
		else [NSApp abortModal];
	[ro release];
	
	[panelController release];
}

#pragma mark Anonymization

+ (NSString*) cleanStringForFile: (NSString*) s
{
	s = [s stringByReplacingOccurrencesOfString:@"/" withString:@"-"];
	s = [s stringByReplacingOccurrencesOfString:@":" withString:@"-"];
	
	return s;	
}

+ (void) error: (NSString*) s
{
    NSRunCriticalAlertPanel( NSLocalizedString( @"Error", nil), @"%@", NSLocalizedString( @"OK", nil), nil, nil, s);
}

+(NSDictionary*)anonymizeFiles:(NSArray*)files dicomImages: (NSArray*) dicomImages toPath:(NSString*)dirPath withTags:(NSArray*)intags
{
    return [self anonymizeFiles:files dicomImages:dicomImages toPath:dirPath withTags:intags error:NULL];
}

+(NSDictionary*)anonymizeFiles:(NSArray*)files dicomImages: (NSArray*) dicomImages toPath:(NSString*)dirPath withTags:(NSArray*)intags error:(NSError **)outError
{
    if (outError) *outError = nil;
    NSMutableOrderedSet *failureReasons = [NSMutableOrderedSet orderedSet];
    NSMutableOrderedSet *failedTags = [NSMutableOrderedSet orderedSet];
    NSMutableDictionary *fileFailures = [NSMutableDictionary dictionary];
    NSMutableDictionary *originalForStaged = [NSMutableDictionary dictionary];
    void (^recordFailure)(NSString *, NSString *) = ^(NSString *source, NSString *reason) {
        [failureReasons addObject:reason];
        if (!source) return;
        NSMutableArray *reasons = [fileFailures objectForKey:source];
        if (!reasons) {
            reasons = [NSMutableArray array];
            [fileFailures setObject:reasons forKey:source];
        }
        if (![reasons containsObject:reason]) [reasons addObject:reason];
    };
    NSMutableArray *publishedFiles = [NSMutableArray array];
    BOOL cancelled = NO;
	if (!files.count || files.count != dicomImages.count || !intags.count || [NSSet setWithArray:files].count != files.count)
	{
		if (outError) *outError = [NSError errorWithDomain:@"HorosAnonymization" code:1 userInfo:
            @{NSLocalizedDescriptionKey: NSLocalizedString(@"Select images and at least one field to anonymize. The image selection must be complete and must not repeat a file path.", nil),
              @"HorosAnonymizationFileResults": HorosAnonymizationFileResults(files, fileFailures, NO)}];
        
		return nil;
	}
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////

	NSMutableArray* tags = [NSMutableArray arrayWithCapacity:intags.count];
    
	for (NSArray* intag in intags)
	{
		DCMAttributeTag* tag = [intag objectAtIndex:0];
		id val = intag.count>1? [intag objectAtIndex:1] : NULL;
		
		if ([val isKindOfClass:[NSDate class]])
		{
			if ([tag.vr isEqualToString:@"DA"]) //Date String
				val = [DCMCalendarDate dicomDateWithDate:val];
			else if ([tag.vr isEqualToString:@"TM"]) //Time String
				val = [DCMCalendarDate dicomTimeWithDate:val];
			else if ([tag.vr isEqualToString:@"DT"]) //Date Time
				val = [DCMCalendarDate dicomDateTimeWithDicomDate:[DCMCalendarDate dicomDateWithDate:val] dicomTime:[DCMCalendarDate dicomTimeWithDate:val]];
		}
		else if ([val isKindOfClass:[NSNumber class]])
		{
			if ([tag.vr isEqualToString:@"DS"]) //Decimal String representing floating point
				val = [val stringValue];
			else if ([tag.vr isEqualToString:@"IS"]) //Integer String
				val = [val stringValue];
		}
		
		[tags addObject:[NSArray arrayWithObjects: tag, val, NULL]];
	}
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
	
	NSMutableDictionary* filenameTranslation = [NSMutableDictionary dictionaryWithCapacity:files.count];
	
    NSError *stagingError = nil;
    NSString *tempDirPath = HorosCreateAnonymizationStagingDirectory(dirPath, &stagingError);
    if (!tempDirPath) {
        if (outError) *outError = [NSError errorWithDomain:@"HorosAnonymization" code:2 userInfo:
            @{NSLocalizedDescriptionKey: NSLocalizedString(@"Cannot create the anonymization working folder. Check destination permissions and available space. The originals were preserved.", nil),
              @"HorosAnonymizationFileResults": HorosAnonymizationFileResults(files, fileFailures, NO)}];
        return nil;
    }

    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
	
    Wait *splash = nil;
    if( [NSThread isMainThread])
    {
        splash = [[[Wait alloc] initWithString: NSLocalizedString( @"Processing...", nil)] autorelease];
        [[splash progress] setMaxValue: [files count] * 2];
        [splash showWindow: self];
        [splash setCancel: YES];
	}
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    
    NSMutableArray* producedFiles = [NSMutableArray arrayWithCapacity: files.count];
    
    NSInteger fileIndex = 0;
    
    for( NSString* filePath in files)
    {
        NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
        
        @try
        {
            NSString* ext = [filePath pathExtension];
            
            if (!ext.length)
                ext = @"dcm";
            
            NSString* tempFileName = [NSString stringWithFormat:@"%d.%@", (int) fileIndex, ext];
            NSString* tempFilePath = [tempDirPath stringByAppendingPathComponent:tempFileName];
            
            NSError *copyError = nil;
            if (![[NSFileManager defaultManager] copyItemAtPath:filePath toPath:tempFilePath error:&copyError])
                [NSException raise:NSFileHandleOperationException format:@"%@", copyError.localizedDescription];
            
            [filenameTranslation setObject:tempFilePath forKey:filePath];
            ++fileIndex;
            
            [producedFiles addObject: tempFilePath];
            [originalForStaged setObject:filePath forKey:tempFilePath];
            
            [splash incrementBy: 1];
        }
        @catch (NSException * e)
        {
            recordFailure(filePath, NSLocalizedString(@"An input file could not be copied. Check access permissions and available space.", nil));
        }
        
        [pool release];
        
        if ([splash pollCancellation]) {
            cancelled = YES;
            break;
        }
    }
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    
    BOOL anonymationSuccess = !cancelled && producedFiles.count == files.count;
    NSMutableArray* producedAnonFiles = [NSMutableArray arrayWithCapacity: files.count];
    
    for (NSString* f in producedFiles)
    {
        if (cancelled || [splash pollCancellation]) {
            cancelled = YES;
            anonymationSuccess = NO;
            break;
        }
        const char* filename = [f cStringUsingEncoding:[NSString defaultCStringEncoding]];
        
        gdcm::Reader reader;
        
        reader.SetFileName(filename);
        
        if( !reader.Read() )
        {
            recordFailure([originalForStaged objectForKey:f], NSLocalizedString(@"An input file is not a readable DICOM file.", nil));
            
            anonymationSuccess = NO;
            
            continue;
        }
        else
        {
            gdcm::File &file = reader.GetFile();
            
            gdcm::MediaStorage ms;
            ms.SetFromFile(file);
            if( !gdcm::Defs::GetIODNameFromMediaStorage(ms) )
            {
                recordFailure([originalForStaged objectForKey:f], NSLocalizedString(@"An input DICOM storage type is not supported for anonymization.", nil));
                
                anonymationSuccess = NO;
                
                continue;
            }
            else
            {
                NSStringEncoding encoding =
                [NSString encodingForDICOMCharacterSet:[[DicomFile getEncodingArrayForFile:f] objectAtIndex: 0]];
                
                std::vector< std::pair<gdcm::Tag, std::string> > replace_tags;
                for (NSArray* replacingItem in tags)
                {
                    std::string newValue = "";
                    
                    DCMAttributeTag* tag = [replacingItem objectAtIndex:0];
                    if ([replacingItem count] > 1) {
                        const char *encoded = [[[replacingItem objectAtIndex:1] description] cStringUsingEncoding:encoding];
                        if (!encoded) {
                            [failedTags addObject:[NSString stringWithFormat:@"(%04X,%04X)", tag.group, tag.element]];
                            recordFailure([originalForStaged objectForKey:f], NSLocalizedString(@"A replacement value cannot be represented in the input file's character set.", nil));
                            anonymationSuccess = NO;
                            continue;
                        }
                        newValue = std::string(encoded);
                    }
                    
                    replace_tags.push_back( std::make_pair(gdcm::Tag(tag.group,tag.element),newValue) );                    
                }
                
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                
                gdcm::Anonymizer anon;
                anon.SetFile( file );
                
                bool success = true;
                
                std::vector< std::pair<gdcm::Tag, std::string> >::const_iterator it2 = replace_tags.begin();
                for(; it2 != replace_tags.end(); ++it2)
                {
                    if (!anon.Replace(it2->first, it2->second.c_str())) {
                        [failedTags addObject:[NSString stringWithFormat:@"(%04X,%04X)", it2->first.GetGroup(), it2->first.GetElement()]];
                        recordFailure([originalForStaged objectForKey:f], NSLocalizedString(@"The DICOM anonymizer cannot replace one or more selected fields.", nil));
                        success = false;
                    }
                }
                
                if (!success)
                {
                    anonymationSuccess = NO;
                }
                
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                
                NSString* _outfilename = [NSString stringWithCString:filename encoding:[NSString defaultCStringEncoding]];
                NSString* anon_folder = [_outfilename stringByDeletingLastPathComponent];
                NSString* anon_filename = [_outfilename lastPathComponent];
                _outfilename = [NSString stringWithFormat:@"%@/anon_%@",anon_folder,anon_filename];
                const char* outfilename = [_outfilename cStringUsingEncoding:[NSString defaultCStringEncoding]];
                
                gdcm::Writer writer;
                writer.SetFileName( outfilename );
                writer.SetFile( file );
                
                if( !writer.Write() )
                {
                    recordFailure([originalForStaged objectForKey:f], NSLocalizedString(@"An anonymized file could not be written. Check available space and destination permissions.", nil));
                    if( strcmp(filename,outfilename) != 0 )
                    {
                        gdcm::System::RemoveFile( outfilename );
                    }
                    else
                    {
                        std::cerr << "gdcmanon just corrupted: " << filename << " (data lost)." << std::endl;
                        
                    }
                    
                    anonymationSuccess = NO;
                    
                    continue;
                }
                else
                {
                    [producedAnonFiles addObject:_outfilename];
                }
            }
        }
    }
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////

    if ([producedAnonFiles count] != [producedFiles count])
    {
        anonymationSuccess = false;
    }
    else
    {
        for (int i = 0; i < [producedAnonFiles count]; i++)
        {
            NSError* error = nil;
            unlink([[producedFiles objectAtIndex:i] cStringUsingEncoding:[NSString defaultCStringEncoding]]);
            if (![[NSFileManager defaultManager] moveItemAtPath:[producedAnonFiles objectAtIndex:i] toPath:[producedFiles objectAtIndex:i] error:&error])
            {
                recordFailure([originalForStaged objectForKey:[producedFiles objectAtIndex:i]], NSLocalizedString(@"An anonymized file could not be prepared for export.", nil));
                anonymationSuccess = false;
                break;
            }
        }
    }
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    
    if (anonymationSuccess == NO)
    {
        filenameTranslation = nil;
    }
    else
    {
        if( [producedFiles count] != [dicomImages count])
        {
            NSLog( @"***** anonymizeFiles [producedFiles count] != [dicomImages count]");
            
            filenameTranslation = nil;
            
            anonymationSuccess = NO;
        }
        else
        {
            NSMutableArray* dicomSeries = [NSMutableArray array];
            NSMutableArray *dicomStudies = [NSMutableArray array];
            NSUUID *anonymousBatch = [NSUUID UUID];
            
            for (int i = 0; i < [dicomImages count]; i++)
            {
                if ([splash pollCancellation]) {
                    cancelled = YES;
                    filenameTranslation = nil;
                    break;
                }
                NSUInteger inputIndex = i;
                DicomImage *image = [dicomImages objectAtIndex:inputIndex];
                
                @try
                {
                    if (![dicomSeries containsObject:image.series])
                    {
                        [dicomSeries addObject:image.series];
                    }
                    
                    NSString* tempFilePath = [producedFiles objectAtIndex: i];
                    NSString* ext = [tempFilePath pathExtension];
                    if (![dicomStudies containsObject:image.series.study])
                        [dicomStudies addObject:image.series.study];
                    NSString *relativePath = [HorosExportFolderNaming anonymousPathForBatch:anonymousBatch
                        studyIndex:[dicomStudies indexOfObject:image.series.study] + 1
                        seriesIndex:[dicomSeries indexOfObject:image.series] + 1];
                    NSString *fileDirPath = [dirPath stringByAppendingPathComponent:relativePath];

                    @try
                    {
                        [[NSFileManager defaultManager] confirmDirectoryAtPath:fileDirPath];
                    }
                    @catch (NSException *exception)
                    {
                        recordFailure([files objectAtIndex:i], NSLocalizedString(@"The export folder could not be created. Check destination permissions and available space.", nil));
                        
                        filenameTranslation = nil;
                        
                        anonymationSuccess = NO;
                        
                        break;
                    }
                    
                    NSString* filePath;
                    NSInteger i = 0;
                    do
                    {
                        ++i;
                        NSString* is = i ? [NSString stringWithFormat:@"-%4.4d", (int) i] : @"";
                        NSString* fileName = [NSString stringWithFormat:@"IM-%4.4d-%4.4d%@.%@", (int) dicomSeries.count, (int) [image.instanceNumber intValue], is, ext];
                        filePath = [fileDirPath stringByAppendingPathComponent:fileName];
                        
                    } while ([[NSFileManager defaultManager] fileExistsAtPath:filePath]);
                    
                    NSError *moveError = nil;
                    if (![[NSFileManager defaultManager] moveItemAtPath:tempFilePath toPath:filePath error:&moveError]) {
                        recordFailure([files objectAtIndex:inputIndex], NSLocalizedString(@"An anonymized file could not be moved to the export folder.", nil));
                        filenameTranslation = nil;
                        anonymationSuccess = NO;
                        break;
                    }
                    
                    [publishedFiles addObject:filePath];
                    // Copies preserve input order; avoid scanning the whole mapping per file.
                    [filenameTranslation setObject:filePath forKey:[files objectAtIndex:inputIndex]];

                }
                @catch (NSException * e)
                {
                    recordFailure([files objectAtIndex:i], NSLocalizedString(@"An anonymized file could not be exported.", nil));
                    
                    filenameTranslation = nil;
                    
                    anonymationSuccess = NO;
                    
                    break;
                }
                
                [splash incrementBy: 1];
            }
            
            
            

        }
    }
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    
    cancelled = cancelled || [splash pollCancellation];
    [[NSFileManager defaultManager] removeItemAtPath:tempDirPath error:NULL];
	[splash close];
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
	
    if (!HorosAnonymizationOutputsComplete(files, filenameTranslation) || cancelled) {
        filenameTranslation = nil;
        NSUInteger remaining = 0;
        for (NSString *path in publishedFiles)
            if (![[NSFileManager defaultManager] removeItemAtPath:path error:NULL]) remaining++;
        if (outError) {
            if (cancelled && !remaining)
                *outError = [NSError errorWithDomain:NSCocoaErrorDomain code:NSUserCancelledError userInfo:
                    @{@"HorosAnonymizationFileResults": HorosAnonymizationFileResults(files, fileFailures, YES)}];
            else {
                NSMutableArray *details = [NSMutableArray arrayWithObject:NSLocalizedString(@"Anonymization did not produce a complete set of files. The original images have been preserved.", nil)];
                [details addObjectsFromArray:[failureReasons.array subarrayWithRange:NSMakeRange(0, MIN((NSUInteger)6, failureReasons.count))]];
                if (failedTags.count) {
                    NSArray *shown = [failedTags.array subarrayWithRange:NSMakeRange(0, MIN((NSUInteger)8, failedTags.count))];
                    [details addObject:[NSString stringWithFormat:NSLocalizedString(@"Fields not replaced: %@%@", nil), [shown componentsJoinedByString:@", "], failedTags.count > shown.count ? @", ..." : @""]];
                }
                if (remaining)
                    [details addObject:NSLocalizedString(@"Some incomplete output files could not be removed. Do not use this export as a complete anonymized set.", nil)];
                *outError = [NSError errorWithDomain:@"HorosAnonymization" code:3 userInfo:@{NSLocalizedDescriptionKey: [details componentsJoinedByString:@"\n\n"],
                    @"HorosAnonymizationFileResults": HorosAnonymizationFileResults(files, fileFailures, cancelled)}];
            }
        }
    }
    return [[filenameTranslation copy] autorelease];
}


@end
