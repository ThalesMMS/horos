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

#import "Horos-Swift.h"
#import "Reports.h"
#import "HorosReportFileReplacement.h"
#import "HorosReportExtraction.h"
#import "HorosReportFields.h"
#import "HorosOpenDocument.h"
#import "HorosPagesCompatibility.h"
#import "DicomFile.h"
#import "DCM.h"
#import "BrowserController.h"
#import "NSString+N2.h"
#import "NSString+SymlinksAndAliases.h"
#import "NSFileManager+N2.h"
#import "NSAppleScript+N2.h"
#import "DicomDatabase.h"
#import "N2Debug.h"

// if you want check point log info, define CHECK to the next line, uncommented:
#define CHECK NSLog(@"Applescript result code = %d", ok);

// This converts an AEDesc into a corresponding NSValue.

//static id aedesc_to_id(AEDesc *desc)
//{
//	OSErr ok;
//
//	if (desc->descriptorType == typeChar)
//	{
//		NSMutableData *outBytes;
//		NSString *txt;
//
//		outBytes = [[NSMutableData alloc] initWithLength:AEGetDescDataSize(desc)];
//		ok = AEGetDescData(desc, [outBytes mutableBytes], [outBytes length]);
//		CHECK;
//
//		txt = [[NSString alloc] initWithData:outBytes encoding: NSUTF8StringEncoding];
//		[outBytes release];
//		[txt autorelease];
//
//		return txt;
//	}
//
//	if (desc->descriptorType == typeSInt16)
//	{
//		SInt16 buf;
//		AEGetDescData(desc, &buf, sizeof(buf));
//		return [NSNumber numberWithShort:buf];
//	}
//
//	return [NSString stringWithFormat:@"[unconverted AEDesc, type=\"%c%c%c%c\"]", ((char *)&(desc->descriptorType))[0], ((char *)&(desc->descriptorType))[1], ((char *)&(desc->descriptorType))[2], ((char *)&(desc->descriptorType))[3]];
//}

@interface Reports ()

- (void)runScript:(NSString*)txt;
- (NSDictionary*)reportFieldValuesForStudy:(NSManagedObject*)study;
- (BOOL)createNewWordReportForStudy:(NSManagedObject*)study toDestinationPath:(NSString*)destinationFile;

@end

@implementation Reports

+ (NSString*) getUniqueFilename:(id) study
{
	NSString *s = [study valueForKey:@"accessionNumber"];
	
	if( [s length] > 0)
		return [DicomFile NSreplaceBadCharacter: [[study valueForKey:@"patientUID"] stringByAppendingFormat:@"-%@", [study valueForKey:@"accessionNumber"]]];
	else
		return [DicomFile NSreplaceBadCharacter: [[study valueForKey:@"patientUID"] stringByAppendingFormat:@"-%@", [study valueForKey:@"studyInstanceUID"]]];
}

+ (NSString*) getOldUniqueFilename:(NSManagedObject*) study
{
	return [DicomFile NSreplaceBadCharacter: [[study valueForKey:@"patientUID"] stringByAppendingFormat:@"-%@", [study valueForKey:@"id"]]];
}



- (NSString *) HFSStyle: (NSString*) string
{
	return [[(NSURL *)CFURLCreateWithFileSystemPath( kCFAllocatorDefault, (CFStringRef)string, kCFURLHFSPathStyle, NO) autorelease] path];
}

- (NSString *) HFSPathFromPOSIXPath: (NSString*) p
{
    // thanks to stone.com for the pointer to  CFURLCreateWithFileSystemPath()

    CFURLRef    url;
    CFStringRef hfsPath = NULL;

    BOOL        isDirectoryPath = [p hasSuffix:@"/"];
    // Note that for the usual case of absolute paths,  isDirectoryPath is
    // completely ignored by CFURLCreateWithFileSystemPath.
    // isDirectoryPath is only considered for relative paths.
    // This code has not really been tested relative paths...

    url = CFURLCreateWithFileSystemPath(kCFAllocatorDefault,
                                          (CFStringRef)p,
                                          kCFURLPOSIXPathStyle,
                                          isDirectoryPath);
    if (NULL != url) {

        // Convert URL to a colon-delimited HFS path
        // represented as Unicode characters in an NSString.

        hfsPath = CFURLCopyFileSystemPath(url, kCFURLHFSPathStyle);
        if (NULL != hfsPath) {
            [(NSString *)hfsPath autorelease];
        }
        CFRelease(url);
    }

    return (NSString *) hfsPath;
}

