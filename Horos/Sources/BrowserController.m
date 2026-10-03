#include <limits.h>
#import "Horos.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import "HorosAlertPanel.h"
/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation, ?version 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE. ?See the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos. ?If not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program: ? OsiriX
 ?Copyright (c) OsiriX Team
 ?All rights reserved.
 ?Distributed under GNU - LGPL
 ?
 ?See http://www.osirix-viewer.com/copyright.html for details.
 ? ? This software is distributed WITHOUT ANY WARRANTY; without even
 ? ? the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
 ? ? PURPOSE.
 ============================================================================*/

#include <objc/runtime.h>

#include "options.h"
#import "QuicktimeExport.h"

#import "HorosRasterSeriesFolder.h"
#import "HorosFileCopy.h"
#import "ToolbarPanel.h"
#import "DicomDatabase.h"
#import "DicomDatabase+Routing.h"
#import "DicomDatabase+Clean.h"
#import "Horos-Swift.h"
#import <PDFKit/PDFKit.h>
#import <ApplicationServices/ApplicationServices.h>
#import "DicomDatabase+DCMTK.h"
#import "DCMTKStudyQueryNode.h"
#import "DCMTKSeriesQueryNode.h"
#import "DicomDatabase+Scan.h"
#import "RemoteDicomDatabase.h"
#import "SRAnnotation.h"
#import <DiscRecording/DRDevice.h>
#import "DCMView.h"
#import "MyOutlineView.h"
#import "PreviewView.h"
#import "QueryController.h"
#import "DicomSeries.h"
#import "DicomImage.h"
#import "NSWindow+N2.h"
#import "DicomStudy.h"
#import "DicomStudy+Report.h"
#import "DCMPix.h"
#import "SRAnnotation.h"
#import "AppController.h"
#import "DicomData.h"
#import "BrowserController.h"
#import "HorosDICOMWriter.h"
#import "HorosDCMTKObject.h"
#import "HorosBoundedTask.h"
#import "HorosDatabaseFileValidation.h"
#import "HorosAnonymizationSafety.h"
#import "HorosReportExtraction.h"
#import "HorosReportFileReplacement.h"
#import "ViewerController.h"
#import "SeriesView.h"
#import "BrowserController+GSPS.h"
#import "PluginFilter.h"
#import "ReportPluginFilter.h"
#import "DicomFile.h"
#import "DicomFileDCMTKCategory.h"
#import "NSSplitViewSave.h"
#import "DicomDirParser.h"
#import "MutableArrayCategory.h"
#import "SmartWindowController.h"
#import "QueryFilter.h"
#import "ImageAndTextCell.h"
#import "Wait.h"
#import "WaitRendering.h"
#import "BurnerWindowController.h"
#import "DCMTransferSyntax.h"
#import "DCMAttributeTag.h"
#import "DCMPixelDataAttribute.h"
#import "DCMCalendarDate.h"
#import "DCM.h"
#import "DCMObject.h"
#import "DCMAbstractSyntaxUID.h"
#import "DCMNetServiceDelegate.h"
#import "LogWindowController.h"
#import "stringAdditions.h"
#import "SendController.h"
#import "Reports.h"
#import "LogManager.h"
#import "DCMTKStoreSCU.h"
#import "BonjourPublisher.h"
#import "BonjourBrowser.h"
#import "WindowLayoutManager.h"
#import "QTExportHTMLSummary.h"
#import "BrowserControllerDCMTKCategory.h"
#import "BrowserMatrix.h"
#import "DicomAlbum.h"
#import "PluginManager.h"
#import "PluginManagerController.h"
#import "N2OpenGLViewWithSplitsWindow.h"
#import "XMLController.h"
#import "WebPortalConnection.h"
#import "WebPortalUser.h"
#import "WebPortalStudy.h"
#import "Notifications.h"
#import "NSAppleScript+HandlerCalls.h"
#import "CSMailMailClient.h"
#import "NSImage+OsiriX.h"
#import "NSString+N2.h"
#import "NSView+N2.h"
#import "NSUserDefaultsController+OsiriX.h"
#import "NSUserDefaultsController+N2.h"
#import "ThreadsManager.h"
#import "NSThread+N2.h"
#import "BrowserController+Activity.h"
#import "NSError+OsiriX.h"
#import "NSImage+N2.h"
#import "NSFileManager+N2.h"
#import "N2Debug.h"
#import "NSThread+N2.h"
#import "ThreadModalForWindowController.h"
#import "NSUserDefaults+OsiriX.h"
#import "WADODownload.h"
#import "NSManagedObject+N2.h"
#import "DICOMExport.h"
#import "PrettyCell.h"
#import "ComparativeCell.h"
#import "N2Stuff.h"
#import "NSNotificationCenter+N2.h"
#import "NSFullScreenWindow.h"
#import "CustomIntervalPanel.h"
#import "DICOMToNSString.h"
#import "XMLControllerDCMTKCategory.h"
#import "WADOXML.h"
#import "DicomDir.h"
#import "CPRVolumeData.h"
#import "O2HMigrationAssistant.h"
#import "ICloudDriveDetector.h"
#import "NSException+N2.h"

#if defined(USEHOMEPHONE)
#import "homephone/HorosHomePhone.h"
#endif

#import "url.h"

#ifndef OSIRIX_LIGHT
#import "Anonymization.h"
#import "AnonymizationSavePanelController.h"
#import "AnonymizationViewController.h"
#import "NSFileManager+N2.h"
#endif

#import "WebPortal.h"
#import "WebPortal+Email+Log.h"
#import "WebPortalDatabase.h"

#define DISTANTSTUDYFONT @"Helvetica-BoldOblique"

//#define DATABASEVERSION @"2.5"

#include <CoreFoundation/CoreFoundation.h>
#include <CoreServices/CoreServices.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/storage/IOMedia.h>
#include <IOKit/storage/IOCDMedia.h>
#include <IOKit/storage/IODVDMedia.h>

static BrowserController *browserWindow = nil;
__attribute__((used)) NSString * const O2AlbumDragType = @"Osirix Album drag";
__attribute__((used)) NSString * const O2DatabaseXIDsDragType = @"BrowserController.database.context.XIDs";
__attribute__((used)) NSString * const O2PasteboardTypeDatabaseObjectXIDs = @"com.opensource.osirix.database.xids";
static BOOL loadingIsOver = NO;//, isAutoCleanDatabaseRunning = NO;
static NSMenu *contextual = nil;
static NSMenu *contextualRT = nil;  // Alternate menus for RT objects (which often don't have images)
static int DicomDirScanDepth = 0;
static int DefaultFolderSizeForDB = 0;
static NSString *smartAlbumDistantArraySync = @"smartAlbumDistantArraySync";

extern int delayedTileWindows;
extern BOOL NEEDTOREBUILD;//, COMPLETEREBUILD;

#pragma deprecated(asciiString)
NSString* asciiString(NSString* str)
{
    return [str ASCIIString];
}

// The public alias selectors preserve nil for a path which is not an alias.
static NSString *HorosBrowserAliasDestination(NSString *path)
{
    if (!path) return nil;
    NSURL *url = [NSURL fileURLWithPath:path];
    NSNumber *isAlias = nil;
    if (![url getResourceValue:&isAlias forKey:NSURLIsAliasFileKey error:NULL] || !isAlias.boolValue) return nil;
    return [NSURL URLByResolvingAliasFileAtURL:url options:0 error:NULL].path;
}

// Preserve the historical OsiriX Distributed Objects endpoint for SDK clients.
// NSXPCConnection uses a different protocol and cannot replace this wire contract.
static void HorosRegisterLegacyDistributedBrowser(id browser)
{
    Class connectionClass = NSClassFromString(@"NSConnection");
    SEL sharedSelector = NSSelectorFromString(@"defaultConnection");
    if (![connectionClass respondsToSelector:sharedSelector]) return;
    id connection = [connectionClass performSelector:sharedSelector];
    for (NSString *name in @[@"registerName:", @"setRootObject:"]) {
        SEL selector = NSSelectorFromString(name);
        NSMethodSignature *signature = [connection methodSignatureForSelector:selector];
        if (!signature) continue;
        NSInvocation *invocation = [NSInvocation invocationWithMethodSignature:signature];
        invocation.target = connection;
        invocation.selector = selector;
        id argument = [name isEqualToString:@"registerName:"] ? @"OsiriX" : browser;
        [invocation setArgument:&argument atIndex:2];
        [invocation invoke];
    }
}

@implementation NSString (BrowserController)

-(NSMutableString*)filenameString
{
    NSMutableString* str = [NSMutableString stringWithString:[self ASCIIString]];
    
    NSMutableString* outString = [BrowserController replaceNotAdmitted:str];
    
    if( [outString length] == 0)
        outString = [NSMutableString stringWithString: @"AAA"];
    
    return outString;
}

@end

@interface BrowserController ()
{
    NSTimeInterval _lastImportListRefresh, _lastImportAlbumsRefresh;
    BOOL _importListRefreshPending, _importAlbumsRefreshPending;
}
- (void)resetToDefaultDatabaseIfNecessary;
+ (NSString*)findFirstDicomdirInFolder:(NSString*)startDirectory;
- (void)importURLsThread:(NSDictionary*)parameters;

-(void)setDBWindowTitle;
-(NSArray*)albumsInDatabase;
-(void)removeAlbumObject:(DicomAlbum*)album;

@end

@interface BrowserControllerClassHelper : NSObject
@end

// The folder of the association processes' lock and state files (HorosQueryRetrieveServer.mm, #801).
extern const char* HorosDICOMProcessFolder(void);

@implementation BrowserControllerClassHelper

static NSString* BrowserControllerClassHelperContext = @"BrowserControllerClassHelperContext";

- (id)init {
    if ((self = [super init])) {
        [[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forValuesKey:OsirixCanActivateDefaultDatabaseOnlyDefaultsKey options:NSKeyValueObservingOptionInitial context:BrowserControllerClassHelperContext];
    }
    
    return self;
}

-(void)observeValueForKeyPath:(NSString*)keyPath ofObject:(id)object change:(NSDictionary*)change context:(void*)context
{
    if (context == BrowserControllerClassHelperContext)
    {
        if ([keyPath isEqualToString:valuesKeyPath(OsirixCanActivateDefaultDatabaseOnlyDefaultsKey)])
        {
            if ([NSUserDefaults canActivateAnyLocalDatabase])
                [DicomDatabase setActiveLocalDatabase:[[BrowserController currentBrowser] database]];
        }
    }
}

- (void) dealloc
{
    [[NSUserDefaults standardUserDefaults] removeObserver: self forValuesKey: OsirixCanActivateDefaultDatabaseOnlyDefaultsKey];
    
    [super dealloc];
}

@end

@implementation BrowserController

+(void)initializeBrowserControllerClass
{
    static BrowserControllerClassHelper* helper = nil;
    if (!helper) helper = [[BrowserControllerClassHelper alloc] init];
}

// The toolbar identifiers are in BrowserController+Toolbar.swift since #831;
// these two are also read here.
static NSString*	SearchToolbarItemIdentifier			= @"Search";
static NSString*	OpenKeyImagesAndROIsToolbarItemIdentifier	= @"ROIsAndKeys.tif";

static NSTimeInterval gLastActivity = 0;
static BOOL dontShowOpenSubSeries = NO;
static BOOL gHorizontalHistory = NO;

static NSArray*	statesArray = nil;

static NSNumberFormatter* decimalNumberFormatter = NULL;
static volatile BOOL waitForRunningProcess = NO;

+(void)initialize
{
    decimalNumberFormatter = [[NSNumberFormatter alloc] init];
    [decimalNumberFormatter setNumberStyle:NSNumberFormatterDecimalStyle];
}

- (void) setTableViewRowHeight
{
    int mode = [[NSUserDefaults standardUserDefaults] integerForKey: @"dbFontSize"];
    
    if( mode == -1) //Small
    {
        [albumTable setRowHeight: 13];
        [_sourcesTableView setRowHeight: 13];
        [databaseOutline setRowHeight: 13];
        if( gHorizontalHistory)
            [comparativeTable setRowHeight: 13];
        else
            [comparativeTable setRowHeight: 24];
        [_activityTableView setRowHeight: 34];
        [oMatrix setCellSize: NSMakeSize( 105 * 0.8, 113 * 0.8)];
    }
    
    if( mode == 0) // Regular
    {
        [albumTable setRowHeight: 17];
        [_sourcesTableView setRowHeight: 17];
        [databaseOutline setRowHeight: 17];
        if( gHorizontalHistory)
            [comparativeTable setRowHeight: 16];
        else
            [comparativeTable setRowHeight: 29];
        [_activityTableView setRowHeight: 38];
        [oMatrix setCellSize: NSMakeSize( 105, 113)];
    }
    
    if( mode == 1) // Large
    {
        [albumTable setRowHeight: 25];
        [_sourcesTableView setRowHeight: 25];
        [databaseOutline setRowHeight: 22];
        if( gHorizontalHistory)
            [comparativeTable setRowHeight: 21];
        else
            [comparativeTable setRowHeight: 43];
        [_activityTableView setRowHeight: 48];
        [oMatrix setCellSize: NSMakeSize( 105 * 1.3, 113 * 1.3)];
    }
}

- (float) fontSize: (NSString*) type
{
    int mode = [[NSUserDefaults standardUserDefaults] integerForKey: @"dbFontSize"];
    
    if( mode == -1) //Small
    {
        if( [type isEqualToString: @"threadNameSize"])
            return 9;
        
        if( [type isEqualToString: @"threadNameStatus"])
            return 8;
        
        if( [type isEqualToString: @"comparativeLineSpace"])
            return 12;
        
        if( [type isEqualToString: @"threadCellLineSpace"])
            return 10;
        
        if( [type isEqualToString: @"dbFont"])
            return 10;
        
        if( [type isEqualToString: @"dbComparativeFont"])
            return 9;
        
        if( [type isEqualToString: @"dbAlbumFont"])
            return 9;
        
        if( [type isEqualToString: @"dbSourceFont"])
            return 9;
        
        if( [type isEqualToString: @"dbSeriesFont"])
            return 8;
        
        if( [type isEqualToString: @"dbMatrixFont"])
            return 8;
        
        if( [type isEqualToString: @"dbSmallMatrixFont"])
            return 7.5;
        
        if( [type isEqualToString: @"viewerSmallCellFont"])
            return 7;
        
        if( [type isEqualToString: @"viewerNumberFont"])
            return 11;
    }
    
    if( mode == 0) // Regular
    {
        if( [type isEqualToString: @"threadNameSize"])
            return [NSFont systemFontSizeForControlSize:NSControlSizeSmall];
        
        if( [type isEqualToString: @"threadNameStatus"])
            return [NSFont systemFontSizeForControlSize:NSControlSizeMini];
        
        if( [type isEqualToString: @"comparativeLineSpace"])
            return 14;
        
        if( [type isEqualToString: @"threadCellLineSpace"])
            return 13;
        
        if( [type isEqualToString: @"dbFont"])
            return 12;
        
        if( [type isEqualToString: @"dbComparativeFont"])
            return 11;
        
        if( [type isEqualToString: @"dbAlbumFont"])
            return 11;
        
        if( [type isEqualToString: @"dbSourceFont"])
            return 11;
        
        if( [type isEqualToString: @"dbSeriesFont"])
            return 10;
        
        if( [type isEqualToString: @"dbMatrixFont"])
            return 9;
        
        if( [type isEqualToString: @"dbSmallMatrixFont"])
            return 8.5;
        
        if( [type isEqualToString: @"viewerSmallCellFont"])
            return 7.8;
        
        if( [type isEqualToString: @"viewerNumberFont"])
            return 15;
    }
    
    if( mode == 1) // Large
    {
        if( [type isEqualToString: @"threadNameSize"])
            return 13;
        
        if( [type isEqualToString: @"threadNameStatus"])
            return 11;
        
        if( [type isEqualToString: @"comparativeLineSpace"])
            return 20;
        
        if( [type isEqualToString: @"threadCellLineSpace"])
            return 19;
        
        if( [type isEqualToString: @"dbFont"])
            return 15;
        
        if( [type isEqualToString: @"dbComparativeFont"])
            return 13.5;
        
        if( [type isEqualToString: @"dbAlbumFont"])
            return 14;
        
        if( [type isEqualToString: @"dbSourceFont"])
            return 14;
        
        if( [type isEqualToString: @"dbSeriesFont"])
            return 13;
        
        if( [type isEqualToString: @"dbMatrixFont"])
            return 13;
        
        if( [type isEqualToString: @"dbSmallMatrixFont"])
            return 12;
        
        if( [type isEqualToString: @"viewerSmallCellFont"])
            return 11;
        
        if( [type isEqualToString: @"viewerNumberFont"])
            return 20;
    }
    
    N2LogStackTrace( @"********* fontSize not found for type: %@", type);
    
    return 12;
}

@synthesize database = _database;
@synthesize lastStudyNotOpenedReason;
@synthesize sources = _sourcesArrayController;

@synthesize CDpassword, passwordForExportEncryption, databaseIndexDictionary;
@synthesize TimeFormat, TimeWithSecondsFormat, temporaryNotificationEmail, customTextNotificationEmail;
@synthesize DateTimeWithSecondsFormat, matrixViewArray, oMatrix, testPredicate;
@synthesize databaseOutline, albumTable, comparativePatientUID, distantStudyMessage;
@synthesize bonjourSourcesBox, timeIntervalType, smartAlbumDistantName, selectedAlbumName;
@synthesize bonjourBrowser, pathToEncryptedFile, comparativeStudies, distantTimeIntervalStart, distantTimeIntervalEnd;
@synthesize fetchPredicate = _fetchPredicate, distantSearchType, distantSearchString;
@synthesize filterPredicate = _filterPredicate, filterPredicateDescription = _filterPredicateDescription;
@synthesize pluginManagerController, modalityFilter;

+ (BOOL) tryLock:(id) c during:(NSTimeInterval) sec
{
    if( c == nil)
        return YES;
    
    if( [c lockBeforeDate: [NSDate dateWithTimeIntervalSinceNow: sec]])
    {
        [c unlock];
        return YES;
    }
    
    NSLog( @"******* tryLockDuring failed for this lock: %@ (%f sec)", c, sec);
    
    return NO;
}

+ (BOOL) horizontalHistory { return gHorizontalHistory;}
+ (BrowserController*) currentBrowser { return browserWindow; }
+ (NSArray*) statesArray { return statesArray; }
+ (void) updateActivity
{
    gLastActivity = [NSDate timeIntervalSinceReferenceDate];
}

+ (int) DefaultFolderSizeForDB
{
    if( DefaultFolderSizeForDB == 0)
    {
        DefaultFolderSizeForDB = [[NSUserDefaults standardUserDefaults] integerForKey: @"DefaultFolderSizeForDB"];
        if( DefaultFolderSizeForDB == 0)
        {
            DefaultFolderSizeForDB = 10000;
            [[NSUserDefaults standardUserDefaults] setInteger: DefaultFolderSizeForDB forKey: @"DefaultFolderSizeForDB"];
        }
    }
    
    return DefaultFolderSizeForDB;
}

-(NSArray*)albumsInDatabase
{
    NSArray* r = [NSArray array];
    
    if( _database.managedObjectContext == nil)
        return r;
    
    @try
    {
        @synchronized (self)
        {
            if (_cachedAlbums && _cachedAlbumsContext && _cachedAlbumsContext == _database.managedObjectContext)
                return [[_cachedAlbums copy] autorelease];
        }
        
        r = [_database albums];
        
        @synchronized (self) {
            [_cachedAlbums release];
            _cachedAlbums = [r retain];
            [_cachedAlbumsIDs release];
            _cachedAlbumsIDs = [[_cachedAlbums valueForKey: @"objectID"] retain];
            _cachedAlbumsContext = _database.managedObjectContext;
        }
    }
    @catch (NSException *e) {
        N2LogException(e);
    }
    
    return [[r copy] autorelease];
}

-(NSArray*)albums
{
    return [self albumsInDatabase];
}

static NSConditionLock *threadLock = nil;

- (void) vImageThread: (NSDictionary*) d
{
    NSAutoreleasePool *p = [[NSAutoreleasePool alloc] init];
    
    if( [[d objectForKey: @"what"] isEqualToString: @"FTo16U"])
    {
        vImage_Buffer src = *(vImage_Buffer*) [[d objectForKey: @"src"] pointerValue];
        vImage_Buffer dst = *(vImage_Buffer*) [[d objectForKey: @"dst"] pointerValue];
        
        src.height = dst.height = [[d objectForKey: @"to"] intValue] - [[d objectForKey: @"from"] intValue];
        src.data = (char*) src.data + [[d objectForKey: @"from"] intValue] * src.rowBytes;
        dst.data = (char*) dst.data + [[d objectForKey: @"from"] intValue] * dst.rowBytes;
        
        vImageConvert_FTo16U(	&src,
                             &dst,
                             [[d objectForKey: @"offset"] floatValue],
                             [[d objectForKey: @"scale"] floatValue],
                             kvImageDoNotTile);
    }
    else if( [[d objectForKey: @"what"] isEqualToString: @"16UToF"])
    {
        vImage_Buffer src = *(vImage_Buffer*) [[d objectForKey: @"src"] pointerValue];
        vImage_Buffer dst = *(vImage_Buffer*) [[d objectForKey: @"dst"] pointerValue];
        
        src.height = dst.height = [[d objectForKey: @"to"] intValue] - [[d objectForKey: @"from"] intValue];
        src.data = (char*) src.data + [[d objectForKey: @"from"] intValue] * src.rowBytes;
        dst.data = (char*) dst.data + [[d objectForKey: @"from"] intValue] * dst.rowBytes;
        
        vImageConvert_16UToF(&src,
                             &dst,
                             [[d objectForKey: @"offset"] floatValue],
                             [[d objectForKey: @"scale"] floatValue],
                             kvImageDoNotTile);
    }
    else NSLog( @"****** unknown vImageThread what: %@", [d objectForKey: @"what"]);
    
    [threadLock lock];
    [threadLock unlockWithCondition: [threadLock condition]-1];
    
    [p release];
}


+ (void) multiThreadedImageConvert: (NSString*) what :(vImage_Buffer*) src :(vImage_Buffer *) dst :(float) offset :(float) scale
{
    int mpprocessors = [[NSProcessInfo processInfo] processorCount];
    
    if( threadLock == nil)
        threadLock = [[NSConditionLock alloc] initWithCondition: 0];
    
    [threadLock lockWhenCondition: 0];
    [threadLock unlockWithCondition: mpprocessors];
    
    NSMutableDictionary *baseDict = [NSMutableDictionary dictionary];
    
    [baseDict setObject: [NSValue valueWithPointer: src] forKey: @"src"];
    [baseDict setObject: [NSValue valueWithPointer: dst] forKey: @"dst"];
    
    [baseDict setObject: [NSNumber numberWithFloat: scale] forKey: @"scale"];
    [baseDict setObject: [NSNumber numberWithFloat: offset] forKey: @"offset"];
    
    [baseDict setObject: what forKey: @"what"];
    
    int no2 = src->height;
    
    for( int i = 0; i < mpprocessors; i++)
    {
        NSMutableDictionary *d = [NSMutableDictionary dictionaryWithDictionary: baseDict];
        
        int from = (i * no2) / mpprocessors;
        int to = ((i+1) * no2) / mpprocessors;
        
        [d setObject: [NSNumber numberWithInt: from] forKey: @"from"];
        [d setObject: [NSNumber numberWithInt: to] forKey: @"to"];
        
        [NSThread detachNewThreadSelector: @selector(vImageThread:) toTarget: browserWindow withObject: d];
    }
    
    [threadLock lockWhenCondition: 0];
    [threadLock unlock];
}

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark Add DICOM Database functions

- (NSString*)getNewFileDatabasePath:(NSString*)extension // __deprecated
{
    return [_database uniquePathForNewDataFileWithExtension:extension];
}

- (NSString*)getNewFileDatabasePath:(NSString*)extension dbFolder:(NSString*)dbFolder // __deprecated
{
    return [[DicomDatabase databaseAtPath:dbFolder] uniquePathForNewDataFileWithExtension:extension];
}

- (void) rebuildViewers: (NSMutableArray*) vlToRebuild
{
    // Refresh preview matrix if needed
    for( ViewerController *vc in vlToRebuild)
    {
        if( [vc windowWillClose] == NO && [[vc window] isVisible] && [[vc imageView] mouseDragging] == NO)
        {
            [vc buildMatrixPreview: NO];
        }
    }
}

#pragma deprecated (addFilesToDatabase:)
-(NSArray*)addFilesToDatabase:(NSArray*)newFilesArray // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    if( [NSThread isMainThread] == NO) N2LogStackTrace( @"********* We should be on MAIN thread for accessing objects from _database object");
    return [_database objectsWithIDs:[_database addFilesAtPaths:newFilesArray]];
}

#pragma deprecated (addFilesToDatabase::)
-(NSArray*)addFilesToDatabase:(NSArray*)newFilesArray :(BOOL)onlyDICOM // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    if( [NSThread isMainThread] == NO) N2LogStackTrace( @"********* We should be on MAIN thread for accessing objects from _database object");
    return [_database objectsWithIDs:[_database addFilesAtPaths:newFilesArray postNotifications:YES dicomOnly:onlyDICOM rereadExistingItems:NO]];
}

#pragma deprecated (addFilesToDatabase:onlyDICOM:produceAddedFiles:)
-(NSArray*) addFilesToDatabase:(NSArray*) newFilesArray onlyDICOM:(BOOL) onlyDICOM  produceAddedFiles:(BOOL) produceAddedFiles // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    if( [NSThread isMainThread] == NO) N2LogStackTrace( @"********* We should be on MAIN thread for accessing objects from _database object");
    return [_database objectsWithIDs:[_database addFilesAtPaths:newFilesArray postNotifications:produceAddedFiles dicomOnly:onlyDICOM rereadExistingItems:NO]];
}

#pragma deprecated (addFilesToDatabase:onlyDICOM:produceAddedFiles:parseExistingObject:)
-(NSArray*) addFilesToDatabase:(NSArray*) newFilesArray onlyDICOM:(BOOL) onlyDICOM  produceAddedFiles:(BOOL) produceAddedFiles parseExistingObject:(BOOL) parseExistingObject // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    if( [NSThread isMainThread] == NO) N2LogStackTrace( @"********* We should be on MAIN thread for accessing objects from _database object");
    return [_database objectsWithIDs:[_database addFilesAtPaths:newFilesArray postNotifications:produceAddedFiles dicomOnly:onlyDICOM rereadExistingItems:parseExistingObject]];
}

#pragma deprecated (checkForExistingReport:dbFolder:)
- (void) checkForExistingReport: (NSManagedObject*) study dbFolder: (NSString*) dbFolder
{
    N2LogStackTrace( @"****** deprecated function");
    DicomDatabase* db = [DicomDatabase databaseForContext:study.managedObjectContext];
    [db checkForExistingReportForStudy:study];
}

#pragma mark-

#pragma deprecated
+(NSArray*)addFiles:(NSArray*)newFilesArray toContext:(NSManagedObjectContext*)context toDatabase:(BrowserController*)browserController onlyDICOM:(BOOL)onlyDICOM notifyAddedFiles:(BOOL)notifyAddedFiles parseExistingObject:(BOOL)parseExistingObject dbFolder:(NSString*)dbFolder // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    DicomDatabase* db = [DicomDatabase databaseForContext:context];
    if (!db && browserController) db = [browserController database];
    if (!db && dbFolder) db = [DicomDatabase databaseAtPath:dbFolder];
    if (!db && (context || dbFolder)) db = [[[DicomDatabase alloc] initWithPath:dbFolder context:context] autorelease];
    if (!db) N2LogError(@"couldn't identify database");
    return [db objectsWithIDs:[db addFilesAtPaths:newFilesArray postNotifications:notifyAddedFiles dicomOnly:onlyDICOM rereadExistingItems:parseExistingObject]];
}

#pragma deprecated
+(NSArray*)addFiles:(NSArray*)newFilesArray toContext:(NSManagedObjectContext*)context toDatabase:(BrowserController*)browserController onlyDICOM:(BOOL)onlyDICOM notifyAddedFiles:(BOOL)notifyAddedFiles parseExistingObject:(BOOL)parseExistingObject dbFolder:(NSString*)dbFolder generatedByOsiriX:(BOOL)generatedByOsiriX // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    DicomDatabase* db = [DicomDatabase databaseForContext:context];
    if (!db && browserController) db = [browserController database];
    if (!db && dbFolder) db = [DicomDatabase databaseAtPath:dbFolder];
    if (!db && (context || dbFolder)) db = [[[DicomDatabase alloc] initWithPath:dbFolder context:context] autorelease];
    if (!db) N2LogError(@"couldn't identify database");
    return [db objectsWithIDs:[db addFilesAtPaths:newFilesArray postNotifications:notifyAddedFiles dicomOnly:onlyDICOM rereadExistingItems:parseExistingObject generatedByOsiriX:generatedByOsiriX]];
}

#pragma deprecated
+(NSArray*) addFiles:(NSArray*) newFilesArray toContext: (NSManagedObjectContext*) context toDatabase: (BrowserController*) browserController onlyDICOM: (BOOL) onlyDICOM  notifyAddedFiles: (BOOL) notifyAddedFiles parseExistingObject: (BOOL) parseExistingObject dbFolder: (NSString*) dbFolder generatedByOsiriX: (BOOL) generatedByOsiriX mountedVolume: (BOOL) mountedVolume // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    DicomDatabase* db = [DicomDatabase databaseForContext:context];
    if (!db && browserController) db = [browserController database];
    if (!db && dbFolder) db = [DicomDatabase databaseAtPath:dbFolder];
    if (!db && (context || dbFolder)) db = [[[DicomDatabase alloc] initWithPath:dbFolder context:context] autorelease];
    if (!db) N2LogError(@"couldn't identify database");
    return [db objectsWithIDs:[db addFilesAtPaths:newFilesArray postNotifications:notifyAddedFiles dicomOnly:onlyDICOM rereadExistingItems:parseExistingObject generatedByOsiriX:generatedByOsiriX]];
}

#pragma deprecated
+(NSArray*)addFiles:(NSArray*)newFilesArray toContext:(NSManagedObjectContext*)context onlyDICOM:(BOOL)onlyDICOM  notifyAddedFiles:(BOOL)notifyAddedFiles parseExistingObject:(BOOL)parseExistingObject dbFolder:(NSString*)dbFolder // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    DicomDatabase* db = [DicomDatabase databaseForContext:context];
    if (!db && dbFolder) db = [DicomDatabase databaseAtPath:dbFolder];
    if (!db && (context || dbFolder)) db = [[[DicomDatabase alloc] initWithPath:dbFolder context:context] autorelease];
    if (!db) N2LogError(@"couldn't identify database");
    return [db objectsWithIDs:[db addFilesAtPaths:newFilesArray postNotifications:notifyAddedFiles dicomOnly:onlyDICOM rereadExistingItems:parseExistingObject]];
}

#pragma deprecated
-(NSArray*)subAddFilesToDatabase:(NSArray*)newFilesArray onlyDICOM:(BOOL)onlyDICOM produceAddedFiles:(BOOL)produceAddedFiles parseExistingObject:(BOOL)parseExistingObject context:(NSManagedObjectContext*)context dbFolder:(NSString*)dbFolder // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    DicomDatabase* db = [DicomDatabase databaseForContext:context];
    if (!db && dbFolder) db = [DicomDatabase databaseAtPath:dbFolder];
    if (!db) db = _database;
    return [db objectsWithIDs:[db addFilesAtPaths:newFilesArray postNotifications:produceAddedFiles dicomOnly:onlyDICOM rereadExistingItems:parseExistingObject]];
}

#pragma deprecated
-(NSArray*)addFilesToDatabase:(NSArray*)newFilesArray onlyDICOM:(BOOL)onlyDICOM safeRebuild:(BOOL)safeRebuild produceAddedFiles:(BOOL)produceAddedFiles { // __deprecated // notice: the "safeRebuild" seemed to be already ignored before the DicomDatabase transition
    
    N2LogStackTrace( @"****** deprecated function");
    if( [NSThread isMainThread] == NO) N2LogStackTrace( @"********* We should be on MAIN thread for accessing objects from _database object");
    return [_database objectsWithIDs:[_database addFilesAtPaths:newFilesArray postNotifications:produceAddedFiles dicomOnly:onlyDICOM rereadExistingItems:NO]];
}

#pragma deprecated
-(NSArray*)addFilesToDatabase:(NSArray*)newFilesArray onlyDICOM:(BOOL)onlyDICOM produceAddedFiles:(BOOL)produceAddedFiles parseExistingObject:(BOOL)parseExistingObject context:(NSManagedObjectContext*)context dbFolder:(NSString*)dbFolder // __deprecated
{
    N2LogStackTrace( @"****** deprecated function");
    DicomDatabase* db = [DicomDatabase databaseForContext:context];
    if (!db && dbFolder) db = [DicomDatabase databaseAtPath:dbFolder];
    if (!db) db = _database;
    return [db objectsWithIDs:[db addFilesAtPaths:newFilesArray postNotifications:produceAddedFiles dicomOnly:onlyDICOM rereadExistingItems:parseExistingObject]];
}

#pragma mark-


+ (void) asyncWADOXMLDownloadURL:(NSURL*) url
{
    WADOXML *w = [[[WADOXML alloc] init] autorelease];
    
    [w parseURL: url];
    
    NSThread* t = [[[NSThread alloc] initWithTarget:[[[WADODownload alloc] init] autorelease] selector:@selector(WADODownload:) object: w.getWADOUrls] autorelease];
    t.name = NSLocalizedString( @"WADO Retrieve...", nil);
    t.supportsCancel = YES;
    t.status = [url lastPathComponent];
    [[ThreadsManager defaultManager] addThreadAndStart: t];
}

- (void) asyncWADODownload:(NSString*) filename
{
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    NSMutableArray *urlToDownloads = [NSMutableArray array];
    
    @try
    {
        NSArray *urlsR = [[NSString stringWithContentsOfFile:filename usedEncoding:NULL error:NULL] componentsSeparatedByString: @"\r"];
        NSArray *urlsN = [[NSString stringWithContentsOfFile:filename usedEncoding:NULL error:NULL] componentsSeparatedByString: @"\n"];
        
        if( urlsR.count >= urlsN.count)
        {
            for( NSString *url in urlsR)
            {
                if( url.length)
                    [urlToDownloads addObject: [NSURL URLWithString: url]];
            }
        }
        else
        {
            for( NSString *url in urlsN)
            {
                if( url.length)
                    [urlToDownloads addObject: [NSURL URLWithString: url]];
            }
        }
    }
    @catch ( NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    WADODownload *downloader = [[[WADODownload alloc] init] autorelease];
    [downloader WADODownload: urlToDownloads];
    
    [[NSFileManager defaultManager] removeItemAtPath: filename error: nil];
    
    [pool release];
}

// Expand one archive somewhere only this process can see, then hand the whole
// folder to the import folder under a name nothing else can already hold.
//
// This used to unzip into /tmp/unzip_folder: one fixed, world-visible path,
// removed and recreated each time with every result ignored. On a shared machine
// /tmp is writable by everyone and sticky, so the remove of a directory owned by
// someone else fails and the create then succeeds on *their* directory - and its
// contents were moved into the database. Two archives in one drop, or two copies
// of Horos, used the same path at the same time. And the destination name came
// from a counter that restarts at 1 every launch, so the move failed against a
// folder still waiting to be imported and the expansion was silently lost, to be
// deleted by the next archive.
- (void) expandArchiveIntoIncomingFolder: (NSString*) archive
{
    NSString *staging = [[NSFileManager.defaultManager tmpDirPath] stringByAppendingPathComponent:
                         [@"unzip-" stringByAppendingString: [[NSUUID UUID] UUIDString]]];
    NSError *error = nil;
    
    if( ![NSFileManager.defaultManager createDirectoryAtPath: staging withIntermediateDirectories: YES
                                                  attributes: @{NSFilePosixPermissions: @0700} error: &error])
    {
        NSLog( @"---- import: %@ could not be expanded: no working directory (%@)", [archive lastPathComponent], error.localizedDescription);
        return;
    }
    
    @try
    {
        [self askForZIPPassword: archive destination: staging];
        
        NSString *destination = [self.database.incomingDirPath stringByAppendingPathComponent:
                                 [@"unzip-" stringByAppendingString: [[NSUUID UUID] UUIDString]]];
        
        if( ![NSFileManager.defaultManager moveItemAtPath: staging toPath: destination error: &error])
            NSLog( @"---- import: %@ was expanded but could not be handed to the import folder (%@); nothing was imported from it", [archive lastPathComponent], error.localizedDescription);
    }
    @catch (NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        // Only if the move did not take it; removing the destination would
        // delete the expansion that is now waiting to be imported.
        if( [NSFileManager.defaultManager fileExistsAtPath: staging])
            [NSFileManager.defaultManager removeItemAtPath: staging error: NULL];
    }
}

- (void) addFilesAndFolderToDatabase:(NSArray*) filenames
{
    NSFileManager       *defaultManager = [NSFileManager defaultManager];
    NSMutableArray		*filesArray;
    BOOL				isDirectory = NO;
    
    filesArray = [[[NSMutableArray alloc] initWithCapacity:0] autorelease];
    
    for( NSString *filename in filenames)
    {
        NSAutoreleasePool *pool = [NSAutoreleasePool new];
        
        @try
        {
            if( [[filename lastPathComponent] characterAtIndex: 0] != '.')
            {
                if([defaultManager fileExistsAtPath: filename isDirectory:&isDirectory])     // A directory
                {
                    if( isDirectory && [[filename pathExtension] isEqualToString: @"pages"] == NO && [[filename pathExtension] isEqualToString: @"app"] == NO)
                    {
                        NSString    *pathname;
                        NSString	*folderSkip = nil;
                        NSDirectoryEnumerator *enumer = [[NSFileManager defaultManager] enumeratorAtPath: filename];
                        
                        while (pathname = [enumer nextObject])
                        {
                            NSAutoreleasePool *p = [NSAutoreleasePool new];
                            
                            @try
                            {
                                NSString * itemPath = [filename stringByAppendingPathComponent: pathname];
                                id fileType = [[enumer fileAttributes] objectForKey:NSFileType];
                                
                                if ([fileType isEqual:NSFileTypeRegular])
                                {
                                    BOOL skip = NO;
                                    
                                    if( folderSkip && [pathname length] >= [folderSkip length])
                                        if( [[pathname substringToIndex: [folderSkip length]] isEqualToString: folderSkip])
                                            skip = YES;
                                    
                                    if( skip == NO)
                                    {
                                        folderSkip = nil;
                                        
                                        if( [[itemPath lastPathComponent] characterAtIndex: 0] != '.')
                                        {
                                            if( [[itemPath pathExtension] isEqualToString: @"dcmURLs"])
                                            {
                                                NSThread* t = [[[NSThread alloc] initWithTarget:self selector:@selector(asyncWADODownload:) object: filename] autorelease];
                                                t.name = NSLocalizedString( @"WADO Retrieve...", nil);
                                                t.supportsCancel = YES;
                                                t.status = [itemPath lastPathComponent];
                                                [[ThreadsManager defaultManager] addThreadAndStart: t];
                                            }
                                            else if( [[itemPath pathExtension] isEqualToString: @"zip"] || [[itemPath pathExtension] isEqualToString: @"osirixzip"])
                                                [self expandArchiveIntoIncomingFolder: itemPath];
                                            else if( [[[itemPath lastPathComponent] uppercaseString] isEqualToString:@"DICOMDIR"] || [[[itemPath lastPathComponent] uppercaseString] isEqualToString:@"DICOMDIR."])
                                                [self addDICOMDIR: itemPath : filesArray];
                                            
                                            else [filesArray addObject:itemPath];
                                        }
                                    }
                                }
                                else if( [[pathname pathExtension] isEqualToString:@"app"])
                                {
                                    folderSkip = pathname;
                                }
                            }
                            @catch( NSException *e)
                            {
                                N2LogExceptionWithStackTrace(e/*, @"addFilesAndFolderToDatabase 2"*/);
                            }
                            
                            [p release];
                        }
                    }
                    else    // A file
                    {
                        if( [[filename pathExtension] isEqualToString: @"xml"]) // Is it a WADO xml file? (like used for Weasis)
                        {
                            [BrowserController asyncWADOXMLDownloadURL: [NSURL fileURLWithPath: filename]];
                        }
                        else if( [[filename pathExtension] isEqualToString: @"dcmURLs"])
                        {
                            NSThread* t = [[[NSThread alloc] initWithTarget:self selector:@selector(asyncWADODownload:) object: filename] autorelease];
                            t.name = NSLocalizedString( @"WADO Retrieve...", nil);
                            t.supportsCancel = YES;
                            t.status = [filename lastPathComponent];
                            [[ThreadsManager defaultManager] addThreadAndStart: t];
                        }
                        else if( [[filename pathExtension] isEqualToString: @"zip"] || [[filename pathExtension] isEqualToString: @"osirixzip"])
                            [self expandArchiveIntoIncomingFolder: filename];
                        else if( [[[filename lastPathComponent] uppercaseString] isEqualToString:@"DICOMDIR"] || [[[filename lastPathComponent] uppercaseString] isEqualToString:@"DICOMDIR."])
                            [self addDICOMDIR: filename :filesArray];
                        else if( [[filename pathExtension] isEqualToString: @"app"])
                        {
                        }
                        else [filesArray addObject: filename];
                    }
                }
            }
        }
        @catch (NSException* e)
        {
            N2LogExceptionWithStackTrace(e);
        }
        
        [pool release];
    }
    
    [self copyFilesIntoDatabaseIfNeeded: filesArray options: [NSDictionary dictionaryWithObjectsAndKeys: [[NSUserDefaults standardUserDefaults] objectForKey: @"onlyDICOM"], @"onlyDICOM", [NSNumber numberWithBool: YES], @"async", [NSNumber numberWithBool: YES], @"addToAlbum",  [NSNumber numberWithBool: YES], @"selectStudy", nil]];
}

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark Autorouting functions

- (void) testAutorouting
{
    // Test the routing filters
#ifndef OSIRIX_LIGHT
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"AUTOROUTINGACTIVATED"])
    {
        NSArray	*autoroutingRules = [[NSUserDefaults standardUserDefaults] arrayForKey: @"AUTOROUTINGDICTIONARY"];
        
        NSManagedObjectContext *context = self.database.managedObjectContext;
        
        N2ManagedObjectContextPerformAndWait(context, ^{
        
        // Take a study for the test
        NSFetchRequest	*dbRequest = [[[NSFetchRequest alloc] init] autorelease];
        [dbRequest setEntity: [[self.database.managedObjectModel entitiesByName] objectForKey:@"Study"]];
        [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
        [dbRequest setFetchLimit: 1];
        
        NSError *error = nil;
        NSArray *studiesArray = [context executeFetchRequest:dbRequest error:&error];
        
        if( studiesArray.count > 0)
        {
            NSArray *images = [[[studiesArray objectAtIndex: 0] images] allObjects];
            
            for( NSDictionary *routingRule in autoroutingRules)
            {
                @try
                {
                    if( [[routingRule objectForKey:@"filterType"] intValue] == 0)
                    {
                        NSPredicate *predicate = [self smartAlbumPredicateString: [routingRule objectForKey: @"filter"]];
                        
                        // Test it on the first study...
                        [images filteredArrayUsingPredicate: predicate];
                    }
                }
                
                @catch( NSException *ne)
                {
                    HorosRunAlertPanel( NSLocalizedString(@"Routing Filter Error", nil), NSLocalizedString(@"Syntax error in this routing filter: %@\r\r%@\r\r%@", nil), nil, nil, nil, [routingRule objectForKey:@"name"], [routingRule objectForKey:@"filter"], [ne description]);
                    
                    [ne printStackTrace];
                }
            }
        }
        
        });
    }
#endif
}

- (DicomStudy*) selectedStudy
{
    NSMutableArray *objects = [NSMutableArray array];
    
    (void)[self filesForDatabaseMatrixSelection: objects onlyImages: NO];
    
    DicomImage *im = objects.lastObject;
    
    if( im == nil)
    {
        [self filesForDatabaseOutlineSelection: objects onlyImages: NO];
        im = objects.lastObject;
    }
    return im.series.study;
}

- (void) applyRoutingRule: (id) sender // For manually applying a routing rule, from the DB contextual menu
{
    BOOL matrixThumbnails = NO;
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
    {
        matrixThumbnails = YES;
        NSLog( @"applyRoutingRule from matrix");
    }
    
    NSMutableArray *objects = [NSMutableArray array];
    
    if( matrixThumbnails)
        (void)[self filesForDatabaseMatrixSelection: objects onlyImages: NO];
    else
        [self filesForDatabaseOutlineSelection: objects onlyImages: NO];
    
    if( [sender representedObject]) // Only selected rule
    {
        NSLog( @" Autorouting trigger: %d image(s) sent through one rule by hand, from the database window", (int) objects.count);
        [_database applyRoutingRules: [NSArray arrayWithObject: [sender representedObject]] toImages: objects];
    }
    else // All rules
    {
        NSLog( @" Autorouting trigger: %d image(s) sent through every rule by hand, from the database window", (int) objects.count);
        [_database applyRoutingRules: nil toImages: objects];
    }
}

- (void)addFiles:(NSArray*)images withRule:(NSDictionary*)routingRule // __deprecated
{
    [_database addImages:images toSendQueueForRoutingRule:routingRule];
}

#pragma mark-
#pragma mark Database functions

- (void) regenerateAutoCommentsThread: (NSDictionary*) arrays
{
    // On a private-queue context, on its queue (#966).
    NSManagedObjectContext *context = self.database.privateQueueIndependentContext;
    N2ManagedObjectContextPerformAndWait(context, ^{
        [self regenerateAutoComments: arrays inContext: context];
    });
}

- (void) regenerateAutoComments: (NSDictionary*) arrays inContext: (NSManagedObjectContext*) context
{
    @autoreleasepool
    {
        NSArray *studiesArray = [arrays objectForKey: @"studyArrayIDs"];
        
        NSString *commentField = [[NSUserDefaults standardUserDefaults] stringForKey: @"commentFieldForAutoFill"];
        
        BOOL studyLevel = [[NSUserDefaults standardUserDefaults] boolForKey: @"COMMENTSAUTOFILLStudyLevel"];
        BOOL seriesLevel = [[NSUserDefaults standardUserDefaults] boolForKey: @"COMMENTSAUTOFILLSeriesLevel"];
        BOOL commentsAutoFill = [[NSUserDefaults standardUserDefaults] boolForKey: @"COMMENTSAUTOFILL"];
        
        int x = 0;
        for( NSManagedObjectID *studyID in studiesArray)
        {
            DicomStudy *s = (DicomStudy*) [context objectWithID: studyID];
            
            [s willChangeValueForKey: commentField];
            [s setPrimitiveValue: 0L forKey: commentField];
            [s didChangeValueForKey: commentField];
        }
        
        for( NSManagedObjectID *studyID in studiesArray)
        {
            DicomStudy *s = (DicomStudy*) [context objectWithID: studyID];
            @try
            {
                [s willChangeValueForKey: commentField];
                
                if( studyLevel == YES && seriesLevel == NO && commentsAutoFill == YES)
                {
                    for( DicomSeries *series in s.imageSeries)
                    {
                        if( [DCMAbstractSyntaxUID isImageStorage: series.seriesSOPClassUID] && [DCMAbstractSyntaxUID isPDF: series.seriesSOPClassUID] == NO)
                        {
                            NSManagedObject *o = [[series valueForKey:@"images"] anyObject];
                            
                            @autoreleasepool
                            {
                                DicomFile *dcm = [[DicomFile alloc] init: [o valueForKey:@"completePath"]];
                                
                                if( dcm)
                                {
                                    if( [[dcm elementForKey:@"commentsAutoFill"] length] > [[s valueForKey: commentField] length])
                                        [s setPrimitiveValue: [dcm elementForKey: @"commentsAutoFill"] forKey: commentField];
                                    else
                                        [s setPrimitiveValue: nil forKey: commentField];
                                    
                                    [dcm release];
                                }
                                
                                float p = (float) (x++) / (float) studiesArray.count;
                                [[NSThread currentThread] setProgress: p];
                                
                                if( x % 100 == 0)
                                    [context save: nil];
                            }
                            
                            break;
                        }
                    }
                }
                else
                    [s setPrimitiveValue: 0L forKey: commentField];
            }
            @catch (NSException *exception) {
                N2LogException( exception);
            }
            @finally {
                [s didChangeValueForKey: commentField];
            }
            
            if( [[NSThread currentThread] isCancelled])
                break;
        }
        
        NSArray *seriesArray = [arrays objectForKey: @"seriesArrayIDs"];
        
        int i = 0;
        for( NSManagedObjectID *seriesID in seriesArray)
        {
            @autoreleasepool
            {
                @try
                {
                    DicomSeries *series = (DicomSeries*) [context objectWithID: seriesID];
                    
                    if( [DCMAbstractSyntaxUID isImageStorage: series.seriesSOPClassUID] && [DCMAbstractSyntaxUID isPDF: series.seriesSOPClassUID] == NO)
                    {
                        NSManagedObject *o = [[series valueForKey:@"images"] anyObject];
                        
                        if( commentsAutoFill && seriesLevel)
                        {
                            DicomFile *dcm = [[DicomFile alloc] init: [o valueForKey:@"completePath"]];
                            
                            if( dcm)
                            {
                                if( [dcm elementForKey:@"commentsAutoFill"])
                                {
                                    [series willChangeValueForKey: commentField];
                                    [series setPrimitiveValue: [dcm elementForKey: @"commentsAutoFill"] forKey: commentField];
                                    [series didChangeValueForKey: commentField];
                                    
                                    if( studyLevel)
                                    {
                                        NSManagedObject *study = [series valueForKey: @"study"];
                                        
                                        if( [study valueForKey: commentField] == nil || [[study valueForKey: commentField] isEqualToString:@""])
                                        {
                                            [study willChangeValueForKey: commentField];
                                            [study setPrimitiveValue: [dcm elementForKey: @"commentsAutoFill"] forKey: commentField];
                                            [study didChangeValueForKey: commentField];
                                        }
                                    }
                                }
                                else
                                {
                                    [series willChangeValueForKey: commentField];
                                    [series setPrimitiveValue: 0L forKey: commentField];
                                    [series didChangeValueForKey: commentField];
                                }
                                [dcm release];
                            }
                        }
                        else
                        {
                            [series willChangeValueForKey: commentField];
                            [series setPrimitiveValue: 0L forKey: commentField];
                            [series didChangeValueForKey: commentField];
                        }
                    }
                }
                @catch ( NSException *e)
                {
                    N2LogExceptionWithStackTrace(e);
                }
            }
            
            float p = (float) (i++) / (float) seriesArray.count;
            [[NSThread currentThread] setProgress: p];
            
            if( i % 100 == 0)
                [context save: nil];
            
            if( [[NSThread currentThread] isCancelled])
                break;
        }
        
        [context save: nil];
        
        [self performSelectorOnMainThread: @selector( outlineViewRefresh)  withObject: nil waitUntilDone: NO];
    }
}

- (IBAction) regenerateAutoComments:(id) sender;
{
    if( HorosRunInformationalAlertPanel(	NSLocalizedString(@"Regenerate Auto Comments", nil),
                                     NSLocalizedString(@"Are you sure you want to regenerate the comments field? It will delete the existing comments of studies and series.", nil),
                                     NSLocalizedString(@"OK",nil),
                                     NSLocalizedString(@"Cancel",nil),
                                     nil) == HorosAlertDefaultResponse)
    {
        NSArray *studiesArray = nil;
        
        if( sender == nil) // Apply to all studies
        {
            // Find all studies
            NSFetchRequest	*dbRequest = [[[NSFetchRequest alloc] init] autorelease];
            [dbRequest setResultType: NSManagedObjectIDResultType];
            [dbRequest setEntity: [[self.database.managedObjectModel entitiesByName] objectForKey:@"Study"]];
            [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
            
            NSError *error = nil;
            
            studiesArray = [self.database.managedObjectContext executeFetchRequest:dbRequest error:&error];
        }
        else
        {
            NSMutableArray *selectedStudies = [NSMutableArray array];
            
            NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
            if( [databaseOutline selectedRow] >= 0)
            {
                for( int x = 0; x < [selectedRows count] ; x++)
                {
                    NSUInteger row = 0;
                    if( x == 0) row = [selectedRows firstIndex];
                    else row = [selectedRows indexGreaterThanIndex: row];
                    
                    id object = [databaseOutline itemAtRow: row];
                    
                    if( [object isKindOfClass:[DicomStudy class]])
                        [selectedStudies addObject: object];
                    
                    if( [object isKindOfClass:[DicomSeries class]])
                        [selectedStudies addObject: [object valueForKey: @"study"]];
                }
            }
            
            studiesArray = [selectedStudies valueForKey: @"objectID"];
        }
        
        NSArray *seriesArray = nil;
        
        if( sender == nil) // Apply to all studies
        {
            // Find all series
            NSFetchRequest *dbRequest = [[[NSFetchRequest alloc] init] autorelease];
            [dbRequest setResultType: NSManagedObjectIDResultType];
            [dbRequest setEntity: [[self.database.managedObjectModel entitiesByName] objectForKey:@"Series"]];
            [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
            
            NSError *error = nil;
            
            seriesArray = [self.database.managedObjectContext executeFetchRequest:dbRequest error:&error];
        }
        else
        {
            NSMutableArray *selectedSeries = [NSMutableArray array];
            
            NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
            if( [databaseOutline selectedRow] >= 0)
            {
                for( int x = 0; x < [selectedRows count] ; x++)
                {
                    NSUInteger row = 0;
                    if( x == 0) row = [selectedRows firstIndex];
                    else row = [selectedRows indexGreaterThanIndex: row];
                    
                    NSManagedObject	*object = [databaseOutline itemAtRow: row];
                    
                    if( [object isKindOfClass: [DicomStudy class]])
                        [selectedSeries addObjectsFromArray: [[object valueForKey: @"series"] allObjects]];
                    
                    if( [object isKindOfClass: [DicomSeries class]])
                        [selectedSeries addObject: object];
                }
            }
            
            seriesArray = [selectedSeries valueForKey: @"objectID"];
        }
        
        NSThread *t = nil;
        t = [[[NSThread alloc] initWithTarget: self selector:@selector(regenerateAutoCommentsThread:) object: [NSDictionary dictionaryWithObjectsAndKeys: studiesArray, @"studyArrayIDs", seriesArray, @"seriesArrayIDs", nil]] autorelease];
        
        t.name = NSLocalizedString( @"Regenerate Auto Comments...", nil);
        t.status = N2LocalizedSingularPluralCount( [studiesArray count], NSLocalizedString(@"study", nil), NSLocalizedString(@"studies", nil));
        t.supportsCancel = YES;
        [[ThreadsManager defaultManager] addThreadAndStart: t];
    }
}

- (NSTimeInterval) databaseLastModification // __deprecated
{
    return _database.timeOfLastModification;
}

-(void)setDatabaseLastModification:(NSTimeInterval)t
{
    _database.timeOfLastModification = t;
}

- (NSManagedObjectModel*)managedObjectModel // __deprecated
{
    return self.database.managedObjectModel;
}

- (void)defaultAlbums:(id)sender
{
    [self.database addDefaultAlbums];
    
    @synchronized (self)
    {
        _cachedAlbumsContext = nil;
    }
    
    [self albumsInDatabase];
    
    [self refreshAlbums];
}

// ------------------

- (NSManagedObjectContext*)localManagedObjectContextIndependentContext:(BOOL)independentContext // __deprecated
{
    return [[DicomDatabase activeLocalDatabase] independentContext:independentContext];
}

- (NSManagedObjectContext*)localManagedObjectContext // __deprecated
{
    return [self localManagedObjectContextIndependentContext:NO];
}

// ------------------

- (NSManagedObjectContext*)defaultManagerObjectContext // __deprecated
{
    return [self defaultManagerObjectContextIndependentContext:NO];
}

- (NSManagedObjectContext*)defaultManagerObjectContextIndependentContext:(BOOL)independentContext // __deprecated
{
    return [[DicomDatabase defaultDatabase] independentContext:independentContext];
}

// ------------------

- (NSManagedObjectContext*)managedObjectContext // __deprecated
{
    return [self managedObjectContextIndependentContext:NO];
}

- (NSManagedObjectContext*)managedObjectContextIndependentContext:(BOOL)independentContext // __deprecated
{
    return [self managedObjectContextIndependentContext:independentContext path:_database.baseDirPath];
}

- (NSManagedObjectContext*)managedObjectContextIndependentContext:(BOOL)independentContext path:(NSString*)path // __deprecated
{
    if (!path)
        return nil;
    
    if ([path isEqualToString:_database.baseDirPath])
        return [_database independentContext:independentContext];
    
    N2LogStackTrace( @"******* __deprecated BrowserController managedObjectContextIndependentContext : unknown DicomDatabase");
    
    return [[DicomDatabase existingDatabaseAtPath:path] independentContext:independentContext];
}

// ------------------

- (void) addDICOMDIR:(NSString*) dicomdir :(NSMutableArray*) files
{
    DicomDirParser *parsed = [[DicomDirParser alloc] init: dicomdir];
    
    [parsed parseArray: files];
    
    [parsed release];
}

-(NSArray*) addURLToDatabaseFiles:(NSArray*) URLs
{
    return [self addURLToDatabaseFiles: URLs report: NULL];
}

// A URL import is a HorosURLImportOperation (URLImportOperation.swift, #973):
// it waits for the downloads, follows cancellation, decides by content where
// each payload goes, writes it, hands it to the database it was given and
// composes the result. The browser states the intent and applies the result.
-(NSArray*) addURLToDatabaseFiles:(NSArray*) URLs report: (NSString**) report
{
    // A synchronous caller must supply a background thread. UI and AppleScript
    // use importURLs:completion: so neither blocks the application's event loop.
    if( [NSThread isMainThread])
    {
        if( report) *report = @"Use asynchronous URL import on the main thread.";
        return @[];
    }
    __block DicomDatabase *database = nil;
    dispatch_sync(dispatch_get_main_queue(), ^{ database = [self.database retain]; });
    @try {
        HorosURLImportResult *result = [[[[HorosURLImportOperation alloc] initWithURLs: URLs database: database] autorelease] run];
        if( report) *report = result.report;
        return result.files;
    } @finally { [database release]; }
}

- (NSThread*)importURLs:(NSArray*)URLs completion:(void (^)(NSArray*, NSString*, BOOL))completion
{
    // The database is the browser's now: a switch during the import does not
    // redirect its writes.
    HorosURLImportOperation *operation = [[[HorosURLImportOperation alloc] initWithURLs: [[URLs copy] autorelease] database: self.database] autorelease];
    NSDictionary *parameters = @{ @"operation": operation, @"completion": [[completion copy] autorelease] };
    NSThread *thread = [[[NSThread alloc] initWithTarget: self selector: @selector(importURLsThread:) object: parameters] autorelease];
    thread.name = NSLocalizedString(@"Import URLs", nil);
    thread.supportsCancel = YES;
    [[ThreadsManager defaultManager] addThreadAndStart: thread];
    return thread;
}

- (void)importURLsThread:(NSDictionary*)parameters
{
    @autoreleasepool {
        void (^completion)(NSArray*, NSString*, BOOL) = [parameters objectForKey: @"completion"];
        NSArray *files = @[];
        NSString *report = nil;
        BOOL succeeded = NO;
        @try {
            HorosURLImportResult *result = [(HorosURLImportOperation*) [parameters objectForKey: @"operation"] run];
            files = result.files;
            report = result.report;
            succeeded = result.succeeded;
        } @catch( NSException *exception) {
            report = exception.reason;
        }
        dispatch_async(dispatch_get_main_queue(), ^{ completion(files, report, succeeded); });
    }
}

- (void)addURLToDatabaseEnd: (id)sender
{
    NSURL *url = [NSURL URLWithString: [urlString stringValue]];
    if( [sender tag] == 1 && !url)
    {
        HorosRunCriticalAlertPanel(NSLocalizedString(@"URL Error", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil, NSLocalizedString(@"Invalid URL.", nil));
        return;
    }
    [urlWindow orderOut:sender];
    [urlWindow.sheetParent endSheet:urlWindow returnCode:[sender tag]];
    if( [sender tag] == 1)
    {
        [[NSUserDefaults standardUserDefaults] setObject: [urlString stringValue] forKey: @"LASTURL"];
        [self importURLs: @[url] completion: ^(NSArray *files, NSString *report, BOOL succeeded) {
            if( !succeeded)
                HorosRunCriticalAlertPanel(NSLocalizedString(@"URL Error", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil, report ?: NSLocalizedString(@"Nothing was downloaded.", nil));
        }];
    }
}

- (void)addURLToDatabase: (id)sender
{
    [urlString setStringValue: [[NSUserDefaults standardUserDefaults] stringForKey: @"LASTURL"]];
    [self.window beginSheet:urlWindow completionHandler:nil];
}

- (void) subSelectFilesAndFoldersToAdd: (NSArray*) filenames
{
    if( [filenames count] == 1 && [[[[filenames objectAtIndex: 0] pathExtension] lowercaseString] isEqualToString: @"sql"])
    {
        if (!HorosIsDatabaseFile(filenames.firstObject))
        {
            HorosRunCriticalAlertPanel(NSLocalizedString(@"Cannot Open Database", nil),
                NSLocalizedString(@"This file is not a Isis DICOM Viewer database. It has not been imported or modified.", nil),
                NSLocalizedString(@"OK", nil), nil, nil);
            return;
        }
        [self setDatabase:[DicomDatabase databaseAtPath:filenames.firstObject]];
    }
    else
    {
        NSMutableArray *filenamesWithoutPlugins = [NSMutableArray arrayWithArray: filenames];
        NSMutableArray *pluginsArray = [NSMutableArray array];
        
        for( int i = 0; i < [filenames count]; i++)
        {
            NSString *aPath = [filenames objectAtIndex:i];
            if ([[aPath pathExtension] isEqualToString:@"horosplugin"] || [[aPath pathExtension] isEqualToString:@"osirixplugin"])
                [pluginsArray addObject:aPath];
        }
        
        [filenamesWithoutPlugins removeObjectsInArray: pluginsArray];
        
        [self addFilesAndFolderToDatabase: filenamesWithoutPlugins];
        
        if( [pluginsArray count] > 0)
        {
            [[AppController sharedAppController] installPlugins: pluginsArray];
        }
    }
}

- (IBAction)selectFilesAndFoldersToAdd: (id)sender
{
    NSOpenPanel         *oPanel = [NSOpenPanel openPanel];
    
    [self.window makeKeyAndOrderFront:sender];
    
    [oPanel setAllowsMultipleSelection:YES];
    [oPanel setCanChooseDirectories:YES];
    
    [oPanel beginWithCompletionHandler:^(NSInteger result) {
        if (result != NSModalResponseOK)
            return;
        
        for (NSURL *url in oPanel.URLs) {
            if (![IsisSandboxFileAccess rememberURL:url]) return;
        }
        [self subSelectFilesAndFoldersToAdd:[oPanel.URLs valueForKeyPath:@"path"]];
    }];
}

- (void) checkIfLocalStudyHasMoreOrSameNumberOfImagesOfADistantStudy: (NSArray*) studiesToCheck
{
    if( studiesToCheck == nil) // Take current selected study
    {
        NSManagedObject *item = [databaseOutline itemAtRow: [[databaseOutline selectedRowIndexes] firstIndex]];
        DicomStudy *studySelected = [[item valueForKey: @"type"] isEqualToString: @"Study"] ? item : [item valueForKey: @"study"];
        
        if( studySelected)
            studiesToCheck = [NSArray arrayWithObject: studySelected];
    }
    
#ifndef OSIRIX_LIGHT
    //If PACS On-Demand is activated, check if a local study has more or same number of images of a distant study
    NSMutableArray *patientStudies = [NSMutableArray array];
    
    for( DicomStudy *study in studiesToCheck)
    {
        if( study != (DicomStudy*) [NSNull null] && [patientStudies containsObject: study] == NO && self.comparativePatientUID && [self.comparativePatientUID compare: study.patientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
            [patientStudies addObject: study];
    }
    
    if( patientStudies.count && self.comparativeStudies.count)
    {
        NSMutableArray *copyComparativeStudies = [NSMutableArray arrayWithArray: self.comparativeStudies];
        BOOL modifications = NO;
        
        for( id distantStudy in [NSArray arrayWithArray: copyComparativeStudies])
        {
            if( [distantStudy isKindOfClass: [DCMTKStudyQueryNode class]])
            {
                DicomStudy *localStudy = nil;
                
                for( DicomStudy *localAddedStudy in patientStudies)
                {
                    if( [localAddedStudy.studyInstanceUID isEqualToString: [distantStudy valueForKey: @"studyInstanceUID"]])
                        localStudy = localAddedStudy;
                }
                
                if( localStudy && [[localStudy rawNoFiles] intValue] >= [[distantStudy noFiles] intValue])
                {
                    modifications = YES;
                    [copyComparativeStudies replaceObjectAtIndex: [copyComparativeStudies indexOfObject: distantStudy] withObject: localStudy];
                }
            }
        }
        
        if( modifications)
            [self refreshComparativeStudies: copyComparativeStudies];
    }
#endif
}

-(void)_observeDatabaseAddNotification:(NSNotification*)notification
{
    if( self.database == nil)
        return;
    
    if (![NSThread isMainThread])
        [self performSelectorOnMainThread:@selector(_observeDatabaseAddNotification:) withObject:notification waitUntilDone:NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
    else
    {
        [ROIsAndKeyImagesCache release]; ROIsAndKeyImagesCache = nil;
        [ROIsImagesCache release]; ROIsImagesCache = nil;
        [KeyImagesCache release]; KeyImagesCache = nil;
        
        [lastROIsAndKeyImagesSelectedFiles release]; lastROIsAndKeyImagesSelectedFiles = nil;
        [lastROIsImagesSelectedFiles release]; lastROIsImagesSelectedFiles = nil;
        [lastKeyImagesSelectedFiles release]; lastKeyImagesSelectedFiles = nil;
        
        [self _refreshDatabaseDisplayAfterImport];
        
        [self checkIfLocalStudyHasMoreOrSameNumberOfImagesOfADistantStudy: [[notification.userInfo valueForKey: OsirixAddToDBNotificationImagesArray] valueForKeyPath: @"series.study"]];
    }
}

-(void)_refreshDatabaseDisplay
{
    // A study arriving reloads the outline. Reloading it under someone typing
    // in a comment tears down the field editor: the partial text and the
    // insertion point go, and studies arrive one after another. The timer-driven
    // -refreshDatabase: has always known to stay out of the way; the
    // notification-driven refresh did not, which is the arrival-by-arrival loss
    // of focus the reports describe. The refresh can wait for the edit to end.
    if( databaseOutline && [databaseOutline editedRow] != -1)
    {
        _refreshDeferredWhileEditing = YES;
        return;
    }
    
    _refreshDeferredWhileEditing = NO;
    [self outlineViewRefresh];
    [self refreshAlbums];
}

// An import reports every batch it indexes. Each report refetched every study on
// the main thread and started an album count, both waiting on the importer's
// commits (#697). During an import the list is refreshed at most every
// HorosImportListRefreshInterval seconds and the albums every
// HorosImportAlbumsRefreshInterval; the first report of a quiet period is shown
// at once, and a trailing refresh shows the last batch of a burst.
static const NSTimeInterval HorosImportListRefreshInterval = 5, HorosImportAlbumsRefreshInterval = 20;

-(void)_refreshDatabaseDisplayAfterImport
{
    NSTimeInterval now = [NSDate timeIntervalSinceReferenceDate];
    if( _importListRefreshPending == NO)
    {
        NSTimeInterval wait = _lastImportListRefresh + HorosImportListRefreshInterval - now;
        if( wait <= 0)
            [self _importListRefreshFire];
        else
        {
            _importListRefreshPending = YES;
            [self performSelector:@selector(_importListRefreshFire) withObject:nil afterDelay:wait inModes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
        }
    }
    if( _importAlbumsRefreshPending == NO)
    {
        NSTimeInterval wait = _lastImportAlbumsRefresh + HorosImportAlbumsRefreshInterval - now;
        if( wait <= 0)
            [self _importAlbumsRefreshFire];
        else
        {
            _importAlbumsRefreshPending = YES;
            [self performSelector:@selector(_importAlbumsRefreshFire) withObject:nil afterDelay:wait inModes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
        }
    }
}

-(void)_importListRefreshFire
{
    _importListRefreshPending = NO;
    _lastImportListRefresh = [NSDate timeIntervalSinceReferenceDate];
    // The same deferral as -_refreshDatabaseDisplay: an edit in progress keeps
    // its field editor, and the end of the edit shows what arrived.
    if( databaseOutline && [databaseOutline editedRow] != -1)
    {
        _refreshDeferredWhileEditing = YES;
        return;
    }
    [self outlineViewRefresh];
}

-(void)_importAlbumsRefreshFire
{
    _importAlbumsRefreshPending = NO;
    _lastImportAlbumsRefresh = [NSDate timeIntervalSinceReferenceDate];
    [self refreshAlbums];
}

// Called when an edit finishes, so that what arrived meanwhile is shown as soon
// as showing it can no longer take the editor away.
-(void)_refreshDatabaseDisplayIfDeferred
{
    if( _refreshDeferredWhileEditing == NO)
        return;
    
    if( databaseOutline && [databaseOutline editedRow] != -1)
        return; // still editing; the next end of edit will come back here
    
    [self _refreshDatabaseDisplay];
}

-(void)_observeDatabaseDidChangeContextNotification:(NSNotification*)notification
{
    if (![NSThread isMainThread])
        [self performSelectorOnMainThread:@selector(_observeDatabaseDidChangeContextNotification:) withObject:notification waitUntilDone:NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
    else
    {
        [self outlineViewRefresh];
        [self refreshAlbums];
    }
}

-(void)_observeDatabaseInvalidateAlbumsCacheNotification:(NSNotification*)notification
{
    @synchronized (self)
    {
        _cachedAlbumsContext = nil;
    }
}

-(void)resetToLocalDatabase
{
    [self setDatabase:[DicomDatabase activeLocalDatabase]];
}

+(BOOL)automaticallyNotifiesObserversForKey:(NSString*)key
{
    if ([key isEqualToString:@"database"])
        return NO;
    return [super automaticallyNotifiesObserversForKey:key];
}

-(void) willChangeContext
{
    [self waitForRunningProcesses];
    
    @synchronized( previewPixThumbnails)
    {
        [matrixLoadIconsThread cancel];
        [matrixLoadIconsThread release];
        matrixLoadIconsThread = nil;
    }
    
    self.comparativePatientUID = nil;
    self.comparativeStudies = nil;
    
    @synchronized( smartAlbumDistantArraySync)
    {
        [smartAlbumDistantArray release];
        smartAlbumDistantArray = nil;
    }
    
    [outlineViewArray release];
    outlineViewArray = nil;
    
    [cachedFilesForDatabaseOutlineSelectionSelectedFiles release]; cachedFilesForDatabaseOutlineSelectionSelectedFiles = nil;
    [cachedFilesForDatabaseOutlineSelectionCorrespondingObjects release]; cachedFilesForDatabaseOutlineSelectionCorrespondingObjects = nil;
    [cachedFilesForDatabaseOutlineSelectionTreeObjects release]; cachedFilesForDatabaseOutlineSelectionTreeObjects = nil;
    [cachedFilesForDatabaseOutlineSelectionIndex release]; cachedFilesForDatabaseOutlineSelectionIndex = nil;
    
    [ROIsAndKeyImagesCache release]; ROIsAndKeyImagesCache = nil;
    [ROIsImagesCache release]; ROIsImagesCache = nil;
    [KeyImagesCache release]; KeyImagesCache = nil;
    
    [lastROIsAndKeyImagesSelectedFiles release]; lastROIsAndKeyImagesSelectedFiles = nil;
    [lastROIsImagesSelectedFiles release]; lastROIsImagesSelectedFiles = nil;
    [lastKeyImagesSelectedFiles release]; lastKeyImagesSelectedFiles = nil;
    
    @synchronized (self)
    {
        _cachedAlbumsContext = nil;
    }
    
    [databaseOutline reloadData];
    [albumTable reloadData];
    [comparativeTable reloadData];
}

-(void)setDatabase:(DicomDatabase*)db
{
    [[db retain] autorelease]; // avoid multithreaded release
    
    if( [NSThread isMainThread] == NO)
        N2LogStackTrace( @"setDatabase MUST be performed on MAIN thread");
    
    if (_database != db)
    {
        @try
        {
            [[LogManager currentLogManager] resetLogs];
            
            [self willChangeValueForKey:@"database"];
            
            [self saveLoadAlbumsSortDescriptors];
            
            [self waitForRunningProcesses];
            
            (void)[_database save:nil];
            [_database autorelease]; _database = nil;
            
            [self willChangeContext];
            
            [reportFilesToCheck removeAllObjects];
            
            if (_database)
                [[NSNotificationCenter defaultCenter] removeObserver:self name:nil object:_database];
            
            [self.window display];
            
            [DCMPix purgeCachedDictionaries];
            [DCMView purgeStringTextureCache];
            
            [self resetLogWindowController];
            
            [[AppController sharedAppController] closeAllViewers: self];
            
            @try
            {
                if( [[NSUserDefaults standardUserDefaults] boolForKey: @"clearSearchAndTimeIntervalWhenSelectingAlbum"])
                    [self showEntireDatabase];
            }
            @catch (...) {
            }
            
            _database = [db retain];
            [_database renewManagedObjectContext]; // We want to be sure to use our 'clean' managedobjectcontext (not used in any other threads)
            
            if ([NSUserDefaults canActivateAnyLocalDatabase] && [db isLocal] && ![db isReadOnly])
                [DicomDatabase setActiveLocalDatabase:db];
            if (db)
                [self selectCurrentDatabaseSource];
            
            [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(_observeDatabaseAddNotification:) name:_O2AddToDBAnywayNotification object:_database];
            [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(_observeDatabaseDidChangeContextNotification:) name:OsirixDicomDatabaseDidChangeContextNotification object:_database];
            [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(_observeDatabaseInvalidateAlbumsCacheNotification:) name:O2DatabaseInvalidateAlbumsCacheNotification object:_database];
            
            [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(_newStudiesRefreshComparativeStudies:) name:OsirixAddNewStudiesDBNotification object:_database];
            
            [albumTable selectRowIndexes: [NSIndexSet indexSetWithIndex: 0] byExtendingSelection:NO];
            [self saveLoadAlbumsSortDescriptors];
            
            @synchronized(_albumNoOfStudiesCache)
            {
                [_albumNoOfStudiesCache removeAllObjects];
                [_distantAlbumNoOfStudiesCache removeAllObjects];
            }
            
            N2ManagedObjectContextPerformAndWait(_database.managedObjectContext, ^{
            @try
            {
                [databaseOutline reloadData];
                [albumTable reloadData];
                [comparativeTable reloadData];
                
                [self.window display];
                [self setDBWindowTitle];
                [self refreshPACSOnDemandResults: self];
                
                [self setNetworkLogs];
                [self outlineViewRefresh];
                [self refreshMatrix: self];
                [self refreshAlbums];
                
#ifndef OSIRIX_LIGHT
                if( [QueryController currentQueryController])
                    [[QueryController currentQueryController] refresh: self];
                else if( [QueryController currentAutoQueryController])
                    [[QueryController currentAutoQueryController] refresh: self];
#endif
            }
            @catch (NSException* e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            });
            
            [[LogManager currentLogManager] resetLogs];
        }
        @catch (...)
        {
            @throw;
        }
        @finally
        {
            [self didChangeValueForKey:@"database"];
        }
    }
}

-(void)openDatabaseIn:(NSString*)a Bonjour:(BOOL)isBonjour // __deprecated
{
    [self openDatabaseIn:a Bonjour:isBonjour refresh:NO];
}

-(void)openDatabaseIn:(NSString*)a Bonjour:(BOOL)isBonjour refresh:(BOOL)refresh // __deprecated
{
    if (isBonjour) [NSException raise:NSGenericException format:@"TODO do something smart :P"]; // TODO: hmmm
    DicomDatabase* db = isBonjour? nil : [DicomDatabase databaseAtPath:a];
    [self setDatabase:db];
}


- (void)openDatabaseInBonjour:(NSString*)path __deprecated {
    [self openDatabaseIn:path Bonjour:YES refresh:YES];
}

-(IBAction)openDatabase:(id)sender
{
    NSOpenPanel* oPanel	= [NSOpenPanel openPanel];
#ifdef MACAPPSTORE
    oPanel.canChooseDirectories = YES;
    oPanel.canChooseFiles = NO;
#else
    oPanel.allowedContentTypes = @[[UTType typeWithFilenameExtension:@"sql"]];
#endif
    oPanel.directoryURL = [NSURL fileURLWithPath:_database.sqlFilePath];
    
    [oPanel beginWithCompletionHandler:^(NSInteger result) {
        if (result != NSModalResponseOK)
            return;
        
        if (oPanel.URL && ![_database.sqlFilePath isEqualToString:oPanel.URL.path])
        {
#ifdef MACAPPSTORE
            if ([IsisSandboxFileAccess rememberURL:oPanel.URL]) [self openDatabasePath:oPanel.URL.path];
#else
            [self subSelectFilesAndFoldersToAdd:@[oPanel.URL.path]];
#endif
        }
    }];
}

-(IBAction) createDatabaseFolder:(id) sender
{
    NSOpenPanel		*oPanel		= [NSOpenPanel openPanel];
    
    [oPanel setCanChooseDirectories: YES];
    [oPanel setCanChooseFiles: NO];
    
    if( [sender tag] == 1)
    {
        [oPanel setPrompt: NSLocalizedString(@"Create", nil)];
        [oPanel setTitle: NSLocalizedString(@"Create a Database Folder", nil)];
    }
    else
    {
        [oPanel setPrompt: NSLocalizedString(@"Open", nil)];
        [oPanel setTitle: NSLocalizedString(@"Open a Database Folder", nil)];
    }
    
    oPanel.directoryURL = [NSURL fileURLWithPath:[self.database.baseDirPath stringByDeletingLastPathComponent]];
    
    
    [oPanel beginWithCompletionHandler:^(NSInteger result) {
        if (result != NSModalResponseOK)
            return;
        
        if (![IsisSandboxFileAccess rememberURL:oPanel.URL]) return;
        NSString *location = oPanel.URL.path;
        
#ifndef MACAPPSTORE
        if( [HorosDatabaseLocation isDataDirectoryName: [location lastPathComponent]])
            location = [location stringByDeletingLastPathComponent];
        
        if( [[location lastPathComponent] isEqualToString:@"DATABASE.noindex"] && [HorosDatabaseLocation isDataDirectoryName: [[location stringByDeletingLastPathComponent] lastPathComponent]])
            location = [[location stringByDeletingLastPathComponent] stringByDeletingLastPathComponent];
        
#endif
        [self openDatabasePath: location];
    }];
}

- (void)showEntireDatabase
{
    self.timeIntervalType = 0;
    self.modalityFilter = nil;
    
    [albumTable selectRowIndexes: [NSIndexSet indexSetWithIndex: 0] byExtendingSelection:NO];
    self.searchString = @"";
}

- (void)setDBWindowTitle
{
    [self.window setTitle: _database? [_database name] : @""];
    
    if( [_database.baseDirPath hasPrefix: @"/tmp/"] || [_database.baseDirPath hasPrefix: [[NSFileManager defaultManager] tmpDirPath]] || _database.isLocal == NO)
    {
        if( _database.sourcePath.length)
            [self.window setRepresentedFilename: _database.sourcePath];
        else
            [self.window setRepresentedFilename: @""];
    }else
        [self.window setRepresentedFilename: _database? _database.baseDirPath : @""];
}

- (NSString*)getDatabaseFolderFor: (NSString*)path // __deprecated
{
    BOOL isDirectory;
    
    if( [[NSFileManager defaultManager] fileExistsAtPath: path isDirectory: &isDirectory])
    {
        if( isDirectory == NO)
        {
            // It is a SQL file
            
            if( [[path pathExtension] isEqualToString:@"sql"] == NO) NSLog( @"**** No SQL extension ???");
            
            NSString	*db = [NSString stringWithContentsOfFile: [[path stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"DBFOLDER_LOCATION"]];
            
            if( db == nil)
            {
                NSString	*p = [[path stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"DATABASE.noindex"];
                
                if( [[NSFileManager defaultManager] fileExistsAtPath: p])
                {
                    db = [[path stringByDeletingLastPathComponent] stringByDeletingLastPathComponent];
                }
                else
                {
                    db = [self.database.baseDirPath stringByDeletingLastPathComponent];
                }
            }
            
            return db;
        }
        else
        {
            return path;
        }
    }
    
    return nil;
}

- (NSString*)getDatabaseIndexFileFor: (NSString*)path {  // __deprecated
    BOOL isDirectory;
    
    if( [[NSFileManager defaultManager] fileExistsAtPath: path isDirectory: &isDirectory])
    {
        if( isDirectory)
        {
            // Default SQL file
            NSString	*index = [[HorosDatabaseLocation existingDataDirectoryInFolder: path] stringByAppendingPathComponent:@"Database.sql"];
            
            if( [[NSFileManager defaultManager] fileExistsAtPath: index])
            {
                return index;
            }
            
            return nil;
        }
        else
        {
            return path;
        }
    }
    
    return nil;
}

-(BOOL)isBonjour:(NSManagedObjectContext*)c // __deprecated
{
    DicomDatabase* db = [DicomDatabase databaseForContext:c];
    return ![db isLocal];
}

-(void)loadDatabase:(NSString*)path // __deprecated
{
    [self setDatabase:[DicomDatabase databaseAtPath:path]];
}

-(long)saveDatabase:(NSString*)path context:(NSManagedObjectContext*)context // __deprecated
{
    NSError* err = nil;
    DicomDatabase* database = [DicomDatabase databaseForContext:context];
    (void)[database save:&err];
    return [err code];
}

// TODO: #pragma we know saveDatabase:context: is deprecated
-(long)saveDatabase // __deprecated
{
    return [self saveDatabase:nil context:self.database.managedObjectContext];
}

// TODO: #pragma we know saveDatabase:context: is deprecated
-(long)saveDatabase:(NSString*)path // __deprecated
{
    return [self saveDatabase:path context:self.database.managedObjectContext];
}

-(void)selectStudyWithObjectID:(NSManagedObjectID*)oid
{
    NSManagedObject* s = [self.database objectWithID:oid];
    DicomStudy *study = nil;
    
    if( [s isKindOfClass: [DicomStudy class]])
        study = (DicomStudy*) s;
    
    if( [s isKindOfClass: [DicomSeries class]])
        study = [s valueForKey: @"study"];
    
    if( [s isKindOfClass: [DicomImage class]])
        study = [s valueForKeyPath: @"series.study"];
    
    if( study)
        [self selectThisStudy: study];
}

- (BOOL) refuseToSelectStudy: (NSManagedObject*) study reason: (NSString*) reason
{
    // Every order from outside - XML-RPC, a horos:// link, a plugin - ends at
    // selectThisStudy:, and a NO from here used to be the whole story: no
    // viewer, and nothing said why.
    self.lastStudyNotOpenedReason = reason;
    NSLog( @"%@%@", [HorosStudyNotOpenedReason logPrefix], reason);
    return NO;
}

- (BOOL) selectThisStudy: (NSManagedObject*)study
{
    if( self.database == nil)
        return [self refuseToSelectStudy: study reason: [HorosStudyNotOpenedReason reasonForNoDatabase]];
    
    if( study == nil)
        return [self refuseToSelectStudy: study reason: [HorosStudyNotOpenedReason reasonForNoStudy]];
    
    @try {
        NSManagedObject *item = [databaseOutline itemAtRow: [[databaseOutline selectedRowIndexes] firstIndex]];
        DicomStudy *studySelected = [[item valueForKey: @"type"] isEqualToString: @"Study"] ? item : [item valueForKey: @"study"];
        
        if( [[study valueForKey: @"studyInstanceUID"] isEqualToString: [studySelected valueForKey: @"studyInstanceUID"]])
            return YES;
        
        if( [study isKindOfClass: [DicomStudy class]])
        {
            NSPersistentStoreCoordinator *sps = study.managedObjectContext.persistentStoreCoordinator;
            NSPersistentStoreCoordinator *dps = self.database.managedObjectContext.persistentStoreCoordinator;
            
            if( sps != nil)
            {
                if( sps != dps) // another database is selected, select the destination DB
                {
                    DicomDatabase *db = [DicomDatabase databaseForContext: [study managedObjectContext]];
                    
                    if( db)
                        [self setDatabase: db];
                    else
                        return [self refuseToSelectStudy: study reason: [HorosStudyNotOpenedReason reasonForUnknownDatabase: [study valueForKey: @"studyInstanceUID"]]];
                }
            }
            else return [self refuseToSelectStudy: study reason: [HorosStudyNotOpenedReason reasonForStudyOutsideAnyDatabase: [study valueForKey: @"studyInstanceUID"]]];
        }
        
        [self outlineViewRefresh];
        
        NSUInteger studyIndex = [[outlineViewArray valueForKey: @"studyInstanceUID"] indexOfObject: [study valueForKey: @"studyInstanceUID"]]; // We can have DicomStudy OR DCMTKQueryStudyNode... : search with studyInstanceUID
        NSInteger rowIndex = -1;
        
        if( studyIndex != NSNotFound)
            rowIndex = [databaseOutline rowForItem: [outlineViewArray objectAtIndex: studyIndex]];
        
        if( studyIndex == NSNotFound && (albumTable.selectedRow > 0 || self.searchString.length > 0 || self.timeIntervalType != 0))
        {
            if( [study isKindOfClass: [DicomStudy class]]) // It's a local study: we HAVE to find it ! Select the entire DB
            {
                [self showEntireDatabase];
                [self outlineViewRefresh];
                
                NSUInteger studyIndex = [[outlineViewArray valueForKey: @"studyInstanceUID"] indexOfObject: [study valueForKey: @"studyInstanceUID"]]; // We can have DicomStudy OR DCMTKQueryStudyNode... : search with studyInstanceUID
                if( studyIndex != NSNotFound)
                    rowIndex = [databaseOutline rowForItem: [outlineViewArray objectAtIndex: studyIndex]];
            }
        }
        
        if (rowIndex != -1)
        {
            [databaseOutline selectRowIndexes: [NSIndexSet indexSetWithIndex: rowIndex] byExtendingSelection: NO];
            [databaseOutline scrollRowToVisible: [databaseOutline selectedRow]];
            
            self.lastStudyNotOpenedReason = nil;
            return YES;
        }
        
        // In the list is where a viewer is opened from, so a study that is in
        // the database and not in the list - imported a moment ago, or hidden
        // behind an album, a search or a date filter - stops here.
        return [self refuseToSelectStudy: study reason: [HorosStudyNotOpenedReason reasonForStudyNotListed: [study valueForKey: @"studyInstanceUID"]]];
    }
    @catch ( NSException *e) {
        N2LogException( e);
    }
    
    // Only an exception reaches here, and it does not mean the study is gone.
    return [self refuseToSelectStudy: study reason: [HorosStudyNotOpenedReason reasonForErrorWhileSelecting]];
}

- (void) copyFilesThread: (NSDictionary*) dict
{
    [self.database performSelector:@selector(copyFilesThread:) withObject:dict];
}

- (IBAction) copyToDBFolder: (id) sender
{
    BOOL matrixThumbnails = NO;
    
    if (![_database isLocal]) return;
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
    {
        matrixThumbnails = YES;
        NSLog( @"copyToDBFolder from matrix");
    }
    
    NSMutableArray *objects = [NSMutableArray array];
    NSMutableArray *files;
    
    if( matrixThumbnails)
        files = [self filesForDatabaseMatrixSelection: objects onlyImages: NO];
    else
        files = [self filesForDatabaseOutlineSelection: objects onlyImages: NO];
    
    Wait *splash = [[Wait alloc] initWithString: NSLocalizedString(@"Copying linked files into Database...", nil) :YES];
    
    [splash showWindow:self];
    [[splash progress] setMaxValue:[objects count]];
    [splash setCancel: YES];
    
    //	[_database lock];
    
    [files removeDuplicatedStringsInSyncWithThisArray: objects];
    
    @try
    {
        for( NSManagedObject *im in objects)
        {
            if( [[im valueForKey: @"inDatabaseFolder"] boolValue] == NO)
            {
                NSString *srcPath = [im valueForKey:@"completePath"];
                NSString *extension = [srcPath pathExtension];
                
                if( [[im valueForKey: @"fileType"] hasPrefix: @"DICOM"])
                    extension = @"dcm";
                
                if( [extension isEqualToString:@""])
                    extension = @"dcm";
                
                NSString *dstPath = [self.database uniquePathForNewDataFileWithExtension:extension];
                
                if( [[NSFileManager defaultManager] copyItemAtPath:srcPath toPath:dstPath error:NULL])
                {
                    [[im valueForKey:@"series"] setValue: [NSNumber numberWithBool: NO] forKey:@"mountedVolume"];
                    
                    for( NSManagedObject *c in [[im valueForKeyPath: @"series.images"] allObjects]) // For multi frame files
                    {
                        if( [[c valueForKey:@"completePath"] isEqualToString: srcPath])
                        {
                            [c setValue: [NSNumber numberWithBool: YES] forKey:@"inDatabaseFolder"];
                            [c setValue: [dstPath lastPathComponent] forKey:@"path"];
                            [c setValue: [NSNumber numberWithBool: NO] forKey:@"mountedVolume"];
                        }
                    }
                }
            }
            
            [splash incrementBy:1];
            
            if( [splash aborted])
                break;
        }
    }
    @catch ( NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        //		[_database unlock];
    }
    [splash close];
    [splash autorelease];
}

- (void) copyFilesIntoDatabaseIfNeeded: (NSMutableArray*) filesInput options: (NSDictionary*) options
{
    if (![_database isLocal]) return;
    if( [filesInput count] == 0) return;
    
    BOOL COPYDATABASE = [[NSUserDefaults standardUserDefaults] boolForKey: @"COPYDATABASE"];
    int COPYDATABASEMODE = [[NSUserDefaults standardUserDefaults] integerForKey: @"COPYDATABASEMODE"];
    
    if( [options objectForKey: @"COPYDATABASE"])
        COPYDATABASE = [[options objectForKey: @"COPYDATABASE"] boolValue];
    
    if( [options objectForKey: @"COPYDATABASEMODE"])
        COPYDATABASEMODE = [[options objectForKey: @"COPYDATABASEMODE"] integerValue];
    
    
    NSMutableArray *newFilesToCopyList = [NSMutableArray arrayWithCapacity: [filesInput count]];
    NSString *INpath = [_database dataDirPath];
    
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    for( NSString *file in filesInput)
    {
        if( [[file commonPrefixWithString: INpath options: NSLiteralSearch] isEqualToString:INpath] == NO)
            [newFilesToCopyList addObject: file];
    }
    [pool release];
    
    BOOL copyFiles = NO;
    
    if( COPYDATABASE && [newFilesToCopyList count])
    {
        copyFiles = YES;
        
        switch (COPYDATABASEMODE)
        {
            case always:
                break;
                
            case notMainDrive:
            {
                // "/Volumes/<name>/..." is what a file on anything but the boot
                // volume looks like. A path with nothing after its root has no
                // component 1 to ask about, and asking anyway would be an
                // out-of-bounds read.
                NSArray *pathFilesComponent = [[filesInput objectAtIndex:0] pathComponents];
                
                if( pathFilesComponent.count > 1 && [[[pathFilesComponent objectAtIndex: 1] uppercaseString] isEqualToString:@"VOLUMES"])
                    NSLog(@"not the main drive!");
                else
                    copyFiles = NO;
            }
                break;
                
            case cdOnly:
            {
                NSLog( @"%@", [filesInput objectAtIndex:0]);
                
                if( [BrowserController isItCD: [filesInput objectAtIndex:0]] == NO)
                    copyFiles = NO;
            }
                break;
                
            case ask:
                switch (HorosRunInformationalAlertPanel(
                                                     NSLocalizedString(@"Isis DICOM Viewer Database", nil),
                                                     NSLocalizedString(@"Should I copy these files in Isis DICOM Viewer Database folder, or only copy links to these files?", nil),
                                                     NSLocalizedString(@"Copy Files", nil),
                                                     NSLocalizedString(@"Cancel", nil),
                                                     NSLocalizedString(@"Copy Links", nil)))
            {
                case HorosAlertDefaultResponse:
                    break;
                    
                case HorosAlertOtherResponse:
                    copyFiles = NO;
                    break;
                    
                case HorosAlertAlternateResponse:
                    [filesInput removeAllObjects];		// zero the array before it is returned.
                    return;
                    break;
            }
                break;
        }
    }
    
    NSMutableArray *filesOutput = [NSMutableArray array];
    
    if( copyFiles)
    {
        NSString *OUTpath = [_database dataDirPath];
        
        [[NSFileManager defaultManager] confirmNoIndexDirectoryAtPath:OUTpath];
        
        if( [[options objectForKey: @"async"] boolValue])
        {
            NSMutableDictionary *dict = [NSMutableDictionary dictionaryWithObjectsAndKeys: filesInput, @"filesInput", [NSNumber numberWithBool: YES], @"copyFiles", [NSNumber numberWithBool: [[options objectForKey: @"mountedVolume"] boolValue]], @"mountedVolume", nil];
            [dict addEntriesFromDictionary: options];
            
            // -copyFilesThread: indexes on a private-queue context of its own (#965).
            NSThread *t = [[[NSThread alloc] initWithTarget:_database selector:@selector(copyFilesThread:) object: dict] autorelease];
            
            if( [[options objectForKey: @"mountedVolume"] boolValue]) t.name = NSLocalizedString( @"Copying and indexing files from CD/DVD...", nil);
            else t.name = NSLocalizedString( @"Copying and indexing files...", nil);
            t.status = N2LocalizedSingularPluralCount( [filesInput count], NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
            t.supportsCancel = YES;
            [[ThreadsManager defaultManager] addThreadAndStart: t];
        }
        else
        {
            Wait *splash = [[Wait alloc] initWithString: NSLocalizedString(@"Copying into Database...", nil)];
            
            [splash showWindow:self];
            [[splash progress] setMaxValue:[filesInput count]];
            [splash setCancel: YES];
            
            for( NSString *srcPath in filesInput)
            {
                NSAutoreleasePool   *pool = [[NSAutoreleasePool alloc] init];
                
                NSString *extension = [srcPath pathExtension];
                
                @try
                {
                    if( [[[srcPath stringByDeletingLastPathComponent] stringByDeletingLastPathComponent] isEqualToString:INpath] == NO)
                    {
                        DicomFile *curFile = [[DicomFile alloc] init: srcPath];
                        
                        if( curFile)
                        {
                            if( [[[curFile dicomElements] objectForKey: @"fileType"] hasPrefix: @"DICOM"])
                                extension = @"dcm";
                            
                            if( [extension isEqualToString:@""])
                                extension = @"dcm";
                            
                            if( [extension length] > 4 || [extension length] < 3)
                                extension = @"dcm";
                            
                            NSString *dstPath = [self.database uniquePathForNewDataFileWithExtension:extension];
                            
                            if( [[NSFileManager defaultManager] copyItemAtPath:srcPath toPath:dstPath error:NULL] == YES)
                            {
                                [filesOutput addObject:dstPath];
                            }
                            
                            if( [extension isEqualToString:@"hdr"])		// ANALYZE -> COPY IMG
                            {
                                [[NSFileManager defaultManager] copyItemAtPath:[[srcPath stringByDeletingPathExtension] stringByAppendingPathExtension:@"img"] toPath:[[dstPath stringByDeletingPathExtension] stringByAppendingPathExtension:@"img"] error:NULL];
                            }
                            
                            [curFile release];
                            curFile = nil;
                        }
                        else NSLog( @"**** DicomFile *curFile = nil");
                    }
                }
                @catch (NSException * e)
                {
                    N2LogExceptionWithStackTrace(e);
                }
                @finally {
                    [pool release];
                }
                [splash incrementBy:1];
                
                if( [splash aborted])
                    break;
            }
            
            [splash close];
            [splash autorelease];
        }
    }
    else
    {
        NSMutableDictionary *dict = [NSMutableDictionary dictionaryWithObjectsAndKeys: filesInput, @"filesInput", [NSNumber numberWithBool: NO], @"copyFiles", [NSNumber numberWithBool: [[options objectForKey: @"mountedVolume"] boolValue]], @"mountedVolume", nil];
        
        
        [dict addEntriesFromDictionary: options];
        
        NSThread *t = [[[NSThread alloc] initWithTarget:_database selector:@selector(copyFilesThread:) object: dict] autorelease];
        
        if( [[options objectForKey: @"mountedVolume"] boolValue]) t.name = NSLocalizedString( @"Indexing files from CD/DVD...", nil);
        else t.name = NSLocalizedString( @"Indexing files...", nil);
        t.status = N2LocalizedSingularPluralCount( [filesInput count], NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
        t.supportsCancel = YES;
        [[ThreadsManager defaultManager] addThreadAndStart: t];
        
        filesOutput = filesInput;
    }
    
    return;
}

-(void)rebuildDatabaseThread:(NSArray*)io
{
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
    @try
    {
        if( self.database != nil)
            NSLog( @"****** WARNING we should not be here if self.database != nil");
        
        DicomDatabase* database = [io objectAtIndex:0];
        BOOL complete = [[io objectAtIndex:1] boolValue];
        // On a private-queue database; -rebuild: works on its context's queue (#966).
        [database.privateQueueIndependentDatabase rebuild:complete];
        [self performSelectorOnMainThread:@selector(setDatabase:) withObject:database waitUntilDone:NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [pool release];
    }
}

-(NSThread*)initiateRebuildDatabase:(BOOL)complete
{
    DicomDatabase* database = [[self.database retain] autorelease];
    
    [self setDatabase:nil];
    
    NSArray* io = [NSMutableArray arrayWithObjects: database, [NSNumber numberWithBool:complete], nil];
    
    NSThread* thread = [[NSThread alloc] initWithTarget:self selector:@selector(rebuildDatabaseThread:) object:io];
    thread.name = NSLocalizedString(@"Rebuilding database...", nil);
    
    (void)[thread startModalForWindow:self.window];
    [thread start];
    
    return [thread autorelease];
}

- (IBAction)endReBuildDatabase:(id)sender
{
    [rebuildWindow.sheetParent endSheet:rebuildWindow];
    [rebuildWindow orderOut: self];
    
    if ([sender tag])
    {
        for (NSThread* t in [[ThreadsManager defaultManager] threads])
            [t cancel];
        
        [self waitForRunningProcesses];
        
        NSTimeInterval t = [NSDate timeIntervalSinceReferenceDate];
        while ([[[ThreadsManager defaultManager] threads] count] && [NSDate timeIntervalSinceReferenceDate]-t < 10) { // give declared background threads 10 secs to cancel
            for (NSThread* thread in [[ThreadsManager defaultManager] threads])
                if (![thread isCancelled])
                    [thread cancel];
            [NSThread sleepForTimeInterval:0.05];
        }
        
        switch ([rebuildType selectedTag])
        {
            case 0:
                [self initiateRebuildDatabase:YES];
                break;
                
            case 1:
                [self initiateRebuildDatabase:NO];
                break;
        }
    }
}

- (IBAction) ReBuildDatabaseSheet: (id)sender
{
    if (![_database rebuildAllowed])
        [NSException raise:NSGenericException format:@"Current database rebuild not allowed, this shouldn't be executed."];
    
    long totalFiles = 0;
    NSString	*aPath = [_database dataDirPath];
    NSArray	*dirContent = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:aPath error:NULL];
    for(NSString *name in dirContent)
    {
        NSString * itemPath = [aPath stringByAppendingPathComponent: name];
        totalFiles += [[[[NSFileManager defaultManager] attributesOfItemAtPath:itemPath error:NULL] objectForKey: NSFileReferenceCount] intValue];
    }
    
    [noOfFilesToRebuild setIntValue: totalFiles];
    
    long durationFor1000 = 9;
    
    long totalSeconds = totalFiles * durationFor1000 / 1000;
    [estimatedTime setStringValue:[NSString timeString:totalSeconds maxUnits:2]];
    
    [[AppController sharedAppController] closeAllViewers: self];
    
    [self.window beginSheet:rebuildWindow completionHandler:nil];
}

-(void)rebuildSqlThread:(DicomDatabase*)database
{
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
    @try
    {
        [database rebuildSqlFile];
        [self performSelectorOnMainThread:@selector(setDatabase:) withObject:database waitUntilDone:NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [pool release];
    }
}

-(NSThread*)initiateRebuildSql
{
    DicomDatabase* database = [[self.database retain] autorelease];
    [self setDatabase:nil];
    [self outlineViewRefresh];
    
    NSThread* thread = [[NSThread alloc] initWithTarget:self selector:@selector(rebuildSqlThread:) object:database];
    thread.name = NSLocalizedString(@"Rebuilding database index...", nil);
    
    [thread start];
    (void)[thread startModalForWindow:self.window];
    
    return [thread autorelease];
}

-(void)_rebuildSqlSheetDidEnd:(NSWindow*)sheet returnCode:(NSInteger)returnCode contextInfo:(void*)contextInfo
{
    [sheet.sheetParent endSheet:sheet];
    [sheet orderOut:self];
    if (returnCode == HorosAlertDefaultResponse)
        [self initiateRebuildSql];
}

-(IBAction)rebuildSQLFile:(id)sender
{
    if (![_database rebuildAllowed])
        [NSException raise:NSGenericException format:@"Current database rebuild not allowed, this shouldn't be executed."];
    NSAlert *alert = [[[NSAlert alloc] init] autorelease];
    alert.alertStyle = NSAlertStyleInformational;
    alert.informativeText = NSLocalizedString(@"Are you sure you want to rebuild this database's SQL index? This operation can take several minutes.", nil);
    [alert addButtonWithTitle:NSLocalizedString(@"OK", nil)];
    [alert addButtonWithTitle:NSLocalizedString(@"Cancel", nil)];
    [alert beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
        if (response == NSAlertFirstButtonReturn) [self initiateRebuildSql];
    }];
}

static NSMenu *CleanupPreviewMenuContainingAction(NSMenu *menu, SEL action)
{
    for (NSMenuItem *item in menu.itemArray) {
        if (item.action == action) return menu;
        NSMenu *found = item.submenu ? CleanupPreviewMenuContainingAction(item.submenu, action) : nil;
        if (found) return found;
    }
    return nil;
}

+ (void)installAutomaticCleanupPreviewMenu
{
    if (CleanupPreviewMenuContainingAction(NSApp.mainMenu, @selector(previewAutomaticCleanup:))) return;
    NSMenu *menu = CleanupPreviewMenuContainingAction(NSApp.mainMenu, @selector(ReBuildDatabaseSheet:));
    if (!menu) { NSLog(@"Cleanup preview: database maintenance menu unavailable"); return; }
    NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Preview Automatic Cleanup...", nil)
        action:@selector(previewAutomaticCleanup:) keyEquivalent:@""] autorelease];
    item.target = [BrowserController currentBrowser];
    [menu addItem:[NSMenuItem separatorItem]];
    [menu addItem:item];
}

static OSStatus HorosNumbersAutomationStatus(void)
{
    for (NSString *identifier in @[@"com.apple.Numbers", @"com.apple.iWork.Numbers"]) {
        NSAppleEventDescriptor *target = [NSAppleEventDescriptor descriptorWithBundleIdentifier:identifier];
        if (target.aeDesc == NULL) continue;
        return AEDeterminePermissionToAutomateTarget(target.aeDesc, typeWildCard, typeWildCard, false);
    }
    return -10814;
}

+ (void)installSurgicalProcedureImportMenu
{
    NSMenu *menu = CleanupPreviewMenuContainingAction(NSApp.mainMenu, @selector(importRawData:));
    if (!menu)
        menu = CleanupPreviewMenuContainingAction(NSApp.mainMenu, @selector(ReBuildDatabaseSheet:));
    if (!menu) { NSLog(@"Surgical procedure import: File menu unavailable"); return; }
    BOOL importInstalled = CleanupPreviewMenuContainingAction(NSApp.mainMenu, @selector(importSurgicalProcedureLog:)) != nil;
    BOOL timelineInstalled = CleanupPreviewMenuContainingAction(NSApp.mainMenu, @selector(showSurgicalProcedureTimeline:)) != nil;
    if (importInstalled && timelineInstalled) return;
    if (importInstalled == NO) {
        NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Import Surgical Procedure Log...", nil)
            action:@selector(importSurgicalProcedureLog:) keyEquivalent:@""] autorelease];
        item.target = [BrowserController currentBrowser];
        [menu addItem:[NSMenuItem separatorItem]];
        [menu addItem:item];
    }
    if (timelineInstalled == NO) {
        NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Surgical Procedure Timeline...", nil)
            action:@selector(showSurgicalProcedureTimeline:) keyEquivalent:@""] autorelease];
        item.target = [BrowserController currentBrowser];
        [menu addItem:item];
    }
}

- (IBAction)importSurgicalProcedureLog:(id)sender
{
    DicomDatabase *database = self.database;
    if (!database) return;

    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.allowsMultipleSelection = NO;
    panel.canChooseDirectories = NO;
    panel.allowedContentTypes = @[[UTType typeWithFilenameExtension:@"csv"], [UTType typeWithFilenameExtension:@"txt"], [UTType typeWithFilenameExtension:@"numbers"]];
    panel.message = NSLocalizedString(@"Choose a CSV surgical log. Numbers documents can be imported when Numbers is installed and Automation is allowed.", nil);
    if ([panel runModal] != NSModalResponseOK || panel.URL.path.length == 0) {
        HorosRunInformationalAlertPanel(NSLocalizedString(@"Surgical Procedure Log", nil),
            @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"Preview cancelled. The database was not changed.", nil));
        return;
    }

    BOOL numbersAvailable = [NSWorkspace.sharedWorkspace URLForApplicationWithBundleIdentifier:@"com.apple.Numbers"] != nil
        || [NSWorkspace.sharedWorkspace URLForApplicationWithBundleIdentifier:@"com.apple.iWork.Numbers"] != nil;
    NSDictionary *diagnosis = [HorosSurgicalProcedureImport diagnoseSourceAtPath:panel.URL.path
        numbersAvailable:numbersAvailable
        automationStatus:HorosNumbersAutomationStatus()];
    if ([diagnosis[@"kind"] isEqualToString:@"csv"] == NO) {
        NSString *message = diagnosis[@"message"];
        if (message.length == 0)
            message = NSLocalizedString(@"The selected file is not a CSV surgical log.", nil);
        HorosRunInformationalAlertPanel(NSLocalizedString(@"Surgical Procedure Log", nil),
            @"%@", NSLocalizedString(@"OK", nil), nil, nil, message);
        return;
    }

    NSMutableArray *patients = [NSMutableArray array];
    NSMutableArray *existing = [NSMutableArray array];
    NSArray *studies = [database objectsForEntity:database.studyEntity predicate:nil error:NULL];
    for (DicomStudy *study in studies) {
        NSMutableDictionary *patient = [NSMutableDictionary dictionaryWithDictionary:@{
            @"name": study.name ?: @"",
            @"patientID": study.patientID ?: @"",
            @"patientUID": study.patientUID ?: @"",
            @"studyInstanceUID": study.studyInstanceUID ?: @"",
        }];
        if (study.dateOfBirth)
            patient[@"dateOfBirth"] = study.dateOfBirth;
        [patients addObject:patient];
        for (DicomSeries *series in study.series) {
            if ([series.seriesDescription isEqualToString:[HorosSurgicalProcedureImport surgicalSeriesDescription]] == NO)
                continue;
            for (NSString *path in series.paths)
                [existing addObject:path];
        }
    }

    HorosSurgicalProcedureImportSession *session = [[[HorosSurgicalProcedureImportSession alloc] init] autorelease];
    NSError *error = nil;
    if ([session prepareCSVAtPath:panel.URL.path patients:patients existingPaths:existing error:&error] == NO) {
        HorosRunCriticalAlertPanel(NSLocalizedString(@"Surgical Procedure Log", nil),
            @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            error.localizedDescription ?: NSLocalizedString(@"The surgical log could not be read.", nil));
        return;
    }
    if (session.changeCount == 0) {
        HorosRunInformationalAlertPanel(NSLocalizedString(@"Surgical Procedure Log", nil),
            @"%@\n%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"No matching surgical procedure records to import.", nil),
            session.summary);
        return;
    }

    NSString *prompt = [NSString stringWithFormat:NSLocalizedString(@"Import %ld surgical procedure SR record(s)? Review and skipped rows will not be written.", nil), (long)session.changeCount];
    if (HorosRunInformationalAlertPanel(NSLocalizedString(@"Surgical Procedure Log", nil),
            @"%@\n%@", NSLocalizedString(@"Import", nil), NSLocalizedString(@"Cancel", nil), nil,
            prompt, session.summary) != HorosAlertDefaultResponse) {
        HorosRunInformationalAlertPanel(NSLocalizedString(@"Surgical Procedure Log", nil),
            @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"Preview cancelled. The database was not changed.", nil));
        return;
    }

    NSString *directory = [NSTemporaryDirectory() stringByAppendingPathComponent:[[NSUUID UUID] UUIDString]];
    NSArray *written = [session commitToDirectory:directory error:&error];
    if (written.count == 0) {
        HorosRunCriticalAlertPanel(NSLocalizedString(@"Surgical Procedure Log", nil),
            NSLocalizedString(@"The surgical procedure records could not be written: %@", nil),
            NSLocalizedString(@"OK", nil), nil, nil,
            error.localizedDescription ?: @"");
        return;
    }
    [database addFilesAtPaths:written postNotifications:YES dicomOnly:YES rereadExistingItems:YES];
}

- (NSArray *)surgicalProcedureTimelineEvents
{
    DicomDatabase *database = self.database;
    if (!database) return @[];
    NSMutableArray *paths = [NSMutableArray array];
    NSArray *studies = [database objectsForEntity:database.studyEntity predicate:nil error:NULL];
    for (DicomStudy *study in studies) {
        for (DicomSeries *series in study.series) {
            if ([series.seriesDescription isEqualToString:[HorosSurgicalProcedureImport surgicalSeriesDescription]] == NO)
                continue;
            for (NSString *path in series.paths)
                [paths addObject:path];
        }
    }
    return [HorosSurgicalProcedureImport timelineEventsFromSRPaths:paths];
}

- (IBAction)showSurgicalProcedureTimeline:(id)sender
{
    NSArray *events = [self surgicalProcedureTimelineEvents];
    if (events.count == 0) {
        HorosRunInformationalAlertPanel(NSLocalizedString(@"Surgical Procedure Timeline", nil),
            @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"No surgical procedure records are in this database.", nil));
        return;
    }
    NSMutableString *body = [NSMutableString string];
    for (NSDictionary *event in events) {
        [body appendFormat:@"%@\t%@\t%@\n",
            event[@"displayModality"] ?: @"SURG",
            event[@"operation"] ?: @"",
            event[@"diagnosis"] ?: @""];
    }
    HorosRunInformationalAlertPanel(NSLocalizedString(@"Surgical Procedure Timeline", nil),
        @"%@", NSLocalizedString(@"OK", nil), nil, nil, body);
}

- (IBAction)previewAutomaticCleanup:(id)sender
{
    static BOOL loading = NO;
    if (loading) return;
    DicomDatabase *database = self.database;
    if (!database) return;
    loading = YES;
    [AutoCleanupPreview beginLoadingWithTarget:self action:@selector(previewAutomaticCleanup:)];
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
        @autoreleasepool {
            NSDictionary *snapshot;
            @try {
                // Read on a private-queue context, on its queue (#965).
                DicomDatabase *reader = database.privateQueueIndependentDatabase;
                __block NSDictionary *read = nil;
                [reader performBlockAndWait:^{ read = [[reader automaticCleanupPreview] retain]; }];
                snapshot = [read autorelease];
            }
            @catch (NSException *exception) {
                snapshot = @{ @"summary": NSLocalizedString(@"The database could not be read. No files were changed.", nil), @"rows": @[], @"error": @YES };
            }
            dispatch_async(dispatch_get_main_queue(), ^{
                [AutoCleanupPreview displayWithSnapshot:snapshot];
                loading = NO;
            });
        }
    });
}

- (void) autoCleanDatabaseDate: (id)sender // __deprecated
{
    [_database cleanOldStuff];
}

+ (BOOL) isHardDiskFull // __deprecated
{
    return [[DicomDatabase activeLocalDatabase] isFileSystemFreeSizeLimitReached];
}

- (void) autoCleanDatabaseFreeSpaceWarning: (NSString*) message
{
    HorosRunCriticalAlertPanel( NSLocalizedString(@"Warning", nil),  @"%@", NSLocalizedString(@"OK",nil), nil, nil, message);
}

- (void) autoCleanDatabaseFreeSpace: (id)sender // __deprecated
{
    [_database initiateCleanUnlessAlreadyCleaning];
}

#pragma mark-
#pragma mark Web Portal Database // deprecated, use WebPortal.defaultWebPortal

-(long)saveUserDatabase // __deprecated
{
#ifndef OSIRIX_LIGHT
    [[[WebPortal defaultWebPortal] database] save:NULL];
#endif
    return 0;
}

-(NSManagedObjectModel*)userManagedObjectModel // __deprecated
{
#ifndef OSIRIX_LIGHT
    return [[[WebPortal defaultWebPortal] database] managedObjectModel];
#else
    return NULL;
#endif
}

-(NSManagedObjectContext*)userManagedObjectContext // __deprecated
{
#ifndef OSIRIX_LIGHT
    return [[[WebPortal defaultWebPortal] database] managedObjectContext];
#else
    return NULL;
#endif
}

-(WebPortalUser*)userWithName:(NSString*)name // __deprecated
{
#ifndef OSIRIX_LIGHT
    return [[[WebPortal defaultWebPortal] database] userWithName:name];
#else
    return NULL;
#endif
}


//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark OutlineView Search & Time Interval Functions

- (IBAction)search: (id)sender
{
    [self outlineViewRefresh];
    [databaseOutline scrollRowToVisible: [databaseOutline selectedRow]];
}

- (IBAction)setSearchType: (id)sender
{
    if( searchType == 0 && [[NSUserDefaults standardUserDefaults] boolForKey: @"HIDEPATIENTNAME"])
        [searchField setTextColor: [NSColor controlBackgroundColor]];
    else
        [searchField setTextColor: [NSColor controlTextColor]];

    for( long i = 0; i < [[sender menu] numberOfItems]; i++)
        [[[sender menu] itemAtIndex: i] setState: NSControlStateValueOff];
    
    [[searchField cell] setPlaceholderString: [[[sender menu] itemWithTag: [sender tag]] title]];
    
    [[[sender menu] itemWithTag: [sender tag]] setState: NSControlStateValueOn];
    [toolbarSearchItem setLabel: [NSString stringWithFormat: NSLocalizedString(@"Search by %@", nil), [sender title]]];
    searchType = [sender tag];
    
    //create new Filter Predicate when changing searchType ans set searchString to nil;
    [self setSearchString:nil];
    [databaseOutline scrollRowToVisible: [databaseOutline selectedRow]];
    
    if( _searchString.length > 2 || (_searchString.length >= 2 && searchType == 5))
    {
        @synchronized( self)
        {
            [distantSearchThread cancel];
            [distantSearchThread release];
            distantSearchThread = nil;
        }
        
        [NSThread detachNewThreadSelector: @selector(searchForSearchField:) toTarget:self withObject: [NSDictionary dictionaryWithObjectsAndKeys: [NSNumber numberWithInt: searchType], @"searchType", _searchString, @"searchString", [NSNumber numberWithInt: albumTable.selectedRow], @"selectedAlbumIndex", nil]];
    }
    else if( timeIntervalStart || timeIntervalEnd)
    {
        @synchronized( self)
        {
            [distantSearchThread cancel];
            [distantSearchThread release];
            distantSearchThread = nil;
        }
        
        if( albumTable.selectedRow == 0)
            [NSThread detachNewThreadSelector: @selector(searchForTimeIntervalFromTo:) toTarget:self withObject: [NSDictionary dictionaryWithObjectsAndKeys: timeIntervalStart, @"from", timeIntervalEnd, @"to", nil]];
    }
    else
    {
        @synchronized( self)
        {
            [distantSearchThread cancel];
            [distantSearchThread release];
            distantSearchThread = nil;
        }
    }
    
    [[NSUserDefaults standardUserDefaults] setInteger: [sender tag] forKey:@"searchType"];
}

- (void) computeTimeInterval
{
    switch( self.timeIntervalType)
    {
        case 0:	// None
            [timeIntervalStart release];		timeIntervalStart = nil;
            [timeIntervalEnd release];			timeIntervalEnd = nil;
            break;
            
        case 1:	// 1 hour
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: -60*60] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
            break;
            
        case 2:	// 6 hours
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: -60*60*6] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
            break;
            
        case 3:	// 12 hours
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: -60*60*12] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
            break;
            
        case 7:	// 24 hours
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: -60*60*24] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
            break;
            
        case 8:	// 48 hours
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: -60*60*48] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
            break;
            
        case 4:	{ // Today
            
            DCMCalendarDate *now = [DCMCalendarDate calendarDate];
            DCMCalendarDate *start = [DCMCalendarDate dateWithYear:[now yearOfCommonEra] month:[now monthOfYear] day:[now dayOfMonth] hour:0 minute:0 second:0 timeZone: [now timeZone]];
            
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: [start timeIntervalSinceDate: now]] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
        }
            break;
            
        case 5:
        {	// One week
            
            DCMCalendarDate *now		= [DCMCalendarDate calendarDate];
            DCMCalendarDate *oneWeek = [now dateByAddingYears:0 months:0 days:-7 hours:0 minutes:0 seconds:0];
            
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: [oneWeek timeIntervalSinceDate: now]] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
        }
            break;
            
        case 6:	{ // One month
            
            DCMCalendarDate *now		= [DCMCalendarDate calendarDate];
            DCMCalendarDate *oneWeek = [now dateByAddingYears:0 months:-1 days:0 hours:0 minutes:0 seconds:0];
            
            [timeIntervalStart release];		timeIntervalStart = [[NSDate dateWithTimeIntervalSinceNow: [oneWeek timeIntervalSinceDate: now]] retain];
            [timeIntervalEnd release];			timeIntervalEnd = nil;
        }
            break;
            
        case 100:	// Custom
            [timeIntervalStart release];
            [timeIntervalEnd release];
            timeIntervalStart = [[CustomIntervalPanel sharedCustomIntervalPanel].fromDate copy];
            timeIntervalEnd = [[CustomIntervalPanel sharedCustomIntervalPanel].toDate copy];
            break;
    }
    
    if( timeIntervalStart || timeIntervalEnd)
    {
        if( [timeIntervalStart isEqualToDate: self.distantTimeIntervalStart] == NO || (timeIntervalEnd != nil && [timeIntervalEnd isEqualToDate: self.distantTimeIntervalEnd] == NO))
        {
            @synchronized( self)
            {
                [distantSearchThread cancel];
                [distantSearchThread release];
                distantSearchThread = nil;
            }
            
            if( albumTable.selectedRow == 0)
                [NSThread detachNewThreadSelector: @selector(searchForTimeIntervalFromTo:) toTarget:self withObject: [NSDictionary dictionaryWithObjectsAndKeys: timeIntervalStart, @"from", timeIntervalEnd, @"to", nil]];
        }
    }
    else if( _searchString.length > 2 || (_searchString.length >= 2 && searchType == 5))
        [self setSearchString: _searchString];
    else
    {
        @synchronized( self)
        {
            [distantSearchThread cancel];
            [distantSearchThread release];
            distantSearchThread = nil;
        }
    }
}

- (void) setTimeIntervalType: (int) t
{
    [self willChangeValueForKey: @"timeIntervalType"];
    timeIntervalType = t;
    [self didChangeValueForKey: @"timeIntervalType"];
    
    if( t == 100)
        [[[CustomIntervalPanel sharedCustomIntervalPanel] window] makeKeyAndOrderFront: self];
    
    [self computeTimeInterval];
    [self outlineViewRefresh];
}

- (void) setModalityFilter:(NSString *) m
{
    if( m == nil)
        m = [[modalityFilterMenu itemAtIndex: 0] title];
    
    [self willChangeValueForKey: @"modalityFilter"];
    modalityFilter = m;
    [self didChangeValueForKey: @"modalityFilter"];
    
    self.distantTimeIntervalStart = nil;
    self.distantTimeIntervalEnd = nil;
    [self computeTimeInterval]; // Yes, this is normal : modality filter is only available if a time interval is selected for PACS On-Demand
    [self outlineViewRefresh];
}

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark OutlineView functions

- (NSPredicate*) smartAlbumPredicateString:(NSString*) string
{
    if( string == nil || [string length] == 0)
        return [NSPredicate predicateWithValue: YES];
    
    NSMutableString *pred = [NSMutableString stringWithString: string];
    
    DCMCalendarDate	*now = [DCMCalendarDate calendarDate];
    NSDate	*start = [NSDate dateWithTimeIntervalSinceReferenceDate: [[DCMCalendarDate dateWithYear:[now yearOfCommonEra] month:[now monthOfYear] day:[now dayOfMonth] hour:0 minute:0 second:0 timeZone: [now timeZone]] timeIntervalSinceReferenceDate]];
    
    NSDictionary	*sub = [NSDictionary dictionaryWithObjectsAndKeys:	[NSString stringWithFormat:@"%lf", [[now dateByAddingTimeInterval: -60*60*1] timeIntervalSinceReferenceDate]],			@"$LASTHOUR",
                            [NSString stringWithFormat:@"%lf", [[now dateByAddingTimeInterval: -60*60*6] timeIntervalSinceReferenceDate]],			@"$LAST6HOURS",
                            [NSString stringWithFormat:@"%lf", [[now dateByAddingTimeInterval: -60*60*12] timeIntervalSinceReferenceDate]],			@"$LAST12HOURS",
                            [NSString stringWithFormat:@"%lf", [start timeIntervalSinceReferenceDate]],										@"$TODAY",
                            [NSString stringWithFormat:@"%lf", [[Horos:start dateByAddingYears:0 months:0 days:-1 hours:0 minutes:0 seconds:0] timeIntervalSinceReferenceDate]],			@"$YESTERDAY",
                            [NSString stringWithFormat:@"%lf", [[Horos:start dateByAddingYears:0 months:0 days:-2 hours:0 minutes:0 seconds:0] timeIntervalSinceReferenceDate]],		@"$2DAYS",
                            [NSString stringWithFormat:@"%lf", [[Horos:start dateByAddingYears:0 months:0 days:-7 hours:0 minutes:0 seconds:0] timeIntervalSinceReferenceDate]],		@"$WEEK",
                            [NSString stringWithFormat:@"%lf", [[start dateByAddingTimeInterval: -60*60*24*31] timeIntervalSinceReferenceDate]],		@"$MONTH",
                            [NSString stringWithFormat:@"%lf", [[start dateByAddingTimeInterval: -60*60*24*31*2] timeIntervalSinceReferenceDate]],	@"$2MONTHS",
                            [NSString stringWithFormat:@"%lf", [[start dateByAddingTimeInterval: -60*60*24*31*3] timeIntervalSinceReferenceDate]],	@"$3MONTHS",
                            [NSString stringWithFormat:@"%lf", [[start dateByAddingTimeInterval: -60*60*24*365] timeIntervalSinceReferenceDate]],		@"$YEAR",
                            nil];
    
    NSEnumerator *enumerator = [sub keyEnumerator];
    NSString *key;
    
    while ((key = [enumerator nextObject]))
    {
        [pred replaceOccurrencesOfString:key withString: [sub valueForKey: key]	options: NSCaseInsensitiveSearch range:pred.range];
    }
    
    NSPredicate *predicate;
    
    if( [string isEqualToString:@""])
        predicate = [NSPredicate predicateWithValue: YES];
    else
        predicate = [NSPredicate predicateWithFormat: pred];
    
    predicate = [predicate predicateWithSubstitutionVariables: [NSDictionary dictionaryWithObjectsAndKeys:
                                                                [now dateByAddingTimeInterval: -60*60*1],			@"NSDATE_LASTHOUR",
                                                                [now dateByAddingTimeInterval: -60*60*6],			@"NSDATE_LAST6HOURS",
                                                                [now dateByAddingTimeInterval: -60*60*12],			@"NSDATE_LAST12HOURS",
                                                                start,                                              @"NSDATE_TODAY",
                                                                [Horos:start dateByAddingYears:0 months:0 days:-1 hours:0 minutes:0 seconds:0],        @"NSDATE_YESTERDAY",
                                                                [Horos:start dateByAddingYears:0 months:0 days:-2 hours:0 minutes:0 seconds:0],		@"NSDATE_2DAYS",
                                                                [Horos:start dateByAddingYears:0 months:0 days:-7 hours:0 minutes:0 seconds:0],		@"NSDATE_WEEK",
                                                                [start dateByAddingTimeInterval: -60*60*24*31],		@"NSDATE_MONTH",
                                                                [start dateByAddingTimeInterval: -60*60*24*31*2],	@"NSDATE_2MONTHS",
                                                                [start dateByAddingTimeInterval: -60*60*24*31*3],	@"NSDATE_3MONTHS",
                                                                [start dateByAddingTimeInterval: -60*60*24*365],    @"NSDATE_YEAR",
                                                                nil]];
    
    return predicate;
}

- (IBAction)selectNoAlbums:(id)sender
{
    BOOL copyClearSearchAndTimeIntervalWhenSelectingAlbum = [[NSUserDefaults standardUserDefaults] boolForKey: @"clearSearchAndTimeIntervalWhenSelectingAlbum"];
    
    [[NSUserDefaults standardUserDefaults] setBool: NO forKey: @"clearSearchAndTimeIntervalWhenSelectingAlbum"];
    
    [albumTable selectRowIndexes: [NSIndexSet indexSetWithIndex: 0] byExtendingSelection:NO];
    
    [[NSUserDefaults standardUserDefaults] setBool: copyClearSearchAndTimeIntervalWhenSelectingAlbum forKey: @"clearSearchAndTimeIntervalWhenSelectingAlbum"];
}

- (void) selectAlbumWithName: (NSString*) name
{
    for( DicomAlbum *album in _database.albums)
    {
        if( [album.name isEqualToString: name])
        {
            if( [self.albumArray indexOfObject:album] != NSNotFound)
                [albumTable selectRowIndexes:[NSIndexSet indexSetWithIndex:[self.albumArray indexOfObject:album]] byExtendingSelection:NO];
        }
    }
}

- (NSPredicate*)smartAlbumPredicate: (NSManagedObject*)album
{
    NSPredicate	*pred = nil;
    
    @try
    {
        pred = [self smartAlbumPredicateString: [album valueForKey:@"predicateString"]];
    }
    
    @catch( NSException *ne)
    {
        pred = [NSPredicate predicateWithValue: NO];
        N2LogExceptionWithStackTrace(ne/*, @"filter error"*/);
    }
    
    return pred;
}

- (void) refreshEntireDBResult
{
    if( distantEntireDBResultCount > outlineViewArray.count || localEntireDBResultCount > outlineViewArray.count)
    {
        [searchInEntireDBResult setTitle: N2LocalizedSingularPluralCount( ((distantEntireDBResultCount > localEntireDBResultCount) ? distantEntireDBResultCount : localEntireDBResultCount), NSLocalizedString(@"result in entire DB", @"Try to keep this string **short**"), NSLocalizedString(@"results in entire DB", @"Try to keep this string **short**"))];
        
        [searchInEntireDBResult setHidden: NO];
    }
    else
        [searchInEntireDBResult setHidden: YES];
}

// The studies found before the other studies of the same patients were added;
// drawn in bold, so asked about for every visible row.
- (void) rememberOriginalOutlineViewArray: (NSArray*) array
{
    [originalOutlineViewArray release];
    originalOutlineViewArray = [array retain];
    [originalOutlineViewStudies release];
    originalOutlineViewStudies = array ? [[NSSet alloc] initWithArray: array] : nil;
}

- (NSString*) outlineViewRefresh		// This function creates the 'root' array for the outlineView
{
    @synchronized (self)
    {
        _cachedAlbumsContext = nil;
    }
    
    if( databaseOutline == nil) return nil;
    if( loadingIsOver == NO) return nil;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"])
    {
        if( [[self window] isVisible] == NO) return nil;
    }
    
    if( [NSThread isMainThread] == NO)
        NSLog( @"******* We HAVE TO be in main thread !");
    
    NSError				*error =nil;
    NSPredicate			*predicate = nil, *subPredicate = nil;
    NSString			*description = [NSString string];
    NSIndexSet			*selectedRowIndexes =  [databaseOutline selectedRowIndexes];
    NSMutableArray		*previousObjects = [NSMutableArray array];
    NSArray				*albumArrayContent = nil;
    BOOL				filtered = NO;
    NSString			*exception = nil;
    
    NSInteger index = [selectedRowIndexes firstIndex];
    while (index != NSNotFound)
    {
        if( [databaseOutline itemAtRow: index])
            [previousObjects addObject: [databaseOutline itemAtRow: index]];
        index = [selectedRowIndexes indexGreaterThanIndex:index];
    }
    
    
    if( [_sourcesTableView selectedRow] >= 0)
    {
        DataNodeIdentifier* bs = [self sourceIdentifierAtRow: [_sourcesTableView selectedRow]];
        
        if( bs)
            description = [description stringByAppendingFormat:NSLocalizedString(@"%@: %@ / ", nil), [_database isLocal] ? NSLocalizedString( @"Local Database", nil) : NSLocalizedString( @"Remote Database", nil), [bs description]];
    }
    
    // ********************
    // ALBUMS
    // ********************
    NSString *smartAlbumName = nil;
    
    if( albumTable.selectedRow > 0)
    {
        NSArray	*albumArray = self.albumArray;
        
        if( [albumArray count] > albumTable.selectedRow)
        {
            NSManagedObject	*album = [albumArray objectAtIndex: albumTable.selectedRow];
            
            if( [[album valueForKey:@"smartAlbum"] boolValue] == YES)
            {
                smartAlbumName = [album valueForKey:@"name"];
                albumArrayContent = [_database objectsForEntity: _database.studyEntity predicate:[self smartAlbumPredicate: album]];
                description = [description stringByAppendingFormat:NSLocalizedString(@"Smart Album selected: %@", nil), smartAlbumName];
            }
            else
            {
                albumArrayContent = [[album valueForKey:@"studies"] allObjects];
                description = [description stringByAppendingFormat:NSLocalizedString(@"Album selected: %@", nil), [album valueForKey:@"name"]];
            }
        }
    }
    else description = [description stringByAppendingString: NSLocalizedString(@"No album selected", nil)];
    
    // ********************
    // TIME INTERVAL
    // ********************
    
    if( timeIntervalStart != nil || timeIntervalEnd != nil)
    {
        if( timeIntervalStart != nil && timeIntervalEnd != nil)
        {
            subPredicate = [NSPredicate predicateWithFormat: @"date >= CAST(%lf, \"NSDate\") AND date <= CAST(%lf, \"NSDate\")", [timeIntervalStart timeIntervalSinceReferenceDate], [timeIntervalEnd timeIntervalSinceReferenceDate]];
            
            description = [description stringByAppendingFormat: NSLocalizedString(@" / Time Interval: from: %@ to: %@", nil),[[NSUserDefaults dateTimeFormatter] stringFromDate: timeIntervalStart],  [[NSUserDefaults dateTimeFormatter] stringFromDate: timeIntervalEnd] ];
        }
        else
        {
            subPredicate = [NSPredicate predicateWithFormat: @"date >= CAST(%lf, \"NSDate\")", [timeIntervalStart timeIntervalSinceReferenceDate]];
            
            description = [description stringByAppendingFormat:NSLocalizedString(@" / Time Interval: since: %@", nil), [[NSUserDefaults dateTimeFormatter] stringFromDate: timeIntervalStart]];
        }
        predicate = [NSCompoundPredicate andPredicateWithSubpredicates: [NSArray arrayWithObjects: subPredicate, predicate, nil]];
        filtered = YES;
    }
    
    // ********************
    // MODALITY FILTER
    // ********************
    
    if( [modalityFilterMenu indexOfSelectedItem] > 0 && self.modalityFilter.length)
    {
        subPredicate = [NSPredicate predicateWithFormat: @"modality CONTAINS %@", self.modalityFilter];
        
        description = [description stringByAppendingFormat: NSLocalizedString(@" / Modality: %@", nil), self.modalityFilter];
        
        predicate = [NSCompoundPredicate andPredicateWithSubpredicates: [NSArray arrayWithObjects: subPredicate, predicate, nil]];
        filtered = YES;
    }
    
    // ********************
    // SEARCH FIELD
    // ********************
    
    if( self.filterPredicate)
    {
        predicate = [NSCompoundPredicate andPredicateWithSubpredicates: [NSArray arrayWithObjects: self.filterPredicate, predicate, nil]];
        description = [description stringByAppendingString: self.filterPredicateDescription];
        filtered = YES;
    }
    
    if( testPredicate)
        predicate = testPredicate;
    
    if( predicate == nil)
        predicate = [NSPredicate predicateWithValue: YES];
    
    //	[_database lock];
    error = nil;
    [outlineViewArray release];
    outlineViewArray = nil;
    @try
    {
        @try
        {
            [searchInEntireDBResult setHidden: YES];
            
            if( albumArrayContent)
            {
                outlineViewArray = [albumArrayContent filteredArrayUsingPredicate:predicate];
                
                if( self.filterPredicate)
                {
                    // Entire DB Result
                    
                    distantEntireDBResultCount = 0;
                    localEntireDBResultCount = [[[_database objectsForEntity:_database.studyEntity predicate:nil error:&error] filteredArrayUsingPredicate: self.filterPredicate] count];
                    
                    [self refreshEntireDBResult];
                }
            }
            else
                outlineViewArray = [[_database objectsForEntity:_database.studyEntity predicate:nil error:&error] filteredArrayUsingPredicate:predicate];

            if (self.filterPredicate && outlineViewArray)
            {
                NSArray *federated = [[self class] federatedStudiesMatchingPredicate:self.filterPredicate excludingDatabasePath:_database.baseDirPath applyingUser:nil];
                if (federated.count)
                {
                    NSMutableArray *merged = [[outlineViewArray mutableCopy] autorelease];
                    NSMutableSet *seen = [NSMutableSet set];
                    for (id study in merged)
                    {
                        NSString *key = [HorosFederatedSearch identityKeyWithPatientUID:[study valueForKey:@"patientUID"]
                                                                              studyUID:[study valueForKey:@"studyInstanceUID"]
                                                                            originPath:_database.baseDirPath];
                        if (key)
                            [seen addObject:key];
                    }
                    for (id study in federated)
                    {
                        DicomDatabase *origin = [study isKindOfClass:[NSManagedObject class]] ? [DicomDatabase databaseForContext:[study managedObjectContext]] : nil;
                        NSString *key = [HorosFederatedSearch identityKeyWithPatientUID:[study valueForKey:@"patientUID"]
                                                                              studyUID:[study valueForKey:@"studyInstanceUID"]
                                                                            originPath:origin.baseDirPath];
                        if (key && [seen containsObject:key] == NO)
                        {
                            [merged addObject:study];
                            [seen addObject:key];
                        }
                    }
                    outlineViewArray = merged;
                }
            }
        }
        @catch( NSException *ne)
        {
            outlineViewArray = [NSArray array];
            N2LogExceptionWithStackTrace(ne);
        }
        
        if( error)
            NSLog( @"**** executeFetchRequest: %@", error);
        
        // Smart Album Distant Studies, if available
        @synchronized( self)
        {
            BOOL useDistantArray = NO;
            
            if( smartAlbumDistantArray && smartAlbumName && [self.smartAlbumDistantName isEqualToString: smartAlbumName])
                useDistantArray = YES;
            else if( timeIntervalStart != nil || timeIntervalEnd != nil || self.filterPredicate) // No smart album selected, but time interval or search field
            {
                if( timeIntervalStart != nil || timeIntervalEnd != nil) // Search for the time interval, then apply the search field, if necessary
                {
                    if( [self.distantTimeIntervalStart isEqualToDate: timeIntervalStart] && (timeIntervalEnd == nil || [self.distantTimeIntervalEnd isEqualToDate: timeIntervalEnd]))
                        useDistantArray = YES;
                }
                
                if( self.distantSearchType == searchType && [self.distantSearchString isEqualToString: _searchString])
                    useDistantArray = YES;
            }
            
            if( useDistantArray)
            {
                NSMutableArray *distantStudies = [NSMutableArray array];
                
                NSArray *filteredAlbumDistantStudies = nil;
                @synchronized( smartAlbumDistantArraySync)
                {
                    filteredAlbumDistantStudies = [smartAlbumDistantArray filteredArrayUsingPredicate: predicate];
                }
                
                // Merge local and distant studies
#ifndef OSIRIX_LIGHT
                
                // Autoretrieve?
                NSMutableArray *studyToAutoretrieve = [NSMutableArray array];
                BOOL autoretrieve = NO;
                
                if( autoretrievingPACSOnDemandSmartAlbum == NO)
                {
                    for( NSDictionary *d in [[NSUserDefaults standardUserDefaults] objectForKey: @"smartAlbumStudiesDICOMNodes"])
                    {
                        if( [[d valueForKey: @"autoretrieve"] boolValue] && [smartAlbumName isEqualToString: [d valueForKey: @"name"]])
                            autoretrieve = YES;
                    }
                }
                
                NSMutableArray *localStudyInstanceUIDs = [outlineViewArray valueForKey: @"studyInstanceUID"];
                for( DCMTKStudyQueryNode *distantStudy in filteredAlbumDistantStudies)
                {
                    if( [localStudyInstanceUIDs containsObject: [distantStudy studyInstanceUID]] == NO)
                    {
                        [distantStudies addObject: distantStudy];
                        
                        if( autoretrieve)
                            [studyToAutoretrieve addObject: distantStudy];
                    }
                    else if( [[NSUserDefaults standardUserDefaults] boolForKey: @"preferStudyWithMoreImages"])
                    {
                        BOOL inTheRetrieveQueue = NO;
                        
                        //Is this study in the retrieve queue? Display the local study
                        @synchronized( comparativeRetrieveQueue)
                        {
                            inTheRetrieveQueue = [[comparativeRetrieveQueue valueForKey: @"studyInstanceUID"] containsObject: [distantStudy studyInstanceUID]];
                        }
                        
                        if( inTheRetrieveQueue == NO)
                        {
                            NSUInteger index = [localStudyInstanceUIDs indexOfObject: [distantStudy studyInstanceUID]];
                            
                            if( index != NSNotFound && [[[outlineViewArray objectAtIndex: index] rawNoFiles] intValue] < [[distantStudy noFiles] intValue])
                            {
                                if( autoretrieve || [[NSUserDefaults standardUserDefaults] boolForKey: @"automaticallyRetrievePartialStudies"])
                                    [studyToAutoretrieve addObject: distantStudy];
                                else
                                {
                                    NSMutableArray *mutableCopy = [[outlineViewArray mutableCopy] autorelease];
                                    [mutableCopy replaceObjectAtIndex: index withObject: distantStudy];
                                    outlineViewArray = mutableCopy;
                                }
                            }
                        }
                    }
                }
                
                @synchronized (_albumNoOfStudiesCache)
                {
                    if( smartAlbumName && filtered == NO && [smartAlbumDistantName isEqualToString: smartAlbumName]) // filtered == NO, we want only if ALL studies are displayed (not limited by Search String or Time Interval, for example
                        [_distantAlbumNoOfStudiesCache setObject: distantStudies forKey: smartAlbumName];
                }
                
                if( autoretrievingPACSOnDemandSmartAlbum == NO && studyToAutoretrieve.count)
                {
                    NSThread* t = [[[NSThread alloc] initWithTarget:self selector:@selector(autoretrievePACSOnDemandSmartAlbum:) object: studyToAutoretrieve] autorelease];
                    t.name = NSLocalizedString( @"Auto-Retrieving...", nil);
                    t.supportsCancel = YES;
                    [[ThreadsManager defaultManager] addThreadAndStart: t];
                }
                
#endif
                
                if( [distantStudies count])
                    outlineViewArray = [outlineViewArray arrayByAddingObjectsFromArray: distantStudies];
            }
        }
        
        @synchronized (_albumNoOfStudiesCache)
        {
            if ([_albumNoOfStudiesCache count] > albumTable.selectedRow && filtered == NO)
            {
                [_albumNoOfStudiesCache replaceObjectAtIndex:albumTable.selectedRow withObject:[decimalNumberFormatter stringForObjectValue:[NSNumber numberWithInt:[outlineViewArray count]]]];
                [albumTable reloadData];
            }
        }
    }
    @catch( NSException *ne)
    {
        N2LogExceptionWithStackTrace(ne);
        
        outlineViewArray = [NSArray array];
        
        exception = [ne description];
    }
    
    if( albumTable.selectedRow > 0) filtered = YES;
    
    NSSortDescriptor * sortdate = [[[NSSortDescriptor alloc] initWithKey: @"date" ascending:NO] autorelease];
    NSArray * sortDescriptors;
    if( [databaseOutline sortDescriptors] == nil || [[databaseOutline sortDescriptors] count] == 0)
    {
        // By default sort by name
        NSSortDescriptor * sort = [[[NSSortDescriptor alloc] initWithKey:@"name" ascending:YES selector:@selector(caseInsensitiveCompare:)] autorelease];
        sortDescriptors = [NSArray arrayWithObjects: sort, sortdate, nil];
    }
    else if( [[[[databaseOutline sortDescriptors] objectAtIndex: 0] key] isEqualToString:@"name"])
    {
        sortDescriptors = [NSArray arrayWithObjects: [[databaseOutline sortDescriptors] objectAtIndex: 0], sortdate, nil];
    }
    else sortDescriptors = [databaseOutline sortDescriptors];
    
    if( filtered == YES && [[NSUserDefaults standardUserDefaults] boolForKey: @"KeepStudiesOfSamePatientTogether"] && outlineViewArray.count > 0 && outlineViewArray.count < 500)
    {
        @try
        {
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"KeepStudiesOfSamePatientTogetherAndGrouped"])
            {
                outlineViewArray = [outlineViewArray sortedArrayUsingDescriptors: sortDescriptors];
                
                NSMutableArray *copyOutlineViewArray = [NSMutableArray arrayWithArray: outlineViewArray];
                int studyIndex = 0;
                
                for( id obj in outlineViewArray)
                {
                    @try {
                        NSPredicate* predicate = [NSPredicate predicateWithFormat: @"(patientID == %@) AND (studyInstanceUID != %@)", [obj valueForKey:@"patientID"], [obj valueForKey:@"studyInstanceUID"]];
                        
                        NSMutableArray *oulineViewArrayStudyInstanceUIDs = [[[copyOutlineViewArray valueForKey: @"studyInstanceUID"] mutableCopy] autorelease];
                        NSInteger expansionLimit = [HorosAssociationContract relatedStudiesLimitIn: [NSUserDefaults standardUserDefaults]];
                        NSInteger expanded = 0;
                        
                        for( id patientStudy in [[_database objectsForEntity:_database.studyEntity predicate:predicate] sortedArrayUsingDescriptors: [NSArray arrayWithObject: [NSSortDescriptor sortDescriptorWithKey:@"date" ascending:NO]]])
                        {
                            if( expansionLimit > 0 && expanded >= expansionLimit)
                                break; // the published limit keeps this expansion bounded (#380 C)
                            
                            if( [oulineViewArrayStudyInstanceUIDs containsObject: [patientStudy valueForKey: @"studyInstanceUID"]] == NO && patientStudy != nil)
                                                        {
                                studyIndex++;
                                expanded++;
                                [copyOutlineViewArray insertObject: patientStudy atIndex: studyIndex];
                                [oulineViewArrayStudyInstanceUIDs insertObject: [patientStudy valueForKey: @"studyInstanceUID"] atIndex: studyIndex];
                            }
                        }
                    } @catch (NSException* e) { // object has become unavailable, who cares, we just won't be showing it anymore
                    }
                    
                    studyIndex++;
                }
                
                [self rememberOriginalOutlineViewArray: outlineViewArray];
                outlineViewArray = copyOutlineViewArray;
            }
            else
            {
                NSMutableArray	*patientPredicateArray = [NSMutableArray array];
                for (id obj in outlineViewArray)
                    [patientPredicateArray addObject: [NSPredicate predicateWithFormat:@"(patientUID BEGINSWITH[cd] %@)", [obj valueForKey:@"patientUID"]]];
                predicate = [NSCompoundPredicate orPredicateWithSubpredicates: patientPredicateArray];
                [self rememberOriginalOutlineViewArray: outlineViewArray];
                outlineViewArray = [[_database objectsForEntity:_database.studyEntity predicate:predicate] sortedArrayUsingDescriptors:sortDescriptors];
            }
        }
        @catch( NSException *ne)
        {
            N2LogExceptionWithStackTrace(ne);
        }
    }
    else
    {
        [self rememberOriginalOutlineViewArray: nil];
        
        outlineViewArray = [outlineViewArray sortedArrayUsingDescriptors: sortDescriptors];
    }
    
    NSArray *timelineEvents = [self surgicalProcedureTimelineEvents];
    if (timelineEvents.count)
        outlineViewArray = [HorosSurgicalProcedureOutline arrayByInsertingEvents:timelineEvents intoStudies:outlineViewArray];
    
    long images = 0;
    for( id obj in outlineViewArray)
    {
        images += [[obj valueForKey:@"noFiles"] intValue];
    }
    
    description = [description stringByAppendingFormat: NSLocalizedString(@" / Result = %@ studies (%@ images)", nil), [decimalNumberFormatter stringForObjectValue:[NSNumber numberWithInt: [outlineViewArray count]]], [decimalNumberFormatter stringForObjectValue:[NSNumber numberWithInt:images]]];
    
    outlineViewArray = [outlineViewArray retain];
    
    //	[_database unlock];
    
    [databaseOutline reloadData];
    [comparativeTable reloadData];
    
    @try
    {
        for( id obj in outlineViewArray)
        {
            if( [[obj valueForKey:@"expanded"] boolValue]) [databaseOutline expandItem: obj];
        }
    }
    @catch( NSException *ne)
    {
        N2LogExceptionWithStackTrace(ne);
    }
    
    
    if( [previousObjects count] > 0)
    {
        // The selected rows are found again by what they are, not by object
        // identity: refreshing a remote index replaces the objects, and
        // -rowForItem: then answers -1, which as an index is NSUIntegerMax. The
        // selection was lost on every refresh and the first patient took its
        // place. A row that really is gone is simply not selected.
        NSMutableArray *currentItems = [NSMutableArray arrayWithCapacity: databaseOutline.numberOfRows];
        for( NSInteger row = 0; row < databaseOutline.numberOfRows; row++)
        {
            id item = [databaseOutline itemAtRow: row];
            [currentItems addObject: item ? item : [NSNull null]];
        }
        
        NSIndexSet *rows = [HorosOutlineSelectionRestore rowsMatching: [HorosOutlineSelectionRestore identifiersForItems: previousObjects] inItems: currentItems];
        
        if( rows.count)
            [databaseOutline selectRowIndexes: rows byExtendingSelection: NO];
    }
    
    if( [outlineViewArray count] > 0)
        [[NSNotificationCenter defaultCenter] postNotificationName: NSOutlineViewSelectionDidChangeNotification  object:databaseOutline userInfo: nil];
    
    if (_database.incomingImportWaitingForSpace)
        description = [NSLocalizedString(@"IMPORT PAUSED: free space or reconnect storage; incoming files are preserved. / ", nil) stringByAppendingString:description];
    
    // A refused file is the reason a study arrives with images missing, and it
    // used to be said in the log only - which is where "rejected with no visible
    // error" comes from. The whole sentence is in the tooltip.
    if (_database.lastImportRefusalSummary.length)
        description = [[NSLocalizedString(@"LAST IMPORT: ", nil) stringByAppendingFormat: @"%@ / ", _database.lastImportRefusalSummary] stringByAppendingString: description];
    [databaseDescription setToolTip:description];
    [databaseDescription setStringValue: description];
    
    return exception;
}

- (void) searchDeadProcesses
{
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    @try
    {
        // Test for deadlock processes lock_process pid in the processes' folder. In /tmp,
        // another user could name any of our processes for this to kill (#801).
        NSString *processFolder = [NSString stringWithUTF8String: HorosDICOMProcessFolder()];
        for( NSString *s in [[NSFileManager defaultManager] contentsOfDirectoryAtPath: processFolder error: nil])
        {
            if( [s hasPrefix: @"lock_process-"])
            {
                int timeIntervalSinceNow = [[[[NSFileManager defaultManager] attributesOfItemAtPath: [processFolder stringByAppendingPathComponent: s] error: nil] fileCreationDate] timeIntervalSinceNow];
                
                if( timeIntervalSinceNow < -60*60*1)
                {
                    NSLog( @"****** dead process found lock_process %@", s);
                    NSLog( @"****** dead process timeIntervalSinceNow %d", timeIntervalSinceNow);
                    
                    int pid = [[s stringByReplacingOccurrencesOfString: @"lock_process-" withString: @""] intValue];
                    
                    if( pid)
                    {
                        NSLog( @"****** kill pid %@", s);
                        kill( pid, 15);
                        
                        char dir[ PATH_MAX];
                        snprintf( dir, sizeof( dir), "%s/lock_process-%d", HorosDICOMProcessFolder(), pid);
                        unlink( dir);
                    }
                }
            }
        }
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
			 
    [pool release];
}


-(void)refreshBonjourSource: (id) sender
{
    if ([_database isKindOfClass:[RemoteDicomDatabase class]])
        (void)[(RemoteDicomDatabase*)_database initiateUpdate];
}

- (void) autoretrievePACSOnDemandSmartAlbum:(NSArray*) studies
{
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    autoretrievingPACSOnDemandSmartAlbum = YES;
    {
#ifndef OSIRIX_LIGHT
        [studies setValue:[NSNumber numberWithBool:YES] forKey:@"isAutoRetrieve"];
        [QueryController retrieveStudies: studies showErrors: NO checkForPreviousAutoRetrieve: YES];
#endif
    }
    autoretrievingPACSOnDemandSmartAlbum = NO;
    [pool release];
}

- (void)_computeNumberOfStudiesForAlbumsThread
{
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
    @try
    {
        // -refreshAlbums marked the count as running before starting this thread.
        [NSThread currentThread].name = NSLocalizedString( @"Compute Albums...", nil);
        [[ThreadsManager defaultManager] addThreadAndStart: [NSThread currentThread]];
        
        DicomDatabase* idatabase = [self.database privateQueueIndependentDatabase];
        if (!idatabase)
        {
            _computingNumberOfStudiesForAlbums = NO;
            [self performSelectorOnMainThread:@selector(delayedRefreshAlbums) withObject:nil waitUntilDone:NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
            return;
        }
        
        // Counted on a private-queue context, on its queue (#966).
        [idatabase performBlockAndWait:^{
        @try
        {
            NSMutableArray* NoOfStudies = [NSMutableArray array];
            
            // compute number of studies in database
            NSInteger count = -1;
            @try
            {
                count = [idatabase countObjectsForEntity:idatabase.studyEntity];
            }
            @catch (NSException* e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            [NoOfStudies addObject: count >= 0 ? [decimalNumberFormatter stringForObjectValue:[NSNumber numberWithInt:count]] : @"#"];
            
            // compute every album's studies count
            
            DicomDatabase *currentDatabase = _database;
            
            NSArray* albumObjectIDs;
            @synchronized (self)
            {
                albumObjectIDs = [NSArray arrayWithArray: _cachedAlbumsIDs];
            }
            
            NSTimeInterval lastTime = [NSDate timeIntervalSinceReferenceDate];
            
            
            BOOL recomputeDistantStudies = NO;
            
            if( [NSDate timeIntervalSinceReferenceDate] - lastComputeAlbumsForDistantStudies > 120)
                recomputeDistantStudies = YES;
            
            for (NSManagedObjectID* albumObjectID in albumObjectIDs)
            {
                if( currentDatabase != _database) // We switched the main database...
                {
                    [self performSelectorOnMainThread:@selector(delayedRefreshAlbums) withObject:nil waitUntilDone:NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
                    break;
                }
                
                // An album deleted while this thread runs leaves a fault that
                // throws on the first access; existingObjectWithID: answers nil
                // instead, and the count simply skips it (#380 B).
                DicomAlbum* ialbum = (DicomAlbum*) [idatabase.managedObjectContext existingObjectWithID:albumObjectID error:nil];
                
                if( ialbum == nil || ialbum.isDeleted)
                    continue;
                
                [NSThread currentThread].status = ialbum.name;
                
                count = -1;
                if( ialbum.smartAlbum.boolValue == YES)
                {
                    @try
                    {
                        NSArray *localStudies = [[idatabase objectsForEntity:idatabase.studyEntity predicate:[self smartAlbumPredicate:ialbum]] valueForKey: @"studyInstanceUID"];
                        
                        count = 0;
                        
                        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForSmartAlbumStudiesOnDICOMNodes"])
                        {
                            NSMutableArray *studyToAutoretrieve = [NSMutableArray array];
                            BOOL autoretrieve = NO;
                            
                            if( autoretrievingPACSOnDemandSmartAlbum == NO)
                            {
                                for( NSDictionary *d in [[NSUserDefaults standardUserDefaults] objectForKey: @"smartAlbumStudiesDICOMNodes"])
                                {
                                    if( [[d valueForKey: @"autoretrieve"] boolValue] && [ialbum.name isEqualToString: [d valueForKey: @"name"]])
                                        autoretrieve = YES;
                                }
                            }
                            
                            // Merge local and distant studies
                            NSArray *distantStudies = nil;
                            @synchronized(_albumNoOfStudiesCache)
                            {
                                distantStudies = [[[_distantAlbumNoOfStudiesCache objectForKey: ialbum.name] copy] autorelease];
                            }
                            
                            if( recomputeDistantStudies || distantStudies == nil)
                            {
                                distantStudies = [self distantStudiesForSmartAlbum: ialbum.name];
                                
                                if( distantStudies)
                                {
                                    @synchronized(_albumNoOfStudiesCache)
                                    {
                                        if( currentDatabase == _database) // Did we switch the main database...
                                            [_distantAlbumNoOfStudiesCache setObject: distantStudies forKey: ialbum.name];
                                    }
                                }
                                
                                lastComputeAlbumsForDistantStudies = [NSDate timeIntervalSinceReferenceDate];
                            }
                            
                            for( DCMTKStudyQueryNode *distantStudy in distantStudies)
                            {
                                if( [localStudies containsObject: [distantStudy studyInstanceUID]] == NO)
                                {
                                    count++;
                                    
                                    if( autoretrieve)
                                        [studyToAutoretrieve addObject: distantStudy];
                                }
                            }
                            
                            if( autoretrievingPACSOnDemandSmartAlbum == NO && studyToAutoretrieve.count)
                            {
                                NSThread* t = [[[NSThread alloc] initWithTarget:self selector:@selector(autoretrievePACSOnDemandSmartAlbum:) object: studyToAutoretrieve] autorelease];
                                t.name = NSLocalizedString( @"Auto-Retrieving Album...", nil);
                                t.supportsCancel = YES;
                                [[ThreadsManager defaultManager] addThreadAndStart: t];
                            }
                        }
                        
                        count += localStudies.count;
                    }
                    @catch (NSException* e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                }
                else count = ialbum.studies.count;
                
                
                [NoOfStudies addObject: count >= 0 ? [decimalNumberFormatter stringForObjectValue:[NSNumber numberWithInt:count]] : @"#"];
                
                if( [NSDate timeIntervalSinceReferenceDate] - lastTime >= 1)
                {
                    lastTime = [NSDate timeIntervalSinceReferenceDate];
                    @synchronized(_albumNoOfStudiesCache)
                    {
                        int max = _albumNoOfStudiesCache.count;
                        if( max > NoOfStudies.count)
                            max = NoOfStudies.count;
                        [_albumNoOfStudiesCache replaceObjectsInRange: NSMakeRange( 0, max) withObjectsFromArray: NoOfStudies];
                    }
                    [albumTable performSelectorOnMainThread: @selector(reloadData) withObject: nil waitUntilDone: NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
                }
                
                if( [[NSThread currentThread] isCancelled])
                    break;
            }
            
            @synchronized (_albumNoOfStudiesCache)
            {
                [_albumNoOfStudiesCache removeAllObjects];
                if (currentDatabase == _database) // Did we switch the main database...
                    [_albumNoOfStudiesCache addObjectsFromArray:NoOfStudies];
            }
            
            [albumTable performSelectorOnMainThread: @selector(reloadData) withObject: nil waitUntilDone: NO  modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
        }
        @catch (NSException * e)
        {
            N2LogExceptionWithStackTrace(e);
        }
        @finally
        {
            _computingNumberOfStudiesForAlbums = NO;
        }
        }];
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    } @finally {
        [pool release];
    }
}

- (void)delayedRefreshAlbums
{
    [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(refreshAlbums) object:nil];
    [self performSelector:@selector(refreshAlbums) withObject:nil afterDelay:20];
}

- (void)refreshAlbums
{
    if( _database)
    {
        if( _computingNumberOfStudiesForAlbums)
            [self delayedRefreshAlbums];
        else
        {
            if ([[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"] == NO || [self.window isVisible]) // Server Mode: dont refresh albums
            {
                // Marked here, on the main thread, before the thread exists. The
                // thread used to mark it itself, and several started together
                // all found it clear: six counts ran at once during an import (#697).
                _computingNumberOfStudiesForAlbums = YES;
                [NSThread detachNewThreadSelector:@selector(_computeNumberOfStudiesForAlbumsThread) toTarget:self withObject: nil];
            }
        }
    }
}

- (void)refreshDatabase: (id)sender
{
    if( [[AppController sharedAppController] isSessionInactive] || waitForRunningProcess) return;
    if( _database == nil) return;
    //	if( bonjourDownloading) return;
    if( DatabaseIsEdited) return;
    if( [databaseOutline editedRow] != -1) return;
    
    NSArray *albumArray = self.albumArray;
    
    if( albumTable.selectedRow >= [albumArray count]) return;
    
    if( [[[albumArray objectAtIndex: albumTable.selectedRow] valueForKey:@"smartAlbum"] boolValue] == YES)
    {
        @try
        {
            [self outlineViewRefresh];
            [self refreshAlbums];
        }
        @catch (NSException * e)
        {
            N2LogExceptionWithStackTrace(e);
        }
    }
    else
    {
        //For filters depending on time....
        [self refreshAlbums];
        [databaseOutline reloadData];
        [comparativeTable reloadData];
    }
    
#ifndef OSIRIX_LIGHT
    if( [QueryController currentQueryController])
        [[QueryController currentQueryController] refresh: self];
    else if( [QueryController currentAutoQueryController])
        [[QueryController currentAutoQueryController] refresh: self];
#endif
}

- (NSArray*) childrenArray: (id)item onlyImages: (BOOL)onlyImages
{
#ifndef OSIRIX_LIGHT
    if( [item isDistant])
        return [NSArray array];
#endif
    
    if( [item isDeleted])
    {
        if( [item isDeleted])
            NSLog( @"----- isDeleted - childrenArray : we have to refresh the outlineView...");
        
        if( [item isDeleted] || item == nil)
            return [NSArray array];
    }
    
    if ([[item valueForKey:@"type"] isEqualToString:@"Series"])
    {
        //		[_database lock];
        
        NSArray *sortedArray = [item sortedImages];
        
        //		[_database unlock];
        
        return sortedArray;
    }
    
    if ([[item valueForKey:@"type"] isEqualToString:@"Study"])
    {
        //		[_database lock];
        
        NSArray *sortedArray = nil;
        @try
        {
            if( onlyImages) sortedArray = [item valueForKey:@"imageSeries"];
            else
            {
                sortedArray = [item valueForKey:@"allSeries"];
                
                // Put the ROI, Comments, Reports, ... at the end of the array
                NSMutableArray *resortedArray = [NSMutableArray arrayWithArray: sortedArray];
                NSMutableArray *SRArray = [NSMutableArray array];
                
                for( int i = 0 ; i < [resortedArray count]; i++)
                {
                    if( [DCMAbstractSyntaxUID isStructuredReport: [[resortedArray objectAtIndex: i] valueForKey:@"seriesSOPClassUID"]])
                        [SRArray addObject: [resortedArray objectAtIndex: i]];
                }
                
                [resortedArray removeObjectsInArray: SRArray];
                [resortedArray addObjectsFromArray: SRArray];
                
                sortedArray = resortedArray;
            }
        }
        @catch (NSException * e)
        {
            N2LogExceptionWithStackTrace(e);
        }
        
        //		[_database unlock];
        
        return sortedArray;
    }
    
    return nil;
}

- (NSArray*) childrenArray: (id) item
{
    return [self childrenArray: item onlyImages: YES];
}

- (NSArray*) imagesArray: (id) item preferredObject: (int) preferredObject onlyImages:(BOOL) onlyImages
{
    NSArray			*childrenArray = [self childrenArray: item onlyImages:onlyImages];
    NSMutableArray	*imagesPathArray = nil;
    
    if( childrenArray == nil)
        return nil;
    
    //	[_database lock];
    
    @try
    {
        if ([[item valueForKey:@"type"] isEqualToString:@"Series"])
        {
            imagesPathArray = [NSMutableArray arrayWithArray: childrenArray];
        }
        else if ([[item valueForKey:@"type"] isEqualToString:@"Study"])
        {
            imagesPathArray = [NSMutableArray arrayWithCapacity: [childrenArray count]];
            
            BOOL first = YES;
            
            for( id i in childrenArray)
            {
                int whichObject = preferredObject;
                
                if( preferredObject == oFirstForFirst)
                {
                    if( first == NO) preferredObject = oAny;
                }
                
                first = NO;
                
                if( preferredObject != oMiddle)
                {
                    if( [i primitiveValueForKey:@"thumbnail"] == nil)
                        whichObject = oMiddle;
                }
                
                switch( whichObject)
                {
                    case oAny:
                    {
                        NSManagedObject	*obj = [[i valueForKey:@"images"] anyObject];
                        if( obj) [imagesPathArray addObject: obj];
                    }
                        break;
                        
                    case oMiddle:
                    {
                        NSArray	*seriesArray = [self childrenArray: i onlyImages:onlyImages];
                        
                        // Get the middle image of the series
                        if( [seriesArray count] > 0)
                        {
                            if( [seriesArray count] > 1)
                                [imagesPathArray addObject: [seriesArray objectAtIndex: -1 + [seriesArray count]/2]];
                            else
                                [imagesPathArray addObject: [seriesArray objectAtIndex: [seriesArray count]/2]];
                        }
                    }
                        
                        break;
                        
                    case oFirstForFirst:
                    {
                        NSArray	*seriesArray = [self childrenArray: i onlyImages:onlyImages];
                        
                        // Get the middle image of the series
                        if( [seriesArray count] > 0)
                            [imagesPathArray addObject: [seriesArray objectAtIndex: 0]];
                    }
                        break;
                }
            }
        }
    }
    
    @catch (NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    //	[_database unlock];
    
    return imagesPathArray;
}

- (NSArray*) imagesArray: (id) item preferredObject: (int) preferredObject
{
    return [self imagesArray: item preferredObject: oAny onlyImages:YES];
}

- (NSArray*) imagesArray: (id) item onlyImages:(BOOL) onlyImages
{
    return [self imagesArray: item preferredObject: oAny onlyImages: onlyImages];
}

- (NSArray*) imagesArray: (id) item
{
    return [self imagesArray: item preferredObject: oAny];
}

- (NSArray*) imagesPathArray: (id) item
{
    return [[self imagesArray: item] valueForKey: @"completePath"];
}

- (NSManagedObject *)firstObjectForDatabaseOutlineSelection
{
    NSManagedObject *aFile = [databaseOutline itemAtRow:[databaseOutline selectedRow]];
    
    //	[_database lock];
    
    if( [[aFile valueForKey:@"type"] isEqualToString:@"Study"])
        aFile = [[aFile valueForKey:@"series"] anyObject];
    
    if( [[aFile valueForKey:@"type"] isEqualToString:@"Series"])
        aFile = [[aFile valueForKey:@"images"] anyObject];
    
    //	[_database unlock];
    
    return aFile;
}

#define BONJOURPACKETS 50

- (NSMutableArray*)filesForDatabaseOutlineSelection:(NSMutableArray*)correspondingManagedObjects treeObjects:(NSMutableSet*)treeManagedObjects onlyImages:(BOOL)onlyImages
{
    NSMutableArray *selectedFiles = [NSMutableArray array];
    NSIndexSet *rowEnumerator = [databaseOutline selectedRowIndexes];
    
    if( cachedFilesForDatabaseOutlineSelectionIndex && [[databaseOutline selectedRowIndexes] isEqualToIndexSet: cachedFilesForDatabaseOutlineSelectionIndex] && onlyImages == YES)
    {
        [selectedFiles addObjectsFromArray: cachedFilesForDatabaseOutlineSelectionSelectedFiles];
        
        if( correspondingManagedObjects)
            [correspondingManagedObjects addObjectsFromArray: cachedFilesForDatabaseOutlineSelectionCorrespondingObjects];
        if( treeManagedObjects)
            [treeManagedObjects addObjectsFromArray: cachedFilesForDatabaseOutlineSelectionTreeObjects.allObjects];
        
        return selectedFiles;
    }
    
    NSManagedObjectContext	*context = self.database.managedObjectContext;
    
    if( correspondingManagedObjects == nil) correspondingManagedObjects = [NSMutableArray array];
    if( treeManagedObjects == nil) treeManagedObjects = [NSMutableSet set];
    
    [context retain];
    N2ManagedObjectContextPerformAndWait(context, ^{
    
    @try
    {
        for (NSUInteger row = [rowEnumerator firstIndex]; row != NSNotFound; row = [rowEnumerator indexGreaterThanIndex: row])
        {
            NSManagedObject *curObj = [databaseOutline itemAtRow: row];
            
            if( [curObj isKindOfClass: [NSManagedObject class]]) // not a distant study
            {
                if( [[curObj valueForKey:@"type"] isEqualToString:@"Series"])
                {
                    @autoreleasepool {
                        NSArray	*imagesArray = [self imagesArray: curObj onlyImages: onlyImages];
                        
                        [correspondingManagedObjects addObjectsFromArray: imagesArray];
                    }
                }
                
                if( [[curObj valueForKey:@"type"] isEqualToString:@"Study"])
                {
                    @autoreleasepool {
                        NSArray	*seriesArray = [self childrenArray: curObj onlyImages: onlyImages];
                        
                        int totImage = 0;
                        DicomSeries* dontDelete = nil;
                        
                        for (DicomSeries* obj in seriesArray)
                        {
                            NSArray	*imagesArray = [self imagesArray: obj onlyImages: onlyImages];
                            
                            totImage += [imagesArray count];
                            
                            [correspondingManagedObjects addObjectsFromArray: imagesArray];
                            
                            if ([obj.name isEqualToString:@"OsiriX No Autodeletion"] && obj.id.intValue == 5005)
                                dontDelete = obj;
                        }
                        
                        if (totImage && dontDelete) // there are images, remove the "OsiriX No Autodeletion" series
                            [context deleteObject:dontDelete];
                        
                        if (onlyImages == NO && totImage == 0 && dontDelete == nil) // We don't want empty studies, unless the "OsiriX No Autodeletion" series is there...
                            [context deleteObject: curObj];
                    }
                }
                
                if (![curObj isDeleted])
                    [treeManagedObjects addObject:curObj];
            }
        }
        
        [correspondingManagedObjects removeDuplicatedObjects];
        
        if (![_database isLocal])
        {
            Wait *splash = [[Wait alloc] initWithString: NSLocalizedString(@"Downloading files...", nil)];
            [splash showWindow:self];
            [splash setCancel: YES];
            
            [[splash progress] setMaxValue: [correspondingManagedObjects count]];
            
            for( NSManagedObject *obj in correspondingManagedObjects)
            {
                if( [splash aborted] == NO)
                {
                    @autoreleasepool
                    {
                        NSString *p = [self getLocalDCMPath: obj :BONJOURPACKETS];
                        
                        [selectedFiles addObject: p];
                        
                        [splash incrementBy: 1];
                    }
                }
            }
            
            if( [splash aborted])
            {
                [selectedFiles removeAllObjects];
                [correspondingManagedObjects removeAllObjects];
            }
            
            [splash close];
            [splash autorelease];
        }
        else
        {
            [selectedFiles addObjectsFromArray: [correspondingManagedObjects valueForKey: @"completePath"]];
        }
        
        if( [correspondingManagedObjects count] != [selectedFiles count])
            NSLog(@"****** WARNING [correspondingManagedObjects count] != [selectedFiles count]");
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    [context save: nil];
    });
    [context release];
    
    if( onlyImages)
    {
        [cachedFilesForDatabaseOutlineSelectionSelectedFiles release];
        [cachedFilesForDatabaseOutlineSelectionCorrespondingObjects release];
        [cachedFilesForDatabaseOutlineSelectionTreeObjects release];
        [cachedFilesForDatabaseOutlineSelectionIndex release];
        
        cachedFilesForDatabaseOutlineSelectionIndex = [[NSIndexSet alloc] initWithIndexSet: [databaseOutline selectedRowIndexes]];
        cachedFilesForDatabaseOutlineSelectionSelectedFiles = [[NSMutableArray alloc] initWithArray:selectedFiles];
        cachedFilesForDatabaseOutlineSelectionTreeObjects = [[NSMutableSet alloc] initWithSet:treeManagedObjects];
        cachedFilesForDatabaseOutlineSelectionCorrespondingObjects = [[NSMutableArray alloc] initWithArray:correspondingManagedObjects];
    }
    
    return selectedFiles;
}

- (NSMutableArray*)filesForDatabaseOutlineSelection:(NSMutableArray*)correspondingManagedObjects onlyImages:(BOOL)onlyImages {
    return [self filesForDatabaseOutlineSelection:correspondingManagedObjects treeObjects:nil onlyImages:onlyImages];
}

- (NSMutableArray *)filesForDatabaseOutlineSelection :(NSMutableArray*) correspondingManagedObjects
{
    return [self filesForDatabaseOutlineSelection:correspondingManagedObjects onlyImages: YES];
}

- (void) resetROIsAndKeysButton
{
    ROIsAndKeyImagesButtonAvailable = NO;
    
    NSMutableArray *i = [NSMutableArray arrayWithArray: [[toolbar items] valueForKey: @"itemIdentifier"]];
    if( [i containsObject: OpenKeyImagesAndROIsToolbarItemIdentifier] && [_database isLocal])
    {
        if( [[databaseOutline selectedRowIndexes] count] >= 5)	//[[self window] firstResponder] == databaseOutline &&
            ROIsAndKeyImagesButtonAvailable = YES;
        else
        {
            NSEvent *event = [[NSApplication sharedApplication] currentEvent];
            
            if([event modifierFlags] & NSEventModifierFlagOption)
            {
                if( [[self KeyImages: nil] count] == 0) ROIsAndKeyImagesButtonAvailable = NO;
                else ROIsAndKeyImagesButtonAvailable = YES;
            }
            else if([event modifierFlags] & NSEventModifierFlagShift)
            {
                if( [[self ROIImages: nil] count] == 0) ROIsAndKeyImagesButtonAvailable = NO;
                else ROIsAndKeyImagesButtonAvailable = YES;
            }
            else
            {
                if( [[self ROIsAndKeyImages: nil] count] == 0) ROIsAndKeyImagesButtonAvailable = NO;
                else ROIsAndKeyImagesButtonAvailable = YES;
            }
        }
    }
}

+ (NSArray*) comparativeServers
{
    NSMutableArray* servers = [NSMutableArray array];
    NSArray* sources = [DCMNetServiceDelegate DICOMServersList];
    NSMutableArray* comparativeNodesDescription = [NSMutableArray array];
    NSMutableArray* comparativeNodesAddress = [NSMutableArray array];
    for( NSDictionary *si in [[NSUserDefaults standardUserDefaults] arrayForKey: @"comparativeSearchDICOMNodes"])
    {
        if( [[si valueForKey: @"server"] valueForKey: @"Description"])
            [comparativeNodesDescription addObject: [[si valueForKey: @"server"] valueForKey: @"Description"]];
        
        if( [[si valueForKey: @"server"] valueForKey: @"Address"])
            [comparativeNodesAddress addObject: [[si valueForKey: @"server"] valueForKey: @"Address"]];
    }
    
    if( comparativeNodesDescription.count != comparativeNodesAddress.count)
        NSLog( @"**** comparativeNodesDescription.count != comparativeNodesAddress.count");
    else
    {
        for( int x = 0; x < comparativeNodesDescription.count; x++)
        {
            NSString *description = [comparativeNodesDescription objectAtIndex: x];
            NSString *address = [comparativeNodesAddress objectAtIndex: x];
            
            for (NSDictionary* si in sources)
            {
                if( [description isEqualToString: [si objectForKey:@"Description"]] && [address isEqualToString: [si objectForKey:@"Address"]])
                    [servers addObject: si];
            }
        }
    }
    
    return servers;
}

+ (NSString*) stringForSearchType:(int) curSearchType
{
    switch( curSearchType)
    {
        case 7:			// All fields -> Use only the Patient Name for distant nodes
        case 0:			// Patient Name
            return NSLocalizedString( @"Patient Name", nil);
            break;
            
        case 1:			// Patient ID
            return NSLocalizedString( @"Patient ID", nil);
            break;
            
        case 2:			// Study ID
            return NSLocalizedString( @"Study ID", nil);
            break;
            
        case 3:			// Comments
            return NSLocalizedString( @"Comments", nil);
            break;
            
        case 4:			// Study Description
            return NSLocalizedString( @"Study Description", nil);
            break;
            
        case 11:
            return NSLocalizedString(@"Series Description", nil);

        case 5:			// Modality
            return NSLocalizedString( @"Modality", nil);
            break;
            
        case 6:			// Accession Number
            return NSLocalizedString( @"AccessionNumber", nil);
            break;
    }
    
    return @"";
}

- (NSArray*) distantStudiesForSearchString: (NSString*) curSearchString type:(int) curSearchType
{
    // Series-level local filtering cannot be expressed by this Study Root query.
    if (curSearchType == 11) return [NSArray array];

#ifndef OSIRIX_LIGHT
    if( !searchForComparativeStudiesLock)
        searchForComparativeStudiesLock = [NSRecursiveLock new];
    
    [searchForComparativeStudiesLock lock];
    
    @try
    {
        NSArray *servers = [BrowserController comparativeServers];
        
        // Distant studies
        NSMutableDictionary *d = [NSMutableDictionary dictionary];
        
        switch( curSearchType)
        {
            case 7:			// All fields -> Use only the Patient Name for distant nodes
            case 0:			// Patient Name
                curSearchString = [curSearchString stringByReplacingOccurrencesOfString: @", " withString: @" "];
                curSearchString = [curSearchString stringByReplacingOccurrencesOfString: @"," withString: @" "];
                
                [d setObject: [curSearchString stringByAppendingString:@"*"] forKey: @"PatientsName"];
                break;
                
            case 1:			// Patient ID
                [d setObject: curSearchString forKey: @"PatientID"];
                break;
                
            case 2:			// Study ID
                [d setObject: curSearchString forKey: @"StudyID"];
                break;
                
            case 3:			// Comments
                [d setObject: [curSearchString stringByAppendingString:@"*"] forKey: @"Comments"];
                break;
                
            case 4:			// Study Description
                [d setObject: [curSearchString stringByAppendingString:@"*"] forKey: @"StudyDescription"];
                break;
                
            case 5:			// Modality
                [d setObject: [NSArray arrayWithObject: curSearchString] forKey: @"modality"];
                break;
                
            case 6:			// Accession Number
                [d setObject: curSearchString forKey: @"AccessionNumber"];
                break;
        }
        
        // Modality Filter?
        if( [modalityFilterMenu indexOfSelectedItem] > 0 && self.modalityFilter.length)
            [d setObject: [NSArray arrayWithObject: self.modalityFilter] forKey: @"modality"];
        
        NSArray *result = [QueryController queryStudiesForFilters: d servers: servers showErrors: NO];
        
        if(( curSearchType == 0 || curSearchType == 7) && [[curSearchString componentsSeparatedByString: @" "] count] > 1) // For patient name, if several components, try with ^ separator, and add missing results
        {
            NSString *s = [curSearchString stringByAppendingString:@"*"];
            
            // replace last occurence // fan siu hung
            s = [s stringByReplacingCharactersInRange: [s rangeOfString: @" " options: NSBackwardsSearch] withString: @"^"];
            
            [d setObject: s forKey: @"PatientsName"];
            
            NSArray *subResult = [QueryController queryStudiesForFilters: d servers: servers showErrors: NO];
            
            NSArray *resultUIDs = [result valueForKey: @"uid"];
            
            for( DCMTKQueryNode *n in subResult)
            {
                if( [resultUIDs containsObject: n.uid] == NO)
                    result = [result arrayByAddingObject: n];
            }
        }
        
        return result;
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [searchForComparativeStudiesLock unlock];
    }
#endif
    return nil;
}

- (void) searchForSearchField: (NSDictionary*) dict
{
    if( self.database == nil)
        return;
    
    if( self.database.isReadOnly || !self.database.isLocal)
        return;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForComparativeStudiesOnDICOMNodes"] == NO)
        return;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"PACSOnDemandForSearchField"] == NO)
        return;
    
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    
    int selectedAlbumIndex = [[dict objectForKey: @"selectedAlbumIndex"] intValue];
    int curSearchType = [[dict objectForKey: @"searchType"] intValue];
    NSString *curSearchString = [dict objectForKey: @"searchString"];
    
    [NSThread currentThread].name = NSLocalizedString( @"Search For Search Field...", nil);
    
    if( curSearchType == searchType && [curSearchString isEqualToString: _searchString]) // There was maybe other locks in the queue...
    {
        NSLog( @"Search For %@: %@", [BrowserController stringForSearchType: curSearchType], curSearchString);
        
        if( [curSearchString length] > 2 || (_searchString.length >= 2 && searchType == 5))
        {
            if( !searchForComparativeStudiesLock)
                searchForComparativeStudiesLock = [NSRecursiveLock new];
            
            @synchronized( smartAlbumDistantArraySync)
            {
                if( smartAlbumDistantSearchArray == nil)
                    smartAlbumDistantSearchArray = [[NSMutableArray alloc] init];
                
                [smartAlbumDistantSearchArray addObject: [NSThread currentThread]];
                distantSearchThread = [[NSThread currentThread] retain];
            }
            
            [searchForComparativeStudiesLock lock];
            
            if( curSearchType == searchType && [curSearchString isEqualToString: _searchString] && [[NSThread currentThread] isCancelled] == NO) // There was maybe other locks in the queue...
            {
                id lastObjectInQueue = nil;
                
                @synchronized( smartAlbumDistantArraySync)
                {
                    lastObjectInQueue = [smartAlbumDistantSearchArray lastObject];
                }
                
                if( [NSThread currentThread] == lastObjectInQueue)
                {
                    [NSThread currentThread].name = [NSString stringWithFormat: NSLocalizedString( @"Search %@: %@", nil), [BrowserController stringForSearchType: curSearchType], curSearchString];
                    [[ThreadsManager defaultManager] addThreadAndStart: [NSThread currentThread]];
                    
                    @try
                    {
                        NSArray *array = [self distantStudiesForSearchString: curSearchString type: curSearchType];
                        
                        if( selectedAlbumIndex == 0)
                        {
                            @synchronized( smartAlbumDistantArraySync)
                            {
                                [smartAlbumDistantArray release];
                                smartAlbumDistantArray = [array retain];
                            }
                        }
                        else distantEntireDBResultCount = array.count;
                        
                        self.distantSearchString = curSearchString;
                        self.distantSearchType = curSearchType;
                        
                        if( curSearchType == searchType && [curSearchString isEqualToString: _searchString]) // There were maybe other locks in the queue...
                        {
                            if( selectedAlbumIndex == 0)
                                [self performSelectorOnMainThread: @selector(_refreshDatabaseDisplay) withObject: nil waitUntilDone: NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
                            else
                                [self performSelectorOnMainThread: @selector(refreshEntireDBResult) withObject: nil waitUntilDone: NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
                        }
                    }
                    @catch (NSException* e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                }
            }
            
            @synchronized( smartAlbumDistantArraySync)
            {
                [smartAlbumDistantSearchArray removeObject: [NSThread currentThread]];
            }
            
            [searchForComparativeStudiesLock unlock];
        }
    }
    
    [pool release];
}

- (NSArray*) distantStudiesForIntervalFrom: (NSDate*) from to:(NSDate*) to
{
#ifndef OSIRIX_LIGHT
    if( !searchForComparativeStudiesLock)
        searchForComparativeStudiesLock = [NSRecursiveLock new];
    
    [searchForComparativeStudiesLock lock];
    
    @try
    {
        NSArray *servers = [BrowserController comparativeServers];
        
        // Distant studies
        NSMutableDictionary *d = [NSMutableDictionary dictionary];
        
        if( from && to)
            [d setObject: [NSNumber numberWithInt: between] forKey: @"date"];
        else if( from)
            [d setObject: [NSNumber numberWithInt: after] forKey: @"date"];
        
        [d setObject: from forKey: @"fromDate"];
        
        if( to)
            [d setObject: to forKey: @"toDate"];
        
        // Modality Filter?
        if( [modalityFilterMenu indexOfSelectedItem] > 0 && self.modalityFilter.length)
            [d setObject: [NSArray arrayWithObject: self.modalityFilter] forKey: @"modality"];
        
        return [QueryController queryStudiesForFilters: d servers: servers showErrors: NO];
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [searchForComparativeStudiesLock unlock];
    }
#endif
    return nil;
}

- (void) searchForTimeIntervalFromTo: (NSDictionary*) dict
{
    if( self.database == nil)
        return;
    
    if( self.database.isReadOnly)
        return;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForComparativeStudiesOnDICOMNodes"] == NO)
        return;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"PACSOnDemandForSearchField"] == NO)
        return;
    
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    
    NSDate* from = [dict objectForKey: @"from"];
    NSDate* to = [dict objectForKey: @"to"];
    
    [NSThread currentThread].name = @"Search For Time Interval Studies";
    
    if( [from isEqualToDate: timeIntervalStart] && (to == nil || [to isEqualToDate: timeIntervalEnd])) // There was maybe other locks in the queue...
    {
        NSLog( @"Search time interval: %@ to %@", from, to);
        
        {
            if( !searchForComparativeStudiesLock)
                searchForComparativeStudiesLock = [NSRecursiveLock new];
            
            @synchronized( smartAlbumDistantArraySync)
            {
                if( smartAlbumDistantSearchArray == nil)
                    smartAlbumDistantSearchArray = [[NSMutableArray alloc] init];
                
                [smartAlbumDistantSearchArray addObject: [NSThread currentThread]];
                distantSearchThread = [[NSThread currentThread] retain];
            }
            
            [searchForComparativeStudiesLock lock];
            
            if( [from isEqualToDate: timeIntervalStart] && (to == nil || [to isEqualToDate: timeIntervalEnd]) && [[NSThread currentThread] isCancelled] == NO) // There was maybe other locks in the queue...
            {
                id lastObjectInQueue = nil;
                
                @synchronized( smartAlbumDistantArraySync)
                {
                    lastObjectInQueue = [smartAlbumDistantSearchArray lastObject];
                }
                
                if( [NSThread currentThread] == lastObjectInQueue)
                {
                    [NSThread currentThread].name = NSLocalizedString( @"Search Time Interval...", nil);
                    [[ThreadsManager defaultManager] addThreadAndStart: [NSThread currentThread]];
                    
                    @try
                    {
                        NSArray *array = [self distantStudiesForIntervalFrom: from to: to];
                        @synchronized( smartAlbumDistantArraySync)
                        {
                            [smartAlbumDistantArray release];
                            smartAlbumDistantArray = [array retain];
                        }
                        
                        self.distantTimeIntervalStart = from;
                        self.distantTimeIntervalEnd = to;
                        
                        if( [from isEqualToDate: timeIntervalStart] && (to == nil || [to isEqualToDate: timeIntervalEnd])) // There was maybe other locks in the queue...
                            [self performSelectorOnMainThread: @selector(_refreshDatabaseDisplay) withObject: nil waitUntilDone: NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
                    }
                    @catch (NSException* e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                }
            }
            
            @synchronized( smartAlbumDistantArraySync)
            {
                [smartAlbumDistantSearchArray removeObject: [NSThread currentThread]];
            }
            
            [searchForComparativeStudiesLock unlock];
        }
    }
    
    [pool release];
}

- (NSArray*) distantStudiesForSmartAlbum: (NSString*) albumName
{
    if( self.database.isReadOnly || !self.database.isLocal)
        return [NSArray array];
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForComparativeStudiesOnDICOMNodes"] == NO)
        return [NSArray array];
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForSmartAlbumStudiesOnDICOMNodes"] == NO)
        return [NSArray array];
    
#ifndef OSIRIX_LIGHT
    if( !searchForComparativeStudiesLock)
        searchForComparativeStudiesLock = [NSRecursiveLock new];
    
    [searchForComparativeStudiesLock lock];
    
    @try
    {
        NSArray *servers = [BrowserController comparativeServers];
        
        // Distant studies
        // In current versions, two filters exist: modality & date
        for( NSDictionary *d in [[NSUserDefaults standardUserDefaults] objectForKey: @"smartAlbumStudiesDICOMNodes"])
        {
            if( [[d valueForKey: @"activated"] boolValue] && [albumName isEqualToString: [d valueForKey: @"name"]])
            {
                return [QueryController queryStudiesForFilters: d servers: servers showErrors: NO];
            }
        }
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [searchForComparativeStudiesLock unlock];
    }
#endif
    return nil;
}

- (void) searchForSmartAlbumDistantStudies: (NSString*) albumName
{
    if( self.database == nil)
        return;
    
    if( self.database.isReadOnly || !self.database.isLocal)
        return;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForComparativeStudiesOnDICOMNodes"] == NO)
        return;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForSmartAlbumStudiesOnDICOMNodes"] == NO)
        return;
    
    if( albumName.length == 0)
        return;
    
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    
    [NSThread currentThread].name = @"Search For Smart Album Distant Studies";
    
    if( [albumName isEqualToString: self.selectedAlbumName]) // There was maybe other locks in the queue...
    {
        NSLog( @"Search album: %@", albumName);
        
        lastRefreshSmartAlbumDistantStudies = [NSDate timeIntervalSinceReferenceDate];
        
        {
            if( !searchForComparativeStudiesLock)
                searchForComparativeStudiesLock = [NSRecursiveLock new];
            
            @synchronized( smartAlbumDistantArraySync)
            {
                if( smartAlbumDistantSearchArray == nil)
                    smartAlbumDistantSearchArray = [[NSMutableArray alloc] init];
                
                for( NSThread *t in smartAlbumDistantSearchArray)
                    [t setIsCancelled: YES];
                
                [smartAlbumDistantSearchArray addObject: [NSThread currentThread]];
            }
            
            [searchForComparativeStudiesLock lock];
            
            if( [albumName isEqualToString: self.selectedAlbumName] && [[NSThread currentThread] isCancelled] == NO) // There was maybe other locks in the queue...
            {
                id lastObjectInQueue = nil;
                
                @synchronized( smartAlbumDistantArraySync)
                {
                    lastObjectInQueue = [smartAlbumDistantSearchArray lastObject];
                }
                
                if( [NSThread currentThread] == lastObjectInQueue)
                {
                    [NSThread currentThread].name = [NSString stringWithFormat: NSLocalizedString( @"Search Smart Album...", nil), albumName];
                    [[ThreadsManager defaultManager] addThreadAndStart: [NSThread currentThread]];
                    
                    @try
                    {
                        NSArray *array = [self distantStudiesForSmartAlbum: albumName];
                        
                        @synchronized( smartAlbumDistantArraySync)
                        {
                            [smartAlbumDistantArray release];
                            smartAlbumDistantArray = [array retain];
                        }
                        
                        self.smartAlbumDistantName = albumName;
                        
                        if( [albumName isEqualToString: self.selectedAlbumName])
                            [self performSelectorOnMainThread: @selector(_refreshDatabaseDisplay) withObject: nil waitUntilDone: NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
                    }
                    @catch (NSException* e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                }
            }
            
            @synchronized( smartAlbumDistantArraySync)
            {
                [smartAlbumDistantSearchArray removeObject: [NSThread currentThread]];
            }
            
            [searchForComparativeStudiesLock unlock];
        }
    }
    
    [pool release];
}

- (NSArray*) subSearchForComparativeStudies: (id) studySelectedID
{
    // The UI's database on the main thread; elsewhere a private-queue one, and
    // the search runs on its queue (#966). The main thread takes the studies
    // by object ID (-refreshComparativeStudies:).
    DicomDatabase *idatabase = [NSThread isMainThread] ? self.database : self.database.privateQueueIndependentDatabase;
    __block NSArray *result = nil;
    [idatabase performBlockAndWait:^{
        result = [[self subSearchForComparativeStudies: studySelectedID inDatabase: idatabase] retain];
    }];
    return [result autorelease];
}

- (NSArray*) subSearchForComparativeStudies: (id) studySelectedID inDatabase: (DicomDatabase*) idatabase
{
    @try
    {
        NSMutableArray *mergedStudies = nil;
        
        DicomStudy *studySelected = nil;
        
        if( [studySelectedID isKindOfClass: [NSManagedObjectID class]])
            studySelected = [idatabase objectWithID: studySelectedID];
        else
            studySelected = studySelectedID; //DCMTKStudyQueryNode
        
        if( studySelected.patientUID.length == 0)
            return nil;
        
        [NSThread currentThread].name = @"Search For Comparative Studies";
        
        if( self.comparativePatientUID && [self.comparativePatientUID compare: studySelected.patientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame) // There was maybe other locks in the queue... Keep only the displayed patientUID
        {
            lastRefreshComparativeStudies = [NSDate timeIntervalSinceReferenceDate];
            
            @try
            {
                // Local studies
                __block NSArray *localStudies = nil;
                N2ManagedObjectContextPerformAndWait(idatabase.managedObjectContext, ^{
                @try
                {
                    // The published contract limits this search and keeps the
                    // most recent studies: a patient with a long history must
                    // not make the browser fetch and hold everything (#380 C).
                    NSFetchRequest *request = [[[NSFetchRequest alloc] init] autorelease];
                    request.entity = idatabase.studyEntity;
                    request.predicate = [NSPredicate predicateWithFormat: @"(patientUID ==[cd] %@)", studySelected.patientUID];
                    request.sortDescriptors = [NSArray arrayWithObject: [NSSortDescriptor sortDescriptorWithKey: @"date" ascending: NO]];
                    NSInteger comparativeLimit = [HorosAssociationContract relatedStudiesLimitIn: [NSUserDefaults standardUserDefaults]];
                    if( comparativeLimit > 0)
                        request.fetchLimit = comparativeLimit;
                    localStudies = [[idatabase.managedObjectContext executeFetchRequest: request error: nil] retain];
                    if( comparativeLimit > 0 && (NSInteger) localStudies.count >= comparativeLimit)
                        NSLog( @"Comparative studies: kept the %ld most recent of this patient's studies (%@ = %ld)",
                              (long) comparativeLimit, HorosAssociationContract.relatedStudiesLimitKey, (long) comparativeLimit);
                }
                @catch (NSException* e)
                {
                    NSLog( @"*** Comparative Studies exception: %@", e);
                }
                });
                
                [localStudies autorelease];
                mergedStudies = [NSMutableArray arrayWithArray: localStudies];
                [mergedStudies sortUsingDescriptors: [NSArray arrayWithObject: [NSSortDescriptor sortDescriptorWithKey:@"date" ascending: NO]]];
                
                if( self.comparativePatientUID && [self.comparativePatientUID compare: studySelected.patientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
                    [self performSelectorOnMainThread: @selector(refreshComparativeStudies:) withObject: mergedStudies waitUntilDone: NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]]; // Already display the local studies, we will display the merged studies later
            }
            @catch (NSException* e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForComparativeStudiesOnDICOMNodes"] && !self.database.isReadOnly && self.database.isLocal)
            {
                if( !searchForComparativeStudiesLock)
                    searchForComparativeStudiesLock = [NSRecursiveLock new];
                
                @synchronized( smartAlbumDistantArraySync)
                {
                    if( comparativeStudySearchArray == nil)
                        comparativeStudySearchArray = [[NSMutableArray alloc] init];
                    
                    for( NSThread *t in comparativeStudySearchArray)
                        [t setIsCancelled: YES];
                    
                    [comparativeStudySearchArray addObject: [NSThread currentThread]];
                }
                
                [searchForComparativeStudiesLock lock];
                if( self.comparativePatientUID && [self.comparativePatientUID compare: studySelected.patientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame && [[NSThread currentThread] isCancelled] == NO) // There was maybe other locks in the queue... Keep only the displayed patientUID
                {
                    id lastObjectInQueue = nil;
                    
                    @synchronized( smartAlbumDistantArraySync)
                    {
                        lastObjectInQueue = [comparativeStudySearchArray lastObject];
                    }
                    
                    if( [NSThread currentThread] == lastObjectInQueue)
                    {
                        [NSThread currentThread].name = [NSString stringWithFormat: NSLocalizedString( @"Search History: %@", nil), studySelected.name];
                        [[ThreadsManager defaultManager] addThreadAndStart: [NSThread currentThread]];
                        
                        @try
                        {
                            NSArray *distantStudies = nil;
                            
                            BOOL usePatientID = [[NSUserDefaults standardUserDefaults] boolForKey: @"UsePatientIDForUID"];
                            BOOL usePatientBirthDate = [[NSUserDefaults standardUserDefaults] boolForKey: @"UsePatientBirthDateForUID"];
                            BOOL usePatientName = [[NSUserDefaults standardUserDefaults] boolForKey: @"UsePatientNameForUID"];
                            
                            // Servers
                            NSArray *servers = [BrowserController comparativeServers];
                            
                            if( servers.count)
                            {
                                // Distant studies
#ifndef OSIRIX_LIGHT
                                distantStudies = [QueryController queryStudiesForPatient: studySelected usePatientID: usePatientID usePatientName: usePatientName usePatientBirthDate: usePatientBirthDate servers: servers showErrors: NO];
                                
                                // Merge local and distant studies
                                NSMutableArray *studyToAutoretrieve = [NSMutableArray array];
                                for( DCMTKStudyQueryNode *distantStudy in distantStudies)
                                {
                                    if( [[mergedStudies valueForKey: @"studyInstanceUID"] containsObject: [distantStudy studyInstanceUID]] == NO)
                                    {
                                        [mergedStudies addObject: distantStudy];
                                    }
                                    else if( [[NSUserDefaults standardUserDefaults] boolForKey: @"preferStudyWithMoreImages"])
                                    {
                                        BOOL inTheRetrieveQueue = NO;
                                        
                                        //Is this study in the retrieve queue? Display the local study
                                        @synchronized( comparativeRetrieveQueue)
                                        {
                                            inTheRetrieveQueue = [[comparativeRetrieveQueue valueForKey: @"studyInstanceUID"] containsObject: [distantStudy studyInstanceUID]];
                                        }
                                        
                                        if( inTheRetrieveQueue == NO)
                                        {
                                            NSUInteger index = [[mergedStudies valueForKey: @"studyInstanceUID"] indexOfObject: [distantStudy studyInstanceUID]];
                                            
                                            if( index != NSNotFound && [[[mergedStudies objectAtIndex: index] rawNoFiles] intValue] < [[distantStudy noFiles] intValue])
                                            {
                                                [mergedStudies replaceObjectAtIndex: index withObject: distantStudy];
                                                
                                                if( [[NSUserDefaults standardUserDefaults] boolForKey: @"automaticallyRetrievePartialStudies"])
                                                    [studyToAutoretrieve addObject: distantStudy];
                                            }
                                        }
                                    }
                                }
                                
                                if( studyToAutoretrieve.count)
                                {
                                    NSThread* t = [[[NSThread alloc] initWithTarget:self selector:@selector(autoretrievePACSOnDemandSmartAlbum:) object: studyToAutoretrieve] autorelease];
                                    t.name = NSLocalizedString( @"Auto-Retrieving...", nil);
                                    t.supportsCancel = YES;
                                    [[ThreadsManager defaultManager] addThreadAndStart: t];
                                }
#endif
                            }
                            
                            [mergedStudies sortUsingDescriptors: [NSArray arrayWithObject: [NSSortDescriptor sortDescriptorWithKey:@"date" ascending: NO]]];
                            
                            if( self.comparativePatientUID && [self.comparativePatientUID compare: studySelected.patientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
                            {
                                [self performSelectorOnMainThread: @selector(refreshComparativeStudiesAndCheck:) withObject: mergedStudies waitUntilDone: NO modes:[NSArray arrayWithObject:NSRunLoopCommonModes]];
                            }
                        }
                        @catch (NSException* e)
                        {
                            N2LogExceptionWithStackTrace(e);
                        }
                    }
                }
                
                @synchronized( smartAlbumDistantArraySync)
                {
                    [comparativeStudySearchArray removeObject: [NSThread currentThread]];
                }
                
                [searchForComparativeStudiesLock unlock];
            }
        }
        
        return mergedStudies;
    }
    @catch (NSException *e) {
        N2LogException( e);
    }
}

- (void) searchForComparativeStudies: (id) studySelectedID
{
    if( self.database == nil)
        return;
    
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    
    [self subSearchForComparativeStudies: studySelectedID];
    
    [pool release];
}

- (IBAction) refreshPACSOnDemandResults:(id) sender
{
    self.comparativePatientUID = nil;
    self.comparativeStudies = nil;
    
    @synchronized( smartAlbumDistantArraySync)
    {
        [smartAlbumDistantArray release];
        smartAlbumDistantArray = nil;
    }
    
    self.smartAlbumDistantName = nil;
    
    [previousItem release];
    previousItem = nil;
    
    [[NSNotificationCenter defaultCenter] postNotificationName: NSTableViewSelectionDidChangeNotification object:albumTable userInfo: nil];
    [[NSNotificationCenter defaultCenter] postNotificationName: NSOutlineViewSelectionDidChangeNotification object:databaseOutline userInfo: nil];
}

- (void) refreshComparativeStudiesAndCheck:(NSArray *)newStudies
{
    [self refreshComparativeStudies: newStudies];
    [self checkIfLocalStudyHasMoreOrSameNumberOfImagesOfADistantStudy: nil];
}

- (void) refreshComparativeStudies: (NSArray*) newStudies
{
    if( [NSThread isMainThread] == NO)
        N2LogStackTrace( @"***** We must be on MAIN thread");
    
    if( _database == nil)
        return;
    
    NSManagedObject *item = [databaseOutline itemAtRow: [[databaseOutline selectedRowIndexes] firstIndex]];
    DicomStudy *studySelected = [[item valueForKey: @"type"] isEqualToString: @"Study"] ? item : [item valueForKey: @"study"];
    
    if( item)
    {
        dontSelectStudyFromComparativeStudies = YES;
        
        NSMutableArray *mainContextStudies = [NSMutableArray array];
        for( id study in newStudies)
        {
            if( [study isKindOfClass: [DicomStudy class]])
            {
                id obj = [self.database objectWithID: [(NSManagedObject *)study objectID]];
                if( obj)
                    [mainContextStudies addObject: obj];
            }
            else
                [mainContextStudies addObject: study];
        }
        
        self.comparativeStudies = mainContextStudies;
        [comparativeTable reloadData];
        
        if( studySelected.name)
            [[[comparativeTable tableColumnWithIdentifier:@"Cell"] headerCell] setStringValue: studySelected.name];
        
        NSUInteger index = [[self.comparativeStudies valueForKey: @"studyInstanceUID"] indexOfObject: [studySelected valueForKey: @"studyInstanceUID"]];
        
        dontSelectStudyFromComparativeStudies = NO;
        
        if( index != NSNotFound)
            [comparativeTable selectRowIndexes: [NSIndexSet indexSetWithIndex: index] byExtendingSelection: NO];
        else
            [comparativeTable selectRowIndexes: [NSIndexSet indexSetWithIndex: 0] byExtendingSelection: NO];
        
        for( ViewerController *v in [ViewerController getDisplayed2DViewers])
            [v comparativeRefresh: self.comparativePatientUID];
        
        [comparativeTable scrollRowToVisible: [comparativeTable selectedRow]];
    }
    else
    {
        self.comparativeStudies = nil;
        [comparativeTable reloadData];
    }
}

- (void) refreshComparativeStudiesIfNeeded:(id) timer
{
    if( timer == nil)
        lastRefreshComparativeStudies = 0;
    
    if( [NSDate timeIntervalSinceReferenceDate] - lastRefreshComparativeStudies > 3 * 60) // 3 min
    {
        NSManagedObject *item = [databaseOutline itemAtRow: [[databaseOutline selectedRowIndexes] firstIndex]];
        DicomStudy *studySelected = [[item valueForKey: @"type"] isEqualToString: @"Study"] ? item : [item valueForKey: @"study"];
        
        id object = nil;
        if( [studySelected isKindOfClass: [DicomStudy class]])
            object = [(NSManagedObject *)studySelected objectID];
        else
            object = studySelected; // DCMTKStudyQueryNode
        
        if( object)
            [NSThread detachNewThreadSelector: @selector(searchForComparativeStudies:) toTarget:self withObject: object];
        
        [self computeTimeInterval];
    }
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"searchForSmartAlbumStudiesOnDICOMNodes"] && albumTable.selectedRow > 0)
    {
        NSArray	*albumArray = self.albumArray;
        
        if( [albumArray count] > albumTable.selectedRow)
        {
            DicomAlbum *album = [albumArray objectAtIndex: albumTable.selectedRow];
            
            if( [[album valueForKey:@"smartAlbum"] boolValue] == YES)
            {
                if( [NSDate timeIntervalSinceReferenceDate] - lastRefreshSmartAlbumDistantStudies > 3 * 60) // 3 min
                    [NSThread detachNewThreadSelector: @selector(searchForSmartAlbumDistantStudies:) toTarget:self withObject: album.name];
            }
        }
    }
    
    if( comparativeStudyWaited) // Select it ! And open it if needed...
    {
        if( [NSDate timeIntervalSinceReferenceDate] - comparativeStudyWaitedTime < 10) // Only try during 10 secs
        {
            [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
            
            NSFetchRequest *request = [[[NSFetchRequest alloc] init] autorelease];
            [request setEntity: [[self.database.managedObjectModel entitiesByName] objectForKey:@"Study"]];
            [request setPredicate: [NSPredicate predicateWithFormat: @"(studyInstanceUID == %@)", [comparativeStudyWaited studyInstanceUID]]];
            
            NSError *error = nil;
            NSArray *studyArray = nil;
            @try {
                studyArray = [self.database.managedObjectContext executeFetchRequest:request error:&error];
            }
            @catch (NSException *e) {
                N2LogExceptionWithStackTrace(e);
            }
            
            if( [studyArray count] > 0)
            {
                DicomStudy *study = [studyArray objectAtIndex: 0];
                NSArray *seriesArray = [self childrenArray: study];
                
                if( [seriesArray count])
                {
                    BOOL success = NO;
                    
                    if( comparativeStudyWaitedToSelect)
                    {
                        if( [self selectThisStudy: study] == YES)
                            success = YES;
                        
                        if( success)
                        {
                            [comparativeStudyWaited release];
                            comparativeStudyWaited = nil;
                            
                            if( comparativeStudyWaitedToOpen && comparativeStudyWaitedViewer)
                            {
                                if( comparativeStudyWaitedViewer.window.isVisible)
                                    [comparativeStudyWaitedViewer loadSelectedSeries: study rightClick: NO];
                            }
                            else if( comparativeStudyWaitedToOpen)
                                [self databaseOpenStudy: study];
                            
                            if( [[self window] firstResponder] != searchField && [[self window] firstResponder] != searchField.currentEditor)
                                [[self window] makeFirstResponder: databaseOutline];
                            
                            [comparativeStudyWaitedViewer release];
                            comparativeStudyWaitedViewer = nil;
                        }
                    }
                    else
                    {
                        [comparativeStudyWaited release];
                        comparativeStudyWaited = nil;
                        
                        [comparativeStudyWaitedViewer release];
                        comparativeStudyWaitedViewer = nil;
                    }
                }
            }
        }
        else
        {
            [comparativeStudyWaited release];
            comparativeStudyWaited = nil;
            
            [comparativeStudyWaitedViewer release];
            comparativeStudyWaitedViewer = nil;
        }
    }
}

- (void)_newStudiesRefreshComparativeStudies: (NSNotification *)aNotification
{
    if( [NSThread isMainThread] == NO)
        N2LogStackTrace( @"***** We must be on MAIN thread");
    
    if( _database == nil)
        return;
    
    NSArray *newStudies = [aNotification.userInfo objectForKey: OsirixAddToDBNotificationImagesArray];
    
    for( DicomStudy *newStudy in newStudies)
    {
        if( self.comparativePatientUID && [self.comparativePatientUID compare: newStudy.patientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
        {
            NSMutableArray *copy = [NSMutableArray arrayWithArray: self.comparativeStudies];
            
            id selectedStudy = nil;
            if( [comparativeTable selectedRow] >= 0)
                selectedStudy = [copy objectAtIndex: [comparativeTable selectedRow]];
            
            BOOL found = NO;
#ifndef OSIRIX_LIGHT
            for( DCMTKStudyQueryNode *study in self.comparativeStudies)
            {
                if( [study.studyInstanceUID isEqualToString: newStudy.studyInstanceUID])
                {
                    found = YES;
                    if( [study isKindOfClass: [DCMTKStudyQueryNode class]])
                    {
                        NSUInteger index = [copy indexOfObject: study];
                        if( index != NSNotFound)
                            [copy replaceObjectAtIndex: index withObject: newStudy];
                    }
                }
            }
#endif
            
            if( found == NO)
            {
                [copy addObject: newStudy];
                [copy sortUsingDescriptors: [NSArray arrayWithObject: [NSSortDescriptor sortDescriptorWithKey:@"date" ascending: NO]]];
            }
            
            self.comparativeStudies = copy;
            
            [comparativeTable reloadData];
            
            if( selectedStudy)
            {
                NSUInteger index = [[copy valueForKey: @"studyInstanceUID"] indexOfObject: [selectedStudy valueForKey: @"studyInstanceUID"]];
                
                if( index != NSNotFound)
                    [comparativeTable selectRowIndexes: [NSIndexSet indexSetWithIndex: index] byExtendingSelection: NO];
            }
        }
    }
}

- (void)outlineViewSelectionDidChange:(NSNotification *)aNotification
{
    if( [NSThread isMainThread] == NO)
        N2LogStackTrace( @"***** We must be on MAIN thread");
    
    @synchronized (self)
    {
        _cachedAlbumsContext = nil;
    }
    
    if( loadingIsOver == NO) return;
    
    @try
    {
        [cachedFilesForDatabaseOutlineSelectionSelectedFiles release]; cachedFilesForDatabaseOutlineSelectionSelectedFiles = nil;
        [cachedFilesForDatabaseOutlineSelectionCorrespondingObjects release]; cachedFilesForDatabaseOutlineSelectionCorrespondingObjects = nil;
        [cachedFilesForDatabaseOutlineSelectionTreeObjects release]; cachedFilesForDatabaseOutlineSelectionTreeObjects = nil;
        [cachedFilesForDatabaseOutlineSelectionIndex release]; cachedFilesForDatabaseOutlineSelectionIndex = nil;
        
        NSIndexSet *index = [databaseOutline selectedRowIndexes];
        id item = [databaseOutline itemAtRow:[index firstIndex]];
        
        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"displaySamePatientWithColorBackground"])
        {
            if( previousItem)
                [databaseOutline setNeedsDisplay: YES];
        }
        
        if( item)
        {
            if( [item isDistant])
            {
                // Check to see if already in retrieving mode, if not download it
                // Retrieve comparative studies only on double-click.
            }
            else
            {
                /**********
                 post notification of new selected item. Can be used by plugins to update RIS connection
                 **********/
                DicomStudy *studySelected = [[item valueForKey: @"type"] isEqualToString: @"Study"] ? item : [item valueForKey: @"study"];
                
                NSDictionary *userInfo = nil;
                if( studySelected)
                {
                    userInfo = [NSDictionary dictionaryWithObject:studySelected forKey: @"Selected Study"];
                    [[NSNotificationCenter defaultCenter] postNotificationName:OsirixNewStudySelectedNotification object:self userInfo:(NSDictionary *)userInfo];
                }
            }
            
            BOOL refreshMatrix = YES;
            long nowFiles = [[item valueForKey:@"noFiles"] intValue];
            
            if( item == previousItem || ([previousItem isKindOfClass: [NSManagedObject class]] && [item isKindOfClass: [NSManagedObject class]] && [[(NSManagedObject *)previousItem objectID] isEqual: [(NSManagedObject *)item objectID]]))
            {
                if( nowFiles == previousNoOfFiles)
                    refreshMatrix = NO;
            }
            else
                DatabaseIsEdited = NO;
            
            previousNoOfFiles = nowFiles;
            
            if( refreshMatrix)
            {
                __block NSArray *files = nil;
                NSMutableArray *selectedRowColumns = [NSMutableArray array], *selectedCellsIDs = [NSMutableArray array];
                __block BOOL imageLevel = NO;
                
                N2ManagedObjectContextPerformAndWait(self.database.managedObjectContext, ^{
                @try {
                    [animationSlider setEnabled:NO];
                    [animationSlider setMaxValue:0];
                    [animationSlider setNumberOfTickMarks:1];
                    [animationSlider setIntValue:0];
                    
                    [matrixViewArray release];
                    
                    if ([[item valueForKey:@"type"] isEqualToString:@"Series"] &&
                        [[[item valueForKey:@"images"] allObjects] count] == 1 &&
                        [[[[[item valueForKey:@"images"] allObjects] objectAtIndex:0] valueForKey:@"numberOfFrames"] intValue] > 1)
                        matrixViewArray = [[NSArray arrayWithObject:item] retain];
                    else
                        matrixViewArray = [[self childrenArray: item] retain];
                    
                    if( item == previousItem || ([previousItem isKindOfClass: [NSManagedObject class]] && [item isKindOfClass: [NSManagedObject class]] && [[(NSManagedObject *)previousItem objectID] isEqual: [(NSManagedObject *)item objectID]]))
                    {
                        for( NSButtonCell *cell in oMatrix.cells)
                        {
                            NSInteger row, column;
                            if( cell.state == NSControlStateValueOn && cell.isTransparent == NO && [oMatrix getRow: &row column: &column ofCell: cell])
                            {
                                if (cell.representedObject)
                                {
                                    [selectedCellsIDs addObject: [cell representedObject]]; // For NSMainThread situation
                                    [selectedRowColumns addObject: [NSDictionary dictionaryWithObjectsAndKeys: [NSNumber numberWithInteger: row], @"row", [NSNumber numberWithInteger: column], @"column", nil]]; //For background thread situation
                                }
                            }
                        }
                    }
                    else
                        [oMatrix selectCellWithTag: 0];
                    
                    [self matrixInit: matrixViewArray.count];
                    
                    files = [[self imagesArray: item preferredObject:oFirstForFirst] retain];
                    imageLevel = [item isKindOfClass:[DicomSeries class]];
                    
                    @synchronized( previewPixThumbnails)
                    {
                        for (unsigned int i = 0; i < [files count]; i++) [previewPixThumbnails addObject:notFoundImage];
                    }
                } @catch (NSException* e) {
                    N2LogExceptionWithStackTrace(e);
                } });
                
                [files autorelease];
                BOOL separateThread = YES;
                if( imageLevel == NO) // If series level, and less than 5 thumbnails to compute: do it on main thread: faster, and no-blinking icons...
                {
                    int thumbnailsToGenerate = 0;
                    for( DicomImage* im in files)
                    {
                        if( [im.series primitiveValueForKey:@"thumbnail"] == nil)
                            thumbnailsToGenerate++;
                    }
                    
                    if( thumbnailsToGenerate < 5)
                        separateThread = NO;
                }
                
                @synchronized( previewPixThumbnails)
                {
                    [matrixLoadIconsThread cancel];
                    [matrixLoadIconsThread release];
                    matrixLoadIconsThread = nil;
                    
                    NSDictionary* dict = [NSDictionary dictionaryWithObjectsAndKeys: _database, @"DicomDatabase", [files valueForKey:@"objectID"], @"objectIDs", [NSNumber numberWithBool: imageLevel], @"imageLevel", previewPix, @"Context", _database, @"DicomDatabase", [NSNumber numberWithUnsignedInteger: previewPixGeneration], @"Generation", nil];
                    if( separateThread)
                    {
                        matrixLoadIconsThread = [[NSThread alloc] initWithTarget: self selector: @selector(matrixLoadIcons:) object: dict];
                        [matrixLoadIconsThread start];
                        
                        if( item == previousItem || ([previousItem isKindOfClass: [NSManagedObject class]] && [item isKindOfClass: [NSManagedObject class]] && [[(NSManagedObject *)previousItem objectID] isEqual: [(NSManagedObject *)item objectID]]))
                        {
                            for( NSCell *cell in [oMatrix cells])
                            {
                                [cell setState: NSControlStateValueOff];
                                [cell setHighlighted: NO];
                            }
                            
                            for( NSDictionary *d in selectedRowColumns)
                            {
                                NSCell *cell = [oMatrix cellAtRow: [[d objectForKey: @"row"] intValue] column: [[d objectForKey: @"column"] intValue]];
                                [cell setState: NSControlStateValueOn];
                                [cell setHighlighted: YES];
                            }
                        }
                    }
                    else
                    {
                        [self matrixLoadIcons: dict];
                        if( item == previousItem || ([previousItem isKindOfClass: [NSManagedObject class]] && [item isKindOfClass: [NSManagedObject class]] && [[(NSManagedObject *)previousItem objectID] isEqual: [(NSManagedObject *)item objectID]]))
                        {
                            [oMatrix deselectAllCells];
                            BOOL first = YES;
                            for( NSCell *cell in [oMatrix cells])
                            {
                                if( [selectedCellsIDs containsObject: [cell representedObject]])
                                {
                                    if( first) {
                                        [oMatrix selectCell: cell];
                                        first = NO;
                                    }
                                    else {
                                        [cell setHighlighted: YES];
                                        [cell setState: NSControlStateValueOn];
                                    }
                                }
                            }
                            
                            [self matrixPressed: oMatrix];
                        }
                    }
                }
            }
            
            if( previousItem != item)
            {
                [previousItem release];
                previousItem = [item retain];
                
                // COMPARATIVE STUDIES
                id studySelected = [[item valueForKey: @"type"] isEqualToString: @"Study"] ? item : [item valueForKey: @"study"];
                
                if( [[studySelected valueForKey: @"patientUID"] compare: self.comparativePatientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] != NSOrderedSame)
                {
                    self.comparativePatientUID = [studySelected valueForKey: @"patientUID"];
                    self.comparativeStudies = nil;
                    [comparativeTable reloadData];
                    [[[comparativeTable tableColumnWithIdentifier:@"Cell"] headerCell] setStringValue: NSLocalizedString( @"History", nil)];
                    
                    id object = nil;
                    if( [studySelected isKindOfClass: [DicomStudy class]])
                        object = [(NSManagedObject *)studySelected objectID];
                    else
                        object = studySelected; // DCMTKStudyQueryNode
                    
                    [NSThread detachNewThreadSelector: @selector(searchForComparativeStudies:) toTarget:self withObject: object];
                }
                else
                {
                    NSUInteger index = [[self.comparativeStudies valueForKey: @"studyInstanceUID"] indexOfObject: [studySelected valueForKey: @"studyInstanceUID"]];
                    if( index != NSNotFound)
                    {
                        [comparativeTable selectRowIndexes: [NSIndexSet indexSetWithIndex: index] byExtendingSelection: NO];
                        [comparativeTable scrollRowToVisible: [comparativeTable selectedRow]];
                    }
                }
            }
            
            if( [item isDistant])
                self.distantStudyMessage = NSLocalizedString( @"Double-click on the Study line to retrieve the images", nil);
            else
                self.distantStudyMessage = @"";
            
            [self resetROIsAndKeysButton];
        }
        else
        {
            [oMatrix selectCellWithTag: 0];
            [self matrixInit: 0];
            
            [previousItem release];
            previousItem = nil;
            
            ROIsAndKeyImagesButtonAvailable = NO;
            
            self.distantStudyMessage = @"";
            self.comparativePatientUID = nil;
            self.comparativeStudies = nil;
            [comparativeTable reloadData];
            [[[comparativeTable tableColumnWithIdentifier:@"Cell"] headerCell] setStringValue: NSLocalizedString( @"History", nil)];
        }
        
        [self splitView:splitViewVert resizeSubviewsWithOldSize:[splitViewVert bounds].size];
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
}

- (void) selectDatabaseOutline
{
    [[self window] makeFirstResponder: databaseOutline];
}

- (void) refreshMatrix:(id) sender
{
    [previousItem release];
    previousItem = nil;	// This will force the matrix update
    
    BOOL firstResponderMatrix = NO;
    
    if( [[self window] firstResponder] == oMatrix && [[self window] firstResponder] != searchField && [[self window] firstResponder] != searchField.currentEditor)
    {
        [[self window] makeFirstResponder: databaseOutline];
        firstResponderMatrix = YES;
    }
    
    [[NSNotificationCenter defaultCenter] postNotificationName: NSOutlineViewSelectionDidChangeNotification  object:databaseOutline userInfo: nil];
    
    [imageView display];
    
    if( firstResponderMatrix && [[self window] firstResponder] != searchField && [[self window] firstResponder] != searchField.currentEditor)
        [[self window] makeFirstResponder: oMatrix];
}

- (void) mergeSeriesExecute:(NSArray*) seriesArray
{
    NSInteger result = HorosRunInformationalAlertPanel(NSLocalizedString(@"Merge Series", nil), NSLocalizedString(@"Are you sure you want to merge the selected series? It cannot be cancelled.\r\rWARNING! If you merge multiple patients, the Patient Name and ID will be identical.", nil), NSLocalizedString(@"OK",nil), NSLocalizedString(@"Cancel",nil), nil);
    
    if( result == HorosAlertDefaultResponse)
    {
        NSManagedObjectContext	*context = self.database.managedObjectContext;
        
        N2ManagedObjectContextPerformAndWait(context, ^{
        
        if( [seriesArray count])
        {
            // The destination series
            NSManagedObject	*destSeries = [seriesArray objectAtIndex: 0];
            
            for( NSInteger x = 0; x < [seriesArray count] ; x++)
            {
                NSManagedObject	*series = [seriesArray objectAtIndex: x];
                
                if( [[series valueForKey:@"type"] isEqualToString: @"Series"] == NO)
                    series = [[series valueForKey:@"series"] anyObject];
                
                if( [[series valueForKey:@"type"] isEqualToString: @"Series"])
                {
                    NSManagedObject *image = [[series valueForKey: @"images"] anyObject];
                    
                    if( [[image valueForKey:@"extension"] isEqualToString:@"dcm"])
                        destSeries = series;
                }
            }
            
            if( [[destSeries valueForKey:@"type"] isEqualToString: @"Series"] == NO) destSeries = [destSeries valueForKey:@"Series"];
            
            NSLog(@"MERGING SERIES: %@", destSeries);
            DicomStudy *study = [destSeries valueForKey:@"study"];
            
            for( NSManagedObject *series in seriesArray)
            {
                if( series != destSeries)
                {
                    if( [[series valueForKey:@"type"] isEqualToString:@"Series"])
                    {
                        NSArray *images = [[series valueForKey: @"images"] allObjects];
                        
                        for( id i in images)
                            [i setValue: destSeries forKey: @"series"];
                        
                        [context deleteObject: series];
                    }
                }
            }
            
            // TODO: when merging multiframe series, we should reevaluate the instanceNumbers in order to have a well-sorted [DicomSeries sortedImages] array
            
            [destSeries setValue:[NSNumber numberWithInt:0] forKey:@"numberOfImages"];
            
            (void)[_database save:NULL];
            
            [self outlineViewRefresh];
            
            [HorosOutlineSelectionRestore selectItem: study inOutline: databaseOutline extending: NO];
            [databaseOutline scrollRowToVisible: [databaseOutline selectedRow]];
            
            [self refreshMatrix: self];
        }
        
        });
    }
}

- (IBAction) mergeSeries:(id) sender
{
    NSArray				*cells = [oMatrix selectedCells];
    NSMutableArray		*seriesArray = [NSMutableArray array];
    
    for( NSCell *cell in cells)
    {
        if( [cell isEnabled] == YES)
        {
            NSManagedObject	*series = [matrixViewArray objectAtIndex: [cell tag]];
            
            [seriesArray addObject: series];
        }
    }
    
    [self mergeSeriesExecute: seriesArray];
}

#ifndef OSIRIX_LIGHT
- (IBAction) unifyStudies:(id) sender
{
    [ViewerController closeAllWindows];
    
    DicomStudy *destStudy = [databaseOutline itemAtRow: [databaseOutline selectedRow]];
    if( [[destStudy valueForKey:@"type"] isEqualToString: @"Study"] == NO) destStudy = [destStudy valueForKey:@"study"];
    
    NSInteger result = HorosRunInformationalAlertPanel( [NSString stringWithFormat: NSLocalizedString(@"Unify Patient Identity to: %@", nil), destStudy.name], [NSString stringWithFormat: NSLocalizedString(@"Are you sure you want to unify the patient identity of the selected studies? It cannot be cancelled. You can choose to modify the database fields only, or also change the DICOM files headers with the new values.\r\rWARNING! The Patient Name and ID will be identical for all these studies to the last selected study (%@ - %@).\r\rThe original Patient Name and Patient ID will be saved in the OtherPatientNames and OtherPatientIDs DICOM fields.", nil), destStudy.name, destStudy.patientID], NSLocalizedString(@"Database & DICOM",nil), NSLocalizedString(@"Database only",nil), NSLocalizedString(@"Cancel",nil), nil);
    
    if( result == HorosAlertDefaultResponse || result == HorosAlertAlternateResponse)
    {
        NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
        
        if( result == HorosAlertDefaultResponse)
        {
            // Now modify the DICOM files
            // row has to outlive the iteration: declared inside, its
            // initialiser read itself and every pass after the first indexed
            // the outline with whatever was on the stack.
            NSInteger row = 0;
            for( NSInteger x = 0; x < [selectedRows count] ; x++)
            {
                row = ( x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex: row];
                
                DicomStudy *study = [databaseOutline itemAtRow: row];
                
                if( [[study valueForKey:@"type"] isEqualToString: @"Study"] == NO) study = [study valueForKey:@"study"];
                
                if( study != destStudy)
                {
                    if( [[study valueForKey:@"type"] isEqualToString: @"Study"])
                    {
                        NSInteger confirm = HorosRunInformationalAlertPanel(NSLocalizedString(@"Unify Patient Identity", nil), NSLocalizedString(@"Do you confirm to DEFINITIVELY change this patient identity:\r\r%@ / %@ / %@\r\rto this new identity:\r\r%@ / %@ ?", nil), NSLocalizedString(@"OK",nil), NSLocalizedString(@"Cancel",nil), nil, study.name, study.patientID, study.studyName, destStudy.name, destStudy.patientID);
                        
                        if( confirm == HorosAlertDefaultResponse)
                        {
                            WaitRendering *wait = [[[WaitRendering alloc] init: NSLocalizedString(@"Updating files...", nil)] autorelease];
                            [wait showWindow:self];
                            
                            NSMutableArray *params = [NSMutableArray arrayWithObjects:@"dcmodify", @"--ignore-errors", nil];
                            
                            DCMObject *dcmObject = [HorosDCMTKObject objectWithContentsOfFile: [[[destStudy paths] allObjects] objectAtIndex: 0]];
                            
                            NSString *originalPatientName = [dcmObject attributeValueWithName:@"PatientsName"];
                            NSString *originalBirthDate = [dcmObject attributeValueWithName:@"PatientsBirthDate"];
                            
                            NSString *existingOtherPatientNames = [dcmObject attributeValueWithName:@"OtherPatientIDs"];
                            NSString *existingOtherPatientIDs = [dcmObject attributeValueWithName:@"OtherPatientNames"];
                            
                            if( existingOtherPatientNames == nil)
                                existingOtherPatientNames = @"";
                            
                            if( existingOtherPatientIDs == nil)
                                existingOtherPatientIDs = @"";
                            
                            if( existingOtherPatientNames.length)
                                existingOtherPatientNames = [existingOtherPatientNames stringByAppendingString: @" - "];
                            
                            if( existingOtherPatientIDs.length)
                                existingOtherPatientIDs = [existingOtherPatientIDs stringByAppendingString: @" - "];
                            
                            existingOtherPatientNames = [existingOtherPatientNames stringByAppendingString: study.name];
                            existingOtherPatientIDs = [existingOtherPatientIDs stringByAppendingString: study.patientID];
                            
                            if( originalPatientName)
                            {
                                
                                [params addObjectsFromArray: [NSArray arrayWithObjects: @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,0020)", destStudy.patientID], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,0010)", originalPatientName], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,0030)", originalBirthDate], nil]];
                                [params addObjectsFromArray: [NSArray arrayWithObjects: @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,1000)", existingOtherPatientIDs], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,1001)", existingOtherPatientNames], nil]];
                                
                                
                                NSArray* tagAndValues = [NSArray arrayWithObjects:
                                                                                    [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,0020)"],(destStudy.patientID?destStudy.patientID:@""),nil],
                                                                                    [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,0010)"],(originalPatientName?originalPatientName:@""),nil],
                                                                                    [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,0030)"],(originalBirthDate?originalBirthDate:@""),nil],
                                                                                    [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,1000)"],(existingOtherPatientIDs?existingOtherPatientIDs:@""),nil],
                                                                                    [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,1001)"],(existingOtherPatientNames?existingOtherPatientNames:@""),nil],
                                nil];
                                
                                
                                NSMutableArray *files = [NSMutableArray arrayWithArray:[[study paths] allObjects]];
                                
                                if (files)
                                {
                                    [files removeDuplicatedStrings];
                                    
                                    [params addObjectsFromArray: files];
                                    
                                    @try
                                    {
                                        
                                        [XMLController modifyDicom:tagAndValues dicomFiles:files];
                                        
                                        for( id loopItem in files)
                                        {
                                            [[NSFileManager defaultManager] removeItemAtPath:[loopItem stringByAppendingString:@".bak"] error:NULL];
                                        }
                                    }
                                    @catch (NSException * e)
                                    {
                                        NSLog(@"**** DicomStudy setComment: %@", e);
                                    }
                                }
                                
                                [wait close];
                            }
                            else
                            {
                                [wait close];
                                
                                HorosRunCriticalAlertPanel( NSLocalizedString(@"Unify Patient Identity", nil), NSLocalizedString( @"Failed to change the DICOM files", nil), NSLocalizedString(@"OK",nil), nil, nil);
                            }
                        }
                        else return;
                    }
                }
            }
        }
        
        // row has to outlive the iteration; see the note at the other loops.
        NSInteger row = 0;
        for( NSInteger x = 0; x < [selectedRows count] ; x++)
        {
            row = ( x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex: row];
            
            DicomStudy *study = [databaseOutline itemAtRow: row];
            if( [[study valueForKey:@"type"] isEqualToString: @"Study"] == NO) study = [study valueForKey:@"study"];
            
            if( study != destStudy)
            {
                if( [[study valueForKey:@"type"] isEqualToString: @"Study"])
                {
                    NSInteger confirm = HorosAlertDefaultResponse;
                    
                    if( result == HorosAlertAlternateResponse)
                        confirm = HorosRunInformationalAlertPanel(NSLocalizedString(@"Unify Patient Identity", nil), NSLocalizedString(@"Do you confirm to DEFINITIVELY change this patient identity:\r\r%@ / %@ / %@\r\rto this new identity:\r\r%@ / %@ ?", nil), NSLocalizedString(@"OK",nil), NSLocalizedString(@"Cancel",nil), nil, study.name, study.patientID, study.studyName, destStudy.name, destStudy.patientID);
                    
                    if( confirm == HorosAlertDefaultResponse)
                    {
                        [study setValue: destStudy.patientID forKey: @"patientID"];
                        [study setValue: [destStudy valueForKey:@"patientUID"]  forKey: @"patientUID"];
                        [study setValue: destStudy.name  forKey: @"name"];
                        
                        NSLog( @"---- Patient Unify: %@ %@ -> %@ %@", [study valueForKey:@"accessionNumber"], study.patientID, [destStudy valueForKey:@"accessionNumber"], destStudy.patientID);
                    }
                }
            }
        }
        
        (void)[_database save: nil];
        
        [self outlineViewRefresh];
        
        [HorosOutlineSelectionRestore selectItem: destStudy inOutline: databaseOutline extending: NO];
        [databaseOutline scrollRowToVisible: [databaseOutline selectedRow]];
        
        [self refreshMatrix: self];
        
        [self refreshPACSOnDemandResults: self];
    }
}

- (IBAction) mergeStudies:(id) sender
{
    [ViewerController closeAllWindows];
    
    // Is it only series??
    NSIndexSet		*selectedRows = [databaseOutline selectedRowIndexes];
    BOOL	onlySeries = YES;
    NSMutableArray	*seriesArray = [NSMutableArray array];
    
    NSInteger row = 0;
    for( NSInteger x = 0; x < [selectedRows count] ; x++)
    {
        row = ( x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex: row];
        NSManagedObject	*series = [databaseOutline itemAtRow: row];
        if( [[series valueForKey:@"type"] isEqualToString: @"Series"] == NO) onlySeries = NO;
        
        [seriesArray addObject: series];
    }
    
    if( onlySeries)
    {
        [self mergeSeriesExecute: seriesArray];
        return;
    }
    
    // The destination study : prefer DICOM study
    DicomStudy	*destStudy = [databaseOutline itemAtRow: [databaseOutline selectedRow]];
    if( [[destStudy valueForKey:@"type"] isEqualToString: @"Study"] == NO) destStudy = [destStudy valueForKey:@"study"];
    
    NSString *nameAndStudy = [NSString stringWithFormat: @"%@ / %@", destStudy.name, destStudy.studyName];
    
    NSInteger result = HorosRunInformationalAlertPanel( NSLocalizedString(@"Merge Studies", nil), [NSString stringWithFormat: NSLocalizedString(@"Are you sure you want to merge the selected studies to: \r\r%@\r\rIt cannot be cancelled.\r\rWARNING! If you merge multiple different patients, the Patient Name, ID and Study Description will be identical.\r\rYou can choose to modify the database fields only, or also change the DICOM files headers with the new values.", nil), nameAndStudy], NSLocalizedString(@"Database & DICOM",nil), NSLocalizedString(@"Database only",nil), NSLocalizedString(@"Cancel",nil), nil);
    
    if( result == HorosAlertDefaultResponse || result == HorosAlertAlternateResponse)
    {
        NSManagedObjectContext	*context = self.database.managedObjectContext;
        
        NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
        
        if( result == HorosAlertDefaultResponse)
        {
            // Now modify the DICOM files
            // row has to outlive the iteration: declared inside, its
            // initialiser read itself and every pass after the first indexed
            // the outline with whatever was on the stack.
            NSInteger row = 0;
            for( NSInteger x = 0; x < [selectedRows count] ; x++)
            {
                row = ( x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex: row];
                
                DicomStudy *study = [databaseOutline itemAtRow: row];
                if( [[study valueForKey:@"type"] isEqualToString: @"Study"] == NO) study = [study valueForKey:@"study"];
                
                if( study != destStudy)
                {
                    if( [[study valueForKey:@"type"] isEqualToString: @"Study"])
                    {
                        NSInteger confirm = HorosRunInformationalAlertPanel(NSLocalizedString(@"Merge Studies", nil), NSLocalizedString(@"Do you confirm to DEFINITIVELY change this study identity to this new identity:\r\r%@ / %@ ?", nil), NSLocalizedString(@"OK",nil), NSLocalizedString(@"Cancel",nil), nil, destStudy.name, destStudy.studyName);
                        
                        if( confirm == HorosAlertDefaultResponse)
                        {
                            NSMutableArray	*params = [NSMutableArray arrayWithObjects:@"dcmodify", @"--ignore-errors", nil];
                            
                            DCMObject *dcmObject = [HorosDCMTKObject objectWithContentsOfFile: [[[destStudy paths] allObjects] objectAtIndex: 0]];
                            
                            NSString *originalPatientName = [dcmObject attributeValueWithName:@"PatientsName"];
                            NSString *originalBirthDate = [dcmObject attributeValueWithName:@"PatientsBirthDate"];
                            NSString *originalStudyID = [dcmObject attributeValueWithName:@"StudyID"];
                            NSString *originalStudyInstanceUID = [dcmObject attributeValueWithName:@"StudyInstanceUID"];
                            NSString *originalStudyDescription = [dcmObject attributeValueWithName:@"StudyDescription"];
                            
                            NSString *existingOtherPatientNames = [dcmObject attributeValueWithName:@"OtherPatientIDs"];
                            NSString *existingOtherPatientIDs = [dcmObject attributeValueWithName:@"OtherPatientNames"];
                            
                            if( existingOtherPatientNames == nil)
                                existingOtherPatientNames = @"";
                            
                            if( existingOtherPatientIDs == nil)
                                existingOtherPatientIDs = @"";
                            
                            if( existingOtherPatientNames.length)
                                existingOtherPatientNames = [existingOtherPatientNames stringByAppendingString: @" - "];
                            
                            if( existingOtherPatientIDs.length)
                                existingOtherPatientIDs = [existingOtherPatientIDs stringByAppendingString: @" - "];
                            
                            existingOtherPatientNames = [existingOtherPatientNames stringByAppendingString: study.name];
                            existingOtherPatientIDs = [existingOtherPatientIDs stringByAppendingString: study.patientID];
                            
                            if( originalPatientName)
                            {
                                
                                NSMutableArray* tagAndValues = [NSMutableArray array];
                                
                                if( [destStudy.patientID isEqualToString: study.patientID] == NO || [destStudy.name isEqualToString: study.name] == NO)
                                {
                                    [params addObjectsFromArray: [NSArray arrayWithObjects: @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,0020)", destStudy.patientID], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,0010)", originalPatientName], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,0030)", originalBirthDate], nil]];
                                    [params addObjectsFromArray: [NSArray arrayWithObjects: @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,1000)", existingOtherPatientIDs], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0010,1001)", existingOtherPatientNames], nil]];
                                    
                                    [tagAndValues addObjectsFromArray:[NSArray arrayWithObjects:
                                                                                                [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,0020)"],(destStudy.patientID?destStudy.patientID:@""),nil],
                                                                                                [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,0010)"],(originalPatientName?originalPatientName:@""),nil],
                                                                                                [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,0030)"],(originalBirthDate?originalBirthDate:@""),nil],
                                                                                                [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,1000)"],(existingOtherPatientIDs?existingOtherPatientIDs:@""),nil],
                                                                                                [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0010,1001)"],(existingOtherPatientNames?existingOtherPatientNames:@""),nil],
                                                                                                nil]];
                                }
                                
                                [params addObjectsFromArray: [NSArray arrayWithObjects: @"-i", [NSString stringWithFormat: @"%@=%@", @"(0020,0010)", originalStudyID], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0020,000D)", originalStudyInstanceUID], @"-i", [NSString stringWithFormat: @"%@=%@", @"(0008,1030)", originalStudyDescription], nil]];
                                
                                [tagAndValues addObjectsFromArray:[NSArray arrayWithObjects:
                                                                                            [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0020,0010)"],(originalStudyID?originalStudyID:@""),nil],
                                                                                            [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0020,000D)"],(originalStudyInstanceUID?originalStudyInstanceUID:@""),nil],
                                                                                            [NSArray  arrayWithObjects:[DCMAttributeTag tagWithTagString:@"(0008,1030)"],(originalStudyDescription?originalStudyDescription:@""),nil],
                                                                                            nil]];
                                
                                NSMutableArray *files = [NSMutableArray arrayWithArray: [[study paths] allObjects]];
                                
                                if( files)
                                {
                                    [files removeDuplicatedStrings];
                                    
                                    [params addObjectsFromArray: files];
                                    
                                    @try
                                    {
                                        
                                        [XMLController modifyDicom:tagAndValues dicomFiles:files];
                                        
                                        for( id loopItem in files)
                                        {
                                            [[NSFileManager defaultManager] removeItemAtPath: [loopItem stringByAppendingString:@".bak"] error:NULL];
                                        }
                                    }
                                    @catch (NSException * e)
                                    {
                                        NSLog(@"**** DicomStudy setComment: %@", e);
                                    }
                                }
                            }
                            else
                                HorosRunCriticalAlertPanel( NSLocalizedString(@"Unify Study Identity", nil), NSLocalizedString( @"Failed to change the DICOM files", nil), NSLocalizedString(@"OK",nil), nil, nil);
                        }
                        else return;
                    }
                }
            }
        }
        
        NSLog(@"MERGING STUDIES: %@", destStudy);
        
        NSInteger row = 0;
        for( NSInteger x = 0; x < [selectedRows count] ; x++)
        {
            row = ( x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex: row];
            
            NSManagedObject	*study = [databaseOutline itemAtRow: row];
            if( [[study valueForKey:@"type"] isEqualToString: @"Study"] == NO) study = [study valueForKey:@"study"];
            
            if( study != destStudy)
            {
                if( [[study valueForKey:@"type"] isEqualToString: @"Study"])
                {
                    NSArray *series = [[study valueForKey: @"series"] allObjects];
                    
                    for( id s in series)
                        [s setValue: destStudy forKey: @"study"];
                    
                    [context deleteObject: study];
                }
            }
        }
        
        [destStudy setValue:[NSNumber numberWithInt:0] forKey:@"numberOfImages"];
        
        (void)[_database save:NULL];
        
        [self outlineViewRefresh];
        
        [HorosOutlineSelectionRestore selectItem: destStudy inOutline: databaseOutline extending: NO];
        [databaseOutline scrollRowToVisible: [databaseOutline selectedRow]];
        
        [self refreshMatrix: self];
    }
}
#endif

- (void) proceedDeleteObjects: (NSArray*) objectsToDelete tree:(NSSet*)treeObjs
{
    if( [NSThread isMainThread] == NO)
        N2LogStackTrace( @"************ This is a MAIN thread only function");
    
    DicomDatabase* database = [_database retain];
    __block BOOL refreshComparative = NO;
    __block NSError *saveError = nil;
    __block BOOL deletionSaved = NO;
    
    NSMutableSet *seriesSet = [NSMutableSet set], *studiesSet = [NSMutableSet set];
    
    [reportFilesToCheck removeAllObjects];
    
    N2ManagedObjectContextPerformAndWait(database.managedObjectContext, ^{
    
    @try
    {
        NSManagedObject	*study = nil, *series = nil;
        
        NSLog(@"objects to delete : %d", (int) [objectsToDelete count]);
        
        for( NSManagedObject *obj in objectsToDelete)
        {
            @autoreleasepool
            {
                // ********* SERIES
                if( [obj valueForKey:@"series"] != series)
                {
                    series = [obj valueForKey:@"series"];
                    
                    if([seriesSet containsObject: series] == NO)
                    {
                        if( series)
                            [seriesSet addObject: series];
                        
                        // Is a viewer containing this series opened? -> close it
                        for( ViewerController *vc in [ViewerController getDisplayed2DViewers])
                        {
                            if( series == [[[vc fileList] objectAtIndex: 0] valueForKey:@"series"])
                                [[vc window] close];
                        }
                    }
                    
                    // ********* STUDY
                    if( [series valueForKey:@"study"] != study)
                    {
                        study = [series valueForKey:@"study"];
                        
                        if([studiesSet containsObject: study] == NO)
                        {
                            if( study)
                                [studiesSet addObject: study];
                            
                            // Is a viewer containing this series opened? -> close it
                            for( ViewerController *vc in [ViewerController getDisplayed2DViewers])
                            {
                                if( study == [[[vc fileList] objectAtIndex: 0] valueForKeyPath:@"series.study"])
                                    [vc buildMatrixPreview];
                            }
                        }
                    }
                }
            }
        }
        
        for ( NSManagedObject *obj in objectsToDelete)
            [database.managedObjectContext deleteObject:obj];
        
    }
    @catch ( NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    for (NSManagedObject* o in treeObjs)
        if ([o isKindOfClass:[DicomSeries class]])
            [studiesSet addObject:[o valueForKey: @"study"]];
        else if ([o isKindOfClass:[DicomStudy class]])
            [studiesSet addObject:o];
    
    @try
    {
        // Remove series without images !
        for (DicomSeries* series in seriesSet)
        {
            @autoreleasepool
            {
                @try
                {
                    if ([series isDeleted] == NO)
                    {
                        if ([series.images count] == 0)
                        {
                            [database.managedObjectContext deleteObject:series];
                        }
                        else
                        {
                            series.numberOfImages = [NSNumber numberWithInt:0];
                            series.thumbnail = nil;
                        }
                    }
                }
                @catch (NSException* e)
                {
                    N2LogExceptionWithStackTrace(e/*, @"context deleteObject: series"*/);
                }
            }
        }
        
        // Remove studies without series !
        for( DicomStudy *study in studiesSet)
        {
            @autoreleasepool
            {
                @try
                {
                    if( self.comparativePatientUID && [self.comparativePatientUID compare: study.patientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
                        refreshComparative = YES;
                    
                    if( [study isDeleted] == NO)
                    {
                        if( [study.imageSeries count] == 0)
                        {
                            NSLog( @"Delete Study: %@ - %@", study.patientID, study.studyInstanceUID);
                            
                            [database.managedObjectContext deleteObject:study];
                        }
                        else
                        {
                            [study setValue:[NSNumber numberWithInt:0]  forKey:@"numberOfImages"];
                            [study setValue:[study valueForKey: @"modalities"] forKey:@"modality"];
                        }
                    }
                }
                @catch( NSException *e)
                {
                    N2LogExceptionWithStackTrace(e/*, @"context deleteObject: study"*/);
                }
            }
        }
        
        [previousItem release];
        previousItem = nil;
    }
    @catch( NSException *ne)
    {
        N2LogExceptionWithStackTrace(ne);
    }
    
    for( DicomStudy *study in studiesSet)
        (void)[study noFiles];
    
    // The result of this save used to be dropped. On a volume that is full, or
    // read-only, or gone, the rows stayed in the store while the outline was
    // reloaded without them - so the deletion looked done, and the studies were
    // back at the next launch. Put them back in view and say what happened
    // instead of showing a success that did not happen.
    deletionSaved = [database save: &saveError];
    [saveError retain];
    if( deletionSaved == NO)
    {
        NSLog( @"---- delete: %d object(s) could not be deleted: %@", (int) [objectsToDelete count], saveError.localizedDescription);
        [database.managedObjectContext rollback];
    }
    
    });
    [database release];
    
    if( deletionSaved == NO && [[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"] == NO)
        HorosRunCriticalAlertPanel( NSLocalizedString(@"Delete Failed", nil),
                                 @"%@\r\r%@",
                                 NSLocalizedString(@"OK", nil), nil, nil,
                                 NSLocalizedString(@"The database could not record this deletion, so nothing was deleted.", nil),
                                 saveError.localizedDescription? saveError.localizedDescription : NSLocalizedString(@"No reason was given.", nil));
    
    [saveError autorelease];
    [self outlineViewRefresh];
    [self refreshAlbums];
    
    if( refreshComparative)
    {
        NSManagedObject *item = [databaseOutline itemAtRow: [[databaseOutline selectedRowIndexes] firstIndex]];
        DicomStudy *studySelected = [[item valueForKey: @"type"] isEqualToString: @"Study"] ? item : [item valueForKey: @"study"];
        
        id object = nil;
        if( [studySelected isKindOfClass: [DicomStudy class]])
            object = [(NSManagedObject *)studySelected objectID];
        else
            object = studySelected;
        
        [NSThread detachNewThreadSelector: @selector(searchForComparativeStudies:) toTarget:self withObject: object];
    }
}

- (void) proceedDeleteObjects:(NSArray*)objectsToDelete
{
    [self proceedDeleteObjects:objectsToDelete tree:nil];
}

- (void) delObjects:(NSMutableArray*) objectsToDelete tree:(NSMutableSet*)treeObjs
{
    NSManagedObjectContext	*context = self.database.managedObjectContext;
    
    N2ManagedObjectContextPerformAndWait(context, ^{
    int result;
    
    // Are some images locked?
    NSArray	*lockedImages = [objectsToDelete filteredArrayUsingPredicate: [NSPredicate predicateWithFormat:@"series.study.lockedStudy == YES"]];
    
    if( [lockedImages count] == [objectsToDelete count] && [lockedImages count] > 0)
    {
        HorosRunAlertPanel( NSLocalizedString(@"Locked Studies", nil),  NSLocalizedString(@"These images are stored in locked studies. First, unlock these studies to delete them.", nil), nil, nil, nil);
    }
    else
    {
        BOOL cancelled = NO;
        
        if( [lockedImages count])
        {
            [objectsToDelete removeObjectsInArray: lockedImages];
            
            HorosRunInformationalAlertPanel(NSLocalizedString(@"Locked Studies", nil), NSLocalizedString(@"Some images are stored in locked studies. Only unlocked images will be deleted.", nil), NSLocalizedString(@"OK",nil), nil, nil);
        }
        
        // Are some images in albums?
        if( albumTable.selectedRow == 0)
        {
            @try
            {
                NSArray	*albumedImages = [objectsToDelete filteredArrayUsingPredicate: [NSPredicate predicateWithFormat:@"series.study.albums.@count > 0"]];
                
                if( [albumedImages count])
                {
                    result = HorosRunInformationalAlertPanel(NSLocalizedString(@"Images in Albums", nil), NSLocalizedString(@"Some or all of these images are stored in albums. Do you really want to delete these images, stored in albums?\r\rDelete all images or only those not stored in an album?", nil), NSLocalizedString(@"All",nil), NSLocalizedString(@"Cancel",nil), NSLocalizedString(@"Only if not stored in an album",nil));
                    
                    if( result == HorosAlertOtherResponse)
                    {
                        [objectsToDelete removeObjectsInArray: albumedImages];
                    }
                    
                    if( result == HorosAlertAlternateResponse)
                        cancelled = YES;
                }
            }
            
            @catch (NSException *e)
            {
                NSLog(@"series.study.albums.@count exception: %@", e);
                [e printStackTrace];
            }
        }
        
        if( cancelled == NO)
        {
            NSLog( @"locked images: %d", (int) [lockedImages count]);
            
            // Try to find images that aren't stored in the local database
            
            NSMutableArray	*nonLocalImagesPath = [NSMutableArray array];
            
            WaitRendering *wait = [[WaitRendering alloc] init: NSLocalizedString(@"Deleting...", nil)];
            [wait showWindow:self];
            
            nonLocalImagesPath = [[objectsToDelete filteredArrayUsingPredicate: [NSPredicate predicateWithFormat:@"inDatabaseFolder == NO"]] valueForKey:@"completePath"];
            
            if( [nonLocalImagesPath  count] > 0)
            {
                [wait.window orderOut: self];
                
                NSLog(@"non-local images : %d", (int) [nonLocalImagesPath count]);
                
                result = HorosRunInformationalAlertPanel(NSLocalizedString(@"Delete/Remove images", nil), NSLocalizedString(@"Some of the selected images are not stored in the Database folder. Do you want to only remove the links of these images from the database or also delete the original files?", nil), NSLocalizedString(@"Remove the links",nil),  NSLocalizedString(@"Cancel",nil), NSLocalizedString(@"Delete the files",nil));
                
                [wait.window makeKeyAndOrderFront: self];
            }
            else result = HorosAlertDefaultResponse;
            
            @try
            {
                if( result == HorosAlertAlternateResponse)
                {
                    NSLog( @"Cancel");
                }
                else
                {
                    if( result == HorosAlertDefaultResponse || result == HorosAlertOtherResponse)
                        [self proceedDeleteObjects:objectsToDelete tree:treeObjs];
                    
                    if( result == HorosAlertOtherResponse)
                    {
                        for( NSString *path in nonLocalImagesPath)
                        {
                            [[NSFileManager defaultManager] removeItemAtPath: path error:NULL];
                            
                            if( [[path pathExtension] isEqualToString:@"hdr"])		// ANALYZE -> DELETE IMG
                            {
                                [[NSFileManager defaultManager] removeItemAtPath:[[path stringByDeletingPathExtension] stringByAppendingPathExtension:@"img"] error:NULL];
                            }
                            
                            NSString *currentDirectory = [[path stringByDeletingLastPathComponent] stringByAppendingString:@"/"];
                            NSArray *dirContent = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:currentDirectory error:NULL];
                            
                            //Is this directory empty?? If yes, delete it!
                            
                            if( [dirContent count] == 0) [[NSFileManager defaultManager] removeItemAtPath:currentDirectory error:NULL];
                            if( [dirContent count] == 1)
                            {
                                if( [[[dirContent objectAtIndex: 0] uppercaseString] hasSuffix:@".DS_STORE"]) [[NSFileManager defaultManager] removeItemAtPath:currentDirectory error:NULL];
                            }
                        }
                    }
                }
            }
            @catch (NSException * e) { NSLog( @"***** exception in %s: %@", __PRETTY_FUNCTION__, e); }
            [wait close];
            [wait autorelease];
            wait = nil;
        }
    }
    
    });
    
    [self refreshMatrix: self];
    
#ifndef OSIRIX_LIGHT
    [[QueryController currentQueryController] executeRefresh: self];
    [[QueryController currentAutoQueryController] executeRefresh: self];
#endif
}

- (void) delObjects:(NSMutableArray*) objectsToDelete {
    [self delObjects:objectsToDelete tree:nil];
}

- (IBAction)delItem: (id)sender
{
    if (self.database.isReadOnly)
        return;
    
    NSInteger				result;
    NSManagedObjectContext	*context = self.database.managedObjectContext;
    BOOL					matrixThumbnails = YES;
    int						animState = [animationCheck state];
    
    //	if( DICOMDIRCDMODE)
    //	{
    //		HorosRunInformationalAlertPanel(NSLocalizedString(@"OsiriX CD/DVD", nil), NSLocalizedString(@"OsiriX is running in read-only mode, from a CD/DVD.", nil), NSLocalizedString(@"OK",nil), nil, nil);
    //		return;
    //	}*/
    
    
    if( sender == nil)
    {
        matrixThumbnails = NO;
    }
    else
    {
        if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
            matrixThumbnails = YES;
        
        if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [databaseOutline menu]) || [[self window] firstResponder] == databaseOutline || [[self window] firstResponder] == comparativeTable)
            matrixThumbnails = NO;
    }
    
    if( matrixThumbnails == NO && [databaseOutline selectedRow] == -1)
        return;
    
    NSString *level = nil;
    
    if( matrixThumbnails)
        level = NSLocalizedString( @"Selected Thumbnails", nil);
    else
        level = NSLocalizedString( @"Selected Lines", nil);
    
    if( matrixThumbnails == NO)
    {
        BOOL onlyDistantStudy = YES;
        
        if( [[databaseOutline selectedRowIndexes] count] > 0)
        {
            NSUInteger idx = databaseOutline.selectedRowIndexes.firstIndex;
            
            while (idx != NSNotFound)
            {
                id object = [databaseOutline itemAtRow: idx];
                
                if( [object isDistant] == NO)
                {
                    onlyDistantStudy = NO;
                    break;
                }
                
                idx = [databaseOutline.selectedRowIndexes indexGreaterThanIndex: idx];
            }
        }
        
        if( onlyDistantStudy)
        {
            HorosRunInformationalAlertPanel(NSLocalizedString(@"Delete images", nil), NSLocalizedString(@"These studies are not stored locally, you cannot delete them", nil), NSLocalizedString(@"OK",nil), nil, nil);
            return;
        }
    }
    
    [animationCheck setState: NSControlStateValueOff];
    
    NSArray *albumArray = self.albumArray;
    
    if( albumTable.selectedRow > 0 && matrixThumbnails == NO)
    {
        NSManagedObject	*album = [albumArray objectAtIndex: albumTable.selectedRow];
        
        if( [[album valueForKey:@"smartAlbum"] boolValue] == NO)
            result = HorosRunInformationalAlertPanel(NSLocalizedString(@"Delete/Remove images", nil), NSLocalizedString(@"Do you want to only remove the selected images from the current album or delete them from the database? (%@)", nil), NSLocalizedString(@"Delete",nil), NSLocalizedString(@"Cancel",nil), NSLocalizedString(@"Remove from current album",nil), level);
        else
        {
            result = HorosRunInformationalAlertPanel(NSLocalizedString(@"Delete images", nil), NSLocalizedString(@"Are you sure you want to delete the selected images? (%@)", nil), NSLocalizedString(@"OK",nil), NSLocalizedString(@"Cancel",nil), nil, level);
        }
    }
    else
    {
        result = HorosRunInformationalAlertPanel(NSLocalizedString(@"Delete images", nil), NSLocalizedString(@"Are you sure you want to delete the selected images? (%@)", nil), NSLocalizedString(@"OK",nil), NSLocalizedString(@"Cancel",nil), nil, level);
    }
    
    [context retain];
    N2ManagedObjectContextPerformAndWait(context, ^{
    
    if( result == HorosAlertOtherResponse)	// REMOVE FROM CURRENT ALBUMS, BUT DONT DELETE IT FROM THE DATABASE
    {
        NSIndexSet* selectedRows = [databaseOutline selectedRowIndexes];
        if (selectedRows.count)
        {
            NSMutableArray* studiesToRemove = [NSMutableArray array];
            DicomAlbum* album = [albumArray objectAtIndex:albumTable.selectedRow];
            
            // row has to outlive the iteration; see the note at the other loops.
            NSInteger row = 0;
            for (NSInteger x = 0; x < selectedRows.count; ++x) {
                row = (x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex:row];
                DicomStudy* study = [databaseOutline itemAtRow: row];
                
                if ([study isKindOfClass:[DicomStudy class]])
                    if ([album.studies containsObject:study] && ![studiesToRemove containsObject:study])
                        [studiesToRemove addObject:study];
            }
            
            NSMutableSet* albumStudies = [album mutableSetValueForKey: @"studies"];
            for (DicomStudy* study in studiesToRemove) {
                [albumStudies removeObject:study];
                [study archiveAnnotationsAsDICOMSR];
            }
            
            if (![_database isLocal]) // notify the remote database about the removal of the selected studies from the current album
                [(RemoteDicomDatabase*)_database removeStudies:studiesToRemove fromAlbum:album];
            
            [databaseOutline selectRowIndexes:[NSIndexSet indexSetWithIndex:[selectedRows firstIndex]] byExtendingSelection:NO];
        }
        
        WaitRendering *wait = [[WaitRendering alloc] init: NSLocalizedString(@"Updating database...", nil)];
        [wait showWindow:self];
        
        @try
        {
            (void)[_database save:NULL];
            
            [self outlineViewRefresh];
            [self refreshAlbums];
        }
        @catch( NSException *ne)
        {
            N2LogExceptionWithStackTrace(ne);
        }
        
        [wait close];
        [wait autorelease];
        
        [self refreshMatrix: self];
        
#ifndef OSIRIX_LIGHT
        [[QueryController currentQueryController] executeRefresh: self];
        [[QueryController currentAutoQueryController] executeRefresh: self];
#endif
    }
    else if (![_database isLocal])
    {
        
        HorosRunAlertPanel( NSLocalizedString(@"Distant Database", nil),  NSLocalizedString(@"You cannot modify a Distant Database.", nil), nil, nil, nil);
        
        [animationCheck setState: animState];
        
        return;
    }
    
    if( result == HorosAlertDefaultResponse)	// REMOVE AND DELETE IT FROM THE DATABASE
    {
        NSMutableArray *objectsToDelete = [NSMutableArray array];
        NSMutableSet *objectsToDeleteTree = [NSMutableSet set];
        
        if( matrixThumbnails)
            (void)[self filesForDatabaseMatrixSelection: objectsToDelete onlyImages: NO];
        else
            [self filesForDatabaseOutlineSelection: objectsToDelete treeObjects:objectsToDeleteTree onlyImages: NO];
        
        if( [databaseOutline selectedRow] >= 0)
        {
            NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
            
            [self delObjects:objectsToDelete tree:objectsToDeleteTree];
            
            [databaseOutline selectRowIndexes: [NSIndexSet indexSetWithIndex: [selectedRows firstIndex]] byExtendingSelection:NO];
        }
    }
    
    });
    [context release];
    
    [animationCheck setState: animState];
}

- (void)buildColumnsMenu
{
    [columnsMenu release];
    columnsMenu = [[NSMenu alloc] initWithTitle:@""];
    [columnsMenu setDelegate:self];
    
    NSMutableArray* cols = [NSMutableArray array];
    for (NSTableColumn* col in [databaseOutline tableColumns])
        [cols addObject:[NSArray arrayWithObjects: col, [[col headerCell] stringValue], nil]];
    [cols sortUsingComparator: ^NSComparisonResult(id obj1, id obj2) {
        return [[obj1 objectAtIndex:1] compare:[obj2 objectAtIndex:1]];
    }];
    
    for (NSArray* a in cols)
    {
        NSTableColumn* col = [a objectAtIndex:0];
        NSMenuItem* item = [columnsMenu addItemWithTitle:[[col headerCell] stringValue] action:@selector(columnsMenuAction:) keyEquivalent:@""];
        [item setRepresentedObject:[col identifier]];
    }
    
    [[databaseOutline headerView] setMenu:columnsMenu];
}

-(void)columnsMenuWillOpen {
    NSArray* cols = [databaseOutline tableColumns];
    NSArray* columnIdentifiers = [cols valueForKey:@"identifier"];
    for (NSMenuItem* mi in [columnsMenu itemArray]) {
        id ro = [mi representedObject];
        
        if ([ro isEqualToString:@"name"])
        {
            if ([[NSUserDefaults standardUserDefaults] boolForKey:@"HIDEPATIENTNAME"])
                [mi setState: NSControlStateValueOff];
            else [mi setState: NSControlStateValueOn];
        }
        else
        {
            NSInteger index = [columnIdentifiers indexOfObject:ro];
            if (index != NSNotFound && ![[cols objectAtIndex:index] isHidden])
                [mi setState: NSControlStateValueOn];
            else [mi setState: NSControlStateValueOff];
        }
    }
}

- (void) columnsMenuAction: (id)sender
{
    [sender setState: ![sender state]];
    
    if( [[sender representedObject] isEqualToString:@"name"]) [[NSUserDefaults standardUserDefaults] setBool:![sender state] forKey:@"HIDEPATIENTNAME"];
    else
    {
        NSArray				*titleArray = [[columnsMenu itemArray] valueForKey:@"title"];
        NSMutableDictionary	*dict = [NSMutableDictionary dictionaryWithCapacity: 0];
        
        for( int i = 0; i < [titleArray count]; i++)
        {
            NSString*	key = [titleArray objectAtIndex: i];
            
            if( [key length] > 0)
                [dict setValue: [NSNumber numberWithInt: [[[columnsMenu itemArray] objectAtIndex: i] state]] forKey: key];
        }
        
        [[NSUserDefaults standardUserDefaults] setObject:dict forKey:@"COLUMNSDATABASE"];
        
        [self refreshColumns];
    }
}

- (void)refreshColumns
{
    NSDictionary	*columnsDatabase	= [[NSUserDefaults standardUserDefaults] objectForKey: @"COLUMNSDATABASE"];
    NSEnumerator	*enumerator			= [columnsDatabase keyEnumerator];
    NSString		*key;
    
    //	[_database lock];
    @try
    {
        while( key = [enumerator nextObject])
        {
            NSInteger index = [[[[databaseOutline tableColumns] valueForKey:@"headerCell"] valueForKey:@"title"] indexOfObject: key];
            
            if( index != NSNotFound)
            {
                NSString	*identifier = [[[databaseOutline tableColumns] objectAtIndex: index] identifier];
                
                if( [databaseOutline isColumnWithIdentifierVisible: identifier] != [[columnsDatabase valueForKey: key] intValue])
                {
                    if( [[columnsDatabase valueForKey: key] intValue] == NO && [databaseOutline columnWithIdentifier: identifier] == [databaseOutline selectedColumn])
                        [databaseOutline selectColumnIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO];
                    
                    [databaseOutline setColumnWithIdentifier:identifier visible: [[columnsDatabase valueForKey: key] intValue]];
                    
                    if( [[columnsDatabase valueForKey: key] intValue] == NSControlStateValueOn)
                    {
                        [databaseOutline scrollColumnToVisible: [databaseOutline columnWithIdentifier: identifier]];
                    }
                }
            }
        }
        
        [self buildColumnsMenu];
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        //		[_database unlock];
    }
}

- (id)outlineView:(NSOutlineView *)outlineView child:(NSInteger)index ofItem:(id)item
{
    if (_database == nil) return nil;
    
    id returnVal = nil;
    
    //	[_database lock];
    
    @try
    {
        if( item == nil)
        {
            returnVal = [outlineViewArray objectAtIndex: index];
        }
        else
        {
#ifndef  OSIRIX_LIGHT
            if( [item isKindOfClass: [DCMTKStudyQueryNode class]])
                returnVal = [[item children]  objectAtIndex: index];
            else
#endif
                returnVal = [[self childrenArray: item] objectAtIndex: index];
        }
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    //	[_database unlock];
    
    return returnVal;
}

- (BOOL)outlineView:(NSOutlineView *)outlineView isItemExpandable:(id)item
{
    BOOL returnVal = NO;
    
    //	[_database lock];
    
    if ([item isKindOfClass:[HorosSurgicalProcedureOutlineRow class]])
        return NO;
    
    if( [item isDistant])
    {
#ifndef OSIRIX_LIGHT
        if( [item isKindOfClass: [DCMTKStudyQueryNode class]])
            return YES;
        else
            return NO;
#endif
    }
    
    if ([[item valueForKey:@"type"] isEqualToString:@"Series"])
        returnVal = NO;
    else returnVal = YES;
    
    //	[_database unlock];
    
    return returnVal;
}

- (NSInteger)outlineView:(NSOutlineView *)outlineView numberOfChildrenOfItem:(id)item
{
    if( _database == nil) return 0;
    
    int returnVal = 0;
    
    //	[_database lock];
    
    if (!item)
    {
        returnVal = [outlineViewArray count];
    }
    else
    {
        if ([item isKindOfClass:[HorosSurgicalProcedureOutlineRow class]])
            return 0;
#ifndef OSIRIX_LIGHT
        if( [item isDistant])
        {
            @try
            {
                if( [item isKindOfClass: [DCMTKStudyQueryNode class]])
                {
                    NSArray *children = [item children];
                    
                    if( children.count > 0 && [[children lastObject] isKindOfClass: [DCMTKStudyQueryNode class]] == NO && [[children lastObject] isKindOfClass: [DCMTKSeriesQueryNode class]] == NO)
                        [item purgeChildren];
                    
                    if (![item children])
                    {
                        [item queryWithValues:nil];
                        
                        if( [item children] == nil) // It failed... put an empty children...
                            [item setChildren: [NSMutableArray array]];
                    }
                }
                return  (item == nil) ? 0 : [[item children] count];
            }
            @catch (NSException * e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            
            return 0;
        }
        else
#endif
            if ([[item valueForKey:@"type"] isEqualToString:@"Image"]) returnVal = 0;
            else if ([[item valueForKey:@"type"] isEqualToString:@"Series"]) returnVal = [[item valueForKey:@"noFiles"] intValue];
            else if ([[item valueForKey:@"type"] isEqualToString:@"Study"]) returnVal = [[item valueForKey:@"imageSeries"] count];
    }
    
    //	[_database unlock];
    
    return returnVal;
}

- (id)intOutlineView:(NSOutlineView *)outlineView objectValueForTableColumn:(NSTableColumn *)tableColumn byItem:(id)item
{
    // *********************************************
    //	PLUGINS
    // *********************************************
    
    if( [[[NSUserDefaults standardUserDefaults] stringForKey:@"REPORTSMODE"] intValue] == 3 && [[tableColumn identifier] isEqualToString:@"reportURL"])
    {
        if ([[item valueForKey:@"type"] isEqualToString:@"Study"])
        {
            NSBundle *plugin = [[PluginManager reportPlugins] objectForKey: [[NSUserDefaults standardUserDefaults] stringForKey:@"REPORTSPLUGIN"]];
            
            if( plugin)
            {
                PluginFilter* filter = [[plugin principalClass] filter];
                
                [PluginManager startProtectForCrashWithFilter: filter];
                
                id returnValue = [filter reportDateForStudy: item];
                
                [PluginManager endProtectForCrash];
                
                return returnValue;
                //return [filter report: item action: @"dateReport"];
            }
            return nil;
        }
        return nil;
    }
    else if( [[tableColumn identifier] isEqualToString:@"reportURL"])
    {
        if ([[item valueForKey:@"type"] isEqualToString:@"Study"])
        {
            if( [item valueForKey:@"reportURL"])
            {
                // The date of the latest report image (#645), found without
                // asking the study for its report image: that merges duplicate
                // report series and saves, which drawing a row must not do.
                NSDate *latest = nil;
                for( DicomSeries *series in [item valueForKey: @"series"])
                {
                    if( [[series valueForKey:@"id"] intValue] != 5003 ||
                       [[series valueForKey:@"name"] isEqualToString: @"OsiriX Report SR"] == NO ||
                       [DCMAbstractSyntaxUID isStructuredReport:[series valueForKey:@"seriesSOPClassUID"]] == NO)
                        continue;
                    
                    for( DicomImage *image in [series valueForKey: @"images"])
                    {
                        NSDate *date = [image valueForKey: @"date"];
                        if( date && (latest == nil || [date compare: latest] == NSOrderedDescending))
                            latest = date;
                    }
                }
                return latest;
            }
            else return nil;
        }
        else return nil;
    }
    
    if( [[tableColumn identifier] isEqualToString:@"stateText"])
    {
        if( [[item valueForKey:@"stateText"] intValue] == 0)
            return nil;
        else
            return [item valueForKey:@"stateText"];
    }
    
    if( [[tableColumn identifier] isEqualToString:@"lockedStudy"])
    {
        if ([[item valueForKey:@"type"] isEqualToString:@"Study"] == NO) return nil;
    }
    
    if( [[tableColumn identifier] isEqualToString:@"note"]) // the note of a study, on one line; series and studies of DICOM nodes have none
    {
        if ([item isKindOfClass: [DicomStudy class]] == NO) return nil;
        return [HorosStudyNote singleLineTextOfNote: [(DicomStudy*) item note]];
    }
    
    if( [[tableColumn identifier] isEqualToString:@"modality"])
    {
        return [item valueForKey:@"modality"];
    }
    
    if( [[tableColumn identifier] isEqualToString:@"name"])
    {
        if ([[item valueForKey:@"type"] isEqualToString:@"Study"])
        {
            NSString	*name;
            
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"HIDEPATIENTNAME"])
                name = [NSString stringWithString: NSLocalizedString( @"Name hidden", nil)];
            else
                name = [item valueForKey:@"name"];
            
            if( [item isDistant])
                return name;

            if ([item isKindOfClass:[NSManagedObject class]] && _database)
            {
                DicomDatabase *origin = [DicomDatabase databaseForContext:[(NSManagedObject *)item managedObjectContext]];
                if (origin && origin != _database && [origin.baseDirPath isEqualToString:_database.baseDirPath] == NO && [HorosFederatedSearch pathsEqual:origin.baseDirPath other:_database.baseDirPath] == NO)
                    return [HorosFederatedSearch displayName:name origin:[HorosFederatedSearch displayOriginWithName:origin.name path:origin.baseDirPath] currentOrigin:_database.name];
            }
            
            return name; // [NSString stringWithFormat: NSLocalizedString( @"%@ (%d series)", nil), name, [[item valueForKey:@"imageSeries"] count]];
        }
    }
    
    if ([[item valueForKey:@"type"] isEqualToString:@"Study"] == NO)
    {
        if( [[tableColumn identifier] isEqualToString:@"dateOfBirth"])			return @"";
        if( [[tableColumn identifier] isEqualToString:@"referringPhysician"])	return @"";
        if( [[tableColumn identifier] isEqualToString:@"performingPhysician"])	return @"";
        if( [[tableColumn identifier] isEqualToString:@"institutionName"])		return @"";
        if( [[tableColumn identifier] isEqualToString:@"patientID"])			return @"";
        if( [[tableColumn identifier] isEqualToString:@"yearOld"])				return @"";
        if( [[tableColumn identifier] isEqualToString:@"accessionNumber"])		return @"";
        if( [[tableColumn identifier] isEqualToString:@"noSeries"])             return @"";
    }
    
    if( [[tableColumn identifier] isEqualToString:@"yearOld"])
    {
        switch ( [[NSUserDefaults standardUserDefaults] integerForKey: @"yearOldDatabaseDisplay"])
        {
            case 0:
                return [item valueForKey: @"yearOld"];
                break;
                
            case 1:
                return [item valueForKey: @"yearOldAcquisition"];
                break;
                
            case 2:
            default:
            {
                NSString *yearOld = [item valueForKey: @"yearOld"];
                NSString *yearOldAcquisition = [item valueForKey: @"yearOldAcquisition"];
                
                if( [yearOld isEqualToString: yearOldAcquisition])
                    return yearOld;
                else
                {
                    if( [yearOld hasSuffix: NSLocalizedString( @" y", @"y = year")] && [yearOldAcquisition hasSuffix: NSLocalizedString( @" y", @"y = year")])
                        return [NSString stringWithFormat: @"%@/%@%@", [yearOld substringToIndex: yearOld.length-[NSLocalizedString( @" y", @"y = year") length]], [yearOldAcquisition substringToIndex: yearOldAcquisition.length-[NSLocalizedString( @" y", @"y = year") length]], NSLocalizedString( @" y", @"y = year")];
                    else
                        return [NSString stringWithFormat: @"%@/%@", yearOld, yearOldAcquisition];
                }
            }
                break;
        }
        
    }
    
    if( [[tableColumn identifier] isEqualToString:@"noSeries"])
    {
        if( [item isKindOfClass: [DicomStudy class]])
            return [NSString stringWithFormat: @"%d", (int) [(DicomStudy*) item numberOfImageSeries]];
        
        if( [item valueForKey:@"imageSeries"])
            return [NSString stringWithFormat: @"%d", (int) [[item valueForKey:@"imageSeries"] count]];
        else
            return @"";
    }
    
    id value = nil;
    BOOL accessed = NO;
    
    if ([[item valueForKey:@"type"] isEqualToString:@"Series"] && [[tableColumn identifier] isEqualToString:@"studyName"])
    {
        if( [item isDistant])
            value = [item valueForKey:@"seriesDescription"];
        else
            value = [item valueForKey:@"seriesDescription"];
        accessed = YES;
    }
    
    if (!accessed)
        value = [item valueForKey:[tableColumn identifier]];
    
    if ([[item valueForKey:@"type"] isEqualToString:@"Series"])
    {   // only Series
        if ([[tableColumn identifier] isEqualToString:@"name"] || [[tableColumn identifier] isEqualToString:@"studyName"] || [[tableColumn identifier] isEqualToString:@"modality"])    // only name & description & modality
        {
            if (!value || ([value isKindOfClass:[NSString class]] && [(NSString*)value length] == 0))
                return NSLocalizedString(@"unknown", nil);
        }
    }
    return value;
}

- (id)outlineView:(NSOutlineView *)outlineView objectValueForTableColumn:(NSTableColumn *)tableColumn byItem:(id)item
{
    if (_database == nil)
        return nil;
    [item retain];
    //	[_database lock];
    @try {
        return [self intOutlineView:outlineView objectValueForTableColumn:tableColumn byItem:item];
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally {
        //        [_database unlock];
        [item release];
    }
    
    return nil;
}

- (void) setDatabaseValue:(id) object item:(id) item forKey:(NSString*) key
{
    if( [item isDistant])
        return;
    
    DatabaseIsEdited = NO;
    
    // The edit is over as far as this object is concerned, but the outline is
    // still in its editing session; catch up once it is not.
    [self performSelector: @selector(_refreshDatabaseDisplayIfDeferred) withObject: nil afterDelay: 0];
    
    //	[_database lock];
    @try {
        if (![_database isLocal])
            [(RemoteDicomDatabase*)_database object:item setValue:object forKey:key];
        
        if( [key isEqualToString:@"stateText"])
        {
            for( id managedObject in [self databaseSelection])
            {
                if( [object intValue] >= 0)
                    [managedObject setValue:object forKey:key];
            }
        }
        else if( [key isEqualToString:@"lockedStudy"])
        {
            for( id managedObject in [self databaseSelection])
            {
                if( [[managedObject valueForKey:@"type"] isEqualToString:@"Study"])
                    [managedObject setValue:[NSNumber numberWithBool: [object intValue]] forKey: @"lockedStudy"];
            }
        }
        else
        {
            for( id managedObject in [self databaseSelection])
            {
                [managedObject setValue:object forKey:key];
            }
        }
        
        [refreshTimer setFireDate: [NSDate dateWithTimeIntervalSinceNow:0.5]];
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        //        [_database unlock];
    }
    
    (void)[_database save:NULL];
    
#ifndef OSIRIX_LIGHT
    if( [QueryController currentQueryController])
        [[QueryController currentQueryController] refresh: self];
    else if( [QueryController currentAutoQueryController])
        [[QueryController currentAutoQueryController] refresh: self];
#endif
    
    [databaseOutline reloadData];
}

- (void)outlineView:(NSOutlineView *)outlineView setObjectValue:(id)object forTableColumn:(NSTableColumn *)tableColumn byItem:(id)item
{
    if( [item isDistant])
        return;
    
    if ([self.database isReadOnly])
        return;
    
    [self setDatabaseValue: object item: item forKey: [tableColumn identifier]];
}

- (void)outlineView:(NSOutlineView *)outlineView sortDescriptorsDidChange:(NSArray *)oldDescriptors
{
    // outlineViewRefresh restores selected objects at their new sorted rows.
    [self outlineViewRefresh];
    if ([databaseOutline selectedRow] >= 0)
        [databaseOutline scrollRowToVisible: [databaseOutline selectedRow]];
}

-(NSString*)outlineView:(NSOutlineView*)outlineView toolTipForCell:(NSCell*)cell rect:(NSRectPointer)rect tableColumn:(NSTableColumn*)tableColumn item:(id)item mouseLocation:(NSPoint)mouseLocation
{
    if ([item isDistant])
        return NSLocalizedString( @"Double-Click to retrieve", nil);;
    
    @try
    {
        if ([[tableColumn identifier] isEqualToString:@"name"])
        {
            NSRect imageFrame = NSMakeRect(rect->origin.x, rect->origin.y, rect->size.height, rect->size.height);
            if (NSPointInRect(mouseLocation, imageFrame))
            {
                NSDate* now = [NSDate date];
                NSDate* today0 = [NSDate dateWithTimeIntervalSinceReferenceDate:floor([now timeIntervalSinceReferenceDate]/(60*60*24))*(60*60*24)];
                NSDate* acqDate = [item valueForKey:@"date"];
                NSTimeInterval acqInterval = [now timeIntervalSinceDate:acqDate];
                NSTimeInterval addInterval = [now timeIntervalSinceDate:[item valueForKey:@"dateAdded"]];
                
                if (acqInterval <= 60*10) return NSLocalizedString(@"Acquired within the last 10 minutes", nil);
                else if (acqInterval <= 60*60) return NSLocalizedString(@"Acquired within the last hour", nil);
                else if (acqInterval <= 4*60*60) return NSLocalizedString(@"Acquired within the last 4 hours", nil);
                else if ([acqDate timeIntervalSinceDate:today0] >= 0) return NSLocalizedString(@"Acquired today", nil); // today
                else if (addInterval <= 60) return NSLocalizedString(@"Added within the last 60 seconds", nil);
            }
        }
    } @catch (NSException* e) {
    }
    
    return nil;
}

- (void)outlineView: (NSOutlineView *)outlineView willDisplayCell: (id)cell forTableColumn: (NSTableColumn *)tableColumn item: (id)item
{
    [cell setHighlighted: NO];
    
    if( [cell isKindOfClass: [ImageAndTextCell class]])
    {
        [(ImageAndTextCell*) cell setImage: nil];
        [(ImageAndTextCell*) cell setLastImage: nil];
    }
    
    NSManagedObjectContext	*context = self.database.managedObjectContext;
    
    N2ManagedObjectContextPerformAndWait(context, ^{
    
    @try
    {
        if ([[item valueForKey:@"type"] isEqualToString: @"Study"])
        {
            if( [[tableColumn identifier] isEqualToString:@"lockedStudy"])
                [cell setTransparent: NO];
            
            if( [item isDistant])
            {
                [cell setFont: [NSFont fontWithName: DISTANTSTUDYFONT size: [self fontSize: @"dbFont"]]];
            }
            else if( originalOutlineViewArray)
            {
                if( [originalOutlineViewStudies containsObject: item]) [cell setFont: [NSFont boldSystemFontOfSize: [self fontSize: @"dbFont"]]];
                else [cell setFont: [NSFont systemFontOfSize: [self fontSize: @"dbFont"]]];
            }
            else [cell setFont: [NSFont boldSystemFontOfSize: [self fontSize: @"dbFont"]]];
            
            if( [[tableColumn identifier] isEqualToString:@"name"])
            {
                BOOL	icon = NO;
                
                if( [[NSUserDefaults standardUserDefaults] boolForKey: @"displaySamePatientWithColorBackground"] && [[self window] firstResponder] == outlineView)
                {
                    if( [[previousItem valueForKey: @"type"] isEqualToString:@"Study"])
                    {
                        NSString *uid = [item valueForKey: @"patientUID"];
                        
                        if( previousItem != item && [uid length] > 1 && [uid compare: [previousItem valueForKey: @"patientUID"] options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
                        {
                            [cell setDrawsBackground: YES];
                            // This was disabledControlTextColor, which is a
                            // *text* colour: pure black at 25% alpha in Aqua and
                            // pure white at 25% in Dark Aqua. Filled behind a
                            // patient name it is the black band over consecutive
                            // studies of one patient that #300 reports, and its
                            // mirror image in dark mode. The commented-out
                            // original was secondarySelectedControlColor, a row
                            // background; this is its modern replacement (#380,
                            // A300).
                            [cell setBackgroundColor: [NSColor unemphasizedSelectedContentBackgroundColor]];
                        }
                        else
                            [cell setDrawsBackground: NO];
                    }
                    else
                        [cell setDrawsBackground: NO];
                }
                else
                    [cell setDrawsBackground: NO];
                
                if( [[item valueForKey:@"date"] timeIntervalSinceNow] > -24*60*60)	// 24 hours
                {
                    DCMCalendarDate	*now = [DCMCalendarDate calendarDate];
                    DCMCalendarDate	*start = [DCMCalendarDate dateWithYear:[now yearOfCommonEra] month:[now monthOfYear] day:[now dayOfMonth] hour:0 minute:0 second:0 timeZone: [now timeZone]];
                    NSDate			*today = [NSDate dateWithTimeIntervalSinceNow: [start timeIntervalSinceDate: now]];
                    
                    icon = YES;
                    if( [[item valueForKey:@"date"] timeIntervalSinceNow] > -60*10) [(ImageAndTextCell*) cell setImage:[NSImage imageNamed:@"Realised1.tif"]];													// 10 min
                    else if( [[item valueForKey:@"date"] timeIntervalSinceNow] > -60*60) [(ImageAndTextCell*) cell setImage:[NSImage imageNamed:@"Realised2.tif"]];												// 1 hour
                    else if( [[item valueForKey:@"date"] timeIntervalSinceNow] > -4*60*60) [(ImageAndTextCell*) cell setImage:[NSImage imageNamed:@"Realised3.tif"]];											// 4 hours
                    else if( [[item valueForKey:@"date"] timeIntervalSinceReferenceDate] > [today timeIntervalSinceReferenceDate]) [(ImageAndTextCell*) cell setImage:[NSImage imageNamed:@"Realised4.tif"]];	// today
                    else icon = NO;
                }
                
                if( icon == NO)
                {
                    if( [item valueForKey:@"dateAdded"] && [[item valueForKey:@"dateAdded"] timeIntervalSinceNow] > -60) [(ImageAndTextCell*) cell setImage:[NSImage imageNamed:@"Receiving.tif"]];
                }
            }
            
            if( [[tableColumn identifier] isEqualToString: @"reportURL"])
            {
                // The recorded link, as it is: a file that has gone is found
                // when the report is opened, not by a disk access per row per
                // redraw - nor by editing the study while drawing it.
                NSString *reportURL = [item valueForKey:@"reportURL"];
                if( reportURL.length)
                {
                    static NSImage *localReportIcon = nil, *webReportIcon = nil;
                    static dispatch_once_t once;
                    dispatch_once( &once, ^{
                        localReportIcon = [[NSImage imageNamed:@"Report.icns"] copy];
                        [localReportIcon setSize: NSMakeSize(16, 16)];
                        webReportIcon = [[[NSWorkspace sharedWorkspace] iconForContentType:([UTType typeWithFilenameExtension:@"download"] ?: UTTypeData)] copy];
                        if( webReportIcon == nil) webReportIcon = [localReportIcon retain];
                        [webReportIcon setSize: NSMakeSize(16, 16)];
                    });
                    
                    BOOL webLink = [_database isLocal] && ([reportURL hasPrefix: @"http://"] || [reportURL hasPrefix: @"https://"]);
                    [(ImageAndTextCell*) cell setImage: webLink ? webReportIcon : localReportIcon];
                }
            }
        }
        else
        {
            if( [[tableColumn identifier] isEqualToString:@"lockedStudy"])
                [cell setTransparent: YES];
            
            [cell setFont: [NSFont boldSystemFontOfSize: [self fontSize: @"dbSeriesFont"]]];
        }
        [cell setLineBreakMode: NSLineBreakByTruncatingMiddle];
        
        // gray "unknown" values
        
        if ([cell respondsToSelector:@selector(setTextColor:)])
        {
            BOOL gray = NO;
            if ([[item valueForKey:@"type"] isEqualToString:@"Series"])                                                                                                                         // only Series
                if ([[tableColumn identifier] isEqualToString:@"name"] || [[tableColumn identifier] isEqualToString:@"studyName"] || [[tableColumn identifier] isEqualToString:@"modality"])    // only name & description & modality
                {
                    id value = nil;
                    BOOL accessed = NO;
                    
                    if ([[item valueForKey:@"type"] isEqualToString:@"Series"] && [[tableColumn identifier] isEqualToString:@"studyName"])
                    {
                        value = [item valueForKey:@"seriesDescription"];
                        accessed = YES;
                    }
                    
                    if (!accessed)
                        value = [item valueForKey:[tableColumn identifier]];
                    
                    if (!value || ([value isKindOfClass:[NSString class]] && [(NSString*)value length] == 0))
                        gray = YES;
                }
            [cell setTextColor: gray? [NSColor disabledControlTextColor] : [NSColor controlTextColor]];
        }
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    });
    
}

- (void)tableView:(NSTableView *)tableView mouseDownInHeaderOfTableColumn:(NSTableColumn *)tableColumn
{
    
}

#pragma mark database drag export (#605)

// Implemented in Swift since #831, with the same selectors: BrowserController+DatabaseDragExport.swift and BrowserController+DatabaseDragExport+Selection.swift.

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark Thumbnails Matrix & Preview functions

static BOOL withReset = NO;

- (DCMPix *)previewPix:(int)i
{
    @synchronized( previewPixThumbnails)
    {
        return [previewPix objectAtIndex:i];
    }
    
    return nil;
}

- (void) initAnimationSlider
{
    BOOL	animate = NO;
    long	noOfImages = 0;
    
    NSButtonCell    *cell = (NSButtonCell *)[oMatrix selectedCell];
    
    if( cell)
    {
        if( [cell tag] >= [matrixViewArray count])
        {
            [oMatrix selectCellWithTag: 0];
            cell = (NSButtonCell *)[oMatrix selectedCell];
        }
        
        
//        [cell setLineBreakMode: NSLineBreakByCharWrapping];
//        [cell setFont:[NSFont systemFontOfSize: [self fontSize: @"dbMatrixFont"]]];
//        
//        [cell setImagePosition: NSImageBelow];
//        [cell setTransparent:NO];
//        [cell setEnabled:YES];
//        
//        [cell setButtonType:NSButtonTypePushOnPushOff];
//        [cell setBezelStyle:NSBezelStyleShadowlessSquare];
//        [cell setShowsStateBy:NSPushInCellMask];
//        [cell setHighlightsBy:NSContentsCellMask];
//        [cell setImageScaling:NSImageScaleProportionallyDown];
//        [cell setBordered:YES];
        
        
        
        NSManagedObject   *aFile = [databaseOutline itemAtRow:[databaseOutline selectedRow]];
        if ([[aFile valueForKey:@"type"] isEqualToString:@"Series"] &&
            [[[aFile valueForKey:@"images"] allObjects] count] == 1 &&
            [[[[[aFile valueForKey:@"images"] allObjects] objectAtIndex:0] valueForKey:@"numberOfFrames"] intValue] > 1)
        {
            noOfImages = [[[[[aFile valueForKey:@"images"] allObjects] objectAtIndex:0] valueForKey:@"numberOfFrames"] intValue];
            animate = YES;
        }
        else if([[aFile valueForKey:@"type"] isEqualToString:@"Series"] && [[[aFile valueForKey:@"images"] allObjects] count] > 1)
        {
            noOfImages = [[[aFile valueForKey:@"images"] allObjects] count];
            animate = YES;
        }
        else if([[aFile valueForKey:@"type"] isEqualToString:@"Study"])
        {
            
            NSArray *images = matrixViewArray.count? [self imagesArray: [matrixViewArray objectAtIndex: [cell tag]]] : nil;
            
            if( [images count])
            {
                if( [images count] > 1) noOfImages = [images count];
                else noOfImages = [[[images objectAtIndex:0] valueForKey:@"numberOfFrames"] intValue];
                
                if( [images count] > 1)
                {
                    animate = YES;
                }
                else if( noOfImages > 1)	// It's a multi-frame single image
                {
                    animate = YES;
                }
            }
            if( images == nil)
            {
                [self outlineViewRefresh];
                [self refreshMatrix: self];
                return;
            }
        }
        
        if( animate == NO)
        {
            [animationSlider setEnabled:NO];
            [animationSlider setMaxValue:0];
            [animationSlider setNumberOfTickMarks:1];
            [animationSlider setIntValue:0];
        }
        else if( [animationSlider isEnabled] == NO)
        {
            [animationSlider setEnabled:YES];
            [animationSlider setMaxValue: noOfImages-1];
            [animationSlider setNumberOfTickMarks: noOfImages];
            [animationSlider setIntValue:0];	//noOfImages/2
        }
    }
    else
    {
        [animationSlider setEnabled:NO];
        [animationSlider setMaxValue:0];
        [animationSlider setNumberOfTickMarks:1];
        [animationSlider setIntValue:0];
    }
    
    withReset = YES;
    [self previewSliderAction: animationSlider];
    withReset = NO;
}

// The identity the preview asks for, built from the database row alone (#380 D).
static HorosPreviewFrame *HorosPreviewFrameForImage( DicomImage *image, int frame)
{
    if( image == nil) return nil;
    return [[[HorosPreviewFrame alloc] initWithPath: image.completePath ?: @""
        sopInstanceUID: image.sopInstanceUID ?: @""
        seriesInstanceUID: [image valueForKeyPath: @"series.seriesDICOMUID"] ?: @""
        sopClassUID: [image valueForKeyPath: @"series.seriesSOPClassUID"] ?: @""
        modality: [image valueForKeyPath: @"series.modality"] ?: @""
        frameNumber: frame frameCount: [image.numberOfFrames intValue]
        rows: [image.height intValue] columns: [image.width intValue]
        seriesID: [[image valueForKeyPath: @"series.id"] intValue]] autorelease];
}

- (DCMPix*) getDCMPixFromViewerIfAvailable: (NSString*) pathToFind frameNumber: (int) frameNumber
{
    return [self getDCMPixFromViewerIfAvailable: pathToFind frameNumber: frameNumber expectedFrame: nil];
}

- (DCMPix*) getDCMPixFromViewerIfAvailable: (NSString*) pathToFind frameNumber: (int) frameNumber expectedFrame: (HorosPreviewFrame*) expectedFrame
{
    if( [NSThread isMainThread] == NO)
        return nil;
    
    DCMPix *returnPix = nil;
    
    //Is this image already displayed on the front most 2D viewers? -> take the dcmpix from there
    for( ViewerController *v in [ViewerController get2DViewers])
    {
        [v retain];
        
        if( ![v windowWillClose])
        {
            NSArray *vFileList = nil;
            NSArray *vPixList = nil;
            NSData *volumeData = nil;
            
            @try {
                // We need to temporarly retain all these objects
                vFileList = [[v fileList] copy];
                vPixList = [[v pixList] copy];
                volumeData = [[v volumeData] retain];
            }
            @catch (NSException * e) {
                N2LogExceptionWithStackTrace(e);
            }
            
            @try
            {
                NSUInteger i = NSNotFound;
                
                // Frame 0 used to match on the path alone. A multiframe file is
                // one row per frame in a viewer's file list, so that returned
                // whichever frame of the file the viewer happened to hold, and
                // the preview then showed a frame nobody asked for. Match the
                // frame in every case (#380 D).
                for( int x = 0 ; x < vFileList.count; x++)
                {
                    DicomImage *image = [vFileList objectAtIndex: x];
                    
                    if( [image.completePath isEqualToString: pathToFind] && [image.frameID intValue] == frameNumber)
                    {
                        i = x;
                        break;
                    }
                }
                
                if( i != NSNotFound && expectedFrame)
                {
                    // The identity of what is loaded elsewhere, against what was
                    // asked for: same file, same frame, same series, same size.
                    DicomImage *image = [vFileList objectAtIndex: i];
                    HorosPreviewFrame *loaded = [[[HorosPreviewFrame alloc] initWithPath: image.completePath ?: @""
                        sopInstanceUID: image.sopInstanceUID ?: @""
                        seriesInstanceUID: [image valueForKeyPath: @"series.seriesDICOMUID"] ?: @""
                        sopClassUID: [image valueForKeyPath: @"series.seriesSOPClassUID"] ?: @""
                        modality: [image valueForKeyPath: @"series.modality"] ?: @""
                        frameNumber: [image.frameID intValue] frameCount: [image.numberOfFrames intValue]
                        rows: [image.height intValue] columns: [image.width intValue]
                        seriesID: [[image valueForKeyPath: @"series.id"] intValue]] autorelease];
                    NSString *refusal = [HorosPreviewIdentity refusalForReusing: loaded asRequested: expectedFrame];
                    if( refusal)
                    {
                        NSLog( @"Preview: not reusing a loaded frame: %@", refusal);
                        i = NSNotFound;
                    }
                }
                
                if( i != NSNotFound)
                {
                    DCMPix *dcmPix = [vPixList objectAtIndex: i];
                    
                    [dcmPix.checking lock];
                    
                    [dcmPix CheckLoad];
                    
                    // The viewer decoded this file at some earlier moment. If the file
                    // was rewritten, replaced or removed since, its pixels are not the
                    // file the preview was asked for (#603).
                    if( [dcmPix isLoaded] && [dcmPix loadedFileMatchesDisk] == NO)
                        NSLog( @"Preview: not reusing a loaded frame: %@", [HorosFileRevision refusalForReusingFileWithLoaded: [dcmPix loadedFileRevision] current: [[[HorosFileRevision alloc] initWithPath: pathToFind] autorelease]] ?: @"the file changed on disk");
                    else if( [dcmPix isLoaded])
                    {
                        DCMPix *dcmPixCopy = [[vPixList objectAtIndex: i] copy];
                        
                        float *fImage = (float*) malloc( dcmPix.pheight*dcmPix.pwidth*sizeof( float));
                        if( fImage)
                        {
                            memcpy( fImage, dcmPix.fImage, dcmPix.pheight*dcmPix.pwidth*sizeof( float));
                            [dcmPixCopy setfImage: fImage];
                            [dcmPixCopy freefImageWhenDone: YES];
                            
                            returnPix = [dcmPixCopy autorelease];
                        }
                        else
                            [dcmPixCopy release];
                    }
                    [dcmPix.checking unlock];
                }
            }
            @catch (NSException * e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            [volumeData release];
            [vFileList release];
            [vPixList release];
        }
        
        [v release];
    }
    
    return returnPix;
}

#pragma mark Preview window policy (#608)

// Implemented in Swift since #831, with the same selectors: BrowserController+Preview.swift.

#pragma mark - NSSplitViewDelegate

// Implemented in Swift since #831, with the same selectors: BrowserController+SplitView.swift.

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark Albums functions

- (IBAction) addSmartAlbum: (id)sender
{
    SmartWindowController* swc = [[SmartWindowController alloc] initWithDatabase:self.database];
    
    [self.window beginSheet:swc.window completionHandler:^(NSModalResponse returnCode) {
        [self smartAlbumSheetDidEnd:swc.window returnCode:returnCode contextInfo:nil];
    }];
    
    /*[smartWindowController addSubview: nil];
     
     int result = [NSApp runModalForWindow:sheet];
     [sheet makeFirstResponder: nil];
     
     // Sheet is up here.
     [sheet.sheetParent endSheet:sheet];
     [sheet orderOut: self];
     [smartWindowController close];
     
     NSMutableArray *criteria = [smartWindowController criteria];
     if( [criteria count] > 0 && result == NSModalResponseStop)
     {
     NSError *error = nil;
     NSString *name;
     
     NSFetchRequest *dbRequest = [[[NSFetchRequest alloc] init] autorelease];
     [dbRequest setEntity: [[self.database.managedObjectModel entitiesByName] objectForKey:@"Album"]];
     [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
     NSManagedObjectContext *context = self.database.managedObjectContext;
     
     [context lock];
     
     @try
     {
     error = nil;
     NSArray *albumsArray = [context executeFetchRequest:dbRequest error:&error];
     
     int i = 2;
     name = [smartWindowController albumTitle];
     while( [[albumsArray valueForKey:@"name"] indexOfObject: name] != NSNotFound)
     {
     name = [NSString stringWithFormat:@"%@ #%d", [smartWindowController albumTitle], i++];
     }
     
     NSManagedObject	*album = [NSEntityDescription insertNewObjectForEntityForName:@"Album" inManagedObjectContext: context];
     [album setValue:name forKey:@"name"];
     [album setValue:[NSNumber numberWithBool:YES] forKey:@"smartAlbum"];
     
     [album setValue: [smartWindowController sqlQueryString] forKey:@"predicateString"];
     (void)[_database save:NULL];
     
     // Distant DICOM node filter
     if( [[[smartWindowController onDemandFilter] allKeys] count] > 0)
     {
     NSMutableArray *savedSmartAlbums = [[[[NSUserDefaults standardUserDefaults] objectForKey: @"smartAlbumStudiesDICOMNodes"] mutableCopy] autorelease];
     
     NSUInteger idx = [[savedSmartAlbums valueForKey: @"name"] indexOfObject: name];
     
     if( idx != NSNotFound)
     [savedSmartAlbums removeObjectAtIndex: idx];
     
     NSMutableDictionary *dict = [NSMutableDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithBool: NO], @"activated", name, @"name", nil];
     
     [dict addEntriesFromDictionary: [smartWindowController onDemandFilter]];
     
     [savedSmartAlbums addObject: dict];
     
     [[NSUserDefaults standardUserDefaults] setObject: savedSmartAlbums forKey: @"smartAlbumStudiesDICOMNodes"];
     }
     
     [self refreshAlbums];
     
     NSInteger index = [self.albumArray indexOfObject:album];
     if (index != NSNotFound)
     [albumTable selectRowIndexes: [NSIndexSet indexSetWithIndex:index] byExtendingSelection: NO];
     }
     @catch (NSException * e)
     {
     N2LogExceptionWithStackTrace(e);
     }
     
     [context unlock];
     
     [self outlineViewRefresh];
     
     if( [smartWindowController editSqlQuery])
     [self albumTableDoublePressed: self];
     }
     
     [smartWindowController release];*/
}

- (void)smartAlbumSheetDidEnd:(NSWindow*)sheet returnCode:(NSInteger)returnCode contextInfo:(void*)contextInfo {
    [sheet orderOut:self];
    
    // The edit context is retained at presentation, including when cancelled.
    DicomAlbum* existingAlbum = [(id)contextInfo autorelease];
    if (returnCode == NSModalResponseStop) {
        DicomAlbum* album = nil;
        if ([existingAlbum isKindOfClass:[DicomAlbum class]])
            album = existingAlbum;
        
        if (!album)
            album = [self.database newObjectForEntity:self.database.albumEntity];
        
        SmartWindowController* swc = sheet.windowController;
        
        album.name = swc.name;
        album.smartAlbum = [NSNumber numberWithBool:YES];
        album.predicateString = [swc.predicate predicateFormat];
        [self.database save];
        
        [albumTable reloadData];
        
        if( [self.albumArray indexOfObject:album] != NSNotFound)
            [albumTable selectRowIndexes:[NSIndexSet indexSetWithIndex:[self.albumArray indexOfObject:album]] byExtendingSelection:NO];
        
        @synchronized (self) {
            _cachedAlbumsContext = nil;
        }
        
        NSInteger index = [self.albumArray indexOfObject:album];
        if (index != NSNotFound)
            [albumTable selectRowIndexes:[NSIndexSet indexSetWithIndex:index] byExtendingSelection:NO];
        
        [self outlineViewRefresh];
        
        [self refreshAlbums];
    }
    
    [sheet.windowController release];
}

- (IBAction) addAlbum:(id)sender
{ // Add album
    
    [self.window beginSheet:newAlbum completionHandler:nil];
    
    int result = [NSApp runModalForWindow: newAlbum];
    [newAlbum makeFirstResponder: nil];
    
    [newAlbum.sheetParent endSheet:newAlbum];
    [newAlbum orderOut: self];
    
    if( result == NSModalResponseStop)
    {
        
        NSFetchRequest *dbRequest = [[[NSFetchRequest alloc] init] autorelease];
        [dbRequest setEntity: [[self.database.managedObjectModel entitiesByName] objectForKey:@"Album"]];
        [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
        
        NSManagedObjectContext *context = self.database.managedObjectContext;
        
        N2ManagedObjectContextPerformAndWait(context, ^{
        NSString *name;
        int i = 2;
        
        @try
        {
            NSError *error = nil;
            NSArray *albumsArray = [context executeFetchRequest:dbRequest error:&error];
            
            name = [newAlbumName stringValue];
            while( [[albumsArray valueForKey:@"name"] indexOfObject: name] != NSNotFound)
            {
                name = [NSString stringWithFormat:@"%@ #%d", [newAlbumName stringValue], i++];
            }
            
            NSManagedObject	*album = [NSEntityDescription insertNewObjectForEntityForName:@"Album" inManagedObjectContext: context];
            [album setValue:name forKey:@"name"];
            
            [_database save];
            
            [self refreshAlbums];
        }
        @catch (NSException * e)
        {
            NSLog( @"***** exception in %s: %@", __PRETTY_FUNCTION__, e);
            [e printStackTrace];
        }
        
        });
        
        [self outlineViewRefresh];
    }
}

- (IBAction) deleteAlbum: (id)sender
{
    if( albumTable.selectedRow > 0)
    {
        DicomAlbum* album = [self.albumArray objectAtIndex:albumTable.selectedRow];
        
        [self removeAlbumObject:album];
    }
}

-(void)removeAlbum:(id)sender // contextual menu action
{
    NSInteger row = [albumTable clickedRow];
    if (!row) return;
    
    DicomAlbum* album = [self.albumArray objectAtIndex:row];
    
    [self removeAlbumObject:album];
}

-(void)removeAlbumObject:(DicomAlbum*)album {
    if ((album.smartAlbum.boolValue == NO && album.studies.count == 0) ||
        HorosRunInformationalAlertPanel(NSLocalizedString(@"Delete Album", nil),
                                     NSLocalizedString(@"Are you sure you want to delete the album named %@?", nil),
                                     NSLocalizedString(@"OK",nil),
                                     NSLocalizedString(@"Cancel",nil),
                                     nil,
                                     album.name) == HorosAlertDefaultResponse)
    {
        N2ManagedObjectContextPerformAndWait(self.database.managedObjectContext, ^{
        @try
        {
            [self.database.managedObjectContext deleteObject:album];
            
            @synchronized (self) {
                _cachedAlbumsContext = nil;
            }
            @synchronized(_albumNoOfStudiesCache) {
                [_albumNoOfStudiesCache removeAllObjects];
                [_distantAlbumNoOfStudiesCache removeAllObjects];
                [albumTable reloadData];
            }
            
            (void)[self.database save:NULL];
            [self refreshAlbums];
            [self outlineViewRefresh];
        }
        @catch (NSException* e)
        {
            N2LogException(e);
        }
        });
    }
}

- (IBAction) albumTableDoublePressed: (id)sender
{
    if( albumTable.selectedRow > 0 && [_database isLocal])
    {
        DicomAlbum* album = [self.albumArray objectAtIndex:albumTable.selectedRow];
        
        if ([[album valueForKey:@"smartAlbum"] boolValue] == YES)
        {
            SmartWindowController* swc = [[SmartWindowController alloc] initWithDatabase:self.database];
            swc.name = album.name;
            swc.predicate = [NSPredicate predicateWithFormat:album.predicateString];
            swc.album = album;
            
            void *albumContext = [album retain];
            [self.window beginSheet:swc.window completionHandler:^(NSModalResponse returnCode) {
                [self smartAlbumSheetDidEnd:swc.window returnCode:returnCode contextInfo:albumContext];
            }];
            
        }
        else
        {
            [newAlbumName setStringValue: [album valueForKey:@"name"]];
            
            [self.window beginSheet:newAlbum completionHandler:nil];
            
            int result = [NSApp runModalForWindow: newAlbum];
            [newAlbum makeFirstResponder: nil];
            
            [newAlbum.sheetParent endSheet:newAlbum];
            [newAlbum orderOut: self];
            
            if( result == NSModalResponseStop)
            {
                
                if( [[newAlbumName stringValue] isEqualToString: [album valueForKey:@"name"]] == NO)
                {
                    NSFetchRequest *dbRequest = [[[NSFetchRequest alloc] init] autorelease];
                    [dbRequest setEntity: [[self.database.managedObjectModel entitiesByName] objectForKey:@"Album"]];
                    [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
                    NSManagedObjectContext *context = self.database.managedObjectContext;
                    
                    [context retain];
                    N2ManagedObjectContextPerformAndWait(context, ^{
                    int i = 2;
                    NSError *error = nil;
                    
                    @try
                    {
                        NSArray *albumsArray = [context executeFetchRequest:dbRequest error:&error];
                        
                        NSString *name = newAlbumName.stringValue;
                        while( [[albumsArray valueForKey:@"name"] indexOfObject: name] != NSNotFound)
                        {
                            name = [NSString stringWithFormat:@"%@ #%d", [newAlbumName stringValue], i++];
                        }
                        
                        [album setValue:name forKey:@"name"];
                        
                        
                        (void)[_database save:NULL];
                        
                        [albumTable selectRowIndexes: [NSIndexSet indexSetWithIndex: [self.albumArray indexOfObject:album]] byExtendingSelection: NO];
                        
                        [albumTable reloadData];
                    }
                    @catch (NSException * e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                    
                    });
                    [context release];
                }
            }
        }
    }
}

- (NSArray*) albumArray
{
    if( !_database) return [NSArray array];
    if( !_database.managedObjectContext) return [NSArray array];
    
    return [[NSArray arrayWithObject:[NSDictionary dictionaryWithObject: NSLocalizedString(@"Database", nil) forKey:@"name"]] arrayByAddingObjectsFromArray:[self albumsInDatabase]];
}

- (NSManagedObjectID*) currentAlbumID: (DicomDatabase*) d
{
    // The UI's database on the main thread; elsewhere a private-queue one (#966).
    if( d == nil)
        d = [NSThread isMainThread] ? _database : _database.privateQueueIndependentDatabase;
    
    NSString *albumName = self.selectedAlbumName;
    
    if( albumName == nil)
        return nil;
    
    __block NSManagedObjectID *albumID = nil;
    [d performBlockAndWait:^{
        albumID = [[(NSManagedObject *)[[d objectsForEntity: d.albumEntity predicate: [NSPredicate predicateWithFormat: @"name == %@", albumName]] lastObject] objectID] retain];
    }];
    return [albumID autorelease];
}

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
#pragma mark-
#pragma mark Albums TableView functions

// Implemented in Swift since #831, with the same selectors: BrowserController+AlbumsTableView.swift.

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
#pragma mark-
#pragma mark Open 2D/4D Viewer functions

static BOOL HorosAccumulateImageMemory(id image, unsigned long long frames, BOOL minimumImageSize,
                                       unsigned long long *pixels, unsigned long long *padded)
{
    long long width = [[image valueForKey:@"width"] longLongValue];
    long long height = [[image valueForKey:@"height"] longLongValue];
    if (width <= 0 || height <= 0 || frames == 0)
        return NO;
    if (minimumImageSize && width < 65536 && height < 65536 && width * height < 256 * 256)
        width = height = 256;
    unsigned long long plain, margin;
    if (__builtin_mul_overflow((unsigned long long)width, (unsigned long long)height, &plain) ||
        __builtin_mul_overflow(plain, frames, &plain) ||
        __builtin_mul_overflow((unsigned long long)width + 1, (unsigned long long)height + 1, &margin) ||
        __builtin_mul_overflow(margin, frames, &margin) ||
        __builtin_add_overflow(*pixels, plain, pixels) ||
        __builtin_add_overflow(*padded, margin, padded))
        return NO;
    return YES;
}

- (BOOL)computeEnoughMemory: (NSArray*)toOpenArray :(unsigned long*)requiredMem
{
    if (requiredMem) *requiredMem = 0;
    NSUInteger count = toOpenArray.count;
    if (count == 0) return YES;
    if (count > SIZE_MAX / sizeof(void*)) return NO;
    void **testPointers = calloc(count, sizeof(void*));
    if (!testPointers) return NO;
    BOOL enoughMemory = YES;
    unsigned long long paddedPixels = 0;
    NSThread *thread = NSThread.currentThread;
    @try {
        for (NSUInteger index = 0; index < count; ++index) {
            NSArray *images = [toOpenArray objectAtIndex:index];
            if (images.count == 0) continue;
            id first = images.firstObject;
            unsigned long long pixels = 0;
            BOOL valid = YES;
            long long frames = [[first valueForKey:@"numberOfFrames"] longLongValue];
            if (images.count == 1 && (frames > 1 || [[first valueForKey:@"numberOfSeries"] longLongValue] > 1)) {
                valid = frames > 0 && HorosAccumulateImageMemory(first, frames, NO, &pixels, &paddedPixels);
            } else {
                [thread enterOperation];
                @try {
                    thread.status = NSLocalizedString(@"Evaluating amount of memory needed...", nil);
                    NSTimeInterval start = NSDate.timeIntervalSinceReferenceDate;
                    for (NSUInteger i = 0; i < images.count; ++i) {
                        if (NSDate.timeIntervalSinceReferenceDate - start > 0.5 || i == images.count-1) {
                            thread.progress = (double)(i+1)/images.count;
                            start = NSDate.timeIntervalSinceReferenceDate;
                        }
                        if (!HorosAccumulateImageMemory([images objectAtIndex:i], 1, NO, &pixels, &paddedPixels)) {
                            valid = NO;
                            break;
                        }
                    }
                } @finally {
                    [thread exitOperation];
                }
            }
            unsigned long long bytes = 0, probe = 0;
            if (!valid || __builtin_mul_overflow(pixels, (unsigned long long)sizeof(float), &bytes) ||
                __builtin_add_overflow(bytes, 4ULL * 1024 * 1024, &bytes) ||
                __builtin_add_overflow(bytes, bytes/2, &probe) || probe > SIZE_MAX) {
                enoughMemory = NO;
                paddedPixels = ULLONG_MAX;
                break;
            }
#if !__LP64__
            if (bytes >= 3584ULL * 1024 * 1024) { enoughMemory = NO; break; }
#endif
            testPointers[index] = malloc((size_t)probe);
            if (!testPointers[index]) enoughMemory = NO;
        }
    } @finally {
        for (NSUInteger index = 0; index < count; ++index) free(testPointers[index]);
        free(testPointers);
    }
    unsigned long long requiredBytes;
    if (__builtin_mul_overflow(paddedPixels, (unsigned long long)sizeof(float), &requiredBytes))
        requiredBytes = ULLONG_MAX;
    if (requiredMem) *requiredMem = (unsigned long)MIN(requiredBytes / (1024ULL * 1024), (unsigned long long)ULONG_MAX);
    return enoughMemory;
}

- (ViewerController*) openViewerFromImages:(NSArray*) toOpenArray movie:(BOOL) movieViewer viewer:(ViewerController*) viewer keyImagesOnly:(BOOL) keyImages
{
    return [self openViewerFromImages:toOpenArray movie:movieViewer viewer:viewer keyImagesOnly:keyImages tryToFlipData: NO];
}

- (ViewerController*) openViewerFromImages:(NSArray*) toOpenArray movie:(BOOL) movieViewer viewer:(ViewerController*) viewer keyImagesOnly:(BOOL) keyImages tryToFlipData:(BOOL) tryToFlipData
{
    if (toOpenArray.count == 0) return nil;
    unsigned long *memBlockSize = calloc(toOpenArray.count, sizeof(unsigned long));
    if (!memBlockSize) {
        HorosRunInformationalAlertPanel(NSLocalizedString(@"Memory", nil), NSLocalizedString(@"Not enough memory to open the selected images.", nil), NSLocalizedString(@"OK", nil), nil, nil);
        return nil;
    }
    BOOL savedAUTOHIDEMATRIX = [[NSUserDefaults standardUserDefaults] boolForKey:@"AUTOHIDEMATRIX"];
    
    BOOL				multiFrame = NO, preFlippedData = NO;
    float				*fVolumePtr = nil;
    NSData				*volumeData = nil;
    NSMutableArray		*viewerPix[ MAX4D];
    ViewerController	*movieController = nil;
    ViewerController	*createdViewer = viewer;
    DicomStudy          *previousStudy = viewer.currentStudy;
    
    ThreadModalForWindowController* wait = nil;
    [[NSThread currentThread] enterOperation];
    if ([self.database hasPotentiallySlowDataAccess]) {
        NSThread.currentThread.name = NSLocalizedString(@"Loading series data...", nil);
        NSThread.currentThread.status = NSLocalizedString(@"Evaluating amount of memory needed...", nil);
        wait = [[ThreadModalForWindowController alloc] initWithThread:[NSThread currentThread] window:nil];
    }
    
    @try
    {
        //  (1) keyImages
        if( keyImages)
        {
            NSMutableArray *keyImagesToOpenArray = [NSMutableArray array];
            
            @try
            {
                for( NSArray *loadList in toOpenArray)
                {
                    NSMutableArray *keyImagesArray = [NSMutableArray array];
                    
                    for( NSManagedObject *image in loadList)
                    {
                        if( [image isKindOfClass: [DicomImage class]])
                            if( [[image valueForKey:@"isKeyImage"] boolValue] == YES)
                                [keyImagesArray addObject: image];
                    }
                    
                    if( [keyImagesArray count] > 0)
                        [keyImagesToOpenArray addObject: keyImagesArray];
                }
            }
            @catch (NSException *e)
            {
                N2LogException( e);
            }
            
            if( [keyImagesToOpenArray count] > 0) toOpenArray = keyImagesToOpenArray;
            else
            {
                if( HorosRunInformationalAlertPanel( NSLocalizedString( @"Key Images", nil), NSLocalizedString(@"No key images in these images.", nil), NSLocalizedString(@"All Images",nil), NSLocalizedString(@"Cancel",nil), nil) == HorosAlertAlternateResponse)
                    return nil;
            }
        }
        
        [[NSUserDefaults standardUserDefaults] setBool: NO forKey:@"AUTOHIDEMATRIX"];
        
        if( dontShowOpenSubSeries == NO)
        {
            if (([[[NSApplication sharedApplication] currentEvent] modifierFlags] & NSEventModifierFlagOption) || ([self computeEnoughMemory: toOpenArray : nil] == NO) || openSubSeriesFlag == YES)
            {
                toOpenArray = [self openSubSeries: toOpenArray];
                if (!toOpenArray) return nil;
            }
        }
        
        for( NSArray * r in toOpenArray)
        {
            if( r.count)
            {
                if( [r.lastObject isKindOfClass: [DicomImage class]] == NO)
                {
                    HorosRunInformationalAlertPanel( NSLocalizedString( @"Loading", nil), NSLocalizedString(@"Failed to load the series.", nil), NSLocalizedString(@"All Images",nil), NSLocalizedString(@"OK",nil), nil);
                    return nil;
                }
            }
        }
        
        //  (2) Compute Required Memory
        
        BOOL	enoughMemory = NO;
        long	subSampling = 1;
        unsigned long mem = 0;
        
        while( enoughMemory == NO)
        {
            mem = 0;
            BOOL memTestFailed = NO;
            unsigned char **testPtr = calloc( [toOpenArray count], sizeof( unsigned char*));
            if (!testPtr) {
                HorosRunInformationalAlertPanel(NSLocalizedString(@"Memory", nil), NSLocalizedString(@"Not enough memory to open the selected images.", nil), NSLocalizedString(@"OK", nil), nil, nil);
                return nil;
            }
            @try {
            
            for( unsigned long x = 0; x < [toOpenArray count]; x++)
            {
                unsigned long memBlock = 0;
                NSArray *loadList = [toOpenArray objectAtIndex: x];
                
                if( [loadList count])
                {
                    DicomImage*  curFile = [loadList objectAtIndex: 0];
                    [curFile setValue:[NSDate date] forKeyPath:@"series.dateOpened"];
                    [curFile setValue:[NSDate date] forKeyPath:@"series.study.dateOpened"];
                    
                    unsigned long long pixels = 0, padded = 0, bytes = 0, total = 0;
                    long long frames = [[curFile valueForKey:@"numberOfFrames"] longLongValue];
                    BOOL valid = YES;
                    if (loadList.count == 1 && (frames > 1 || [[curFile valueForKey:@"numberOfSeries"] longLongValue] > 1)) {
                        multiFrame = YES;
                        valid = frames > 0 && HorosAccumulateImageMemory(curFile, frames, NO, &pixels, &padded);
                    } else {
                        for (curFile in loadList) {
                            if (!HorosAccumulateImageMemory(curFile, 1, YES, &pixels, &padded)) { valid = NO; break; }
                        }
                    }
                    pixels = MAX(pixels, 256ULL * 256);
                    if (!valid || __builtin_mul_overflow(pixels, (unsigned long long)sizeof(float), &bytes) ||
                        __builtin_add_overflow(bytes, 4096ULL, &bytes) || bytes > SIZE_MAX || pixels > ULONG_MAX ||
                        __builtin_add_overflow((unsigned long long)mem, padded, &total) || total > ULONG_MAX / sizeof(float)) {
                        HorosRunInformationalAlertPanel(NSLocalizedString(@"Opening Error", nil), NSLocalizedString(@"The selected image dimensions cannot be loaded safely.", nil), NSLocalizedString(@"OK", nil), nil, nil);
                        return nil;
                    }
                    mem = (unsigned long)total;
                    memBlock = (unsigned long)pixels;

                    testPtr[ x] = malloc( (memBlock * sizeof(float)) + 4096);
                    if( testPtr[ x] == nil)
                    {
                        // Try to find the memory...
                        
                        [DCMView purgeStringTextureCache];
                        @try
                        {
                            @synchronized( previewPixThumbnails)
                            {
                                for( DCMPix *p in previewPix)
                                {
                                    [p kill8bitsImage];
                                    [p revert: NO];
                                }
                            }
                        }
                        @catch (NSException *e) {}
                        
                        testPtr[ x] = malloc( (memBlock * sizeof(float)) + 4096);
                        if( testPtr[ x] == nil)
                        {
                            memTestFailed = YES;
                            
                            NSLog(@"Failed to allocate memory for: %lu Mb", (memBlock * sizeof(float)) / (1024 * 1024));
                        }
                    }
                    memBlockSize[ x] = memBlock;
                }
                
            } //end for
            
            } @finally {
                for (NSUInteger x = 0; x < toOpenArray.count; ++x) free(testPtr[x]);
                free(testPtr);
            }
            
            // TEST MEMORY : IF NOT ENOUGH -> REDUCE SAMPLING
            
            if( memTestFailed)
            {
                NSLog(@"Test memory failed -> sub-sampling");
                
                NSMutableArray *newArray = [NSMutableArray array];
                
                BOOL canReduce = NO;
                for (NSArray *images in toOpenArray)
                    if (images.count > 1) { canReduce = YES; break; }
                // A single file (including multi-frame DICOM) cannot be reduced by dropping files.
                if (!canReduce || subSampling > LONG_MAX / 2) {
                    HorosRunInformationalAlertPanel(NSLocalizedString(@"Memory", nil), NSLocalizedString(@"Not enough memory to open the selected images.", nil), NSLocalizedString(@"OK", nil), nil, nil);
                    return nil;
                }
                subSampling *= 2;
                
                for( NSArray *loadList in toOpenArray)
                {
                    NSMutableArray *imagesArray = [NSMutableArray array];
                    
                    for( NSUInteger i = 0; i < [loadList count]; i++)
                    {
                        NSManagedObject	*image = [loadList objectAtIndex: i];
                        
                        if( i % 2 == 0)	[imagesArray addObject: image];
                    }
                    
                    if( [imagesArray count] > 0)
                        [newArray addObject: imagesArray];
                }
                
                toOpenArray = newArray;
            }
            else enoughMemory = YES;
        } //end while
        
        int result = HorosAlertDefaultResponse;
        
        if( subSampling != 1)
        {
            for( NSWindow *win in [NSApp windows])
            {
                if( [win isMiniaturized])
                {
                    [win deminiaturize:self];
                }
            }
            
            result = HorosRunInformationalAlertPanel( NSLocalizedString(@"Memory", nil), NSLocalizedString(@"There is not enough memory to load all selected images. Load a subset containing 1 in every %ld images?", nil), NSLocalizedString(@"OK",nil), NSLocalizedString(@"Cancel",nil), nil, subSampling);
        }
        
        //  (3) Load Images (memory allocation)
        
        BOOL notEnoughMemory = NO;
        
        if( result == HorosAlertDefaultResponse && toOpenArray != nil)
        {
            if( movieViewer == NO)
            {
                //				NSLog(@"I will try to allocate: %d Mb", (mem * sizeof(float)) / (1024 * 1024));
                //
                //				fVolumePtr = malloc(mem * sizeof(float));
                //				if( fVolumePtr == nil)
                //				{
                //					NSArray	*winList = [NSApp windows];
                //					for( i = 0; i < [winList count]; i++)
                //					{
                //						if([[winList objectAtIndex:i] isMiniaturized])
                //						{
                //							[[winList objectAtIndex:i] deminiaturize:self];
                //						}
                //					}
                //
                //					HorosRunCriticalAlertPanel( NSLocalizedString(@"Not enough memory",@"Not enough memory"),  NSLocalizedString(@"Your computer doesn't have enough RAM to load this series",@"Your computer doesn't have enough RAM to load this series"), NSLocalizedString(@"OK",nil), nil, nil);
                //					notEnoughMemory = YES;
                //				}
                //
                //				free( fVolumePtr);	// We will allocate each block independently !
                //				fVolumePtr = nil;
            }
            else
            {
                char **memBlockTestPtr = calloc( [toOpenArray count], sizeof( char*));
                if (!memBlockTestPtr) {
                    HorosRunInformationalAlertPanel(NSLocalizedString(@"Memory", nil), NSLocalizedString(@"Not enough memory to open the selected images.", nil), NSLocalizedString(@"OK", nil), nil, nil);
                    return nil;
                }
                
                NSLog(@"4D Viewer TOTAL: %lu Mb", (mem * sizeof(float)) / (1024 * 1024));
                for( unsigned long x = 0; x < [toOpenArray count]; x++)
                {
                    memBlockTestPtr[ x] = malloc(memBlockSize[ x] * sizeof(float));
                    NSLog(@"4D Viewer: I will try to allocate: %lu Mb", (memBlockSize[ x]* sizeof(float)) / (1024 * 1024));
                    
                    if( memBlockTestPtr[ x] == nil) notEnoughMemory = YES;
                }
                
                for( unsigned long x = 0; x < [toOpenArray count]; x++)
                {
                    if( memBlockTestPtr[ x] != nil) free( memBlockTestPtr[ x]);
                }
                
                if( notEnoughMemory)
                {
                    HorosRunCriticalAlertPanel(NSLocalizedString(@"Memory", nil), NSLocalizedString(@"Not enough memory to open the selected images.", nil), NSLocalizedString(@"OK", nil), nil, nil);
                }
                
                free( memBlockTestPtr);
                fVolumePtr = nil;
            }
        }
        else notEnoughMemory = YES;
        
        //  (4) Load Images loop
        
        if( notEnoughMemory == NO)
        {
            // Pre-Flip data ?
            
            NSMutableArray *resortedToOpenArray = [NSMutableArray array], *isFlippedData = [NSMutableArray array];
            
            for( NSArray *a in toOpenArray)
            {
                BOOL flipped = NO;
                
                if( multiFrame == NO && tryToFlipData == YES && [a count] > 2)
                {
                    @try
                    {
                        DicomImage *o = nil;
                        o = [a objectAtIndex: 1];
                        DCMPix *p1 = [[DCMPix alloc] initWithPath: [o valueForKey:@"completePath"] :0 :1 :nil :[[o valueForKey:@"frameID"] intValue] :[[o valueForKeyPath:@"series.id"] intValue] isBonjour:![_database isLocal] imageObj: o];
                        o = [a objectAtIndex: 2];
                        DCMPix *p2 = [[DCMPix alloc] initWithPath: [o valueForKey:@"completePath"] :0 :1 :nil :[[o valueForKey:@"frameID"] intValue] :[[o valueForKeyPath:@"series.id"] intValue] isBonjour:![_database isLocal] imageObj: o];
                        
                        if( p1 && p2 && [ViewerController computeIntervalForDCMPix: p1 And: p2] < 0)
                        {
                            //Inverse the array
                            a = [[a reverseObjectEnumerator] allObjects];
                            
                            preFlippedData = YES;
                            flipped = YES;
                        }
                        
                        [p1 release];
                        [p2 release];
                    }
                    @catch (NSException * e)
                    {
                        N2LogExceptionWithStackTrace(e/*, @"pre-flip data"*/);
                    }
                }
                
                [resortedToOpenArray addObject: a];
                [isFlippedData addObject: [NSNumber numberWithBool: flipped]];
            }
            
            if( preFlippedData)
                toOpenArray = resortedToOpenArray;
            
            //            NSMutableArray *viewerToStartLoadingThread = [NSMutableArray array];
            
            for( unsigned long x = 0; x < [toOpenArray count]; x++)
            {
                fVolumePtr = malloc( memBlockSize[ x] * sizeof(float));
                unsigned long mem = 0;
                
                if( fVolumePtr)
                {
                    volumeData = [[NSData alloc] initWithBytesNoCopy:fVolumePtr length:memBlockSize[ x]*sizeof( float) freeWhenDone:YES];
                    NSArray *loadList = [toOpenArray objectAtIndex: x];
                    
                    if( [loadList count])
                        [[WindowLayoutManager sharedWindowLayoutManager] setCurrentHangingProtocolForModality: [[loadList objectAtIndex: 0] valueForKeyPath:@"series.study.modality"] description:[[loadList objectAtIndex: 0] valueForKeyPath:@"series.study.studyName"]];
                    
                    // Why viewerPix[0] (fixed value) within the loop? Because it's not a 4D volume !
                    viewerPix[0] = [[NSMutableArray alloc] initWithCapacity:0];
                    NSMutableArray *correspondingObjects = [[NSMutableArray alloc] initWithCapacity:0];
                    NSString *missingFileReason = nil;
                    
                    if( [loadList count] == 1 && [[[loadList objectAtIndex: 0] valueForKey:@"numberOfFrames"] intValue] > 1)
                    {
                        multiFrame = YES;
                        NSManagedObject*  curFile = [loadList objectAtIndex: 0];
                        
                        for( unsigned long i = 0; i < [[curFile valueForKey:@"numberOfFrames"] intValue]; i++)
                        {
                            NSManagedObject*  curFile = [loadList objectAtIndex: 0];
                            DCMPix*	dcmPix = [[DCMPix alloc] initWithPath: [curFile valueForKey:@"completePath"] :i :[[curFile valueForKey:@"numberOfFrames"] intValue] :fVolumePtr+mem :i :[[curFile valueForKeyPath:@"series.id"] intValue] isBonjour:![_database isLocal] imageObj:curFile];
                            
                            if( dcmPix)
                            {
                                mem += ([[curFile valueForKey:@"width"] intValue]) * ([[curFile valueForKey:@"height"] intValue]);
                                
                                [viewerPix[0] addObject: dcmPix];
                                [correspondingObjects addObject: curFile];
                                [dcmPix release];
                            }
                        } //end for
                    }
                    else
                    {
                        //multiframe==NO
                        for( unsigned long i = 0; i < [loadList count]; i++)
                        {
                            NSManagedObject*  curFile = [loadList objectAtIndex: i];
                            DCMPix* dcmPix = [[DCMPix alloc] initWithPath: [curFile valueForKey:@"completePath"] :i :[loadList count] :fVolumePtr+mem :[[curFile valueForKey:@"frameID"] intValue] :[[curFile valueForKeyPath:@"series.id"] intValue] isBonjour:![_database isLocal] imageObj:curFile];
                            
                            if( dcmPix)
                            {
                                mem += ([[curFile valueForKey:@"width"] intValue]) * ([[curFile valueForKey:@"height"] intValue]);
                                
                                [viewerPix[0] addObject: dcmPix];
                                [correspondingObjects addObject: curFile];
                                [dcmPix release];
                            }
                            else
                            {
                                // Not just "not readable": a study imported as links
                                // to a disc says that when the disc is out, which
                                // reads as a damaged study rather than a
                                // disconnected one.
                                NSLog( @"---- %@", [HorosMissingFileReason reasonForPath: [curFile valueForKey: @"completePath"]
                                                    inDatabaseFolder: [[curFile valueForKey: @"inDatabaseFolder"] boolValue]]);
                                
                                if( missingFileReason == nil)
                                    missingFileReason = [HorosMissingFileReason reasonForPath: [curFile valueForKey: @"completePath"]
                                                         inDatabaseFolder: [[curFile valueForKey: @"inDatabaseFolder"] boolValue]];
                            }
                        }
                    }
                    
                    if( [viewerPix[0] count] != [loadList count] && multiFrame == NO)
                    {
                        for( unsigned int i = 0; i < [viewerPix[0] count]; i++)
                        {
                            [[viewerPix[0] objectAtIndex: i] setID: i];
                            [[viewerPix[0] objectAtIndex: i] setTot: [viewerPix[0] count]];
                        }
                        if( [viewerPix[0] count] == 0)
                            HorosRunCriticalAlertPanel( NSLocalizedString(@"Files not available (readable)", nil), NSLocalizedString(@"No files available (readable) in this series.\r\r%@", nil), NSLocalizedString(@"Continue",nil), nil, nil, missingFileReason ?: @"");
                        else
                            HorosRunCriticalAlertPanel( NSLocalizedString(@"Not all files available (readable)", nil), NSLocalizedString(@"Not all files are available (readable) in this series.\r%@ are missing.\r\r%@", nil), NSLocalizedString(@"Continue",nil), nil, nil, N2LocalizedSingularPluralCount( [loadList count] - [viewerPix[0] count], NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil)), missingFileReason ?: @"");
                    }
                    //opening images refered to in viewerPix[0] in the adequate viewer
                    
                    [DCMView setDontListenToSyncMessage: YES];
                    
                    BOOL copyCOPYSETTINGS = [[NSUserDefaults standardUserDefaults] boolForKey:@"COPYSETTINGS"];
                    [[NSUserDefaults standardUserDefaults] setBool: NO forKey:@"COPYSETTINGS"];
                    
                    if( [viewerPix[0] count] > 0)
                    {
                        if( movieViewer == NO)
                        {
                            if( multiFrame == YES)
                            {
                                NSMutableArray  *filesAr = [[NSMutableArray alloc] initWithCapacity: [viewerPix[0] count]];
                                
                                if( [correspondingObjects count])
                                {
                                    for( unsigned int i = 0; i < [viewerPix[0] count]; i++)
                                        [filesAr addObject: [correspondingObjects objectAtIndex:0]];
                                }
                                
                                if( viewer)
                                {
                                    //reuse of existing viewer
                                    [viewer changeImageData:viewerPix[0] :filesAr :volumeData :NO];
                                    [viewer startLoadImageThread];
                                }
                                else
                                {
                                    //creation of new viewer
                                    createdViewer = [[ViewerController alloc] initWithPix:viewerPix[0] withFiles:filesAr withVolume:volumeData];
                                    [createdViewer showWindowTransition];
                                    [createdViewer startLoadImageThread];
                                    //[viewerToStartLoadingThread addObject: createdViewer];
                                }
                                
                                [filesAr release];
                            }
                            else
                            {
                                //multiframe == NO
                                if( viewer)
                                {
                                    //reuse of existing viewer
                                    [viewer changeImageData:viewerPix[0] :[NSMutableArray arrayWithArray:correspondingObjects] :volumeData :NO ];
                                    [viewer startLoadImageThread];
                                    
                                    if( [[isFlippedData objectAtIndex: x] boolValue])
                                        [viewer flipDataSeries: self];
                                }
                                else
                                {
                                    //creation of new viewer
                                    createdViewer = [[ViewerController alloc] initWithPix:viewerPix[0] withFiles: [NSMutableArray arrayWithArray: correspondingObjects] withVolume:volumeData];
                                    [createdViewer showWindowTransition];
                                    [createdViewer startLoadImageThread];
                                    //[viewerToStartLoadingThread addObject: createdViewer];
                                    
                                    if( [[isFlippedData objectAtIndex: x] boolValue])
                                        [createdViewer flipDataSeries: self];
                                }
                            }
                        }
                        else
                        {
                            //movieViewer==YES
                            if( movieController == nil)
                            {
                                if( viewer)
                                {
                                    [viewer changeImageData:viewerPix[0] :[NSMutableArray arrayWithArray:correspondingObjects] :volumeData :NO];
                                    
                                    movieController = viewer;
                                }
                                else
                                {
                                    movieController = [[ViewerController alloc] initWithPix:viewerPix[0] withFiles:[NSMutableArray arrayWithArray:correspondingObjects] withVolume:volumeData];
                                }
                            }
                            else
                                [movieController addMovieSerie:viewerPix[0] :[NSMutableArray arrayWithArray:correspondingObjects] :volumeData];
                        }
                        [volumeData release];
                    }
                    
                    if( [[NSUserDefaults standardUserDefaults] boolForKey:@"COPYSETTINGS"])
                    {
                        // @"COPYSETTINGS" was activated in a sub function, keep it activated: for example, when fusion is activated during opening
                    }
                    else [[NSUserDefaults standardUserDefaults] setBool: copyCOPYSETTINGS forKey:@"COPYSETTINGS"];
                    
                    [DCMView setDontListenToSyncMessage: NO];
                    
                    [viewerPix[0] release];
                    [correspondingObjects release];
                }
            } //end for
            
            //            [self performSelector: @selector( startLoadingThreads:) withObject: viewerToStartLoadingThread afterDelay: 0.01];
        }
        
        //  (5) movieController activation
        
        if( movieController)
        {
            NSLog(@"openViewerFromImages-movieController activation");
            [movieController showWindowTransition];
            [movieController startLoadImageThread];
        }
        
    }
    @catch( NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
        HorosRunAlertPanel( NSLocalizedString(@"Opening Error", nil), NSLocalizedString(@"Opening Error : %@\r\r%@", nil), nil, nil, nil, e, [e printStackTrace]);
    }
    @finally {
        [[NSUserDefaults standardUserDefaults] setBool:savedAUTOHIDEMATRIX forKey:@"AUTOHIDEMATRIX"];
        free(memBlockSize);
        [wait invalidate];
        [wait autorelease];
        [[NSThread currentThread] exitOperation];
    }
    
    
    if( movieController) createdViewer = movieController;
    
    [self.database save]; //To save 'dateOpened' field, and allow independentContext to see it
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"AUTOTILING"])
    {
        if( viewer && [[NSUserDefaults standardUserDefaults] boolForKey: @"tileWindowsOrderByStudyDate"])
        {
            if( [previousStudy.studyInstanceUID isEqualToString: viewer.currentStudy.studyInstanceUID] == NO)
            {
                // Keep current row/column
                NSDictionary *d = nil;
                
                NSString *rw = [[NSUserDefaults standardUserDefaults] stringForKey: @"LastWindowsTilingRowsColumns"];
                if( rw)
                {
                    if( rw.length == 2)
                    {
                        d = [NSDictionary dictionaryWithObjectsAndKeys: [NSNumber numberWithInt: [[rw substringWithRange: NSMakeRange( 0, 1)] intValue]], @"rows", [NSNumber numberWithInt: [[rw substringWithRange: NSMakeRange( 1, 1)] intValue]], @"columns", nil];
                    }
                }
                
                [[AppController sharedAppController] tileWindows: d];
            }
        }
    }
    
    return createdViewer;
}

//- (void) startLoadingThreads: (NSArray*) viewerToStartLoadingThread
//{
//    for( ViewerController *v in viewerToStartLoadingThread)
//        [v startLoadImageThread];
//}

- (IBAction) selectSubSeriesAndOpen:(id) sender
{
    [NSApp stopModalWithCode: 2];
}

- (IBAction) selectAll3DSeries:(id) sender
{
    [NSApp stopModalWithCode: 6];
}

- (IBAction) reparseIn3D:(id) sender
{
    [NSApp stopModalWithCode: 10];
}

- (IBAction) reparseIn4D:(id) sender
{
    [NSApp stopModalWithCode: 11];
}

- (IBAction) selectAll4DSeries:(id) sender
{
    if( [subOpenMatrix4D isEnabled] == YES)
        [NSApp stopModalWithCode: 7];
}

- (void) processOpenViewerDICOMFromArray:(NSArray*) toOpenArray movie:(BOOL) movieViewer viewer: (ViewerController*) viewer
{
    long numberImages;
    BOOL movieError = NO, tryToFlipData = NO;
    
    if( [toOpenArray count] > 2)
        [self displayWaitWindowIfNecessary];
    
    numberImages = 0;
    if( movieViewer == YES) // First check if all series contain same amount of images
    {
        if( [toOpenArray count] == 1)	// Just one thumbnail is selected, check if multiples lines are selected
        {
            NSArray			*singleSeries = [toOpenArray objectAtIndex: 0];
            NSMutableArray	*splittedSeries = [NSMutableArray array];
            
            float interval, previousinterval = 0;
            
            [splittedSeries addObject: [NSMutableArray array]];
            
            if( [singleSeries count] > 1)
            {
                [[splittedSeries lastObject] addObject: [singleSeries objectAtIndex: 0]];
                
                interval = [[[singleSeries objectAtIndex: 0] valueForKey:@"sliceLocation"] floatValue] - [[[singleSeries objectAtIndex: 1] valueForKey:@"sliceLocation"] floatValue];
                
                if( interval == 0)	// 4D - 3D
                {
                    int pos3Dindex = 1;
                    for( int x = 1; x < [singleSeries count]; x++)
                    {
                        interval = [[[singleSeries objectAtIndex: x -1] valueForKey:@"sliceLocation"] floatValue] - [[[singleSeries objectAtIndex: x] valueForKey:@"sliceLocation"] floatValue];
                        
                        if( interval != 0)
                            pos3Dindex = 0;
                        
                        if( [splittedSeries count] <= pos3Dindex) [splittedSeries addObject: [NSMutableArray array]];
                        
                        [[splittedSeries objectAtIndex: pos3Dindex] addObject: [singleSeries objectAtIndex: x]];
                        
                        pos3Dindex++;
                    }
                }
                else	// 3D - 4D
                {
                    for( int x = 1; x < [singleSeries count]; x++)
                    {
                        interval = [[[singleSeries objectAtIndex: x -1] valueForKey:@"sliceLocation"] floatValue] - [[[singleSeries objectAtIndex: x] valueForKey:@"sliceLocation"] floatValue];
                        
                        if( (interval < 0 && previousinterval > 0) || (interval > 0 && previousinterval < 0))
                        {
                            [splittedSeries addObject: [NSMutableArray array]];
                            //NSLog(@"split at: %d", x);
                            
                            previousinterval = 0;
                        }
                        else if( previousinterval)
                        {
                            if( fabs(interval/previousinterval) > 2.0f || fabs(interval/previousinterval) < 0.5f)
                            {
                                [splittedSeries addObject: [NSMutableArray array]];
                                //NSLog(@"split at: %d", x);
                                previousinterval = 0;
                            }
                            else previousinterval = interval;
                        }
                        else previousinterval = interval;
                        
                        [[splittedSeries lastObject] addObject: [singleSeries objectAtIndex: x]];
                    }
                }
            }
            
            toOpenArray = splittedSeries;
        }
        
        if( [toOpenArray count] == 1)
        {
            HorosRunCriticalAlertPanel( NSLocalizedString(@"4D Player",@"4D Player"), NSLocalizedString(@"To see an animated series, you have to select multiple series of the same area at different times: e.g. a cardiac CT", nil), NSLocalizedString(@"OK",nil), nil, nil);
            movieError = YES;
        }
        else if( [toOpenArray count] > MAX4D)
        {
            HorosRunCriticalAlertPanel( NSLocalizedString(@"4D Player",@"4D Player"), NSLocalizedString(@"4D Player is limited to a maximum number of %d series.", nil), NSLocalizedString(@"OK",nil), nil, nil, MAX4D);
            movieError = YES;
        }
        else
        {
            numberImages = -1;
            
            for( unsigned long x = 0; x < [toOpenArray count]; x++)
            {
                if( numberImages == -1)
                {
                    numberImages = [[toOpenArray objectAtIndex: x] count];
                }
                else if( [[toOpenArray objectAtIndex: x] count] != numberImages)
                {
                    HorosRunCriticalAlertPanel( NSLocalizedString(@"4D Player",@"4D Player"),  NSLocalizedString(@"In the current version, all series must contain the same number of images.",@"In the current version, all series must contain the same number of images."), NSLocalizedString(@"OK",nil), nil, nil);
                    movieError = YES;
                    x = [toOpenArray count];
                }
            }
        }
    }
    else
    {
        tryToFlipData = YES;
        
        if( [toOpenArray count] == 1)	// Just one thumbnail is selected
        {
            if( ([[[NSApplication sharedApplication] currentEvent] modifierFlags]  & NSEventModifierFlagOption) || openReparsedSeriesFlag)
            {
                NSArray			*singleSeries = [[toOpenArray objectAtIndex: 0] sortedArrayUsingDescriptors: [NSArray arrayWithObjects: [NSSortDescriptor sortDescriptorWithKey: @"instanceNumber" ascending: YES], [NSSortDescriptor sortDescriptorWithKey: @"frameID" ascending: YES], nil]];
                NSMutableArray	*splittedSeries = [NSMutableArray array];
                NSMutableArray  *intervalArray = [NSMutableArray array];
                
                float interval, previousinterval = 0;
                
                [splittedSeries addObject: [NSMutableArray array]];
                
                if( [singleSeries count] > 1)
                {
                    [[splittedSeries lastObject] addObject: [singleSeries objectAtIndex: 0]];
                    
                    //					if( [[[singleSeries lastObject] valueForKey: @"numberOfFrames"] intValue] > 1)
                    //					{
                    //						for( id o in singleSeries)	//We need to extract the *true* sliceLocation
                    //						{
                    //							DCMPix *p = [[DCMPix alloc] initWithPath:[o valueForKey:@"completePath"] :0 :1 :nil :[[o valueForKey:@"frameID"] intValue] :[[o valueForKeyPath:@"series.id"] intValue] isBonjour:isCurrentDatabaseBonjour imageObj: o];
                    //
                    //							[intervalArray addObject: [NSNumber numberWithFloat: [p sliceLocation]]];
                    //
                    //							[p release];
                    //						}
                    //					}
                    //					else
                    //					{
                    for( id o in singleSeries)
                        [intervalArray addObject: [NSNumber numberWithFloat: [[o valueForKey:@"sliceLocation"] floatValue]]];
                    //					}
                    
                    interval = [[intervalArray objectAtIndex: 0] floatValue] - [[intervalArray objectAtIndex: 1] floatValue];
                    
                    if( interval == 0)
                    { // 4D - 3D
                        int pos3Dindex = 1;
                        
                        for( int x = 1; x < [singleSeries count]; x++)
                        {
                            float interval4D = [[intervalArray objectAtIndex: x -1] floatValue] - [[intervalArray objectAtIndex: x] floatValue];
                            if( interval4D != 0) pos3Dindex = 0;
                            
                            if( [splittedSeries count] <= pos3Dindex) [splittedSeries addObject: [NSMutableArray array]];
                            
                            [[splittedSeries objectAtIndex: pos3Dindex] addObject: [singleSeries objectAtIndex: x]];
                            
                            pos3Dindex++;
                        }
                        
                        if( pos3Dindex == [singleSeries count]) // No 3D-4D.... Try something else...
                        {
                            [intervalArray removeAllObjects];
                            
                            // Let's try the comment field Cardiac Magnitude, Phase, Flow
                            for( id o in singleSeries)
                            {
                                [intervalArray addObject: [NSNumber numberWithFloat: [[o valueForKey:@"comment"] floatValue]]];
                                
                                if( [[o valueForKey:@"comment"] floatValue] != 0)
                                    interval = 1; // To enter in the: if( interval != 0)
                            }
                            
                            if( interval)
                            {
                                splittedSeries = [NSMutableArray array];
                                [splittedSeries addObject: [NSMutableArray array]];
                                [[splittedSeries lastObject] addObject: [singleSeries objectAtIndex: 0]];
                            }
                        }
                    }
                    
                    if( interval != 0)
                    {	// 3D - 4D
                        BOOL	fixedRepetition = YES;
                        int		repetition = 0, previousPos = 0;
                        float	previousLocation;
                        
                        previousLocation = [[intervalArray objectAtIndex: 0] floatValue];
                        
                        for( int x = 1; x < [singleSeries count]; x++)
                        {
                            if( [[intervalArray objectAtIndex: x] floatValue] - previousLocation == 0)
                            {
                                if( repetition)
                                    if( repetition != x - previousPos)
                                        fixedRepetition = NO;
                                
                                repetition = x - previousPos;
                                previousPos = x;
                            }
                        }
                        
                        if( fixedRepetition && repetition != 0)
                        {
                            NSLog( @"repetition = %d", repetition);
                            
                            for( int x = 1; x < [singleSeries count]; x++)
                            {
                                if( x % repetition == 0)
                                {
                                    [splittedSeries addObject: [NSMutableArray array]];
                                    //NSLog(@"split at: %d", x);
                                }
                                
                                [[splittedSeries lastObject] addObject: [singleSeries objectAtIndex: x]];
                            }
                        }
                        else
                        {
                            for( int x = 1; x < [singleSeries count]; x++)
                            {
                                interval = [[intervalArray objectAtIndex: x -1] floatValue] - [[intervalArray objectAtIndex: x] floatValue];
                                
                                if( [[splittedSeries lastObject] count] > 2)
                                {
                                    if( (interval < 0 && previousinterval > 0) || (interval > 0 && previousinterval < 0))
                                    {
                                        [splittedSeries addObject: [NSMutableArray array]];
                                        //NSLog(@"split at: %d", x);
                                        previousinterval = 0;
                                    }
                                    else if( previousinterval)
                                    {
                                        if( fabs(interval/previousinterval) > 1.2f || fabs(interval/previousinterval) < 0.8f)
                                        {
                                            [splittedSeries addObject: [NSMutableArray array]];
                                            //NSLog(@"split at: %d", x);
                                            previousinterval = 0;
                                        }
                                        else previousinterval = interval;
                                    }
                                    else previousinterval = interval;
                                }
                                else previousinterval = interval;
                                
                                [[splittedSeries lastObject] addObject: [singleSeries objectAtIndex: x]];
                            }
                        }
                    }
                }
                
                if( [splittedSeries count] > 1)
                {
                    [self closeWaitWindowIfNecessary];
                    
                    [subOpenMatrix3D renewRows: 1 columns: [splittedSeries count]];
                    [subOpenMatrix3D sizeToCells];
                    [subOpenMatrix3D setTarget:self];
                    [subOpenMatrix3D setAction: @selector(selectSubSeriesAndOpen:)];
                    
                    [subOpenMatrix4D renewRows: 1 columns: [[splittedSeries objectAtIndex: 0] count]];
                    [subOpenMatrix4D sizeToCells];
                    [subOpenMatrix4D setTarget:self];
                    [subOpenMatrix4D setAction: @selector(selectSubSeriesAndOpen:)];
                    
                    [[supOpenButtons cellWithTag: 3] setEnabled: YES];
                    
                    BOOL areData4D = YES;
                    
                    NSArray *array0 = [splittedSeries objectAtIndex: 0];
                    
                    for( NSArray *array in splittedSeries)
                    {
                        if( [array0 count] != [array count])
                        {
                            [[supOpenButtons cellWithTag: 3] setEnabled: NO];
                            areData4D = NO;
                        }
                    }
                    
                    for( int i = 0 ; i < [splittedSeries count]; i++)
                    {
                        NSManagedObject	*oob = [[splittedSeries objectAtIndex:i] objectAtIndex: [[splittedSeries objectAtIndex:i] count] / 2];
                        
                        DCMPix *dcmPix  = [[DCMPix alloc] initWithPath:[oob valueForKey:@"completePath"] :0 :1 :nil :[[oob valueForKey:@"frameID"] intValue] :[[oob valueForKeyPath:@"series.id"] intValue] isBonjour:![_database isLocal] imageObj: oob];
                        
                        if( dcmPix)
                        {
                            NSImage	 *img = [dcmPix generateThumbnailImageWithWW:[[oob valueForKeyPath: @"series.windowWidth"] floatValue] WL: [dcmPix calibratedWindowLevelForStoredLevel:[[oob valueForKeyPath: @"series.windowLevel"] floatValue]]];
                            
                            NSButtonCell *cell = [subOpenMatrix3D cellAtRow:0 column: i];
                            [cell setTransparent:NO];
                            [cell setEnabled:YES];
                            [cell setFont:[NSFont systemFontOfSize:10]];
                            [cell setImagePosition: NSImageBelow];
                            [cell setTitle:[NSString stringWithFormat:NSLocalizedString(@"%d/%d Images", nil), i+1, (int)[[splittedSeries objectAtIndex:i] count]]];
                            [cell setImage: img];
                            [cell setAlternateImage:img];
                            [dcmPix release];
                        }
                    }
                    
                    if( areData4D)
                    {
                        for( int i = 0 ; i < [[splittedSeries objectAtIndex: 0] count]; i++)
                        {
                            NSManagedObject	*oob = [[splittedSeries objectAtIndex: 0] objectAtIndex: i];
                            
                            DCMPix *dcmPix  = [[DCMPix alloc] initWithPath:[oob valueForKey:@"completePath"] :0 :1 :nil :[[oob valueForKey:@"frameID"] intValue] :[[oob valueForKeyPath:@"series.id"] intValue] isBonjour:![_database isLocal] imageObj: oob];
                            
                            if( dcmPix)
                            {
                                NSImage	 *img = [dcmPix generateThumbnailImageWithWW:[[oob valueForKeyPath: @"series.windowWidth"] floatValue] WL:[dcmPix calibratedWindowLevelForStoredLevel:[[oob valueForKeyPath: @"series.windowLevel"] floatValue]]];
                                
                                NSButtonCell *cell = [subOpenMatrix4D cellAtRow:0 column: i];
                                [cell setTransparent:NO];
                                [cell setEnabled:YES];
                                [cell setFont:[NSFont systemFontOfSize:10]];
                                [cell setImagePosition: NSImageBelow];
                                [cell setTitle:[NSString stringWithFormat:NSLocalizedString(@"%d/%d Images", nil), i+1, (int)[splittedSeries count]]];
                                [cell setImage: img];
                                [cell setAlternateImage:img];
                                [dcmPix release];
                            }
                        }
                    }
                    else
                    {
                        [subOpenMatrix4D renewRows: 0 columns: 0];
                        [subOpenMatrix4D sizeToCells];
                        [subOpenMatrix4D setEnabled: NO];
                    }
                    
                    [[NSApp mainWindow] beginSheet:subOpenWindow completionHandler:nil];
                    
                    int result = [NSApp runModalForWindow: subOpenWindow];
                    [subOpenWindow makeFirstResponder: nil];
                    
                    if( result == 2)
                    {
                        [supOpenButtons selectCellWithTag: 2];
                        
                        if( [subOpenMatrix3D selectedColumn] < 0)
                        {
                            if( [subOpenMatrix4D selectedColumn] < 0) result = 0;
                            else result = 5;
                        }
                    }
                    else if( result == 6)
                    {
                        NSLog( @"Open all 3D");
                    }
                    else if( result == 7)
                    {
                        NSLog( @"Open all 4D");
                    }
                    else if( result == 10)
                    {
                        NSLog( @"Reparse in 3D");
                        
                        // Create the new series
                        
                        N2ManagedObjectContextPerformAndWait(_database.managedObjectContext, ^{
                        
                        @try
                        {
                            int reparseIndex = 1;
                            
                            DicomSeries *originalSeries = [[[splittedSeries lastObject] lastObject] valueForKey: @"Series"];
                            
                            for( NSArray *array in splittedSeries)
                            {
                                DicomSeries *newSeries = [NSEntityDescription insertNewObjectForEntityForName: @"Series" inManagedObjectContext:_database.managedObjectContext];
                                
                                for ( NSString *name in [[[NSEntityDescription entityForName: @"Series" inManagedObjectContext:_database.managedObjectContext] attributesByName] allKeys]) // Duplicate values
                                {
                                    id value = nil;
                                    
                                    if( [name isEqualToString: @"seriesInstanceUID"])
                                        value = [[originalSeries valueForKey: name] stringByAppendingFormat: @"RP-%d", reparseIndex++];
                                    else
                                        value = [originalSeries valueForKey: name];
                                    
                                    if( value)
                                        [newSeries setValue: value forKey: name];
                                }
                                
                                [newSeries setValue: [originalSeries valueForKey: @"study"] forKey: @"study"];
                                
                                // Add the images
                                for( DicomImage *image in array)
                                {
                                    DicomImage *newImage = [NSEntityDescription insertNewObjectForEntityForName: @"Image" inManagedObjectContext:_database.managedObjectContext];
                                    
                                    for ( NSString *name in [[[NSEntityDescription entityForName: @"Image" inManagedObjectContext:_database.managedObjectContext] attributesByName] allKeys]) // Duplicate values
                                    {
                                        [newImage setValue: [image valueForKey: name] forKey: name];
                                    }
                                    
                                    [image setValue: newSeries forKey: @"series"];
                                }
                                
                                [newSeries setValue: [NSNumber numberWithInt: 0] forKey: @"numberOfImages"];
                                [newSeries setValue: nil forKey:@"thumbnail"];
                            }
                            
                            [_database.managedObjectContext deleteObject:originalSeries];
                            
                            (void)[_database save: nil];
                        }
                        @catch (NSException * e)
                        {
                            N2LogExceptionWithStackTrace(e/*, @"reparsing"*/);
                        }
                        });
                        
                        [self refreshDatabase: self];
                        [self refreshMatrix: self];
                        
                        result = 0;
                    }
                    else if( result == 11)
                    {
                        NSLog( @"Reparse in 4D");
                        
                        // Create the new series
                        
                        N2ManagedObjectContextPerformAndWait(_database.managedObjectContext, ^{
                        
                        @try
                        {
                            int reparseIndex = 1;
                            
                            DicomSeries *originalSeries = [[[splittedSeries lastObject] lastObject] valueForKey: @"Series"];
                            
                            for( int i = 0; i < [[splittedSeries objectAtIndex: 0] count]; i++)
                            {
                                NSMutableArray	*array4D = [NSMutableArray array];
                                
                                for ( NSArray *array in splittedSeries)
                                    [array4D addObject: [array objectAtIndex: i]];
                                
                                DicomSeries *newSeries = [NSEntityDescription insertNewObjectForEntityForName: @"Series" inManagedObjectContext:_database.managedObjectContext];
                                
                                for ( NSString *name in [[[NSEntityDescription entityForName: @"Series" inManagedObjectContext:_database.managedObjectContext] attributesByName] allKeys]) // Duplicate values
                                {
                                    id value = nil;
                                    
                                    if( [name isEqualToString: @"seriesInstanceUID"])
                                        value = [[originalSeries valueForKey: name] stringByAppendingFormat: @"RP-%d", reparseIndex++];
                                    else
                                        value = [originalSeries valueForKey: name];
                                    
                                    if( value)
                                        [newSeries setValue: value forKey: name];
                                }
                                
                                [newSeries setValue: [originalSeries valueForKey: @"study"] forKey: @"study"];
                                
                                // Add the images
                                for( DicomImage *image in array4D)
                                {
                                    DicomImage *newImage = [NSEntityDescription insertNewObjectForEntityForName: @"Image" inManagedObjectContext:_database.managedObjectContext];
                                    
                                    for ( NSString *name in [[[NSEntityDescription entityForName: @"Image" inManagedObjectContext:_database.managedObjectContext] attributesByName] allKeys]) // Duplicate values
                                    {
                                        [newImage setValue: [image valueForKey: name] forKey: name];
                                    }
                                    
                                    [image setValue: newSeries forKey: @"series"];
                                }
                                
                                [newSeries setValue: [NSNumber numberWithInt: 0] forKey: @"numberOfImages"];
                                [newSeries setValue: nil forKey:@"thumbnail"];
                            }
                            
                            [_database.managedObjectContext deleteObject: originalSeries];
                            
                            (void)[_database save:nil];
                        }
                        @catch (NSException * e)
                        {
                            N2LogExceptionWithStackTrace(e/*, @"reparsing"*/);
                        }
                        });
                        
                        [self refreshDatabase: self];
                        [self refreshMatrix: self];
                        
                        result = 0;
                    }
                    else
                    {
                        //Workaround for UI calls from background UI (runtime warnings) - Binding could be the definitive resolution for this
                        __block NSInteger supOpenButtonsSelectedTag = 0;
                        if ([NSThread isMainThread])
                        {
                            supOpenButtonsSelectedTag = [supOpenButtons selectedTag];
                        }
                        else
                        {
                            dispatch_sync(dispatch_get_main_queue(), ^(void) {
                                supOpenButtonsSelectedTag = [supOpenButtons selectedTag];
                            });
                        }
                        
                        result = supOpenButtonsSelectedTag;
                    }
                    
                    [subOpenWindow.sheetParent endSheet:subOpenWindow];
                    [subOpenWindow orderOut: self];
                    
                    switch( result)
                    {
                        case 0:	// Cancel
                            movieError = YES;
                            break;
                            
                        case 1: // Entire
                            
                            break;
                            
                        case 2: // selected 3D
                            toOpenArray = [NSMutableArray arrayWithObject: [splittedSeries objectAtIndex: [subOpenMatrix3D selectedColumn]]];
                            break;
                            
                        case 3:	// 4D Viewer
                            toOpenArray = splittedSeries;
                            movieViewer = YES;
                            break;
                            
                        case 5: // selected 4D
                        {
                            NSMutableArray	*array4D = [NSMutableArray array];
                            
                            for( NSArray *array in splittedSeries)
                            {
                                [array4D addObject: [array objectAtIndex: [subOpenMatrix4D selectedColumn]]];
                            }
                            
                            toOpenArray = [NSMutableArray arrayWithObject: array4D];
                        }
                            break;
                            
                        case 6:
                            
                            [self displayWaitWindowIfNecessary];
                            
                            for( NSArray *array in splittedSeries)
                            {
                                toOpenArray = [NSMutableArray arrayWithObject: array];
                                [self openViewerFromImages :toOpenArray movie: movieViewer viewer :viewer keyImagesOnly:NO];
                            }
                            toOpenArray = 0;
                            break;
                            
                        case 7:
                        {
                            BOOL openAllWindows = YES;
                            
                            if( [[splittedSeries objectAtIndex: 0] count] > 25)
                            {
                                openAllWindows = NO;
                                
                                if( HorosRunInformationalAlertPanel( NSLocalizedString(@"Series Opening", nil), NSLocalizedString(@"Are you sure you want to open %d windows? It's a lot of windows for this screen...", nil), NSLocalizedString(@"Yes", nil), NSLocalizedString(@"Cancel", nil), nil, (int)[[splittedSeries objectAtIndex: 0] count]) == HorosAlertDefaultResponse)
                                    openAllWindows = YES;
                            }
                            
                            if( openAllWindows)
                            {
                                [self displayWaitWindowIfNecessary];
                                
                                for( int i = 0; i < [[splittedSeries objectAtIndex: 0] count]; i++)
                                {
                                    NSMutableArray	*array4D = [NSMutableArray array];
                                    
                                    for ( NSArray *array in splittedSeries)
                                    {
                                        [array4D addObject: [array objectAtIndex: i]];
                                    }
                                    
                                    toOpenArray = [NSMutableArray arrayWithObject: array4D];
                                    
                                    [self openViewerFromImages :toOpenArray movie: movieViewer viewer :viewer keyImagesOnly:NO];
                                }
                            }
                            toOpenArray = nil;
                        }
                            break;
                    }
                }
            }
        }
    }
    
    if( movieError == NO && toOpenArray != nil)
        [self openViewerFromImages :toOpenArray movie: movieViewer viewer :viewer keyImagesOnly:NO tryToFlipData: tryToFlipData];
}

- (void) viewerDICOMInt:(BOOL) movieViewer dcmFile:(NSArray *)selectedLines viewer:(ViewerController*) viewer
{
    return [self viewerDICOMInt:  movieViewer dcmFile: selectedLines viewer: viewer tileWindows: YES protocol: nil];
}

- (void) viewerDICOMInt:(BOOL) movieViewer dcmFile:(NSArray *)selectedLines viewer:(ViewerController*) viewer tileWindows: (BOOL) tileWindows
{
    return [self viewerDICOMInt:  movieViewer dcmFile: selectedLines viewer: viewer tileWindows: tileWindows protocol: nil];
}

- (void) viewerDICOMInt:(BOOL) movieViewer dcmFile:(NSArray *)selectedLines viewer:(ViewerController*) viewer tileWindows: (BOOL) tileWindows protocol: (NSDictionary*) protocol
{
    if( [selectedLines count] == 0) return;
    
    N2ManagedObjectContextPerformAndWait(_database.managedObjectContext, ^{
    
    @try
    {
        NSManagedObject		*selectedLine = [selectedLines objectAtIndex: 0];
        NSInteger			row, column;
        NSMutableArray		*selectedFilesList;
        NSArray				*loadList;
        
        NSArray				*cells = [oMatrix selectedCells];
        
        if( [cells count] == 0 && [[oMatrix cells] count] > 0)
        {
            cells = [NSArray arrayWithObject: [[oMatrix cells] objectAtIndex: 0]];
        }
        
        if( [[selectedLine valueForKey:@"type"] isEqualToString: @"Series"])
            [[AppController sharedAppController] addStudyToRecentStudiesMenu: [(NSManagedObject *)[selectedLine valueForKey: @"study"] objectID]];
        else
            [[AppController sharedAppController] addStudyToRecentStudiesMenu: selectedLine.objectID];
        
        //////////////////////////////////////
        // Open selected images only !!!
        //////////////////////////////////////
        
        if( [cells count] > 1 && [[selectedLine valueForKey:@"type"] isEqualToString: @"Series"])
        {
            NSArray  *curList = [self childrenArray: selectedLine];
            
            selectedFilesList = [[NSMutableArray alloc] initWithCapacity:0];
            
            for( NSCell* c in cells)
            {
                if( [c tag] < curList.count)
                {
                    NSManagedObject*  curImage = [curList objectAtIndex: [c tag]];
                    [selectedFilesList addObject: curImage];
                }
            }
            
            [self openViewerFromImages :[NSArray arrayWithObject: selectedFilesList] movie: movieViewer viewer :viewer keyImagesOnly:NO];
            
            [selectedFilesList release];
        }
        else
        {
            //////////////////////////////////////
            // Open series !!!
            //////////////////////////////////////
            
            //////////////////////////////////////
            // Prepare an array that contains arrays of series
            //////////////////////////////////////
            
            NSMutableArray	*toOpenArray = [NSMutableArray array];
            
            int x = 0;
            if( [cells count] == 1 && [selectedLines count] > 1)	// Just one thumbnail is selected, but multiples lines are selected
            {
                for( NSManagedObject* curFile in selectedLines)
                {
                    x++;
                    loadList = nil;
                    
                    if( [[curFile valueForKey:@"type"] isEqualToString: @"Study"])
                    {
                        // Find the first series of images! DONT TAKE A ROI SERIES !
                        if( [[curFile valueForKey:@"imageSeries"] count])
                        {
                            curFile = [[curFile valueForKey:@"imageSeries"] objectAtIndex: 0];
                            loadList = [self childrenArray: curFile];
                        }
                    }
                    
                    if( [[curFile valueForKey:@"type"] isEqualToString: @"Series"])
                    {
                        loadList = [self childrenArray: curFile];
                    }
                    
                    if( loadList) [toOpenArray addObject: loadList];
                }
            }
            else
            {
                for( NSButtonCell *cell in cells)
                {
                    x++;
                    if( [oMatrix getRow: &row column: &column ofCell: cell] == NO)
                    {
                        row = 0;
                        column = 0;
                    }
                    
                    loadList = nil;
                    
                    if( matrixViewArray.count > [cell tag])
                    {
                        NSManagedObject*  curFile = [matrixViewArray objectAtIndex: [cell tag]];
                        
                        if( [[curFile valueForKey:@"type"] isEqualToString: @"Image"])
                            loadList = [self childrenArray: selectedLine onlyImages: YES];
                        
                        if( [[curFile valueForKey:@"type"] isEqualToString: @"Series"])
                            loadList = [self childrenArray: curFile onlyImages: YES];
                        
                        if( loadList) [toOpenArray addObject: loadList];
                    }
                }
            }
            
            [self processOpenViewerDICOMFromArray: toOpenArray movie: movieViewer viewer: viewer];
        }
        
        if( tileWindows)
        {
            NSArray *viewers = [ViewerController getDisplayed2DViewers];
            
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"AUTOTILING"])
            {
                [[AppController sharedAppController] tileWindows: protocol];
                
                if( [viewers count] > 1)
                {
                    ViewerController *kV = nil;
                    
                    for( ViewerController *v in viewers)
                    {
                        [[v imageView] scaleToFit];
                        [[v imageView] setOriginX:0 Y:0];
                        
                        if( [[v window] isKeyWindow]) kV = v;
                    }
                    
                    [kV propagateSettings];
                }
            }
            else
                [[AppController sharedAppController] checkAllWindowsAreVisible: self makeKey: YES];
        }
    }
    @catch (NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
        HorosRunAlertPanel( NSLocalizedString(@"Opening Error", nil), NSLocalizedString(@"Opening Error : %@\r\r%@", nil) , nil, nil, nil, e, [e printStackTrace]);
    }
    
    });
}

- (void) viewerSubSeriesDICOM: (id)sender
{
    openSubSeriesFlag = YES;
    [self viewerDICOM: sender];
    openSubSeriesFlag = NO;
}

- (void) viewerReparsedSeries: (id) sender
{
    openReparsedSeriesFlag = YES;
    [self viewerDICOM: sender];
    openReparsedSeriesFlag = NO;
}

- (void) viewerDICOM: (id)sender
{
    if ([[[NSApplication sharedApplication] currentEvent] modifierFlags]  & NSEventModifierFlagShift)
        [self viewerDICOMMergeSelection: sender];
    else
    {
        if( [[self window] firstResponder] == databaseOutline)
            [self newViewerDICOM: nil];
        else
            [self newViewerDICOM: sender];
    }
}


//????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

- (void)newViewerDICOM: (id)sender
{
    __block NSManagedObject *item = nil;
    N2ManagedObjectContextPerformAndWait(_database.managedObjectContext, ^{
    item = [[databaseOutline itemAtRow: [databaseOutline selectedRow]] retain];
    
    @try
    {
        if (sender == Nil &&
            [[oMatrix selectedCells] count] == 1 &&
            [[item valueForKey:@"type"] isEqualToString:@"Study"])
        {
            NSArray *array = [self databaseSelection];
            
            BOOL savedValue = [[NSUserDefaults standardUserDefaults] boolForKey:@"automaticWorkspaceLoad"];
            
            if( [array count] > 1 && savedValue == YES) [[NSUserDefaults standardUserDefaults] setBool: NO forKey:@"automaticWorkspaceLoad"];
            
            for( id obj in array)
            {
                [HorosOutlineSelectionRestore selectItem: obj inOutline: databaseOutline extending: NO];
                [self databaseOpenStudy: obj];
            }
            
            if( [array count] > 1 && savedValue == YES) [[NSUserDefaults standardUserDefaults] setBool: YES forKey:@"automaticWorkspaceLoad"];
        }
        else
        {
            if( [matrixViewArray count] > [[oMatrix selectedCell] tag] && [self isUsingExternalViewer: [matrixViewArray objectAtIndex: [[oMatrix selectedCell] tag]]] == NO)
            {
                //To avoid loading the dcmpix in previewSliderAction
                dontUpdatePreviewPane = YES;
                [self viewerDICOMInt: NO dcmFile: [self databaseSelection] viewer: nil];
                dontUpdatePreviewPane = NO;
                
                [self previewSliderAction: nil];
            }
        }
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    });
    
    [[NSNotificationCenter defaultCenter] postNotificationName:OsirixDidLoadNewObjectNotification object:item userInfo:nil];
    
    [item autorelease];
    [self closeWaitWindowIfNecessary];
}


//????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

- (void)viewerDICOMMergeSelection: (id)sender
{
    NSMutableArray	*images = [NSMutableArray array];
    
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix) (void)[self filesForDatabaseMatrixSelection: images];
    else [self filesForDatabaseOutlineSelection: images];
    
    [self openViewerFromImages :[NSArray arrayWithObject:images] movie: 0 viewer :nil keyImagesOnly:NO];
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"AUTOTILING"])
        [NSApp sendAction: @selector(tileWindows:) to:nil from: self];
    else
        [[AppController sharedAppController] checkAllWindowsAreVisible: self makeKey: YES];;
}

- (void) viewerDICOMROIsImages:(id) sender
{
    NSArray *roisImagesArray = [self ROIImages: sender];
    
    if( [roisImagesArray count])
    {
        dontShowOpenSubSeries = YES;
        [self openViewerFromImages :[NSArray arrayWithObject: roisImagesArray] movie: 0 viewer :nil keyImagesOnly:NO];
        dontShowOpenSubSeries = NO;
        
        if(	[[NSUserDefaults standardUserDefaults] boolForKey: @"AUTOTILING"])
            [NSApp sendAction: @selector(tileWindows:) to:nil from: self];
        else
            [[AppController sharedAppController] checkAllWindowsAreVisible: self makeKey: YES];
    }
    else
    {
        HorosRunInformationalAlertPanel(NSLocalizedString(@"ROIs Images", nil), NSLocalizedString(@"No images containing ROIs are found in this selection.", nil), NSLocalizedString(@"OK",nil), nil, nil);
    }
    
#ifndef OSIRIX_LIGHT
    BOOL escKey = CGEventSourceKeyState( kCGEventSourceStateCombinedSessionState, 53);
    
    if( escKey) //Open the images, and export them
    {
        if( [[ViewerController getDisplayed2DViewers] count])
        {
            ViewerController *v = [[ViewerController getDisplayed2DViewers] objectAtIndex: 0];
            
            [v exportAllImages: @"ROIs images"];
            
            [[v window] close];
        }
    }
#endif
}

- (void) viewerDICOMKeyImages:(id) sender
{
    NSMutableArray	*selectedItems = [NSMutableArray array];
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
        (void)[self filesForDatabaseMatrixSelection: selectedItems];
    else
        [self filesForDatabaseOutlineSelection: selectedItems];
    
    dontShowOpenSubSeries = YES;
    [self openViewerFromImages :[NSArray arrayWithObject:selectedItems] movie: 0 viewer :nil keyImagesOnly:YES];
    dontShowOpenSubSeries = NO;
    
    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"AUTOTILING"])
        [NSApp sendAction: @selector(tileWindows:) to:nil from: self];
    else
        [[AppController sharedAppController] checkAllWindowsAreVisible: self makeKey: YES];
    
#ifndef OSIRIX_LIGHT
    BOOL escKey = CGEventSourceKeyState( kCGEventSourceStateCombinedSessionState, 53);
    
    if( escKey) //Open the images, and export them
    {
        if( [[ViewerController getDisplayed2DViewers] count])
        {
            ViewerController *v = [[ViewerController getDisplayed2DViewers] objectAtIndex: 0];
            
            [v exportAllImages: @"Key images"];
            
            [[v window] close];
        }
    }
#endif
}

- (void) MovieViewerDICOM:(id) sender
{
    NSInteger				index;
    NSMutableArray			*selectedItems = [NSMutableArray array];
    
    NSIndexSet				*selectedRowIndexes = [databaseOutline selectedRowIndexes];
    for (index = [selectedRowIndexes firstIndex]; 1+[selectedRowIndexes lastIndex] != index; ++index)
    {
        if ([selectedRowIndexes containsIndex:index]) [selectedItems addObject: [databaseOutline itemAtRow:index]];
    }
    
    [self viewerDICOMInt:YES dcmFile: selectedItems viewer:nil];
}

static NSArray*	openSubSeriesArray = nil;

- (NSArray*)produceNewArray: (NSArray*)toOpenArray
{
    NSMutableArray *newArray = [NSMutableArray array];
    // The panel uses inclusive, one-based bounds. Clamp before unsigned conversion.
    NSUInteger from = subFrom > 0 ? (NSUInteger)subFrom - 1 : 0;
    NSUInteger to = subTo > 0 ? (NSUInteger)subTo : 0;
    NSUInteger interval = subInterval > 0 ? (NSUInteger)subInterval : 1;
    if (from >= to) return newArray;

    for (NSArray *loadList in toOpenArray)
    {
        NSUInteger end = MIN(to, loadList.count);
        NSMutableArray *imagesArray = [NSMutableArray array];
        for (NSUInteger i = MIN(from, end); i < end; ++i)
        {
            // Keep the existing sampling phase relative to the original series.
            if (i % interval == 0) [imagesArray addObject:[loadList objectAtIndex:i]];
        }
        if (imagesArray.count > 0)
        {
            [imagesArray sortUsingDescriptors:[[[imagesArray lastObject] series] sortDescriptorsForImages]];
            [newArray addObject:imagesArray];
        }
    }
    return newArray;
}

- (IBAction) checkMemory:(id) sender
{
    unsigned long mem;
    
    NSArray *selection = [self produceNewArray:openSubSeriesArray];
    if (selection.count == 0) {
        [subSeriesOKButton setEnabled:NO];
        [memoryMessage setStringValue:NSLocalizedString(@"Select at least one image.", nil)];
        return;
    }
    if( [self computeEnoughMemory: selection :&mem])
    {
        [leftIcon setImage: [NSImage imageNamed: @"smile"]];
        [rightIcon setImage: [NSImage imageNamed: @"smile"]];
        
        [subSeriesOKButton setEnabled: YES];
        
        [memoryMessage setStringValue: NSLocalizedString( @"OK !", nil)];
    }
    else
    {
        [leftIcon setImage: [NSImage imageNamed: @"error"]];
        [rightIcon setImage: [NSImage imageNamed: @"error"]];
        
        [subSeriesOKButton setEnabled: NO];
        
        [memoryMessage setStringValue: NSLocalizedString(@"Not enough memory. Select fewer images and try again.", nil)];
    }
}

- (void) setSubInterval: (id)sender
{
    subInterval = [sender intValue];
    
    [self checkMemory: self];
}

- (void) setSubFrom: (id)sender
{
    subFrom = [sender intValue];
    
    if( _database == nil) return;
    //	if( bonjourDownloading) return;
    
    [animationSlider setIntValue: subFrom-1];
    
    BOOL copyDontUpdatePreviewPane = dontUpdatePreviewPane;
    
    dontUpdatePreviewPane = NO;
    [self previewSliderAction: nil];
    dontUpdatePreviewPane = copyDontUpdatePreviewPane;
    
    [self checkMemory: self];
}

- (void)setSubTo: (id)sender
{
    subTo = [sender intValue];
    
    if( _database == nil) return;
    //	if( bonjourDownloading) return;
    
    [animationSlider setIntValue: subTo-1];
    
    
    BOOL copyDontUpdatePreviewPane = dontUpdatePreviewPane;
    
    dontUpdatePreviewPane = NO;
    [self previewSliderAction: nil];
    dontUpdatePreviewPane = copyDontUpdatePreviewPane;
    
    [self checkMemory: self];
}

- (NSArray*)openSubSeries: (NSArray*)toOpenArray
{
    [[waitOpeningWindow window] orderOut: self];
    
    int copySortSeriesBySliceLocation = [[NSUserDefaults standardUserDefaults] integerForKey: @"sortSeriesBySliceLocation"];
    
    openSubSeriesArray = [toOpenArray retain];
    
    if( [[NSApp mainWindow] level] > NSModalPanelWindowLevel){ NSBeep(); return nil;}		// To avoid the problem of displaying this sheet when the user is in fullscreen mode
    if( [[NSApp keyWindow] level] > NSModalPanelWindowLevel) { NSBeep(); return nil;}		// To avoid the problem of displaying this sheet when the user is in fullscreen mode
    
    [self setValue:[NSNumber numberWithInt:[[toOpenArray objectAtIndex:0] count]] forKey:@"subTo"];
    [self setValue:[NSNumber numberWithInt:[[toOpenArray objectAtIndex:0] count]] forKey:@"subMax"];
    
    [self setValue:[NSNumber numberWithInt:1] forKey:@"subFrom"];
    [self setValue:[NSNumber numberWithInt:1] forKey:@"subInterval"];
    
    if (!subSeriesWindowIsOn)
    {
        subSeriesWindowIsOn = YES;
        // The legacy nib puts this status inside a hidden memory-information section.
        // Keep selection feedback visible independently of that section.
        NSView *content = subSeriesWindow.contentView;
        if (memoryMessage && memoryMessage.superview != content) {
            [memoryMessage retain];
            [memoryMessage removeFromSuperview];
            [content addSubview:memoryMessage];
            [memoryMessage release];
            memoryMessage.translatesAutoresizingMaskIntoConstraints = NO;
            memoryMessage.hidden = NO;
            memoryMessage.textColor = NSColor.labelColor;
            memoryMessage.font = [NSFont systemFontOfSize:NSFont.systemFontSize];
            memoryMessage.alignment = NSTextAlignmentLeft;
            memoryMessage.cell.wraps = YES;
            memoryMessage.cell.scrollable = NO;
            [NSLayoutConstraint activateConstraints:@[
                [memoryMessage.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:20],
                [memoryMessage.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-20],
                [memoryMessage.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-20]
            ]];
        }
        [[NSApp mainWindow] beginSheet:subSeriesWindow completionHandler:nil];
        
        [self checkMemory: self];
        
        int result = [NSApp runModalForWindow: subSeriesWindow];
        [subSeriesWindow makeFirstResponder: nil];
        
        [subSeriesWindow.sheetParent endSheet:subSeriesWindow];
        [subSeriesWindow orderOut: self];
        
        [[waitOpeningWindow window] orderBack: self];
        
        subSeriesWindowIsOn = NO;
        
        NSArray *returnedArray = nil;
        
        if( result == NSModalResponseStop)
            returnedArray = [self produceNewArray: toOpenArray];
        
        [openSubSeriesArray release];
        
        [[NSUserDefaults standardUserDefaults] setInteger: copySortSeriesBySliceLocation forKey: @"sortSeriesBySliceLocation"];
        
        return returnedArray;
    }
    
    return nil;
}


//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark GUI functions

+ (unsigned int)_currentModifierFlags
{
    unsigned int flags = 0;
    UInt32 currentKeyModifiers = GetCurrentKeyModifiers();
    if (currentKeyModifiers & cmdKey)
        flags |= NSEventModifierFlagCommand;
    if (currentKeyModifiers & shiftKey)
        flags |= NSEventModifierFlagShift;
    if (currentKeyModifiers & optionKey)
        flags |= NSEventModifierFlagOption;
    if (currentKeyModifiers & controlKey)
        flags |= NSEventModifierFlagControl;
    
    return flags;
}

// For the DB: fullscreen is equivalent to 'go to the search field'

- (IBAction) switchSoundex: (id)sender
{
    [self setSearchString: _searchString];
}

- (IBAction) searchField: (id)sender
{
    // Is the item available in the toolbar?
    NSArray	*visibleItems = [toolbar visibleItems];
    
    for( id toolbarItem in visibleItems)
    {
        if( [[toolbarItem itemIdentifier] isEqualToString: SearchToolbarItemIdentifier])
        {
            [self.window makeFirstResponder: searchField];
            return;
        }
    }
    
    HorosRunCriticalAlertPanel(NSLocalizedString(@"Search", nil), NSLocalizedString(@"The search field is currently not displayed in the toolbar. Customize your toolbar to add it.", nil), NSLocalizedString(@"OK", nil), nil, nil);
}

+ (long) computeDATABASEINDEXforDatabase:(NSString*)path // __deprecated
{
    return [[DicomDatabase databaseAtPath:path] computeDataFileIndex];
}

- (id)initWithWindow: (NSWindow *)window
{
    
    [AppController initialize];
    
    self = [super initWithWindow: window];
    if( self)
    {
        // Remove identical local sources, and the ones that were never worth
        // remembering: a CD is copied under the user's temporary directory and
        // opened from there, so inserting one left a permanent entry pointing at
        // a path that stops existing when the media is ejected, or when the
        // system empties its temporary folders on its own.
        
        NSArray *dbArray = [[NSUserDefaults standardUserDefaults] arrayForKey: @"localDatabasePaths"];
        for( NSString *dropped in [HorosSourceLocation temporaryEntriesIn: dbArray pathKey: @"Path"])
            NSLog( @"---- sources: forgetting %@; it is in a temporary location, not a database to come back to", dropped);
        
        [[NSUserDefaults standardUserDefaults] setObject: [HorosSourceLocation permanentEntriesIn: dbArray pathKey: @"Path"] forKey: @"localDatabasePaths"];
        
        if( [BrowserController _currentModifierFlags] & NSEventModifierFlagShift && [BrowserController _currentModifierFlags] & NSEventModifierFlagOption)
        {
            NSLog( @"WARNING ---- Protected Mode Activated");
            [DCMPix setRunOsiriXInProtectedMode: YES];
        }
        
        if( [DCMPix isRunOsiriXInProtectedModeActivated])
        {
            HorosRunCriticalAlertPanel(NSLocalizedString(@"Protected Mode", nil), NSLocalizedString(@"Isis DICOM Viewer is now running in Protected Mode (shift + option keys at startup): no images are displayed, allowing you to delete crashing or corrupted images/studies.", nil), NSLocalizedString(@"OK", nil), nil, nil);
        }
        
        _distantAlbumNoOfStudiesCache = [[NSMutableDictionary alloc] init];
        _albumNoOfStudiesCache = [[NSMutableArray alloc] init];
        databaseIndexDictionary = [[NSMutableDictionary alloc] initWithCapacity: 0];
        
        notFoundImage = [[NSImage imageNamed:@"FileNotFound.tif"] retain];
        
        reportFilesToCheck = [[NSMutableDictionary dictionary] retain];
        
        pressedKeys = [[NSMutableString stringWithString:@""] retain];
        
        processorsLock = [[NSConditionLock alloc] initWithCondition: 1];
        
        DatabaseIsEdited = NO;
        
        previousBonjourIndex = -1;
        toolbarSearchItem = nil;
        
        _filterPredicateDescription = nil;
        _filterPredicate = nil;
        _fetchPredicate = nil;
        
        matrixViewArray = nil;
        
        previousNoOfFiles = 0;
        previousItem = nil;
        
        searchType = 7;
        self.timeIntervalType = 0;
        
        outlineViewArray = [[NSArray array] retain];
        browserWindow = self;
        
        [[NSUserDefaults standardUserDefaults] setInteger: [[NSUserDefaults standardUserDefaults] integerForKey: @"DEFAULT_DATABASELOCATION"] forKey: @"DATABASELOCATION"];
        [[NSUserDefaults standardUserDefaults] setObject: [[NSUserDefaults standardUserDefaults] stringForKey: @"DEFAULT_DATABASELOCATIONURL"] forKey: @"DATABASELOCATIONURL"];
        
        if (![HorosDatabaseFirstUse hasPendingChoice])
        {
            NSThread* thread = [NSThread currentThread];
            NSString* oldThreadName = thread.name;
            DicomDatabase* theDatabase = nil;
            [thread enterOperation];
            NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
            @try
            {
            
                theDatabase = [[DicomDatabase activeLocalDatabase] retain]; // explicitly released later
            
            }
            @catch (NSException* e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            @finally
            {
                [thread exitOperation];
                [pool release];
            }
        
            thread.name = oldThreadName;
            self.database = [theDatabase autorelease]; // explicitly retained earlier
        
        }

        previewPix = [[NSMutableArray alloc] init];
        previewPixThumbnails = [[NSMutableArray alloc] init];
        
        [NSTimer scheduledTimerWithTimeInterval: 0.15 target:self selector:@selector(previewPerformAnimation:) userInfo:self repeats:YES];
        
        if( [[NSUserDefaults standardUserDefaults] integerForKey:@"LISTENERCHECKINTERVAL"] < 1)
            [[NSUserDefaults standardUserDefaults] setInteger:1 forKey:@"LISTENERCHECKINTERVAL"];
        
        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"] == NO)
            refreshTimer = [[NSTimer scheduledTimerWithTimeInterval: 5*60 target:self selector:@selector(refreshDatabase:) userInfo:self repeats:YES] retain];
        
        [NSTimer scheduledTimerWithTimeInterval: 10 target:self selector:@selector(emptyDeleteQueue:) userInfo:self repeats:YES]; // 10
        [NSTimer scheduledTimerWithTimeInterval: 1 target:self selector:@selector(refreshComparativeStudiesIfNeeded:) userInfo:self repeats:YES];
        
        loadPreviewIndex = 0;
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(updateReportToolbarIcon:) name:OsirixReportModeChangedNotification object:nil];
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(alternateButtonPressed:) name:OsirixAlternateButtonPressedNotification object:nil];
    }
    return self;
}
- (void) setDBDate
{
    [TimeFormat release];
    TimeFormat = [[NSDateFormatter alloc] init];
    [TimeFormat setTimeStyle: NSDateFormatterShortStyle];
    
    [TimeWithSecondsFormat release];
    TimeWithSecondsFormat = [[NSDateFormatter alloc] init];
    [TimeWithSecondsFormat setTimeStyle: NSDateFormatterMediumStyle];
    
    [DateTimeWithSecondsFormat release];
    DateTimeWithSecondsFormat = [[NSDateFormatter alloc] init];
    [DateTimeWithSecondsFormat setDateStyle: NSDateFormatterShortStyle];
    [DateTimeWithSecondsFormat setTimeStyle: NSDateFormatterMediumStyle];
    
    [[[databaseOutline tableColumnWithIdentifier: @"dateOpened"] dataCell] setFormatter:[NSUserDefaults dateTimeFormatter]];
    [[[databaseOutline tableColumnWithIdentifier: @"date"] dataCell] setFormatter:[NSUserDefaults dateTimeFormatter]];
    [[[databaseOutline tableColumnWithIdentifier: @"dateAdded"] dataCell] setFormatter:[NSUserDefaults dateTimeFormatter]];
    
    [[[databaseOutline tableColumnWithIdentifier: @"dateOfBirth"] dataCell] setFormatter:[NSUserDefaults dateFormatter]];
    [[[databaseOutline tableColumnWithIdentifier: @"reportURL"] dataCell] setFormatter:[NSUserDefaults dateFormatter]];
    [[[databaseOutline tableColumnWithIdentifier: @"noFiles"] dataCell] setFormatter: decimalNumberFormatter];
}

+ (NSString*) DateTimeWithSecondsFormat:(NSDate*) t
{
    NSString *s = nil;
    
    @synchronized( [[BrowserController currentBrowser] DateTimeWithSecondsFormat])
    {
        s = [[[BrowserController currentBrowser] DateTimeWithSecondsFormat] stringFromDate: t];
    }
    
    return s;
}

+ (NSString*) TimeWithSecondsFormat:(NSDate*) t
{
    NSString *s = nil;
    
    @synchronized( [[BrowserController currentBrowser] TimeWithSecondsFormat])
    {
        s = [[[BrowserController currentBrowser] TimeWithSecondsFormat] stringFromDate: t];
    }
    
    return s;
}

+ (NSString*) TimeFormat:(NSDate*) t
{
    NSString *s = nil;
    
    @synchronized( [[BrowserController currentBrowser] TimeFormat])
    {
        s = [[[BrowserController currentBrowser] TimeFormat] stringFromDate: t];
    }
    return s;
}

- (NSDateFormatter*)DateOfBirthFormat // __deprecated
{
    return  [NSUserDefaults dateFormatter];
}

+ (NSString*)DateOfBirthFormat:(NSDate*)d // __deprecated
{
    return  [[NSUserDefaults dateFormatter] stringFromDate:d];
}

- (NSDateFormatter*)DateTimeFormat // __deprecated
{
    return [NSUserDefaults dateTimeFormatter];
}

+ (NSString*)DateTimeFormat:(NSDate*)d // __deprecated
{
    return [[NSUserDefaults dateTimeFormatter] stringFromDate:d];
}

-(void)menuWillOpen:(NSMenu*)menu // DATABASE contextual menu and ALBUMS contextualMenu
{
    if (menu == columnsMenu) {
        [self columnsMenuWillOpen];
        return;
    }
    
    [menu removeAllItems];
    
    BOOL isWritable = ![self.database isReadOnly];
    
    if (menu == [albumTable menu])
    {
        if ([self.database isLocal])
        {
            int row = [albumTable clickedRow];
            NSMenuItem* item;
            
            if (![_database isReadOnly])
            {
                item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Edit Album", nil) action:@selector(albumTableDoublePressed:) keyEquivalent:@""] autorelease];
                [item setTarget:self];
                [menu addItem:item];
                
                [menu addItem: [NSMenuItem separatorItem]];
                
                item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Add Album", nil) action:@selector(addAlbum:) keyEquivalent:@""] autorelease];
                [item setTarget:self];
                [menu addItem:item];
                
                item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Add Smart Album", nil) action:@selector(addSmartAlbum:) keyEquivalent:@""] autorelease];
                [item setTarget:self];
                [menu addItem:item];
                
                [menu addItem: [NSMenuItem separatorItem]];
                
                if (row > 0) { // index 0 is database, cannot be removed. Negative index = click on empty table (not on a particular item)
                    item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Delete Album", nil) action:@selector(removeAlbum:) keyEquivalent:@""] autorelease];
                    [item setTarget:self];
                    [menu addItem:item];
                    
                    [menu addItem: [NSMenuItem separatorItem]];
                }
            }
            
            item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Save Albums", nil) action:@selector(saveAlbums:) keyEquivalent:@""] autorelease];
            [item setTarget: self]; // required because the drawner is the first responder
            [menu addItem:item];
            
            item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Import Albums", nil) action:@selector(addAlbums:) keyEquivalent:@""] autorelease];
            [item setTarget: self]; // required because the drawner is the first responder
            [menu addItem:item];
            
            [menu addItem: [NSMenuItem separatorItem]];
            
            item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Create Default Albums", nil) action:@selector(defaultAlbums:) keyEquivalent:@""] autorelease];
            [item setTarget: self]; // required because the drawner is the first responder
            [menu addItem:item];
        }
        
        return;
    }
    
    [menu addItemWithTitle: NSLocalizedString(@"Display only this patient", nil) action: @selector(searchForCurrentPatient:) keyEquivalent:@""];
    
    [menu addItem: [NSMenuItem separatorItem]];
    [menu addItemWithTitle: NSLocalizedString(@"Open Images", nil) action: @selector(viewerDICOM:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Open Images in 4D", nil) action: @selector(MovieViewerDICOM:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Open Sub-Selection", nil)  action:@selector(viewerSubSeriesDICOM:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Open Reparsed Series", nil)  action:@selector(viewerReparsedSeries:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Open Key Images", nil) action: @selector(viewerDICOMKeyImages:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Open ROIs Images", nil) action: @selector(viewerDICOMROIsImages:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Open ROIs and Key Images", nil) action: @selector(viewerKeyImagesAndROIsImages:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Open Merged Selection", nil) action: @selector(viewerDICOMMergeSelection:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Reveal In Finder", nil) action: @selector(revealInFinder:) keyEquivalent:@""];
    if( [[AppController sharedAppController] workspaceMenu]) {
        [menu addItem: [NSMenuItem separatorItem]];
        NSMenuItem *mi = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Load Workspace State DICOM SR", nil) action: nil keyEquivalent:@""] autorelease];
        [mi setSubmenu: [[[[AppController sharedAppController] workspaceMenu] copy] autorelease]];
        [menu addItem: mi];
        [menu addItemWithTitle: NSLocalizedString(@"Reset Workspace State", nil) action: @selector(resetWindowsState:) keyEquivalent:@""];
    }
    [menu addItem: [NSMenuItem separatorItem]];
    [menu addItemWithTitle: [NSLocalizedString(@"Export to DICOM Network Node", nil) stringByAppendingString:@"\u2026"] action: @selector(export2PACS:) keyEquivalent:@""];
    [menu addItemWithTitle: [NSLocalizedString(@"Export to Movie", nil) stringByAppendingString:@"\u2026"] action: @selector(exportQuicktime:) keyEquivalent:@""];
    [menu addItemWithTitle: [NSLocalizedString(@"Export to JPEG", nil) stringByAppendingString:@"\u2026"] action: @selector(exportJPEG:) keyEquivalent:@""];
    [menu addItemWithTitle: [NSLocalizedString(@"Export to TIFF", nil) stringByAppendingString:@"\u2026"] action: @selector(exportTIFF:) keyEquivalent:@""];
    [menu addItemWithTitle: [NSLocalizedString(@"Export to DICOM File(s)", nil) stringByAppendingString:@"\u2026"] action: @selector(exportDICOMFile:) keyEquivalent:@""];
    [menu addItemWithTitle: [NSLocalizedString(@"Export to Email", nil) stringByAppendingString:@"\u2026"]  action:@selector(sendMail:) keyEquivalent:@""];
    [menu addItemWithTitle: NSLocalizedString(@"Export ROI and Key Images as a DICOM Series", nil) action:@selector(exportROIAndKeyImagesAsDICOMSeries:) keyEquivalent:@""];
    
    if (isWritable) {
        [menu addItem: [NSMenuItem separatorItem]];
        [menu addItemWithTitle: NSLocalizedString(@"Add selected study(s) to user(s)", nil)  action:@selector(addStudiesToUser:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Send an email notification to user(s)", nil)  action:@selector(sendEmailNotification:) keyEquivalent:@""];
    }
    
    if (isWritable) {
        [menu addItem: [NSMenuItem separatorItem]];
        [menu addItemWithTitle: NSLocalizedString(@"Compress DICOM files", nil)  action:@selector(compressSelectedFiles:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Decompress DICOM files", nil)  action:@selector(decompressSelectedFiles:) keyEquivalent:@""];
    }
    
    if (isWritable) {
        [menu addItem: [NSMenuItem separatorItem]];
        [menu addItemWithTitle: NSLocalizedString(@"Lock Studies", nil)  action:@selector(lockStudies:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Unlock Studies", nil)  action:@selector(unlockStudies:) keyEquivalent:@""];
    }
    
    if (isWritable) { // TODO: allow report access, read-only
        [menu addItem: [NSMenuItem separatorItem]];
        [menu addItemWithTitle: NSLocalizedString(@"Create/Open Report", nil) action: @selector(generateReport:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Convert Report to PDF...", nil) action: @selector(convertReportToPDF:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Convert Report to DICOM PDF", nil) action: @selector(convertReportToDICOMSR:) keyEquivalent:@""];
    }
    
    if (isWritable) {
        [menu addItem: [NSMenuItem separatorItem]];
        [menu addItemWithTitle: NSLocalizedString(@"Merge Selected Studies", nil) action: @selector(mergeStudies:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Unify patient identity", nil) action: @selector(unifyStudies:) keyEquivalent:@""];
    }
    
    if (isWritable) {
        [menu addItem: [NSMenuItem separatorItem]];
        [menu addItemWithTitle: NSLocalizedString(@"Delete", nil) action: @selector(delItem:) keyEquivalent:@""];
    }
    
    if (isWritable) {
        [menu addItem: [NSMenuItem separatorItem]];
        [menu addItemWithTitle: NSLocalizedString(@"Query Selected Patient from Q&R Window...", nil) action: @selector(querySelectedStudy:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Burn", nil) action: @selector(burnDICOM:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Anonymize", nil) action: @selector(anonymizeDICOM:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Rebuild Selected Thumbnails", nil)  action:@selector(rebuildThumbnails:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Regenerate Auto-Fill Comment field", nil)  action:@selector(regenerateAutoComments:) keyEquivalent:@""];
        [menu addItemWithTitle: NSLocalizedString(@"Copy Linked Files to Database Folder", nil)  action:@selector(copyToDBFolder:) keyEquivalent:@""];
    }
    
    NSArray *autoroutingRules = [[NSUserDefaults standardUserDefaults] arrayForKey: @"AUTOROUTINGDICTIONARY"];
    
    if(isWritable && [autoroutingRules count])
    {
        [menu addItem: [NSMenuItem separatorItem]];
        
        NSMenu *submenu = nil;
        
        if( [autoroutingRules count] > 0)
        {
            submenu = [[[NSMenu alloc] initWithTitle: NSLocalizedString(@"Apply this Routing Rule to Selection", nil)] autorelease];
            
            NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"All routing rules", nil)  action:@selector(applyRoutingRule:) keyEquivalent:@""] autorelease];
            [submenu addItem: item];
            [submenu addItem: [NSMenuItem separatorItem]];
            
            for( NSDictionary *routingRule in autoroutingRules)
            {
                NSString *s = [routingRule valueForKey: @"description"];
                
                if( [s length] > 0)
                    item = [[[NSMenuItem alloc] initWithTitle: [NSString stringWithFormat: @"%@ - %@", [routingRule valueForKey: @"name"], s] action: @selector(applyRoutingRule:) keyEquivalent:@""] autorelease];
                else
                    item = [[[NSMenuItem alloc] initWithTitle: [routingRule valueForKey: @"name"] action: @selector(applyRoutingRule:) keyEquivalent:@""] autorelease];
                
                [item setRepresentedObject: routingRule];
                
                if( [routingRule valueForKey:@"activated"] == nil || [[routingRule valueForKey:@"activated"] boolValue])
                    [item setEnabled: NO];
                else
                    [item setEnabled: NO];
                
                [submenu addItem: item];
            }
            
            item = [[[NSMenuItem alloc] initWithTitle: NSLocalizedString(@"Apply this Routing Rule to Selection", nil)  action: nil keyEquivalent:@""] autorelease];
            [item setSubmenu: submenu];
            [menu addItem: item];
        }
    }
}

-(void) awakeFromNib
{
    @try
    {
        [self buildMetadataExportMenuItem];
        
        // The preview keeps the reason for its window, so that a scroll or a
        // second thumbnail batch cannot quietly undo an adjustment (#608).
        if( previewWindowPolicy == nil)
            previewWindowPolicy = [[HorosPreviewWindowPolicy alloc] init];
        if( previewRedrawCoalescer == nil)
            previewRedrawCoalescer = [[HorosPreviewRedrawCoalescer alloc] initWithInterval: 0.03];
        [imageView setWindowDelegate: self];

        
        NSRect r = NSMakeRect(0, 0, 0, 0);
        
        r = NSRectFromString( [[NSUserDefaults standardUserDefaults] stringForKey: @"DBWindowFrame"]);
        
        [HorosFullScreenWindowSupport enablePrimaryFullScreen: self.window];
        
        gHorizontalHistory = [[NSUserDefaults standardUserDefaults] boolForKey: @"horizontalHistory"];
        
        if( gHorizontalHistory)
        {
            NSSplitView * s = [[NSSplitView alloc] initWithFrame: splitViewVert.bounds];
            
            [s setDelegate: self];
            [s addSubview: comparativeScrollView];
            [s addSubview: matrixView];
            
            [splitViewVert addSubview: s];
            [splitViewVert addSubview: imageView];
            
            splitComparative = s;
        }
        
        [self setTableViewRowHeight];

        [HorosDatabaseBrowserLayout prepareSidebar:splitAlbums];
        [HorosDatabaseBrowserLayout prepareFilterView:timeIntervalView];
        [HorosDatabaseBrowserLayout prepareFilterView:modalityFilterView];
        [HorosDatabaseBrowserLayout prepareSearchView:searchView];
        
        [self saveLoadAlbumsSortDescriptors];
        
        WaitRendering *wait = [[AppController sharedAppController] splashScreen];
        
        
        
        [oMatrix setIntercellSpacing:NSMakeSize(-1, -1)];
        
        [wait showWindow:self];
        
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(updateReportToolbarIcon:) name:NSOutlineViewSelectionDidChangeNotification object:databaseOutline];
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(updateReportToolbarIcon:) name:NSOutlineViewSelectionIsChangingNotification object:databaseOutline];
        [reportTemplatesListPopUpButton setAccessibilityLabel:NSLocalizedString(@"Report template", nil)];
        [reportTemplatesListPopUpButton setAccessibilityHelp:NSLocalizedString(@"Choose a template to create a report for the selected study.", nil)];
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(reportToolbarItemWillPopUp:) name:NSPopUpButtonWillPopUpNotification object:reportTemplatesListPopUpButton];
        
        [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(observeScrollerStyleDidChangeNotification:) name:@"NSPreferredScrollerStyleDidChangeNotification" object:nil];
        [self observeScrollerStyleDidChangeNotification:nil];
        
        @try
        {
            [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(previewMatrixScrollViewFrameDidChange:) name:NSViewFrameDidChangeNotification object:thumbnailsScrollView];
            [self previewMatrixScrollViewFrameDidChange:nil];
            
            NSTableColumn		*tableColumn = nil;
            NSPopUpButtonCell	*buttonCell = nil;
            
            // thumbnails : no background color
            [thumbnailsScrollView setDrawsBackground:NO];
            [[thumbnailsScrollView contentView] setDrawsBackground:NO];
            
            if (![HorosDatabaseFirstUse hasPendingChoice])
                [self awakeSources];
            [oMatrix setDelegate:self];
            [oMatrix setSelectionByRect: NO];
            [oMatrix setDoubleAction:@selector(matrixDoublePressed:)];
            [oMatrix setFocusRingType: NSFocusRingTypeExterior];
            [oMatrix renewRows:0 columns: 0];
            
            [imageView setTheMatrix:oMatrix];
            
            
            [databaseOutline setAction:@selector(databasePressed:)];
            [databaseOutline setDoubleAction:@selector(databaseDoublePressed:)];
            [databaseOutline registerForDraggedTypes:@[@"NSFilenamesPboardType"]];
            [databaseOutline setAllowsMultipleSelection:YES];
            [databaseOutline setAutosaveName: nil];
            [databaseOutline setAutosaveTableColumns: NO];
            [databaseOutline setAllowsTypeSelect: NO];
            
            [self setupToolbar];
            
            [toolbar setVisible:YES];
            // Toolbar attachment changes the frame to preserve content height. Restore
            // the saved outer frame only after the toolbar is installed and visible.
            [HorosDatabaseWindowPlacement restoreWindow:self.window savedFrame:r];
            // NSMenu for DatabaseOutline
            NSMenu* menu = [[[NSMenu alloc] initWithTitle:@""] autorelease];
            [menu setDelegate:self];
            [databaseOutline setMenu:menu];
            
            [self addHelpMenu];
            
            ImageAndTextCell *cell = [[[ImageAndTextCell alloc] init] autorelease];
            [cell setEditable:YES];
            [[albumTable tableColumnWithIdentifier:@"Source"] setDataCell:cell];
            [albumTable setDelegate:self];
            [albumTable registerForDraggedTypes:[BrowserController.DatabaseObjectXIDsPasteboardTypes arrayByAddingObjectsFromArray:@[
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
                                                  O2AlbumDragType // we still support the original, non-UTI type, in case some plugin uses this (very unlikely)
#pragma clang diagnostic pop
                                                  ]]];

            //		[customStart setDateValue: [NSCalendarDate dateWithYear:[[NSCalendarDate date] yearOfCommonEra] month:[[NSCalendarDate date] monthOfYear] day:[[NSCalendarDate date] dayOfMonth] hour:0 minute:0 second:0 timeZone: nil]];
            //		[customStart2 setDateValue: [NSCalendarDate dateWithYear:[[NSCalendarDate date] yearOfCommonEra] month:[[NSCalendarDate date] monthOfYear] day:[[NSCalendarDate date] dayOfMonth] hour:0 minute:0 second:0 timeZone: nil]];
            //		[customEnd setDateValue: [NSCalendarDate dateWithYear:[[NSCalendarDate date] yearOfCommonEra] month:[[NSCalendarDate date] monthOfYear] day:[[NSCalendarDate date] dayOfMonth] hour:0 minute:0 second:0 timeZone: nil]];
            //		[customEnd2 setDateValue: [NSCalendarDate dateWithYear:[[NSCalendarDate date] yearOfCommonEra] month:[[NSCalendarDate date] monthOfYear] day:[[NSCalendarDate date] dayOfMonth] hour:0 minute:0 second:0 timeZone: nil]];
            
            statesArray = [[NSArray arrayWithObjects:NSLocalizedString(@"empty", nil), NSLocalizedString(@"unread", nil), NSLocalizedString(@"reviewed", nil), NSLocalizedString(@"dictated", nil), NSLocalizedString(@"validated", nil), nil] retain];
            
            
            ImageAndTextCell *cellName = [[[ImageAndTextCell alloc] init] autorelease];
            [[databaseOutline tableColumnWithIdentifier:@"name"] setDataCell:cellName];
            
            ImageAndTextCell *cellReport = [[[ImageAndTextCell alloc] init] autorelease];
            [[databaseOutline tableColumnWithIdentifier:@"reportURL"] setDataCell:cellReport];
            
            // Set International dates for columns
            [self setDBDate];
            
            tableColumn = [databaseOutline tableColumnWithIdentifier: @"stateText"];
            buttonCell = [[[NSPopUpButtonCell alloc] initTextCell: @"" pullsDown:NO] autorelease];
            [buttonCell setEditable: YES];
            [buttonCell setBordered: NO];
            [buttonCell addItemsWithTitles: statesArray];
            [tableColumn setDataCell:buttonCell];
            
            // setInitialState was a compatibility no-op; tableColumns is authoritative.
            
            
            if( [[NSUserDefaults standardUserDefaults] objectForKey: @"databaseColumns2"])
                [databaseOutline restoreColumnState: [[NSUserDefaults standardUserDefaults] objectForKey: @"databaseColumns2"]];
            
            if( [[NSUserDefaults standardUserDefaults] objectForKey: @"databaseSortDescriptor"])
            {
                NSDictionary	*sort = [[NSUserDefaults standardUserDefaults] objectForKey: @"databaseSortDescriptor"];
                {
                    if( [databaseOutline isColumnWithIdentifierVisible: [sort objectForKey:@"key"]])
                    {
                        NSSortDescriptor *prototype = [[databaseOutline tableColumnWithIdentifier: [sort objectForKey:@"key"]] sortDescriptorPrototype];
                        
                        [databaseOutline setSortDescriptors: [NSArray arrayWithObject: [[[NSSortDescriptor alloc] initWithKey:[sort objectForKey:@"key"] ascending:[[sort objectForKey:@"order"] boolValue]  selector: [prototype selector]] autorelease]]];
                    }
                    else
                        [databaseOutline setSortDescriptors:[NSArray arrayWithObject: [[[NSSortDescriptor alloc] initWithKey:@"name" ascending:YES selector:@selector(caseInsensitiveCompare:)] autorelease]]];
                }
            }
            else
                [databaseOutline setSortDescriptors:[NSArray arrayWithObject: [[[NSSortDescriptor alloc] initWithKey:@"name" ascending:YES selector:@selector(caseInsensitiveCompare:)] autorelease]]];
            
            [self loadSortDescriptors:nil];
            
            [databaseOutline selectRowIndexes: [NSIndexSet indexSetWithIndex: 0] byExtendingSelection:NO];
            [databaseOutline scrollRowToVisible: 0];
            [self buildColumnsMenu];
            
            self.modalityFilter = nil;
            
            [animationCheck setState: [[NSUserDefaults standardUserDefaults] boolForKey: @"AutoPlayAnimation"]];
            
            activeSends = [[NSMutableDictionary dictionary] retain];
            sendLog = [[NSMutableArray array] retain];
            activeReceives = [[NSMutableDictionary dictionary] retain];
            receiveLog = [[NSMutableArray array] retain];
            
            // bonjour
            bonjourBrowser = [[BonjourBrowser alloc] initWithBrowserController:self];
            [self displayBonjourServices];
            
            [[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forValuesKey:OsirixBonjourSharingIsActiveDefaultsKey options:NSKeyValueObservingOptionInitial context:bonjourBrowser];
            
            [splitDrawer restoreDefault: @"SplitDrawer"];
            [splitAlbums restoreDefault: @"SplitAlbums"];
            [HorosDatabaseBrowserLayout layoutSidebar:splitAlbums];
            [splitViewHorz restoreDefault: @"SplitHorz2"];
            [splitComparative restoreDefault: @"SplitComparative"];
            [splitViewVert restoreDefault: @"SplitVert2"];
            
            if( gHorizontalHistory)
            {
                NSView* top = [[splitComparative subviews] objectAtIndex:0];
                BOOL hidden = [top isHidden] || [splitComparative isSubviewCollapsed: top];
                if( [[NSUserDefaults standardUserDefaults] boolForKey: @"SplitComparativeHidden"] != hidden)
                    [self comparativeToggle: self];
            }
            else
            {
                NSView* right = [[splitComparative subviews] objectAtIndex:1];
                BOOL hidden = [right isHidden] || [splitComparative isSubviewCollapsed: right];
                if( [[NSUserDefaults standardUserDefaults] boolForKey: @"SplitComparativeHidden"] != hidden)
                    [self comparativeToggle: self];
            }
            {
                NSView* left = [[splitDrawer subviews] objectAtIndex:0];
                BOOL hidden = [left isHidden] || [splitDrawer isSubviewCollapsed:left];
                if( [[NSUserDefaults standardUserDefaults] boolForKey: @"SplitDrawerHidden"] != hidden)
                    [self drawerToggle: self];
            }
            
            
            [[albumTable tableColumnWithIdentifier:@"Source"] setDataCell: [[[PrettyCell alloc] init] autorelease]];
            
            [[comparativeTable tableColumnWithIdentifier:@"Cell"] setDataCell: [[[ComparativeCell alloc] init] autorelease]];
            [comparativeTable setDoubleAction: @selector(doubleClickComparativeStudy:)];
            
            [self initContextualMenus];
            
            // opens a port for interapplication communication
            HorosRegisterLegacyDistributedBrowser(self);
            //start timer for monitoring incoming logs on main thread
            (void)[LogManager currentLogManager];
            
            // SCAN FOR AN IPOD!
            // Mounted media are handled by the volume observers in BrowserController+Sources.
        }
        
        @catch( NSException *ne)
        {
            N2LogExceptionWithStackTrace(ne);
            [@"" writeToFile:_database.loadingFilePath atomically:NO encoding:NSUTF8StringEncoding error:NULL];
            
            NSString *message = [NSString stringWithFormat: NSLocalizedString(@"A problem occured during start-up of Isis DICOM Viewer:\r\r%@\r\r%@",nil), [ne description], [ne printStackTrace]];
            
            HorosRunCriticalAlertPanel(NSLocalizedString(@"Error",nil), @"%@", NSLocalizedString( @"OK",nil), nil, nil, message);
            
            exit( 0);
        }
        
        [wait close];
        
        [self testAutorouting];
        
        [self setDBWindowTitle];
        
        loadingIsOver = YES;
        
        [self outlineViewRefresh];
        
        [self awakeActivity];
        [self.window makeKeyAndOrderFront: self];
        
        [self refreshMatrix: self];
        
#ifndef OSIRIX_LIGHT
        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"restartAutoQueryAndRetrieve"] == YES && [[NSUserDefaults standardUserDefaults] objectForKey: @"savedAutoDICOMQuerySettingsArray"] != nil)
        {
            [[AppController sharedAppController] notificationTitle: NSLocalizedString( @"Auto-Query", nil) description: NSLocalizedString( @"DICOM Auto-Query is restarting...", nil)  name:@"autoquery"];
            NSLog( @"-------- automatically restart DICOM AUTO-QUERY --------");
            
            WaitRendering *wait = [[WaitRendering alloc] init: NSLocalizedString(@"Restarting Auto Query/Retrieve...", nil)];
            [wait showWindow:self];
            [[QueryController alloc] initAutoQuery: YES];
            [[QueryController currentAutoQueryController] switchAutoRetrieving: self];
            [NSThread sleepForTimeInterval: 0.5];
            [wait close];
            [wait autorelease];
        }
        else
            [[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"autoRetrieving"];
#endif
        
        [[self window] setAnimationBehavior: NSWindowAnimationBehaviorNone];
        
        // Responder chain
        
        [albumTable setNextKeyView: databaseOutline];
        [_sourcesTableView setNextKeyView: databaseOutline];
        [databaseOutline setNextKeyView: searchField];
        [searchField setNextKeyView: databaseOutline];
        
        // Extend every localized nib's search menu without renumbering saved modes.
        NSMenu *searchMenu = [[[searchField cell] searchMenuTemplate] copy];
        if (![searchMenu itemWithTag:11]) {
            NSMenuItem *seriesSearch = [[[NSMenuItem alloc] initWithTitle:NSLocalizedString(@"Series Description", nil) action:@selector(setSearchType:) keyEquivalent:@""] autorelease];
            seriesSearch.tag = 11;
            seriesSearch.target = self;
            [searchMenu insertItem:seriesSearch atIndex:MIN([searchMenu numberOfItems], [searchMenu indexOfItemWithTag:4] + 1)];
        }
        [[searchField cell] setSearchMenuTemplate:searchMenu];
        [searchMenu release];
        [self setSearchType: [[[searchField cell] searchMenuTemplate] itemWithTag: [[NSUserDefaults standardUserDefaults] integerForKey: @"searchType"]]];
        
    }
    @catch (NSException *e) {
        N2LogException( e);
    }
    
    BOOL firstTimeExecution = ([[NSUserDefaults standardUserDefaults] objectForKey:@"FIRST_TIME_EXECUTION_2_0"] == nil);
    BOOL foundNotValidatedOsiriXPlugins = NO;
    
    if (firstTimeExecution)
    {
        [[NSUserDefaults standardUserDefaults] setObject:[NSNumber numberWithBool:YES] forKey:@"FIRST_TIME_EXECUTION_2_0"];
        
        
        
        NSArray* installedPlugins = [self->pluginManagerController plugins];
        for (NSDictionary* pluginDesc in installedPlugins)
        {
            if ([[pluginDesc objectForKey:@"HorosCompatiblePlugin"] boolValue] == NO)
            {
                foundNotValidatedOsiriXPlugins = YES;
                break;
            }
        }
        
        
        [[NSUserDefaults standardUserDefaults] setInteger:CPRInterpolationModeCubic
                                                   forKey:@"selectedCPRInterpolationMode"];
        
        
        dispatch_async(dispatch_get_main_queue(), ^() {
            
            [self restoreWindowState:self];
            
        });
    }
    
    
    
    if (firstTimeExecution == YES && foundNotValidatedOsiriXPlugins == YES)
    {
        NSAlert *alert = [[NSAlert alloc] init];
        [alert addButtonWithTitle:NSLocalizedString(@"OK",nil)];
        [alert setMessageText:NSLocalizedString(@"Not validated OsiriX plugins were detected!",nil)];
        [alert setInformativeText:NSLocalizedString(@"Not validated OsiriX plugins may cause Isis DICOM Viewer run-time errors. In case of problems, you can disable/uninstall them in [Plugins => Plugin Manager]. A brand new Isis DICOM Viewer plugin database is being built for you.",nil)];
        [alert setAlertStyle:NSAlertStyleWarning];
        [alert runModal];
        [alert release];
    }
    
    
    NSUserDefaults *userDefaults= [NSUserDefaults standardUserDefaults];
    if ([[[userDefaults dictionaryRepresentation] allKeys] containsObject:@"ROIColorRotation"] == NO)
    {
        [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"ROIColorRotation"];
    }
    
#if defined(USEHOMEPHONE)
    [[HorosHomePhone sharedHomePhone] callHomeInformingFunctionType:HOME_PHONE_HOROS_STARTED detail:@"{}"];
#endif
    
    if (![HorosDatabaseFirstUse hasPendingChoice])
    {
        [ICloudDriveDetector performStartupICloudDriveTasks:self];
        [O2HMigrationAssistant performStartupO2HTasks:self];
    }
}

- (void)completeFirstUseDatabaseSetup
{
    // Sources can have queued a nil default database while setup was pending.
    // Do not let that stale nib-loading selection clear the chosen database.
    [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(setDatabase:) object:nil];
    [self awakeSources];
    [self resetToLocalDatabase];
    [ICloudDriveDetector performStartupICloudDriveTasks:self];
    [O2HMigrationAssistant performStartupO2HTasks:self];
}

// The banner was fetched and shown only when WITH_BANNER was defined, which it
// never is. The action stays: it is declared in the public header.
- (IBAction) clickBanner:(id) sender
{
}

-(void)dealloc
{
    [self deallocActivity];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forValuesKey:OsirixBonjourSharingIsActiveDefaultsKey];
    [self deallocSources];
    
    [NSObject cancelPreviousPerformRequestsWithTarget: self selector: @selector(applyPreviewWindowForCurrentFrame) object: nil];
    [imageView setWindowDelegate: nil];
    [previewRedrawCoalescer cancel];
    [previewRedrawCoalescer release]; previewRedrawCoalescer = nil;
    [previewWindowPolicy release]; previewWindowPolicy = nil;
    
    [super dealloc];
}

-(void)observeValueForKeyPath:(NSString*)keyPath ofObject:(id)object change:(NSDictionary*)change context:(void*)context
{
    if (object == [NSUserDefaultsController sharedUserDefaultsController])
    {
        keyPath = [keyPath substringFromIndex:7];
        if ([keyPath isEqual:OsirixBonjourSharingIsActiveDefaultsKey])
        {
            [self resetToDefaultDatabaseIfNecessary];
            return;
        }
    }
    
    [super observeValueForKeyPath:keyPath ofObject:object change:change context:context];
}

- (IBAction)customize:(id)sender
{
    [toolbar runCustomizationPalette:sender];
}

- (IBAction)showhide:(id)sender
{
    [toolbar setVisible:![toolbar isVisible]];
}

- (void)waitForRunningProcesses
{
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    if( waitForRunningProcess == YES)
        return;
    
    waitForRunningProcess = YES;
    
    WaitRendering *wait = nil;
    
    if( [NSThread isMainThread] && [[self window] isVisible])
        wait = [[WaitRendering alloc] init: NSLocalizedString(@"Wait for running processes...", nil)];
    
    @try
    {
        // ----------
        
        if (![[NSUserDefaults standardUserDefaults] hasArgumentOverrideForKey:@"hideListenerError"])
        {
            BOOL hideListenerError_copy = [[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"];
        
            [[NSUserDefaults standardUserDefaults] setBool: hideListenerError_copy forKey: @"copyHideListenerError"];
            [[NSUserDefaults standardUserDefaults] setBool: YES forKey: @"hideListenerError"];
            [[NSUserDefaults standardUserDefaults] synchronize];
        
        
            [[NSUserDefaults standardUserDefaults] setBool: hideListenerError_copy forKey: @"hideListenerError"];
            [[NSUserDefaults standardUserDefaults] removeObjectForKey: @"copyHideListenerError"];
            [[NSUserDefaults standardUserDefaults] synchronize];
        
        }

        // ----------
        
        [BrowserController tryLock:searchForComparativeStudiesLock during: 120];
        
        //Something in the delete queue? Write it to the disk
        [self saveDeleteQueue];
        [self syncReportsIfNecessary];
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    waitForRunningProcess = NO;
    
    [wait close];
    [wait autorelease];
    
    [pool release];
}

- (void) browserPrepareForClose
{
    
    NSRect savedFrame = self.window.frame;
    if ((self.window.styleMask & NSWindowStyleMaskFullScreen) && !NSIsEmptyRect(_databaseWindowedFrame))
        savedFrame = _databaseWindowedFrame;
    [[NSUserDefaults standardUserDefaults] setObject:NSStringFromRect(savedFrame) forKey:@"DBWindowFrame"];
    
    NSLog( @"browserPrepareForClose");
    
    [self saveLoadAlbumsSortDescriptors];
    
    [[DicomStudy dbModifyLock] lock];
    [[DicomStudy dbModifyLock] unlock];
    
    #ifndef OSIRIX_LIGHT
    [[[WebPortal defaultWebPortal] database] save:NULL];
#endif
    (void)[_database save:NULL];
    #ifndef OSIRIX_LIGHT
    [[[WebPortal defaultWebPortal] database] save:NULL];
#endif
    
    [self waitForRunningProcesses];
    
    (void)[_database save:NULL];
    
    self.database = nil;
    
    
    [splitViewVert saveDefault:@"SplitVert2"];
    [splitViewHorz saveDefault:@"SplitHorz2"];
    [splitAlbums saveDefault:@"SplitAlbums"];
    [splitComparative saveDefault:@"SplitComparative"];
    [splitDrawer saveDefault:@"SplitDrawer"];
    
    {
        NSView* left = [[splitDrawer subviews] objectAtIndex:0];
        BOOL hidden = [left isHidden] || [splitDrawer isSubviewCollapsed:[[splitDrawer subviews] objectAtIndex:0]];
        
        [[NSUserDefaults standardUserDefaults] setBool: hidden forKey: @"SplitDrawerHidden"];
    }
    
    if( gHorizontalHistory)
    {
        NSView* top = [[splitComparative subviews] objectAtIndex:0];
        BOOL hidden = [top isHidden] || [splitComparative isSubviewCollapsed:[[splitComparative subviews] objectAtIndex:0]];
        
        [[NSUserDefaults standardUserDefaults] setBool: hidden forKey: @"SplitComparativeHidden"];
    }
    else
    {
        NSView* right = [[splitComparative subviews] objectAtIndex:1];
        BOOL hidden = [right isHidden] || [splitComparative isSubviewCollapsed:[[splitComparative subviews] objectAtIndex:1]];
        
        [[NSUserDefaults standardUserDefaults] setBool: hidden forKey: @"SplitComparativeHidden"];
    }
    
    if( [[databaseOutline sortDescriptors] count] >= 1)
    {
        NSDictionary	*sort = [NSDictionary	dictionaryWithObjectsAndKeys: [NSNumber numberWithBool:[[[databaseOutline sortDescriptors] objectAtIndex: 0] ascending]], @"order", [[[databaseOutline sortDescriptors] objectAtIndex: 0] key], @"key", nil];
        [[NSUserDefaults standardUserDefaults] setObject:sort forKey: @"databaseSortDescriptor"];
    }
    [[NSUserDefaults standardUserDefaults] setObject:[databaseOutline columnState] forKey: @"databaseColumns2"];
    
    [self.window setDelegate:nil];
    
    [[NSUserDefaults standardUserDefaults] setBool: [animationCheck state] forKey: @"AutoPlayAnimation"];
    
    [[NSUserDefaults standardUserDefaults] synchronize];
    
    [[NSFileManager defaultManager] removeItemAtPath: [[[NSFileManager defaultManager] tmpDirPath] stringByAppendingPathComponent: @"OsiriXTemporaryDatabase"] error:NULL];
    [[NSFileManager defaultManager] removeItemAtPath: [[[NSFileManager defaultManager] tmpDirPath] stringByAppendingPathComponent: @"dicomsr_osirix"] error:NULL];
}

-(void)shouldTerminateCallback:(NSTimer*) tt
{
    if(/* newFilesInIncoming || */[[ThreadsManager defaultManager] threadsCount] > 0)
    {
    }
    else
        [[NSApplication sharedApplication] stopModalWithCode: HorosAlertAlternateResponse];
}

- (BOOL)shouldTerminate: (id)sender
{
    // Is there a full screen window displayed?
    for( id window in [NSApp orderedWindows])
    {
        if( [window isKindOfClass: [NSFullScreenWindow class]])
        {
            NSBeep();
            return NO;
        }
    }
    
    [ViewerController closeAllWindows];
    
    (void)[_database save:NULL];
    
    if(/* newFilesInIncoming ||*/ [[ThreadsManager defaultManager] threadsCount] > 0)
    {
        NSAlert* w = [[[NSAlert alloc] init] autorelease];
        w.messageText = NSLocalizedString(@"Background Operations", NULL);
        w.informativeText = NSLocalizedString(@"Background operations are currently running. Are you sure you want to quit now? These operations will be cancelled.", NULL);
        [w addButtonWithTitle:NSLocalizedString(@"Cancel", NULL)];
        [w addButtonWithTitle:NSLocalizedString(@"Quit", NULL)];
        
        NSTimer *t = [NSTimer timerWithTimeInterval: 0.3 target:self selector:@selector(shouldTerminateCallback:) userInfo: w repeats:YES];
        
        [[NSRunLoop currentRunLoop] addTimer: t forMode:NSModalPanelRunLoopMode];
        
        NSInteger r = [w runModal];
        
        [t invalidate];
        
        if( /*newFilesInIncoming ||*/ [[ThreadsManager defaultManager] threadsCount] > 0)
        {
            if( r == NSAlertFirstButtonReturn)
                return NO;
        }
        
        // AppController will cancel these threads and give them 10 secs to finish... then kill them
    }
    
    if( [SendController sendControllerObjects] > 0)
    {
        if( HorosRunInformationalAlertPanel( NSLocalizedString(@"DICOM Sending - STORE", nil), NSLocalizedString(@"Files are currently being sent to a DICOM node. Are you sure you want to quit now? The sending will be stopped.", nil), NSLocalizedString(@"No", nil), NSLocalizedString(@"Quit", nil), nil) == HorosAlertDefaultResponse) return NO;
    }
    
    [self setDatabase:nil];
    
    return YES;
}

- (IBAction)fullScreenMenu:(id)sender
{
    [self.window toggleFullScreen:sender];
}

- (void)windowWillEnterFullScreen:(NSNotification *)notification
{
    if (notification.object == self.window) _databaseWindowedFrame = self.window.frame;
}

- (void)showDatabase: (id)sender
{
    [HorosDatabaseWindowPlacement restoreWindow:self.window savedFrame:self.window.frame];
    if (self.window.isMiniaturized) [self.window deminiaturize:sender];
    [NSApp activateIgnoringOtherApps:YES];
    
    [self.window makeKeyAndOrderFront:sender];
    [self outlineViewRefresh];
}

- (void)keyDown:(NSEvent *)event
{
    NSResponder* firstResponder = [[self window] firstResponder];
    if (firstResponder == albumTable || firstResponder == _sourcesTableView || firstResponder == _activityTableView) {
        [super keyDown:event];
        return;
    }
    
    if( [[event characters] length] == 0) return;
    
    unichar c = [[event characters] characterAtIndex:0];
    
    if (c == NSDeleteFunctionKey || c == NSDeleteCharacter || c == NSBackspaceCharacter || c == NSDeleteCharFunctionKey)
        [self delItem: [[self window] firstResponder]];
    
    else if(c == NSNewlineCharacter ||
            c == NSEnterCharacter ||
            c == NSCarriageReturnCharacter)
        [self viewerDICOM: [[self window] firstResponder]];
    
    else if(c == ' ')
        [animationCheck setState: ![animationCheck state]];
    
    else
    {
        [pressedKeys appendString: [event characters]];
        
        NSLog(@"%@", pressedKeys);
        
        NSArray		*result = [outlineViewArray filteredArrayUsingPredicate: [NSPredicate predicateWithFormat:@"name BEGINSWITH[cd] %@", [NSString stringWithFormat:@"%@", pressedKeys]]];
        
        [NSObject cancelPreviousPerformRequestsWithTarget: pressedKeys selector:@selector(setString:) object:@""];
        [pressedKeys performSelector:@selector(setString:) withObject:@"" afterDelay:0.5];
        
        if( [result count])
        {
            [HorosOutlineSelectionRestore selectItem: [result objectAtIndex: 0] inOutline: databaseOutline extending: NO];
            [databaseOutline scrollRowToVisible: databaseOutline.selectedRow];
        }
        else NSBeep();
    }
}

- (IBAction) unlockStudies: (id) sender
{
    NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
    
    for( NSInteger x = 0, row; x < selectedRows.count; x++)
    {
        if( x == 0) row = selectedRows.firstIndex;
        else row = [selectedRows indexGreaterThanIndex: row];
        
        NSManagedObject	*object = [databaseOutline itemAtRow: row];
        
        if( [[object valueForKey:@"type"] isEqualToString: @"Study"] && [[object valueForKey: @"lockedStudy"] boolValue])
            [object setValue: [NSNumber numberWithBool: NO] forKey: @"lockedStudy"];
    }
    
    [self refreshDatabase: self];
}

- (IBAction) lockStudies: (id) sender
{
    NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
    
    for( NSInteger x = 0, row; x < selectedRows.count; x++)
    {
        if( x == 0) row = selectedRows.firstIndex;
        else row = [selectedRows indexGreaterThanIndex: row];
        
        NSManagedObject	*object = [databaseOutline itemAtRow: row];
        
        if( [[object valueForKey:@"type"] isEqualToString: @"Study"] && [[object valueForKey: @"lockedStudy"] boolValue] == NO)
            [object setValue: [NSNumber numberWithBool: YES] forKey: @"lockedStudy"];
    }
    
    [self refreshDatabase: self];
}

- (BOOL) validateMenuItem: (NSMenuItem*) menuItem
{
    if (menuItem.action == @selector(attachExistingReport:)) {
        if (!self.database.isLocal || self.database.isReadOnly || databaseOutline.selectedRowIndexes.count != 1) return NO;
        id item = [databaseOutline itemAtRow:databaseOutline.selectedRowIndexes.firstIndex];
        if ([item isDistant]) return NO;
        id study = [[item valueForKey:@"type"] isEqualToString:@"Study"] ? item : [item valueForKey:@"study"];
        return study && ![[study valueForKey:@"lockedStudy"] boolValue];
    }
    if (menuItem.action == @selector(insertSelectedImagesIntoReport:)) {
        if (!self.database.isLocal || self.database.isReadOnly || databaseOutline.selectedRowIndexes.count != 1) return NO;
        id item = [databaseOutline itemAtRow:databaseOutline.selectedRowIndexes.firstIndex];
        if ([item isDistant]) return NO;
        id study = [[item valueForKey:@"type"] isEqualToString:@"Study"] ? item : [item valueForKey:@"study"];
        NSString *report = [study valueForKey:@"reportURL"];
        return study && ![[study valueForKey:@"lockedStudy"] boolValue] &&
            report.length && [[NSFileManager defaultManager] fileExistsAtPath:report] &&
            [HorosReportImageInsertion kindOfReportPath:report] != HorosReportImageKindUnsupported;
    }
#ifdef EXPORTTOOLBARITEM
    return YES;
#endif
    
    BOOL containsDistantStudy = NO;
    
    if( [[databaseOutline selectedRowIndexes] count] > 0)
    {
        NSUInteger idx = databaseOutline.selectedRowIndexes.firstIndex;
        
        while (idx != NSNotFound)
        {
            id object = [databaseOutline itemAtRow: idx];
            
            if( [object isDistant])
            {
                containsDistantStudy = YES;
                break;
            }
            
            idx = [databaseOutline.selectedRowIndexes indexGreaterThanIndex: idx];
        }
    }
    
    if( [[databaseOutline selectedRowIndexes] count] < 1 || containsDistantStudy == YES) // No Database Selection or Distant Study
    {
        if( containsDistantStudy == YES && [menuItem action] == @selector(querySelectedStudy:))
            return YES;
        
        if(	[menuItem action] == @selector(rebuildThumbnails:) ||
           [menuItem action] == @selector(searchForCurrentPatient:) ||
           [menuItem action] == @selector(viewerDICOM:) ||
           [menuItem action] == @selector(MovieViewerDICOM:) ||
           [menuItem action] == @selector(viewerDICOMMergeSelection:) ||
           [menuItem action] == @selector(revealInFinder:) ||
           [menuItem action] == @selector(export2PACS:) ||
           [menuItem action] == @selector(exportQuicktime:) ||
           [menuItem action] == @selector(exportJPEG:) ||
           [menuItem action] == @selector(exportTIFF:) ||
           [menuItem action] == @selector(exportDICOMFile:) ||
           [menuItem action] == @selector(sendMail:) ||
           [menuItem action] == @selector(addStudiesToUser:) ||
           [menuItem action] == @selector(sendEmailNotification:) ||
           [menuItem action] == @selector(compressSelectedFiles:) ||
           [menuItem action] == @selector(decompressSelectedFiles:) ||
           [menuItem action] == @selector(generateReport:) ||
           [menuItem action] == @selector(deleteReport:) ||
           [menuItem action] == @selector(convertReportToPDF:) ||
           [menuItem action] == @selector(convertReportToDICOMSR:) ||
           [menuItem action] == @selector(delItem:) ||
           [menuItem action] == @selector(querySelectedStudy:) ||
           [menuItem action] == @selector(burnDICOM:) ||
           [menuItem action] == @selector(anonymizeDICOM:) ||
           [menuItem action] == @selector(viewXML:) ||
           [menuItem action] == @selector(applyRoutingRule:) ||
           [menuItem action] == @selector(regenerateAutoComments:) ||
           [menuItem action] == @selector(unifyStudies:) ||
           [menuItem action] == @selector(viewerSubSeriesDICOM:) ||
           [menuItem action] == @selector(viewerReparsedSeries:) ||
           [menuItem action] == @selector(copyToDBFolder:)
           )
            return NO;
    }
    
    if( [[databaseOutline selectedRowIndexes] count] < 1 || containsDistantStudy == NO)
    {
        if(	[menuItem action] == @selector(retrieveSelectedPODStudies:))
            return NO;
    }
    
    if ([_database isReadOnly])
    {
        if([menuItem action] == @selector(compressSelectedFiles:) ||
           [menuItem action] == @selector(decompressSelectedFiles:) ||
           [menuItem action] == @selector(generateReport:) ||
           [menuItem action] == @selector(deleteReport:) ||
           [menuItem action] == @selector(convertReportToPDF:) ||
           [menuItem action] == @selector(convertReportToDICOMSR:) ||
           [menuItem action] == @selector(delItem:) ||
           [menuItem action] == @selector(regenerateAutoComments:) ||
           [menuItem action] == @selector(copyToDBFolder:) ||
           [menuItem action] == @selector(querySelectedStudy:) ||
           [menuItem action] == @selector(unifyStudies:) ||
           [menuItem action] == @selector(retrieveSelectedPODStudies:))
            return NO;
    }
    
    if ([_database isLocal] == NO)
    {
        if( [menuItem action] == @selector(deleteAlbum:) ||
           [menuItem action] == @selector(addAlbum:) ||
           [menuItem action] == @selector(addSmartAlbum:) ||
           [menuItem action] == @selector(addAlbums:) ||
           [menuItem action] == @selector(defaultAlbums:))
            return NO;
        
        if( [menuItem action] == @selector(selectFilesAndFoldersToAdd:) ||
           [menuItem action] == @selector(addURLToDatabase:) ||
           [menuItem action] == @selector(importRawData:))
            return NO;
        
        if( [menuItem action] == @selector(anonymizeDICOM:))
            return NO;
        
        if( [menuItem action] == @selector(compressSelectedFiles:) ||
           [menuItem action] == @selector(decompressSelectedFiles:))
            return NO;
    }
    
    if( [menuItem action] == @selector(convertReportToPDF:) || [menuItem action] == @selector(convertReportToDICOMSR:))
    {
        id item = [databaseOutline itemAtRow: [[databaseOutline selectedRowIndexes] firstIndex]];
        
        if( item)
        {
            DicomStudy *studySelected;
            
            if ([[item valueForKey: @"type"] isEqualToString:@"Study"])
                studySelected = (DicomStudy*) item;
            else
                studySelected = [item valueForKey:@"study"];
            
            if( [studySelected valueForKey:@"reportURL"] == nil)
                return NO;
        }
    }
    else if( menuItem.menu == imageTileMenu)
    {
        return [[[NSApp mainWindow] windowController] isKindOfClass:[ViewerController class]];
    }
    else if( [menuItem action] == @selector(unifyStudies:))
    {
        if (![_database isLocal]) return NO;
        
        if( [[databaseOutline selectedRowIndexes] count] <= 1) return NO;
        
        return YES;
    }
    else if( [menuItem action] == @selector(regenerateAutoComments:))
    {
        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"COMMENTSAUTOFILL"]) return YES;
        else return NO;
    }
    else if( [menuItem action] == @selector(viewerDICOMROIsImages:))
    {
        if( containsDistantStudy)
            return NO;
        
        if ([_database isLocal])
        {
            if( [[databaseOutline selectedRowIndexes] count] < 10 && [[self ROIImages: menuItem] count] == 0) return NO;
        }
        else return YES;
    }
    else if( [menuItem action] == @selector(viewerKeyImagesAndROIsImages:))
    {
        if( containsDistantStudy)
            return NO;
        
        if ([_database isLocal])
        {
            if( [[databaseOutline selectedRowIndexes] count] < 10 && [[self ROIsAndKeyImages: menuItem] count] == 0) return NO;
        }
        else return YES;
    }
    else if( [menuItem action] == @selector(exportROIAndKeyImagesAsDICOMSeries:))
    {
        if( containsDistantStudy)
            return NO;
        
        if ([_database isLocal])
        {
            if( [[databaseOutline selectedRowIndexes] count] < 10 && [[self ROIsAndKeyImages: menuItem] count] == 0) return NO;
        }
        else return YES;
    }
    else if( [menuItem action] == @selector(viewerDICOMKeyImages:))
    {
        if( containsDistantStudy)
            return NO;
        
        if ([_database isLocal])
        {
            if( [[databaseOutline selectedRowIndexes] count] < 10 && [[self KeyImages: menuItem] count] == 0) return NO;
        }
        else return YES;
    }
    else if( [menuItem action] == @selector(createROIsFromRTSTRUCT:))
    {
        if( containsDistantStudy)
            return NO;
        
        if (![_database isLocal])
            return NO;
    }
    else if( [menuItem action] == @selector(compressSelectedFiles:))
    {
        if( containsDistantStudy)
            return NO;
    }
    else if( [menuItem action] == @selector(decompressSelectedFiles:))
    {
        if( containsDistantStudy)
            return NO;
    }
    else if( [menuItem action] == @selector(copyToDBFolder:))
    {
        if( containsDistantStudy)
            return NO;
        
        if (![_database isLocal])
            return NO;
        
        if( [[databaseOutline selectedRowIndexes] count] < 10)
        {
            BOOL matrixThumbnails;
            
            if( menuItem.menu == contextual) matrixThumbnails = YES;
            else matrixThumbnails = NO;
            
            NSMutableArray *files, *objects = [NSMutableArray array];
            
            if( matrixThumbnails)
                files = [self filesForDatabaseMatrixSelection: objects onlyImages: NO];
            else
                files = [self filesForDatabaseOutlineSelection: objects onlyImages: NO];
            
            [files removeDuplicatedStringsInSyncWithThisArray: objects];
            
            for( NSManagedObject *im in objects)
            {
                if( [[im valueForKey: @"inDatabaseFolder"] boolValue] == NO)
                    return YES;
            }
            
            return NO;
        }
        else return YES;
    }
    else if( [menuItem action] == @selector(lockStudies:))
    {
        if( containsDistantStudy)
            return NO;
        
        NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
        
        for( NSInteger x = 0, row; x < selectedRows.count; x++)
        {
            if( x == 0) row = selectedRows.firstIndex;
            else row = [selectedRows indexGreaterThanIndex: row];
            
            NSManagedObject	*object = [databaseOutline itemAtRow: row];
            
            if( [[object valueForKey:@"type"] isEqualToString: @"Study"] && [[object valueForKey: @"lockedStudy"] boolValue] == NO)
                return YES;
        }
        
        return NO;
    }
    else if( [menuItem action] == @selector(unlockStudies:))
    {
        if( containsDistantStudy)
            return NO;
        
        NSIndexSet *selectedRows = [databaseOutline selectedRowIndexes];
        
        for( NSInteger x = 0, row; x < selectedRows.count; x++)
        {
            if( x == 0) row = selectedRows.firstIndex;
            else row = [selectedRows indexGreaterThanIndex: row];
            
            NSManagedObject	*object = [databaseOutline itemAtRow: row];
            
            if( [[object valueForKey:@"type"] isEqualToString: @"Study"] && [[object valueForKey: @"lockedStudy"] boolValue])
                return YES;
        }
        
        return NO;
    }
    else if( [menuItem action] == @selector(delItem:))
    {
        if( containsDistantStudy)
            return NO;
        
        if (![_database isLocal]) return NO;
        
        BOOL matrixThumbnails = YES;
        
        if( menuItem.menu == [oMatrix menu] || [[self window] firstResponder] == oMatrix)
            matrixThumbnails = YES;
        
        if( menuItem.menu == [databaseOutline menu] || [[self window] firstResponder] == databaseOutline || [[self window] firstResponder] == comparativeTable)
            matrixThumbnails = NO;
        
        if( matrixThumbnails)
            [menuItem setTitle: NSLocalizedString( @"Delete Selected Series Thumbnails", nil)];
        else
            [menuItem setTitle: NSLocalizedString( @"Delete Selected Lines", nil)];
    }
    else if( [menuItem action] == @selector(mergeStudies:))
    {
        if( containsDistantStudy)
            return NO;
        
        if (![_database isLocal]) return NO;
        
        NSIndexSet		*selectedRows = [databaseOutline selectedRowIndexes];
        BOOL	onlySeries = YES;
        
        NSInteger row = 0;
        for( NSInteger x = 0; x < [selectedRows count] ; x++)
        {
            row = ( x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex: row];
            NSManagedObject	*series = [databaseOutline itemAtRow: row];
            if( [[series valueForKey:@"type"] isEqualToString: @"Series"] == NO) onlySeries = NO;
        }
        
        if( onlySeries && [selectedRows count])
            [menuItem setTitle: NSLocalizedString( @"Merge Selected Series", nil)];
        else
            [menuItem setTitle: NSLocalizedString( @"Merge Selected Studies", nil)];
        
        if( [selectedRows count] > 1) return YES;
        else return NO;
    }
    else if( [menuItem action] == @selector(mergeSeries:))
    {
        if( containsDistantStudy)
            return NO;
        
        if (![_database isLocal]) return NO;
        
        if( [[oMatrix selectedCells] count] > 1) return YES;
        else return NO;
    }
    else if( [menuItem action] == @selector(annotMenu:))
    {
        if( [menuItem tag] == [[NSUserDefaults standardUserDefaults] integerForKey:@"ANNOTATIONS"]) [menuItem setState: NSControlStateValueOn];
        else [menuItem setState: NSControlStateValueOff];
    }
    return YES;
}

- (BOOL)is2DViewer
{
    return NO;
}

- (IBAction)customizeViewerToolBar:(id)sender
{
    [toolbar runCustomizationPalette:sender];
}

- (void)addHelpMenu
{
    NSMenu *mainMenu = [[NSApplication sharedApplication] mainMenu];
    NSMenuItem *helpItem = [mainMenu addItemWithTitle:NSLocalizedString(@"Help", nil) action:nil keyEquivalent:@""];
    NSMenu *helpMenu = [[NSMenu alloc] initWithTitle: NSLocalizedString(@"Help", nil)];
    [helpItem setSubmenu:helpMenu];
    
    [helpMenu addItemWithTitle: NSLocalizedString(@"Professional support", nil) action: @selector(openHorosSupport:) keyEquivalent: @""];
    [helpMenu addItemWithTitle: NSLocalizedString(@"Community support", nil) action: @selector(openCommunityPage:) keyEquivalent: @""];
    [helpMenu addItem: [NSMenuItem separatorItem]];
    [helpMenu addItemWithTitle: NSLocalizedString(@"Report a bug", nil) action: @selector(openBugReportPage:) keyEquivalent: @""];
    
    [helpMenu release];
}

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark DICOM Network & Files functions

- (void) resetListenerTimer // __deprecated
{
    [DicomDatabase syncImportFilesFromIncomingDirTimerWithUserDefaults];
}

- (void) saveDeleteQueue
{
    [deleteQueue lock];
    NSArray	*copyArray = [NSArray arrayWithArray: deleteQueueArray];
    [deleteQueueArray removeAllObjects];
    
    if( copyArray.count)
    {
        if( [[NSFileManager defaultManager] fileExistsAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"]])
        {
            NSArray *oldQueue = [NSArray arrayWithContentsOfFile: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"]];
            
            copyArray = [copyArray arrayByAddingObjectsFromArray: oldQueue];
            
            NSLog( @"---- old Delete Queue List found (%d files) add it to current queue.", (int) [oldQueue count]);
            
            [[NSFileManager defaultManager] removeItemAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] error: nil];
        }
        
        NSLog( @"---- save delete queue: %d objects", (int) [copyArray count]);
        
        [[NSFileManager defaultManager] removeItemAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] error: nil];
        [copyArray writeToFile: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] atomically: YES];
    }
    [deleteQueue unlock];
}

- (void) emptyDeleteQueueThread
{
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    
    [deleteInProgress lock];
    [deleteQueue lock];
    NSArray	*copyArray = [NSArray arrayWithArray: deleteQueueArray];
    [deleteQueueArray removeAllObjects];
    
    if( [[NSFileManager defaultManager] fileExistsAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"]])
    {
        NSArray *oldQueue = [NSArray arrayWithContentsOfFile: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"]];
        
        copyArray = [copyArray arrayByAddingObjectsFromArray: oldQueue];
        
        NSLog( @"---- old Delete Queue List found (%d files) add it to current queue.", (int) [oldQueue count]);
        
        [[NSFileManager defaultManager] removeItemAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] error: nil];
    }
    
    if( copyArray.count)
    {
        NSMutableArray *folders = [NSMutableArray array];
        
        NSLog( @"delete Queue start: %d objects", (int) [copyArray count]);
        
        [[NSFileManager defaultManager] removeItemAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] error: nil];
        [copyArray writeToFile: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] atomically: YES];
        
        [deleteQueue unlock];
        
        long f = 0;
        NSString *lastFolder = nil;
        NSTimeInterval date = 0;
        for( NSString *file in copyArray)
        {
            unlink( [file UTF8String]);		// <- this is faster
            
            NSString *parentFolder = [file stringByDeletingLastPathComponent];
            if( [lastFolder isEqualToString: parentFolder] == NO)
            {
                if( [folders containsObject: parentFolder] == NO)
                    [folders addObject: parentFolder];
                
                [lastFolder release];
                lastFolder = [[NSString alloc] initWithString: parentFolder];
            }
            
            if( [NSDate timeIntervalSinceReferenceDate] - date > 1)
            {
                date = [NSDate timeIntervalSinceReferenceDate];
                [NSThread currentThread].progress = (float)f / (float)[copyArray count];
                [NSThread currentThread].status = N2LocalizedSingularPluralCount( (long)copyArray.count-f, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
                
                if( [NSThread currentThread].isCancelled) //The queue is saved as a plist, we can continue later...
                    break;
            }
            f++;
        }
        [NSThread currentThread].progress = (float) f / (float) [copyArray count];
        [NSThread currentThread].status = N2LocalizedSingularPluralCount( [copyArray count]-f, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
        
        [lastFolder release];
        
        if( [NSThread currentThread].isCancelled == NO)
            [[NSFileManager defaultManager] removeItemAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] error: nil];
        
        [deleteInProgress unlock];
        
        [NSThread currentThread].status = NSLocalizedString(@"Cleaning database folders...", nil);
        [NSThread currentThread].progress = -1;
        
        @try
        {
            for( NSString *f in folders)
            {
                NSDictionary *fileAttributes = [[NSFileManager defaultManager] attributesOfItemAtPath: f error: NULL];
                
                if( [[fileAttributes objectForKey: NSFileType] isEqualToString: NSFileTypeDirectory])
                {
                    NSDate* dirCreationDate = [fileAttributes objectForKey:NSFileCreationDate];
                    if ((!dirCreationDate || -[dirCreationDate timeIntervalSinceNow] > 120) // if it has been created at least 2 minutes ago (or if we don't know)
                        && [[fileAttributes objectForKey: NSFileReferenceCount] intValue] < 4) // if it contains less than 3 files
                    { // check if this folder is empty, and delete it if necessary
                        int numberOfValidFiles = 0;
                        for( NSString *s in [[NSFileManager defaultManager] contentsOfDirectoryAtPath: f error: nil])
                        {
                            if( [[s lastPathComponent] characterAtIndex: 0] != '.')
                                numberOfValidFiles++;
                        }
                        
                        if( numberOfValidFiles == 0 && [[f lastPathComponent] isEqualToString: @"ROIs"] == NO)
                        {
                            NSLog( @"delete Queue: delete folder: %@", f);
                            [[NSFileManager defaultManager] removeItemAtPath: f error:NULL];
                            
                        }
                    }
                }
                
            }
        }
        @catch (NSException * e)
        {
            N2LogExceptionWithStackTrace(e);
        }
        
        NSLog(@"delete Queue end");
    }
    else {
        [deleteQueue unlock];
        [deleteInProgress unlock];
    }
    
    [pool release];
}

- (void) emptyDeleteQueueNow: (id) sender
{
    [deleteInProgress lock];
    [deleteInProgress unlock];
    
    [self emptyDeleteQueueThread];
    
    [deleteInProgress lock];
    [deleteInProgress unlock];
}

- (void) emptyDeleteQueue: (id)sender
{
    if( [[AppController sharedAppController] isSessionInactive] || waitForRunningProcess) return;
    
    // Check for the errors generated by the Q&R DICOM functions -- see dcmqrsrv.mm
    
    NSString *str = [NSString stringWithContentsOfFile: [[[NSFileManager defaultManager] tmpDirPath] stringByAppendingPathComponent: @"error_message"] usedEncoding:NULL error:NULL];
    if( str)
    {
        [[NSFileManager defaultManager] removeItemAtPath: [[[NSFileManager defaultManager] tmpDirPath] stringByAppendingPathComponent: @"error_message"] error:NULL];
        
        NSString *alertSuppress = @"hideListenerError";
        if ([[NSUserDefaults standardUserDefaults] boolForKey: alertSuppress] == NO)
        {
            NSAlert* alert = [[NSAlert new] autorelease];
            [alert setMessageText: NSLocalizedString( @"DICOM Network Error", nil)];
            [alert setInformativeText: str];
            [alert setShowsSuppressionButton:YES ];
            [alert addButtonWithTitle: NSLocalizedString(@"OK", nil)];
            
            if ([[alert suppressionButton] state] == NSControlStateValueOn)
                [[NSUserDefaults standardUserDefaults] setBool:YES forKey:alertSuppress];
        }
        else
            NSLog( @"*** DICOM Network Error (not displayed - hideListenerError): %@", str);
    }
    
    //////////////////////////////////////////////////
    
    if( deleteQueueArray == nil) deleteQueueArray = [[NSMutableArray array] retain];
    if( deleteQueue == nil) deleteQueue = [[NSRecursiveLock alloc] init];
    if( deleteInProgress == nil) deleteInProgress = [[NSRecursiveLock alloc] init];
    
    if( [deleteInProgress tryLock])
    {
        if( [[NSFileManager defaultManager] fileExistsAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"]])
        {
            NSArray *oldQueue = [NSArray arrayWithContentsOfFile: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"]];
            
            NSLog( @"---- old Delete Queue List found (%d files) add it to current queue.", (int) [oldQueue count]);
            [[NSFileManager defaultManager] removeItemAtPath: [[self.database baseDirPath] stringByAppendingPathComponent: @"DeleteQueueFile.plist"] error: nil];
            
            [deleteQueue lock];
            
            @try
            {
                [deleteQueueArray addObjectsFromArray: oldQueue];
            }
            @catch (NSException *e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            
            [deleteQueue unlock];
        }
        [deleteInProgress unlock];
    }
    
    if( [deleteQueueArray count] > 0)
    {
        if( [deleteInProgress tryLock])
        {
            [deleteInProgress unlock];
            
            NSThread *t = [[[NSThread alloc] initWithTarget:self selector:@selector(emptyDeleteQueueThread) object:  nil] autorelease];
            t.name = NSLocalizedString( @"Deleting files...", nil);
            t.status = N2LocalizedSingularPluralCount(deleteQueueArray.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
            t.progress = 0;
            t.supportsCancel = YES;
            [[ThreadsManager defaultManager] addThreadAndStart: t];
        }
    }
    
    if( self.database.managedObjectContext.deletedObjects.count)
    {
        NSLog( @"---- self.database.managedObjectContext.deletedObjects.count (%d) > 0 -> save db", (int) self.database.managedObjectContext.deletedObjects.count);
        [self.database save];
    }
}

- (void)addFileToDeleteQueue: (NSString*)file
{
    if( deleteQueueArray == nil) deleteQueueArray = [[NSMutableArray array] retain];
    if( deleteQueue == nil) deleteQueue = [[NSRecursiveLock alloc] init];
    if( deleteInProgress == nil) deleteInProgress = [[NSRecursiveLock alloc] init];
    
    [deleteQueue lock];
    if( file)
        [deleteQueueArray addObject: file];
    [deleteQueue unlock];
}

+ (NSString*)_findFirstDicomdirOnCDMedia: (NSString*)startDirectory // __deprecated
{
    return [self findFirstDicomdirInFolder:startDirectory];
}

+ (NSString*)findFirstDicomdirInFolder:(NSString*)startDirectory
{
    @try {
        return [DicomDatabase _findDicomdirIn:[startDirectory stringsByAppendingPaths:[[[NSFileManager defaultManager] enumeratorAtPath:startDirectory filesOnly:YES] allObjects]]];
    }
    @catch (NSException *e) {
        N2LogException( e);
    }
    
    return nil;
}

+ (BOOL) unzipFile: (NSString*) file withPassword: (NSString*) pass destination: (NSString*) destination
{
    return [BrowserController unzipFile:  file withPassword:  pass destination:  destination showGUI: YES];
}

+ (BOOL) unzipFile: (NSString*) file withPassword: (NSString*) pass destination: (NSString*) destination showGUI: (BOOL) showGUI
{
    [[NSFileManager defaultManager] removeItemAtPath: destination error:NULL];
    
    NSTask *t;
    NSArray *args;
    WaitRendering *wait = nil;
    
    if( [NSThread isMainThread] && showGUI == YES)
    {
        wait = [[WaitRendering alloc] init: NSLocalizedString(@"Decompressing the files...", nil)];
        [wait showWindow:self];
    }
    
    t = [[[NSTask alloc] init] autorelease];
    
    @try
    {
        [t setLaunchPath: @"/usr/bin/unzip"];
        
        [t setCurrentDirectoryPath: [[NSFileManager defaultManager] tmpDirPath]];
        if( pass)
            args = [NSArray arrayWithObjects: @"-qq", @"-o", @"-d", destination, @"-P", pass, file, nil];
        else
            args = [NSArray arrayWithObjects: @"-qq", @"-o", @"-d", destination, file, nil];
        [t setArguments: args];
        [t launch];
        while( [t isRunning])
            [NSThread sleepForTimeInterval: 0.1];
        
        //[t waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
    }
    @catch ( NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    [wait close];
    [wait autorelease];
    
    BOOL fileExist = NO;
    
    NSDirectoryEnumerator *dirEnum = [[NSFileManager defaultManager] enumeratorAtPath: destination];
    NSString *item = nil;
    while( item = [dirEnum nextObject])
    {
        BOOL isDirectory;
        if( [[NSFileManager defaultManager] fileExistsAtPath: [destination stringByAppendingPathComponent: item] isDirectory: &isDirectory])
        {
            if( isDirectory == NO && [[[[NSFileManager defaultManager] attributesOfItemAtPath: [destination stringByAppendingPathComponent: item] error: nil] valueForKey: NSFileSize] longLongValue] > 0)
            {
                fileExist = YES;
                break;
            }
        }
    }
    
    if( fileExist)
    {
        // Is it on writable media? Ask if the user want to delete the original file?
        
        if( [NSThread isMainThread] && [[NSFileManager defaultManager] isWritableFileAtPath: file] && showGUI == YES)
        {
            if ([[NSUserDefaults standardUserDefaults] boolForKey: @"HideZIPSuppressionMessage"] == NO)
            {
                NSAlert* alert = [[NSAlert new] autorelease];
                [alert setMessageText: NSLocalizedString(@"Delete ZIP file", nil)];
                [alert setInformativeText: NSLocalizedString(@"The ZIP file was successfully decompressed and the images successfully incorporated in Isis DICOM Viewer database. Should I delete the ZIP file?", nil)];
                [alert setShowsSuppressionButton: YES];
                [alert addButtonWithTitle: NSLocalizedString( @"Yes", nil)];
                [alert addButtonWithTitle: NSLocalizedString( @"No", nil)];
                int result = [alert runModal];
                
                if( result == NSAlertFirstButtonReturn)
                    [[NSUserDefaults standardUserDefaults] setBool: YES forKey: @"deleteZIPfile"];
                else
                    [[NSUserDefaults standardUserDefaults] setBool: NO forKey: @"deleteZIPfile"];
                
                if ([[alert suppressionButton] state] == NSControlStateValueOn)
                    [[NSUserDefaults standardUserDefaults] setBool:YES forKey: @"HideZIPSuppressionMessage"];
            }
            
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"deleteZIPfile"])
                [[NSFileManager defaultManager] removeItemAtPath: file error: nil];
        }
        return YES;
    }
    
    return NO;
}

- (int) askForZIPPassword: (NSString*) file destination: (NSString*) destination
{
    // first, try without password
    int result = 0;
    
    if( [BrowserController unzipFile: file withPassword: nil destination: destination] == NO)
    {
        self.pathToEncryptedFile = [NSString stringWithFormat: NSLocalizedString( @"File: %@", nil), file];
        self.CDpassword = @"";
        do
        {
            [self.window beginSheet:CDpasswordWindow completionHandler:nil];
            
            result = [NSApp runModalForWindow: CDpasswordWindow];
            [CDpasswordWindow makeFirstResponder: nil];
            
            [CDpasswordWindow.sheetParent endSheet:CDpasswordWindow];
            [CDpasswordWindow orderOut: self];
        }
        while( result == NSModalResponseStop && [BrowserController unzipFile: file withPassword: self.CDpassword destination: destination] == NO);
    }
    else
        result = NSModalResponseStop;
    
    return result;
}

-(void) ReadDicomCDRom:(id) sender
{
    // TODO: something
}

+(BOOL) isItCD:(NSString*) path
{
    NSArray *pathFilesComponent = [path pathComponents];
    
    if( [pathFilesComponent count] > 2 && [[[pathFilesComponent objectAtIndex: 1] uppercaseString] isEqualToString:@"VOLUMES"])
    {
        NSArray *removeableMedia = [[NSFileManager defaultManager] mountedVolumeURLsIncludingResourceValuesForKeys:@[NSURLVolumeIsRemovableKey] options:0];
        
        for( NSURL *mediaURL in removeableMedia)
        {
            NSString *mediaPath = mediaURL.path;
            if( [[mediaPath commonPrefixWithString: path options: NSCaseInsensitiveSearch] isEqualToString: mediaPath])
            {
                BOOL hasDICOMDIR = NO;
                NSNumber *isRemovable = nil;
                [mediaURL getResourceValue:&isRemovable forKey:NSURLVolumeIsRemovableKey error:nil];
                if( isRemovable.boolValue)
                {
                    // has encryptedDICOM.zip ?
                    {
                        NSString *aPath = mediaPath;
                        NSDirectoryEnumerator *enumer = [[NSFileManager defaultManager] enumeratorAtPath:aPath];
                        
                        if( enumer == nil)
                            aPath = [NSString stringWithFormat:@"/Volumes/Untitled"];
                        
                        for( NSString *p in [[NSFileManager defaultManager] contentsOfDirectoryAtPath: aPath error: nil])
                        {
                            if( [[p lastPathComponent] isEqualToString: @"encryptedDICOM.zip"]) // See BurnerWindowController
                            {
                                return YES;
                            }
                        }
                    }
                    
                    // hasDICOMDIR ?
                    {
                        NSString *aPath = mediaPath;
                        NSDirectoryEnumerator *enumer = [[NSFileManager defaultManager] enumeratorAtPath:aPath];
                        
                        if( enumer == nil)
                            aPath = [NSString stringWithFormat:@"/Volumes/Untitled"];
                        
                        DicomDirScanDepth = 0;
                        aPath = [BrowserController findFirstDicomdirInFolder: aPath];
                        
                        if( [[NSFileManager defaultManager] fileExistsAtPath:aPath])
                            hasDICOMDIR = YES;
                        
                        if(  hasDICOMDIR == YES)
                            return YES;
                    }
                }
            }
        }
    }
    return NO;
}

//- (void)listenerAnonymizeFiles: (NSArray*)files
//{
//	#ifndef OSIRIX_LIGHT
//	NSArray				*array = [NSArray arrayWithObjects: [DCMAttributeTag tagWithName:@"PatientsName"], @"**anonymized**", [DCMAttributeTag tagWithName:@"PatientID"], @"00000",nil];
//	NSMutableArray		*tags = [NSMutableArray array];
//
//	[tags addObject:array];
//
//	for( NSString *file in files)
//	{
//		NSString *destPath = [file stringByAppendingString:@"temp"];
//
//		@try
//		{
//			[DCMObject anonymizeContentsOfFile: file  tags:tags  writingToFile:destPath];
//		}
//		@catch (NSException * e)
//		{
//            N2LogExceptionWithStackTrace(e);
//		}
//
//		[[NSFileManager defaultManager] removeItemAtPath: file error:NULL];
//		[[NSFileManager defaultManager] movePath:destPath toPath: file handler: nil];
//	}
//#endif
//}

#pragma deprecated (pathResolved:)
- (NSString*) pathResolved:(NSString*) inPath
{
    return HorosBrowserAliasDestination(inPath);
}

#pragma deprecated (isAliasPath:)
- (BOOL) isAliasPath:(NSString *)inPath
{
    return HorosBrowserAliasDestination(inPath) != nil;
}

#pragma deprecated (resolveAliasPath:)
- (NSString*) resolveAliasPath:(NSString*)inPath
{
    NSString* resolved = HorosBrowserAliasDestination(inPath);
    return resolved ? resolved : inPath;
}

- (NSString *)folderPathResolvingAliasAndSymLink:(NSString *)path // __deprecated
{
    NSString *folder = path;
    
    if (![[NSFileManager defaultManager] fileExistsAtPath:path])
    {
        NSString* temp = [self pathResolved:path];
        if (!temp)
            [[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
        else
        {
            folder = temp;
        }
    }
    /*
     if it exists see if it is a file or symbolic link
     if it is a file, create a folder else leave it
     */
    else
    {
        NSDictionary *attrs = [[NSFileManager defaultManager] fileAttributesAtPath:path traverseLink:YES];
        
        if (![[attrs objectForKey:NSFileType] isEqualToString:NSFileTypeDirectory])
            [[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
        
        attrs = [[NSFileManager defaultManager] fileAttributesAtPath:path traverseLink:NO];
        
        //get absolute path if link
        if( [[attrs objectForKey:NSFileType] isEqualToString:NSFileTypeSymbolicLink])
            folder = [[NSFileManager defaultManager] pathContentOfSymbolicLinkAtPath:path];
        
        if( [self pathResolved: path])
            folder = [self pathResolved: path];
    }
    return folder;
}

- (IBAction)revealInFinder: (id)sender
{
    NSMutableArray *dicomFiles2Export = [NSMutableArray array];
    NSMutableArray *filesToExport;
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
    {
        filesToExport = [self filesForDatabaseMatrixSelection: dicomFiles2Export];
    }
    else filesToExport = [self filesForDatabaseOutlineSelection: dicomFiles2Export];
    
    if( [filesToExport count])
    {
        [[NSWorkspace sharedWorkspace] selectFile:filesToExport.firstObject inFileViewerRootedAtPath:[filesToExport.firstObject stringByDeletingLastPathComponent]];
    }
}

static volatile int numberOfThreadsForJPEG = 0;

- (BOOL) waitForAProcessor
{
    int processors =  [[NSProcessInfo processInfo] processorCount];
    
    if( processors < 1)
        processors = 1;
    
    [processorsLock lockWhenCondition: 1];
    BOOL result = numberOfThreadsForJPEG >= processors;
    if( result == NO)
    {
        numberOfThreadsForJPEG++;
        if( numberOfThreadsForJPEG >= processors)
        {
            [processorsLock unlockWithCondition: 0];
        }
        else
        {
            [processorsLock unlockWithCondition: 1];
        }
    }
    else
    {
        NSLog( @"waitForAProcessor ?? We should not be here...");
        [processorsLock unlockWithCondition: 0];
    }
    
    return result;
}

// Always modify this function in sync with compressionForModality in Decompress.mm / BrowserController.m
+ (int) compressionForModality: (NSString*) mod quality:(int*) quality resolution: (int) resolution
{
    NSArray *array;
    if( resolution < [[NSUserDefaults standardUserDefaults] integerForKey: @"CompressionResolutionLimit"])
        array = [[NSUserDefaults standardUserDefaults] arrayForKey: @"CompressionSettingsLowRes"];
    else
        array = [[NSUserDefaults standardUserDefaults] arrayForKey: @"CompressionSettings"];
    
    if( [mod isEqualToString: @"SR"]) // No compression for DICOM SR
        return compression_none;
    
    for( NSDictionary *dict in array)
    {
        if( [mod rangeOfString: [dict valueForKey: @"modality"]].location != NSNotFound)
        {
            int compression = compression_none;
            if( [[dict valueForKey: @"compression"] intValue] == compression_sameAsDefault)
                dict = [array objectAtIndex: 0];
            
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
    
    if( [array count] == 0)
        return compression_none;
    
    if( quality)
        *quality = [[[array objectAtIndex: 0] valueForKey: @"quality"] intValue];
    
    return [[[array objectAtIndex: 0] valueForKey: @"compression"] intValue];
}

#ifndef OSIRIX_LIGHT

#pragma deprecated(decompressDICOMJPEGinINCOMING:)
- (void)decompressDICOMJPEGinINCOMING:(NSArray*)array // __deprecated
{
    [_database decompressFilesAtPaths:array intoDirAtPath:_database.incomingDirPath];
}

- (void)decompressDICOMJPEG:(NSArray*)array // __deprecated
{
    [_database decompressFilesAtPaths:array intoDirAtPath:nil];
}

- (void)compressDICOMJPEGinINCOMING:(NSArray*)array // __deprecated
{
    [_database compressFilesAtPaths:array intoDirAtPath:_database.incomingDirPath];
}

- (void)compressDICOMJPEG:(NSArray*)array // __deprecated
{
    [_database compressFilesAtPaths:array];
}

- (void)decompressArrayOfFiles:(NSArray*)array work:(NSNumber*)work // __deprecated
{
    switch ([work charValue])
    {
        case 'C':
            [_database processFilesAtPaths: array intoDirAtPath: nil mode: Compress];
            break;
        case 'X':
            [_database processFilesAtPaths: array intoDirAtPath: [_database incomingDirPath] mode: Compress];
            break;
        case 'D':
            [_database processFilesAtPaths: array intoDirAtPath: nil mode: Decompress];
            break;
        case 'I':
            [_database processFilesAtPaths: array intoDirAtPath: [_database incomingDirPath] mode: Decompress];
            break;
    }
}

- (IBAction) compressSelectedFiles: (id)sender
{
    if( /*bonjourDownloading == NO &&*/ [_database isLocal])
    {
        NSMutableArray *dicomFiles2Export = [NSMutableArray array];
        NSMutableArray *filesToExport;
        
        if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
        {
            filesToExport = [self filesForDatabaseMatrixSelection: dicomFiles2Export];
        }
        else filesToExport = [self filesForDatabaseOutlineSelection: dicomFiles2Export];
        
        [filesToExport removeDuplicatedStringsInSyncWithThisArray: dicomFiles2Export];
        
        NSMutableArray *result = [NSMutableArray array];
        
        for( int i = 0 ; i < [filesToExport count] ; i++)
        {
            if( [[[dicomFiles2Export objectAtIndex:i] valueForKey:@"fileType"] hasPrefix:@"DICOM"])
                [result addObject: [filesToExport objectAtIndex: i]];
        }
        
        [DCMPix purgeCachedDictionaries];
        
        [_database initiateCompressFilesAtPaths:result];
    }
    else HorosRunInformationalAlertPanel(NSLocalizedString(@"Non-Local Database", nil), NSLocalizedString(@"Cannot compress images in a distant database.", nil), NSLocalizedString(@"OK",nil), nil, nil);
}

- (IBAction)decompressSelectedFiles: (id)sender
{
    if( /*bonjourDownloading == NO &&*/ [_database isLocal])
    {
        NSMutableArray *dicomFiles2Export = [NSMutableArray array];
        NSMutableArray *filesToExport;
        
        if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
        {
            filesToExport = [self filesForDatabaseMatrixSelection: dicomFiles2Export];
        }
        else filesToExport = [self filesForDatabaseOutlineSelection: dicomFiles2Export];
        
        [filesToExport removeDuplicatedStringsInSyncWithThisArray: dicomFiles2Export];
        
        NSMutableArray *result = [NSMutableArray array];
        
        for( int i = 0 ; i < [filesToExport count] ; i++)
        {
            if( [[[dicomFiles2Export objectAtIndex:i] valueForKey:@"fileType"] hasPrefix:@"DICOM"])
                [result addObject: [filesToExport objectAtIndex: i]];
        }
        
        [DCMPix purgeCachedDictionaries];
        
        [_database initiateDecompressFilesAtPaths:result];
    }
    else HorosRunInformationalAlertPanel(NSLocalizedString(@"Non-Local Database", nil), NSLocalizedString(@"Cannot decompress images in a distant database.", nil), NSLocalizedString(@"OK",nil), nil, nil);
}

#endif

- (void)checkIncomingThread: (id)sender // __deprecated
{
    [[DicomDatabase activeLocalDatabase] importFilesFromIncomingDir];
}

- (void) checkIncomingNow: (id) sender // __deprecated
{
    //	if( DatabaseIsEdited == YES && [[self window] isKeyWindow] == YES) return;
    [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
}

- (void)checkIncoming: (id)sender // __deprecated
{
    //	if( DatabaseIsEdited == YES && [[self window] isKeyWindow] == YES) return;
    [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
}

+ (void)writeMovieToPath:(NSString*)fileName images:(NSArray*)imagesArray framesPerSecond:(NSInteger)fps
{
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
    
    @try
    {
        if (fps <= 0)
            fps = [[NSUserDefaults standardUserDefaults] integerForKey: @"quicktimeExportRateValue"];
        if (fps <= 0)
            fps = 10;
        
        CMTimeValue timeValue = 600 / fps;
        CMTime frameDuration = CMTimeMake( timeValue, 600);
        
        NSError *error = nil;
        AVAssetWriter *writer = [[AVAssetWriter alloc] initWithURL:[NSURL fileURLWithPath: fileName] fileType: AVFileTypeQuickTimeMovie error:&error];
        
        if (!error)
        {
            NSImage *im = [imagesArray lastObject];
            
            double bitsPerSecond = im.size.width * im.size.height * fps * 4;
            
            if( bitsPerSecond > 0)
            {
                NSDictionary *videoSettings = [NSDictionary dictionaryWithObjectsAndKeys:
                                               AVVideoCodecTypeH264, AVVideoCodecKey,
                                               [NSDictionary dictionaryWithObjectsAndKeys:
                                                [NSNumber numberWithDouble: bitsPerSecond], AVVideoAverageBitRateKey,
                                                [NSNumber numberWithInteger: 1], AVVideoMaxKeyFrameIntervalKey,
                                                nil], AVVideoCompressionPropertiesKey,
                                               [NSNumber numberWithInt: im.size.width], AVVideoWidthKey,
                                               [NSNumber numberWithInt: im.size.height], AVVideoHeightKey, nil];
                
                // Instanciate the AVAssetWriterInput
                AVAssetWriterInput *writerInput = [AVAssetWriterInput assetWriterInputWithMediaType:AVMediaTypeVideo outputSettings:videoSettings];
                
                if( writerInput == nil)
                    N2LogStackTrace( @"**** writerInput == nil : %@", videoSettings);
                
                // Instanciate the AVAssetWriterInputPixelBufferAdaptor to be connected to the writer input
                AVAssetWriterInputPixelBufferAdaptor *pixelBufferAdaptor = [AVAssetWriterInputPixelBufferAdaptor assetWriterInputPixelBufferAdaptorWithAssetWriterInput:writerInput sourcePixelBufferAttributes:nil];
                // Add the writer input to the writer and begin writing
                [writer addInput:writerInput];
                [writer startWriting];
                
                CMTime nextPresentationTimeStamp;
                
                nextPresentationTimeStamp = kCMTimeZero;
                
                [writer startSessionAtSourceTime:nextPresentationTimeStamp];
                
                for( NSImage *im in imagesArray)
                {
                    NSAutoreleasePool *pool = [NSAutoreleasePool new];
                    
                    CVPixelBufferRef buffer = nil;
                    
                    buffer = [QuicktimeExport CVPixelBufferFromNSImage: im];
                    
                    [pool release];
                    
                    if( buffer)
                    {
                        CVPixelBufferLockBaseAddress(buffer, 0);
                        while( writerInput && [writerInput isReadyForMoreMediaData] == NO)
                            [NSThread sleepForTimeInterval: 0.1];
                        [pixelBufferAdaptor appendPixelBuffer:buffer withPresentationTime:nextPresentationTimeStamp];
                        CVPixelBufferUnlockBaseAddress(buffer, 0);
                        CVPixelBufferRelease(buffer);
                        buffer = nil;
                        
                        nextPresentationTimeStamp = CMTimeAdd(nextPresentationTimeStamp, frameDuration);
                    }
                }
                [writerInput markAsFinished];
            }
            else
                N2LogStackTrace( @"********** bitsPerSecond == 0");
            
            dispatch_semaphore_t finished = dispatch_semaphore_create(0);
            [writer finishWritingWithCompletionHandler:^{ dispatch_semaphore_signal(finished); }];
            dispatch_semaphore_wait(finished, DISPATCH_TIME_FOREVER);
#if !OS_OBJECT_USE_OBJC
            dispatch_release(finished);
#endif
        }
    }
    @catch( NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [pool release];
    }
}

+ (void)writeMovieToPath:(NSString*)fileName images:(NSArray*)imagesArray {
    [self writeMovieToPath:fileName images:imagesArray framesPerSecond:0];
}

- (void)writeMovie:(NSArray*)imagesArray name:(NSString*)fileName
{
    [BrowserController writeMovieToPath:fileName images:imagesArray];
}

+(void)setPath:(NSString*)path relativeTo:(NSString*)dirPath forSeriesId:(int)seriesId kind:(NSString*)kind toSeriesPaths:(NSMutableDictionary*)seriesPaths
{
    
    if (seriesId == -1)
        NSLog(@"SeriesId %d", seriesId);
    
    if (seriesPaths)
    {
        NSNumber* seriesIdK = [NSNumber numberWithInt:seriesId];
        
        path = [path stringByReplacingCharactersInRange:dirPath.range withString:@""];
        if ([path characterAtIndex:0] == '/')
            path = [path stringByReplacingCharactersInRange:NSMakeRange(0,1) withString:@""];
        
        NSMutableDictionary* pathsForSeries = [seriesPaths objectForKey:seriesIdK];
        if (!pathsForSeries)
        {
            pathsForSeries = [NSMutableDictionary dictionary];
            [seriesPaths setObject:pathsForSeries forKey:seriesIdK];
        }
        
        [pathsForSeries setObject:path forKey:kind];
    }
}

+(void) exportQuicktime:(NSArray*)dicomFiles2Export :(NSString*)path :(BOOL)html :(BrowserController*)browser :(NSMutableDictionary*)seriesPaths
{
    Wait                *splash = nil;
    NSMutableArray		*imagesArray = [NSMutableArray array], *imagesArrayObjects = [NSMutableArray array];
    NSString			*tempPath, *previousPath = nil;
    long				previousSeries = -1;
    NSString			*previousStudy = @"", *previousPatientUID = @"", *previousSeriesInstanceUID = @"";
    BOOL				createHTML = html;
    
    NSMutableDictionary *htmlExportDictionary = [NSMutableDictionary dictionary];
    
    if([NSThread isMainThread])
        splash = [[Wait alloc] initWithString: NSLocalizedString(@"Export...", nil) :YES];
    
    [splash setCancel: YES];
    [splash showWindow: browser];
    [[splash progress] setMaxValue:[dicomFiles2Export count]];
    
    NSManagedObjectContext* managedObjectContext = NULL;
    if (dicomFiles2Export.count)
        managedObjectContext = [[dicomFiles2Export objectAtIndex:0] managedObjectContext];
    
    @try
    {
        int uniqueSeriesID = 0;
        BOOL first = YES;
        BOOL cineRateSet = NO;
        
        NSInteger fps = 10;
        
        for( DicomImage *curImage in dicomFiles2Export)
        {
            NSString *patientDirName = [curImage.series.study.name filenameString];
            
            tempPath = [path stringByAppendingPathComponent: patientDirName];
            
            NSMutableArray *htmlExportSeriesArray;
            if(![htmlExportDictionary objectForKey:curImage.series.study.name])
            {
                htmlExportSeriesArray = [NSMutableArray array];
                [htmlExportSeriesArray addObject:[curImage valueForKey: @"series"]];
                [htmlExportDictionary setObject:htmlExportSeriesArray forKey:[curImage valueForKeyPath: @"series.study.name"]];
            }
            else
            {
                htmlExportSeriesArray = [htmlExportDictionary objectForKey:[curImage valueForKeyPath: @"series.study.name"]];
                [htmlExportSeriesArray addObject:[curImage valueForKey: @"series"]];
            }
            
            // Find the PATIENT folder
            if (![[NSFileManager defaultManager] fileExistsAtPath:tempPath]) [[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:NULL];
            else
            {
                if( first)
                {
                    if( HorosRunInformationalAlertPanel( NSLocalizedString(@"Export", nil), NSLocalizedString(@"A folder already exists. Should I replace it? It will delete the entire content of this folder (%@)", nil), NSLocalizedString(@"Replace", nil), NSLocalizedString(@"Cancel", nil), nil, [tempPath lastPathComponent]) == HorosAlertDefaultResponse)
                    {
                        [[NSFileManager defaultManager] removeItemAtPath:tempPath error:NULL];
                        [[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:NULL];
                    }
                    else break;
                }
            }
            first = NO;
            
            tempPath = [tempPath stringByAppendingPathComponent: [[NSMutableString stringWithFormat: @"%@ - %@", [curImage valueForKeyPath: @"series.study.studyName"], [curImage valueForKeyPath: @"series.study.id"]] filenameString]];
            if( [[curImage valueForKeyPath: @"series.study.id"] isEqualToString: previousStudy] == NO || [[curImage valueForKeyPath: @"series.study.patientUID"] compare: previousPatientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] != NSOrderedSame)
            {
                previousPatientUID = [curImage valueForKeyPath: @"series.study.patientUID"];
                previousStudy = [curImage valueForKeyPath: @"series.study.id"];
                previousSeries = -1;
                uniqueSeriesID = 0;
                previousSeriesInstanceUID = @"";
            }
            
            // Find the STUDY folder
            if (![[NSFileManager defaultManager] fileExistsAtPath:tempPath])
                [[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:NULL];
            
            NSString *seriesName = [curImage.series.name filenameString];
            if( seriesName.length == 0)
                seriesName = @"series";
            
            NSMutableString *seriesStr = [NSMutableString stringWithString: seriesName];
            [BrowserController replaceNotAdmitted: seriesStr];
            
            tempPath = [tempPath stringByAppendingPathComponent: seriesStr ];
            tempPath = [tempPath stringByAppendingFormat: @"_%@", [curImage valueForKeyPath: @"series.id"]];
            
            
            if( previousSeries != [[curImage valueForKeyPath: @"series.id"] intValue] || [[curImage valueForKeyPath: @"series.seriesInstanceUID"] isEqualToString: previousSeriesInstanceUID] == NO)
            {
                previousSeriesInstanceUID = [curImage valueForKeyPath: @"series.seriesInstanceUID"];
                uniqueSeriesID++;
                
                // DONT FORGET TO MODIFY THE SAME FUNCTIONS AT THE END OF THIS LOOP !
                
                if( [imagesArray count])
                {
                    NSImage *lastImage = [imagesArray lastObject];
            id tempID = [lastImage bestRepresentationForRect:NSMakeRect(0, 0, lastImage.size.width, lastImage.size.height) context:nil hints:nil];
                    
                    if( [tempID isKindOfClass: [NSPDFImageRep class]])
                    {
                        NSString* fullPath = [previousPath stringByAppendingPathExtension: @"pdf"];
                        [[tempID PDFRepresentation] writeToFile:fullPath atomically: YES];
                        [BrowserController setPath:fullPath relativeTo:path forSeriesId:previousSeries kind:@"pdf" toSeriesPaths:seriesPaths];
                        [imagesArray removeAllObjects];
                        [imagesArrayObjects removeAllObjects];
                    }
                }
                
                if( [imagesArray count] > 1)
                {
                    int width, height;
                    [QTExportHTMLSummary getMovieWidth: &width height: &height imagesArray: imagesArrayObjects];
                    
                    for( int index = 0 ; index < [imagesArray count]; index++)
                    {
                        NSImage *im = [imagesArray objectAtIndex: index];
                        
                        if( width != 0 && height != 0)
                        {
                            if( (int) [im size].width != width || height != (int) [im size].height)
                            {
                                @autoreleasepool
                                {
                                    NSImage *newImage = [im imageByScalingProportionallyToSize:NSMakeSize( width, height)];
                                    if( newImage)
                                        [imagesArray replaceObjectAtIndex: index withObject: newImage];
                                    
                                }
                            }
                        }
                    }
                    
                    NSString* fullPath = [previousPath stringByAppendingPathExtension: @"mp4"];
                    [BrowserController writeMovieToPath:fullPath images:imagesArray];
                    [BrowserController setPath:fullPath relativeTo:path forSeriesId:previousSeries kind:@"mp4" toSeriesPaths:seriesPaths];
                }
                else if( [imagesArray count] == 1)
                {
                    NSArray *representations = [[imagesArray objectAtIndex: 0] representations];
                    NSData *bitmapData = [NSBitmapImageRep representationOfImageRepsInArray:representations usingType:NSBitmapImageFileTypeJPEG properties:[NSDictionary dictionaryWithObject:[NSDecimalNumber numberWithFloat:0.9] forKey:NSImageCompressionFactor]];
                    NSString* fullPath = [previousPath stringByAppendingPathExtension: @"jpg"];
                    [bitmapData writeToFile:fullPath atomically:YES];
                    [BrowserController setPath:fullPath relativeTo:path forSeriesId:previousSeries kind:@"jpg" toSeriesPaths:seriesPaths];
                }
                
                //
                if(createHTML)
                {
                    NSImage	*thumbnail = [[[NSImage alloc] initWithData: [curImage valueForKeyPath: @"series.thumbnail"]] autorelease];
                    
                    @try
                    {
                        if( thumbnail == nil)
                        {
                            if (browser)
                            {
                                [browser buildThumbnail: [curImage valueForKey: @"series"]];
                                thumbnail = [[[NSImage alloc] initWithData: [curImage valueForKeyPath: @"series.thumbnail"]] autorelease];
                            }
                            else
                            {
                                // TODO: write thumb on TMP, assign thumbnail to its filecontents, delete tmp file
                            }
                        }
                    }
                    @catch ( NSException *e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                    
                    if(!thumbnail)
                        thumbnail = [[[NSImage alloc] initWithContentsOfFile:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/Empty.tif"]] autorelease];
                    
                    if( thumbnail)
                    {
                        NSData *bitmapData = nil;
                        NSArray *representations = [thumbnail representations];
                        bitmapData = [NSBitmapImageRep representationOfImageRepsInArray:representations usingType:NSBitmapImageFileTypeJPEG properties:[NSDictionary dictionaryWithObject:[NSDecimalNumber numberWithFloat:0.9] forKey:NSImageCompressionFactor]];
                        NSString* fullPath = [[tempPath stringByAppendingFormat: @"_%d", uniqueSeriesID] stringByAppendingString:@"_thumb.jpg"];
                        [bitmapData writeToFile:fullPath atomically:YES];
                        [BrowserController setPath:fullPath relativeTo:path forSeriesId:[[curImage valueForKeyPath:@"series.id"] intValue] kind:@"thumb" toSeriesPaths:seriesPaths];
                    }
                }
                
                [imagesArrayObjects removeAllObjects];
                [imagesArray removeAllObjects];
                previousSeries = [[curImage valueForKeyPath: @"series.id"] intValue];
            }
            
            tempPath = [tempPath stringByAppendingFormat: @"_%d", uniqueSeriesID];
            previousPath = [NSString stringWithString: tempPath];
            
#ifndef OSIRIX_LIGHT
            if( [DCMAbstractSyntaxUID isPDF: [curImage valueForKeyPath: @"series.seriesSOPClassUID"]])
            {
                DCMObject *dcmObject = [HorosDCMTKObject objectWithContentsOfFile: [curImage valueForKey: @"completePath"]];
                
                @try
                {
                    if ([[dcmObject attributeValueWithName:@"SOPClassUID"] isEqualToString:[DCMAbstractSyntaxUID pdfStorageClassUID]])
                    {
                        NSData *pdfData = [dcmObject attributeValueWithName:@"EncapsulatedDocument"];
                        
                        if( pdfData)
                        {
                            NSImage *im = [[[NSImage alloc] initWithData: pdfData] autorelease];
                            
                            if( im)
                            {
                                [imagesArray addObject: im];
                                [imagesArrayObjects addObject: curImage];
                            }
                        }
                    }
                }
                @catch (NSException * e)
                {
                    N2LogExceptionWithStackTrace(e);
                }
            }
            else if( [DCMAbstractSyntaxUID isStructuredReport: [curImage valueForKeyPath: @"series.seriesSOPClassUID"]])
            {
                [[NSFileManager defaultManager] confirmDirectoryAtPath:[[[NSFileManager defaultManager] tmpDirPath] stringByAppendingPathComponent: @"dicomsr_osirix"]];
                
                NSString *htmlpath = [[[[[NSFileManager defaultManager] tmpDirPath] stringByAppendingPathComponent: @"dicomsr_osirix"] stringByAppendingPathComponent: [[curImage valueForKey: @"completePath"] lastPathComponent]] stringByAppendingPathExtension: @"xml"];
                
                if( [[NSFileManager defaultManager] fileExistsAtPath: htmlpath] == NO)
                {
                    NSTask *aTask = [[[NSTask alloc] init] autorelease];
                    [aTask setEnvironment:[NSDictionary dictionaryWithObject:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/dicom.dic"] forKey:@"DCMDICTPATH"]];
                    [aTask setLaunchPath: [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent: @"/dsr2html"]];
                    [aTask setArguments: [NSArray arrayWithObjects: @"+X1", @"--unknown-relationship", @"--ignore-constraints", @"--ignore-item-errors", @"--skip-invalid-items", [curImage valueForKey: @"completePath"], htmlpath, nil]];
                    [aTask launch];
                    while( [aTask isRunning])
                        [NSThread sleepForTimeInterval: 0.1];
                    
                    //[aTask waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
                    [aTask interrupt];
                }
                
                if( [[NSFileManager defaultManager] fileExistsAtPath: [htmlpath stringByAppendingPathExtension: @"pdf"]] == NO)
                {
                    if( [[NSFileManager defaultManager] fileExistsAtPath: [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/Decompress"]])
                    {
                        NSTask *aTask = [[[NSTask alloc] init] autorelease];
                        [aTask setLaunchPath: [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/Decompress"]];
                        [aTask setArguments: [NSArray arrayWithObjects: htmlpath, @"pdfFromURL", nil]];
                        [aTask launch];
                        NSTimeInterval start = [NSDate timeIntervalSinceReferenceDate];
                        while( [aTask isRunning] && [NSDate timeIntervalSinceReferenceDate] - start < 10)
                            [NSThread sleepForTimeInterval: 0.1];
                        
                        //[aTask waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
                        [aTask interrupt];
                    }
                }
                
                NSImage *im = [[[NSImage alloc] initWithData: [NSData dataWithContentsOfFile: [htmlpath stringByAppendingPathExtension: @"pdf"]]] autorelease];
                
                if( im)
                {
                    [imagesArray addObject: im];
                    [imagesArrayObjects addObject: curImage];
                }
            }
            else
#endif
            {
                @autoreleasepool
                {
                    @try
                    {
                        int frame = 0;
                        
                        if( [curImage valueForKey:@"frameID"])
                            frame = [[curImage valueForKey:@"frameID"] intValue];
                        
                        DCMPix* dcmPix = [[DCMPix alloc] initWithPath: [curImage valueForKey:@"completePathResolved"] :0 :1 :nil :frame :[[curImage valueForKeyPath:@"series.id"] intValue] isBonjour:browser.isCurrentDatabaseBonjour imageObj:curImage];
                        
                        if( dcmPix)
                        {
                            float curWW = 0;
                            float curWL = 0;
                            
                            if( [[curImage valueForKey:@"series"] valueForKey:@"windowWidth"])
                            {
                                curWW = [[[curImage valueForKey:@"series"] valueForKey:@"windowWidth"] floatValue];
                                curWL = [dcmPix calibratedWindowLevelForStoredLevel:[[[curImage valueForKey:@"series"] valueForKey:@"windowLevel"] floatValue]];
                            }
                            
                            if( curWW != 0 && curWW !=curWL)
                                [dcmPix checkImageAvailble :curWW :curWL];
                            else
                                [dcmPix checkImageAvailble :[dcmPix savedWW] :[dcmPix savedWL]];
                            
                            NSImage *im = [dcmPix image];
                            
                            if( im)
                            {
                                [imagesArray addObject: im];
                                [imagesArrayObjects addObject: curImage];
                                
                                if( cineRateSet == NO && [dcmPix cineRate])
                                {
                                    fps = [dcmPix cineRate];
                                }
                            }
                            
                            [dcmPix release];
                        }
                    }
                    @catch( NSException *e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                }
            }
            
            [splash incrementBy:1];
            
            if( [splash aborted]) break;
        }
        
        if( [imagesArray count])
        {
            NSImage *lastImage = [imagesArray lastObject];
            id tempID = [lastImage bestRepresentationForRect:NSMakeRect(0, 0, lastImage.size.width, lastImage.size.height) context:nil hints:nil];
            
            if( [tempID isKindOfClass: [NSPDFImageRep class]])
            {
                NSString* fullPath = [previousPath stringByAppendingPathExtension: @"pdf"];
                [[tempID PDFRepresentation] writeToFile:fullPath atomically: YES];
                [BrowserController setPath:fullPath relativeTo:path forSeriesId:previousSeries kind:@"pdf" toSeriesPaths:seriesPaths];
                [imagesArray removeAllObjects];
                [imagesArrayObjects removeAllObjects];
            }
        }
        
        if( [imagesArray count] > 1)
        {
            int width, height;
            [QTExportHTMLSummary getMovieWidth: &width height: &height imagesArray: imagesArrayObjects];
            
            for( int index = 0 ; index < [imagesArray count]; index++)
            {
                NSImage *im = [imagesArray objectAtIndex: index];
                
                if( width != 0 && height != 0)
                {
                    if( (int) [im size].width != width || height != (int) [im size].height)
                    {
                        @autoreleasepool
                        {
                            NSImage *newImage = [im imageByScalingProportionallyToSize:NSMakeSize( width, height)];
                            
                            if( newImage)
                                [imagesArray replaceObjectAtIndex: index withObject: newImage];
                        }
                    }
                }
            }
            
            NSString* fullPath = [previousPath stringByAppendingPathExtension:@"mp4"];
            [BrowserController writeMovieToPath:fullPath images:imagesArray framesPerSecond:fps];
            [BrowserController setPath:fullPath relativeTo:path forSeriesId:previousSeries kind:@"mp4" toSeriesPaths:seriesPaths];
        }
        else if( [imagesArray count] == 1)
        {
            NSArray *representations = [[imagesArray objectAtIndex: 0] representations];
            NSData *bitmapData = [NSBitmapImageRep representationOfImageRepsInArray:representations usingType:NSBitmapImageFileTypeJPEG properties:[NSDictionary dictionaryWithObject:[NSDecimalNumber numberWithFloat:0.9] forKey:NSImageCompressionFactor]];
            NSString* fullPath = [previousPath stringByAppendingPathExtension: @"jpg"];
            [bitmapData writeToFile:fullPath atomically:YES];
            [BrowserController setPath:fullPath relativeTo:path forSeriesId:previousSeries kind:@"jpg" toSeriesPaths:seriesPaths];
        }
        
        if( createHTML && imagesArray.count)
        {
            QTExportHTMLSummary *htmlExport = [[QTExportHTMLSummary alloc] init];
            [htmlExport setPatientsDictionary:htmlExportDictionary];
            [htmlExport setPath:path];
            [htmlExport createHTMLfiles];
            [htmlExport release];
        }
    }
    
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    @finally
    {
        [splash close];
        [splash autorelease];
    }
}

-(void) exportQuicktimeInt:(NSArray*) dicomFiles2Export :(NSString*) path :(BOOL) html
{
    [BrowserController exportQuicktime:dicomFiles2Export :path :html :self :NULL];
}

- (void)exportQuicktime: (id)sender
{
    NSOpenPanel *sPanel	= [NSOpenPanel openPanel];
    
    NSMutableArray *dicomFiles2Export = [NSMutableArray array];
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
        (void)[self filesForDatabaseMatrixSelection: dicomFiles2Export onlyImages: YES];
    else
        [self filesForDatabaseOutlineSelection: dicomFiles2Export onlyImages: YES];
    
    [sPanel setCanChooseDirectories:YES];
    [sPanel setCanChooseFiles:NO];
    [sPanel setAllowsMultipleSelection:NO];
    [sPanel setMessage: NSLocalizedString(@"Select the location where to export the Movie files:",nil)];
    [sPanel setPrompt: NSLocalizedString(@"Choose",nil)];
    [sPanel setTitle: NSLocalizedString(@"Export",nil)];
    [sPanel setCanCreateDirectories:YES];
    
    [sPanel setAccessoryView:exportQuicktimeView];
    
    if ([sPanel runModal] == NSModalResponseOK)
    {
        [self exportQuicktimeInt: dicomFiles2Export :sPanel.URL.path :[exportHTMLButton state]];
    }
}

- (void) exportImageAs:(NSString*) format sender:(id) sender
{
    NSOpenPanel			*sPanel			= [NSOpenPanel openPanel];
    long				previousSeries = -1;
    long				serieCount		= 0;
    
    NSMutableArray *dicomFiles2Export = [NSMutableArray array], *renameArray = [NSMutableArray array];
    NSMutableArray *filesToExport;
    NSMutableDictionary *seriesFolderAssignments = [NSMutableDictionary dictionary];
    NSMutableSet *reservedSeriesPaths = [NSMutableSet set];
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
    {
        filesToExport = [self filesForDatabaseMatrixSelection: dicomFiles2Export];
        NSLog(@"Files from contextual menu: %d", (int) [filesToExport count]);
    }
    else filesToExport = [self filesForDatabaseOutlineSelection: dicomFiles2Export];
    
    [sPanel setCanChooseDirectories:YES];
    [sPanel setCanChooseFiles:NO];
    [sPanel setAllowsMultipleSelection:NO];
    [sPanel setMessage: NSLocalizedString(@"Select the location where to export the image files:",nil)];
    [sPanel setPrompt: NSLocalizedString(@"Choose",nil)];
    [sPanel setTitle: NSLocalizedString(@"Export",nil)];
    [sPanel setCanCreateDirectories:YES];
    
    if ([sPanel runModal] == NSModalResponseOK)
    {
        NSString *dest, *path = sPanel.URL.path;
        Wait *splash = [[Wait alloc] initWithString:NSLocalizedString(@"Export...", nil) :YES];
        
        [splash setCancel:YES];
        [splash showWindow:self];
        [[splash progress] setMaxValue:[filesToExport count]];
        
        for( int i = 0; i < [filesToExport count]; i++)
        {
            @autoreleasepool
            {
            NSManagedObject	*curImage = [dicomFiles2Export objectAtIndex:i];
            NSString *extension = format;
            
            NSString *tempPath = [path stringByAppendingPathComponent:[curImage valueForKeyPath: @"series.study.name"]];
            
            // Find the PATIENT folder
            if (![[NSFileManager defaultManager] fileExistsAtPath:tempPath]) [[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:NULL];
            else
            {
                if( i == 0)
                {
                    if( HorosRunInformationalAlertPanel( NSLocalizedString(@"Export", nil), NSLocalizedString(@"A folder already exists. Should I replace it? It will delete the entire content of this folder (%@)", nil), NSLocalizedString(@"Replace", nil), NSLocalizedString(@"Cancel", nil), nil, [tempPath lastPathComponent]) == HorosAlertDefaultResponse)
                    {
                        [[NSFileManager defaultManager] removeItemAtPath:tempPath error:NULL];
                        [[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:NULL];
                    }
                    else break;
                }
            }
            
            tempPath = [tempPath stringByAppendingPathComponent: [BrowserController replaceNotAdmitted: [NSMutableString stringWithFormat: @"%@ - %@", [curImage valueForKeyPath: @"series.study.studyName"], [curImage valueForKeyPath: @"series.study.id"]]]];
            
            // Find the STUDY folder
            if (![[NSFileManager defaultManager] fileExistsAtPath:tempPath]) [[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:NULL];
            
            NSMutableString *seriesStr = [NSMutableString stringWithString: @"series"];
            if( [curImage valueForKeyPath: @"series.name"])
                seriesStr = [NSMutableString stringWithString: [curImage valueForKeyPath: @"series.name"]];
            
            [BrowserController replaceNotAdmitted:seriesStr];
            NSString *seriesFolder = HorosRasterSeriesFolder(seriesStr, [curImage valueForKeyPath:@"series.id"], tempPath,
                [curImage valueForKey:@"series"], seriesFolderAssignments, reservedSeriesPaths);
            tempPath = [tempPath stringByAppendingPathComponent:seriesFolder];
            
            // Find the SERIES folder
            if (![[NSFileManager defaultManager] fileExistsAtPath:tempPath]) [[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:NULL];
            
            long imageNo = [[curImage valueForKey:@"instanceNumber"] intValue];
            
            if( previousSeries != [[curImage valueForKeyPath: @"series.id"] intValue])
            {
                previousSeries = [[curImage valueForKeyPath: @"series.id"] intValue];
                serieCount++;
            }
            
            dest = [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, extension];
            
            int t = 2;
            while( [[NSFileManager defaultManager] fileExistsAtPath: dest])
            {
                dest = [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, t, extension];
                t++;
            }
            
            if( t != 2)
            {
                [renameArray addObject: [NSDictionary dictionaryWithObjectsAndKeys: [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, extension], @"oldName", [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, 1, extension], @"newName", nil]];
            }
            
            DCMPix* dcmPix = [[DCMPix alloc] initWithPath: [curImage valueForKey:@"completePathResolved"] :0 :1 :nil :[[curImage valueForKey:@"frameID"] intValue] :[[curImage valueForKeyPath:@"series.id"] intValue] isBonjour:![_database isLocal] imageObj:curImage];
            
            if( dcmPix)
            {
                float curWW = 0;
                float curWL = 0;
                
                if( [[curImage valueForKey:@"series"] valueForKey:@"windowWidth"])
                {
                    curWW = [[[curImage valueForKey:@"series"] valueForKey:@"windowWidth"] floatValue];
                    curWL = [dcmPix calibratedWindowLevelForStoredLevel:[[[curImage valueForKey:@"series"] valueForKey:@"windowLevel"] floatValue]];
                }
                
                if( curWW != 0 && curWW !=curWL)
                    [dcmPix checkImageAvailble :curWW :curWL];
                else
                    [dcmPix checkImageAvailble :[dcmPix savedWW] :[dcmPix savedWL]];
                
                if( [format isEqualToString:@"jpg"])
                {
                    NSArray *representations = [[dcmPix image] representations];
                    NSData *bitmapData = [NSBitmapImageRep representationOfImageRepsInArray:representations usingType:NSBitmapImageFileTypeJPEG properties:[NSDictionary dictionaryWithObject:[NSDecimalNumber numberWithFloat:0.9] forKey:NSImageCompressionFactor]];
                    [bitmapData writeToFile:dest atomically:YES];
                }
                else
                {
                    [[[dcmPix image] TIFFRepresentation] writeToFile:dest atomically:YES];
                }
                
                [dcmPix release];
            }
            
            [splash incrementBy:1];
            
            if( [splash aborted])
                i = [filesToExport count];
            } // Release decoded images and encoded data before the next file.
        }
        
        for( NSDictionary *d in renameArray)
            [[NSFileManager defaultManager] moveItemAtPath: [d objectForKey: @"oldName"] toPath: [d objectForKey: @"newName"] error: nil];
        
        //close progress window
        [splash close];
        [splash autorelease];
    }
}

- (void)exportJPEG: (id)sender
{
    [self exportImageAs: @"jpg" sender: sender];
}

- (void)exportTIFF: (id)sender
{
    [self exportImageAs: @"tif" sender: sender];
}

#ifndef OSIRIX_LIGHT

- (IBAction) addStudiesToUser: (id) sender
{
    [notificationEmailArrayController setSelectionIndexes: [NSIndexSet indexSet]];
    
    [self.window beginSheet:addStudiesToUserWindow completionHandler:nil];
    
    int result = [NSApp runModalForWindow: addStudiesToUserWindow];
    [addStudiesToUserWindow makeFirstResponder: nil];
    
    if( result == NSModalResponseStop)
    {
        if( [[notificationEmailArrayController selectedObjects] count] == 0)
        {
            HorosRunCriticalAlertPanel( NSLocalizedString( @"Error", nil), NSLocalizedString( @"No user(s) selected, no studies will be added.", nil), NSLocalizedString( @"OK", nil) , nil, nil);
        }
        else
        {
            // Add them to select users
            
            @try
            {
                for( NSManagedObject *user in [notificationEmailArrayController selectedObjects])
                {
                    NSArray *studiesArrayStudyInstanceUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"studyInstanceUID"];
                    NSArray *studiesArrayPatientUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"patientUID"];
                    
                    for( NSManagedObject *study in [self databaseSelection])
                    {
                        if( [[study valueForKey: @"type"] isEqualToString:@"Series"])
                            study = [study valueForKey:@"study"];
                        
                        if( [studiesArrayStudyInstanceUID indexOfObject: [study valueForKey: @"studyInstanceUID"]] == NSNotFound || [studiesArrayPatientUID
                                                                                                                                     indexOfObjectPassingTest:^(id obj, NSUInteger idx, BOOL *stop) { if( [obj compare: [study valueForKey: @"patientUID"] options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame) return YES; else return NO;}] == NSNotFound)
                        {
                            NSManagedObject *studyLink = [NSEntityDescription insertNewObjectForEntityForName: @"Study" inManagedObjectContext: user.managedObjectContext];
                            
                            [studyLink setValue: [[[study valueForKey: @"studyInstanceUID"] copy] autorelease] forKey: @"studyInstanceUID"];
                            [studyLink setValue: [[[study valueForKey: @"patientUID"] copy] autorelease] forKey: @"patientUID"];
                            
                            [studyLink setValue: user forKey: @"user"];
                            
                            @try
                            {
                                [[[WebPortal defaultWebPortal] database] save:nil];
                            }
                            @catch (NSException * e)
                            {
                                N2LogExceptionWithStackTrace(e);
                            }
                            
                            studiesArrayStudyInstanceUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"studyInstanceUID"];
                            studiesArrayPatientUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"patientUID"];
                            
                            [[WebPortal defaultWebPortal] updateLogEntryForStudy: study withMessage: @"Add Study to User" forUser: [user valueForKey: @"name"] ip: nil];
                        }
                    }
                }
            }
            @catch (NSException * e)
            {
                N2LogExceptionWithStackTrace(e);
            }
        }
    }
    
    [addStudiesToUserWindow.sheetParent endSheet:addStudiesToUserWindow];
    [addStudiesToUserWindow orderOut: self];
}

-(IBAction)sendEmailNotification:(id)sender
{
#ifndef OSIRIX_LIGHT
    self.temporaryNotificationEmail = @"";
    self.customTextNotificationEmail = @"";
    
    [notificationEmailArrayController setSelectionIndexes: [NSIndexSet indexSet]];
    
    [self.window beginSheet:notificationEmailWindow completionHandler:nil];
    
    int result;
restart:
    {
        result = [NSApp runModalForWindow: notificationEmailWindow];
    }
    
    [notificationEmailWindow makeFirstResponder: nil];
    
    if( result == NSModalResponseStop)
    {
        if( [[notificationEmailArrayController selectedObjects] count] == 0 && [temporaryNotificationEmail length] <= 3)
        {
            HorosRunCriticalAlertPanel( NSLocalizedString( @"Error", nil), NSLocalizedString( @"Select one or more users.", nil), NSLocalizedString( @"OK", nil) , nil, nil);
            goto restart;
        }
        else
        {
            @try
            {
                NSArray *destinationUsers = [notificationEmailArrayController selectedObjects];
                
                if( [temporaryNotificationEmail length] > 3)
                {
                    // First, create a temporary user
                    
                    if( [temporaryNotificationEmail rangeOfString: @"@"].location == NSNotFound)
                    {
                        HorosRunCriticalAlertPanel( NSLocalizedString( @"Error", nil), NSLocalizedString( @"Is the user email correct? the @ character is not found.", nil), NSLocalizedString( @"OK", nil) , nil, nil);
                        goto restart;
                    }
                    else
                    {
                        NSString *name = [temporaryNotificationEmail substringToIndex: [temporaryNotificationEmail rangeOfString: @"@"].location];
                        
                        if( [name length] < 2)
                        {
                            HorosRunCriticalAlertPanel( NSLocalizedString( @"Error", nil), NSLocalizedString( @"Name needs to be at least 2 characters.", nil), NSLocalizedString( @"OK", nil) , nil, nil);
                            goto restart;
                        }
                        else
                        {
                            // Swift returns the "new" family retained.
                            NSManagedObject *user = [[[WebPortal defaultWebPortal] newUserWithEmail:temporaryNotificationEmail] autorelease];
                            destinationUsers = [destinationUsers arrayByAddingObject: user];
                        }
                    }
                }
                
                @try
                {
                    // Add them to selected users AND send a notification email
                    if( [destinationUsers count] > 0)
                    {
                        for( NSManagedObject *user in destinationUsers)
                        {
                            NSArray *studiesArrayStudyInstanceUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"studyInstanceUID"];
                            NSArray *studiesArrayPatientUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"patientUID"];
                            
                            for( NSManagedObject *study in [self databaseSelection])
                            {
                                if( [[study valueForKey: @"type"] isEqualToString:@"Series"])
                                    study = [study valueForKey:@"study"];
                                
                                if( [studiesArrayStudyInstanceUID indexOfObject: [study valueForKey: @"studyInstanceUID"]] == NSNotFound ||
                                   [studiesArrayPatientUID indexOfObjectPassingTest:^(id obj, NSUInteger idx, BOOL *stop) { if( [obj compare: [study valueForKey: @"patientUID"] options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame) return YES; else return NO;}] == NSNotFound)
                                {
                                    NSManagedObject *studyLink = [NSEntityDescription insertNewObjectForEntityForName: @"Study" inManagedObjectContext: user.managedObjectContext];
                                    
                                    [studyLink setValue: [[[study valueForKey: @"studyInstanceUID"] copy] autorelease] forKey: @"studyInstanceUID"];
                                    [studyLink setValue: [[[study valueForKey: @"patientUID"] copy] autorelease] forKey: @"patientUID"];
                                    [studyLink setValue: [NSDate dateWithTimeIntervalSinceReferenceDate: [[NSUserDefaults standardUserDefaults] doubleForKey: @"lastNotificationsDate"]] forKey: @"dateAdded"];
                                    
                                    [studyLink setValue: user forKey: @"user"];
                                    
                                    @try
                                    {
                                        [[[WebPortal defaultWebPortal] database] save:nil];
                                    }
                                    @catch (NSException * e)
                                    {
                                        N2LogExceptionWithStackTrace(e);
                                    }
                                    
                                    studiesArrayStudyInstanceUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"studyInstanceUID"];
                                    studiesArrayPatientUID = [[[user valueForKey: @"studies"] allObjects] valueForKey: @"patientUID"];
                                    
                                    [[WebPortal defaultWebPortal] updateLogEntryForStudy: study withMessage: @"Add Study to User" forUser: [user valueForKey: @"name"] ip: nil];
                                }
                            }
                        }
                        
                        (void)[[WebPortal defaultWebPortal] sendNotificationsEmailsTo: destinationUsers aboutStudies: [self databaseSelection] predicate: nil customText: self.customTextNotificationEmail];
                    }
                }
                @catch( NSException *e)
                {
                    N2LogExceptionWithStackTrace(e);
                }
            }
            @catch( NSException *e)
            {
                N2LogExceptionWithStackTrace(e);
            }
        }
    }
    
    [notificationEmailWindow.sheetParent endSheet:notificationEmailWindow];
    [notificationEmailWindow orderOut: self];
#endif
}

-(IBAction)sendMail:(id)sender
{
#ifndef OSIRIX_LIGHT
    if( [AppController hasMacOSXSnowLeopard])
    {
        [[NSUserDefaults standardUserDefaults] setValue: @"" forKey:@"defaultZIPPasswordForEmail"];
        
    redoZIPpassword:
        
        [self.window beginSheet:ZIPpasswordWindow completionHandler:nil];
        
        int result = [NSApp runModalForWindow: ZIPpasswordWindow];
        [ZIPpasswordWindow makeFirstResponder: nil];
        
        [ZIPpasswordWindow.sheetParent endSheet:ZIPpasswordWindow];
        [ZIPpasswordWindow orderOut: self];
        
        if( result == NSModalResponseStop)
        {
            if( [(NSString*) [[NSUserDefaults standardUserDefaults] valueForKey: @"defaultZIPPasswordForEmail"] length] < 8)
            {
                NSBeep();
                goto redoZIPpassword;
            }
            
            NSMutableArray *dicomFiles2Export = [NSMutableArray array];
            NSMutableArray *filesToExport = [self filesForDatabaseOutlineSelection: dicomFiles2Export onlyImages: NO];
            
            NSString *emailDirectory = [NSTemporaryDirectory() stringByAppendingPathComponent:[@"horos-mail-" stringByAppendingString:NSUUID.UUID.UUIDString]];
            NSError *directoryError = nil;
            if( ![[NSFileManager defaultManager] createDirectoryAtPath:emailDirectory withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:&directoryError])
            {
                [self showDICOMExportError:directoryError];
                return;
            }
            
            BOOL encrypt = [[NSUserDefaults standardUserDefaults] boolForKey: @"encryptForExport"];
            
            [[NSUserDefaults standardUserDefaults] setBool: YES forKey: @"encryptForExport"];
            
            self.passwordForExportEncryption = [[NSUserDefaults standardUserDefaults] valueForKey: @"defaultZIPPasswordForEmail"];
            
            NSArray *r = [self exportDICOMFileInt: emailDirectory files: filesToExport objects: dicomFiles2Export];
            
            [[NSUserDefaults standardUserDefaults] setBool: encrypt forKey: @"encryptForExport"];
            
            if( [r count] > 0)
            {
                NSMutableArray *mailFilePaths = [NSMutableArray array];
                NSString *root = emailDirectory;
                NSArray *files = [[NSFileManager defaultManager] contentsOfDirectoryAtPath: root error: nil];
                for( int x = 0; x < [files count] ; x++)
                {
                    if( [[[files objectAtIndex: x] pathExtension] isEqualToString: @"zip"])
                    {
                        NSString *sourceArchive = [root stringByAppendingPathComponent:[files objectAtIndex:x]];
                        NSString *attachment = [root stringByAppendingPathComponent:[NSString stringWithFormat:@"Images-%@.zip", NSUUID.UUID.UUIDString]];
                        // The export clears passwordForExportEncryption after packaging.
                        NSError *attachmentError = nil;
                        if( ![BrowserController prepareProtectedEmailAttachment:sourceArchive destination:attachment password:[[NSUserDefaults standardUserDefaults] stringForKey:@"defaultZIPPasswordForEmail"] error:&attachmentError])
                        {
                            [self showDICOMExportError:attachmentError];
                            return;
                        }
                        if( ![sourceArchive isEqualToString:attachment])
                            [[NSFileManager defaultManager] removeItemAtPath:sourceArchive error:NULL];
                        [mailFilePaths addObject:attachment];
                    }
                }
                
                [HorosMailDraftComposer composeRecipientFreeDraftWithSubject:@"subject" filePaths:mailFilePaths completion:^(NSString *mailError) {
                    if (mailError)
                        HorosRunAlertPanel(NSLocalizedString(@"Email Export Failed", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil, mailError);
                }];
            }
        }
    }
    else if( [NSThread isMainThread]) HorosRunCriticalAlertPanel( NSLocalizedString( @"Unsupported", nil), NSLocalizedString( @"This function requires MacOS 10.6 or higher.", nil), NSLocalizedString( @"OK", nil) , nil, nil);
#endif
}

#endif

+ (NSMutableString*) replaceNotAdmitted: (NSString*)name
{
    return [self replaceNotAdmitted:name preserveHyphens:NO];
}

+ (NSMutableString*) replaceNotAdmitted:(NSString*)name preserveHyphens:(BOOL)preserveHyphens
{
    NSMutableString* mstr;
    // Foundation string cluster subclasses can report mutable ancestry even
    // for immutable instances. The coding class preserves their mutability.
    if ([[name classForCoder] isSubclassOfClass:[NSMutableString class]])
        mstr = (NSMutableString*) name;
    else
        mstr = [[name mutableCopy] autorelease];
    
    [mstr replaceOccurrencesOfString:@" " withString:@"_" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"." withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"," withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"^" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"/" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"\\" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"|" withString:@"" options:0 range:mstr.range];
    if( !preserveHyphens)
        [mstr replaceOccurrencesOfString:@"-" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@":" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"*" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"<" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@">" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"?" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"#" withString:@"" options:0 range:mstr.range];
    [mstr replaceOccurrencesOfString:@"%" withString:@"" options:0 range:mstr.range];
    
    return mstr;
}

#ifndef OSIRIX_LIGHT
- (void) importReport:(NSString*) path UID: (NSString*) uid
{
    NSError *error = nil;
    if (![self importReport:path UID:uid error:&error])
        NSLog(@"Report attachment failed: %@", error.localizedDescription);
}

- (BOOL) importReport:(NSString*) path UID:(NSString*) uid error:(NSError**) error
{
    if (!self.database.isLocal || self.database.isReadOnly || !path.length || !uid.length) {
        if (error) *error = [NSError errorWithDomain:@"HorosReportImport" code:1 userInfo:@{NSLocalizedDescriptionKey: NSLocalizedString(@"Choose a report and a study in a writable local database.", nil)}];
        return NO;
    }
    NSManagedObjectContext *context = self.database.managedObjectContext;
    __block BOOL saved = NO;
    N2ManagedObjectContextPerformAndWait(context, ^{
    NSString *destination = nil;
    NSString *previous = nil;
    DicomStudy *study = nil;
    BOOL associated = NO;
    @try {
        NSFetchRequest *request = [[[NSFetchRequest alloc] init] autorelease];
        [request setEntity:[[self.database.managedObjectModel entitiesByName] objectForKey:@"Study"]];
        [request setPredicate:[NSPredicate predicateWithFormat:@"studyInstanceUID == %@", uid]];
        NSArray *studies = [context executeFetchRequest:request error:error];
        if (!studies) return;
        if (studies.count != 1 || [[[studies firstObject] valueForKey:@"lockedStudy"] boolValue]) {
            if (error) *error = [NSError errorWithDomain:@"HorosReportImport" code:2 userInfo:@{NSLocalizedDescriptionKey: NSLocalizedString(@"The study is missing, ambiguous, or locked. Select one unlocked study.", nil)}];
            return;
        }
        study = [studies firstObject];
        previous = [[study valueForKey:@"reportURL"] copy];
        // A new name preserves the old document even if database saving fails.
        NSString *name = [@"Attached-" stringByAppendingString:NSUUID.UUID.UUIDString];
        if (path.pathExtension.length) name = [name stringByAppendingPathExtension:path.pathExtension];
        destination = [[self.database.reportsDirPath stringByAppendingPathComponent:name] copy];
        if (!HorosReplaceReportFile(path, destination, error)) return;
        [study setValue:destination forKey:@"reportURL"];
        associated = YES;
        saved = [context save:error];
        return;
    } @catch (NSException *exception) {
        if (error) *error = [NSError errorWithDomain:@"HorosReportImport" code:3 userInfo:@{NSLocalizedDescriptionKey: NSLocalizedString(@"The report could not be attached. The previous report has been kept.", nil)}];
        return;
    } @finally {
        if (!saved) {
            if (associated) [study setValue:previous forKey:@"reportURL"];
            if (destination) [NSFileManager.defaultManager removeItemAtPath:destination error:NULL];
        }
        [previous release];
        [destination release];
        if (error) [*error retain];
    }
    });
    if (error) [*error autorelease];
    return saved;
}

- (IBAction)attachExistingReport:(id)sender
{
    if (!self.database.isLocal || self.database.isReadOnly || databaseOutline.selectedRowIndexes.count != 1) return;
    id item = [databaseOutline itemAtRow:databaseOutline.selectedRowIndexes.firstIndex];
    if ([item isDistant]) return;
    DicomStudy *study = [[item valueForKey:@"type"] isEqualToString:@"Study"] ? item : [item valueForKey:@"study"];
    if (!study || [[study valueForKey:@"lockedStudy"] boolValue]) return;
    NSString *uid = [[study valueForKey:@"studyInstanceUID"] copy];
    @try {
        NSOpenPanel *panel = [NSOpenPanel openPanel];
        panel.title = NSLocalizedString(@"Attach existing report", nil);
        panel.prompt = NSLocalizedString(@"Attach", nil);
        panel.message = NSLocalizedString(@"Choose a report to copy into the selected study. The original file will be kept.", nil);
        panel.canChooseFiles = YES;
        panel.canChooseDirectories = NO;
        panel.allowsMultipleSelection = NO;
        panel.treatsFilePackagesAsDirectories = NO;
        panel.allowedContentTypes = @[[UTType typeWithFilenameExtension:@"pdf"], [UTType typeWithFilenameExtension:@"rtf"], UTTypeRTFD, [UTType typeWithFilenameExtension:@"doc"], [UTType typeWithFilenameExtension:@"docx"], [UTType typeWithFilenameExtension:@"pages"], [UTType typeWithFilenameExtension:@"odt"], [UTType typeWithFilenameExtension:@"txt"]];
        if ([panel runModal] != NSModalResponseOK) return;
        if ([[study valueForKey:@"reportURL"] length] && HorosRunInformationalAlertPanel(
            NSLocalizedString(@"Replace report association", nil),
            NSLocalizedString(@"Attach this document instead of the current report? The previous document will be kept on disk.", nil),
            NSLocalizedString(@"Attach", nil), NSLocalizedString(@"Cancel", nil), nil) != HorosAlertDefaultResponse) return;
        NSError *error = nil;
        if (![self importReport:panel.URL.path UID:uid error:&error]) {
            HorosRunAlertPanel(NSLocalizedString(@"Report attachment failed", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
                error.localizedDescription ?: NSLocalizedString(@"The report could not be attached.", nil));
            return;
        }
        [reportFilesToCheck setObject:[NSMutableDictionary dictionaryWithObjectsAndKeys:study, @"study", [NSDate distantPast], @"date", nil] forKey:study.objectID];
        [databaseOutline reloadData];
        [self updateReportToolbarIcon:nil];
    } @finally {
        [uid release];
    }
}

- (IBAction)insertSelectedImagesIntoReport:(id)sender
{
    if (!self.database.isLocal || self.database.isReadOnly || databaseOutline.selectedRowIndexes.count != 1) return;
    id item = [databaseOutline itemAtRow:databaseOutline.selectedRowIndexes.firstIndex];
    if ([item isDistant]) return;
    DicomStudy *study = [[item valueForKey:@"type"] isEqualToString:@"Study"] ? item : [item valueForKey:@"study"];
    if (!study || [[study valueForKey:@"lockedStudy"] boolValue]) return;
    NSString *report = [study valueForKey:@"reportURL"];
    if (!report.length || ![[NSFileManager defaultManager] fileExistsAtPath:report]) {
        HorosRunCriticalAlertPanel(NSLocalizedString(@"Report", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"Choose a Pages or Word report before inserting images. Open or attach a report first. No document has been changed.", nil));
        return;
    }
    if ([HorosReportImageInsertion kindOfReportPath:report] == HorosReportImageKindUnsupported) {
        HorosRunCriticalAlertPanel(NSLocalizedString(@"Report", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"Images can be inserted into a Pages or Word report. This report is a different format. No document has been changed.", nil));
        return;
    }
    NSArray *rendered = [self renderedJPEGPathsForReportInsertion:study];
    if (!rendered.count) {
        HorosRunCriticalAlertPanel(NSLocalizedString(@"Report", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil,
            NSLocalizedString(@"Select one or more images to insert into the report. No document has been changed.", nil));
        return;
    }
    if (![HorosReportImageInsertion insertWithReportPath:report sources:rendered]) {
        NSString *message = [HorosReportImageInsertion lastErrorMessage];
        if (!message.length) {
            message = NSLocalizedString(@"The selected images could not be inserted. The original report and the source images have been preserved.", nil);
        }
        HorosRunCriticalAlertPanel(NSLocalizedString(@"Report", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil, message);
        return;
    }
}

- (NSArray*)renderedJPEGPathsForReportInsertion:(DicomStudy*)study
{
    NSString *directory = [NSTemporaryDirectory() stringByAppendingPathComponent:[@"horos-report-images-" stringByAppendingString:NSUUID.UUID.UUIDString]];
    if (![[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:NULL])
        return @[];
    NSMutableArray *paths = [NSMutableArray array];
    ViewerController *viewer = [ViewerController frontMostDisplayed2DViewer];
    NSString *viewerUID = [[viewer currentStudy] valueForKey:@"studyInstanceUID"];
    NSString *studyUID = [study valueForKey:@"studyInstanceUID"];
    if (viewer && viewerUID.length && studyUID.length && [viewerUID isEqualToString:studyUID]) {
        NSImage *image = [[viewer imageView] nsimage:NO];
        NSString *path = [directory stringByAppendingPathComponent:@"0001.jpg"];
        if (image && [HorosReportImageInsertion writeJPEG:image toPath:path])
            [paths addObject:path];
        return paths;
    }
    NSMutableArray *objects = [NSMutableArray array];
    (void)[self filesForDatabaseMatrixSelection:objects onlyImages:YES];
    NSInteger index = 0;
    for (id object in objects) {
        if (![object isKindOfClass:[DicomImage class]]) continue;
        NSImage *image = [object image];
        if (!image) continue;
        NSString *path = [directory stringByAppendingPathComponent:[NSString stringWithFormat:@"%04ld.jpg", (long)++index]];
        if ([HorosReportImageInsertion writeJPEG:image toPath:path])
            [paths addObject:path];
        if (index >= 16) break;
    }
    return paths;
}

#endif

- (NSArray*) exportDICOMFileInt: (NSString*) location files: (NSMutableArray*) filesToExport objects: (NSMutableArray*) dicomFiles2Export
{
    return [self exportDICOMFileInt: [NSMutableDictionary dictionaryWithObjectsAndKeys: location, @"location", filesToExport, @"filesToExport", dicomFiles2Export, @"dicomFiles2Export", nil]];
}

- (void) runInformationAlertPanel:(NSMutableDictionary*) dict
{
    int a = HorosRunInformationalAlertPanel( [dict objectForKey: @"title"], @"%@", [dict objectForKey: @"button1"], [dict objectForKey: @"button2"], [dict objectForKey: @"button3"], [dict objectForKey: @"message"]);
    
    [dict setObject: [NSNumber numberWithInt: a] forKey: @"result"];
}

+ (NSString*) configuredPatientFolderForImage:(NSManagedObject*) image naming:(HorosExportFolderNaming*) naming
{
    NSManagedObject *study = [image valueForKeyPath:@"series.study"];
    NSString *identity = [study valueForKey:@"patientUID"];
    if (!identity.length) identity = [study valueForKey:@"studyInstanceUID"];
    if (!identity.length) identity = study.objectID.URIRepresentation.absoluteString;
    return [naming patientFolderWithName:[study valueForKey:@"name"] patientID:[study valueForKey:@"patientID"] identity:identity];
}

+ (NSString*) dicomExportPatientFolderName:(NSString*) name addDICOMDIR:(BOOL) addDICOMDIR
{
    if( name.length == 0)
        name = @"unnamed";
    NSMutableString *component;
    if( addDICOMDIR)
    {
        // Preserve the existing media-name truncation and ASCII conversion policy.
        NSString *shortName = name.length > 8 ? [name substringToIndex:7] : name;
        NSData *asciiData = [[shortName uppercaseString] dataUsingEncoding:NSASCIIStringEncoding allowLossyConversion:YES];
        component = [[[NSMutableString alloc] initWithData:asciiData encoding:NSASCIIStringEncoding] autorelease];
    }
    else
        component = [NSMutableString stringWithString:name];
    component = [BrowserController replaceNotAdmitted:component preserveHyphens:!addDICOMDIR];
    return component.length ? component : (addDICOMDIR ? @"UNNAMED" : @"unnamed");
}

- (BOOL) confirmDICOMExportFolder:(NSString*) path
{
    NSMutableDictionary *options = [NSMutableDictionary dictionaryWithObjectsAndKeys:	NSLocalizedString(@"Export", nil), @"title",
                                    [NSString stringWithFormat: NSLocalizedString(@"A folder already exists. Should I replace it? It will delete the entire content of this folder (%@), or merge the existing content with the new files?", nil), [path lastPathComponent]], @"message",
                                    NSLocalizedString(@"Replace", nil), @"button1",
                                    NSLocalizedString(@"Cancel", nil), @"button2",
                                    NSLocalizedString(@"Merge", nil), @"button3",
                                    nil];

    [self performSelectorOnMainThread: @selector(runInformationAlertPanel:) withObject: options waitUntilDone: YES]; // YES : because we are waiting the result

    int a;
    if( [options objectForKey: @"result"])
        a = [[options objectForKey: @"result"] intValue];
    else a = HorosAlertAlternateResponse; // Cancel

    if( a == HorosAlertDefaultResponse)
    {
        [[NSFileManager defaultManager] removeItemAtPath:path error:NULL];
        [[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
    }
    else if( a == HorosAlertOtherResponse)
    {
        // Merge
    }
    else
    {
        return NO;
    }
    return YES;
}

- (void) showDICOMExportCompletion:(NSDictionary*) result
{
    NSAlert *alert = [[[NSAlert alloc] init] autorelease];
    alert.messageText = NSLocalizedString(@"DICOM export completed", nil);
    alert.informativeText = [NSString stringWithFormat:NSLocalizedString(@"Exported files: %@\nDestination: %@", nil), [result objectForKey:@"count"], [result objectForKey:@"location"]];
    [alert addButtonWithTitle:NSLocalizedString(@"OK", nil)];
    [alert runModal];
}

- (void) showDICOMExportError:(NSError*) error
{
    NSAlert *alert = [NSAlert alertWithError:error];
    NSString *guidance = NSLocalizedString(@"Check that the source files are accessible and the destination is a folder you can write to with enough free space. For OneDrive or another cloud provider, make source files available offline and check that the destination provider is available. Files already exported were kept.", nil);
    NSMutableArray *details = [NSMutableArray array];
    if( alert.informativeText.length)
        [details addObject:alert.informativeText];
    NSString *reason = error.localizedFailureReason;
    if( reason.length && [alert.informativeText rangeOfString:reason].location == NSNotFound)
        [details addObject:reason];
    [details addObject:guidance];
    alert.informativeText = [details componentsJoinedByString:@"\n\n"];
    [alert runModal];
}

- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters
{
    NSAutoreleasePool *pool = nil;
    
    if( [NSThread isMainThread] == NO) // This is IMPORTANT for the result ! A thread cannot return a 'autorelease' object without a pool.... DO NOT MODIFY !
        pool = [[NSAutoreleasePool alloc] init];
    
    NSMutableArray *result = [NSMutableArray array];
    
    @synchronized( parameters)
    {
        [parameters setObject: result forKey: @"result"];
    }
    
    // The UI's database on the main thread; elsewhere a private-queue one, and the
    // export reads it on its queue (#966).
    DicomDatabase *idatabase = [NSThread isMainThread] ? self.database : self.database.privateQueueIndependentDatabase;
    [idatabase performBlockAndWait:^{
    @try
    {
        NSString *location = [parameters objectForKey: @"location"];
        NSMutableArray *filesToExport = [parameters objectForKey: @"filesToExport"];
        NSMutableArray *dicomFiles2Export = [NSMutableArray arrayWithArray: [idatabase objectsWithIDs: [parameters objectForKey: @"dicomFiles2Export"]]];
        
        [filesToExport removeDuplicatedStringsInSyncWithThisArray: dicomFiles2Export];
        
        NSString			*dest = nil, *path = location;
        Wait                *splash = nil;
        // A file promise captured these before the drop (#605); a menu export reads them now.
        BOOL				addDICOMDIR = [parameters objectForKey:@"addDICOMDIR"] ? [[parameters objectForKey:@"addDICOMDIR"] boolValue] : [[NSUserDefaults standardUserDefaults] boolForKey:@"AddDICOMDIRForExport"];
        BOOL                encryptExport = [parameters objectForKey:@"encrypt"] ? [[parameters objectForKey:@"encrypt"] boolValue] : [[NSUserDefaults standardUserDefaults] boolForKey: @"encryptForExport"];
        NSString            *exportPassword = [parameters objectForKey:@"password"] ?: passwordForExportEncryption;
        BOOL                quietErrors = [[parameters objectForKey:@"quietErrors"] boolValue];
        NSDictionary *folderOptions = [parameters objectForKey:@"folderNaming"];
        HorosExportFolderNaming *customFolderNaming = (!addDICOMDIR && folderOptions) ? [[[HorosExportFolderNaming alloc] initWithOptions:folderOptions] autorelease] : nil;
        long				previousSeries = -1, serieCount = 0;
        
        if( [NSThread isMainThread])
            splash = [[Wait alloc] initWithString:NSLocalizedString( @"Exporting...", nil) :YES];
        
        NSMutableArray		*files2Compress = [NSMutableArray array];
        DicomStudy			*previousStudy = nil;
        BOOL				exportAborted = NO;
        NSError *exportError = nil;
        NSMutableSet *exportedPaths = [NSMutableSet set];
        NSUInteger exportedCount = 0;
        NSMutableArray		*renameArray = [NSMutableArray array];
        NSMutableSet *reviewedPatientFolders = [NSMutableSet set];
        NSMutableDictionary *reviewedStudyFolders = [NSMutableDictionary dictionary];
        NSMutableDictionary *reviewedSeriesFolders = [NSMutableDictionary dictionary];
        
        [splash setCancel:YES];
        [splash showWindow:self];
        [[splash progress] setMaxValue:[filesToExport count]];
        
        [[DicomStudy dbModifyLock] lock];
        
        @try
        {
            for( int i = 0; i < [filesToExport count]; i++)
            {
                NSManagedObject	*curImage = [dicomFiles2Export objectAtIndex:i];
                NSString		*extension = [[filesToExport objectAtIndex:i] pathExtension];
                
                if( [curImage valueForKey: @"fileType"])
                {
                    if( [[curImage valueForKey: @"fileType"] hasPrefix:@"DICOM"])
                        extension = @"dcm";
                }
                
                if([extension isEqualToString:@""])
                    extension = @"dcm";
                
                NSString *tempPath = [path stringByAppendingPathComponent:
                    [BrowserController dicomExportPatientFolderName:[curImage valueForKeyPath:@"series.study.name"] addDICOMDIR:addDICOMDIR]];
                if (customFolderNaming)
                    tempPath = [path stringByAppendingPathComponent:[BrowserController configuredPatientFolderForImage:curImage naming:customFolderNaming]];


                @synchronized( parameters)
                {
                    [result addObject: [tempPath lastPathComponent]];
                }
                
                // Track the source patient as well as the destination: two different
                // patients may sanitize to the same folder name within one batch.
                id patientIdentity = [curImage valueForKeyPath:@"series.study.patientUID"];
                if( ![patientIdentity length])
                    patientIdentity = [curImage valueForKeyPath:@"series.study"];
                NSArray *patientFolderKey = @[tempPath, patientIdentity];

                // Find the DICOM-PATIENT folder
                if ( ![[NSFileManager defaultManager] fileExistsAtPath:tempPath])
                {
                    if (![[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:&exportError]) {
                            exportAborted = YES;
                            break;
                        }
                }
                else
                {
                    if( ![reviewedPatientFolders containsObject:patientFolderKey])
                    {
                        if( ![self confirmDICOMExportFolder:tempPath])
                        {
                            exportAborted = YES;
                            break;
                        }
                    }
                }
                
                [reviewedPatientFolders addObject:patientFolderKey];

                NSString *studyPath = nil;
                
                //Workaround for UI calls from background UI (runtime warnings) - Binding could be the definitive resolution for this
                __block NSInteger folderTreeSelectedTag = 0;
                if ([parameters objectForKey:@"folderTreeTag"])
                {
                    folderTreeSelectedTag = [[parameters objectForKey:@"folderTreeTag"] integerValue];
                }
                else if ([NSThread isMainThread])
                {
                    folderTreeSelectedTag = [folderTree selectedTag];
                }
                else
                {
                    dispatch_sync(dispatch_get_main_queue(), ^(void) {
                        folderTreeSelectedTag = [folderTree selectedTag];
                    });
                }
                
                if(folderTreeSelectedTag == 0)
                {
                    NSString *name = [curImage valueForKeyPath: @"series.study.studyName"];
                    NSString *idstring = [curImage valueForKeyPath: @"series.study.id"];
                    
                    if( name.length == 0)
                        name = @"unnamed";
                    
                    if( idstring == nil)
                        idstring = @"0";
                    
                    NSString *studyId = [BrowserController replaceNotAdmitted: [NSMutableString stringWithString: idstring] preserveHyphens:!addDICOMDIR];
                    NSString *studyName = [BrowserController replaceNotAdmitted: [NSMutableString stringWithString: name] preserveHyphens:!addDICOMDIR];
                    
                    if( studyId == nil || [studyId length] == 0)
                        studyId = @"0";
                    
                    if( studyName.length == 0)
                        studyName = @"unnamed";
                    
                    if (!addDICOMDIR)
                        tempPath = [tempPath stringByAppendingPathComponent: [NSString stringWithFormat: @"%@ - %@", studyName, studyId]];
                    else
                    {
                        NSMutableString *name;
                        if ([(NSString*)studyId length] > 8)
                            name = [NSMutableString stringWithString:[[studyId substringToIndex:7] uppercaseString]];
                        else
                            name = [NSMutableString stringWithString:[studyId uppercaseString]];
                        
                        NSData* asciiData = [name dataUsingEncoding:NSASCIIStringEncoding allowLossyConversion:YES];
                        name = [[[NSMutableString alloc] initWithData:asciiData encoding:NSASCIIStringEncoding] autorelease];
                        
                        [BrowserController replaceNotAdmitted: name preserveHyphens:!addDICOMDIR];
                        tempPath = [tempPath stringByAppendingPathComponent:name];
                    }
                    
                    if (customFolderNaming)
                    {
                        NSManagedObject *study = [curImage valueForKeyPath:@"series.study"];
                        NSString *component = [customFolderNaming studyFolderWithName:[study valueForKey:@"studyName"] studyID:[study valueForKey:@"id"] uid:[study valueForKey:@"studyInstanceUID"] identity:study.objectID.URIRepresentation.absoluteString];
                        tempPath = [[tempPath stringByDeletingLastPathComponent] stringByAppendingPathComponent:component];
                    }

                    // Confirm distinct study identities that collapse to one folder
                    // within this parent. A previous parent-level Merge covers older files.
                    id studyIdentity = [curImage valueForKeyPath:@"series.study.studyInstanceUID"];
                    if( ![studyIdentity length])
                        studyIdentity = [curImage valueForKeyPath:@"series.study"];
                    NSArray *studyFolderKey = @[patientIdentity, tempPath];
                    NSMutableSet *studySources = reviewedStudyFolders[studyFolderKey];
                    if( !studySources)
                    {
                        studySources = [NSMutableSet set];
                        reviewedStudyFolders[studyFolderKey] = studySources;
                    }
                    if( studySources.count && ![studySources containsObject:studyIdentity] &&
                        [[NSFileManager defaultManager] fileExistsAtPath:tempPath] &&
                        ![self confirmDICOMExportFolder:tempPath])
                    {
                        exportAborted = YES;
                        break;
                    }
                    [studySources addObject:studyIdentity];

                    // Find the DICOM-STUDY folder
                    if (![[NSFileManager defaultManager] fileExistsAtPath:tempPath])
                        if (![[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:&exportError]) {
                            exportAborted = YES;
                            break;
                        }
                    
                    studyPath = tempPath;
                    
                    NSString *sname = [curImage valueForKeyPath: @"series.name"];
                    if( sname.length == 0)
                        sname = @"series";
                    
                    NSString *seriesName = [BrowserController replaceNotAdmitted: [NSMutableString stringWithString: sname] preserveHyphens:!addDICOMDIR];
                    
                    NSNumber *seriesId = [curImage valueForKeyPath: @"series.id"];
                    
                    if( seriesId == nil)
                        seriesId = [NSNumber numberWithInt: 0];
                    
                    if( seriesName.length == 0)
                        seriesName = @"unnamed";
                    
                    if ( !addDICOMDIR)
                    {
                        NSMutableString *seriesStr = [NSMutableString stringWithString: seriesName];
                        
                        [BrowserController replaceNotAdmitted:seriesStr preserveHyphens:!addDICOMDIR];
                        
                        tempPath = [tempPath stringByAppendingPathComponent: seriesStr ];
                        tempPath = [tempPath stringByAppendingFormat:@"_%@", seriesId];
                    }
                    else
                    {
                        NSMutableString *name;
                        
                        name = [NSMutableString stringWithString: [[seriesId stringValue] uppercaseString]];
                        
                        NSData* asciiData = [name dataUsingEncoding:NSASCIIStringEncoding allowLossyConversion:YES];
                        name = [[[NSMutableString alloc] initWithData:asciiData encoding:NSASCIIStringEncoding] autorelease];
                        
                        [BrowserController replaceNotAdmitted: name preserveHyphens:!addDICOMDIR];
                        tempPath = [tempPath stringByAppendingPathComponent:name];
                    }
                    
                    if (customFolderNaming)
                    {
                        NSManagedObject *series = [curImage valueForKey:@"series"];
                        NSString *component = [customFolderNaming seriesFolderWithName:[series valueForKey:@"name"] number:[series valueForKey:@"id"] uid:[series valueForKey:@"seriesInstanceUID"] identity:series.objectID.URIRepresentation.absoluteString];
                        tempPath = [[tempPath stringByDeletingLastPathComponent] stringByAppendingPathComponent:component];
                    }

                    // Confirm distinct series identities that collapse to one folder
                    // within this parent. A previous parent-level Merge covers older files.
                    id seriesIdentity = [curImage valueForKeyPath:@"series.seriesInstanceUID"];
                    if( ![seriesIdentity length])
                        seriesIdentity = [curImage valueForKeyPath:@"series"];
                    NSArray *seriesFolderKey = @[studyIdentity, tempPath];
                    NSMutableSet *seriesSources = reviewedSeriesFolders[seriesFolderKey];
                    if( !seriesSources)
                    {
                        seriesSources = [NSMutableSet set];
                        reviewedSeriesFolders[seriesFolderKey] = seriesSources;
                    }
                    if( seriesSources.count && ![seriesSources containsObject:seriesIdentity] &&
                        [[NSFileManager defaultManager] fileExistsAtPath:tempPath] &&
                        ![self confirmDICOMExportFolder:tempPath])
                    {
                        exportAborted = YES;
                        break;
                    }
                    [seriesSources addObject:seriesIdentity];

                    // Find the DICOM-SERIE folder
                    if (![[NSFileManager defaultManager] fileExistsAtPath:tempPath])
                        if (![[NSFileManager defaultManager] createDirectoryAtPath:tempPath withIntermediateDirectories:YES attributes:nil error:&exportError]) {
                            exportAborted = YES;
                            break;
                        }
                }
                else studyPath = tempPath;
                
                if( previousStudy != [curImage valueForKeyPath: @"series.study"])
                {
                    previousStudy = [curImage valueForKeyPath: @"series.study"];
                }
                
                long imageNo = [[curImage valueForKey:@"instanceNumber"] intValue];
                
                if( previousSeries != [[curImage valueForKeyPath: @"series.id"] intValue])
                {
                    previousSeries = [[curImage valueForKeyPath: @"series.id"] intValue];
                    serieCount++;
                }
                if (!addDICOMDIR)
                    dest = [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, extension];
                else
                    dest = [NSString stringWithFormat:@"%@/%4.4d%4.4d", tempPath, (int) serieCount, (int) imageNo];
                
                int t = 2;
                while( [[NSFileManager defaultManager] fileExistsAtPath: dest])
                {
                    if (!addDICOMDIR)
                        dest = [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, t, extension];
                    else
                        dest = [NSString stringWithFormat:@"%@/%4.4d%d", tempPath, (int) imageNo, t];
                    t++;
                }
                
                NSError *error = nil;
                if( dest == nil || HorosCopyFileForPublication(NSFileManager.defaultManager, [filesToExport objectAtIndex:i], dest, NO, &error) == NO)
                {
                    NSLog( @"***** %@", error);
                    NSLog( @"***** src = %@", [filesToExport objectAtIndex:i]);
                    NSLog( @"***** dst = %@", dest);
                    exportError = error ?: [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:
                        @{NSLocalizedDescriptionKey: NSLocalizedString(@"The destination for the DICOM export could not be determined.", nil)}];
                    exportAborted = YES;
                    break;
                }

                [exportedPaths addObject:dest];

                if( t != 2)
                {
                    if (!addDICOMDIR)
                        [renameArray addObject: [NSDictionary dictionaryWithObjectsAndKeys: [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, extension], @"oldName", [NSString stringWithFormat:@"%@/IM-%4.4d-%4.4d-%4.4d.%@", tempPath, (int) serieCount, (int) imageNo, 1, extension], @"newName", nil]];
                    else
                        [renameArray addObject: [NSDictionary dictionaryWithObjectsAndKeys: [NSString stringWithFormat:@"%@/%4.4d%4.4d", tempPath, (int) serieCount, (int) imageNo], @"oldName", [NSString stringWithFormat:@"%@/%4.4d%d", tempPath, (int) imageNo, 1], @"newName", nil]];
                }

                if( [[curImage valueForKey: @"fileType"] hasPrefix:@"DICOM"])
                {
                    //Workaround for UI calls from background UI (runtime warnings) - Binding could be the definitive resolution for this
                    __block NSInteger compressionMatrixSelectedTag = 1;
                    if ([parameters objectForKey:@"compressionTag"])
                    {
                        compressionMatrixSelectedTag = [[parameters objectForKey:@"compressionTag"] integerValue];
                    }
                    else if ([NSThread isMainThread])
                    {
                        compressionMatrixSelectedTag = [compressionMatrix selectedTag];
                    }
                    else
                    {
                        dispatch_sync(dispatch_get_main_queue(), ^(void) {
                            compressionMatrixSelectedTag = [compressionMatrix selectedTag];
                        });
                    }
                    
                    switch(compressionMatrixSelectedTag)
                    {
                        case 1: // compress
                            [files2Compress addObject: dest];
                            break;
                            
                        case 2: // decompress
                            [files2Compress addObject: dest];
                            break;
                    }
                }
                
                if( [extension isEqualToString:@"hdr"])		// ANALYZE -> COPY IMG
                {
                    [[NSFileManager defaultManager] copyItemAtPath:[[[filesToExport objectAtIndex:i] stringByDeletingPathExtension] stringByAppendingPathExtension:@"img"] toPath:[[dest stringByDeletingPathExtension] stringByAppendingPathExtension:@"img"] error:NULL];
                }
                
                [splash incrementBy:1];
                
                [NSThread currentThread].progress = (float) i / (float) [filesToExport count];
                [NSThread currentThread].status = N2LocalizedSingularPluralCount( [filesToExport count]-i, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
                
                if( [splash aborted] || [NSThread currentThread].isCancelled)
                {
                    i = [filesToExport count];
                    exportAborted = YES;
                }
            }
        }
        @catch (NSException * e)
        {
            N2LogExceptionWithStackTrace(e);
            exportAborted = YES;
            exportError = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:@{NSLocalizedDescriptionKey:NSLocalizedString(@"DICOM export could not be completed.", nil), NSLocalizedFailureReasonErrorKey:e.reason ?: @""}];
        }
        
        [[DicomStudy dbModifyLock] unlock];
        
        NSMutableSet *renamedSources = [NSMutableSet set];
        for (NSDictionary *d in renameArray)
        {
            NSString *oldName = [d objectForKey:@"oldName"];
            NSString *newName = [d objectForKey:@"newName"];
            if ([renamedSources containsObject:oldName]) continue;
            NSError *renameError = nil;
            if (![[NSFileManager defaultManager] moveItemAtPath:oldName toPath:newName error:&renameError])
            {
                if (!exportError) exportError = renameError;
                exportAborted = YES;
                break;
            }
            [renamedSources addObject:oldName];
            if ([exportedPaths containsObject:oldName])
            {
                [exportedPaths removeObject:oldName];
                [exportedPaths addObject:newName];
            }
            for (NSUInteger index = 0; index < files2Compress.count; index++)
                if ([[files2Compress objectAtIndex:index] isEqualToString:oldName])
                    [files2Compress replaceObjectAtIndex:index withObject:newName];
        }

        //close progress window
        [splash close];
        [splash autorelease];

        if( exportError)
        {
            @synchronized( parameters) { [parameters setObject: exportError forKey: @"exportError"]; }
            if( !quietErrors)
                [self performSelectorOnMainThread:@selector(showDICOMExportError:) withObject:exportError waitUntilDone:YES];
        }
        
        if( [files2Compress count] > 0 && exportAborted == NO)
        {
            
#ifndef OSIRIX_LIGHT
            
            //Workaround for UI calls from background UI (runtime warnings) - Binding could be the definitive resolution for this
            __block NSInteger compressionMatrixSelectedTag = 1;
            if ([parameters objectForKey:@"compressionTag"])
            {
                compressionMatrixSelectedTag = [[parameters objectForKey:@"compressionTag"] integerValue];
            }
            else if ([NSThread isMainThread])
            {
                compressionMatrixSelectedTag = [compressionMatrix selectedTag];
            }
            else
            {
                dispatch_sync(dispatch_get_main_queue(), ^(void) {
                    compressionMatrixSelectedTag = [compressionMatrix selectedTag];
                });
            }
            
            if (compressionMatrixSelectedTag == 1 || compressionMatrixSelectedTag == 2)
            {
                NSError *conversionError = nil;
                if (![idatabase processFilesAtPaths:files2Compress intoDirAtPath:nil mode:(compressionMatrixSelectedTag == 1 ? Compress : Decompress) error:&conversionError])
                {
                    exportAborted = YES;
                    [self performSelectorOnMainThread:@selector(showDICOMExportError:) withObject:conversionError waitUntilDone:YES];
                }
            }
#endif
            
        }
        
        // ANR - I had to create this loop, otherwise, if I export a folder on the desktop, the dcmkdir will scan all files and folders available on the desktop.... not only the exported folder.
        
#ifndef OSIRIX_LIGHT
        if (addDICOMDIR && exportAborted == NO)
        {
            NSMutableSet *indexedFolders = [NSMutableSet set];
            for( int i = 0; i < [filesToExport count]; i++)
            {
                NSManagedObject	*curImage = [dicomFiles2Export objectAtIndex:i];
                NSString *tempPath = [path stringByAppendingPathComponent:
                    [BrowserController dicomExportPatientFolderName:[curImage valueForKeyPath:@"series.study.name"] addDICOMDIR:addDICOMDIR]];
                if (customFolderNaming)
                    tempPath = [path stringByAppendingPathComponent:[BrowserController configuredPatientFolderForImage:curImage naming:customFolderNaming]];


                if( ![indexedFolders containsObject:tempPath])
                {
                    [NSThread currentThread].status = NSLocalizedString( @"Writing DICOMDIR...", nil);
                    NSError *dicomdirError = nil;
                    if( ![DicomDir createDicomDirAtDir:tempPath error:&dicomdirError])
                    {
                        exportAborted = YES;
                        [self performSelectorOnMainThread:@selector(showDICOMExportError:) withObject:dicomdirError waitUntilDone:YES];
                        break;
                    }
                    [indexedFolders addObject:tempPath];
                }
            }
        }
#endif
        for (NSString *exportedPath in exportedPaths)
            if ([[NSFileManager defaultManager] fileExistsAtPath:exportedPath]) exportedCount++;

        if( encryptExport == YES && exportAborted == NO)
        {
            NSMutableSet *packagedFolders = [NSMutableSet set];
            for( int i = 0; i < [filesToExport count]; i++)
            {
                NSManagedObject	*curImage = [dicomFiles2Export objectAtIndex:i];
                NSString *tempPath = [path stringByAppendingPathComponent:
                    [BrowserController dicomExportPatientFolderName:[curImage valueForKeyPath:@"series.study.name"] addDICOMDIR:addDICOMDIR]];
                if (customFolderNaming)
                    tempPath = [path stringByAppendingPathComponent:[BrowserController configuredPatientFolderForImage:curImage naming:customFolderNaming]];


                if( ![packagedFolders containsObject:tempPath])
                {
                    NSError *zipError = nil;
                    if( ![BrowserController encryptFileOrFolder:tempPath inZIPFile:[tempPath stringByAppendingPathExtension:@"zip"] password:exportPassword deleteSource:YES showGUI:!quietErrors error:&zipError])
                    {
                        exportAborted = YES;
                        @synchronized( parameters) { if( zipError) [parameters setObject: zipError forKey: @"exportError"]; }
                        if( !quietErrors)
                            [self performSelectorOnMainThread:@selector(showDICOMExportError:) withObject:zipError waitUntilDone:YES];
                        break;
                    }
                    [packagedFolders addObject:tempPath];
                }
            }
        }
        if (!exportAborted && ![NSThread currentThread].isCancelled && exportedCount > 0 && [[parameters objectForKey:@"showCompletion"] boolValue])
            [self performSelectorOnMainThread:@selector(showDICOMExportCompletion:) withObject:@{@"count":@(exportedCount), @"location":location} waitUntilDone:YES];
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
        NSError *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:@{NSLocalizedDescriptionKey:NSLocalizedString(@"DICOM export could not be completed.", nil), NSLocalizedFailureReasonErrorKey:e.reason ?: @""}];
        [self performSelectorOnMainThread:@selector(showDICOMExportError:) withObject:error waitUntilDone:YES];
    }
    }];
    
    self.passwordForExportEncryption = @"";
    
    [pool release];
    
    if( [NSThread isMainThread])
        return result;
    else
        return nil;
}

+ (void) encryptFiles: (NSArray*) srcFiles inZIPFile: (NSString*) destFile password: (NSString*) password
{
    NSTask *t;
    NSArray *args;
    
    if( [AppController hasMacOSXSnowLeopard] == NO && [NSThread isMainThread] && [password length] > 0)
    {
        password = nil;
        HorosRunCriticalAlertPanel(NSLocalizedString(@"ZIP Encryption", nil), NSLocalizedString(@"ZIP encryption requires MacOS 10.6 or higher. The ZIP file will be generated, but NOT encrypted with a password.", nil), NSLocalizedString(@"OK",nil),nil, nil);
        return;
    }
    
    if( destFile)
        [[NSFileManager defaultManager] removeItemAtPath: destFile error: nil];
    
    WaitRendering *wait = nil;
    if( [NSThread isMainThread])
    {
        wait = [[WaitRendering alloc] init: NSLocalizedString(@"Compressing the files...", nil)];
        [wait showWindow:self];
    }
    
    @try
    {
#define CHUNKZIP 1000
        
        int total = [srcFiles count];
        
        for( int i = 0; i < total;)
        {
            int no;
            
            if( i + CHUNKZIP >= total) no = total - i;
            else no = CHUNKZIP;
            
            NSRange range = NSMakeRange( i, no);
            
            id *objs = (id*) malloc( no * sizeof( id));
            if( objs)
            {
                [srcFiles getObjects: objs range: range];
                
                NSArray *subArray = [NSArray arrayWithObjects: objs count: no];
                
                t = [[[NSTask alloc] init] autorelease];
                [t setLaunchPath: @"/usr/bin/zip"];
                
                if( [password length] > 0)
                    args = [NSArray arrayWithObjects: @"-q", @"-j", @"-e", @"-P", password, destFile, nil];
                else
                    args = [NSArray arrayWithObjects: @"-q", @"-j", destFile, nil];
                
                args = [args arrayByAddingObjectsFromArray: subArray];
                
                [t setArguments: args];
                [t launch];
                while( [t isRunning]) [NSThread sleepForTimeInterval: 0.01];
                
                free( objs);
            }
            
            i += no;
        }
    }
    @catch (NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    [wait close];
    [wait autorelease];
}

+ (void) encryptFileOrFolder: (NSString*) srcFolder inZIPFile: (NSString*) destFile password: (NSString*) password
{
    return [BrowserController encryptFileOrFolder: srcFolder inZIPFile: destFile password: password deleteSource: YES showGUI: YES];
}

+ (void) encryptFileOrFolder: (NSString*) srcFolder inZIPFile: (NSString*) destFile password: (NSString*) password deleteSource: (BOOL) deleteSource
{
    return [BrowserController encryptFileOrFolder: srcFolder inZIPFile: destFile password: password deleteSource: deleteSource showGUI: YES];
}

+ (void) encryptFileOrFolder: (NSString*) srcFolder inZIPFile: (NSString*) destFile password: (NSString*) password deleteSource: (BOOL) deleteSource showGUI: (BOOL) showGUI
{
    [self encryptFileOrFolder:srcFolder inZIPFile:destFile password:password deleteSource:deleteSource showGUI:showGUI error:NULL];
}

// ZIP encryption leaves entry names readable. Wrap the existing archive in a
// generic entry so patient/study names are inside the encrypted payload.
+ (BOOL) prepareProtectedEmailAttachment:(NSString*) source destination:(NSString*) destination password:(NSString*) password error:(NSError**) error
{
    if( error) *error = nil;
    if( password.length == 0)
    {
        if( error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:
            @{NSLocalizedDescriptionKey:NSLocalizedString(@"A password is required for email attachments.", nil)}];
        return NO;
    }
    NSFileManager *fm = [NSFileManager defaultManager];
    NSString *temporary = [NSTemporaryDirectory() stringByAppendingPathComponent:[@"horos-email-" stringByAppendingString:NSUUID.UUID.UUIDString]];
    BOOL succeeded = NO;
    @try
    {
        if( [fm createDirectoryAtPath:temporary withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:error])
        {
            NSString *payload = [temporary stringByAppendingPathComponent:@"Images.zip"];
            if( [fm copyItemAtPath:source toPath:payload error:error])
                succeeded = [self encryptFileOrFolder:payload inZIPFile:destination password:password deleteSource:NO showGUI:NO error:error];
        }
    }
    @finally
    {
        [fm removeItemAtPath:temporary error:NULL];
    }
    return succeeded;
}

+ (BOOL) encryptFileOrFolder: (NSString*) srcFolder inZIPFile: (NSString*) destFile password: (NSString*) password deleteSource: (BOOL) deleteSource showGUI: (BOOL) showGUI error:(NSError**) error
{
    if( error) *error = nil;
    if( srcFolder.length == 0 || destFile.length == 0)
    {
        if( error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteInvalidFileNameError userInfo:
            @{NSLocalizedDescriptionKey: NSLocalizedString(@"A source and destination are required for ZIP export.", nil)}];
        return NO;
    }
    BOOL succeeded = NO;
    NSTask *t;
    NSArray *args;
    
    if( [AppController hasMacOSXSnowLeopard] == NO && [NSThread isMainThread] && [password length] > 0)
    {
        password = nil;
        HorosRunCriticalAlertPanel(NSLocalizedString(@"ZIP Encryption", nil), NSLocalizedString(@"ZIP encryption requires MacOS 10.6 or higher. The ZIP file will be generated, but NOT encrypted with a password.", nil), NSLocalizedString(@"OK",nil),nil, nil);
        if( error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFeatureUnsupportedError userInfo:nil];
        return NO;
    }
    
    @synchronized (destFile) {
        HorosExportArchive *archive = [[HorosExportArchive alloc] initWithDestinationPath:destFile error:error];
        if( !archive) return NO;
        WaitRendering *wait = nil;
        if( [NSThread isMainThread] && showGUI == YES)
        {
            wait = [[WaitRendering alloc] init: NSLocalizedString(@"Compressing the files...", nil)];
            [wait showWindow:self];
        }
        
        [NSThread currentThread].status = NSLocalizedString( @"Compressing the files...", nil);
        
        @try
        {
            t = [[[NSTask alloc] init] autorelease];
            [t setLaunchPath: @"/usr/bin/zip"];
            
            BOOL isDirectory;
            
            if( [[NSFileManager defaultManager] fileExistsAtPath: srcFolder isDirectory: &isDirectory])
            {
                [t setCurrentDirectoryPath: [srcFolder stringByDeletingLastPathComponent]];
                
                if( [password length] > 0)
                    args = [NSArray arrayWithObjects: @"-q", @"-r", @"-e", @"-P", password, archive.archivePath, [srcFolder lastPathComponent], nil];
                else
                    args = [NSArray arrayWithObjects: @"-q", @"-r", archive.archivePath, [srcFolder lastPathComponent], nil];
                
                [t setArguments: args];
                [t launch];
                while( [t isRunning])
                    [NSThread sleepForTimeInterval: 0.1];
                
                //[t waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
                
                succeeded = [t terminationStatus] == 0 && [archive commitWithError:error];
                if( succeeded && deleteSource == YES)
                {
                    if( srcFolder)
                        [[NSFileManager defaultManager] removeItemAtPath: srcFolder error: nil];
                }
            }
        }
        @catch (NSException *e)
        {
            N2LogExceptionWithStackTrace(e);
        }
        
        [wait close];
        [wait autorelease];
        [archive release];
    }
    if( !succeeded && error && !*error)
        *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:
            @{NSLocalizedDescriptionKey: NSLocalizedString(@"ZIP export could not be completed. The uncompressed source files were kept.", nil),
              NSFilePathErrorKey: destFile}];
    return succeeded;
}

#ifdef OSIRIX_VIEWER
#ifndef OSIRIX_LIGHT
- (void) exportROIAndKeyImagesAsDICOMSeries: (id) sender
{
    WaitRendering *wait = [[WaitRendering alloc] init: NSLocalizedString(@"Generating the DICOM files...", nil)];
    [wait showWindow: self];
    
    DICOMExport *exporter = [[[DICOMExport alloc] init] autorelease];
    NSMutableArray *producedFiles = [NSMutableArray array];
    
    [exporter setSeriesDescription: NSLocalizedString( @"ROIs and Key Images", nil)];
    [exporter setSeriesNumber: 0];
    
    NSEvent *event = [[NSApplication sharedApplication] currentEvent];
    NSArray *images = nil;
    if([event modifierFlags] & NSEventModifierFlagOption)
        images = [self KeyImages: self];
    else if([event modifierFlags] & NSEventModifierFlagShift)
        images = [self ROIImages: self];
    else
        images = [self ROIsAndKeyImages: self];
    
    for( DicomImage *image in images)
    {
        NSDictionary *d = [image imageAsDICOMScreenCapture: exporter];
        
        [producedFiles addObject: d];
    }
    
    if( [producedFiles count])
    {
        NSArray *objects = [BrowserController.currentBrowser.database addFilesAtPaths: [producedFiles valueForKey: @"file"]
                                                                    postNotifications: YES
                                                                            dicomOnly: YES
                                                                  rereadExistingItems: YES
                                                                    generatedByOsiriX: YES];
        
        objects = [BrowserController.currentBrowser.database objectsWithIDs: objects];
        
        if( objects.count)
            (void)[self findAndSelectFile: nil image: objects.lastObject shouldExpand: NO];
    }
    
    [wait close];
    [wait autorelease];
}
#endif
#endif

- (void) showEmptyDICOMExportSelection
{
    HorosRunInformationalAlertPanel(NSLocalizedString(@"DICOM Export", nil),
        @"%@", NSLocalizedString(@"OK", nil), nil, nil,
        NSLocalizedString(@"No exportable files were found in the selection. Select a study, series, or image and check the export options before trying again.", nil));
}

- (void) exportDICOMFile: (id)sender
{
    BOOL exportMatrixSelection = ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix;
    BOOL hasSelection = exportMatrixSelection ? [oMatrix selectedCells].count > 0 : [databaseOutline selectedRowIndexes].count > 0;
    if( !hasSelection)
    {
        [self showEmptyDICOMExportSelection];
        return;
    }

    NSOpenPanel *sPanel = [NSOpenPanel openPanel];
    
    [sPanel setCanChooseDirectories:YES];
    [sPanel setCanChooseFiles:NO];
    [sPanel setAllowsMultipleSelection:NO];
    [sPanel setMessage: NSLocalizedString(@"Select the location where to export the DICOM files:",nil)];
    [sPanel setPrompt: NSLocalizedString(@"Choose",nil)];
    [sPanel setTitle: NSLocalizedString(@"Export",nil)];
    [sPanel setCanCreateDirectories:YES];
    [exportAccessoryView retain];
    NSRect legacyAccessoryFrame = exportAccessoryView.frame;
    HorosExportFolderOptions *folderOptionsView = [[[HorosExportFolderOptions alloc] initWithLegacyView:exportAccessoryView] autorelease];
    [sPanel setAccessoryView:folderOptionsView];
    self.passwordForExportEncryption = @"";
    
    [compressionMatrix selectCellWithTag: [[NSUserDefaults standardUserDefaults] integerForKey: @"Compression Mode for Export"]];
    
    NSInteger panelResult = [sPanel runModal];
    NSDictionary *folderOptions = panelResult == NSModalResponseOK ? [folderOptionsView acceptedOptions] : nil;
    [exportAccessoryView removeFromSuperview];
    exportAccessoryView.frame = legacyAccessoryFrame;
    [sPanel setAccessoryView:exportAccessoryView];
    [exportAccessoryView release];
    if (panelResult == NSModalResponseOK)
    {
        [sPanel makeFirstResponder: nil];
        
        NSMutableArray *dicomFiles2Export = [NSMutableArray array];
        NSMutableArray *filesToExport;
        
        WaitRendering *wait = [[WaitRendering alloc] init: NSLocalizedString(@"Preparing the files...", nil)];
        [wait showWindow: self];
        
        if( exportMatrixSelection)
            filesToExport = [self filesForDatabaseMatrixSelection: dicomFiles2Export onlyImages: NO];
        else
            filesToExport = [self filesForDatabaseOutlineSelection: dicomFiles2Export onlyImages: NO];
        
        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"AddROIsForExport"] == NO)
        {
            NSPredicate *predicate = nil;
            
            @try
            {
                predicate = [NSPredicate predicateWithFormat: @"!(series.name CONTAINS[c] %@) AND !(series.id == %@)", @"OsiriX ROI SR", @"5002"];
                dicomFiles2Export = [[[dicomFiles2Export filteredArrayUsingPredicate: predicate] mutableCopy] autorelease];
                
                predicate = [NSPredicate predicateWithFormat: @"!(series.name CONTAINS[c] %@) AND !(series.id == %@)", @"OsiriX Report SR", @"5003"];
                dicomFiles2Export = [[[dicomFiles2Export filteredArrayUsingPredicate: predicate] mutableCopy] autorelease];
                
                predicate = [NSPredicate predicateWithFormat: @"!(series.name CONTAINS[c] %@) AND !(series.id == %@)", @"OsiriX Annotations SR", @"5004"];
                dicomFiles2Export = [[[dicomFiles2Export filteredArrayUsingPredicate: predicate] mutableCopy] autorelease];
                
                predicate = [NSPredicate predicateWithFormat: @"!(series.name CONTAINS[c] %@) AND !(series.id == %@)", @"OsiriX No Autodeletion", @"5005"];
                dicomFiles2Export = [[[dicomFiles2Export filteredArrayUsingPredicate: predicate] mutableCopy] autorelease];
                
                predicate = [NSPredicate predicateWithFormat: @"!(series.name CONTAINS[c] %@) AND !(series.id == %@)", @"OsiriX WindowsState SR", @"5006"];
                dicomFiles2Export = [[[dicomFiles2Export filteredArrayUsingPredicate: predicate] mutableCopy] autorelease];
            }
            @catch (NSException *e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            
            filesToExport = [[[dicomFiles2Export valueForKey: @"completePath"] mutableCopy] autorelease];
        }
        
        [wait close];
        [wait autorelease];
        
        if( filesToExport.count == 0 || dicomFiles2Export.count == 0)
        {
            [self showEmptyDICOMExportSelection];
            return;
        }

        NSMutableDictionary *d = [NSMutableDictionary dictionaryWithObjectsAndKeys: sPanel.URL.path, @"location", filesToExport, @"filesToExport", [dicomFiles2Export valueForKey: @"objectID"], @"dicomFiles2Export", nil];
        
        if (folderOptions) [d setObject:folderOptions forKey:@"folderNaming"];
        [d setObject:@YES forKey:@"showCompletion"];
        NSThread* t = [[[NSThread alloc] initWithTarget:self selector:@selector(exportDICOMFileInt: ) object: d] autorelease];
        t.name = NSLocalizedString( @"Exporting...", nil);
        t.supportsCancel = YES;
        t.status = N2LocalizedSingularPluralCount( [filesToExport count], NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
        
        [[ThreadsManager defaultManager] addThreadAndStart: t];
        
        //Workaround for UI calls from background UI (runtime warnings) - Binding could be the definitive resolution for this
        __block NSInteger compressionMatrixSelectedTag = 1;
        if ([NSThread isMainThread])
        {
            compressionMatrixSelectedTag = [compressionMatrix selectedTag];
        }
        else
        {
            dispatch_sync(dispatch_get_main_queue(), ^(void) {
                compressionMatrixSelectedTag = [compressionMatrix selectedTag];
            });
        }
        
        [[NSUserDefaults standardUserDefaults] setInteger:[compressionMatrix selectedTag] forKey:@"Compression Mode for Export"];
    }
}

#ifndef OSIRIX_LIGHT
- (void)burnDICOM: (id)sender
{
    for( NSWindow *win in [NSApp windows])
    {
        if( [[win windowController] isKindOfClass:[BurnerWindowController class]])
        {
            HorosRunInformationalAlertPanel( NSLocalizedString(@"Burn", nil), NSLocalizedString(@"A burn session is already opened. Close it to burn a new study.", nil), NSLocalizedString(@"OK", nil), nil, nil);
            [win makeKeyAndOrderFront:self];
            return;
        }
    }
    
    NSMutableArray *managedObjects = [NSMutableArray array];
    NSMutableArray *filesToBurn;
    //Burn additional Files. Not just images. Add SRs
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix) filesToBurn = [self filesForDatabaseMatrixSelection:managedObjects onlyImages:NO];
    else filesToBurn = [self filesForDatabaseOutlineSelection: managedObjects onlyImages:NO];
    
    BurnerWindowController *burnerWindowController = [[BurnerWindowController alloc] initWithFiles:filesToBurn managedObjects:managedObjects];
    
    [burnerWindowController showWindow:self];
}
#endif

#ifndef OSIRIX_LIGHT
- (IBAction)anonymizeDICOM:(id)sender
{
    NSMutableArray *dicomFiles2Anonymize = [NSMutableArray array];
    NSMutableArray *filesToAnonymize;
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
        filesToAnonymize = [self filesForDatabaseMatrixSelection: dicomFiles2Anonymize];
    else
        filesToAnonymize = [self filesForDatabaseOutlineSelection: dicomFiles2Anonymize];
    
    [filesToAnonymize removeDuplicatedStringsInSyncWithThisArray: dicomFiles2Anonymize];
    
    for( int i = 0 ; i < dicomFiles2Anonymize.count; i++)
    {
        if( [[[dicomFiles2Anonymize objectAtIndex: i] fileType] isEqualToString: @"DICOM"] == NO)
        {
            [dicomFiles2Anonymize removeObjectAtIndex: i];
            [filesToAnonymize removeObjectAtIndex: i];
            
            i--;
        }
    }
    
    if( dicomFiles2Anonymize.count == 0)
    {
        HorosRunAlertPanel( NSLocalizedString(@"Anonymize Error", nil), NSLocalizedString(@"No DICOM files in this selection.", nil), nil, nil, nil);
    }
    else
    {
        NSArray* ref = [NSArray arrayWithObjects: filesToAnonymize, dicomFiles2Anonymize, NULL];
        [Anonymization showSavePanelForDefaultsKey:@"AnonymizationFields" modalForWindow:self.window modalDelegate:self didEndSelector:@selector(anonymizationSavePanelDidEnd:) representedObject:ref];
    }
}

- (BOOL)importAnonymizedFiles:(NSDictionary *)files originalImages:(NSArray *)originalImages replace:(BOOL)replace error:(NSError **)error
{
    if (error) *error = nil;
    DicomDatabase *target = self.database;
    NSMutableDictionary *originalForCopy = [NSMutableDictionary dictionary];
    NSMutableDictionary *fileFailures = [NSMutableDictionary dictionary];
    N2ManagedObjectContext *context = (N2ManagedObjectContext *)target.managedObjectContext;
    NSMutableArray *copiedPaths = [NSMutableArray array];
    NSMutableSet *captured = [NSMutableSet set];
    NSMutableSet *sourceSeries = [NSMutableSet set];
    NSMutableSet *retired = [NSMutableSet set];
    NSMutableDictionary *expectedCounts = [NSMutableDictionary dictionary];
    __block BOOL committed = NO;
    __block Wait *progress = nil;
    N2ManagedObjectContextPerformAndWait(context, ^{
    @try {
        if (target.isReadOnly || !HorosAnonymizationOutputsComplete(files.allKeys, files))
            [NSException raise:@"AnonymizationImport" format:@"The destination is read-only or the output files are incomplete."];
        NSSet *sourcePaths = [NSSet setWithArray:files.allKeys];
        for (DicomImage *image in originalImages) {
            if (image.managedObjectContext != context || image.isDeleted ||
                ![sourcePaths containsObject:image.completePath] ||
                (replace && image.series.study.lockedStudy.boolValue))
                [NSException raise:@"AnonymizationImport" format:@"The original images or active database changed, or a study is locked."];
            if (image.series) [sourceSeries addObject:image.series];
        }
        // Visit each series once, including all indexed frames of selected files.
        for (DicomSeries *series in sourceSeries)
            for (DicomImage *frame in series.images)
                if ([sourcePaths containsObject:frame.completePath]) [captured addObject:frame];
        if (replace && !captured.count)
            [NSException raise:@"AnonymizationImport" format:@"No original images remain to replace."];
        // Preserve unrelated pending edits before entering the clean-context batch.
        if (![target save:error]) return;
        progress = [[[Wait alloc] initWithString:NSLocalizedString(@"Importing anonymized images...", nil)] autorelease];
        [[progress progress] setMaxValue:files.count * 2];
        [progress setCancel:YES];
        [progress showWindow:self];
        BOOL (^cancelled)(NSError **) = ^BOOL(NSError **failure) {
            if (![progress pollCancellation]) return NO;
            if (failure) *failure = [NSError errorWithDomain:NSCocoaErrorDomain code:NSUserCancelledError userInfo:nil];
            return YES;
        };
        for (NSString *original in files) {
            NSString *source = [files objectForKey:original];
            if (cancelled(error)) return;
            NSString *destination = [target uniquePathForNewDataFileWithExtension:@"dcm"];
            if (![[NSFileManager defaultManager] copyItemAtPath:source toPath:destination error:error]) {
                [fileFailures setObject:@[NSLocalizedString(@"The anonymized file could not be copied into the database.", nil)] forKey:original];
                return;
            }
            [copiedPaths addObject:destination];
            [originalForCopy setObject:original forKey:destination];
            DicomFile *parsed = [[[DicomFile alloc] init:destination DICOMOnly:YES] autorelease];
            NSDictionary *elements = parsed.dicomElements;
            NSUInteger frames = MAX(1, [[elements objectForKey:@"numberOfFrames"] integerValue]);
            NSUInteger series = [[elements objectForKey:@"numberOfSeries"] unsignedIntegerValue];
            if (!elements || !series || frames > NSUIntegerMax / series) {
                [fileFailures setObject:@[NSLocalizedString(@"The anonymized file could not be parsed completely for import.", nil)] forKey:original];
                [NSException raise:@"AnonymizationImport" format:@"An anonymized file could not be parsed completely."];
            }
            [expectedCounts setObject:@(frames * series) forKey:destination];
            [progress incrementBy:1];
        }
        committed = [context performAtomicChanges:^BOOL(NSError **failure) {
            NSMutableArray *identifiers = [NSMutableArray array];
            for (NSUInteger offset = 0; offset < copiedPaths.count; offset += 32) {
                if (cancelled(failure)) return NO;
                NSArray *chunk = [copiedPaths subarrayWithRange:NSMakeRange(offset, MIN((NSUInteger)32, copiedPaths.count-offset))];
                NSArray *added = [target addFilesAtPaths:chunk postNotifications:YES dicomOnly:YES rereadExistingItems:YES generatedByOsiriX:YES importedFiles:NO returnArray:YES];
                if (!added) return NO;
                [identifiers addObjectsFromArray:added];
                [progress incrementBy:chunk.count];
            }
            if (cancelled(failure)) return NO;
            NSMutableSet *imported = [NSMutableSet set];
            NSMutableDictionary *counts = [NSMutableDictionary dictionary];
            for (NSManagedObjectID *identifier in identifiers) {
                DicomImage *image = (DicomImage *)[context existingObjectWithID:identifier error:failure];
                if (!image || image.isDeleted) return NO;
                NSString *path = image.completePath;
                if (![expectedCounts objectForKey:path]) return NO;
                if (![imported containsObject:image]) {
                    [imported addObject:image];
                    [counts setObject:@([[counts objectForKey:path] unsignedIntegerValue] + 1) forKey:path];
                }
            }
            if (![counts isEqualToDictionary:expectedCounts]) {
                for (NSString *path in expectedCounts) {
                    NSUInteger actual = [[counts objectForKey:path] unsignedIntegerValue];
                    NSUInteger expected = [[expectedCounts objectForKey:path] unsignedIntegerValue];
                    if (actual != expected)
                        [fileFailures setObject:@[[NSString stringWithFormat:NSLocalizedString(@"The importer retained %lu of %lu expected image records. The import batch was rolled back.", nil), (unsigned long)actual, (unsigned long)expected]] forKey:[originalForCopy objectForKey:path]];
                }
                if (failure) *failure = [NSError errorWithDomain:@"HorosAnonymizationImport" code:2 userInfo:
                    @{NSLocalizedDescriptionKey: NSLocalizedString(@"Not all anonymized files could be indexed. The import was rolled back and the original images were preserved.", nil)}];
                return NO;
            }
            if (replace) {
                NSMutableSet *series = [NSMutableSet set], *studies = [NSMutableSet set];
                for (DicomImage *image in captured) {
                    if ([imported containsObject:image]) continue; // unchanged SOP/frame reused in place
                    if (image.series) [series addObject:image.series];
                    if (image.series.study) [studies addObject:image.series.study];
                    [retired addObject:image];
                    [context deleteObject:image];
                }
                [context processPendingChanges];
                for (DicomSeries *item in series) {
                    if (![[item.images filteredSetUsingPredicate:[NSPredicate predicateWithFormat:@"isDeleted == NO"]] count])
                        [context deleteObject:item];
                    else { item.numberOfImages = @0; item.thumbnail = nil; }
                }
                [context processPendingChanges];
                for (DicomStudy *item in studies) {
                    if (![[item.series filteredSetUsingPredicate:[NSPredicate predicateWithFormat:@"isDeleted == NO"]] count])
                        [context deleteObject:item];
                    else item.numberOfImages = @0;
                }
            }
            return YES;
        } error:error];
    } @catch (NSException *exception) {
        if (error) *error = [NSError errorWithDomain:@"HorosAnonymizationImport" code:1 userInfo:@{NSLocalizedDescriptionKey: exception.reason ?: @"Anonymized images could not be imported."}];
    } @finally {
        [progress close];
        if (!committed)
            for (NSString *path in copiedPaths)
                [[NSFileManager defaultManager] removeItemAtPath:path error:NULL];
        if (!committed && error) {
            NSError *failure = *error ?: [NSError errorWithDomain:@"HorosAnonymizationImport" code:1 userInfo:
                @{NSLocalizedDescriptionKey: NSLocalizedString(@"The anonymized images could not be imported. The originals were preserved.", nil)}];
            NSMutableDictionary *info = [NSMutableDictionary dictionaryWithDictionary:failure.userInfo ?: @{}];
            BOOL cancelled = [failure.domain isEqualToString:NSCocoaErrorDomain] && failure.code == NSUserCancelledError;
            [info setObject:HorosAnonymizationFileResults(files.allKeys, fileFailures, cancelled) forKey:@"HorosAnonymizationFileResults"];
            *error = [NSError errorWithDomain:failure.domain code:failure.code userInfo:info];
        }
        if (error) [*error retain];
    }
    });
    if (error) [*error autorelease];
    if (committed) {
        for (ViewerController *viewer in [[[ViewerController getDisplayed2DViewers] copy] autorelease]) {
            for (DicomImage *image in [viewer fileList])
                if ([retired containsObject:image]) { [[viewer window] close]; break; }
        }
        [self outlineViewRefresh];
        [self refreshAlbums];
    }
    return committed;
}

-(void)anonymizationSavePanelDidEnd:(AnonymizationSavePanelController*)aspc
{
    NSArray* imagePaths = [aspc.representedObject objectAtIndex:0];
    NSArray* imageObjs = [aspc.representedObject objectAtIndex:1];
    
    switch (aspc.end)
    {
        case AnonymizationSavePanelSaveAs:
        {
            NSError *error = nil;
            NSDictionary *outputs = [Anonymization anonymizeFiles:imagePaths dicomImages:imageObjs toPath:aspc.outputDir withTags:aspc.anonymizationViewController.tagsValues error:&error];
            if (!HorosAnonymizationOutputsComplete(imagePaths, outputs) &&
                !([error.domain isEqualToString:NSCocoaErrorDomain] && error.code == NSUserCancelledError))
                [HorosAnonymizationErrorPresenter presentError:error];
        }
            break;
            
        case AnonymizationSavePanelAdd:
        case AnonymizationSavePanelReplace:
        {
            NSError *temporaryError = nil;
            NSString *tempDir = HorosCreateAnonymizationStagingDirectory(NSTemporaryDirectory(), &temporaryError);
            if (!tempDir) {
                HorosRunAlertPanel(NSLocalizedString(@"Anonymize Error", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil, temporaryError.localizedDescription);
                break;
            }
            NSError *anonymizationError = nil;
            NSDictionary* anonymizedFiles = [Anonymization anonymizeFiles:imagePaths dicomImages: imageObjs toPath:tempDir withTags:aspc.anonymizationViewController.tagsValues error:&anonymizationError];
            
            if (!HorosAnonymizationOutputsComplete(imagePaths, anonymizedFiles)) {
                if (!([anonymizationError.domain isEqualToString:NSCocoaErrorDomain] && anonymizationError.code == NSUserCancelledError))
                    [HorosAnonymizationErrorPresenter presentError:anonymizationError];
                [[NSFileManager defaultManager] removeItemAtPath:tempDir error:NULL];
                break;
            }

            NSError *importError = nil;
            if (![self importAnonymizedFiles:anonymizedFiles originalImages:imageObjs replace:aspc.end == AnonymizationSavePanelReplace error:&importError] &&
                !([importError.domain isEqualToString:NSCocoaErrorDomain] && importError.code == NSUserCancelledError)) {
                [HorosAnonymizationErrorPresenter presentError:importError];
            }
            [[NSFileManager defaultManager] removeItemAtPath:tempDir error:NULL];
        }
            break;
    }
}

#endif

- (void) unmountPath:(NSString*) path
{
    [_sourcesTableView display];
    
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
    
    [_sourcesTableView display];
    [_sourcesTableView setNeedsDisplay:YES];
    
    if( attempts == 5)
    {
        HorosRunCriticalAlertPanel(NSLocalizedString(@"Failed", nil), NSLocalizedString(@"Unable to unmount this disk. This disk is probably in used by another application.", nil), NSLocalizedString(@"OK",nil),nil, nil);
    }
}

- (void)alternateButtonPressed: (NSNotification*)n
{
    int i = [_sourcesTableView selectedRow];
    if( i > 0)
    {
        NSString *path = [[[bonjourBrowser services] objectAtIndex: i-1] valueForKey:@"Path"];
        
        [self resetToLocalDatabase];
        [self unmountPath: path];
    }
}

#ifndef OSIRIX_LIGHT

#endif

- (void) selectServer: (NSArray*)objects
{
    if( [objects count] > 0) [SendController sendFiles: objects];
    else HorosRunCriticalAlertPanel(NSLocalizedString(@"DICOM Send",nil),NSLocalizedString( @"No files are selected...",nil),NSLocalizedString( @"OK",nil), nil, nil);
}

- (void)export2PACS: (id)sender
{
    [self.window makeKeyAndOrderFront:sender];
    
    NSMutableArray	*objects = [NSMutableArray array];
    NSMutableArray  *files;
    
    if( ([sender isKindOfClass:[NSMenuItem class]] && [sender menu] == [oMatrix menu]) || [[self window] firstResponder] == oMatrix)
        files = [self filesForDatabaseMatrixSelection:objects onlyImages: NO];
    else
        files = [self filesForDatabaseOutlineSelection:objects onlyImages: NO];
    
    [self selectServer: objects];
}

#ifndef OSIRIX_LIGHT
- (IBAction)querySelectedStudy: (id)sender
{
    //	if( DICOMDIRCDMODE)
    //	{
    //		HorosRunInformationalAlertPanel(NSLocalizedString(@"OsiriX CD/DVD", nil), NSLocalizedString(@"OsiriX is running in read-only mode, from a CD/DVD.", nil), NSLocalizedString(@"OK",nil), nil, nil);
    //		return;
    //	}
    
    [self.window makeKeyAndOrderFront:sender];
    
    if( [QueryController currentQueryController] == nil) [[QueryController alloc] initAutoQuery : NO];
    
    [[QueryController currentQueryController] showWindow:self];
    
    // *****
    
    NSIndexSet			*index = [databaseOutline selectedRowIndexes];
    NSManagedObject		*item = [databaseOutline itemAtRow:[index firstIndex]];
    NSManagedObject		*studySelected;
    
    if (item)
    {
        if ([[item valueForKey: @"type"] isEqualToString:@"Study"])
            studySelected = item;
        else
            studySelected = [item valueForKey:@"study"];
        
        [[QueryController currentQueryController] queryPatientID: [studySelected valueForKey:@"patientID"]];
    }
}

- (void)queryDICOM: (id) sender
{
    //	if( DICOMDIRCDMODE)
    //	{
    //		HorosRunInformationalAlertPanel(NSLocalizedString(@"OsiriX CD/DVD", nil), NSLocalizedString(@"OsiriX is running in read-only mode, from a CD/DVD.", nil), NSLocalizedString(@"OK",nil), nil, nil);
    //		return;
    //	}
    
    if ([[[NSApplication sharedApplication] currentEvent] modifierFlags]  & NSEventModifierFlagShift)	// Query selected patient
        [self querySelectedStudy: self];
    else
    {
        
        if ([sender tag] == 0 && [QueryController currentQueryController] == nil)
            [[QueryController alloc] initAutoQuery: NO];
        else if ([sender tag] == 1 && [QueryController currentAutoQueryController] == nil)
            [[QueryController alloc] initAutoQuery: YES];
        
        if( [sender tag] == 0)
            [[QueryController currentQueryController] showWindow:self];
        
        if( [sender tag] == 1)
            [[QueryController currentAutoQueryController] showWindow:self];
    }
}
#endif

- (void)storeSCPComplete: (id)sender
{
    //release storescp when done
    [sender release];
}

#ifndef OSIRIX_LIGHT
- (IBAction)importRawData:(id)sender
{
    [[rdPatientForm cellWithTag:0] setStringValue: @"Raw Data"]; //Patient Name
    [[rdPatientForm cellWithTag:1] setStringValue: @"RD0001"];	//Patient ID
    [[rdPatientForm cellWithTag:2] setStringValue: @"Raw Data Secondary Capture"]; //Study Descripition
    
    [[rdPixelForm cellWithTag:0] setObjectValue:[NSNumber numberWithInt:512]];		//rows
    [[rdPixelForm cellWithTag:1] setObjectValue:[NSNumber numberWithInt:512]];		//columns
    [[rdPixelForm cellWithTag:2] setObjectValue:[NSNumber numberWithInt:1]];		//slices
    
    [[rdVoxelForm cellWithTag:0] setObjectValue:[NSNumber numberWithInt:1]];		//voxel width
    [[rdVoxelForm cellWithTag:1] setObjectValue:[NSNumber numberWithInt:1]];		//voxel height
    [[rdVoxelForm cellWithTag:2] setObjectValue:[NSNumber numberWithInt:1]];		//voxel depth
    
    [[rdOffsetForm cellWithTag:0] setObjectValue:[NSNumber numberWithInt:0]];		//offset
    
    NSOpenPanel *openPanel = [NSOpenPanel openPanel];
    [openPanel setAccessoryView:rdAccessory];
    [openPanel setPrompt:NSLocalizedString(@"Import", nil)];
    [openPanel setTitle:NSLocalizedString(@"Import Raw Data", nil)];
    
    [openPanel setMessage:NSLocalizedString(@"Choose file containing raw data:", nil)];
    
    if ([openPanel runModal] == NSModalResponseOK)
    {
        NSData *data = [NSData dataWithContentsOfFile:openPanel.URL.path];
        if (data)
        {
            NSString *patientName = [[rdPatientForm cellWithTag:0] stringValue];
            NSString *patientID = [[rdPatientForm cellWithTag:1] stringValue];
            NSString *studyDescription = [[rdPatientForm cellWithTag:2] stringValue];
            
            NSNumber *rows = [[rdPixelForm cellWithTag:0] objectValue];
            NSNumber *columns = [[rdPixelForm cellWithTag:1] objectValue];
            NSNumber *slices = [[rdPixelForm cellWithTag:2] objectValue];
            
            NSNumber *width = [[rdVoxelForm cellWithTag:0] objectValue];
            NSNumber *height = [[rdVoxelForm cellWithTag:1] objectValue];
            NSNumber *depth = [[rdVoxelForm cellWithTag:2] objectValue];
            
            NSNumber *offset = [[rdOffsetForm cellWithTag:0] objectValue];
            
            int pixelType = [(NSCell *)[rdPixelTypeMatrix selectedCell] tag];
            
            NSUInteger spp;
            NSUInteger highBit = 7;
            NSUInteger bitsAllocated = 8;
            NSUInteger numberBytes;
            BOOL isSigned = YES;
            BOOL isLittleEndian = YES;
            NSString *photometricInterpretation = @"MONOCHROME2";
            switch (pixelType)
            {
                case 0:  spp = 3;
                    numberBytes = 1;
                    photometricInterpretation = @"RGB";
                    break;
                case 1: spp = 1;
                    numberBytes = 1;
                    break;
                case 2:	spp = 1;
                    numberBytes = 2;
                    highBit = 15;
                    bitsAllocated = 16;
                    isSigned = NO;
                    break;
                case 3:	spp = 1;
                    numberBytes = 2;
                    highBit = 15;
                    bitsAllocated = 16;
                    break;
                case 4:	spp = 1;
                    numberBytes = 2;
                    highBit = 15;
                    bitsAllocated = 16;
                    isSigned = NO;
                    isLittleEndian = NO;
                    break;
                case 5:	spp = 1;
                    numberBytes = 2;
                    highBit = 15;
                    bitsAllocated = 16;
                    isSigned = YES;
                    isLittleEndian = NO;
                    break;
                case 6: spp = 1;
                    numberBytes = 4;
                    highBit = 31;
                    bitsAllocated = 32;
                    isSigned = YES;
                    isLittleEndian = YES;
                    break;
                    
                default:	spp = 1;
                    numberBytes = 2;
            }
            
            NSUInteger subDataLength = spp  * numberBytes * [rows unsignedIntegerValue] * [columns unsignedIntegerValue];
            
            if ([data length] >= subDataLength * [slices unsignedIntegerValue]  + [offset unsignedIntegerValue])
            {
                NSUInteger s = [slices unsignedIntegerValue];
                
                //tmpObject for StudyUID andd SeriesUID
                
                // Written by DCMTK (#738): one Secondary Capture per slice, with
                // the attributes the DCM Framework's secondary capture factory set.
                NSString *studyUID = [HorosDICOMWriter newStudyInstanceUID];
                NSString *seriesUID = [HorosDICOMWriter newSeriesInstanceUID];
                int studyID = [[NSUserDefaults standardUserDefaults] integerForKey:@"SCStudyID"];
                DCMCalendarDate *studyDate = [DCMCalendarDate date];
                DCMCalendarDate *seriesDate = [DCMCalendarDate date];
                [[NSUserDefaults standardUserDefaults] setInteger:(++studyID) forKey:@"SCStudyID"];
                for(NSUInteger i = 0; i < s; i++)
                {
                    HorosDICOMWriter *dcmObject = [[[HorosDICOMWriter alloc] init] autorelease];
                    [dcmObject setValues:@[[DCMAbstractSyntaxUID secondaryCaptureImageStorage]] forName:@"SOPClassUID"];
                    [dcmObject setValues:@[[HorosDICOMWriter newSOPInstanceUID]] forName:@"SOPInstanceUID"];
                    [dcmObject setValues:@[@"Isis DICOM Viewer"] forName:@"Manufacturer"];
                    [dcmObject setValues:@[[DCMObject MACAddress]] forName:@"SecondaryCaptureDeviceID"];
                    [dcmObject setValues:@[@"Isis DICOM Viewer"] forName:@"SecondaryCaptureDeviceManufacturer"];
                    [dcmObject setValues:@[@"Isis DICOM Viewer"] forName:@"SecondaryCaptureDeviceManufacturersModelName"];
                    [dcmObject setValues:@[@"3.8"] forName:@"SecondaryCaptureDeviceSoftwareVersions"];
                    [dcmObject setValues:@[[DCMCalendarDate date]] forName:@"DateofSecondaryCapture"];
                    [dcmObject setValues:@[[DCMCalendarDate date]] forName:@"TimeofSecondaryCapture"];
                    [dcmObject setValues:@[@"SC"] forName:@"Modality"];
                    [dcmObject setValues:@[] forName:@"SeriesDescription"];
                    // Type 2C in General Series and General Image: present, empty.
                    [dcmObject setValues:@[] forName:@"Laterality"];
                    [dcmObject setValues:@[] forName:@"PatientOrientation"];
                    DCMCalendarDate *aquisitionDate = [DCMCalendarDate date];
                    //add attributes
                    [dcmObject setValues:[NSMutableArray arrayWithObject:studyUID] forName:@"StudyInstanceUID"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:seriesUID] forName:@"SeriesInstanceUID"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:patientName] forName:@"PatientsName"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:patientID] forName:@"PatientID"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:studyDescription] forName:@"StudyDescription"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSString stringWithFormat:@"%d", (int) i]] forName:@"InstanceNumber"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSString stringWithFormat:@"%d", studyID]] forName:@"StudyID"];
                    
                    [dcmObject setValues:[NSMutableArray arrayWithObject:studyDate] forName:@"StudyDate"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:studyDate] forName:@"StudyTime"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:seriesDate] forName:@"SeriesDate"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:seriesDate] forName:@"SeriesTime"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:aquisitionDate] forName:@"AcquisitionDate"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:aquisitionDate] forName:@"AcquisitionTime"];
                    
                    [dcmObject setValues:[NSMutableArray arrayWithObject:@"101"] forName:@"SeriesNumber"];
                    
                    [dcmObject setValues:[NSMutableArray arrayWithObject:rows] forName:@"Rows"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:columns] forName:@"Columns"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSNumber numberWithInt:spp]] forName:@"SamplesperPixel"];
                    [dcmObject setValues:[NSMutableArray arrayWithObjects:[NSString stringWithFormat:@"%f", [width floatValue]], [NSString stringWithFormat:@"%f",  [height floatValue]], nil] forName:@"PixelSpacing"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSString stringWithFormat:@"%f", [depth floatValue]]] forName:@"SliceThickness"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:photometricInterpretation] forName:@"PhotometricInterpretation"];
                    
                    float slicePosition = i * [depth floatValue];
                    NSMutableArray *positionArray = [NSMutableArray arrayWithObjects:[NSString stringWithFormat:@"%f", 0.0], [NSString stringWithFormat:@"%f", 0.0], [NSString stringWithFormat:@"%f", slicePosition], nil];
                    NSMutableArray *orientationArray = [NSMutableArray arrayWithObjects:[NSString stringWithFormat:@"%f", 1.0], [NSString stringWithFormat:@"%f", 0.0], [NSString stringWithFormat:@"%f", 0.0], [NSString stringWithFormat:@"%f", 0.0], [NSString stringWithFormat:@"%f", 1.0], [NSString stringWithFormat:@"%f", 0.0], nil];
                    
                    [dcmObject setValues:positionArray forName:@"ImagePositionPatient"];
                    [dcmObject setValues:orientationArray forName:@"ImageOrientationPatient"];
                    
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSNumber numberWithBool:isSigned]] forName:@"PixelRepresentation"];
                    
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSNumber numberWithInt:highBit]] forName:@"HighBit"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSNumber numberWithInt:bitsAllocated]] forName:@"BitsAllocated"];
                    [dcmObject setValues:[NSMutableArray arrayWithObject:[NSNumber numberWithInt:bitsAllocated]] forName:@"BitsStored"];
                    
                    //add Pixel data
                    NSString *vr = @"OW";
                    if (numberBytes < 2)
                        vr = @"OB";
                    
                    NSRange range = NSMakeRange([offset unsignedIntegerValue] + subDataLength * i, subDataLength);
                    
                    NSMutableData *subdata = [NSMutableData dataWithData:[data subdataWithRange:range]];
                    
                    if (isLittleEndian == NO)
                    {
                        if( isSigned == NO)
                        {
                            unsigned short *ptr = (unsigned short*) [subdata mutableBytes];
                            NSUInteger l = subDataLength/2;
                            while( l-- > 0)
                                ptr[ l] = EndianU16_BtoL( ptr[ l]);
                        }
                        else
                        {
                            short *ptr = ( short*) [subdata mutableBytes];
                            NSUInteger l = subDataLength/2;
                            while( l-- > 0)
                                ptr[ l] = EndianS16_BtoL( ptr[ l]);
                        }
                    }
                    
                    [dcmObject setData:subdata forName:@"PixelData" vr:vr];
                    
                    NSString *tempFilename = [_database.incomingDirPath stringByAppendingPathComponent: [NSString stringWithFormat:@"%d.dcm", (int) i]];
                    [dcmObject writeToFile:tempFilename transferSyntax:@"1.2.840.10008.1.2"];
                } 
            }
            else
                NSLog(@"Not enough data");
        }
    }
}

- (IBAction) viewXML:(id) sender
{
    XMLController * xmlController = [[XMLController alloc] initWithImage: [self firstObjectForDatabaseMatrixSelection]
                                                              windowName:[NSString stringWithFormat: NSLocalizedString( @"Meta-Data: %@", nil), [[self firstObjectForDatabaseMatrixSelection] valueForKey:@"completePath"]]
                                                                  viewer: nil];
    
    [xmlController showWindow:self];
}
#endif

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark -
#pragma mark RTSTRUCT

#ifndef OSIRIX_LIGHT
- (void)createROIsFromRTSTRUCT: (id)sender
{
    NSMutableArray *filesArray = [NSMutableArray array];
    NSMutableArray *filePaths = [self filesForDatabaseMatrixSelection: filesArray];
    
    for( int i = 0; i < [filesArray count]; i++)
    {
        NSString *modality = [[filesArray objectAtIndex: i] valueForKey: @"modality"];
        if( [modality isEqualToString: @"RTSTRUCT"])
        {
            DCMObject *dcmObj = [HorosDCMTKObject objectWithContentsOfFile: [filePaths objectAtIndex: i ]];
            
            DCMPix *pix = nil;
            @synchronized( previewPixThumbnails)
            {
                pix = [previewPix objectAtIndex: 0];  // Should only be one DCMPix associated w/ an RTSTRUCT
            }
            
            [pix createROIsFromRTSTRUCT: dcmObj];
        }
    }
}
#endif

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark -
#pragma mark Report functions

// Implemented in Swift since #831, with the same selectors: BrowserController+Reports.swift.


#pragma mark-
#pragma mark Toolbar functions

// Implemented in Swift since #831, with the same selectors: BrowserController+Toolbar.swift.


//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark Bonjour

- (void)setBonjourDatabaseValue:(NSManagedObject*) obj value:(id) value forKey:(NSString*) key // __deprecated
{
    [(RemoteDicomDatabase*)_database object:obj setValue:value forKey:key];
}

-(NSString*)askPassword
{
    [password setStringValue:@""];
    
    [self.window beginSheet:bonjourPasswordWindow completionHandler:nil];
    
    int result = [NSApp runModalForWindow:bonjourPasswordWindow];
    [bonjourPasswordWindow makeFirstResponder: nil];
    
    [bonjourPasswordWindow.sheetParent endSheet:bonjourPasswordWindow];
    [bonjourPasswordWindow orderOut: self];
    
    if( result == NSModalResponseStop)
    {
        return [password stringValue];
    }
    
    return nil;
}

- (NSString*)getLocalDCMPath: (NSManagedObject*)obj : (long)no
{
    if (![_database isLocal]) return [(RemoteDicomDatabase*)_database cacheDataForImage:(DicomImage*)obj maxFiles:no];
    else return [obj valueForKey:@"completePath"];
}

- (void)displayBonjourServices
{
    [_sourcesTableView reloadData];
}

- (void) switchToDefaultDBIfNeeded // __deprecated
{
    [self resetToDefaultDatabaseIfNecessary];
}

- (void)resetToDefaultDatabaseIfNecessary
{
    NSString *defaultPath = [DicomDatabase baseDirPathForMode: (int)[[NSUserDefaults standardUserDefaults] integerForKey: @"DEFAULT_DATABASELOCATION"] path: [[NSUserDefaults standardUserDefaults] stringForKey: @"DEFAULT_DATABASELOCATIONURL"]];
    
    if( [[self.database baseDirPath] isEqualToString: defaultPath] == NO)
        [self resetToLocalDatabase];
}

- (void)openDatabasePath: (NSString*)path
{
    NSThread* thread = [NSThread currentThread];
    [thread setName:NSLocalizedString(@"Opening database...", nil)];
    ThreadModalForWindowController* tmc = [thread startModalForWindow:self.window];
    
    @try
    {
        NSString *indexPath = [[DicomDatabase baseDirPathForPath:path] stringByAppendingPathComponent:@"Database.sql"];
        if ([NSFileManager.defaultManager fileExistsAtPath:indexPath] && !HorosIsDatabaseFile(indexPath))
            [NSException raise:NSGenericException format:@"The selected folder contains an unrecognized database index."];
        DicomDatabase* db = [DicomDatabase databaseAtPath:path];
        if( db)
            [self setDatabase:db];
        else
            [NSException raise:NSGenericException format: @"DicomDatabase == nil"];
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
        HorosRunAlertPanel(NSLocalizedString(@"Isis DICOM Viewer Database", nil), NSLocalizedString( @"Isis DICOM Viewer cannot read/create this file/folder. Permissions error?", nil), nil, nil, nil);
        [self resetToLocalDatabase];
    }
    
    [tmc invalidate];
}


- (NSString*) localDatabasePath { // deprecated
    return [[DicomDatabase activeLocalDatabase] sqlFilePath];
}

//???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

#pragma mark-
#pragma mark Plugins

// Implemented in Swift since #831, with the same selectors: BrowserController+Plugins.swift.


@end

// The file-scope statics the Swift extensions of #831 read or write, declared
// in BrowserController+SwiftIvars.h.
@implementation BrowserController (SwiftStatics)

+(NSMenu*)horos_contextualMenu
{
    return contextual;
}

+(void)setHoros_contextualMenu:(NSMenu*)menu
{
    [menu retain];
    [contextual release];
    contextual = menu;
}

+(NSMenu*)horos_contextualRTMenu
{
    return contextualRT;
}

+(void)setHoros_contextualRTMenu:(NSMenu*)menu
{
    [menu retain];
    [contextualRT release];
    contextualRT = menu;
}

+(BOOL)horos_waitForRunningProcess
{
    return waitForRunningProcess;
}

+(BOOL)horos_dontShowOpenSubSeries
{
    return dontShowOpenSubSeries;
}

+(void)setHoros_dontShowOpenSubSeries:(BOOL)value
{
    dontShowOpenSubSeries = value;
}

+(BOOL)horos_withReset
{
    return withReset;
}

+(HorosPreviewFrame*)horos_previewFrameForImage:(DicomImage*)image frame:(int)frame
{
    return HorosPreviewFrameForImage( image, frame);
}

@end

#pragma mark Patient list album (#703)

// An album from a list of patients in an image: the window, the parsing and the
// decisions are Swift (PatientListAlbumWindow.swift, PatientListImport.swift);
// the database and the Query/Retrieve are here. No name or identifier is logged.
@interface BrowserController (HorosPatientListAlbum) <HorosPatientListAlbumHost>
@end

@implementation BrowserController (HorosPatientListAlbum)

- (IBAction)createAlbumFromPatientListImage:(id)sender
{
    if (_database.isLocal == NO)
    {
        NSBeep();
        return;
    }
    [HorosPatientListAlbumWindowController beginWithHost: self parent: self.window];
}

- (NSArray *)patientListCandidatesForIdentifier:(NSString *)identifier name:(NSString *)name
{
    NSMutableArray *predicates = [NSMutableArray array];
    NSString *trimmed = [identifier stringByTrimmingCharactersInSet: [NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (trimmed.length)
        [predicates addObject: [NSPredicate predicateWithFormat: @"patientID ==[c] %@", trimmed]];
    // Every word of the name, anywhere in the stored one: the list may say
    // "Given Family" where DICOM says "FAMILY^GIVEN". The leading * is how
    // patientsnamePredicate: is asked for that.
    NSArray *words = [HorosPatientListMatching searchWords: name ?: @""];
    if (words.count)
        [predicates addObject: [self patientsnamePredicate: [@"*" stringByAppendingString: [words componentsJoinedByString: @" "]] soundex: NO]];
    if (predicates.count == 0)
        return @[];
    
    NSMutableArray *candidates = [NSMutableArray array];
    NSManagedObjectContext *context = _database.managedObjectContext;
    N2ManagedObjectContextPerformAndWait(context, ^{
    @try
    {
        NSArray *found = [_database objectsForEntity: _database.studyEntity predicate: [NSCompoundPredicate orPredicateWithSubpredicates: predicates]];
        NSMutableSet *patients = [NSMutableSet set], *studies = [NSMutableSet setWithArray: found];
        for (DicomStudy *study in found)
            if ([study isKindOfClass: [DicomStudy class]] && study.patientUID.length)
                [patients addObject: study.patientUID];
        // The patient's other studies, as the browser gathers them.
        if (patients.count)
            [studies addObjectsFromArray: [_database objectsForEntity: _database.studyEntity predicate: [NSPredicate predicateWithFormat: @"patientUID IN %@", patients]]];
        for (DicomStudy *study in studies)
        {
            if ([study isKindOfClass: [DicomStudy class]] == NO)
                continue;
            [candidates addObject: @{@"objectID": study.objectID,
                                     @"patientUID": study.patientUID ?: @"",
                                     @"patientID": study.patientID ?: @"",
                                     @"name": study.name ?: @"",
                                     @"dateOfBirth": study.dateOfBirth ?: (id)[NSNull null],
                                     @"sex": study.patientSex ?: @"",
                                     @"date": study.date ?: (id)[NSNull null]}];
        }
    }
    @catch (NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    });
    return candidates;
}

- (NSString *)patientListCreateAlbumNamed:(NSString *)name studies:(NSArray *)studyIDs expected:(NSArray *)expected error:(NSError **)error
{
    __block NSString *created = nil, *problem = nil;
    __block DicomAlbum *album = nil;
    NSManagedObjectContext *context = _database.managedObjectContext;
    N2ManagedObjectContextPerformAndWait(context, ^{
    @try
    {
        // What the user reviewed must still be what is stored: another import,
        // a merge or an edit may have changed a study since.
        NSMutableArray *studies = [NSMutableArray array];
        for (NSUInteger i = 0; i < studyIDs.count && problem == nil; i++)
        {
            DicomStudy *study = (DicomStudy *) [context existingObjectWithID: studyIDs[i] error: NULL];
            if (study)
                [context refreshObject: study mergeChanges: YES];
            NSDictionary *reviewed = i < expected.count ? expected[i] : nil;
            if ([study isKindOfClass: [DicomStudy class]] == NO || study.isDeleted ||
                [(study.patientID ?: @"") isEqualToString: reviewed[@"patientID"] ?: @""] == NO ||
                [(study.name ?: @"") isEqualToString: reviewed[@"name"] ?: @""] == NO)
                problem = NSLocalizedString(@"A study changed or was deleted after the list was reviewed. Review the list again.", nil);
            else
                [studies addObject: study];
        }
        if (problem == nil)
        {
            NSArray *names = [[_database objectsForEntity: _database.albumEntity] valueForKey: @"name"];
            NSString *unique = name;
            int n = 2;
            while ([names containsObject: unique])
                unique = [NSString stringWithFormat: @"%@ #%d", name, n++];
            album = [NSEntityDescription insertNewObjectForEntityForName: @"Album" inManagedObjectContext: context];
            album.name = unique;
            [_database addStudies: studies toAlbum: album];
            [_database save];
            created = unique;
        }
    }
    @catch (NSException *e)
    {
        N2LogExceptionWithStackTrace(e);
        problem = e.reason ?: NSLocalizedString(@"The album could not be saved.", nil);
    }
    [created retain];
    [problem retain];
    [album retain];
    });
    [created autorelease];
    [problem autorelease];
    [album autorelease];
    if (created)
    {
        [self refreshAlbums];
        NSInteger index = [self.albumArray indexOfObject: album];
        if (index != NSNotFound)
            [albumTable selectRowIndexes: [NSIndexSet indexSetWithIndex: index] byExtendingSelection: NO];
        [self outlineViewRefresh];
    }
    else if (error)
        *error = [NSError errorWithDomain: @"HorosPatientListAlbum" code: 1 userInfo: @{NSLocalizedDescriptionKey: problem ?: @""}];
    return created;
}

- (void)patientListQueryPACSWithIdentifier:(NSString *)identifier name:(NSString *)name
{
#ifndef OSIRIX_LIGHT
    if ([QueryController currentQueryController] == nil)
        [[QueryController alloc] initAutoQuery: NO];
    QueryController *query = [QueryController currentQueryController];
    [query showWindow: self];
    if (identifier.length)
        [query queryPatientID: identifier];
    else if (name.length)
        [query queryPatientName: name];
#endif
}

@end