- (NSString*) getDICOMStringValueForField: (NSString*) rawField inDICOMFile: (NSString*) path
{
    NSLog( @"Report: DICOM_Field: %@", rawField);
    
    @try {
        NSArray *dicomFields = [rawField componentsSeparatedByString: @":"];
        
        DCMObject *dcmObject = [DCMObject objectWithContentsOfFile: path decodingPixelData:NO];
        if( dcmObject)
        {
            id lastObj = nil;
            for( NSString *dicomField in dicomFields)
            {
                dicomField = [dicomField stringByReplacingOccurrencesOfString:@" " withString:@""];
                
                if( lastObj == nil)
                    lastObj = [dcmObject attributeWithName: dicomField];
                
                if( lastObj == nil)
                    lastObj = [dcmObject attributeForTag: [DCMAttributeTag tagWithTagString: dicomField]];
                
                if( lastObj == nil)
                    break;
                
                if( [lastObj isKindOfClass: [DCMSequenceAttribute class]] == NO)
                    break;
                else
                {
                    dcmObject = [[lastObj sequence] objectAtIndex: 0]; // Read only first item...
                    
                    if( [dicomFields lastObject] != dicomField)
                        lastObj = 0;
                }
            }
            
            if( [lastObj isKindOfClass: [DCMSequenceAttribute class]])
                lastObj = [lastObj readableDescription];
            
            if( [lastObj isKindOfClass: [DCMAttribute class]])
                lastObj = [lastObj value];
            
            if( [lastObj isKindOfClass: [NSString class]])
                return lastObj;
        }
    }
    @catch ( NSException *e) {
        N2LogException( e);
    }
        
    NSLog( @"**** Dicom field not found: %@ in %@", rawField, path);
    
    return nil;
}

- (BOOL) createNewReport:(NSManagedObject*) study destination:(NSString*) path type:(int) type
{
	NSString *uniqueFilename = [Reports getUniqueFilename: study];
	
	switch( type)
	{
		case 0:
		{
			NSString *destinationFile = [NSString stringWithFormat:@"%@%@.%@", path, uniqueFilename, @"doc"];
            return [self createNewWordReportForStudy:study toDestinationPath:destinationFile];
        }
		break;
		
        case 1:
        {
            NSString *destinationFile = [NSString stringWithFormat:@"%@%@.rtf", path, uniqueFilename];
            NSString *templatePath = [BrowserController.currentBrowser.database.baseDirPath stringByAppendingPathComponent:@"ReportTemplate.rtf"];
            NSDictionary *values = [self reportFieldValuesForStudy:study];
            NSArray *series = [[BrowserController currentBrowser] childrenArray:study];
            NSArray *paths = series.count ? [[BrowserController currentBrowser] imagesPathArray:series.firstObject] : nil;
            BOOL created = HorosCreateReportFromTemplate(templatePath, destinationFile, ^BOOL(NSString *prepared, NSError **error) {
                NSDictionary *attributes = nil;
                NSMutableAttributedString *rtf = [[[NSMutableAttributedString alloc] initWithRTF:[NSData dataWithContentsOfFile:prepared] documentAttributes:&attributes] autorelease];
                if (!rtf) return NO;
                HorosFillAttributedReport(rtf, values, ^NSString *(NSString *field) {
                    return paths.count ? [self getDICOMStringValueForField:field inDICOMFile:paths.firstObject] : @"";
                });
                NSData *data = [rtf RTFFromRange:NSMakeRange(0, rtf.length) documentAttributes:attributes];
                return data && [data writeToFile:prepared options:NSDataWritingAtomic error:error];
            }, NULL);
            if (!created) {
                NSRunCriticalAlertPanel(NSLocalizedString(@"Report", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
                    NSLocalizedString(@"The RTF report could not be created. Check the report template and destination. Any existing report has been preserved.", nil));
                return NO;
            }
            [study setValue:destinationFile forKey:@"reportURL"];
            [[NSWorkspace sharedWorkspace] openFile:[study valueForKey:@"reportURL"] withApplication:@"TextEdit" andDeactivate:YES];
        }
        break;

		case 2:
		{
			NSString *destinationFile = [NSString stringWithFormat:@"%@%@.%@", path, uniqueFilename, @"pages"];
			return [self createNewPagesReportForStudy:study toDestinationPath:destinationFile];
		}
		break;
		
		case 5:
		{
			NSString *destinationFile = [NSString stringWithFormat:@"%@%@.%@", path, uniqueFilename, @"odt"];
            return [self createNewOpenDocumentReportForStudy:study toDestinationPath:destinationFile];

		}
		break;
	}
	return YES;
}

// initialize it in your init method:

- (void) dealloc
{
	[templateName release];
	
	[super dealloc];
}

- (id)init
{
	self = [super init];
	if (self)
	{
		templateName = [[NSMutableString stringWithString:@""] retain];
	}
	return self;
}

// do the grunge work -

// the sweetly wrapped method is all we need to know:

- (void)runScript:(NSString *)txt
{
    NSAppleScript* as = [[[NSAppleScript alloc] initWithSource:txt] autorelease];
    NSDictionary* errs = nil;
    [as runWithArguments:nil error:&errs];
    if ([errs count])
        NSLog(@"Error: AppleScript execution failed: %@", errs);
}

+(id)_runAppleScript:(NSString*)source withArguments:(NSArray*)args
{
    NSDictionary* errs = nil;
    
    if (!source) [NSException raise:NSGenericException format:@"Couldn't read script source"];
    
    NSAppleScript* script = [[[NSAppleScript alloc] initWithSource:source] autorelease];
    if (!script) [NSException raise:NSGenericException format:@"Invalid script source"];
    
    id r = [script runWithArguments:args error:&errs];
    if (errs)
    {
        // The caller turns this into a generic "report could not be created",
        // so the editor's own number and message have to be recorded here or
        // they are lost: -1712 (timed out, often a modal dialog), -1743
        // (Automation denied), -10024 (sandbox refused the destination).
        NSLog( @"***** report AppleScript failed: %@ (%@)",
              errs[ NSAppleScriptErrorBriefMessage] ?: errs[ NSAppleScriptErrorMessage] ?: errs,
              errs[ NSAppleScriptErrorNumber] ?: @"no number");
        [NSException raise:NSGenericException format:@"%@ (%@)",
            errs[ NSAppleScriptErrorMessage] ?: errs[ NSAppleScriptErrorBriefMessage] ?: errs,
            errs[ NSAppleScriptErrorNumber] ?: @"no number"];
    }
    
    return r;
}

#pragma mark -

- (NSDictionary*)reportFieldValuesForStudy:(NSManagedObject*)aStudy
{
    NSDateFormatter *date = [[[NSDateFormatter alloc] init] autorelease];
    date.dateStyle = NSDateFormatterShortStyle;
    NSDateFormatter *longDate = [[[NSDateFormatter alloc] init] autorelease];
    longDate.dateStyle = NSDateFormatterLongStyle;
    NSMutableDictionary *values = [NSMutableDictionary dictionary];
    for (NSString *key in aStudy.entity.attributesByName) {
        id value = [aStudy valueForKey:key];
        [values setObject:([value isKindOfClass:NSDate.class] ? [date stringFromDate:value] : [value description]) ?: @"" forKey:key];
    }
    NSDate *now = [NSDate date];
    [values setObject:[date stringFromDate:now] forKey:@"today"];
    [values setObject:[longDate stringFromDate:now] forKey:@"longtoday"];
    return values;
}

- (void)searchAndReplaceFieldsFromStudy:(NSManagedObject*)aStudy inString:(NSMutableString*)aString
{
    if (!aString) return;
    NSDictionary *values = [self reportFieldValuesForStudy:aStudy];
    NSArray *series = [[BrowserController currentBrowser] childrenArray:aStudy];
    NSArray *paths = series.count ? [[BrowserController currentBrowser] imagesPathArray:series.firstObject] : nil;
    HorosFillReportXML(aString, values, ^NSString *(NSString *field) {
        return paths.count ? [self getDICOMStringValueForField:field inDICOMFile:paths.firstObject] : @"";
    });
}

#pragma mark -
#pragma mark Word

+(void)checkForWordTemplates
{
#ifndef MACAPPSTORE
#ifndef OSIRIX_LIGHT
    @try {
        NSString *path = BrowserController.currentBrowser.database.baseDirPath;
        
        if( path == nil)
            path = DicomDatabase.defaultBaseDirPath;
        
        // previously, we had a single word template in the Horos Data folder
        NSString* oldReportFilePath = [path stringByAppendingPathComponent:@"ReportTemplate.doc"];
        
        // today, we use a dir in the database folder, which contains the templates
        NSString* templatesDirPath = [Reports databaseWordTemplatesDirPath];
        
        if( templatesDirPath == nil)
            return;
        
        NSUInteger templatesCount = 0;
        
        if( [[NSFileManager defaultManager] fileExistsAtPath:templatesDirPath])
        {
            for (NSString* filename in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:templatesDirPath error:NULL])
            {
                if( [filename.pathExtension isEqualToString: @"doc"])
                    ++templatesCount;
            }
        }
        
        if (!templatesCount)
        {
            if ([[NSFileManager defaultManager] fileExistsAtPath: oldReportFilePath])
                [[NSFileManager defaultManager] moveItemAtPath: oldReportFilePath toPath:[templatesDirPath stringByAppendingPathComponent: [oldReportFilePath lastPathComponent]] error: nil];
            else
                [[NSFileManager defaultManager] copyItemAtPath:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"ReportTemplate.doc"] toPath:[templatesDirPath stringByAppendingPathComponent:@"Basic Report Template.doc"] error:NULL];
        }
    }
    @catch (NSException *exception) {
        N2LogException( exception);
    }
#endif
#endif
}

+(NSString*)databaseWordTemplatesDirPath {
    
    NSString *path = BrowserController.currentBrowser.database.baseDirPath;
    
    if( path == nil)
        path = DicomDatabase.defaultBaseDirPath;
    
    if (!path.length) return nil;
    NSString *folder = [path stringByAppendingPathComponent:@"WORD TEMPLATES"];
    BOOL isDirectory = NO;
    if ([NSFileManager.defaultManager fileExistsAtPath:folder isDirectory:&isDirectory])
        return isDirectory ? folder : nil;
    // A colliding file, dangling symlink, or failed mkdir must never be removed.
    if (![NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:NO attributes:nil error:NULL])
        return nil;
    return folder;
}

+(NSString*)resolvedDatabaseWordTemplatesDirPath {
    return [[self databaseWordTemplatesDirPath] stringByResolvingSymlinksAndAliases];
}

+ (NSMutableArray*)wordTemplatesList
{
	NSMutableArray* templatesArray = [NSMutableArray array];
    
    NSString *directory = [self resolvedDatabaseWordTemplatesDirPath];
    if (!directory.length) return templatesArray;
	NSDirectoryEnumerator* directoryEnumerator = [[NSFileManager defaultManager] enumeratorAtPath:directory];
	NSString* filename;
	while ((filename = [directoryEnumerator nextObject]))
	{
		[directoryEnumerator skipDescendents];
        
        if( [filename.pathExtension hasPrefix: @"doc"]) //hasPrefix: compatible with .doc and .docx
            [templatesArray addObject: filename];
	}
	
    [templatesArray sortUsingSelector:@selector(compare:)];
    
	return templatesArray;
}

- (NSString*) generateWordReportMergeDataForStudy:(NSManagedObject*)study toPath:(NSString*)path
{
	long x;
	
	NSManagedObjectModel	*model = [[[study managedObjectContext] persistentStoreCoordinator] managedObjectModel];
    
	NSArray *properties = [[[[model entitiesByName] objectForKey:@"Study"] attributesByName] allKeys];
	
	NSMutableString	*file = [NSMutableString stringWithString:@""];
	
	for( x = 0; x < [properties count]; x++)
	{
		NSString	*name = [properties objectAtIndex: x];
		[file appendString:name];
		[file appendFormat: @"%c", NSTabCharacter];
	}
	
	[file appendString:@"\r"];
	
	NSDateFormatter		*date = [[[NSDateFormatter alloc] init] autorelease];
	[date setDateStyle: NSDateFormatterShortStyle];
	
	for( x = 0; x < [properties count]; x++)
	{
		NSString	*name = [properties objectAtIndex: x];
		NSString	*string;
		
		if( [[study valueForKey: name] isKindOfClass: [NSDate class]])
		{
			string = [date stringFromDate: [study valueForKey: name]];
		}
		else string = [[study valueForKey: name] description];
		
		if( string)
			[file appendString: [DicomFile NSreplaceBadCharacter:string]];
		else
			[file appendString: @""];
		
		[file appendFormat: @"%c", NSTabCharacter];
	}
	
	NSMutableAttributedString	*rtf = [[[NSMutableAttributedString alloc] initWithString: file] autorelease];
	
    NSData *data = [rtf RTFFromRange:rtf.range documentAttributes:@{}];
    return [data writeToFile:path options:NSDataWritingAtomic error:NULL] ? path : nil;
}

- (BOOL)createNewWordReportForStudy:(NSManagedObject*)study toDestinationPath:(NSString*)destinationFile
{
    NSString* inTemplateName = templateName;
    
    if( inTemplateName.length == 0 && [[Reports wordTemplatesList] count])
        inTemplateName = [[Reports wordTemplatesList] objectAtIndex: 0];
    
    NSString* templatePath = nil;
    
    NSString* templatesDirPath = [[self class] resolvedDatabaseWordTemplatesDirPath];
    NSArray *filenames = templatesDirPath.length ? [[NSFileManager.defaultManager contentsOfDirectoryAtPath:templatesDirPath error:NULL]
        sortedArrayUsingSelector:@selector(compare:)] : nil;
    BOOL explicitFormat = [inTemplateName.pathExtension.lowercaseString hasPrefix:@"doc"];
    for (NSString *filename in filenames) {
        NSString *candidate = [templatesDirPath stringByAppendingPathComponent:filename];
        if (![filename.pathExtension.lowercaseString hasPrefix:@"doc"] ||
            ![[NSFileManager.defaultManager attributesOfItemAtPath:candidate error:NULL].fileType isEqualToString:NSFileTypeRegular])
            continue;
        // A menu selection includes its extension: never substitute another
        // format with the same stem. Keep legacy extensionless names working.
        if ([filename isEqualToString:inTemplateName] ||
            (!explicitFormat && [filename.stringByDeletingPathExtension isEqualToString:inTemplateName])) {
            templatePath = candidate;
            break;
        }
    }

    if( templatePath == nil || ![[NSFileManager defaultManager] fileExistsAtPath:templatePath])
    {
        NSRunCriticalAlertPanel( NSLocalizedString( @"Microsoft Word", nil),  NSLocalizedString(@"I cannot find the Horos Word Template doc file.", nil), NSLocalizedString(@"OK", nil), nil, nil);
        return NO;
    }
    
    // Word 16 returns no value for `open ... add to recent files false`, so
    // `set d to open ...` leaves d undefined and every later reference fails.
    // Track the documents by name instead, and never let the error handler
    // touch a variable the failing statement may not have assigned - it used
    // to raise -2753 of its own and replace Word's error with "variable not
    // defined". Commands are sent to the loop variable of `every document`:
    // Word rejects `active document` and `document 1` as command targets.
    NSString *source =
    @"on run argv\n"
    @"  set dataSourceFile to POSIX file (item 1 of argv)\n"
    @"  set outFilePath to POSIX file (item 2 of argv)\n"
    @"  set templatePath to POSIX file (item 3 of argv)\n"
    @"  set templateName to missing value\n"
    @"  set mergedName to missing value\n"
    @"  tell application \"Microsoft Word\"\n"
    @"    try\n"
    @"      open templatePath add to recent files false\n"
    @"      set templateName to name of active document\n"
    @"      open data source data merge of active document name dataSourceFile\n"
    @"      set myMerge to data merge of active document\n"
    @"      set destination of myMerge to send to new document\n"
    @"      execute data merge myMerge\n"
    @"      set mergedName to name of active document\n"
    @"      if mergedName is templateName then error \"The merge did not create a new document.\"\n"
    @"      set savedMerge to false\n"
    @"      repeat with d in (get every document)\n"
    @"        if (name of d) is mergedName then\n"
    @"          if (item 4 of argv) is \"docx\" then\n"
    @"            save as d file name (outFilePath as string) file format format document add to recent files false\n"
    @"          else\n"
    @"            save as d file name (outFilePath as string) file format format document97 add to recent files false\n"
    @"          end if\n"
    @"          set savedMerge to true\n"
    @"        end if\n"
    @"      end repeat\n"
    @"      if not savedMerge then error \"The merged document could not be saved.\"\n"
    @"      my closeReportDocument(mergedName)\n"
    @"      set mergedName to missing value\n"
    @"      my closeReportDocument(templateName)\n"
    @"      set templateName to missing value\n"
    @"    on error errorMessage number errorNumber\n"
    @"      my closeReportDocument(mergedName)\n"
    @"      my closeReportDocument(templateName)\n"
    @"      error errorMessage number errorNumber\n"
    @"    end try\n"
    @"  end tell\n"
    @"end run\n"
    @"\n"
    @"on closeReportDocument(theName)\n"
    @"  if theName is missing value then return\n"
    @"  tell application \"Microsoft Word\"\n"
    @"    try\n"
    @"      repeat with d in (get every document)\n"
    @"        if (name of d) is theName then close d saving no\n"
    @"      end repeat\n"
    @"    end try\n"
    @"  end tell\n"
    @"end closeReportDocument\n";

    NSError *reportError = nil;
    BOOL created = HorosCreateReportFromTemplate(templatePath, destinationFile, ^BOOL(NSString *prepared, NSError **error) {
        NSString *directory = prepared.stringByDeletingLastPathComponent;
        NSString *sourceData = [self generateWordReportMergeDataForStudy:study
            toPath:[directory stringByAppendingPathComponent:@"MergeData.rtf"]];
        if (!sourceData) return NO;
        NSString *extension = [destinationFile.pathExtension.lowercaseString isEqualToString:@"docx"] ? @"docx" : @"doc";
        NSString *output = [directory stringByAppendingPathComponent:[@"Merged" stringByAppendingPathExtension:extension]];
        @try {
            [[self class] _runAppleScript:source withArguments:@[sourceData, output, prepared, extension]];
        }
        @catch (NSException *exception) {
            // Keep the editor's own message: the caller only sees a BOOL, and
            // the preparation wrapper would otherwise replace it.
            if (error) *error = [NSError errorWithDomain:@"HorosWordReport" code:1
                userInfo:@{NSLocalizedDescriptionKey: exception.reason ?: exception.name}];
            return NO;
        }
        NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:output error:error];
        if (![attributes.fileType isEqualToString:NSFileTypeRegular] || !attributes.fileSize) return NO;
        // Only the private copy is replaced here; publication happens after success.
        if (![NSFileManager.defaultManager removeItemAtPath:prepared error:error]) return NO;
        return [NSFileManager.defaultManager moveItemAtPath:output toPath:prepared error:error];
    }, &reportError);
    if (!created) {
        // Name what Word refused: the generic sentence alone sent people
        // looking at the template when the cause was an Automation refusal or
        // a destination the editor's sandbox would not write.
        NSString *detail = reportError.localizedDescription.length
            ? [NSString stringWithFormat:@"%@\n\n%@",
               NSLocalizedString(@"The Word report could not be created. Check the template, Word permissions, and destination. Any existing report has been preserved.", nil),
               reportError.localizedDescription]
            : NSLocalizedString(@"The Word report could not be created. Check the template, Word permissions, and destination. Any existing report has been preserved.", nil);
        NSLog( @"***** Word report not created: %@", reportError ?: @"no error reported");
        NSRunCriticalAlertPanel(NSLocalizedString(@"Microsoft Word", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil, detail);
        return NO;
    }

    [study setValue:destinationFile forKey: @"reportURL"];
    
    [[NSWorkspace sharedWorkspace] openFile:destinationFile withApplication:@"Microsoft Word" andDeactivate:YES];
    
    return YES;
}

#pragma mark -
#pragma mark OpenDocument

// ODT templates live beside the legacy ReportTemplate.odt in the database root.
+ (NSMutableArray*)openDocumentTemplatesList
{
    NSString *directory = BrowserController.currentBrowser.database.baseDirPath;
    NSMutableArray *templates = [NSMutableArray array];
    for (NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:directory error:NULL]) {
        NSString *path = [directory stringByAppendingPathComponent:name];
        if ([name.pathExtension.lowercaseString isEqualToString:@"odt"] &&
            [[NSFileManager.defaultManager attributesOfItemAtPath:path error:NULL].fileType isEqualToString:NSFileTypeRegular])
            [templates addObject:name];
    }
    [templates sortUsingSelector:@selector(compare:)];
    return templates;
}

+ (NSString*)pathForOpenDocumentTemplate:(NSString*)name
{
    NSArray *templates = [self openDocumentTemplatesList];
    if (!name.length)
        name = [templates containsObject:@"ReportTemplate.odt"] ? @"ReportTemplate.odt" : templates.firstObject;
    // Only resolve a listed file, never silently substitute a missing selection.
    if (!name || ![templates containsObject:name]) return nil;
    return [BrowserController.currentBrowser.database.baseDirPath stringByAppendingPathComponent:name];
}

- (BOOL) createNewOpenDocumentReportForStudy:(NSManagedObject*)aStudy toDestinationPath:(NSString*)aPath;
{
    NSString *templatePath = [[self class] pathForOpenDocumentTemplate:templateName];
    BOOL created = HorosCreateOpenDocument(templatePath, aPath, ^(NSMutableString *content) {
        [self searchAndReplaceFieldsFromStudy:aStudy inString:content];
    }, NULL);
    if (!created) {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Report", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"The OpenDocument report could not be created. Check the report template and destination. Any existing report has been preserved.", nil));
        return NO;
    }

	[aStudy setValue:aPath forKey:@"reportURL"];
	
	// open the modified .odt file
	if( [[NSWorkspace sharedWorkspace] openFile:aPath withApplication: @"LibreOffice" andDeactivate: YES] == NO)
    {
        if( [[NSWorkspace sharedWorkspace] openFile:aPath withApplication: @"OpenOffice" andDeactivate: YES] == NO)
            [[NSWorkspace sharedWorkspace] openFile:aPath withApplication: nil andDeactivate: YES];
	}
    [NSThread sleepForTimeInterval: 1];
	
	// end
	return YES;
}

#pragma mark -
#pragma mark Pages.app


+(NSString*)databasePagesTemplatesDirPath {
    
    NSString *path = BrowserController.currentBrowser.database.baseDirPath;
    
    if( path == nil)
        path = DicomDatabase.defaultBaseDirPath;
    
    return [path stringByAppendingPathComponent:@"PAGES TEMPLATES"];
}

+ (void)checkForPagesTemplate;
{
#ifndef MACAPPSTORE
#ifndef OSIRIX_LIGHT
    
	NSString* templatesDirPath = [Reports databasePagesTemplatesDirPath];
	
    if ([[NSFileManager defaultManager] fileExistsAtPath:templatesDirPath] == NO)
        [[NSFileManager defaultManager] createDirectoryAtPath:templatesDirPath withIntermediateDirectories:NO attributes:nil error:nil];
    
	// Pages template
    NSString *defaultReport = [templatesDirPath stringByAppendingPathComponent:@"/Horos Basic Report.pages"];
	if ([[NSFileManager defaultManager] fileExistsAtPath: defaultReport] == NO)
        [[NSFileManager defaultManager] copyItemAtPath:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/Horos Report.pages"] toPath:defaultReport error:NULL];
	
#endif
#endif
}


+ (int)Pages5orHigher
{
    return HorosPagesUsesModernTemplates([HorosPagesApplication information]);
}

- (BOOL)decompressPagesFileIfNecessary:(NSString*)aPath
{
    BOOL isDirectory = NO;
    if (![NSFileManager.defaultManager fileExistsAtPath:aPath isDirectory:&isDirectory]) return NO;
    if (isDirectory) return YES;
    NSData *data = [NSData dataWithContentsOfFile:aPath options:NSDataReadingMappedIfSafe error:NULL];
    NSString *unpacked = HorosExtractPagesPackage(data);
    if (!unpacked) return NO;
    @try {
        return HorosReplaceReportFile(unpacked, aPath, NULL);
    } @finally {
        [NSFileManager.defaultManager removeItemAtPath:unpacked error:NULL];
    }
}

- (BOOL)createNewPagesReportForStudy:(NSManagedObject*)aStudy toDestinationPath:(NSString*)aPath
{
    // Not by one bundle identifier: Pages '09 answers to com.apple.iWork.Pages
    // and Pages 15 to com.apple.Pages, so asking only for the first said "Pages
    // is not installed" with Pages in the Applications folder.
    NSURL *pagesApplication = [HorosPagesApplication url];
    if (!pagesApplication) {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Pages", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"Pages is not installed or could not be located. Install Pages before creating a Pages report. No report has been changed.", nil));
        return NO;
    }
    NSString *templatePath = [[self class] pathForPagesTemplate:templateName];
    if (!templatePath.length || ![[NSFileManager defaultManager] fileExistsAtPath:templatePath]) {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Pages", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"The selected Pages template could not be found. Choose an available template and try again. No report has been changed.", nil));
        return NO;
    }
    NSError *error = nil;
    BOOL created = HorosCreateReportFromTemplate(templatePath, aPath, ^BOOL(NSString *prepared, NSError **preparationError) {
        // A template Pages '09 wrote keeps its text in index.xml and can be
        // filled in here. One that Pages 5 or later wrote keeps it in
        // Index/*.iwa, where nothing here can reach it - and unpacking it first
        // would turn the document into a directory - so Pages fills that one in.
        BOOL isDirectory = NO;
        BOOL legacy = NO;
        if ([NSFileManager.defaultManager fileExistsAtPath:prepared isDirectory:&isDirectory] && isDirectory)
            legacy = [NSFileManager.defaultManager fileExistsAtPath:[prepared stringByAppendingPathComponent:@"index.xml"]];
        else
            legacy = HorosPagesArchiveHasIndexXML([NSData dataWithContentsOfFile:prepared options:NSDataReadingMappedIfSafe error:NULL]);

        if (legacy)
        {
            if (![self decompressPagesFileIfNecessary:prepared]) return NO;
            NSString *indexPath = [prepared stringByAppendingPathComponent:@"index.xml"];
            NSMutableString *xml = [NSMutableString stringWithContentsOfFile:indexPath encoding:NSUTF8StringEncoding error:preparationError];
            if (!xml) return NO;
            [self searchAndReplaceFieldsFromStudy:aStudy inString:xml];
            return [xml writeToFile:indexPath atomically:YES encoding:NSUTF8StringEncoding error:preparationError];
        }

        NSDictionary *values = [self reportFieldValuesForStudy:aStudy];
        NSArray *series = [[BrowserController currentBrowser] childrenArray:aStudy];
        NSArray *paths = series.count ? [[BrowserController currentBrowser] imagesPathArray:series.firstObject] : nil;
        return [HorosPagesDocumentFill fillDocumentAtPath:prepared substitute:^NSString *(NSString *line) {
            NSMutableString *filled = [[line mutableCopy] autorelease];
            HorosFillReportText(filled, values, ^NSString *(NSString *field) {
                return paths.count ? [self getDICOMStringValueForField:field inDICOMFile:paths.firstObject] : @"";
            });
            return filled;
        }];
    }, &error);
    if (!created) {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Pages", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"The Pages report could not be created. Check that Pages can open the template, and that Horos is allowed to control Pages in System Settings > Privacy & Security > Automation. The original template and any existing report have been preserved.", nil));
        return NO;
    }
    [aStudy setValue:aPath forKey:@"reportURL"];
    if (![[NSWorkspace sharedWorkspace] openFile:aPath withApplication:pagesApplication.path andDeactivate:YES]) {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Pages", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"The report was created and attached to the study, but Pages could not open it. Check that Pages can launch, then open the report again. The generated report has been kept.", nil));
        return NO;
    }
    return YES;
}

+ (NSString*) pathForPagesTemplate: (NSString*) templateName
{
    if( templateName.length == 0 && [[Reports pagesTemplatesList] count])
        templateName = [[Reports pagesTemplatesList] objectAtIndex: 0];
    
    if( [Reports Pages5orHigher])
    {
        NSString *templateDirectory = [self databasePagesTemplatesDirPath];
        NSDirectoryEnumerator *directoryEnumerator = [[NSFileManager defaultManager] enumeratorAtPath:templateDirectory];
        
        NSString *file;
        while ((file = [directoryEnumerator nextObject]))
        {
            [directoryEnumerator skipDescendents];
            if( [file.stringByDeletingPathExtension isEqualToString: templateName.stringByDeletingPathExtension])
            {
                if( [file.pathExtension isEqualToString: @"pages"])
                    return [templateDirectory stringByAppendingPathComponent: file];
            }
        }
    }
    else
    {
        NSArray *templateDirectoryPathArray = [NSArray arrayWithObjects:NSHomeDirectory(), @"Library", @"Application Support", @"iWork", @"Pages", @"Templates", @"OsiriX", @"Horos", nil];
        NSString *templateDirectory = [NSString pathWithComponents:templateDirectoryPathArray];
        NSDirectoryEnumerator *directoryEnumerator = [[NSFileManager defaultManager] enumeratorAtPath:templateDirectory];
        
//        NSMutableArray *templatesArray = [NSMutableArray arrayWithCapacity:1];
        id file;
        while ((file = [directoryEnumerator nextObject]))
        {
            [directoryEnumerator skipDescendents];
            
            if( [file isEqualToString: templateName] || [file isEqualToString: [NSString stringWithFormat: @"Horos %@", templateName]])
                return [templateDirectory stringByAppendingPathComponent: file];
        }
    }
    
    return nil;
}

+ (void) copyPages4templatesToPages5: (NSString*) newDirectory
{
    NSArray *templateDirectoryPathArray = [NSArray arrayWithObjects:NSHomeDirectory(), @"Library", @"Application Support", @"iWork", @"Pages", @"Templates", @"OsiriX", @"Horos", nil];
    NSString *templateDirectory = [NSString pathWithComponents:templateDirectoryPathArray];
    NSDirectoryEnumerator *directoryEnumerator = [[NSFileManager defaultManager] enumeratorAtPath:templateDirectory];
    
//    NSMutableArray *templatesArray = [NSMutableArray arrayWithCapacity:1];
    id file;
    while ((file = [directoryEnumerator nextObject]))
    {
        [directoryEnumerator skipDescendents];
        if ([file hasPrefix:@"Horos "])
        {
            NSString *fromPath = [templateDirectory stringByAppendingPathComponent: file];
            NSString *toPath = [newDirectory stringByAppendingPathComponent: file];
            
            toPath = [[toPath stringByDeletingPathExtension] stringByAppendingPathExtension: @"pages"];
            
            [[NSFileManager defaultManager] copyItemAtPath: fromPath toPath: toPath byReplacingExisting: NO error: nil];
        }
    }
}

+ (NSMutableArray*)pagesTemplatesList;
{
    if( [Reports Pages5orHigher])
    {
        NSString *templateDirectory = [self databasePagesTemplatesDirPath];
        
        static BOOL firstTime = YES;
        if( firstTime)
        {
            firstTime = NO;
            [Reports copyPages4templatesToPages5: templateDirectory];
        }
        
        NSDirectoryEnumerator *directoryEnumerator = [[NSFileManager defaultManager] enumeratorAtPath:templateDirectory];
        NSMutableArray *templatesArray = [NSMutableArray arrayWithCapacity:1];
        NSString *file;
        while ((file = [directoryEnumerator nextObject]))
        {
            [directoryEnumerator skipDescendents];
            if( [file.pathExtension isEqualToString: @"pages"])
                [templatesArray addObject: file];
        }
        
        [templatesArray sortUsingSelector:@selector(compare:)];
        
        return templatesArray;
    }
    else
    {
        NSArray *templateDirectoryPathArray = [NSArray arrayWithObjects:NSHomeDirectory(), @"Library", @"Application Support", @"iWork", @"Pages", @"Templates", @"OsiriX", @"Horos", nil];
        NSString *templateDirectory = [NSString pathWithComponents:templateDirectoryPathArray];
        NSDirectoryEnumerator *directoryEnumerator = [[NSFileManager defaultManager] enumeratorAtPath:templateDirectory];
        
        NSMutableArray *templatesArray = [NSMutableArray arrayWithCapacity:1];
        id file;
        while ((file = [directoryEnumerator nextObject]))
        {
            [directoryEnumerator skipDescendents];
            NSRange rangeOfOsiriX = [file rangeOfString:@"Horos "];
            if(rangeOfOsiriX.location==0 && rangeOfOsiriX.length==7)
            {
                // this is a template for us (we should maybe verify that it is a valid Pages template... but what ever...)
                [templatesArray addObject:[file substringFromIndex:7]];
            }
        }
        
        [templatesArray sortUsingSelector:@selector(compare:)];

        return templatesArray;
    }
}

- (NSMutableString *)templateName;
{
	return templateName;
}

- (void)setTemplateName:(NSString *)aName;
{
    // Resolvers remove only the final extension when comparing names. Keep the
    // selected filename intact so dots and format-like text in its stem survive.
    [templateName setString:aName ?: @""];
}

@end
