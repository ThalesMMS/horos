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

#import "HorosFileCopy.h"
#import "Horos-Swift.h"
#import <objc/message.h>
#import <objc/runtime.h>
#import "DicomDatabase.h"
#import "HorosImportFileSafety.h"
#import "HorosReportFileReplacement.h"
#import "NSString+N2.h"
#import "NSString+SymlinksAndAliases.h"
#import "Notifications.h"
#import "DicomAlbum.h"
#import "NSException+N2.h"
#import "N2MutableUInteger.h"
#import "NSFileManager+N2.h"
#import "N2Debug.h"
#import "HorosDerivedUID.h"
#import "DicomImage.h"
#import "DicomStudy.h"
#import "DicomSeries.h"
#import "DicomFile.h"
#import "DicomFileDCMTKCategory.h"
#import "Reports.h"
#import "ThreadsManager.h"
#import "AppController.h"
#import "NSDictionary+N2.h"
#import "BrowserControllerDCMTKCategory.h"
#import "PluginManager.h"
#import "NSThread+N2.h"
#import "NSArray+N2.h"
#import "DicomDatabase+DCMTK.h"
#import "NSError+OsiriX.h"
#import "DCMAbstractSyntaxUID.h"
#import "DCMTKStudyQueryNode.h"
#import "N2Debug.h"
#import "NSUserDefaults+OsiriX.h"
#import "DataNodeIdentifier.h"
#import "NSThread+N2.h"
#import "N2Stuff.h"
#import "ThreadModalForWindowController.h"
#import "NSNotificationCenter+N2.h"
#import "Wait.h"
#import "WaitRendering.h"
#import "SRAnnotation.h"
#import "DicomDatabase+Clean.h"
#import "DicomDatabase+Routing.h"
#include <copyfile.h>

NSString* const CurrentDatabaseVersion = @"2.5";


@interface DicomDatabase ()

@property(readwrite,retain) NSString* baseDirPath;
@property(readwrite,retain) NSString* dataBaseDirPath;
@property(readonly,retain) N2MutableUInteger* dataFileIndex;
@property(readonly,retain) NSRecursiveLock* processFilesLock;
@property(readonly,retain) NSRecursiveLock* importFilesFromIncomingDirLock;
@property(readonly) NSMutableArray* compressQueue;
@property(readonly) NSMutableArray* decompressQueue;
@property(assign) NSThread* compressDecompressThread;

+(NSString*)sqlFilePathForBasePath:(NSString*)basePath;
-(void)modifyDefaultAlbums;
+(void)recomputePatientUIDsInContext:(NSManagedObjectContext*)context;
+(void)repairEmptySeriesIdentifiersInContext:(NSManagedObjectContext*)context;
+(void)repairFabricatedPatientIdentifiersInContext:(NSManagedObjectContext*)context;
-(BOOL)upgradeSqlFileFromModelVersion:(NSString*)databaseModelVersion;

@end

@implementation DicomDatabase

+(void)initializeDicomDatabaseClass {
    [NSUserDefaultsController.sharedUserDefaultsController addObserver:(id)self forValuesKey:OsirixCanActivateDefaultDatabaseOnlyDefaultsKey options:NSKeyValueObservingOptionInitial context:[DicomDatabase class]];
}

+(void)observeValueForKeyPath:(NSString*)keyPath ofObject:(id)object change:(NSDictionary*)change context:(void*)context {
    if (context == [DicomDatabase class]) {
        if ([keyPath isEqualToString:valuesKeyPath(OsirixCanActivateDefaultDatabaseOnlyDefaultsKey)]) {
            if ([NSUserDefaults canActivateOnlyDefaultDatabase])
                [self setActiveLocalDatabase:self.defaultDatabase];
        }
    }
}

static NSString* const SqlFileName = @"Database.sql";
NSString* const OsirixDataDirName = @"Horos Data";
NSString* const O2ScreenCapturesSeriesName = NSLocalizedString(@"OsiriX Screen Captures", nil);;

+(NSString*)baseDirPathForPath:(NSString*)path {
    // A folder that carries the data directory's name only when it has not been
    // renamed; a backup usually has been. HorosDatabaseLocation also recognises
    // a folder by the index inside it, and the index file itself.
    return [HorosDatabaseLocation baseDirectoryForPath: path];
}

+(NSString*)baseDirPathForMode:(int)mode path:(NSString*)path {
    switch (mode) {
        case 0:
            path = [[[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:kUserDomain] firstObject] path];
#ifdef MACAPPSTORE
            NSString* temp = [self baseDirPathForPath:path];
            BOOL isDir;
            if (![NSFileManager.defaultManager fileExistsAtPath:temp isDirectory:&isDir] || !isDir)
                path = [NSFileManager.defaultManager userApplicationSupportFolderForApp];
#endif
            break;
        case 1:
            break;
        default:
            path = nil;
            break;
    }
    
    path = [self baseDirPathForPath:path];
    if (!path)
        N2LogError(@"nil path");
    else {
        NSArray *pathSeparated = [path componentsSeparatedByString:@"/"];
        
        if( pathSeparated.count >= 3)
        {
            NSString* volPath = [[pathSeparated subarrayWithRange:NSMakeRange(0,3)] componentsJoinedByString:@"/"];
            
            if ([path hasPrefix:@"/Volumes/"] && ![NSFileManager.defaultManager fileExistsAtPath:volPath])
                return nil; // not mounted
        }
        
        // Reopening a database that moved and creating one are different events,
        // and the folder that was chosen is not always the one that ends up
        // being used. Say which, once, where the location is decided.
        BOOL existing = [HorosDatabaseLocation pathHoldsExistingDatabase: path];
        [NSFileManager.defaultManager confirmDirectoryAtPath:path];
        // This is asked repeatedly for the same location; say it when it changes.
        static NSString *lastReportedLocation = nil;
        @synchronized( [DicomDatabase class])
        {
            if( [lastReportedLocation isEqualToString: path] == NO)
            {
                [lastReportedLocation release];
                lastReportedLocation = [path copy];
                NSLog( @"---- database location: %@ (%@)", path, existing? @"opening the database already there" : @"no index there yet; a new database will be created");
            }
        }
    }
    
    return path;
}

+(NSString*)defaultBaseDirPath {
    NSString* path = nil;
    @try {
        path = [self baseDirPathForMode:[[NSUserDefaults standardUserDefaults] integerForKey:@"DATABASELOCATION"] path:[[NSUserDefaults standardUserDefaults] stringForKey: @"DATABASELOCATIONURL"]];
        if (!path || ![[NSFileManager defaultManager] fileExistsAtPath:path]) {	// STILL NOT AVAILABLE?? Use the default folder.. and reset this strange URL..
            [[NSUserDefaults standardUserDefaults] setInteger: 0 forKey: @"DATABASELOCATION"];
            [[NSUserDefaults standardUserDefaults] setInteger: 0 forKey: @"DEFAULT_DATABASELOCATION"];
            path = [self baseDirPathForMode:[[NSUserDefaults standardUserDefaults] integerForKey:@"DATABASELOCATION"] path:[[NSUserDefaults standardUserDefaults] stringForKey: @"DATABASELOCATIONURL"]];
        }
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    }
    
    return path;
}

#pragma Factory

static DicomDatabase* defaultDatabase = nil;

+(DicomDatabase*)defaultDatabase {
    // Nib loading can request the database before first-use setup is complete.
    if ([HorosDatabaseFirstUse hasPendingChoice]) return nil;
    @synchronized(self) {
        if (!defaultDatabase)
        {
            WaitRendering *w = nil;
            
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"eraseEntireDBAtStartup"])
            {
                NSString *databaseDir = [[[self defaultBaseDirPath] stringByAppendingPathComponent:@"DATABASE.noindex"] stringByResolvingSymlinksAndAliases];
                
                if( [NSThread isMainThread])
                {
                    w = [[[WaitRendering alloc] init:NSLocalizedString(@"Erase Entire Database...", nil)] autorelease];
                    [w showWindow:self];
                }
                
                [[NSFileManager defaultManager] removeItemAtPath: databaseDir  error: nil];
                [[NSFileManager defaultManager] createDirectoryAtPath: databaseDir withIntermediateDirectories: NO attributes: nil error: nil];
            }
            
            NSString *dbName = nil;
            
            for( NSDictionary *d in [[NSUserDefaults standardUserDefaults] objectForKey:@"localDatabasePaths"])
            {
                if( [[d valueForKey:@"Path"] isEqualToString: [[self defaultBaseDirPath] stringByDeletingLastPathComponent]])
                    dbName = [d valueForKey: @"Description"];
            }
            
            if( dbName == nil)
                dbName = [[[[self defaultBaseDirPath] stringByDeletingLastPathComponent] lastPathComponent] stringByAppendingString: NSLocalizedString( @" DB", @"DB = DataBase")];
            
            defaultDatabase = [[self databaseAtPath:[self defaultBaseDirPath] name: dbName] retain];
            
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"eraseEntireDBAtStartup"])
            {
                NSArray *studies = [defaultDatabase objectsForEntity: defaultDatabase.studyEntity];
                
                for (DicomStudy *study in studies)
                    [defaultDatabase.managedObjectContext deleteObject:study];
                
                [defaultDatabase save:NULL];
            }
            
            [w close];
        }
    }
    
    return defaultDatabase;
}

static NSMutableDictionary *databasesDictionary = [[NSMutableDictionary alloc] init];
static NSRecursiveLock *databasesDictionaryLock = [[NSRecursiveLock alloc] init];

+(NSArray*)allDatabases
{
    [databasesDictionaryLock lock];
    
    NSMutableArray* mainDatabases = [NSMutableArray array];
    
    for (NSValue *value in [databasesDictionary allValues])
    {
        DicomDatabase* db = (DicomDatabase*) [value pointerValue];
        
        if ([db isMainDatabase])
            [mainDatabases addObject:db];
    }
    
    [databasesDictionaryLock unlock];
    
    return mainDatabases;
}

+(void)knowAbout:(DicomDatabase*)db
{
    if (db && db.baseDirPath)
    {
        [databasesDictionaryLock lock];
        
        if (![[databasesDictionary allValues] containsObject: [NSValue valueWithPointer: db]] && ![databasesDictionary objectForKey:db.baseDirPath])
        {
            [databasesDictionary setObject: [NSValue valueWithPointer: db] forKey:db.baseDirPath];
        }
        else
        {
            NSValue* k = [NSValue valueWithPointer: db];
            
            if (![databasesDictionary objectForKey:k])
                [databasesDictionary setObject: [NSValue valueWithPointer: db] forKey:k];
        }
        
        [databasesDictionaryLock unlock];
    }
}

+(DicomDatabase*)databaseAtPath:(NSString*)path {
    return [[self class] databaseAtPath:path name:nil];
}

+(DicomDatabase*)databaseAtPath:(NSString*)path name:(NSString*)name
{
    path = [self baseDirPathForPath:path];
    
    DicomDatabase* database = nil;
    
    [databasesDictionaryLock lock];
    
    database = (DicomDatabase*) [[databasesDictionary objectForKey:path] pointerValue];
    [[database retain] autorelease]; // It was a weak link in databasesDictionary : add it to the current autorelease pool
    
    [databasesDictionaryLock unlock];
    
    if (database) return database;
    
    database = [[[[self class] alloc] initWithPath:[self sqlFilePathForBasePath:path]] autorelease];
    database.name = name;
    return database;
}

+(DicomDatabase*)existingDatabaseAtPath:(NSString*)path
{
    DicomDatabase *database = nil;
    
    [databasesDictionaryLock lock];
    {
        database = (DicomDatabase*) [[databasesDictionary objectForKey:[self baseDirPathForPath:path]] pointerValue];
        [[database retain] autorelease]; // It was a weak link in databasesDictionary : add it to the current autorelease pool
    }
    [databasesDictionaryLock unlock];
    
    return database;
}

+(DicomDatabase*)databaseForContext:(NSManagedObjectContext*)c
{
    DicomDatabase *db = nil;
    
    if( [c isKindOfClass: [N2ManagedObjectContext class]])
        db = (DicomDatabase*) [(N2ManagedObjectContext*)c database];
    
    if( !db)
        N2LogStackTrace( @"databaseForContext == nil");
    
    return db;
}

static DicomDatabase* activeLocalDatabase = nil;

+(DicomDatabase*)activeLocalDatabase {
    return activeLocalDatabase? activeLocalDatabase : self.defaultDatabase;
}

+(void)setActiveLocalDatabase:(DicomDatabase*)ldb {
    if (!ldb.isLocal)
        return;
    if (ldb != self.activeLocalDatabase) {
        [activeLocalDatabase release];
        activeLocalDatabase = [ldb retain];
        [NSNotificationCenter.defaultCenter postNotificationName:OsirixActiveLocalDatabaseDidChangeNotification object:nil];
    }
}

#pragma mark Instance

@synthesize baseDirPath = _baseDirPath, dataBaseDirPath = _dataBaseDirPath, dataFileIndex = _dataFileIndex, name = _name, timeOfLastModification = _timeOfLastModification;
@synthesize isReadOnly = _isReadOnly;
@synthesize sourcePath = _sourcePath;
@synthesize processFilesLock = _processFilesLock;
@synthesize importFilesFromIncomingDirLock = _importFilesFromIncomingDirLock;
@synthesize hasPotentiallySlowDataAccess = _hasPotentiallySlowDataAccess;
@synthesize compressQueue = _compressQueue, decompressQueue = _decompressQueue, compressDecompressThread = _compressDecompressThread;

/*- (void)setIsReadOnly:(BOOL)isReadOnly {
 _isReadOnly = isReadOnly;
 }*/

-(DataNodeIdentifier*)dataNodeIdentifier {
    return [LocalDatabaseNodeIdentifier localDatabaseNodeIdentifierWithPath:self.baseDirPath];
}

-(NSString*)description {
    return [NSString stringWithFormat:@"<%@ 0x%08lx> \"%@\"", self.className, (long) self, self.name];
}

+(NSString*)modelName
{
    return @"OsiriXDB_DataModel.momd";
}

-(BOOL) deleteSQLFileIfOpeningFailed
{
    return YES;
}

-(NSManagedObjectModel*)managedObjectModel {
    static NSManagedObjectModel* managedObjectModel = NULL;
    if (!managedObjectModel)
        managedObjectModel = [[NSManagedObjectModel alloc] initWithContentsOfURL:[NSURL fileURLWithPath:[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent: DicomDatabase.modelName]]];
    return managedObjectModel;
}

/*-(NSMutableDictionary*)persistentStoreCoordinatorsDictionary {
	static NSMutableDictionary* dict = NULL;
	if (!dict)
 dict = [[NSMutableDictionary alloc] initWithCapacity:4];
	return dict;
 }*/

-(id)initWithPath:(NSString*)p context:(NSManagedObjectContext*)c mainDatabase:(N2ManagedDatabase*)mainDbReference // reminder: context may be nil (assigned in -[N2ManagedDatabase initWithPath:] after calling this method)
{
    @try {
        p = [DicomDatabase baseDirPathForPath:p];
        p = [p stringByResolvingSymlinksAndAliases];
        
        if (!mainDbReference)
            mainDbReference = [DicomDatabase existingDatabaseAtPath:p];
        
        [NSFileManager.defaultManager confirmDirectoryAtPath:p];
        
        NSString* sqlFilePath = [DicomDatabase sqlFilePathForBasePath:p];
        BOOL isNewFile = ![NSFileManager.defaultManager fileExistsAtPath:sqlFilePath];
        
        // init and register
        
        self.baseDirPath = p;
        _dataBaseDirPath = [NSString stringWithContentsOfFile:[p stringByAppendingPathComponent:@"DBFOLDER_LOCATION"] encoding:NSUTF8StringEncoding error:NULL];
        if (!_dataBaseDirPath) _dataBaseDirPath = p; // TODO: what if this path is not mounted?
        [_dataBaseDirPath retain];
        
        BOOL isNewDb = ![NSFileManager.defaultManager fileExistsAtPath:[self dataDirPath]];
        
        self = [super initWithPath:sqlFilePath context:c mainDatabase:mainDbReference];
        
        [DicomDatabase knowAbout:self]; // retains self
        
        // post-init
        
        if (self.isMainDatabase) // is main (not independent)
        {
            [NSFileManager.defaultManager removeItemAtPath:self.loadingFilePath error:nil];
            
            _dataFileIndex = [[N2MutableUInteger alloc] initWithUInteger:0];
            _processFilesLock = [[NSRecursiveLock alloc] init];
            _importFilesFromIncomingDirLock = [[NSRecursiveLock alloc] init];
            
            _compressQueue = [[NSMutableArray alloc] init];
            _decompressQueue = [[NSMutableArray alloc] init];
            
            // create dirs if necessary
            [NSFileManager.defaultManager confirmDirectoryAtPath:self.dataDirPath];
            [NSFileManager.defaultManager confirmDirectoryAtPath:self.incomingDirPath];
            [NSFileManager.defaultManager confirmDirectoryAtPath:self.tempDirPath];
            [NSFileManager.defaultManager confirmDirectoryAtPath:self.reportsDirPath];
            [NSFileManager.defaultManager confirmDirectoryAtPath:self.dumpDirPath];
            
            if (self.baseDirPath) strncpy(baseDirPathC, self.baseDirPath.fileSystemRepresentation, sizeof(baseDirPathC)); else baseDirPathC[0] = 0;
            if (self.incomingDirPath) strncpy(incomingDirPathC, self.incomingDirPath.fileSystemRepresentation, sizeof(incomingDirPathC)); else incomingDirPathC[0] = 0;
            if (self.tempDirPath) strncpy(tempDirPathC, self.tempDirPath.fileSystemRepresentation, sizeof(tempDirPathC)); else tempDirPathC[0] = 0;
            
            // if a TOBEINDEXED dir exists, move it into INCOMING so we will import the data
            
            if ([NSFileManager.defaultManager fileExistsAtPath:self.toBeIndexedDirPath])
                [NSFileManager.defaultManager moveItemAtPath:self.toBeIndexedDirPath toPath:[self.incomingDirPath stringByAppendingPathComponent:self.toBeIndexedDirPath.lastPathComponent] error:NULL];
            
            // report templates
#ifndef MACAPPSTORE
#ifndef OSIRIX_LIGHT
            
            for (NSString* rfn in [NSArray arrayWithObjects: @"ReportTemplate.rtf", @"ReportTemplate.odt", nil]) {
                NSString* rfp = [self.baseDirPath stringByAppendingPathComponent:rfn];
                if (rfp && ![NSFileManager.defaultManager fileExistsAtPath:rfp]) {
                    [NSFileManager.defaultManager copyItemAtPath:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:rfn] toPath:rfp error:NULL];
                    [NSFileManager.defaultManager applyFileModeOfParentToItemAtPath:rfp];
                }
            }
            
            [Reports checkForPagesTemplate];
            [Reports checkForWordTemplates];
            
#endif
#endif
            
            [self checkForHtmlTemplates];
            
            if (isNewFile && [NSThread isMainThread] && ![p hasPrefix:@"/tmp/"] && !isNewDb) {
                [NSThread.currentThread enterOperation];
                NSThread.currentThread.name = NSLocalizedString(@"Rebuilding default OsiriX database...", nil);
                ThreadModalForWindowController* tmfwc = [[ThreadModalForWindowController alloc] initWithThread:[NSThread currentThread] window:nil];
                [self rebuild:YES];
                [tmfwc invalidate];
                [tmfwc release];
                [NSThread.currentThread exitOperation];
            }
            
            if (isNewFile && ![p hasPrefix:@"/tmp/"])
                [self addDefaultAlbums];
            [self modifyDefaultAlbums];
            [DicomDatabase repairEmptySeriesIdentifiersInContext: self.managedObjectContext];
            [DicomDatabase repairFabricatedPatientIdentifiersInContext: self.managedObjectContext];
            
            [DicomDatabase syncImportFilesFromIncomingDirTimerWithUserDefaults];
        }
        else // is independentDatabase
        {
            _dataFileIndex = [[self.mainDatabase dataFileIndex] retain];
            _processFilesLock = [[self.mainDatabase processFilesLock] retain];
            _importFilesFromIncomingDirLock = [[self.mainDatabase importFilesFromIncomingDirLock] retain];
            _hasPotentiallySlowDataAccess = [self.mainDatabase hasPotentiallySlowDataAccess];
            
            _compressQueue = [[self.mainDatabase compressQueue] retain];
            _decompressQueue = [[self.mainDatabase decompressQueue] retain];
            
            
            [NSNotificationCenter.defaultCenter addObserver:mainDbReference selector:@selector(observeIndependentDatabaseNotification:) name:_O2AddToDBAnywayNotification object:self];
            [NSNotificationCenter.defaultCenter addObserver:mainDbReference selector:@selector(observeIndependentDatabaseNotification:) name:_O2AddToDBAnywayCompleteNotification object:self];
            // the followindo notifications look like the previous ones but they're not the same. do not remove them! viewercontroller needs them ot it won't update the preview matrix with the added images
            [NSNotificationCenter.defaultCenter addObserver:mainDbReference selector:@selector(observeIndependentDatabaseNotification:) name:OsirixAddToDBNotification object:self];
            [NSNotificationCenter.defaultCenter addObserver:mainDbReference selector:@selector(observeIndependentDatabaseNotification:) name:OsirixAddToDBCompleteNotification object:self];
            [NSNotificationCenter.defaultCenter addObserver:mainDbReference selector:@selector(observeIndependentDatabaseNotification:) name:OsirixAddNewStudiesDBNotification object:self];
            [NSNotificationCenter.defaultCenter addObserver:mainDbReference selector:@selector(observeIndependentDatabaseNotification:) name:O2DatabaseInvalidateAlbumsCacheNotification object:self];
        }
        
        [self initRouting];
        [self initClean];
        
    }
    @catch (NSException *e) {
        N2LogExceptionWithStackTrace( e);
        
        if( [NSThread isMainThread])
            NSRunAlertPanel( NSLocalizedString( @"Database", nil), @"%@", NSLocalizedString( @"OK", nil), nil, nil, e.reason);
        
        [self autorelease];
        return nil;
    }
    
    return self;
}

-(oneway void) release
{
    [databasesDictionaryLock lock];
    [super release];
    [databasesDictionaryLock unlock];
}

-(void)dealloc
{
    if( _deallocating)
        return;
    _deallocating = YES;
    
    [_lastImportRefusalSummary release];
    _lastImportRefusalSummary = nil;
    
    BOOL found = NO;
    for(id key in [NSDictionary dictionaryWithDictionary: databasesDictionary])
    {
        if( [[databasesDictionary objectForKey: key] pointerValue] == (void*) self)
        {
            [databasesDictionary removeObjectForKey: key];
            found = YES;
        }
    }
    if( found == NO)
    {
        // A database whose -initWithPath: threw - the usual cause is its volume
        // going away under it - never reached the registry, so this is a real
        // situation and not a mystery. Name it instead of logging a stack trace
        // under "WTF", which said nothing about what had happened.
        NSLog( @"---- database at %@ was released without ever being registered; it did not finish opening", self.baseDirPath? self.baseDirPath : @"an unknown path");
    }
    
#ifndef NDEBUG
    if( databasesDictionary.count > 50)
        NSLog( @"******** WARNING databasesDictionary.count is very high = %lu", (unsigned long)databasesDictionary.count);
#endif
    
    [databasesDictionaryLock unlock]; //We are locked from -(oneway void) release
    
    [self deallocClean];
    [self deallocRouting];
    
    if (self.isMainDatabase)
    {
        NSRecursiveLock* temp;
        
        temp = _importFilesFromIncomingDirLock;
        [temp lock]; // if currently importing, wait until finished
        _importFilesFromIncomingDirLock = nil;
        [temp unlock];
        [temp release];
        
        temp = _processFilesLock;
        [temp lock]; // if currently importing, wait until finished
        _processFilesLock = nil;
        [temp unlock];
        [temp release];
    } else {
        [_importFilesFromIncomingDirLock release];
        [_processFilesLock release];
        [NSNotificationCenter.defaultCenter removeObserver:self.mainDatabase name:nil object:self];
    }
    
    [_dataFileIndex release];
    self.dataBaseDirPath = nil;
    self.baseDirPath = nil;
    self.sourcePath = nil;
    
    [_decompressQueue release];
    [_compressQueue release];
    
    [super dealloc];
    
    [databasesDictionaryLock lock]; //We will be unlocked from -(oneway void) release
    
    return;
}

-(void)observeIndependentDatabaseNotification:(NSNotification*)notification {
    if (![NSThread isMainThread])
        [self performSelectorOnMainThread:@selector(observeIndependentDatabaseNotification:) withObject:notification waitUntilDone:NO];
    else
    {
        NSMutableDictionary* userInfo = [NSMutableDictionary dictionary];
        
        [self lock];
        @try
        {
            DicomDatabase *idatabase = self.isMainDatabase? self : self.mainDatabase; //We are on the mainthread : we can'safely' use the maindatabase
            
            NSArray* independentObjects = [notification.userInfo objectForKey:OsirixAddToDBNotificationImagesArray];
            if (independentObjects) {
                NSArray* selfObjects = [idatabase objectsWithIDs:independentObjects];
                if (selfObjects.count != independentObjects.count)
                    NSLog(@"Warning: independent database is notifying about %d new images, but the main database can only find %d.", (int)independentObjects.count, (int)selfObjects.count);
                [userInfo setObject:selfObjects forKey:OsirixAddToDBNotificationImagesArray]; // We should NOT send a notification with objects, but objectsID instead...
            }
            
            NSDictionary* independentDictionary = [notification.userInfo objectForKey:OsirixAddToDBNotificationImagesPerAETDictionary];
            if (independentDictionary) {
                NSMutableDictionary* selfDictionary = [NSMutableDictionary dictionary];
                for (NSString* key in independentDictionary)
                    [selfDictionary setObject:[idatabase objectsWithIDs:[independentDictionary objectForKey:key]] forKey:key];
                [userInfo setObject:selfDictionary forKey:OsirixAddToDBNotificationImagesPerAETDictionary];
            }
        }
        @catch (NSException *exception) {
            N2LogException( exception);
        }
        @finally {
            [self unlock];
        }
        
        [NSNotificationCenter.defaultCenter postNotificationName:notification.name object:self userInfo:userInfo];
    }
}

-(BOOL)isLocal {
    return YES;
}

-(NSString*)name {
    return _name? _name : [NSString stringWithFormat:NSLocalizedString(@"Local Database (%@)", nil), self.baseDirPath];
}

- (NSManagedObjectContext *)contextAtPath:(NSString *)sqlFilePath {
    // custom migration
    
    NSManagedObjectContext* context = nil;
    
    BOOL rebuildPatientUIDs = NO;
    BOOL independentContext = YES;
    
    if (!self.managedObjectContext || ![sqlFilePath isEqualToString:self.managedObjectContext.persistentStoreCoordinator.persistentStores.firstObject.URL.path])
        independentContext = NO;
    
    if( independentContext == NO) // avoid doing this for independent contexts: we know it's already ok, and this leads to very bad crashes
    {
        NSString* modelVersion = [NSString stringWithContentsOfFile:self.modelVersionFilePath encoding:NSUTF8StringEncoding error:nil];
        if (!modelVersion) modelVersion = [NSUserDefaults.standardUserDefaults stringForKey:@"DATABASEVERSION"];
        
        if (modelVersion.length && ![modelVersion isEqualToString:CurrentDatabaseVersion]) {
            rebuildPatientUIDs = [self upgradeSqlFileFromModelVersion:modelVersion];
            [CurrentDatabaseVersion writeToFile:self.modelVersionFilePath atomically:YES encoding:NSUTF8StringEncoding error:NULL];
        }
    }
    
    // super + spec
    
    context = [super contextAtPath:sqlFilePath];
    [context setMergePolicy:NSMergeByPropertyStoreTrumpMergePolicy];
    [context setUndoManager: nil];
    
    if( independentContext == NO)
    {
        // Meta Data
        if( context.persistentStoreCoordinator.persistentStores.count == 1)
        {
            NSDictionary *metaData = [context.persistentStoreCoordinator metadataForPersistentStore: [context.persistentStoreCoordinator.persistentStores lastObject]];
            
#define PATIENTUIDVERSION @"2.0"
            
            NSString *PatientUIDVersion = [NSString stringWithFormat: @"%@ - %d - %d - %d", PATIENTUIDVERSION, [[NSUserDefaults standardUserDefaults] boolForKey: @"UsePatientBirthDateForUID"], [[NSUserDefaults standardUserDefaults] boolForKey: @"UsePatientIDForUID"], [[NSUserDefaults standardUserDefaults] boolForKey: @"UsePatientNameForUID"]];
            
            if( [metaData objectForKey: @"patientUIDVersion"] == nil || [[metaData objectForKey: @"patientUIDVersion"] isEqualToString: PatientUIDVersion] == NO)
            {
                rebuildPatientUIDs = YES; //recompute patient UIDs
                NSMutableDictionary *newMetaData = [NSMutableDictionary dictionaryWithDictionary: metaData];
                [newMetaData setObject: PatientUIDVersion forKey: @"patientUIDVersion"];
                [context.persistentStoreCoordinator setMetadata: newMetaData forPersistentStore: [context.persistentStoreCoordinator.persistentStores lastObject]];
            }
        }
        else
            N2LogStackTrace( @"********* persistentStoreCoordinator.persistentStores.count != 1, %d", context.persistentStoreCoordinator.persistentStores.count);
    }
    
    if (rebuildPatientUIDs)
        [DicomDatabase recomputePatientUIDsInContext:context]; // if upgradeSqlFileFromModelVersion returns NO, the database was rebuilt so no need to recompute IDs
    
    return context;
}

-(BOOL)save:(NSError**)err {
    
    BOOL b = NO;
    
    [self.managedObjectContext lock];
    @try {
        NSError* error = nil;
        if (!err) err = &error;
        
        b = [super save:err];
        
        if (*err)
            NSLog(@"DicomDatabase save error: %@", *err);
        else {
            [NSUserDefaults.standardUserDefaults setObject:CurrentDatabaseVersion forKey:@"DATABASEVERSION"];
            [CurrentDatabaseVersion writeToFile:self.modelVersionFilePath atomically:YES encoding:NSUTF8StringEncoding error:nil];
        }
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    } @finally {
        [self.managedObjectContext unlock];
    }
    
    return b;
}

NSString* const DicomDatabaseImageEntityName = @"Image";
NSString* const DicomDatabaseSeriesEntityName = @"Series";
NSString* const DicomDatabaseStudyEntityName = @"Study";
NSString* const DicomDatabaseAlbumEntityName = @"Album";
NSString* const DicomDatabaseLogEntryEntityName = @"LogEntry";

-(NSEntityDescription*)imageEntity {
    return [self entityForName: @"Image"];
}

-(NSEntityDescription*)seriesEntity {
    return [self entityForName: @"Series"];
}

-(NSEntityDescription*)studyEntity {
    return [self entityForName: @"Study"];
}

-(NSEntityDescription*)albumEntity {
    return [self entityForName: @"Album"];
}

-(NSEntityDescription*)logEntryEntity {
    return [self entityForName: @"LogEntry"];
}

+(NSString*)sqlFilePathForBasePath:(NSString*)basePath {
    return [basePath stringByAppendingPathComponent:SqlFileName];
}

/*-(NSString*)sqlFilePath {
	return [DicomDatabase sqlFilePathForBasePath:self.baseDirPath];
 }*/

-(NSString*)dataDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"DATABASE.noindex"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)incomingDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"INCOMING.noindex"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)decompressionDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"DECOMPRESSION.noindex"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)toBeIndexedDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"TOBEINDEXED.noindex"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)tempDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"TEMP.noindex"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)dumpDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"DUMP"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)errorsDirPath {
    NSString *path = [[self.dataBaseDirPath stringByAppendingPathComponent:@"NOT READABLE"] stringByResolvingSymlinksAndAliases];
    // Nothing created this directory, so every -moveItemAtPath: into it failed
    // and the fallback removed the file instead: the preference that is meant to
    // keep unreadable files for inspection kept nothing.
    [NSFileManager.defaultManager confirmDirectoryAtPath: path];
    return path;
}

-(NSString*)reportsDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"REPORTS"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)pagesDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"PAGES"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)roisDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"ROIs"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)htmlTemplatesDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"HTML_TEMPLATES"] stringByResolvingSymlinksAndAliases];
}

- (NSString *)statesDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"3DSTATE"] stringByResolvingSymlinksAndAliases];
}

- (NSString *)clutsDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"CLUTs"] stringByResolvingSymlinksAndAliases];
}

- (NSString *)presetsDirPath {
    return [[self.dataBaseDirPath stringByAppendingPathComponent:@"3DPRESETS"] stringByResolvingSymlinksAndAliases];
}

-(NSString*)modelVersionFilePath {
    return [self.baseDirPath stringByAppendingPathComponent:@"DB_VERSION"];
}

-(NSString*)loadingFilePath {
    return [self.baseDirPath stringByAppendingPathComponent:@"Loading"];
}

-(const char*)baseDirPathC {
    return baseDirPathC;
}

-(const char*)incomingDirPathC {
    return incomingDirPathC;
}

-(const char*)tempDirPathC {
    return tempDirPathC;
}

-(NSUInteger)computeDataFileIndex {
    @synchronized (_dataFileIndex) {
        DLog(@"In -[DicomDatabase computeDataFileIndex] for %@ initially %d", self.sqlFilePath, (int)_dataFileIndex.unsignedIntegerValue);
        
        BOOL hereBecauseZero = (_dataFileIndex.unsignedIntegerValue == 0);
        @synchronized(_dataFileIndex) {
            if (hereBecauseZero && _dataFileIndex.unsignedIntegerValue != 0)
                return _dataFileIndex.unsignedIntegerValue += 1;
            @try {
                NSString* path = self.dataDirPath;
                //			NSLog(@"Path is %@", path);
                
                // delete empty dirs and scan for files with number names
                //			NSLog(@"Scanning %d dirs", fs.count);
                for (NSString* f in [NSFileManager.defaultManager enumeratorAtPath:path filesOnly:NO recursive:NO]) {
                    //				NSLog(@"Scanning dir %@", f);
                    NSString* fpath = [path stringByAppendingPathComponent:f];
                    //NSDictionary* fattr = [NSFileManager.defaultManager fileAttributesAtPath:fpath traverseLink:YES];
                    //NSLog(@"Has %d attrs", fattr.count);
                    
                    // check if this folder is empty, and delete it if necessary
                    BOOL isDir;
                    if ([NSFileManager.defaultManager fileExistsAtPath:fpath isDirectory:&isDir] && isDir) {
                        NSAutoreleasePool* pool = [NSAutoreleasePool new];
                        @try {
                            BOOL hasValidFiles = NO;
                            
                            //						NSLog(@"Content of %@", f);
                            N2DirectoryEnumerator* n2de = [NSFileManager.defaultManager enumeratorAtPath:fpath filesOnly:NO recursive:NO];
                            NSString* s;
                            while (s = [n2de nextObject]) // [NSFileManager.defaultManager contentsOfDirectoryAtPath:fpath error:nil])
                                if ([[s stringByDeletingPathExtension] integerValue] > 0) {
                                    hasValidFiles = YES;
                                    break;
                                }
                            
                            if (!hasValidFiles)
                                [NSFileManager.defaultManager removeItemAtPath:fpath error:nil];
                            else {
                                NSUInteger fi = [f integerValue];
                                if (fi > _dataFileIndex.unsignedIntegerValue)
                                    _dataFileIndex.unsignedIntegerValue = fi;
                            }
                        } @catch (NSException* e) {
                            N2LogExceptionWithStackTrace(e);
                        } @finally {
                            [pool release];
                        }
                    }
                }
                
                // scan directories
                
                if (_dataFileIndex.unsignedIntegerValue > 0) {
                    //				NSLog(@"datafileindex is %d", _dataFileIndex.unsignedIntegerValue);
                    
                    NSInteger t = _dataFileIndex.unsignedIntegerValue;
                    t -= [BrowserController DefaultFolderSizeForDB];
                    if (t < 0) t = 0;
                    
                    NSArray* paths = [[NSFileManager.defaultManager enumeratorAtPath:[path stringByAppendingPathComponent:[NSString stringWithFormat:@"%d", (int) _dataFileIndex.unsignedIntegerValue]] filesOnly:NO recursive:NO] allObjects]; // [NSFileManager.defaultManager contentsOfDirectoryAtPath:[path stringByAppendingPathComponent:[NSString stringWithFormat:@"%d", _dataFileIndex.unsignedIntegerValue]] error:nil];
                    //				NSLog(@"contains %d files", paths.count);
                    for (NSString* s in paths) {
                        long si = [[s stringByDeletingPathExtension] integerValue];
                        if (si > t)
                            t = si;
                    }
                    
                    _dataFileIndex.unsignedIntegerValue = t;
                }
                
                if (!_dataFileIndex.unsignedIntegerValue)
                    _dataFileIndex.unsignedIntegerValue = 1;
                
                DLog(@"   -[DicomDatabase computeDataFileIndex] for %@ computed %d", self.sqlFilePath, (int)_dataFileIndex.unsignedIntegerValue);
            } @catch (NSException* e) {
                N2LogExceptionWithStackTrace(e);
            }
        }
        
        return _dataFileIndex.unsignedIntegerValue;
    }
    
    return 0;
}

-(NSString*)uniquePathForNewDataFileWithExtension:(NSString*)ext {
    NSString* path = nil;
    
    if (ext.length > 4 || ext.length < 3) {
        if (ext.length)
            NSLog(@"Warning: strange extension \"%@\", it will be replaced with \"dcm\"", ext);
        ext = @"dcm";
    }
    
    @try
    {
        @synchronized(_dataFileIndex)
        {
            NSString* dataDirPath = self.dataDirPath;
            [NSFileManager.defaultManager confirmNoIndexDirectoryAtPath:dataDirPath]; // old impl only did this every 3 secs..
            
            NSUInteger index = 0;
            @synchronized(_dataFileIndex) {
                if (!_dataFileIndex.unsignedIntegerValue)
                    [self computeDataFileIndex];
                [_dataFileIndex increment];
                index = _dataFileIndex.unsignedIntegerValue;
            }
            
            unsigned long long defaultFolderSizeForDB = [BrowserController DefaultFolderSizeForDB];
            
            BOOL fileExists = NO, firstExists = YES;
            do {
                unsigned long long subFolderInt = defaultFolderSizeForDB*(index/defaultFolderSizeForDB+1);
                NSString* subFolderPath = [dataDirPath stringByAppendingPathComponent:[NSString stringWithFormat:@"%llu", subFolderInt]];
                [NSFileManager.defaultManager confirmDirectoryAtPath:subFolderPath];
                
                path = [subFolderPath stringByAppendingPathComponent:[NSString stringWithFormat:@"%llu.%@", (unsigned long long)_dataFileIndex.unsignedIntegerValue, ext]];
                fileExists = [NSFileManager.defaultManager fileExistsAtPath:path];
                
                if (fileExists)
                {
                    if (firstExists)
                    {
                        firstExists = NO;
                        @synchronized(_dataFileIndex) {
                            [self computeDataFileIndex];
                            index = _dataFileIndex.unsignedIntegerValue;
                        }
                    }
                    else
                        @synchronized (_dataFileIndex) {
                            [_dataFileIndex increment];
                            index = _dataFileIndex.unsignedIntegerValue;
                        }
                }
            } while (fileExists);
        }
    }
    @catch (NSException *exception) {
        N2LogExceptionWithStackTrace( exception);
    }
    
    return path;
}

#pragma mark Albums

- (void) loadAlbumsFromPath:(NSString*) path
{
    NSArray* albums = [NSArray arrayWithContentsOfFile: path];
    if (albums)
    {
        [self.managedObjectContext lock];
        @try
        {
            NSFetchRequest *dbRequest = [[[NSFetchRequest alloc] init] autorelease];
            [dbRequest setEntity: [[self.managedObjectModel entitiesByName] objectForKey:@"Album"]];
            [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
            NSError *error = nil;
            NSMutableArray *albumArray = [NSMutableArray arrayWithArray: [self.managedObjectContext executeFetchRequest: dbRequest error: &error]];
            
            for (NSDictionary* dict in albums)
            {
                DicomAlbum* a = nil;
                
                NSInteger index = [[albumArray valueForKey:@"name"] indexOfObject:[dict valueForKey:@"name"]];
                if (index == NSNotFound)
                {
                    a = [self newObjectForEntity:self.albumEntity];
                    
                    a.name = [dict objectForKey: @"name"];
                    
                    if ([[dict objectForKey: @"smartAlbum"] boolValue])
                    {
                        a.smartAlbum = [NSNumber numberWithBool:YES];
                        a.predicateString = [dict valueForKey: @"predicateString"];
                    }
                }
                else {
                    a = [albumArray objectAtIndex:index];
                }
                
                if (!a.smartAlbum.boolValue) {
                    a.smartAlbum = [NSNumber numberWithBool:NO];
                    for (NSDictionary* entry in [dict objectForKey:@"studies"]) {
                        NSString* studyInstanceUID = [entry objectForKey:@"studyInstanceUID"];
                        NSArray* qr = [self objectsForEntity:self.studyEntity predicate:[NSPredicate predicateWithFormat:@"studyInstanceUID = %@", studyInstanceUID]];
                        if (qr.count)
                        {
                            [[a mutableSetValueForKey:@"studies"] addObjectsFromArray:qr];
                        }
                        else
                        {
                            DicomStudy* s = [self newObjectForEntity:self.studyEntity];
                            s.studyInstanceUID = [entry objectForKey:@"studyInstanceUID"];
                            s.name = [entry objectForKey:@"patientName"];
                            s.patientID = [entry objectForKey:@"patientID"];
                            s.patientUID = [entry objectForKey:@"patientUID"];
                            s.dateOfBirth = [entry objectForKey:@"dateOfBirth"];
                            s.studyName = [entry objectForKey:@"name"];
                            s.date = [entry objectForKey:@"date"];
                            s.modality = [entry objectForKey:@"modality"];
                            s.accessionNumber = [entry objectForKey:@"accessionNumber"];
                            [[a mutableSetValueForKey:@"studies"] addObject:s];
                            DicomSeries* se = [self newObjectForEntity:self.seriesEntity];
                            se.name = @"OsiriX No Autodeletion";
                            se.id = [NSNumber numberWithInt:5005];
                            [[s mutableSetValueForKey:@"series"] addObject:se];
                        }
                    }
                }
            }
            
            [self.managedObjectContext save:NULL];
        }
        @catch (NSException * e)
        {
            N2LogExceptionWithStackTrace(e);
        }
        @finally
        {
            [self.managedObjectContext unlock];
        }
    }
}

- (void) saveAlbumsToPath:(NSString*) path
{
    [self.managedObjectContext lock];
    
    @try
    {
        [self.managedObjectContext save: nil];
        
        NSMutableArray *albums = [NSMutableArray array];
        NSFetchRequest *dbRequest = [[[NSFetchRequest alloc] init] autorelease];
        [dbRequest setEntity: [[self.managedObjectModel entitiesByName] objectForKey:@"Album"]];
        [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
        NSError *error = nil;
        NSArray *albumArray = [self.managedObjectContext executeFetchRequest:dbRequest error:&error];
        
        if( [albumArray count])
        {
            for (DicomAlbum* album in albumArray)
            {
                NSMutableDictionary* entry = [NSMutableDictionary dictionaryWithObject:album.name forKey:@"name"];
                
                if (album.smartAlbum.boolValue)
                {
                    [entry setObject:[NSNumber numberWithBool:YES] forKey:@"smartAlbum"];
                    [entry setObject:album.predicateString forKey:@"predicateString"];
                }
                else
                {
                    NSMutableArray* studies = [NSMutableArray array];
                    for (DicomStudy* study in album.studies)
                    {
                        NSMutableDictionary* entry = [NSMutableDictionary dictionary];
                        if( study.studyInstanceUID) [entry setObject:study.studyInstanceUID forKey:@"studyInstanceUID"];
                        if( study.name) [entry setObject:study.name forKey:@"patientName"];
                        if( study.patientID) [entry setObject:study.patientID forKey:@"patientID"];
                        if( study.patientUID) [entry setObject:study.patientUID forKey:@"patientUID"];
                        if( study.dateOfBirth) [entry setObject:study.dateOfBirth forKey:@"dateOfBirth"];
                        if( study.studyName) [entry setObject:study.studyName forKey:@"name"];
                        if( study.date) [entry setObject:study.date forKey:@"date"];
                        if( study.modality) [entry setObject:study.modality forKey:@"modality"];
                        if( study.accessionNumber) [entry setObject:study.accessionNumber forKey:@"accessionNumber"];
                        [studies addObject:entry];
                    }
                    
                    [entry setObject:studies forKey:@"studies"];
                }
                
                [albums addObject:entry];
                
                [[NSFileManager defaultManager] removeItemAtPath: path error: nil];
                [albums writeToFile: path atomically: YES];
            }
        }
        else NSLog( @"--- no albums to save");
    }
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    [self.managedObjectContext unlock];
}

-(NSArray*)albums {
    NSArray* albums = [self objectsForEntity:self.albumEntity];
    @try {
        albums = [albums sortedArrayUsingComparator: ^(id a, id b) {
            @try {
                return [[a name] caseInsensitiveCompare:[b name]];
            } @catch (...) {
            }
            return (NSComparisonResult) NSOrderedSame;
        }];
    } @catch (NSException* e) {
        N2LogException(e);
    }
    
    return albums;
}

+(NSPredicate*)predicateForSmartAlbumFilter:(NSString*)string {
    if (!string.length)
        return [NSPredicate predicateWithValue:YES];
    
    NSMutableString* pred = [NSMutableString stringWithString: string];
    
    // DATES
    NSCalendarDate* now = [NSCalendarDate calendarDate];
    NSDate *start = [NSDate dateWithTimeIntervalSinceReferenceDate: [[NSCalendarDate dateWithYear:[now yearOfCommonEra] month:[now monthOfYear] day:[now dayOfMonth] hour:0 minute:0 second:0 timeZone: [now timeZone]] timeIntervalSinceReferenceDate]];
    
    NSDictionary	*sub = [NSDictionary dictionaryWithObjectsAndKeys:	[NSString stringWithFormat:@"%lf", [[now dateByAddingTimeInterval: -60*60*1] timeIntervalSinceReferenceDate]],			@"$LASTHOUR",
                            [NSString stringWithFormat:@"%lf", [[now dateByAddingTimeInterval:-60*60*6] timeIntervalSinceReferenceDate]],			@"$LAST6HOURS",
                            [NSString stringWithFormat:@"%lf", [[now dateByAddingTimeInterval: -60*60*12] timeIntervalSinceReferenceDate]],			@"$LAST12HOURS",
                            [NSString stringWithFormat:@"%lf", [start timeIntervalSinceReferenceDate]],										@"$TODAY",
                            [NSString stringWithFormat:@"%lf", [[start dateByAddingTimeInterval: -60*60*24] timeIntervalSinceReferenceDate]],			@"$YESTERDAY",
                            [NSString stringWithFormat:@"%lf", [[start dateByAddingTimeInterval: -60*60*24*2] timeIntervalSinceReferenceDate]],		@"$2DAYS",
                            [NSString stringWithFormat:@"%lf", [[start dateByAddingTimeInterval: -60*60*24*7] timeIntervalSinceReferenceDate]],		@"$WEEK",
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
    
    NSPredicate *predicate = [[NSPredicate predicateWithFormat:pred] predicateWithSubstitutionVariables: [NSDictionary dictionaryWithObjectsAndKeys:
                                                                                                          [now dateByAddingTimeInterval: -60*60*1],			@"NSDATE_LASTHOUR",
                                                                                                          [now dateByAddingTimeInterval: -60*60*6],			@"NSDATE_LAST6HOURS",
                                                                                                          [now dateByAddingTimeInterval: -60*60*12],			@"NSDATE_LAST12HOURS",
                                                                                                          start,                                              @"NSDATE_TODAY",
                                                                                                          [start dateByAddingTimeInterval: -60*60*24],        @"NSDATE_YESTERDAY",
                                                                                                          [start dateByAddingTimeInterval: -60*60*24*2],		@"NSDATE_2DAYS",
                                                                                                          [start dateByAddingTimeInterval: -60*60*24*7],		@"NSDATE_WEEK",
                                                                                                          [start dateByAddingTimeInterval: -60*60*24*31],		@"NSDATE_MONTH",
                                                                                                          [start dateByAddingTimeInterval: -60*60*24*31*2],	@"NSDATE_2MONTHS",
                                                                                                          [start dateByAddingTimeInterval: -60*60*24*31*3],	@"NSDATE_3MONTHS",
                                                                                                          [start dateByAddingTimeInterval: -60*60*24*365],    @"NSDATE_YEAR",
                                                                                                          nil]];
    if( predicate == nil)
        predicate = [NSPredicate predicateWithValue:YES];
    
    return predicate;
}

-(void)addDefaultAlbums {
    NSDictionary* albumDescriptors = [NSDictionary dictionaryWithObjectsAndKeys:
                                      
                                      @"(dateAdded >= $NSDATE_LASTHOUR)", NSLocalizedString( @"Just Added (last hour)", nil),
                                      @"(date >= $NSDATE_LASTHOUR)", NSLocalizedString( @"Just Acquired (last hour)", nil),
                                      @"(dateOpened >= $NSDATE_LAST6HOURS)", NSLocalizedString( @"Just Opened", nil),
                                      
                                      @"(modality CONTAINS[cd] 'MR') AND (date >= $NSDATE_TODAY)", NSLocalizedString( @"Today MR", nil),
                                      @"(modality CONTAINS[cd] 'CT') AND (date >= $NSDATE_TODAY)", NSLocalizedString( @"Today CT", nil),
                                      @"(modality CONTAINS[cd] 'US') AND (date >= $NSDATE_TODAY)", NSLocalizedString( @"Today US", nil),
                                      @"(modality CONTAINS[cd] 'MG') AND (date >= $NSDATE_TODAY)", NSLocalizedString( @"Today MG", nil),
                                      @"(modality CONTAINS[cd] 'CR') AND (date >= $NSDATE_TODAY)", NSLocalizedString( @"Today CR", nil),
                                      @"(modality CONTAINS[cd] 'XA') AND (date >= $NSDATE_TODAY)", NSLocalizedString( @"Today XA", nil),
                                      @"(modality CONTAINS[cd] 'RF') AND (date >= $NSDATE_TODAY)", NSLocalizedString( @"Today RF", nil),
                                      
                                      @"(modality CONTAINS[cd] 'MR') AND (date >= $NSDATE_YESTERDAY AND date <= $NSDATE_TODAY)", NSLocalizedString( @"Yesterday MR", nil),
                                      @"(modality CONTAINS[cd] 'CT') AND (date >= $NSDATE_YESTERDAY AND date <= $NSDATE_TODAY)", NSLocalizedString( @"Yesterday CT", nil),
                                      @"(modality CONTAINS[cd] 'US') AND (date >= $NSDATE_YESTERDAY AND date <= $NSDATE_TODAY)", NSLocalizedString( @"Yesterday US", nil),
                                      @"(modality CONTAINS[cd] 'MG') AND (date >= $NSDATE_YESTERDAY AND date <= $NSDATE_TODAY)", NSLocalizedString( @"Yesterday MG", nil),
                                      @"(modality CONTAINS[cd] 'CR') AND (date >= $NSDATE_YESTERDAY AND date <= $NSDATE_TODAY)", NSLocalizedString( @"Yesterday CR", nil),
                                      @"(modality CONTAINS[cd] 'XA') AND (date >= $NSDATE_YESTERDAY AND date <= $NSDATE_TODAY)", NSLocalizedString( @"Yesterday XA", nil),
                                      @"(modality CONTAINS[cd] 'RF') AND (date >= $NSDATE_YESTERDAY AND date <= $NSDATE_TODAY)", NSLocalizedString( @"Yesterday RF", nil),
                                      
                                      [NSNull null], NSLocalizedString( @"Interesting Cases", nil),
                                      
                                      @"(comment != '' AND comment != NIL)", NSLocalizedString( @"Cases with comments", nil),
                                      
                                      NULL];
    
    NSArray* albums = [self albums];
    
    for (NSString* localizedName in albumDescriptors)
    {
        if ([[albums valueForKey:@"name"] indexOfObject:localizedName] == NSNotFound)
        {
            DicomAlbum* album = [self newObjectForEntity:self.albumEntity];
            album.name = localizedName;
            NSString* predicate = [albumDescriptors objectForKey:localizedName];
            
            if ([predicate isKindOfClass:[NSString class]])
            {
                album.predicateString = predicate;
                album.smartAlbum = [NSNumber numberWithBool:YES];
            }
        }
    }
    
    [self save:nil];
}

-(void)modifyDefaultAlbums {
    @try {
        for (DicomAlbum* album in self.albums)
        {
            if ([album.predicateString isEqualToString:@"(ANY series.comment != '' AND ANY series.comment != NIL) OR (comment != '' AND comment != NIL)"])
                album.predicateString = @"(comment != '' AND comment != NIL)";
            
            if( [album valueForKey: @"predicateString"] && [[album valueForKey: @"predicateString"] rangeOfString: @"ANY series.modality"].location != NSNotFound)
            {
                NSString *previousString = [album valueForKey: @"predicateString"];
                [album setValue: [previousString stringByReplacingOccurrencesOfString:@"ANY series.modality" withString:@"modality"] forKey: @"predicateString"];
            }
        }
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    }
}

-(void)addStudies:(NSArray*)dicomStudies toAlbum:(DicomAlbum*)dicomAlbum {
    for (DicomStudy* study in dicomStudies)
        [dicomAlbum addStudiesObject:study];
}

#pragma mark Lifecycle

-(BOOL)isFileSystemFreeSizeLimitReached {
    NSTimeInterval currentTime = NSDate.timeIntervalSinceReferenceDate;
    if (currentTime-_timeOfLastIsFileSystemFreeSizeLimitReachedVerification > 20) {
        // refresh _isFileSystemFreeSizeLimitReached
        NSDictionary* dataBasePathAttrs = [[NSFileManager defaultManager] attributesOfFileSystemForPath:self.dataBaseDirPath error:NULL];
        NSNumber* dataBasePathSize = [dataBasePathAttrs objectForKey:NSFileSystemSize];
        NSNumber* dataBasePathFreeSize = [dataBasePathAttrs objectForKey:NSFileSystemFreeSize];
        if (dataBasePathFreeSize && dataBasePathSize) {
            unsigned long long sizeBytes = [dataBasePathSize unsignedLongLongValue], sizeMegaBytes = sizeBytes/1024/1024;
            unsigned long long freeBytes = [dataBasePathFreeSize unsignedLongLongValue], freeMegaBytes = freeBytes/1024/1024;
            
            unsigned long long thresholdMegaBytes = MIN(300, sizeMegaBytes/100); // 300 MB is the lower limit, but if the disk is small, the threshold is put at 1/100 the disk's size
            
            _isFileSystemFreeSizeLimitReached = freeMegaBytes < thresholdMegaBytes;
            _timeOfLastIsFileSystemFreeSizeLimitReachedVerification = currentTime;
            
            if (_isFileSystemFreeSizeLimitReached)
                NSLog(@"Warning: the volume used to store data for %@ is full; queued incoming files are preserved and new DICOM transfers will be rejected", self.name);
        } else return YES;
    }
    
    return _isFileSystemFreeSizeLimitReached;
}



//- (void)listenerAnonymizeFiles: (NSArray*)files
//{
//#ifndef OSIRIX_LIGHT
//	NSArray* array = [NSArray arrayWithObjects: [DCMAttributeTag tagWithName:@"PatientsName"], @"**anonymized**", nil];
//	NSMutableArray* tags = [NSMutableArray array];
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
//          N2LogExceptionWithStackTrace(e);
//		}
//
//		[[NSFileManager defaultManager] removeItemAtPath: file error:NULL];
//		[[NSFileManager defaultManager] movePath:destPath toPath: file handler: nil];
//	}
//#endif
//}

-(BOOL)compressFilesAtPaths:(NSArray*)paths
{
    return [DicomDatabase compressDicomFilesAtPaths:paths];
}

-(BOOL)compressFilesAtPaths:(NSArray*)paths intoDirAtPath:(NSString*)destDir
{
    return [DicomDatabase compressDicomFilesAtPaths:paths intoDirAtPath:destDir];
}

-(BOOL)decompressFilesAtPaths:(NSArray*)paths
{
    return [DicomDatabase decompressDicomFilesAtPaths:paths];
}

-(BOOL)decompressFilesAtPaths:(NSArray*)paths intoDirAtPath:(NSString*)destDir
{
    return [DicomDatabase decompressDicomFilesAtPaths:paths intoDirAtPath:destDir];
}

-(NSNumber*)_processFilesAtPaths_processChunk:(NSArray*)io {
    NSArray* chunk = [io objectAtIndex:0];
    int mode = [[io objectAtIndex:1] intValue];
    NSString* destDir = nil;
    if( io.count >= 3)
        destDir = [io objectAtIndex:2];
    
    if (mode == Compress)
        return [NSNumber numberWithBool:[DicomDatabase compressDicomFilesAtPaths:chunk intoDirAtPath:destDir]];
    else
        return [NSNumber numberWithBool:[DicomDatabase decompressDicomFilesAtPaths:chunk intoDirAtPath:destDir]];
}

-(void)processFilesAtPaths:(NSArray*)paths intoDirAtPath:(NSString*)destDir mode:(int)mode
{
    [self processFilesAtPaths:paths intoDirAtPath:destDir mode:mode error:NULL];
}

-(BOOL)processFilesAtPaths:(NSArray*)paths intoDirAtPath:(NSString*)destDir mode:(int)mode error:(NSError**)error
{
    BOOL succeeded = YES;
    NSOperationQueue* queue = nil;
    NSThread* thread = [NSThread currentThread];
    
    if (mode == Compress)
        thread.name = [NSString stringWithFormat: NSLocalizedString( @"Compressing %@", nil), N2LocalizedSingularPluralCount( paths.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil))];
    else
        thread.name = [NSString stringWithFormat: NSLocalizedString( @"Decompressing %@", nil), N2LocalizedSingularPluralCount( paths.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil))];
    
    thread.status = NSLocalizedString(@"Waiting for similar threads to complete...", nil);
    thread.progress = -1;
    
    if (![thread isMainThread])
        [[ThreadsManager defaultManager] addThreadAndStart:thread]; // this thread will be added more than one time, manager supports this.
    
    [_processFilesLock lock];
    @try
    {
        thread.status = NSLocalizedString(@"Processing...", nil);
        
        size_t nTasks = 10;
        size_t chunkSize = paths.count/nTasks;
        if (chunkSize < 100) chunkSize = 100;
        
        NSArray* chunks = [paths splitArrayIntoArraysOfMinSize:chunkSize maxArrays:nTasks];
        
        queue = [NSOperationQueue new];
        NSMutableArray *operations = [NSMutableArray array];
        NSUInteger nProcs = [[NSProcessInfo processInfo] processorCount];
        queue.maxConcurrentOperationCount = MAX(nProcs-1, 1);
        for (NSArray* chunk in chunks)
        {
            NSInvocationOperation *operation = [[[NSInvocationOperation alloc] initWithTarget:self selector:@selector(_processFilesAtPaths_processChunk:) object:[NSArray arrayWithObjects:chunk, [NSNumber numberWithInt:mode], destDir, nil]] autorelease];
            [operations addObject:operation];
            [queue addOperation:operation];
        }
        
        NSUInteger initialOpCount = queue.operationCount;
        while (queue.operationCount) {
            if (queue.operationCount != initialOpCount)
                thread.progress = CGFloat(initialOpCount-queue.operationCount)/initialOpCount;
            [NSThread sleepForTimeInterval:0.01];
        }
        
        [queue waitUntilAllOperationsAreFinished];
        for (NSInvocationOperation *operation in operations)
            if (![[operation result] boolValue])
                succeeded = NO;
    }
    @catch (NSException* e)
    {
        succeeded = NO;
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [queue waitUntilAllOperationsAreFinished];
        [queue release];
        [_processFilesLock unlock];
        //		[thread popLevel];
    }
    if (!succeeded && error)
        *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileWriteUnknownError userInfo:@{
            NSLocalizedDescriptionKey: NSLocalizedString(@"DICOM conversion could not be completed.", nil),
            NSLocalizedFailureReasonErrorKey: NSLocalizedString(@"The compression or decompression process failed. Check that the input files are accessible and valid DICOM files.", nil)
        }];
    return succeeded;
}

-(void)threadBridgeForProcessFilesAtPaths:(NSDictionary*)params
{
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
    
    NSThread* thread = [NSThread currentThread];
    thread.name = NSLocalizedString(@"Waiting for processing files...", nil);
    
    [ThreadsManager.defaultManager addThreadAndStart: thread];
    
    static NSString *singleThread = @"threadBridgeForProcessFilesAtPaths";
    static int numberOfWaitingThreads = 0;
    
    if( numberOfWaitingThreads < 50)
    {
        numberOfWaitingThreads++;
        
        @synchronized( singleThread)
        {
            @try
            {
                if( self.isMainDatabase)
                    [self.independentDatabase processFilesAtPaths:[params objectForKey:@":"] intoDirAtPath:[params objectForKey:@"intoDirAtPath:"] mode:[[params objectForKey:@"mode:"] intValue]];
                else
                    [self processFilesAtPaths:[params objectForKey:@":"] intoDirAtPath:[params objectForKey:@"intoDirAtPath:"] mode:[[params objectForKey:@"mode:"] intValue]];
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
        
        numberOfWaitingThreads--;
    }
}

-(void)initiateProcessFilesAtPaths:(NSArray*)paths intoDirAtPath:(NSString*)destDir mode:(int)mode
{
    [self performSelectorInBackground:@selector(threadBridgeForProcessFilesAtPaths:) withObject:[NSDictionary dictionaryWithObjectsAndKeys: paths, @":", [NSNumber numberWithInt:mode], @"mode:", destDir, @"intoDirAtPath:", /*destDir can be nil*/nil]];
}

-(void)initiateCompressFilesAtPaths:(NSArray*)paths
{
    [self initiateProcessFilesAtPaths:paths intoDirAtPath:nil mode:Compress];
}

-(void)initiateCompressFilesAtPaths:(NSArray*)paths intoDirAtPath:(NSString*)destDir
{
    [self initiateProcessFilesAtPaths:paths intoDirAtPath:destDir mode:Compress];
}

-(void)initiateDecompressFilesAtPaths:(NSArray*)paths
{
    [self initiateProcessFilesAtPaths:paths intoDirAtPath:nil mode:Decompress];
}

-(void)initiateDecompressFilesAtPaths:(NSArray*)paths intoDirAtPath:(NSString*)destDir
{
    [self initiateProcessFilesAtPaths:paths intoDirAtPath:destDir mode:Decompress];
}

// Defined further down, beside the incoming folder's own use of it: two archives
// can each hold a readme.txt, and moving the second onto the first fails.
static NSString *availablePathInDirectory( NSString *directory, NSString *name);

-(NSArray*)addFilesAtPaths:(NSArray*)paths
{
    return [self addFilesAtPaths:paths postNotifications:YES];
}

-(NSArray*)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)postNotifications
{
    return [self addFilesAtPaths:paths postNotifications:postNotifications dicomOnly:[[NSUserDefaults standardUserDefaults] boolForKey: @"onlyDICOM"] rereadExistingItems:NO];
}

-(NSArray*)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)postNotifications dicomOnly:(BOOL)dicomOnly rereadExistingItems:(BOOL)rereadExistingItems
{
    return [self addFilesAtPaths:paths postNotifications:postNotifications dicomOnly:dicomOnly rereadExistingItems:rereadExistingItems generatedByOsiriX:NO];
}

-(NSArray*)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)postNotifications dicomOnly:(BOOL)dicomOnly rereadExistingItems:(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX
{
    return [self addFilesAtPaths: paths postNotifications:postNotifications dicomOnly:dicomOnly rereadExistingItems:rereadExistingItems generatedByOsiriX:generatedByOsiriX returnArray: YES];
}

-(NSArray*)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)postNotifications dicomOnly:(BOOL)dicomOnly rereadExistingItems:(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX returnArray: (BOOL) returnArray
{
    return [self addFilesAtPaths: paths postNotifications: postNotifications dicomOnly: dicomOnly rereadExistingItems: rereadExistingItems generatedByOsiriX: generatedByOsiriX importedFiles: NO returnArray: returnArray];
}

-(NSArray*)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)postNotifications dicomOnly:(BOOL)dicomOnly rereadExistingItems:(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX importedFiles: (BOOL) importedFiles returnArray: (BOOL) returnArray
{
    NSThread* thread = [NSThread currentThread];
    
    //#define RANDOMFILES
#ifdef RANDOMFILES
    NSMutableArray* randomArray = [NSMutableArray array];
    for( int i = 0; i < 50000; i++)
        [randomArray addObject:@"yahoo/google/osirix/microsoft"];
    paths = randomArray;
#endif
    
#ifndef NDEBUG
    [self checkForCorrectContextThread];
#endif
    
    NSMutableArray* retArray = nil; // This array can be HUGE when rebuild a DB with millions of images
    
    if( returnArray)
        retArray = [NSMutableArray array];
    
    NSString* errorsDirPath = self.errorsDirPath;
    NSString* dataDirPath = self.dataDirPath;
    NSString* reportsDirPath = self.reportsDirPath;
    //NSString* tempDirPath = self.tempDirPath;
    
    [thread enterOperation];
    thread.status = [NSString stringWithFormat:NSLocalizedString(@"Scanning %@", nil), N2LocalizedSingularPluralCount(paths.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil))];
    
    NSArray* chunkRanges = [paths splitArrayIntoChunksOfMinSize:20000 maxChunks:0];
    for (NSUInteger chunkIndex = 0; chunkIndex < chunkRanges.count; ++chunkIndex)
    {
        NSAutoreleasePool* pool2 = [[NSAutoreleasePool alloc] init];
        
        NSRange chunkRange = [[chunkRanges objectAtIndex:chunkIndex] rangeValue];
        
        BOOL DELETEFILELISTENER = [[NSUserDefaults standardUserDefaults] boolForKey: @"DELETEFILELISTENER"], addFailed = NO;
        NSMutableArray *dicomFilesArray = [NSMutableArray arrayWithCapacity:chunkRange.length];
        
        // A file that cannot be turned into an instance was dropped in silence
        // unless it was already inside the database folder. On a medium that means
        // a study quietly missing images, with nothing to say which.
        HorosImportRefusals *refusals = [[[HorosImportRefusals alloc] initWithConsidered: chunkRange.length] autorelease];
        
        // What the previous import refused stops being current the moment another
        // one has files of its own. An idle scan - the usual case, several times a
        // minute - leaves the line alone, so a refusal stays readable.
        if (chunkIndex == 0 && chunkRange.length)
            [self setLastImportRefusalSummary: nil];
        
        // A file inside the database folder that cannot be indexed has to leave it,
        // or it sits there for ever with no row pointing at it. This used to be
        // done only for a file that opened and produced no dictionary; a file that
        // -[DicomFile init:] could not construct at all fell outside the enclosing
        // if( curFile) and was left where it was. Measured on an import of 1204
        // files, one truncated: the database folder ended with 1201 files for 1200
        // images, and NOT READABLE was empty.
        void (^disposeOfUnreadable)(NSString*) = ^(NSString *unreadable)
        {
            if (dataDirPath == nil || [unreadable hasPrefix: dataDirPath] == NO)
                return;
            
            if (DELETEFILELISTENER)
            {
                NSError *removeError = nil;
                if ([[NSFileManager defaultManager] removeItemAtPath: unreadable error: &removeError])
                    NSLog( @"---- import: %@ could not be indexed; deleted (DELETEFILELISTENER)",
                          unreadable.lastPathComponent);
                else
                    NSLog( @"---- import: %@ could not be indexed and could not be deleted (%@); "
                          @"it stays in the database folder", unreadable.lastPathComponent,
                          removeError.localizedDescription);
                return;
            }
            
            NSString *kept = availablePathInDirectory( errorsDirPath, unreadable.lastPathComponent);
            NSError *moveError = nil;
            if ([[NSFileManager defaultManager] moveItemAtPath: unreadable toPath: kept error: &moveError])
                NSLog( @"---- import: %@ could not be indexed; kept in %@",
                      unreadable.lastPathComponent, errorsDirPath.lastPathComponent);
            else
            {
                NSLog( @"---- import: %@ could not be indexed and could not be kept (%@); deleted",
                      unreadable.lastPathComponent, moveError.localizedDescription);
                [[NSFileManager defaultManager] removeItemAtPath: unreadable error: NULL];
            }
        };
        
        if ([[NSFileManager defaultManager] fileExistsAtPath: dataDirPath] == NO)
            [[NSFileManager defaultManager] createDirectoryAtPath: dataDirPath withIntermediateDirectories:YES attributes:nil error:NULL];
        
        if ([[NSFileManager defaultManager] fileExistsAtPath: reportsDirPath] == NO)
            [[NSFileManager defaultManager] createDirectoryAtPath: reportsDirPath withIntermediateDirectories:YES attributes:nil error:NULL];
        
        if (chunkRange.length == 0)
            break;
        
        NSTimeInterval start = [NSDate timeIntervalSinceReferenceDate];
        
        for (NSUInteger i = chunkRange.location; i < chunkRange.location+chunkRange.length; ++i)
        {
            if( [NSDate timeIntervalSinceReferenceDate] - start > 0.5 || i == chunkRange.location+chunkRange.length-1) {
                thread.progress = 1.0*i/paths.count;
                start = [NSDate timeIntervalSinceReferenceDate];
            }
            
        
            NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
            @try {
                NSString* newFile = [paths objectAtIndex:i];
                DicomFile *curFile = nil;
                NSMutableDictionary	*curDict = nil;
                
                @try {
#ifdef RANDOMFILES
                    curFile = [[DicomFile alloc] initRandom];
#else
                    curFile = [[DicomFile alloc] init:newFile];
#endif
                } @catch (NSException* e)
                {
                    N2LogExceptionWithStackTrace(e);
                }
                
                if (curFile == nil)
                {
                    [refusals refuse: newFile];
                    disposeOfUnreadable( newFile);
                }
                
                if (curFile)
                {
                    curDict = [curFile dicomElements];
                    // A file the reader understood, refused because this database
                    // indexes only DICOM. Saying it could not be read would send
                    // someone looking for a fault in a file that has none.
                    NSString *refusedByPolicy = nil;
                    if (dicomOnly)
                    {
                        NSString *kind = [curDict objectForKey: @"fileType"];
                        if ([kind hasPrefix:@"DICOM"] == NO)
                        {
                            refusedByPolicy = [NSString stringWithFormat:
                                NSLocalizedString(@"is %@, and this database indexes only DICOM "
                                                  @"(see the onlyDICOM preference)", nil),
                                kind.length ? kind : NSLocalizedString(@"not DICOM", nil)];
                            curDict = nil;
                        }
                    }
                    
                    if (curDict)
                    {
                        [dicomFilesArray addObject: curDict];
                    }
                    else
                    {
                        if (refusedByPolicy)
                            [refusals refuse: newFile reason: refusedByPolicy];
                        else
                            [refusals refuse: newFile];
                        disposeOfUnreadable( newFile);
                    }
                    
                    [curFile release];
                }
            }
            @catch (NSException* e)
            {
                N2LogExceptionWithStackTrace(e);
            }
            @finally
            {
                [pool release];
            }
            
            if (thread.isCancelled)
            {
                [dicomFilesArray removeAllObjects];
                break;
            }
            
            BOOL cancelled = NO;
            for( NSOperation *o in [[NSOperationQueue currentQueue] operations])
            {
                if( o.isCancelled)
                    cancelled = YES;
            }
            if( cancelled)
            {
                [dicomFilesArray removeAllObjects];
                break;
            }
        }
        
        if (refusals.count)
        {
            NSLog( @"(addFilesAtPaths): %@", refusals.summary);
            // The incoming scanner calls this once per batch, so a refusal in one
            // batch must not be erased by the next batch being clean. The scan
            // clears the line when it starts.
            [self addImportRefusalSummary: refusals.summary];
        }
        
        [thread enterOperationIgnoringLowerLevels];
        thread.status = [NSString stringWithFormat:NSLocalizedString(@"Adding %@", nil), N2LocalizedSingularPluralCount(dicomFilesArray.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil))];
        //        NSLog(@"before: %X", self.managedObjectContext);
        //      NSArray* addedImagesArray = [self addFilesInDictionaries:dicomFilesArray postNotifications:postNotifications rereadExistingItems:rereadExistingItems generatedByOsiriX:generatedByOsiriX];
        
        NSArray* objectIDs = [self addFilesDescribedInDictionaries:dicomFilesArray
                                                 postNotifications:postNotifications
                                               rereadExistingItems:rereadExistingItems
                                                 generatedByOsiriX:generatedByOsiriX
                                                     importedFiles: importedFiles
                                                       returnArray: returnArray];
        
        [thread exitOperation];
        
        
        //	[[NSFileManager defaultManager] removeItemAtPath: @"/tmp/dicomsr_osirix" error:NULL]; // nooooooo because other threads may be using it
        
        if (addFailed)
        {
            NSLog(@"adding failed....");
            
            return nil;
        }
        
        if( returnArray)
            [retArray addObjectsFromArray: objectIDs];
        else
        {
            [self.managedObjectContext save: nil];
            [self.managedObjectContext reset];
            
            NSLog( @"%d / %d", (int) chunkIndex, (int) chunkRanges.count);
        }
        
        [pool2 release];
    }
    
    [thread exitOperation];
    
    return retArray;
}

/*
 Keys in (MUTABLE) dictionaries:
 
 filePath
 SOPClassUID
 seriesDescription
 seriesID (?)
 fileType
 studyID
 patientUID
 modality
 
 accessionNumber
 patientBirthDate
 patientSex
 patientName
 patientID
 studyNumber
 studyDescription
 referringPhysiciansName
 performingPhysiciansName
 institutionName
 
 hasDICOM
 studyDate
 date
 seriesDICOMUID
 SOPClassUID
 seriesID
 seriesDescription
 seriesNumber
 studyDate
 protocolName
 
 numberOfFrames
 SOPUID* ()
 imageID* ()
 
 sliceLocation
 fileType
 height
 width
 numberOfSeries
 numberOfROIs
 referencedSOPInstanceUID
 commentsAutoFill
 seriesComments
 studyComments
 stateText
 keyFrames
 
 album
 
 
 addFilesDescribedInDictionaries:postNotifications:rereadExistingItems:generatedByOsiriX:
 
 */
-(NSArray*)addFilesDescribedInDictionaries:(NSArray*)dicomFilesArray postNotifications:(BOOL)postNotifications rereadExistingItems:(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX
{
    return [self addFilesDescribedInDictionaries: dicomFilesArray postNotifications: postNotifications rereadExistingItems: rereadExistingItems generatedByOsiriX: generatedByOsiriX returnArray: YES];
}

static BOOL protectionAgainstReentry = NO;

-(NSArray*)addFilesDescribedInDictionaries:(NSArray*)dicomFilesArray postNotifications:(BOOL)postNotifications rereadExistingItems:(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX returnArray: (BOOL) returnArray
{
    return [self addFilesDescribedInDictionaries: dicomFilesArray postNotifications: postNotifications rereadExistingItems: rereadExistingItems generatedByOsiriX: generatedByOsiriX importedFiles: NO returnArray: returnArray];
}

static BOOL HorosIncomingLooksLikeCloudReport(NSDictionary *dict)
{
    NSString *sop = [dict objectForKey:@"SOPClassUID"];
    NSString *mod = [dict objectForKey:@"modality"];
    NSString *desc = [dict objectForKey:@"seriesDescription"];
    NSString *mfr = [dict objectForKey:@"manufacturer"];
    if ([DCMAbstractSyntaxUID isPDF:sop] || [DCMAbstractSyntaxUID isStructuredReport:sop])
        return YES;
    if ([mod caseInsensitiveCompare:@"DOC"] == NSOrderedSame)
        return YES;
    if ([desc rangeOfString:@"Cloud" options:NSCaseInsensitiveSearch].location != NSNotFound)
        return YES;
    if ([mfr rangeOfString:@"Cloud" options:NSCaseInsensitiveSearch].location != NSNotFound)
        return YES;
    return NO;
}

// Group a Cloud/PDF report with the study it references. Name alone does not
// join patients or studies. The file keeps its original Study Instance UID.
static void HorosAssociateCloudReports(NSArray *dicomFilesArray, NSArray *studiesArray)
{
    Class assoc = NSClassFromString(@"HorosCloudReportAssociation");
    if (assoc == Nil)
        return;
    SEL sel = @selector(associateReportsInFiles:existingStudies:);
    if (![assoc respondsToSelector:sel])
        return;

    BOOL maybeReport = NO;
    for (id item in dicomFilesArray)
    {
        if ([item isKindOfClass:[NSDictionary class]] && HorosIncomingLooksLikeCloudReport(item))
        {
            maybeReport = YES;
            break;
        }
    }
    if (!maybeReport)
        return;

    NSMutableArray *known = [NSMutableArray array];
    for (DicomStudy *study in studiesArray)
    {
        NSMutableArray *sops = [NSMutableArray array];
        for (DicomSeries *series in [[study valueForKey:@"series"] allObjects])
        {
            for (id image in [[series valueForKey:@"images"] allObjects])
            {
                NSString *uid = [image valueForKey:@"sopInstanceUID"];
                if ([uid length])
                    [sops addObject:uid];
            }
        }
        NSMutableDictionary *entry = [NSMutableDictionary dictionary];
        if (study.studyInstanceUID)
            [entry setObject:study.studyInstanceUID forKey:@"studyID"];
        if (study.patientUID)
            [entry setObject:study.patientUID forKey:@"patientUID"];
        if (study.name)
            [entry setObject:study.name forKey:@"patientName"];
        if (study.patientID)
            [entry setObject:study.patientID forKey:@"patientID"];
        [entry setObject:sops forKey:@"SOPUIDs"];
        [known addObject:entry];
    }
    ((void (*)(id, SEL, id, id))objc_msgSend)(assoc, sel, dicomFilesArray, known);
}

-(NSArray*)addFilesDescribedInDictionaries:(NSArray*)dicomFilesArray postNotifications:(BOOL)postNotifications rereadExistingItems:(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX importedFiles: (BOOL) importedFiles returnArray: (BOOL) returnArray
{
#ifndef NDEBUG
    [self checkForCorrectContextThread];
#endif
    
    NSThread* thread = [NSThread currentThread];
    thread.status = [NSString stringWithFormat:NSLocalizedString(@"Adding %@", nil), N2LocalizedSingularPluralCount(dicomFilesArray.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil))];
    
    NSUInteger rejectedReports = 0;
    NSMutableArray* newStudies = [NSMutableArray array];
    
    NSMutableArray* addedImageObjects = nil;
    NSMutableArray* completeAddedImageObjects = nil;
    NSMutableDictionary* addedImagesPerCreatorUID = nil;
    NSMutableDictionary* completeAddedImagesPerCreatorUID = nil;
    
    if( returnArray)
    {
        addedImageObjects = [NSMutableArray arrayWithCapacity:[dicomFilesArray count]];
        completeAddedImageObjects = [NSMutableArray arrayWithCapacity:[dicomFilesArray count]];
        addedImagesPerCreatorUID = [NSMutableDictionary dictionary];
        completeAddedImagesPerCreatorUID = [NSMutableDictionary dictionary];
    }
    
    BOOL newStudy = NO;
    
    //  NSLog(@"Add: %@", dicomFilesArray);
    
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init]; // It has to be done after the NSMutableArray autorelease: we will return it.
    
    [self cleanForFreeSpace];
    
    @try
    {
        NSMutableArray* studiesArray = [[self objectsForEntity:self.studyEntity] mutableCopy];
        NSMutableArray* modifiedStudiesArray = [NSMutableArray array];
        
        NSDate *defaultDate = [NSCalendarDate dateWithYear:1901 month:1 day:1 hour:0 minute:0 second:0 timeZone:nil];
        
        DicomStudy *study = nil;
        DicomSeries *seriesTable = nil;
        DicomImage *image = nil;
        NSMutableArray *studiesArrayStudyInstanceUID = [[studiesArray valueForKey:@"studyInstanceUID"] mutableCopy];
        NSString *curPatientUID = nil, *curStudyID = nil, *curSerieID = nil;
        BOOL newObject = NO;
        
        NSDate* today = [NSDate date];
        NSString* dataDirPath = self.dataDirPath;
        NSString* reportsDirPath = self.reportsDirPath;
        NSString* errorsDirPath = self.errorsDirPath;
        int combineProjectionSeries = [[NSUserDefaults standardUserDefaults] boolForKey:@"combineProjectionSeries"], combineProjectionSeriesMode = [[NSUserDefaults standardUserDefaults] boolForKey: @"combineProjectionSeriesMode"];
        BOOL COMMENTSAUTOFILL = [[NSUserDefaults standardUserDefaults] boolForKey: @"COMMENTSAUTOFILL"];
        BOOL DELETEFILELISTENER = [[NSUserDefaults standardUserDefaults] boolForKey: @"DELETEFILELISTENER"];
        NSString *commentField = [[NSUserDefaults standardUserDefaults] stringForKey: @"commentFieldForAutoFill"];
        BOOL COMMENTSAUTOFILLSeriesLevel = [[NSUserDefaults standardUserDefaults] boolForKey: @"COMMENTSAUTOFILLSeriesLevel"];
        BOOL COMMENTSAUTOFILLStudyLevel = [[NSUserDefaults standardUserDefaults] boolForKey: @"COMMENTSAUTOFILLStudyLevel"];
        
        HorosAssociateCloudReports(dicomFilesArray, studiesArray);
        
        NSString* newFile = nil;
        NSTimeInterval start = [NSDate timeIntervalSinceReferenceDate];
        // Add the new files
        for (NSInteger i = 0; i < dicomFilesArray.count; ++i)
        {
            if( [NSDate timeIntervalSinceReferenceDate] - start > 0.5 || i == dicomFilesArray.count-1) {
                thread.progress = 1.0*i/dicomFilesArray.count;
                start = [NSDate timeIntervalSinceReferenceDate];
            }
            
            @autoreleasepool
            {
                NSString *preparedReportPath = nil;
                @try
                {
                    NSMutableDictionary *curDict = [dicomFilesArray objectAtIndex:i];
                    //				NSLog(@"curDict: %@", curDict);
                    
                    newFile = [curDict objectForKey:@"filePath"];
                    
                    BOOL DICOMSR = NO;
                    BOOL inParseExistingObject = rereadExistingItems;
                    
                    NSString *SOPClassUID = [curDict objectForKey:@"SOPClassUID"];
                    
                    if ([DCMAbstractSyntaxUID isStructuredReport: SOPClassUID])
                    {
                        // Check if it is an OsiriX Annotations SR
                        if ([[curDict valueForKey:@"seriesDescription"] isEqualToString: @"OsiriX Annotations SR"])
                        {
                            [curDict setValue: @"OsiriX Annotations SR" forKey: @"seriesID"];
                            inParseExistingObject = YES;
                            DICOMSR = YES;
                        }
                        
                        // Check if it is an OsiriX ROI SR
                        if ([[curDict valueForKey:@"seriesDescription"] isEqualToString: @"OsiriX ROI SR"])
                        {
                            [curDict setValue: @"OsiriX ROI SR" forKey: @"seriesID"];
                            
                            inParseExistingObject = YES;
                            DICOMSR = YES;
                        }
                        
                        // Check if it is an OsiriX Report SR
                        if ([[curDict valueForKey:@"seriesDescription"] isEqualToString: @"OsiriX Report SR"])
                        {
                            NSError *extractionError = nil;
                            preparedReportPath = [DicomDatabase extractReportSR:newFile contentDate:[curDict objectForKey:@"studyDate"] error:&extractionError];
                            if (extractionError) {
                                ++rejectedReports;
                                HorosQuarantineUnindexedImport((N2ManagedObjectContext *)self.managedObjectContext, newFile, dataDirPath, errorsDirPath);
                                NSLog(@"Report import rejected before indexing: %@", extractionError.localizedDescription);
                                continue;
                            }
                            [curDict setValue: @"OsiriX Report SR" forKey: @"seriesID"];
                            
                            inParseExistingObject = YES;
                            DICOMSR = YES;
                        }
                        
                        // Check if it is an OsiriX WindowsState SR
                        if ([[curDict valueForKey:@"seriesDescription"] isEqualToString: @"OsiriX WindowsState SR"])
                        {
                            [curDict setValue: @"OsiriX WindowsState SR" forKey: @"seriesID"];
                            
                            inParseExistingObject = YES;
                            DICOMSR = YES;
                        }
                    }
                    
                    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"acceptUnsupportedSOPClassUID"] == NO)
                    {
                        if( SOPClassUID != nil)
                        {
                            BOOL supportedSOPClass = NO;
                            for( NSString *s in [DCMAbstractSyntaxUID allSupportedSyntaxes])
                            {
                                if( [SOPClassUID hasPrefix: s])
                                {
                                    supportedSOPClass = YES;
                                    break;
                                }
                            }
                            
                            if( supportedSOPClass == NO)
                            {
                                NSLog( @"unsupported DICOM SOP CLASS (%@)-> for the file : %@", SOPClassUID, newFile);
                                //                                curDict = nil;
                            }
                        }
                    }
                    
                    if ([curDict objectForKey:@"SOPClassUID"] == nil && [[curDict objectForKey: @"fileType"] hasPrefix:@"DICOM"] == YES)
                    {
                        NSLog(@"no DICOM SOP CLASS -> for the file: %@", newFile);
                        //                        curDict = nil;
                    }
                    
                    if (curDict != nil)
                    {
                        if ([[curDict objectForKey: @"studyID"] isEqualToString: curStudyID] &&
                            [[curDict objectForKey: @"patientUID"] compare: curPatientUID options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
                        {
                            if ([[study valueForKey: @"modality"] isEqualToString: @"SR"] || [[study valueForKey: @"modality"] isEqualToString: @"OT"])
                                [study setValue: [curDict objectForKey: @"modality"] forKey:@"modality"];
                        }
                        else
                        {
                            /*******************************************/
                            /*********** Find study object *************/
                            // match: StudyInstanceUID and patientUID (see patientUID function in dicomFile.m, based on patientName, patientID and patientBirthDate)
                            study = nil;
                            curSerieID = nil;
                            
                            NSInteger index = [studiesArrayStudyInstanceUID indexOfObject:[curDict objectForKey: @"studyID"]];
                            
                            newObject = NO;
                            
                            if (index != NSNotFound)
                            {
                                if ([[curDict objectForKey: @"fileType"] hasPrefix:@"DICOM"] == NO) // We do this double check only for DICOM files.
                                {
                                    study = [studiesArray objectAtIndex: index];
                                }
                                else
                                {
                                    DicomStudy* tstudy = [studiesArray objectAtIndex:index];
                                    
                                    // is this actually an empty study? if so, treat it as a newObject
                                    NSSet* series = [tstudy series];
                                    if (series.count == 1 && [[series.anyObject id] intValue] == 5005 && [[series.anyObject name] isEqualToString:@"OsiriX No Autodeletion"]) {
                                        newObject = YES;
                                        tstudy.dateAdded = today;
                                        tstudy.patientUID = [curDict objectForKey: @"patientUID"];
                                    }
                                    
                                    if (!tstudy.patientUID)
                                        tstudy.patientUID = [curDict objectForKey: @"patientUID"];
                                    
                                    if ([[curDict objectForKey: @"patientUID"] compare:tstudy.patientUID options:NSCaseInsensitiveSearch|NSDiacriticInsensitiveSearch|NSWidthInsensitiveSearch] == NSOrderedSame)
                                        study = tstudy;
                                    else
                                    {
                                        // Are there multiple studies with same studyInstanceUID ???
                                        NSString *curUID = [curDict objectForKey: @"studyID"];
                                        for( int i = 0 ; i < [studiesArrayStudyInstanceUID count]; i++)
                                        {
                                            NSString *uid = [studiesArrayStudyInstanceUID objectAtIndex: i];
                                            
                                            if ([uid isEqualToString: curUID])
                                            {
                                                if ([[curDict objectForKey: @"patientUID"] compare:[[studiesArray objectAtIndex: i] patientUID] options:NSCaseInsensitiveSearch|NSDiacriticInsensitiveSearch|NSWidthInsensitiveSearch] == NSOrderedSame)
                                                    study = [studiesArray objectAtIndex:i];
                                            }
                                        }
                                        
                                        if( study == nil)
                                        {
                                            // Two identifiers side by side leave the reader to
                                            // spot the difference and then work out which tag
                                            // produced it. A differing key can be a genuinely
                                            // different person, so name what differs.
                                            NSString *existingUID = [[studiesArray objectAtIndex: index] valueForKey: @"patientUID"];
                                            NSString *arrivingUID = [curDict objectForKey: @"patientUID"];
                                            NSLog( @"-*-*-*-*-* same studyUID (%@), but not same patientUID: %@", [curDict objectForKey: @"studyID"], [HorosPatientIdentity differenceBetweenUID: arrivingUID? arrivingUID : @"" andUID: existingUID? existingUID : @""]);
                                            
                                            if( self.hasPotentiallySlowDataAccess) //It's a CD... be less restrictive !
                                                study = tstudy;
                                        }
                                    }
                                }
                            }
                            
                            if (study == nil)
                            {
                                // Fields
                                study = [NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:self.managedObjectContext];
                                
                                newObject = YES;
                                newStudy = YES;
                                
                                study.dateAdded = today;
                                
                                [newStudies addObject: study];
                                [studiesArray addObject: study];
                                if( [curDict objectForKey: @"studyID"])
                                    [studiesArrayStudyInstanceUID addObject: [curDict objectForKey: @"studyID"]];
                                else
                                {
                                    N2LogStackTrace( @"no studyID !");
                                    [studiesArrayStudyInstanceUID addObject: @"noStudyID"];
                                }
                                
                                curSerieID = nil;
                            }
                            
                            if (newObject || inParseExistingObject)
                            {
                                study.studyInstanceUID = [curDict objectForKey: @"studyID"];
                                study.accessionNumber = [curDict objectForKey: @"accessionNumber"];
                                study.modality = study.modalities;
                                study.dateOfBirth = [curDict objectForKey: @"patientBirthDate"];
                                study.patientSex = [curDict objectForKey: @"patientSex"];
                                study.patientID = [curDict objectForKey: @"patientID"];
                                study.name = [curDict objectForKey: @"patientName"];
                                study.patientUID = [curDict objectForKey: @"patientUID"];
                                study.id = [curDict objectForKey: @"studyNumber"];
                                
                                if (([DCMAbstractSyntaxUID isStructuredReport: SOPClassUID] || [DCMAbstractSyntaxUID isPDF: SOPClassUID]) && inParseExistingObject)
                                {
                                    if( [[curDict objectForKey: @"studyDescription"] length] && [[curDict objectForKey: @"studyDescription"] isEqualToString: @"unnamed"] == NO)
                                        study.studyName = [curDict objectForKey: @"studyDescription"];
                                    if ([[curDict objectForKey: @"referringPhysiciansName"] length])
                                        study.referringPhysician = [curDict objectForKey: @"referringPhysiciansName"];
                                    if ([[curDict objectForKey: @"performingPhysiciansName"] length])
                                        study.performingPhysician = [curDict objectForKey: @"performingPhysiciansName"];
                                    if ([[curDict objectForKey: @"institutionName"] length])
                                        study.institutionName = [curDict objectForKey: @"institutionName"];
                                }
                                else
                                {
                                    study.studyName = [curDict objectForKey: @"studyDescription"];
                                    study.referringPhysician = [curDict objectForKey: @"referringPhysiciansName"];
                                    study.performingPhysician = [curDict objectForKey: @"performingPhysiciansName"];
                                    study.institutionName = [curDict objectForKey: @"institutionName"];
                                }
                                
                                if( study.studyName.length == 0 || [study.studyName isEqualToString: @"unnamed"])
                                    study.studyName = [curDict objectForKey: @"seriesDescription"];
                                
                                //need to know if is DICOM so only DICOM is queried for Q/R
                                if ([curDict objectForKey: @"hasDICOM"])
                                    study.hasDICOM = [curDict objectForKey: @"hasDICOM"];
                                
                                if (newObject)
                                    [self checkForExistingReportForStudy:study];
                            }
                            else
                            {
                                if ([[study valueForKey: @"modality"] isEqualToString: @"SR"] || [[study valueForKey: @"modality"] isEqualToString: @"OT"])
                                    study.modality = [curDict objectForKey: @"modality"];
                                
                                if ([study valueForKey: @"studyName"] == nil || [[study valueForKey: @"studyName"] isEqualToString: @"unnamed"] || [[study valueForKey: @"studyName"] isEqualToString: @""])
                                    
                                    study.studyName = [curDict objectForKey: @"studyDescription"];
                                if( study.studyName.length == 0 || [study.studyName isEqualToString: @"unnamed"])
                                    study.studyName = [curDict objectForKey: @"seriesDescription"];
                            }
                            
                            if ([curDict objectForKey: @"studyDate"] && [[curDict objectForKey: @"studyDate"] isEqualToDate: defaultDate] == NO)
                            {
                                if ([study valueForKey: @"date"] == 0L || [[study valueForKey: @"date"] isEqualToDate: defaultDate] || [[study valueForKey: @"date"] timeIntervalSinceDate: [curDict objectForKey: @"studyDate"]] >= 0)
                                    [study setValue:[curDict objectForKey: @"studyDate"] forKey:@"date"];
                            }
                            
                            curStudyID = [curDict objectForKey: @"studyID"];
                            curPatientUID = [curDict objectForKey: @"patientUID"];
                            
                            [modifiedStudiesArray addObject: study];
                        }
                        
                        int NoOfSeries = [[curDict objectForKey: @"numberOfSeries"] intValue];
                        for( int i = 0; i < NoOfSeries; i++)
                        {
                            NSString* SeriesNum = i ? [NSString stringWithFormat:@"%d",i] : @"";
                            NSString* curDictSeriesID = [curDict objectForKey:[@"seriesID" stringByAppendingString:SeriesNum]];
                            
                            if ([curDictSeriesID isEqualToString: curSerieID])
                            {
                            }
                            else
                            {
                                /********************************************/
                                /*********** Find series object *************/
                                
                                NSArray *seriesArray = [[study valueForKey:@"series"] allObjects];
                                
                                NSInteger index = [[seriesArray valueForKey:@"seriesInstanceUID"] indexOfObject:[curDict objectForKey: [@"seriesID" stringByAppendingString:SeriesNum]]];
                                if (index == NSNotFound)
                                {
                                    // Fields
                                    seriesTable = [NSEntityDescription insertNewObjectForEntityForName:@"Series" inManagedObjectContext:self.managedObjectContext];
                                    [seriesTable setValue:today forKey:@"dateAdded"];
                                    
                                    newObject = YES;
                                }
                                else
                                {
                                    seriesTable = [seriesArray objectAtIndex: index];
                                    newObject = NO;
                                }
                                
                                if (newObject || inParseExistingObject)
                                {
                                    if ([curDict objectForKey: @"seriesDICOMUID"]) [seriesTable setValue:[curDict objectForKey: @"seriesDICOMUID"] forKey:@"seriesDICOMUID"];
                                    if ([curDict objectForKey: @"SOPClassUID"]) [seriesTable setValue:[curDict objectForKey: @"SOPClassUID"] forKey:@"seriesSOPClassUID"];
                                    [seriesTable setValue:[curDict objectForKey: [@"seriesID" stringByAppendingString:SeriesNum]] forKey:@"seriesInstanceUID"];
                                    [seriesTable setValue:[curDict objectForKey: [@"seriesDescription" stringByAppendingString:SeriesNum]] forKey:@"name"];
                                    [seriesTable setValue:[curDict objectForKey: @"modality"] forKey:@"modality"];
                                    [seriesTable setValue:[curDict objectForKey: [@"seriesNumber" stringByAppendingString:SeriesNum]] forKey:@"id"];
                                    [seriesTable setValue:[curDict objectForKey: @"studyDate"] forKey:@"date"];
                                    [seriesTable setValue:[curDict objectForKey: @"protocolName"] forKey:@"seriesDescription"];
                                    
                                    // Relations
                                    [seriesTable setValue:study forKey:@"study"];
                                    // If a study has an SC or other non primary image  series. May need to change modality to true modality
                                    if (([[study valueForKey:@"modality"] isEqualToString:@"OT"]  || [[study valueForKey:@"modality"] isEqualToString:@"SC"])
                                        && !([[curDict objectForKey: @"modality"] isEqualToString:@"OT"] || [[curDict objectForKey: @"modality"] isEqualToString:@"SC"]))
                                        [study setValue:[curDict objectForKey: @"modality"] forKey:@"modality"];
                                }
                                
                                curSerieID = curDictSeriesID;
                            }
                            
                            /*******************************************/
                            /*********** Find image object *************/
                            
                            BOOL local = NO;
                            if (dataDirPath && [newFile hasPrefix:dataDirPath])
                                local = YES;
                            
                            NSArray	*imagesArray = [[seriesTable valueForKey:@"images"] allObjects];
                            int numberOfFrames = [[curDict objectForKey: @"numberOfFrames"] intValue];
                            if (numberOfFrames == 0)
                                numberOfFrames = 1;
                            
                            for( int f = 0 ; f < numberOfFrames; f++)
                            {
                                image = nil;
                                
                                NSString *SOPUID = [curDict objectForKey: [@"SOPUID" stringByAppendingString: SeriesNum]];
                                
                                @autoreleasepool
                                {
                                    for( DicomImage *ii in imagesArray)
                                    {
                                        if( [ii.sopInstanceUID isEqualToString: SOPUID] && [ii.frameID intValue] == f)
                                        {
                                            image = ii;
                                            break;
                                        }
                                    }
                                }
                                
                                if( image)
                                {
                                    // Does this image contain a valid image path? If not replace it, with the new one
                                    if ([[NSFileManager defaultManager] fileExistsAtPath:[DicomImage completePathForLocalPath: [image valueForKey:@"path"] directory:self.dataBaseDirPath]] == YES &&
                                        inParseExistingObject == NO &&
                                        ![NSUserDefaults.standardUserDefaults boolForKey:@"REPLACE_WITH_NEW_INCOMING_FILE"])
                                    {
                                        if (local)	// Delete this file, it's already in the DB folder
                                        {
                                            if ([[image valueForKey:@"path"] isEqualToString: [newFile lastPathComponent]] == NO)
                                                [[NSFileManager defaultManager] removeItemAtPath: newFile error:NULL];
                                        }
                                        
                                        newObject = NO;
                                    }
                                    else
                                    {
                                        newObject = YES;
                                        
                                        NSString *imPath = [DicomImage completePathForLocalPath: [image valueForKey:@"path"] directory:self.dataBaseDirPath];
                                        
                                        if ([[image valueForKey:@"inDatabaseFolder"] boolValue] && [imPath isEqualToString: newFile] == NO)
                                        {
                                            HorosRetireImportedFileAfterSave((N2ManagedObjectContext *)self.managedObjectContext, imPath, newFile);
                                        }
                                    }
                                }
                                else
                                {
                                    image = [self newObjectForEntity:self.imageEntity];
                                    newObject = YES;
                                }
                                
                                [completeAddedImageObjects addObject:image];
                                
                                NSString* imagePrivateInformationCreatorUID = [curDict objectForKey:@"PrivateInformationCreatorUID"];
                                if (!imagePrivateInformationCreatorUID.length)
                                    imagePrivateInformationCreatorUID = [NSUserDefaults.standardUserDefaults stringForKey:@"AETITLE"];
                                
                                NSMutableArray* completeAddedImagesForImageCreator = [completeAddedImagesPerCreatorUID objectForKey:imagePrivateInformationCreatorUID];
                                if (!completeAddedImagesForImageCreator)
                                    [completeAddedImagesPerCreatorUID setObject:(completeAddedImagesForImageCreator = [NSMutableArray array]) forKey:imagePrivateInformationCreatorUID];
                                
                                [completeAddedImagesForImageCreator addObject:image];
                                
                                if (newObject || inParseExistingObject)
                                {
                                    if (DICOMSR == NO)
                                    {
                                        [seriesTable setValue:today forKey:@"dateAdded"];
                                        study.dateAdded = today;
                                    }
                                    
                                    if (numberOfFrames > 1)
                                    {
                                        [image setValue: [NSNumber numberWithInt: f] forKey:@"frameID"];
                                        
                                        NSString *Modality = [study valueForKey: @"modality"];
                                        if (combineProjectionSeries && combineProjectionSeriesMode == 0 && ([Modality isEqualToString:@"MG"] || [Modality isEqualToString:@"CR"] || [Modality isEqualToString:@"DR"] || [Modality isEqualToString:@"DX"] || [Modality  isEqualToString:@"RF"]))
                                        {
                                            // *******Combine all CR and DR Modality series in a study into one series
                                            long imageInstance = [[curDict objectForKey: [ @"imageID" stringByAppendingString: SeriesNum]] intValue];
                                            imageInstance *= 10000;
                                            imageInstance += f;
                                            [image setValue: [NSNumber numberWithLong: imageInstance] forKey:@"instanceNumber"];
                                        }
                                        else if( [[curDict objectForKey: @"instanceNumberArray"] count] > f)
                                        {
                                            // The acquisition numbered its own frames.
                                            // Adding the file's instance number to the
                                            // frame index numbers them by where they
                                            // happen to be stored instead.
                                            [image setValue: [[curDict objectForKey: @"instanceNumberArray"] objectAtIndex: f] forKey:@"instanceNumber"];
                                        }
                                        else
                                        {
                                            int instanceNumber = [[curDict objectForKey: [@"imageID" stringByAppendingString: SeriesNum]] intValue];
                                            [image setValue: [NSNumber numberWithInt: instanceNumber + f] forKey:@"instanceNumber"];
                                        }
                                    }
                                    else
                                        [image setValue: [curDict objectForKey: [@"imageID" stringByAppendingString: SeriesNum]] forKey:@"instanceNumber"];
                                    
                                    if (local) [image setValue: [newFile lastPathComponent] forKey:@"path"];
                                    else [image setValue:newFile forKey:@"path"];
                                    
                                    [image setValue:[NSNumber numberWithBool: local] forKey:@"inDatabaseFolder"];
                                    
                                    [image setValue:[curDict objectForKey: @"studyDate"]  forKey:@"date"];
                                    
                                    [image setValue:SOPUID forKey:@"sopInstanceUID"];
                                    
                                    if (NSString *originalUID = [curDict objectForKey:@"cloudReportOriginalStudyUID"])
                                    {
                                        if ([originalUID length])
                                        {
                                            NSString *provenance = [NSString stringWithFormat:@"Horos Cloud report originally StudyInstanceUID %@", originalUID];
                                            if ([image valueForKey:@"comment"] == nil)
                                                [image setValue:provenance forKey:@"comment"];
                                            if ([seriesTable valueForKey:@"comment"] == nil)
                                                [seriesTable setValue:provenance forKey:@"comment"];
                                        }
                                    }
                                    
                                    if( [[curDict objectForKey: @"sliceLocationArray"] count] > f)
                                        [image setValue: [[curDict objectForKey: @"sliceLocationArray"] objectAtIndex: f] forKey:@"sliceLocation"];
                                    else
                                        [image setValue:[curDict objectForKey: @"sliceLocation"] forKey:@"sliceLocation"];
                                    
                                    if( [[curDict objectForKey: @"imageCommentPerFrame"] count] > f)
                                        [image setValue: [[curDict objectForKey: @"imageCommentPerFrame"] objectAtIndex: f] forKey:@"comment"];
                                    
                                    [image setValue:[[newFile pathExtension] lowercaseString] forKey:@"extension"];
                                    [image setValue:[curDict objectForKey: @"fileType"] forKey:@"fileType"];
                                    
                                    [image setValue:[curDict objectForKey: @"height"] forKey:@"height"];
                                    [image setValue:[curDict objectForKey: @"width"] forKey:@"width"];
                                    [image setValue:[curDict objectForKey: @"numberOfFrames"] forKey:@"numberOfFrames"];
                                    [image setValue:[curDict objectForKey: @"numberOfSeries"] forKey:@"numberOfSeries"];
                                    
                                    [image setThumbnail:[curDict objectForKey:@"NSImageThumbnail"]];
                                    
                                    if (importedFiles)
                                        image.importedFile = @YES;
                                    else
                                        image.importedFile = nil;
                                    
                                    if (generatedByOsiriX)
                                        [image setValue: [NSNumber numberWithBool: generatedByOsiriX] forKey: @"generatedByOsiriX"];
                                    else
                                        [image setValue: 0L forKey: @"generatedByOsiriX"];
                                    
                                    if (newObject) {
                                        [seriesTable setValue: nil forKey: @"windowWidth"];
                                        [seriesTable setValue: nil forKey: @"windowLevel"];
                                    }
                                    
                                    [image setValue: [curDict objectForKey: @"modality"]  forKey:@"modality"];
                                    [study setValue:[study valueForKey:@"modalities"] forKey:@"modality"];
                                    [seriesTable setValue: nil forKey:@"thumbnail"];
                                    
                                    if (DICOMSR && [curDict objectForKey: @"numberOfROIs"] && [curDict objectForKey: @"referencedSOPInstanceUID"]) // OsiriX ROI SR
                                    {
                                        NSString *s = [curDict objectForKey: @"referencedSOPInstanceUID"];
                                        [image setValue: s forKey:@"comment"];
                                        [image setValue: [curDict objectForKey: @"numberOfROIs"] forKey:@"scale"];
                                    }
                                    
                                    // Relations
                                    [image setValue:seriesTable forKey:@"series"];
                                    
                                    if (DICOMSR == NO)
                                    {
                                        if (COMMENTSAUTOFILL)
                                        {
                                            if([curDict objectForKey: @"commentsAutoFill"])
                                            {
                                                [seriesTable willChangeValueForKey: commentField];
                                                [study willChangeValueForKey: commentField];
                                                
                                                if( COMMENTSAUTOFILLSeriesLevel)
                                                    [seriesTable setPrimitiveValue: [curDict objectForKey: @"commentsAutoFill"] forKey: commentField];
                                                
                                                if( COMMENTSAUTOFILLStudyLevel)
                                                {
                                                    if( [[curDict objectForKey: @"commentsAutoFill"] length] > [[study valueForKey: commentField] length])
                                                        [study setPrimitiveValue:[curDict objectForKey: @"commentsAutoFill"] forKey: commentField];
                                                }
                                                
                                                [seriesTable didChangeValueForKey: commentField];
                                                [study didChangeValueForKey: commentField];
                                            }
                                        }
                                        
                                        if (generatedByOsiriX == NO && [(NSString*)[curDict objectForKey: @"seriesComments"] length] > 0)
                                        {
                                            [seriesTable willChangeValueForKey: @"comment"];
                                            [seriesTable setPrimitiveValue: [curDict objectForKey: @"seriesComments"] forKey: @"comment"];
                                            [seriesTable didChangeValueForKey: @"comment"];
                                        }
                                        
                                        if (generatedByOsiriX == NO && [(NSString*)[curDict objectForKey: @"studyComments"] length] > 0)
                                        {
                                            [study willChangeValueForKey: @"comment"];
                                            [study setPrimitiveValue: [curDict objectForKey: @"studyComments"] forKey: @"comment"];
                                            [study didChangeValueForKey: @"comment"];
                                        }
                                        
                                        if (generatedByOsiriX == NO && [[study valueForKey:@"stateText"] intValue] == 0 && [[curDict objectForKey: @"stateText"] intValue] != 0)
                                        {
                                            [study willChangeValueForKey: @"stateText"];
                                            [study setPrimitiveValue: [curDict objectForKey: @"stateText"] forKey: @"stateText"];
                                            [study didChangeValueForKey: @"stateText"];
                                        }
                                        
                                        if (generatedByOsiriX == NO && [curDict objectForKey: @"keyFrames"])
                                        {
                                            @try
                                            {
                                                for( NSString *k in [curDict objectForKey: @"keyFrames"])
                                                {
                                                    if ([k intValue] == f) // corresponding frame
                                                    {
                                                        [image willChangeValueForKey: @"storedIsKeyImage"];
                                                        [image setPrimitiveValue: [NSNumber numberWithBool: YES] forKey: @"storedIsKeyImage"];
                                                        [image didChangeValueForKey: @"storedIsKeyImage"];
                                                        break;
                                                    }
                                                }
                                            }
                                            @catch (NSException * e) {
                                                N2LogExceptionWithStackTrace(e);
                                            }
                                        }
                                    }
                                    
                                    if (DICOMSR && [[curDict valueForKey:@"seriesDescription"] isEqualToString: @"OsiriX WindowsState SR"])
                                    {
                                        DicomImage *reportSR = [study windowsStateImage]; // return the most recent sr
                                        
                                        if (reportSR == image) // Because we can have multiple sr -> only the most recent one is valid
                                        {
                                            @try {
                                                SRAnnotation *r = [[[SRAnnotation alloc] initWithContentsOfFile: newFile] autorelease];
                                                
                                                NSArray *viewers = [NSPropertyListSerialization propertyListFromData: r.dataEncapsulated mutabilityOption: NSPropertyListImmutable format: nil errorDescription: nil];
                                                
                                                if( viewers.count > 0)
                                                {
                                                    [study willChangeValueForKey: @"windowsState"];
                                                    [study setPrimitiveValue: r.dataEncapsulated forKey: @"windowsState"];
                                                    [study didChangeValueForKey: @"windowsState"];
                                                }
                                            }
                                            @catch (NSException *exception) {
                                                N2LogException( exception);
                                            }
                                        }
                                    }
                                    
                                    if (DICOMSR && [[curDict valueForKey:@"seriesDescription"] isEqualToString: @"OsiriX Report SR"])
                                    {
                                        BOOL reportUpToDate = HorosReportsHaveSameContents([study reportURL], preparedReportPath);
                                        
                                        if (reportUpToDate == NO)
                                        {
                                            //                                            NSString *reportURL = nil; // <- For an empty DICOM SR File
                                            
                                            DicomImage *reportSR = [study reportImage];
                                            
                                            if (reportSR == image) // Because we can have multiple reports -> only the most recent one is valid
                                            {
                                                NSString *reportURL = nil, *reportPath = preparedReportPath;
                                                
                                                if (reportPath)
                                                {
                                                    if ([reportPath length] > 8 && ([reportPath hasPrefix: @"http://"] || [reportPath hasPrefix: @"https://"]))
                                                    {
                                                        reportURL = reportPath;
                                                    }
                                                    else // It's a file!
                                                    {
                                                        NSError *reportError = nil;
                                                        reportURL = HorosPrepareImportedReport((N2ManagedObjectContext *)self.managedObjectContext,
                                                            reportPath, reportsDirPath, &reportError);
                                                        if (!reportURL)
                                                            [NSException raise:@"ReportImport" format:@"Could not prepare the extracted report: %@", reportError.localizedDescription];
                                                    }
                                                    
                                                    NSLog( @"--- DICOM SR -> Report : %@", [curDict valueForKey: @"patientName"]);
                                                }
                                                
                                                [study willChangeValueForKey: @"reportURL"];
                                                if ([reportURL length] > 0)
                                                    [study setPrimitiveValue: reportURL forKey: @"reportURL"];
                                                else
                                                    [study setPrimitiveValue: 0L forKey: @"reportURL"];
                                                [study didChangeValueForKey: @"reportURL"];
                                            }
                                        }
                                    }
                                    
                                    [addedImageObjects addObject:image];
                                    
                                    NSMutableArray* addedImagesForImageCreator = [addedImagesPerCreatorUID objectForKey:imagePrivateInformationCreatorUID];
                                    if (!addedImagesForImageCreator)
                                        [addedImagesPerCreatorUID setObject:(addedImagesForImageCreator = [NSMutableArray array]) forKey:imagePrivateInformationCreatorUID];
                                    
                                    [addedImagesForImageCreator addObject:image];
                                    
                                    //								if(seriesTable && [addedSeries containsObject: seriesTable] == NO)
                                    //									[addedSeries addObject: seriesTable];
                                    
                                    if (DICOMSR == NO && [curDict valueForKey:@"album"] !=nil)
                                    {
                                        NSArray* albumArray = self.albums;
                                        
                                        DicomAlbum* album = NULL;
                                        for (album in albumArray)
                                        {
                                            if ([album.name isEqualToString:[curDict valueForKey:@"album"]])
                                                break;
                                        }
                                        
                                        if (album == nil)
                                        {
                                            //NSString *name = [curDict valueForKey:@"album"];
                                            //album = [NSEntityDescription insertNewObjectForEntityForName:@"Album" inManagedObjectContext: context];
                                            //[album setValue:name forKey:@"name"];
                                            
                                            for (album in albumArray)
                                            {
                                                if ([album.name isEqualToString:@"other"])
                                                    break;
                                            }
                                            
                                            if (album == nil)
                                            {
                                                album = [NSEntityDescription insertNewObjectForEntityForName:@"Album" inManagedObjectContext: self.managedObjectContext];
                                                [album setValue:@"other" forKey:@"name"];
                                                
                                                [NSNotificationCenter.defaultCenter postNotificationName:O2DatabaseInvalidateAlbumsCacheNotification object:self userInfo:nil];
                                            }
                                        }
                                        
                                        // add the file to the album
                                        if ( [[album valueForKey:@"smartAlbum"] boolValue] == NO)
                                        {
                                            NSMutableSet *studies = [album mutableSetValueForKey: @"studies"];
                                            [studies addObject: [image valueForKeyPath:@"series.study"]];
                                            [[image valueForKeyPath:@"series.study"] archiveAnnotationsAsDICOMSR];
                                        }
                                    }
                                }
                                else
                                {
                                    if (DICOMSR == NO)
                                    {
                                        [seriesTable setValue:today forKey:@"dateAdded"];
                                        study.dateAdded = today;
                                    }
                                }
                            }
                        }
                    }
                    else
                    {
                        // This file was not readable -> If it is located in the DATABASE folder, we have to delete it or to move it to the 'NOT READABLE' folder
                        if (dataDirPath && [newFile hasPrefix: dataDirPath])
                        {
                            NSLog(@"**** Unreadable file: %@", newFile);
                            
                            if ( DELETEFILELISTENER)
                            {
                                [[NSFileManager defaultManager] removeItemAtPath: newFile error:NULL];
                            }
                            else
                            {
                                if ([[NSFileManager defaultManager] moveItemAtPath: newFile toPath:[errorsDirPath stringByAppendingPathComponent: [newFile lastPathComponent]]  error:NULL] == NO)
                                    [[NSFileManager defaultManager] removeItemAtPath: newFile error:NULL];
                            }
                        }
                    }
                }
                @catch (NSException* e)
                {
                    N2LogExceptionWithStackTrace(e);
                }
                @finally {
                    if (preparedReportPath.length && ![preparedReportPath hasPrefix:@"http://"] && ![preparedReportPath hasPrefix:@"https://"]) {
                        [NSFileManager.defaultManager removeItemAtPath:preparedReportPath error:NULL];
                        HorosCleanReportExtractionParent(preparedReportPath);
                    }
                }
            }
        }
        
        [studiesArrayStudyInstanceUID release];
        [studiesArray release];
        
        for (DicomStudy* study in modifiedStudiesArray)
        {
            // Compute no of images in studies/series
            [study noFiles];
            // Reapply annotations from DICOMSR file
            [study reapplyAnnotationsFromDICOMSR];
        }
        
        thread.status = NSLocalizedString(@"Synchronizing database...", nil);
        thread.progress = -1;
        
        // This is the step the progress panel stops on when an import goes wrong,
        // and it used to be the one step that could not say anything: the error
        // was thrown away with save:NULL, and a save that raised left
        // protectionAgainstReentry set, so every later import in the session
        // skipped its save in silence - the images were in the context and never
        // written. The flag is cleared whatever happens, and the outcome is
        // named.
        if( protectionAgainstReentry == NO)
        {
            protectionAgainstReentry = YES;
            @try
            {
                NSError *saveError = nil;
                if( [self.managedObjectContext save: &saveError] == NO)
                {
                    // The files are already in the database folder and their rows
                    // are not written, so say what state that leaves: they are not
                    // lost, and rebuilding the index finds them.
                    NSLog( @"(addFilesDescribedInDictionaries): the database could not be saved: %@; "
                          @"%lu file(s) are in the database folder and not in the index, and "
                          @"rebuilding the database index will bring them in",
                          saveError.localizedDescription ?: @"no reason given",
                          (unsigned long) dicomFilesArray.count);
                    thread.status = [NSString stringWithFormat:
                        NSLocalizedString(@"The database could not be saved: %@", nil),
                        saveError.localizedDescription ?: NSLocalizedString(@"unknown error", nil)];
                }
            }
            @finally
            {
                protectionAgainstReentry = NO;
            }
        }
        else
            NSLog( @"(addFilesDescribedInDictionaries): another import is saving; these %lu file(s) "
                  @"are written with it", (unsigned long) dicomFilesArray.count);
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    if (rejectedReports && ![(N2ManagedObjectContext *)self.managedObjectContext defersSaves]) {
        dispatch_async(dispatch_get_main_queue(), ^{
            NSRunAlertPanel(NSLocalizedString(@"Report import", nil), @"%@",
                NSLocalizedString(@"OK", nil), nil, nil,
                [NSString stringWithFormat:NSLocalizedString(@"%lu report(s) could not be imported because their contents could not be read. Existing reports were preserved.", nil), (unsigned long)rejectedReports]);
        });
    }

    void (^publishImportChanges)(void) = ^{
    @try
    {
        thread.progress = -1;
        
        NSString* notificationString = nil;
        NSString* notificationStringNewStudy = nil;
        
        @try
        {
            NSAutoreleasePool* pool = [NSAutoreleasePool new];
            @try {
                if( returnArray)
                {
                    [NSNotificationCenter.defaultCenter postNotificationName:_O2AddToDBAnywayNotification object:self userInfo:[NSDictionary dictionaryWithObjectsAndKeys: addedImageObjects, OsirixAddToDBNotificationImagesArray, addedImagesPerCreatorUID, OsirixAddToDBNotificationImagesPerAETDictionary, nil]];
                    
                    [NSNotificationCenter.defaultCenter postNotificationName:_O2AddToDBAnywayCompleteNotification object:self userInfo:[NSDictionary dictionaryWithObjectsAndKeys:completeAddedImageObjects, OsirixAddToDBNotificationImagesArray, completeAddedImagesPerCreatorUID, OsirixAddToDBNotificationImagesPerAETDictionary, nil]];
                }
                
                if (postNotifications)
                {
                    if( newStudy)
                    {
                        [NSNotificationCenter.defaultCenter postNotificationOnMainThreadName:OsirixAddNewStudiesDBNotification object:self userInfo: [NSDictionary dictionaryWithObject:newStudies forKey: OsirixAddToDBNotificationImagesArray]];
                    }
                    
                    [NSNotificationCenter.defaultCenter postNotificationOnMainThreadName:OsirixAddToDBNotification object:self userInfo:[NSDictionary dictionaryWithObjectsAndKeys: addedImageObjects, OsirixAddToDBNotificationImagesArray, addedImagesPerCreatorUID, OsirixAddToDBNotificationImagesPerAETDictionary, nil]];
                    
                    [NSNotificationCenter.defaultCenter postNotificationOnMainThreadName:OsirixAddToDBCompleteNotification object:self userInfo:[NSDictionary dictionaryWithObjectsAndKeys: completeAddedImageObjects, OsirixAddToDBNotificationImagesArray, completeAddedImagesPerCreatorUID, OsirixAddToDBNotificationImagesPerAETDictionary, nil]];
                }
            } @catch (NSException* e) {
                N2LogExceptionWithStackTrace(e);
            } @finally {
                [pool release];
            }
            
            if (postNotifications)
            {
                if ([addedImageObjects count] > 0 && generatedByOsiriX == NO)
                {
                    notificationString = [NSString stringWithFormat:NSLocalizedString(@"Patient: %@\r%@ to the database", nil), [[addedImageObjects objectAtIndex:0] valueForKeyPath:@"series.study.name"], N2LocalizedSingularPluralCount(addedImageObjects.count, NSLocalizedString(@"image added", nil), NSLocalizedString(@"images added", nil))];
                    notificationStringNewStudy = [NSString stringWithFormat:NSLocalizedString(@"%@\r%@", nil), [[addedImageObjects objectAtIndex:0] valueForKeyPath:@"series.study.name"], [[addedImageObjects objectAtIndex:0] valueForKeyPath:@"series.study.studyName"]];
                }
            }
            if (self.isLocal && returnArray && [[NSUserDefaults standardUserDefaults] boolForKey: @"AUTOROUTINGACTIVATED"] && [self allowAutoroutingWithPostNotifications:postNotifications rereadExistingItems:rereadExistingItems])
            {
                // What set the routing going. Without it a send that repeats
                // cannot be told from one the rules asked for.
                NSLog( @" Autorouting trigger: %d image(s) %@", (int) addedImageObjects.count,
                      rereadExistingItems ? @"re-read from disk" : @"added to the database");
                [self alertToApplyRoutingRules:nil toImages:addedImageObjects];
            }
        }
        @catch( NSException *ne)
        {
            N2LogExceptionWithStackTrace(ne);
        }
        
        self.timeOfLastModification = [NSDate timeIntervalSinceReferenceDate];
        if (postNotifications)
        {
            if (notificationString)
                [self performSelectorOnMainThread:@selector(_notificationImagesAdded:) withObject:notificationString waitUntilDone:NO];
            
            if (newStudy && notificationStringNewStudy)
                [self performSelectorOnMainThread:@selector(_notificationNewStudy:) withObject:notificationStringNewStudy waitUntilDone:NO];
        }
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    };
    N2ManagedObjectContext *importContext = (N2ManagedObjectContext *)self.managedObjectContext;
    if ([importContext respondsToSelector:@selector(defersSaves)] && importContext.defersSaves)
        [importContext performAfterNextSuccessfulSave:publishImportChanges];
    else
        publishImportChanges();

    [pool release];
    
    return [addedImageObjects valueForKey:@"objectID"];
}

-(void)_notify:(NSArray*)args
{
    [NSNotificationCenter.defaultCenter postNotificationName:[args objectAtIndex:0] object:[args objectAtIndex:1] userInfo:[args objectAtIndex:2]];
}

-(void)copyFilesThread:(NSDictionary*)dict
{
    @autoreleasepool
    {
        NSOperationQueue* queue = [[[NSOperationQueue alloc] init] autorelease];
        [queue setMaxConcurrentOperationCount:1];
        
        BOOL onlyDICOM = [[dict objectForKey: @"onlyDICOM"] boolValue], copyFiles = [[dict objectForKey: @"copyFiles"] boolValue];
        __block BOOL studySelected = NO;
        NSUInteger failedCopies = 0;
        NSMutableArray *copyFailureDetails = [NSMutableArray array];
        // What was taken and what became a row. A medium pulled out mid-import
        // leaves the files it managed to copy in the database folder; whether any
        // of them were indexed was not written down anywhere, so the two counts
        // are kept and reported together at the end.
        __block NSUInteger copiedTotal = 0, indexedTotal = 0;
        NSArray *filesInput = [[dict objectForKey: @"filesInput"] sortedArrayUsingSelector:@selector(compare:)]; // sorting the array should make the data access faster on optical media
        
        for( int i = 0; i < [filesInput count];)
        {
            if ([[NSThread currentThread] isCancelled]) break;
            
            @autoreleasepool
            {
                @try
                {
                    NSMutableArray *copiedFiles = [NSMutableArray array];
                    NSTimeInterval lastGUIUpdate = 0;
                    NSTimeInterval twentySeconds = [NSDate timeIntervalSinceReferenceDate] + 5; // actually fiveSeconds
                    
                    for( ; i < [filesInput count] && twentySeconds > [NSDate timeIntervalSinceReferenceDate]; i++)
                    {
                        if ([[NSThread currentThread] isCancelled]) break;
                        
                        if( [NSDate timeIntervalSinceReferenceDate] - lastGUIUpdate > 1)
                        {
                            lastGUIUpdate = [NSDate timeIntervalSinceReferenceDate];
                            
                            [NSThread currentThread].status = N2LocalizedSingularPluralCount((long)filesInput.count-i, NSLocalizedString(@"file left", nil), NSLocalizedString(@"files left", nil));
                            [NSThread currentThread].progress = float(i)/filesInput.count;
                        }
                        
                        NSString *srcPath = [filesInput objectAtIndex: i], *dstPath = nil;
                        
                        if( copyFiles)
                        {
                            NSString *extension = [srcPath pathExtension];
                            
                            if( [extension isEqualToString:@""])
                                extension = @"dcm";
                            
                            if( [extension length] > 4 || [extension length] < 3)
                                extension = @"dcm";
                            
                            dstPath = [self uniquePathForNewDataFileWithExtension:extension];
                            
                            try
                            {
                                @try
                                {
                                    static NSString *oneCopyAtATime = @"oneCopyAtATime";
                                    @synchronized( oneCopyAtATime)
                                    {
                                        NSError *copyError = nil;
                                        BOOL copySucceeded = HorosCopyFileForPublication(NSFileManager.defaultManager, srcPath, dstPath,
                                            [[dict objectForKey:@"mountedVolume"] boolValue], &copyError);
                                        if (!copySucceeded) {
                                            failedCopies++;
                                            if (!copyFailureDetails.count)
                                                [copyFailureDetails addObject:copyError.localizedDescription ?: NSLocalizedString(@"The file could not be copied.", nil)];
                                        }
                                        if (copySucceeded)
                                        {
                                            if( [extension isEqualToString: @"dcm"] == NO)
                                            {
                                                if([DicomFile isDICOMFile:dstPath])
                                                {
                                                    NSString *newPathExtension = [[dstPath stringByDeletingPathExtension] stringByAppendingPathExtension: @"dcm"];
                                                    if ([[NSFileManager defaultManager] moveItemAtPath:dstPath toPath:newPathExtension error:NULL])
                                                        dstPath = newPathExtension;
                                                }
                                            }
                                            
                                            [copiedFiles addObject: dstPath];
                                        }
                                    }
                                }
                                @catch (NSException *exception)
                                {
                                    N2LogException( exception);
                                }
                            }
                            catch (...)
                            {
                                N2LogStackTrace( @"C++ exception");
                            }
                        }
                        else
                        {
                            if( [[NSFileManager defaultManager] fileExistsAtPath: srcPath])
                            {
                                if( [[dict objectForKey: @"mountedVolume"] boolValue])
                                {
                                    @try
                                    {
                                        if( [[[DicomFile alloc] init: srcPath] autorelease]) // Pre-load for CD/DVD in cache
                                        {
                                            [copiedFiles addObject: srcPath];
                                        }
                                        else NSLog( @"**** DicomFile *curFile = nil");
                                    }
                                    @catch (NSException * e) {
                                        N2LogExceptionWithStackTrace(e);
                                    }
                                }
                                else
                                {
                                    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"validateFilesBeforeImporting"] && [[dict objectForKey: @"mountedVolume"] boolValue] == NO) // mountedVolume : it's too slow to test the files now from a CD
                                    {
                                        // Pre-load for faster validating
                                        /*NSData *d =*/ [NSData dataWithContentsOfFile: srcPath];
                                    }
                                    [copiedFiles addObject: srcPath];
                                }
                            }
                        }
                        
                        if ([NSThread currentThread].isCancelled)
                            break;
                    }
                    
                    [queue addOperationWithBlock:^{
                        NSThread* thread = [NSThread currentThread];
                        thread.name = NSLocalizedString(@"Adding files...", nil);
                        [[ThreadsManager defaultManager] addThreadAndStart:thread];
                        
                        BOOL succeed = YES;
                        
#ifndef OSIRIX_LIGHT
                        thread.status = NSLocalizedString(@"Validating the files...", nil);
                        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"validateFilesBeforeImporting"] && [[dict objectForKey: @"mountedVolume"] boolValue] == NO) // mountedVolume : it's too slow to test the files now from a CD
                            succeed = [DicomDatabase testFiles: copiedFiles];
#endif
                        
                        NSArray *objects = nil;
                        
                        if( succeed)
                        {
                            thread.status = NSLocalizedString(@"Indexing the files...", nil);
                            
                            DicomDatabase *idatabase = self.isMainDatabase? self.independentDatabase : [self.mainDatabase independentDatabase];
                            
                            objects = [idatabase addFilesAtPaths:copiedFiles postNotifications:YES dicomOnly:onlyDICOM rereadExistingItems:YES generatedByOsiriX:NO importedFiles:YES returnArray:YES];
                            
                            @synchronized( copyFailureDetails)
                            {
                                copiedTotal += copiedFiles.count;
                                indexedTotal += objects.count;
                            }
                            
                            DicomDatabase* mdatabase = self.isMainDatabase? self : self.mainDatabase;
                            if( [[BrowserController currentBrowser] database] == mdatabase && [[dict objectForKey:@"addToAlbum"] boolValue])
                            {
                                NSManagedObjectID *iAlbum = [[BrowserController currentBrowser] currentAlbumID: idatabase];
                                if( iAlbum)
                                {
                                    DicomAlbum *album = [idatabase objectWithID: iAlbum];
                                    NSMutableSet *studies = [album mutableSetValueForKey: @"studies"];
                                    
                                    BOOL change = NO;
                                    for( DicomImage* mobject in [idatabase objectsWithIDs: objects])
                                    {
                                        DicomStudy* s = [mobject valueForKeyPath:@"series.study"];
                                        
                                        if( s && [studies containsObject: s] == NO)
                                        {
                                            change = YES;
                                            [studies addObject:s];
                                        }
                                    }
                                    
                                    if( change)
                                        [idatabase save];
                                }
                            }
                            
                        }
                        else if( copyFiles)
                        {
                            for( NSString * f in copiedFiles)
                                [[NSFileManager defaultManager]removeItemAtPath: f error: nil];
                        }
                        
                        if ([objects count])
                        {
                            @try
                            {
                                BrowserController* bc = [BrowserController currentBrowser];
                                
                                @try
                                {
                                    if( studySelected == NO)
                                    {
                                        studySelected = YES;
                                        if ([[dict objectForKey:@"selectStudy"] boolValue])
                                            [bc performSelectorOnMainThread:@selector(selectStudyWithObjectID:) withObject: [objects objectAtIndex:0] waitUntilDone:NO];
                                    }
                                }
                                @catch (NSException *e) {
                                    N2LogExceptionWithStackTrace(e);
                                }
                                
                            } @catch (NSException* e) {
                                N2LogExceptionWithStackTrace(e);
                            }
                        }
                        
                        [[ThreadsManager defaultManager] removeThread:thread]; // NSOperationQueue threads don't finish after ablock execution, they're recycled
                    }];
                    
                    if( [NSThread currentThread].isCancelled)
                        break;
                }
                @catch (NSException * e)
                {
                    N2LogExceptionWithStackTrace(e);
                }
            }
        }
        
        // The queued work indexes files that are already in the database folder; it
        // does not touch the medium. Cancelling it threw that away: pulling a disc
        // out cancels the scan thread, which cancels this one, and the operation
        // holding the files copied so far was cancelled before it could run.
        // Measured on a disc of 1200 instances pulled out one second in: 373 files
        // copied, 0 indexed, and 373 files left in the database folder that no row
        // pointed at. Cancelling stops the copying; what is already copied is
        // indexed, so a cut-short import is a smaller import and not a hidden one.
        if (queue.operationCount) {
            [NSThread currentThread].status = NSLocalizedString(@"Waiting for subtasks to complete...", nil);
            while (queue.operationCount)
                [NSThread sleepForTimeInterval:0.05];
        }
        
        // An import that took less than it was given says so, whether the shortfall
        // was in the copying or in the indexing. Both counts matter: files copied
        // into the database folder and never indexed are invisible to the browser
        // and to every clean-up that works from the database.
        if (failedCopies || copiedTotal != indexedTotal)
            NSLog( @"(copyFilesThread): %lu file(s) offered, %lu copied, %lu indexed, "
                  @"%lu could not be copied%@%@",
                  (unsigned long) filesInput.count, (unsigned long) copiedTotal,
                  (unsigned long) indexedTotal, (unsigned long) failedCopies,
                  copyFailureDetails.firstObject ? @": " : @"",
                  copyFailureDetails.firstObject ?: @"");
        
        if (failedCopies) {
            NSString *message = [NSString stringWithFormat:NSLocalizedString(@"%lu file(s) could not be copied and were not indexed. Source files were preserved.\n\n%@\n\nFor OneDrive or another cloud provider, make the files available offline and retry. Also check access permissions and free disk space.", nil), (unsigned long)failedCopies, copyFailureDetails.firstObject];
            dispatch_async(dispatch_get_main_queue(), ^{
                NSRunAlertPanel(NSLocalizedString(@"Import incomplete", nil), @"%@", NSLocalizedString(@"OK", nil), nil, nil, message);
            });
        }

        if( !failedCopies && [[dict objectForKey: @"ejectCDDVD"] boolValue] == YES && copyFiles == YES)
        {
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"EJECTCDDVD"])
                [[NSWorkspace sharedWorkspace] unmountAndEjectDeviceAtPath: [filesInput objectAtIndex:0]];
        }
    }
}


-(void)_notificationImagesAdded:(NSString*)message {
    [AppController.sharedAppController notificationTitle:NSLocalizedString(@"Incoming Files", nil) description:message name:@"newfiles"];
}

-(void)_notificationNewStudy:(NSString*)message {
    [AppController.sharedAppController notificationTitle:NSLocalizedString(@"New Study", nil) description:message name:@"newstudy"];
}

-(BOOL) hasFilesToImport
{
    NSDirectoryEnumerator *enumer = [NSFileManager.defaultManager enumeratorAtPath:self.incomingDirPath limitTo:-1];
    
    if( [enumer nextObject])
        return YES;
    
    return NO;
}

// Two archives can each hold a readme.txt, and two senders can each send a file
// called IM1. Moving the second one onto the first fails, and the fallback then
// deletes it - the opposite of what the preference that keeps unreadable files
// asks for. Give it a name of its own instead.
static NSString *availablePathInDirectory( NSString *directory, NSString *name)
{
    NSString *candidate = [directory stringByAppendingPathComponent: name];
    NSString *stem = [name stringByDeletingPathExtension];
    NSString *extension = [name pathExtension];
    for( int attempt = 1; [NSFileManager.defaultManager fileExistsAtPath: candidate] && attempt < 1000; attempt++)
    {
        NSString *unique = [NSString stringWithFormat: @"%@-%d", stem, attempt];
        if( extension.length)
            unique = [unique stringByAppendingPathExtension: extension];
        candidate = [directory stringByAppendingPathComponent: unique];
    }
    return candidate;
}

-(NSInteger)importFilesFromIncomingDir
{
    return [self importFilesFromIncomingDir: @NO];
}

-(NSInteger)importFilesFromIncomingDir: (NSNumber*) showGUI
{
    return [self importFilesFromIncomingDir: showGUI
                listenerCompressionSettings: [[NSUserDefaults standardUserDefaults] integerForKey: @"ListenerCompressionSettings"]];
}

// A scan reports for itself: whatever the last one refused stops being current
// the moment a new one starts.
-(NSInteger)importFilesFromIncomingDir: (NSNumber*) showGUI
           listenerCompressionSettings: (int) listenerCompressionSettings
{
    NSMutableArray* compressedPathArray = [NSMutableArray array];
    NSThread* thread = [NSThread currentThread];
    NSUInteger addedFilesCount = 0;
    BOOL activityFeedbackShown = NO;
    

    [NSFileManager.defaultManager confirmNoIndexDirectoryAtPath:self.decompressionDirPath];
    
    N2DirectoryEnumerator *enumer = [NSFileManager.defaultManager enumeratorAtPath:self.incomingDirPath limitTo:-1];
    
    [_importFilesFromIncomingDirLock lock];
    @try {
        if ([self isFileSystemFreeSizeLimitReached]) {
            [self cleanForFreeSpace];
            // Cleanup may have just freed space; do not reuse the pre-cleanup
            // capacity result cached for up to twenty seconds.
            _timeOfLastIsFileSystemFreeSizeLimitReachedVerification = 0;
            if ([self isFileSystemFreeSizeLimitReached]) {
                NSLog(@"Incoming import paused: database storage is full or unavailable; queued files are preserved");
                return 0;
            }
        }
        
        NSMutableArray *filesArray = [NSMutableArray array];
#ifdef OSIRIX_LIGHT
        listenerCompressionSettings = 0;
#endif
        
        [[NSFileManager defaultManager] confirmNoIndexDirectoryAtPath:self.dataDirPath];
        
        int maxNumberOfFiles = [[NSUserDefaults standardUserDefaults] integerForKey:@"maxNumberOfFilesForCheckIncoming"];
        if (maxNumberOfFiles < 100) maxNumberOfFiles = 100;
        if (maxNumberOfFiles > 30000) maxNumberOfFiles = 30000;
        
        NSString *pathname;
        // NSDirectoryEnumerator *enumer = [NSFileManager.defaultManager enumeratorAtPath:self.incomingDirPath];
        
        NSTimeInterval startTime = [NSDate timeIntervalSinceReferenceDate];
        NSTimeInterval start = startTime;
        
        while([filesArray count] < maxNumberOfFiles &&
              ([NSDate timeIntervalSinceReferenceDate]-startTime < ([[NSUserDefaults standardUserDefaults] integerForKey:@"LISTENERCHECKINTERVAL"]*3)) // don't let them wait more than (incomingdelay*3) seconds
              && (pathname = [enumer nextObject]))
        {
            if (thread.isCancelled)
                return 0;
            
            NSString *srcPath = [self.incomingDirPath stringByAppendingPathComponent:pathname];
            NSString *originalPath = srcPath;
            NSString *lastPathComponent = [srcPath lastPathComponent];
            
            // An archive is expanded into a directory of its own name inside this
            // folder, and its entries are then imported one by one - here, and
            // possibly over several scans. Each entry says what became of it; the
            // running tally is what lets the archive itself say so too.
            NSString *enclosingArchiveComponent = [HorosArchiveImportLedger archiveComponentOfRelativePath: pathname];
            NSString *enclosingArchive = enclosingArchiveComponent? [self.incomingDirPath stringByAppendingPathComponent: enclosingArchiveComponent] : nil;
            
            if ([[lastPathComponent uppercaseString] isEqualToString:@".DS_STORE"])
            {
                [[NSFileManager defaultManager] removeItemAtPath: srcPath error: nil];
                continue;
            }
            
            if ([[lastPathComponent uppercaseString] isEqualToString:@"__MACOSX"])
            {
                [[NSFileManager defaultManager] removeItemAtPath: srcPath error: nil];
                continue;
            }
            
            //            if ([[lastPathComponent uppercaseString] hasSuffix:@".APP"]) // We don't want to scan MacOS applications
            //			{
            //				[[NSFileManager defaultManager] removeItemAtPath: srcPath error: nil];
            //				continue;
            //			}
            
            if ([lastPathComponent length] > 0 && [lastPathComponent characterAtIndex: 0] == '.')
            {
                // delete old files starting with '.'
                struct stat st;
                if ([enumer stat:&st] == 0)
                {
                    NSDate* date = [NSDate dateWithTimeIntervalSince1970:st.st_mtime];
                    if( date && [date timeIntervalSinceNow] < -60*60*24)
                    {
                        NSLog(@"deleting old incoming file %@ (date modified: %@)", srcPath, date);
                        if (srcPath)
                            [[NSFileManager defaultManager] removeItemAtPath: srcPath error: nil];
                    }
                }
                
                continue; // don't handle this file, it's probably a busy file
            }
            
            NSString * originalSrcPath = srcPath;
            srcPath = [srcPath stringByResolvingSymlinksAndAliases];
            BOOL isAlias = ![srcPath isEqualToString:originalSrcPath];
            
            if( filesArray.count && !activityFeedbackShown && showGUI.boolValue) {
                [ThreadsManager.defaultManager addThreadAndStart:thread];
                [OsiriX setReceivingIcon];
                activityFeedbackShown = YES;
            }
            
            // Is it a real file? Is it writable (transfer done)?
            //					if ([[NSFileManager defaultManager] isWritableFileAtPath:srcPath] == YES)	<- Problems with CD : read-only files, but valid files
            {
                NSDictionary *fattrs = [enumer fileAttributes];	//[[NSFileManager defaultManager] fileAttributesAtPath:srcPath traverseLink: YES];
                
                if ([[fattrs objectForKey:NSFileBusy] boolValue])
                    continue;
                
                if ([[fattrs objectForKey:NSFileType] isEqualToString: NSFileTypeDirectory])
                {
                    // if alias assume nested folders should stay
                    if (!isAlias) { // Is this directory empty?? If yes, delete it!
                        BOOL dirContainsStuff = ([[[NSFileManager defaultManager] enumeratorAtPath:srcPath filesOnly:NO] nextObject] != nil);
                        
                        if (!dirContainsStuff)
                        {
                            // The expansion has run out: this is the last moment
                            // at which anything can still say what the archive
                            // held. Without it an archive containing no DICOM at
                            // all left no trace whatsoever.
                            if (enclosingArchive == nil && [HorosArchiveImportLedger isArchiveName: lastPathComponent])
                                NSLog( @"---- import: %@", [[HorosArchiveImportLedger shared] verdictForArchive: srcPath keptDirectoryName: [self.errorsDirPath lastPathComponent]]);
                            
                            [[NSFileManager defaultManager] removeItemAtPath:srcPath error:NULL];
                        }
                    }
                }
                else if ([[fattrs objectForKey:NSFileSize] longLongValue] == 0)
                {
                    // An empty file matched neither branch and stayed in the
                    // incoming folder for ever, re-enumerated on every scan. A
                    // transfer that has written nothing for five minutes has
                    // stopped writing.
                    NSDate *modified = [fattrs objectForKey: NSFileModificationDate];
                    if( modified == nil || [modified timeIntervalSinceNow] < -60*5)
                    {
                        NSLog( @"---- import: %@ is empty; removed from the incoming folder", lastPathComponent);
                        [[NSFileManager defaultManager] removeItemAtPath: srcPath error: NULL];
                    }
                }
                else if ([[fattrs objectForKey:NSFileSize] longLongValue] > 0)
                {
                    //=======================
                    //JF wado rest multi-part WADO-RS WADORS
                    //=======================
                    
                    //if file not available for reading, do nothing
                    NSFileHandle *file = [NSFileHandle fileHandleForReadingAtPath:srcPath];
                    if (file)
                    {
#define WADORSSIZE 0x500
                        BOOL dicomFileCreated=NO;
                        NSMutableData *data = [NSMutableData data];
                        [data appendData:[file readDataOfLength:WADORSSIZE]];
                        
                        if( data.length >= WADORSSIZE)
                        {
                            NSData *applicationDicom = [@"application/dicom;" dataUsingEncoding:NSASCIIStringEncoding];
                            NSRange applicationDicomRange  = [data rangeOfData:applicationDicom options:0 range:NSMakeRange(0, WADORSSIZE)];
                            if (applicationDicomRange.location != NSNotFound)
                            {
                                //read the rest of file
                                [data appendData:[file readDataToEndOfFile]];
                                NSUInteger dataLength = [data length];
                                
                                /*
                                 find the mime multipart boundary.
                                 ================================
                                 
                                 [preamble CRLF]
                                 
                                 --boundary transport-padding CRLF
                                 
                                 CRLF --boundary transport-padding CRLF
                                 1. body-part
                                 
                                 CRLF --boundary transport-padding CRLF
                                 2. body-part
                                 
                                 CRLF --boundary transport-padding CRLF
                                 3. body-part
                                 
                                 CRLF --boundary-- transport-padding
                                 [CRLF epilogue]
                                 
                                 ---
                                 
                                 We assume that neither the eventual preamble nor the boundary contain "--"
                                 */
                                
                                unsigned short dash = 0x2D2D;
                                NSData *dashData =[NSData dataWithBytes:&dash length:2];
                                NSRange boundaryRange = [data rangeOfData:dashData options:0 range:NSMakeRange(0, dataLength)];
                                NSUInteger lastBoundaryLocation = boundaryRange.location;
                                if ((lastBoundaryLocation != NSNotFound) && (lastBoundaryLocation < dataLength - 75))
                                {
                                    unsigned short CRLF = 0x0A0D;
                                    NSData *CRLFData =[NSData dataWithBytes:&CRLF length:2];
                                    NSRange firstBoundaryCRLFRange = [data rangeOfData:CRLFData options:0 range:NSMakeRange(boundaryRange.location, 75)];
                                    if (firstBoundaryCRLFRange.location != NSNotFound)
                                    {
                                        NSData *boundaryData = [data subdataWithRange:NSMakeRange(lastBoundaryLocation, firstBoundaryCRLFRange.location - lastBoundaryLocation)];
                                        NSUInteger boundaryLength=[boundaryData length];
                                        NSData *DICMData = [@"DICM" dataUsingEncoding:NSASCIIStringEncoding];
                                        NSRange DICMRange;
                                        NSRange dataRange;
                                        NSUInteger datasetOffset;
                                        while (lastBoundaryLocation < dataLength)
                                        {
                                            dataRange.location = lastBoundaryLocation;
                                            dataRange.length   = dataLength-lastBoundaryLocation;
                                            applicationDicomRange = [data rangeOfData:applicationDicom options:0 range:dataRange];
                                            if (applicationDicomRange.location==NSNotFound) lastBoundaryLocation = dataLength;
                                            else
                                            {
                                                DICMRange = [data rangeOfData:DICMData options:0 range:dataRange];
                                                if (DICMRange.location==NSNotFound) lastBoundaryLocation = dataLength;
                                                else
                                                {
                                                    
                                                    boundaryRange = [data rangeOfData:boundaryData options:0 range:NSMakeRange(lastBoundaryLocation+boundaryLength, dataLength - lastBoundaryLocation - boundaryLength)];
                                                    if (boundaryRange.location != NSNotFound) lastBoundaryLocation = dataLength;
                                                    if ((DICMRange.location > applicationDicomRange.location) && (boundaryRange.location > DICMRange.location))
                                                    {
                                                        //write dicom file
                                                        datasetOffset=DICMRange.location - 128;
                                                        dicomFileCreated=[[data subdataWithRange:NSMakeRange(datasetOffset,boundaryRange.location - 2 - datasetOffset)]writeToFile:[self.incomingDirPath stringByAppendingPathComponent:[[NSUUID UUID]UUIDString]] atomically:NO];
                                                    }
                                                    lastBoundaryLocation=boundaryRange.location;
                                                }
                                            }
                                        }
                                    }
                                }
                                
                            }
                        }
                        [file closeFile];
                        if (dicomFileCreated)
                        {
                            // The parts were written out as separate files and
                            // this one no longer exists: continuing would test a
                            // missing path and report it as unreadable.
                            [[NSFileManager defaultManager] removeItemAtPath:srcPath error:NULL];
                            if (enclosingArchive)
                                [[HorosArchiveImportLedger shared] recordIndexedEntryInArchive: enclosingArchive];
                            continue;
                        }
                        
                    }
                    //===========================
                    //JF end wado rest multi-part
                    //===========================
                    
                    
                    
                    if ([[srcPath pathExtension] isEqualToString: @"zip"] ||
                        [[srcPath pathExtension] isEqualToString: @"osirixzip"])
                    {
                        NSString *compressedPath = [self.decompressionDirPath stringByAppendingPathComponent: lastPathComponent];
                        NSError *moveError = nil;
                        if ([[NSFileManager defaultManager] moveItemAtPath:srcPath toPath:compressedPath error:&moveError])
                        {
                            [compressedPathArray addObject: compressedPath];
                            if (enclosingArchive)
                                [[HorosArchiveImportLedger shared] recordNestedArchiveInArchive: enclosingArchive];
                        }
                        else
                        {
                            // It stays here and is retried on every scan - which
                            // is what makes it recoverable once the cause is
                            // fixed - so say it once per file rather than once
                            // per scan, and once rather than not at all.
                            static NSMutableSet *reportedUnmovableArchives = nil;
                            static dispatch_once_t once;
                            dispatch_once( &once, ^{ reportedUnmovableArchives = [[NSMutableSet alloc] init]; });
                            @synchronized( reportedUnmovableArchives)
                            {
                                if( [reportedUnmovableArchives containsObject: srcPath] == NO)
                                {
                                    [reportedUnmovableArchives addObject: srcPath];
                                    NSLog( @"---- import: %@ could not be moved to the decompression folder (%@); it stays here and is tried again on the next scan", lastPathComponent, moveError.localizedDescription);
                                }
                            }
                        }
                    }
                    else
                    {
                        BOOL isDicomFile, isJPEGCompressed, isImage;
                        NSString *dstPath = [self.dataDirPath stringByAppendingPathComponent: lastPathComponent];
                        
                        isDicomFile = [DicomFile isDICOMFile:srcPath compressed: &isJPEGCompressed image: &isImage];
                        
                        // Detection, enhanced reading and the thumbnail stack are
                        // decided before a file leaves INCOMING. A zero-size or
                        // unloadable image still crashes series icons; keep it
                        // out of the indexed store and say why. The manufacturer
                        // is not consulted - the same gate applies to any vendor.
                        if (isDicomFile)
                        {
                            HorosEnhancedImportAssessment *stack = [HorosEnhancedImportTriage assessPath: srcPath];
                            HorosIVUSImportAssessment *ivus = [HorosIVUSImportTriage assessPath: srcPath];
                            BOOL mayMerge = stack.mayMergeIntoIncoming;
                            NSString *why = stack.recordedError.length ? stack.recordedError
                                : @"the pixel/thumbnail stack cannot load this object";
                            // IVUS/US objects decide for themselves: Implicit VR
                            // Volcano-shaped cines that the Enhanced parser does
                            // not read still have a size and a diagnosis here.
                            // A file this gate does not apply to keeps the
                            // Enhanced answer. The manufacturer is not consulted.
                            if (ivus.appliesToFile)
                            {
                                mayMerge = ivus.mayMergeIntoIncoming;
                                why = ivus.recordedError.length ? ivus.recordedError
                                    : @"the thumbnail stack cannot load this IVUS/US object";
                            }
                            if (mayMerge == NO)
                            {
                                [self addImportRefusalSummary: [NSString stringWithFormat: @"%@: %@", lastPathComponent, why]];
                                NSLog( @"---- import: %@ not merged into the incoming index (%@)", lastPathComponent, why);
                                NSString *kept = availablePathInDirectory( self.errorsDirPath, lastPathComponent);
                                NSError *moveError = nil;
                                if ([[NSFileManager defaultManager] moveItemAtPath: srcPath toPath: kept error: &moveError] == NO)
                                    NSLog( @"---- import: %@ could not be kept aside (%@); it stays in incoming",
                                          lastPathComponent, moveError.localizedDescription);
                                continue;
                            }
                        }
                        
                        // A database that indexes anything readable takes the
                        // formats the raster reader handles as well: -getImageFile
                        // reads png, jpg, jp2, pdf, pct and gif beside tiff, and
                        // refusing them at the door meant a valid PNG or PDF never
                        // reached it. When only DICOM is indexed they are left
                        // alone, rather than moved in and thrown away.
                        BOOL indexesAnything = ![[NSUserDefaults standardUserDefaults] boolForKey: @"onlyDICOM"];
                        
                        // NIfTI belongs in this list for the same reason NRRD
                        // does: DCMPix reads it. Leaving it out meant a valid .nii
                        // dropped into the incoming folder was called "not a DICOM
                        // file this database can index" and, with DELETEFILELISTENER,
                        // deleted - a file the viewer can open, destroyed on arrival.
                        if (isDicomFile == YES ||
                            (([DicomFile isFVTiffFile:srcPath] ||
                              [DicomFile isTiffFile:srcPath] ||
                              [DicomFile isNRRDFile:srcPath] ||
                              [DicomFile isNIfTIFile:srcPath] ||
                              (indexesAnything && [DicomFile isImageFile:srcPath]))
                             && [[NSFileManager defaultManager] fileExistsAtPath:dstPath] == NO))
                        {
                            if (isDicomFile && isImage)
                            {
                                if ((isJPEGCompressed == YES && listenerCompressionSettings == 1) ||    // Decompress
                                    (isJPEGCompressed == NO  && listenerCompressionSettings == 2        // Compress
#ifndef OSIRIX_LIGHT
                     && [DicomDatabase fileNeedsDecompression: srcPath]
#else
#endif
                                                                                                      ))
                                {
                                    NSString *compressedPath = [self.decompressionDirPath stringByAppendingPathComponent: lastPathComponent];
                                    [[NSFileManager defaultManager] moveItemAtPath:srcPath toPath:compressedPath error:NULL];
                                    [compressedPathArray addObject: compressedPath];
                                    if (enclosingArchive)
                                        [[HorosArchiveImportLedger shared] recordQueuedEntryInArchive: enclosingArchive];
                                    continue;
                                }
                                
                                dstPath = [self uniquePathForNewDataFileWithExtension:@"dcm"];
                            }
                            else
                            {
                                dstPath = [self uniquePathForNewDataFileWithExtension:[[srcPath pathExtension] lowercaseString]];
                            }
                            
                            BOOL result;
                            
                            if (isAlias)
                            {
                                result = [[NSFileManager defaultManager] copyItemAtPath:srcPath toPath: dstPath error:NULL];
                                [[NSFileManager defaultManager] removeItemAtPath:originalPath error:NULL];
                            }
                            else
                            {
                                result = [[NSFileManager defaultManager] moveItemAtPath:srcPath
                                                                                 toPath:dstPath
                                                                                  error:NULL];
                            }
                            
                            if (result == YES)
                            {
                                // A file that is not DICOM has no identity but
                                // its name, and the copy above replaced it with
                                // a number. -[DicomFile getImageFile] makes the
                                // study and the series out of that name, so
                                // every raster file came out with the same
                                // empty stem and they all fell into one series.
                                if (isDicomFile == NO)
                                    [HorosImportedFileNames rememberName: lastPathComponent forPath: dstPath];
                                
                                [filesArray addObject:dstPath];
                                if (enclosingArchive)
                                    [[HorosArchiveImportLedger shared] recordIndexedEntryInArchive: enclosingArchive];
                            }
                        }
                        else // DELETE or MOVE THIS UNKNOWN FILE ?
                        {
                            // Every file that arrives ends either as a study or
                            // as a refusal that says so. This branch used to be
                            // silent, so a file that was accepted by whatever
                            // put it here simply disappeared.
                            // An archive the decompression helper could not expand
                            // is handed back under this name, so that it is
                            // reported here instead of being left in a folder
                            // nothing reads. The helper's own diagnosis goes to
                            // its stderr, which the application does not capture,
                            // so say here what the file actually was.
                            if ([[lastPathComponent pathExtension] isEqualToString: @"horos-unexpanded"])
                                NSLog( @"---- import: %@ could not be expanded as an archive", [lastPathComponent stringByDeletingPathExtension]);
                            
                            // The scan refuses a file before it ever reaches
                            // -addFilesAtPaths:, so it has to report for itself, or
                            // the window says nothing about the file that was
                            // dropped - which is what "rejected with no visible
                            // error" means to the person who sent it.
                            [self addImportRefusalSummary: [NSString stringWithFormat: NSLocalizedString( @"%@ is not a DICOM file this database can index", nil), lastPathComponent]];
                            
                            if ([[NSUserDefaults standardUserDefaults] boolForKey:@"DELETEFILELISTENER"])
                            {
                                NSLog( @"---- import: %@ is not a DICOM file this database can index; deleted (DELETEFILELISTENER)", lastPathComponent);
                                [[NSFileManager defaultManager] removeItemAtPath:srcPath error:NULL];
                                if (enclosingArchive)
                                    [[HorosArchiveImportLedger shared] recordDeletedEntryInArchive: enclosingArchive];
                            }
                            else {
                                NSString *kept = availablePathInDirectory( self.errorsDirPath, lastPathComponent);
                                NSError *moveError = nil;
                                if (![NSFileManager.defaultManager moveItemAtPath:srcPath toPath:kept error:&moveError])
                                {
                                    NSLog( @"---- import: %@ is not a DICOM file this database can index, and could not be kept (%@); deleted", lastPathComponent, moveError.localizedDescription);
                                    [NSFileManager.defaultManager removeItemAtPath:srcPath error:NULL];
                                    if (enclosingArchive)
                                        [[HorosArchiveImportLedger shared] recordDeletedEntryInArchive: enclosingArchive];
                                }
                                else
                                {
                                    NSLog( @"---- import: %@ is not a DICOM file this database can index; kept in %@", lastPathComponent, [self.errorsDirPath lastPathComponent]);
                                    if (enclosingArchive)
                                        [[HorosArchiveImportLedger shared] recordKeptEntryInArchive: enclosingArchive];
                                }
                            }
                        }
                    }
                }
            }
            
            if( [NSDate timeIntervalSinceReferenceDate] - start > 0.5)
            {
                thread.status =  N2LocalizedSingularPluralCount( filesArray.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
                start = [NSDate timeIntervalSinceReferenceDate];
            }
        }
        
        if( filesArray.count)
            thread.status = N2LocalizedSingularPluralCount( filesArray.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil));
        
        if ([filesArray count] > 0)
        {
            //				if ( [[NSUserDefaults standardUserDefaults] boolForKey:@"ANONYMIZELISTENER"] == YES)
            //					[self listenerAnonymizeFiles: filesArray];
            
            if ([[PluginManager preProcessPlugins] count])
            {
                thread.status = [NSString stringWithFormat:NSLocalizedString(@"Preprocessing %d files with %d plugins...", nil), filesArray.count, [[PluginManager preProcessPlugins] count]];
                for (id filter in [PluginManager preProcessPlugins])
                {
                    @try
                    {
                        [PluginManager startProtectForCrashWithFilter: filter];
                        [filter processFiles: filesArray];
                        [PluginManager endProtectForCrash];
                    }
                    @catch (NSException* e)
                    {
                        N2LogExceptionWithStackTrace(e);
                    }
                }
            }
            
            thread.status = [NSString stringWithFormat:NSLocalizedString(@"Processing %@...", nil), N2LocalizedSingularPluralCount(filesArray.count, NSLocalizedString(@"file", nil),NSLocalizedString(@"files", nil))];
            
            NSArray* addedFiles = nil;
            if( thread.isCancelled == NO)
                addedFiles = [self addFilesAtPaths:filesArray]; // these are IDs!
            
            addedFilesCount = addedFiles.count;
            
            // What this pass took and what it indexed. The incoming folder is the
            // local half of the same question the medium scan answers for a
            // mounted volume, and comparing the two needs the same three numbers
            // from both.
            if( filesArray.count)
                NSLog( @"(importFilesFromIncomingDir): %lu file(s) taken from the incoming folder, "
                      @"%lu indexed, in %.1f s (%.1f ms per file)",
                      (unsigned long) filesArray.count, (unsigned long) addedFilesCount,
                      [NSDate timeIntervalSinceReferenceDate] - startTime,
                      1000.0 * ([NSDate timeIntervalSinceReferenceDate] - startTime) / filesArray.count);
            
            if (!addedFiles) // Add failed.... Keep these files: move them back to the INCOMING folder and try again later....
            {
                NSString *dstPath;
                int x = 0;
                
                NSLog( @"------------ Move the files back to the incoming folder...");
                
                for( NSString *file in filesArray)
                {
                    do
                    {
                        dstPath = [self.incomingDirPath stringByAppendingPathComponent:[NSString stringWithFormat:@"%d", x]];
                        x++;
                    }
                    while( [[NSFileManager defaultManager] fileExistsAtPath:dstPath] == YES);
                    
                    [[NSFileManager defaultManager] moveItemAtPath: file toPath: dstPath error: NULL];
                }
            }
            
        }
        
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [_importFilesFromIncomingDirLock unlock];
        if (activityFeedbackShown)
            [OsiriX unsetReceivingIcon];
    }
    
    if (enumer.nextObject) // there is more data
        [self performSelector:@selector(initiateImportFilesFromIncomingDirUnlessAlreadyImporting) withObject:nil afterDelay:0];
    
#ifndef OSIRIX_LIGHT
    if ([compressedPathArray count] > 0) // there are files to compress/decompress in the decompression dir
    {
        if (listenerCompressionSettings == 1 || listenerCompressionSettings == 0) // decompress, listenerCompressionSettings == 0 for zip support!
        {
            //            [self performSelectorInBackground:@selector(_threadDecompressToIncoming:) withObject:compressedPathArray];
            
            @synchronized (_decompressQueue) {
                [_decompressQueue addObjectsFromArray:compressedPathArray];
            }
            
            [self kickstartCompressDecompress];
            
            //            [self initiateDecompressFilesAtPaths: compressedPathArray intoDirAtPath: self.incomingDirPath];
        }
        else if (listenerCompressionSettings == 2) // compress
        {
            //            [self performSelectorInBackground:@selector(_threadCompressToIncoming:) withObject:compressedPathArray];
            
            @synchronized (_decompressQueue) {
                [_compressQueue addObjectsFromArray:compressedPathArray];
            }
            
            [self kickstartCompressDecompress];
            
            //            [self initiateCompressFilesAtPaths: compressedPathArray intoDirAtPath: self.incomingDirPath];
        }
    }
#endif
    
    return addedFilesCount;
}

-(BOOL)waitForCompressThread
{
    DicomDatabase* mdb = self.isMainDatabase? self : self.mainDatabase;
    
    if( [mdb.compressDecompressThread isFinished] || [mdb.compressDecompressThread isCancelled])
        return NO;
    
    if( [mdb.compressDecompressThread isExecuting])
    {
        while( [mdb.compressDecompressThread isExecuting])
            [NSThread sleepForTimeInterval:0.1];
        
        return YES;
    }
    
    return NO;
}

- (void)kickstartCompressDecompress
{
    @synchronized (_compressQueue) {
        @synchronized (_decompressQueue) {
            DicomDatabase* mdb = self.isMainDatabase? self : self.mainDatabase;
            if (!mdb.compressDecompressThread) {
                mdb.compressDecompressThread = [[[NSThread alloc] initWithTarget:self selector:@selector(_threadCompressDecompress) object:nil] autorelease];
                [mdb.compressDecompressThread start];
            } else {
                mdb.compressDecompressThread.status = [NSString stringWithFormat:NSLocalizedString(@"%d additional files queued", nil), _compressQueue.count+_decompressQueue.count];
            }
        }
    }
}

- (void)_threadCompressDecompress
{
    while (true) {
        for (int i = 0; i < 2; ++i) // i 0 -> compression; i 1 -> decompression
            @autoreleasepool {
                NSArray* todo = nil;
                
                if (i == 0) // compression
                {
                    @synchronized (_compressQueue) {
                        todo = [[_compressQueue copy] autorelease];
                        [_compressQueue removeAllObjects];
                    }
                }
                else // decompression
                {
                    @synchronized (_decompressQueue) {
                        todo = [[_decompressQueue copy] autorelease];
                        [_decompressQueue removeAllObjects];
                    }
                }
                if (todo.count)
                {
                    DicomDatabase *worker = self.isMainDatabase ? self.independentDatabase : self;
                    NSError *conversionError = nil;
                    if (![worker processFilesAtPaths:todo intoDirAtPath:self.incomingDirPath
                                               mode:i == 0 ? Compress : Decompress error:&conversionError])
                    {
                        NSString *verdict = [HorosConversionImportFallback recoverFiles:todo
                            allocateDestination:^NSString * {
                                @try { return [worker uniquePathForNewDataFileWithExtension:@"dcm"]; }
                                @catch (NSException *exception) { return nil; }
                            }
                            importFile:^NSInteger(NSString *path) {
                                @try {
                                    return [worker addFilesAtPaths:@[path] postNotifications:YES dicomOnly:YES
                                              rereadExistingItems:NO generatedByOsiriX:NO].count;
                                } @catch (NSException *exception) {
                                    N2LogExceptionWithStackTrace(exception);
                                    return 0;
                                }
                            }];
                        if (verdict.length)
                        {
                            NSLog(@"---- conversion fallback: %@", verdict);
                            [NSThread currentThread].status = verdict;
                        }
                    }
                }
            }
        
        @synchronized (_compressQueue) {
            @synchronized (_decompressQueue) {
                if (!_compressQueue.count && !_decompressQueue.count) {
                    DicomDatabase* mdb = self.isMainDatabase? self : self.mainDatabase;
                    mdb.compressDecompressThread = nil;
                    break;
                }
            }
        }
    }
}

//-(void)_threadDecompressToIncoming:(NSArray*)compressedPathArray {
//    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
//    @try {
//        NSThread* thread = [NSThread currentThread];
//        thread.name = NSLocalizedString(@"DICOM Decompression...", nil);
//        thread.status = [NSString stringWithFormat:NSLocalizedString(@"Decompressing %d %@", nil), compressedPathArray.count, compressedPathArray.count == 1? NSLocalizedString(@"file", nil) : NSLocalizedString(@"files", nil)];
//        [ThreadsManager.defaultManager addThreadAndStart:thread];
//        [self decompressFilesAtPaths:compressedPathArray intoDirAtPath:self.incomingDirPath];
//    } @catch (NSException* e) {
//        N2LogExceptionWithStackTrace(e);
//    } @finally {
//        [pool release];
//    }
//}

//-(void)_threadCompressToIncoming:(NSArray*)compressedPathArray {
//    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
//    @try {
//        NSThread* thread = [NSThread currentThread];
//        thread.name = NSLocalizedString(@"DICOM Compression...", nil);
//        thread.status = [NSString stringWithFormat:NSLocalizedString(@"Compressing %d %@", nil), compressedPathArray.count, compressedPathArray.count == 1? NSLocalizedString(@"file", nil) : NSLocalizedString(@"files", nil)];
//        [ThreadsManager.defaultManager addThreadAndStart:thread];
//        [self compressFilesAtPaths:compressedPathArray intoDirAtPath:self.incomingDirPath];
//    } @catch (NSException* e) {
//        N2LogExceptionWithStackTrace(e);
//    } @finally {
//        [pool release];
//    }
//}

-(void)importFilesFromIncomingDirThread
{
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
    [_importFilesFromIncomingDirLock lock];
    @try
    {
        NSInteger importCount = 0;
        if( [self hasFilesToImport])
        {
            NSThread* thread = [NSThread currentThread];
            thread.name = NSLocalizedString(@"Adding incoming files...", nil);
            [thread enterOperation];
            importCount = [self.independentDatabase importFilesFromIncomingDir: @YES];
            [thread exitOperation];
            thread.status = NSLocalizedString(@"Finishing...", nil);
            thread.progress = -1;
        }
        DicomDatabase* theDatabase = self.isMainDatabase? self : self.mainDatabase;
        if (theDatabase == DicomDatabase.activeLocalDatabase)
        {
            NSString *newBadge = (importCount? [[NSNumber numberWithInteger:importCount] stringValue] : nil);
            
            dispatch_async(dispatch_get_main_queue(), ^(void)
            {
                if( [newBadge isEqualToString: [[NSApp dockTile] badgeLabel]] == NO)
                    [AppController.sharedAppController setBadgeLabel:newBadge];
                   
            });
        }
    }
    @catch (NSException* e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally
    {
        [pool release];
        [_importFilesFromIncomingDirLock unlock];
    }
}

// The window reads this from the main database, whichever context did the import.
- (NSString*)lastImportRefusalSummary {
    if (self.isMainDatabase == NO)
        return [(DicomDatabase *)self.mainDatabase lastImportRefusalSummary];
    @synchronized (self) { return [[_lastImportRefusalSummary copy] autorelease]; }
}

- (void)addImportRefusalSummary:(NSString*) summary {
    if (summary.length == 0)
        return;
    if (self.isMainDatabase == NO)
    {
        [(DicomDatabase *)self.mainDatabase addImportRefusalSummary: summary];
        return;
    }
    @synchronized (self)
    {
        NSString *joined = _lastImportRefusalSummary.length ? [_lastImportRefusalSummary stringByAppendingFormat: @"; %@", summary] : summary;
        [_lastImportRefusalSummary release];
        _lastImportRefusalSummary = [joined copy];
    }
}

- (void)setLastImportRefusalSummary:(NSString*) summary {
    if (self.isMainDatabase == NO)
    {
        [(DicomDatabase *)self.mainDatabase setLastImportRefusalSummary: summary];
        return;
    }
    @synchronized (self)
    {
        if (_lastImportRefusalSummary == summary || [_lastImportRefusalSummary isEqualToString: summary])
            return;
        [_lastImportRefusalSummary release];
        _lastImportRefusalSummary = [summary copy];
    }
}

- (BOOL)incomingImportWaitingForSpace {
    return self.isMainDatabase ? _incomingImportSpaceWarningShown : [(DicomDatabase *)self.mainDatabase incomingImportWaitingForSpace];
}

// Shared by the incoming scheduler and cleanup workers. Own episode state on the
// main database/main thread so independent contexts cannot duplicate warnings.
- (void)updateStorageAvailabilityWarning {
    if (![NSThread isMainThread]) {
        [self performSelectorOnMainThread:@selector(updateStorageAvailabilityWarning) withObject:nil waitUntilDone:NO];
        return;
    }
    if (!self.isMainDatabase) {
        [(DicomDatabase *)self.mainDatabase updateStorageAvailabilityWarning];
        return;
    }
    BOOL storageUnavailable = [self isFileSystemFreeSizeLimitReached];
    BOOL stateChanged = _incomingImportSpaceWarningShown != storageUnavailable;
    _incomingImportSpaceWarningShown = storageUnavailable;
    if (stateChanged && [BrowserController currentBrowser].database == self)
        [[BrowserController currentBrowser] performSelector:@selector(outlineViewRefresh) withObject:nil afterDelay:0];
    if (storageUnavailable && stateChanged) {
        NSLog(@"Incoming import paused: database storage is full or unavailable; queued files are preserved");
        if (![NSUserDefaults.standardUserDefaults boolForKey:@"hideListenerError"]) {
            @try {
                [[AppController sharedAppController] notificationTitle:NSLocalizedString(@"Import Paused", nil)
                    description:NSLocalizedString(@"The database volume is full or unavailable. Incoming files are preserved. Free space or reconnect the volume; Horos will retry automatically.", nil)
                    name:@"newfiles"];
            } @catch (NSException *e) {
                // Notification availability must not prevent import retries.
                N2LogExceptionWithStackTrace(e);
            }
        }
    }
}

-(void)initiateImportFilesFromIncomingDirUnlessAlreadyImporting {
    //if ([[AppController sharedAppController] isSessionInactive])
    //	return;
    
    if( [NSThread isMainThread] == NO)
    {
        [self performSelectorOnMainThread: @selector(initiateImportFilesFromIncomingDirUnlessAlreadyImporting) withObject: nil waitUntilDone: NO];
        return;
    }
    
    if( [ViewerController areLoadingViewers]) //Don't try to do everything at the same time... we are not in a hurry for checking the incoming dir, preserve the user experience !
        return;
    
    if ([_importFilesFromIncomingDirLock tryLock])
    {
        @try {
            [self updateStorageAvailabilityWarning];
            [self performSelectorInBackground:@selector(importFilesFromIncomingDirThread) withObject:nil];
        } @catch (NSException* e) {
            N2LogExceptionWithStackTrace(e);
        } @finally {
            [_importFilesFromIncomingDirLock unlock];
        }
    }
}

+(void)importFilesFromIncomingDirTimerCallback:(NSTimer*)timer {
    for (DicomDatabase* dbi in [self allDatabases])
        if (dbi.isLocal)
            [dbi initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
}

+(void)syncImportFilesFromIncomingDirTimerWithUserDefaults {
    static NSTimer* importFilesFromIncomingDirTimer = nil;
    
    NSInteger newInterval = [[NSUserDefaults standardUserDefaults] integerForKey:@"LISTENERCHECKINTERVAL"];
    if (importFilesFromIncomingDirTimer.timeInterval == newInterval)
        return;
    
    [importFilesFromIncomingDirTimer invalidate];
    [importFilesFromIncomingDirTimer release];
    importFilesFromIncomingDirTimer = nil;
    if (newInterval) {
        importFilesFromIncomingDirTimer = [[NSTimer timerWithTimeInterval:newInterval target:self selector:@selector(importFilesFromIncomingDirTimerCallback:) userInfo:nil repeats:YES] retain];
        [[NSRunLoop mainRunLoop] addTimer:importFilesFromIncomingDirTimer forMode:NSModalPanelRunLoopMode];
        [[NSRunLoop mainRunLoop] addTimer:importFilesFromIncomingDirTimer forMode:NSDefaultRunLoopMode];
    }
}

#pragma mark Other

-(BOOL)rebuildAllowed
{
    return YES;
}

-(BOOL)upgradeSqlFileFromModelVersion:(NSString*)databaseModelVersion
{
    NSLog( @"------ upgradeSqlFileFromModelVersion: %@", databaseModelVersion);
    
    NSThread* thread = [NSThread currentThread];
    NSString* oldThreadName = thread.name;
    
    NSManagedObjectModel* oldModel = nil;
    NSPersistentStoreCoordinator* oldPersistentStoreCoordinator = nil;
    NSManagedObjectContext* oldContext = nil;
    NSManagedObjectModel* newModel = nil;
    NSPersistentStoreCoordinator* newPersistentStoreCoordinator = nil;
    NSManagedObjectContext* newContext = nil;
    
    [thread enterOperation];
    @try {
        thread.name = NSLocalizedString(@"Upgrading database...", nil);
        
        //   [NSThread sleepForTimeInterval:2];
        
        NSString* oldModelFilename = [NSString stringWithFormat:@"OsiriXDB_Previous_DataModel%@.mom", databaseModelVersion];
        if ([databaseModelVersion isEqualToString:CurrentDatabaseVersion]) oldModelFilename = [NSString stringWithFormat:@"OsiriXDB_DataModel.mom"]; // same version
        
        if (![NSFileManager.defaultManager fileExistsAtPath:[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:oldModelFilename]])
        {
            int r = NSAlertDefaultReturn;
            
            if( [[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"])
            {
                r = NSAlertDefaultReturn;
            }
            else
                r = NSRunAlertPanel(NSLocalizedString(@"Horos Database", nil), NSLocalizedString(@"Horos cannot understand the model of current saved database... The database index will be deleted and reconstructed (no images are lost).", nil), NSLocalizedString(@"OK", nil), NSLocalizedString(@"Quit", nil), nil);
            
            if (r == NSAlertAlternateReturn)
            {
                [NSFileManager.defaultManager removeItemAtPath:self.loadingFilePath error:nil]; // to avoid the crash message during next startup
                [NSApp terminate:self];
            }
            
            [[NSFileManager defaultManager] removeItemAtPath:self.sqlFilePath error:nil];
            
            [self rebuild:YES];
            
            return NO;
        }
        
        NSManagedObjectModel* oldModel = [[NSManagedObjectModel alloc] initWithContentsOfURL: [NSURL fileURLWithPath: [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:oldModelFilename]]];
        NSPersistentStoreCoordinator* oldPersistentStoreCoordinator = [[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:oldModel];
        NSManagedObjectContext* oldContext = [[NSManagedObjectContext alloc] init];
        
        NSManagedObjectModel* newModel = self.managedObjectModel;
        NSPersistentStoreCoordinator* newPersistentStoreCoordinator = [[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:newModel];
        NSManagedObjectContext* newContext = [[NSManagedObjectContext alloc] init];
        
        NSError* err = NULL;
        NSMutableArray* upgradeProblems = [NSMutableArray array];
        
        [oldContext setPersistentStoreCoordinator:oldPersistentStoreCoordinator];
        [oldContext setUndoManager: nil];
        [newContext setPersistentStoreCoordinator:newPersistentStoreCoordinator];
        [newContext setUndoManager: nil];
        
        [NSFileManager.defaultManager removeItemAtPath:[self.baseDirPath stringByAppendingPathComponent:@"Database3.sql"] error:nil];
        [NSFileManager.defaultManager removeItemAtPath:[self.baseDirPath stringByAppendingPathComponent:@"Database3.sql-journal"] error:nil];
        
        if (![oldPersistentStoreCoordinator addPersistentStoreWithType:NSSQLiteStoreType configuration:nil URL:[NSURL fileURLWithPath:self.sqlFilePath] options:nil error:&err])
            N2LogError(err.description);
        
        if (![newPersistentStoreCoordinator addPersistentStoreWithType:NSSQLiteStoreType configuration:nil URL:[NSURL fileURLWithPath:[self.baseDirPath stringByAppendingPathComponent:@"Database3.sql"]] options:nil error:&err])
            N2LogError(err.description);
        
        NSManagedObject *newStudyTable, *newSeriesTable, *newImageTable, *newAlbumTable;
        NSArray *albumProperties, *studyProperties, *seriesProperties, *imageProperties;
        
        NSFetchRequest* req = [[[NSFetchRequest alloc] init] autorelease];
        req.entity = [NSEntityDescription entityForName:@"Album" inManagedObjectContext:oldContext];
        req.predicate = [NSPredicate predicateWithValue:YES];
        NSArray* albums = [oldContext executeFetchRequest:req error:NULL];
        
        albumProperties = [[[NSEntityDescription entityForName:@"Album" inManagedObjectContext:oldContext] attributesByName] allKeys];
        for (NSManagedObject* oldAlbum in albums)
        {
            newAlbumTable = [NSEntityDescription insertNewObjectForEntityForName:@"Album" inManagedObjectContext: newContext];
            
            for ( NSString *name in albumProperties)
            {
                [newAlbumTable setValue: [oldAlbum valueForKey: name] forKey: name];
            }
        }
        
        [newContext save:nil];
        
        // STUDIES
        NSFetchRequest* dbRequest = [[[NSFetchRequest alloc] init] autorelease];
        [dbRequest setEntity: [[oldModel entitiesByName] objectForKey:@"Study"]];
        [dbRequest setPredicate: [NSPredicate predicateWithValue:YES]];
        
        NSMutableArray* studies = [NSMutableArray arrayWithArray: [oldContext executeFetchRequest:dbRequest error:nil]];
        NSInteger studiesCount = studies.count;
        thread.status = [NSString stringWithFormat:NSLocalizedString(@"Upgrading %d %@...", nil), studiesCount, (studiesCount != 1 ? NSLocalizedString(@"studies", nil) : NSLocalizedString(@"study", nil))];
        thread.progress = 0;
        //   [NSThread sleepForTimeInterval:2];
        
        //[[splash progress] setMaxValue:[studies count]];
        
        int chunk = 0;
        
        studies = [NSMutableArray arrayWithArray: [studies sortedArrayUsingDescriptors: [NSArray arrayWithObject: [[[NSSortDescriptor alloc] initWithKey:@"patientUID" ascending:YES] autorelease]]]];
        if ([studies count] > 100)
        {
            int max = [studies count] - chunk*100;
            if (max > 100) max = 100;
            studies = [NSMutableArray arrayWithArray: [studies subarrayWithRange: NSMakeRange( chunk*100, max)]];
            chunk++;
        }
        [studies retain];
        
        studyProperties = [[[[oldModel entitiesByName] objectForKey:@"Study"] attributesByName] allKeys];
        seriesProperties = [[[[oldModel entitiesByName] objectForKey:@"Series"] attributesByName] allKeys];
        imageProperties = [[[[oldModel entitiesByName] objectForKey:@"Image"] attributesByName] allKeys];
        
        int counter = 0;
        
        NSArray *newAlbums = nil;
        NSArray *newAlbumsNames = nil;
        
        while( [studies count] > 0)
        {
            thread.progress = 1.0*counter/studiesCount;
            
            NSAutoreleasePool	*poolLoop = [[NSAutoreleasePool alloc] init];
            NSString *studyName = nil;
            
            @try
            {
                NSManagedObject *oldStudy = [studies lastObject];
                [studies removeLastObject];
                
                newStudyTable = [NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext: newContext];
                
                for ( NSString *name in studyProperties)
                {
                    if ([name isEqualToString: @"isKeyImage"] ||
                        [name isEqualToString: @"comment"] ||
                        [name isEqualToString: @"comment2"] ||
                        [name isEqualToString: @"comment3"] ||
                        [name isEqualToString: @"comment4"] ||
                        [name isEqualToString: @"reportURL"] ||
                        [name isEqualToString: @"stateText"])
                    {
                        [newStudyTable willChangeValueForKey: name];
                        @try {
                            [newStudyTable setPrimitiveValue: [oldStudy primitiveValueForKey: name] forKey: name];
                        }
                        @catch (NSException *exception) {
                            N2LogException( exception);
                        }
                        [newStudyTable didChangeValueForKey: name];
                    }
                    else [newStudyTable setValue: [oldStudy primitiveValueForKey: name] forKey: name];
                    
                    if ([name isEqualToString: @"name"])
                        studyName = [oldStudy primitiveValueForKey: name];
                }
                
                // SERIES
                NSArray *series = [[oldStudy valueForKey:@"series"] allObjects];
                for( NSManagedObject *oldSeries in series)
                {
                    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
                    
                    @try
                    {
                        newSeriesTable = [NSEntityDescription insertNewObjectForEntityForName:@"Series" inManagedObjectContext: newContext];
                        
                        for( NSString *name in seriesProperties)
                        {
                            if ([name isEqualToString: @"xOffset"] ||
                                [name isEqualToString: @"yOffset"] ||
                                [name isEqualToString: @"scale"] ||
                                [name isEqualToString: @"rotationAngle"] ||
                                [name isEqualToString: @"displayStyle"] ||
                                [name isEqualToString: @"windowLevel"] ||
                                [name isEqualToString: @"windowWidth"] ||
                                [name isEqualToString: @"yFlipped"] ||
                                [name isEqualToString: @"xFlipped"])
                            {
                                
                            }
                            else if ( [name isEqualToString: @"isKeyImage"] ||
                                     [name isEqualToString: @"comment"] ||
                                     [name isEqualToString: @"comment2"] ||
                                     [name isEqualToString: @"comment3"] ||
                                     [name isEqualToString: @"comment4"] ||
                                     [name isEqualToString: @"reportURL"] ||
                                     [name isEqualToString: @"stateText"])
                            {
                                [newSeriesTable willChangeValueForKey: name];
                                @try {
                                    [newSeriesTable setPrimitiveValue: [oldSeries primitiveValueForKey: name] forKey: name];
                                }
                                @catch (NSException *exception) {
                                    N2LogException( exception);
                                }
                                [newSeriesTable didChangeValueForKey: name];
                            }
                            else [newSeriesTable setValue: [oldSeries primitiveValueForKey: name] forKey: name];
                        }
                        [newSeriesTable setValue: newStudyTable forKey: @"study"];
                        
                        // IMAGES
                        NSArray *images = [[oldSeries valueForKey:@"images"] allObjects];
                        for ( NSManagedObject *oldImage in images)
                        {
                            @try
                            {
                                newImageTable = [NSEntityDescription insertNewObjectForEntityForName:@"Image" inManagedObjectContext: newContext];
                                
                                for( NSString *name in imageProperties)
                                {
                                    if ([name isEqualToString: @"xOffset"] ||
                                        [name isEqualToString: @"yOffset"] ||
                                        [name isEqualToString: @"scale"] ||
                                        [name isEqualToString: @"rotationAngle"] ||
                                        [name isEqualToString: @"windowLevel"] ||
                                        [name isEqualToString: @"windowWidth"] ||
                                        [name isEqualToString: @"yFlipped"] ||
                                        [name isEqualToString: @"xFlipped"])
                                    {
                                        
                                    }
                                    else if ([name isEqualToString: @"isKeyImage"] ||
                                             [name isEqualToString: @"comment"] ||
                                             [name isEqualToString: @"comment2"] ||
                                             [name isEqualToString: @"comment3"] ||
                                             [name isEqualToString: @"comment4"] ||
                                             [name isEqualToString: @"reportURL"] ||
                                             [name isEqualToString: @"stateText"])
                                    {
                                        [newImageTable willChangeValueForKey: name];
                                        @try {
                                            [newImageTable setPrimitiveValue: [oldImage primitiveValueForKey: name] forKey: name];
                                        }
                                        @catch (NSException *exception) {
                                            N2LogException( exception);
                                        }
                                        [newImageTable didChangeValueForKey: name];
                                    }
                                    else [newImageTable setValue: [oldImage primitiveValueForKey: name] forKey: name];
                                }
                                [newImageTable setValue: newSeriesTable forKey: @"series"];
                            }
                            
                            @catch (NSException *e)
                            {
                                NSLog(@"IMAGE LEVEL: Problems during updating: %@", e);
                                [e printStackTrace];
                            }
                        }
                    }
                    
                    @catch (NSException *e)
                    {
                        NSLog(@"SERIES LEVEL: Problems during updating: %@", e);
                        [e printStackTrace];
                    }
                    [pool release];
                }
                
                NSArray		*storedInAlbums = [[oldStudy valueForKey: @"albums"] allObjects];
                
                if ([storedInAlbums count])
                {
                    if (newAlbums == nil)
                    {
                        // Find all current albums
                        NSFetchRequest *r = [[[NSFetchRequest alloc] init] autorelease];
                        [r setEntity: [[newModel entitiesByName] objectForKey:@"Album"]];
                        [r setPredicate: [NSPredicate predicateWithValue:YES]];
                        
                        newAlbums = [newContext executeFetchRequest:r error:NULL];
                        newAlbumsNames = [newAlbums valueForKey:@"name"];
                        
                        [newAlbums retain];
                        [newAlbumsNames retain];
                    }
                    
                    @try
                    {
                        for( NSManagedObject *sa in storedInAlbums)
                        {
                            NSString *name = [sa valueForKey:@"name"];
                            NSMutableSet *studiesStoredInAlbum = [[newAlbums objectAtIndex: [newAlbumsNames indexOfObject: name]] mutableSetValueForKey:@"studies"];
                            
                            [studiesStoredInAlbum addObject: newStudyTable];
                        }
                    }
                    
                    @catch (NSException *e)
                    {
                        NSLog(@"ALBUM : %@", e);
                        [e printStackTrace];
                    }
                }
            }
            
            @catch (NSException * e)
            {
                NSLog(@"STUDY LEVEL: Problems during updating: %@", e);
                NSLog(@"Patient Name: %@", studyName);
                [upgradeProblems addObject:studyName];
                
                [e printStackTrace];
            }
            
            //		[splash incrementBy:1];
            counter++;
            
            NSLog(@"%d", counter);
            
            if (counter % 100 == 0)
            {
                [newContext save:nil];
                
                [newContext reset];
                [oldContext reset];
                
                [newAlbums release];			newAlbums = nil;
                [newAlbumsNames release];		newAlbumsNames = nil;
                
                [studies release];
                
                studies = [NSMutableArray arrayWithArray: [oldContext executeFetchRequest:dbRequest error:nil]];
                
                //	[[splash progress] setMaxValue:[studies count]];
                
                studies = [NSMutableArray arrayWithArray: [studies sortedArrayUsingDescriptors: [NSArray arrayWithObject: [[[NSSortDescriptor alloc] initWithKey:@"patientUID" ascending:YES] autorelease]]]];
                if ([studies count] > 100)
                {
                    int max = [studies count] - chunk*100;
                    if (max>100) max = 100;
                    studies = [NSMutableArray arrayWithArray: [studies subarrayWithRange: NSMakeRange( chunk*100, max)]];
                    chunk++;
                }
                
                [studies retain];
            }
            
            [poolLoop release];
        }
        
        thread.progress = -1;
        
        [newContext save:NULL];
        
        [[NSFileManager defaultManager] removeItemAtPath: [self.baseDirPath stringByAppendingPathComponent:@"Database-Old-PreviousVersion.sql"] error:nil];
        [[NSFileManager defaultManager] moveItemAtPath:self.sqlFilePath toPath:[self.baseDirPath stringByAppendingPathComponent:@"Database-Old-PreviousVersion.sql"] error:NULL];
        [[NSFileManager defaultManager] moveItemAtPath:[self.baseDirPath stringByAppendingPathComponent:@"Database3.sql"] toPath:self.sqlFilePath error:NULL];
        
        [studies release];					studies = nil;
        [newAlbums release];			newAlbums = nil;
        [newAlbumsNames release];		newAlbumsNames = nil;
        
        if (upgradeProblems.count)
            NSRunAlertPanel(NSLocalizedString(@"Database Upgrade", nil), NSLocalizedString(@"The upgrade encountered %d errors. These corrupted studies have been removed: %@", nil), nil, nil, nil, upgradeProblems.count, [upgradeProblems componentsJoinedByString:@", "]);
        
        return YES;
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
        
        NSRunAlertPanel( NSLocalizedString(@"Database Update", nil), NSLocalizedString(@"Database updating failed... The database SQL index file is probably corrupted... The database will be reconstructed.", nil), nil, nil, nil);
        
        [self rebuild:YES];
        
        return NO;
    } @finally {
        [oldContext reset];
        [oldContext release];
        [oldPersistentStoreCoordinator release];
        [oldModel release];
        
        [newContext reset];
        [newContext release];
        [newPersistentStoreCoordinator release];
        [newModel release];
        
        [thread exitOperation];
        thread.name = oldThreadName;
    }
    
    return NO;
}



// Series indexed before the importer derived an identifier for a file that
// carried none have an empty seriesDICOMUID, and the C-FIND SCP answers with it:
// an empty UI, in every response about that series. The value is derived from
// what the row is already grouped on, so it is the same identifier a re-import
// would produce.
+(void)repairEmptySeriesIdentifiersInContext:(NSManagedObjectContext*)context {
    NSFetchRequest* request = [[[NSFetchRequest alloc] init] autorelease];
    [request setEntity:[NSEntityDescription entityForName:@"Series" inManagedObjectContext:context]];
    [request setPredicate:[NSPredicate predicateWithFormat: @"seriesDICOMUID == nil OR seriesDICOMUID == %@", @""]];
    
    [context lock];
    @try {
        NSArray* series = [context executeFetchRequest:request error:nil];
        if( series.count == 0)
            return;
        
        NSLog( @"-------------- %d series have no DICOM identifier; deriving one for each", (int) series.count);
        
        for( NSManagedObject* one in series)
        {
            @try {
                NSString* grouping = [one valueForKey: @"seriesInstanceUID"];
                NSString* study = [one valueForKeyPath: @"study.studyInstanceUID"];
                NSString* derived = [HorosDerivedUID seriesUIDForKey:
                                     [NSString stringWithFormat: @"%@|%@", study? study : @"", grouping? grouping : @""]];
                [one setValue: derived forKey: @"seriesDICOMUID"];
            }
            @catch (NSException* e) {
                N2LogExceptionWithStackTrace(e);
            }
        }
        
        // The context is what holds the changes; this is a class method, so
        // there is no database instance to ask.
        NSError* error = nil;
        if( [context save: &error] == NO)
            NSLog( @"**** could not save the derived series identifiers: %@", error.localizedDescription);
    }
    @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    }
    @finally {
        [context unlock];
    }
}

+(void)repairFabricatedPatientIdentifiersInContext:(NSManagedObjectContext*)context {
    // A patient with no date of birth used to be given one, so the identifier
    // stored for those studies carries a date that was never in any file. Left
    // there, every instance of that patient arriving from now on computes an
    // identifier without it and lands in a third study instead of the one it
    // belongs to - the same split again, by the other route.
    NSFetchRequest* request = [[[NSFetchRequest alloc] init] autorelease];
    [request setEntity:[NSEntityDescription entityForName:@"Study" inManagedObjectContext:context]];
    [request setPredicate:[NSPredicate predicateWithFormat: @"dateOfBirth == nil AND patientUID != nil"]];
    
    [context lock];
    @try {
        NSArray* studies = [context executeFetchRequest:request error:nil];
        int repaired = 0;
        
        for( NSManagedObject* study in studies)
        {
            @try {
                NSString* stored = [study valueForKey: @"patientUID"];
                if( [HorosPatientIdentity uidCarriesABirthDate: stored] == NO)
                    continue;
                
                NSString* corrected = [HorosPatientIdentity uidWithoutBirthDate: stored];
                if( [corrected isEqualToString: stored])
                    continue;
                
                NSLog( @"---- patient identity: %@ has no date of birth; %@ becomes %@", [study valueForKey: @"name"], stored, corrected);
                [study setValue: corrected forKey: @"patientUID"];
                repaired++;
            }
            @catch (NSException* e) {
                N2LogExceptionWithStackTrace(e);
            }
        }
        
        if( repaired)
        {
            NSError* error = nil;
            if( [context save: &error] == NO)
                NSLog( @"**** could not save the repaired patient identifiers: %@", error.localizedDescription);
        }
    }
    @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    }
    @finally {
        [context unlock];
    }
}

+(void)recomputePatientUIDsInContext:(NSManagedObjectContext*)context {
    
    // Find all studies
    NSFetchRequest* dbRequest = [[[NSFetchRequest alloc] init] autorelease];
    [dbRequest setEntity:[NSEntityDescription entityForName:@"Study" inManagedObjectContext:context]];
    [dbRequest setPredicate:[NSPredicate predicateWithValue:YES]];
    
    [context lock];
    @try {
        NSArray* studiesArray = [context executeFetchRequest:dbRequest error:nil];
        
        if( studiesArray.count)
        {
            NSLog( @"-------------- Recompute Patient UIDs -- START");
            
            Wait *wait = nil;
            if( [NSThread isMainThread] && studiesArray.count > 200)
                wait = [[[Wait alloc] initWithString: NSLocalizedString( @"Recomputing Patient UIDs...", nil)] autorelease];
            
            [wait showWindow:self];
            
            [[wait progress] setMaxValue: studiesArray.count];
            
            int i = 0;
            
            for (DicomStudy* study in studiesArray)
            {
                NSAutoreleasePool *pool = [NSAutoreleasePool new];
                
                [wait incrementBy:1];
                
                @try {
                    
                    NSString *uid = [DicomFile patientUID: [NSDictionary dictionaryWithObjectsAndKeys: study.name, @"patientName", study.patientID, @"patientID", study.dateOfBirth, @"patientBirthDate", nil]];
                    
                    if( uid)
                        study.patientUID = uid;
                    
                    //				DicomImage* o = [[[[study valueForKey:@"series"] anyObject] valueForKey:@"images"] anyObject];
                    //				DicomFile* dcm = [[DicomFile alloc] init:o.completePath];
                    //				if (dcm && [dcm elementForKey:@"patientUID"])
                    //					study.patientUID = [dcm elementForKey:@"patientUID"];
                    //				[dcm release];
                    
                } @catch (NSException* e) {
                    N2LogExceptionWithStackTrace(e);
                }
                
                [pool release];
                
                i++;
                
                if( i % 1000 == 0)
                    [context save: nil];
            }
            
            [context save: nil];
            
            [wait close];
            
            NSLog( @"-------------- Recompute Patient UIDs -- END");
        }
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    } @finally {
        [context unlock];
    }
}

-(void)rebuild {
    [self rebuild:NO];
}

-(void)rebuild:(BOOL)complete
{
    NSThread* thread = [NSThread currentThread];
    
    [NSNotificationCenter.defaultCenter postNotificationName:OsirixDatabaseObjectsMayBecomeUnavailableNotification object:self userInfo:nil];
    
    [_importFilesFromIncomingDirLock lock];
    
    NSString *recoveryFolder = nil;
    NSString *savedAlbumsPath = nil;
    BOOL contextLocked = NO;
    @try {
        if (complete) {
            NSError *error = nil;
            if (self.managedObjectContext && ![self save:&error])
                @throw [NSException exceptionWithName:@"DatabaseRebuildFailure" reason:error.localizedDescription userInfo:@{NSUnderlyingErrorKey: error}];

            // Finish a verified recovery snapshot before retiring any active file.
            if ([NSFileManager.defaultManager fileExistsAtPath:self.sqlFilePath]) {
                NSString *metadata = [NSFileManager.defaultManager fileExistsAtPath:self.modelVersionFilePath] ? self.modelVersionFilePath : nil;
                recoveryFolder = [HorosDatabaseIndexBackup snapshotAtPath:self.sqlFilePath metadataPath:metadata error:&error];
                if (!recoveryFolder)
                    @throw [NSException exceptionWithName:@"DatabaseRebuildFailure" reason:error.localizedDescription userInfo:@{NSUnderlyingErrorKey: error}];
            } else {
                recoveryFolder = [[self.sqlFilePath.stringByDeletingLastPathComponent stringByAppendingPathComponent:@"Index Backups"] stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
                if (![NSFileManager.defaultManager createDirectoryAtPath:recoveryFolder withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions: @0700} error:&error])
                    @throw [NSException exceptionWithName:@"DatabaseRebuildFailure" reason:error.localizedDescription userInfo:@{NSUnderlyingErrorKey: error}];
            }
            savedAlbumsPath = [recoveryFolder stringByAppendingPathComponent:@"Albums.plist"];
            [self saveAlbumsToPath:savedAlbumsPath];

            thread.status = NSLocalizedString(@"Locking database...", nil);
            NSManagedObjectContext *oldContext = [self.managedObjectContext retain];
            [oldContext lock];
            @try {
                self.managedObjectContext = nil;
                if ([NSFileManager.defaultManager fileExistsAtPath:self.sqlFilePath]) {
                    NSString *retiredPath = [recoveryFolder stringByAppendingPathComponent:@"RetiredDatabase.sql"];
                    if (![NSFileManager.defaultManager moveItemAtPath:self.sqlFilePath toPath:retiredPath error:&error]) {
                        self.managedObjectContext = oldContext;
                        @throw [NSException exceptionWithName:@"DatabaseRebuildFailure" reason:error.localizedDescription userInfo:@{NSUnderlyingErrorKey: error}];
                    }
                }
            } @finally {
                [oldContext unlock];
                [oldContext release];
            }
            [NSFileManager.defaultManager removeItemAtPath:self.modelVersionFilePath error:NULL];
            self.managedObjectContext = [self contextAtPath:self.sqlFilePath];
            if (!self.managedObjectContext)
                @throw [NSException exceptionWithName:@"DatabaseRebuildFailure" reason:NSLocalizedString(@"The reconstructed database index could not be opened.", nil) userInfo:nil];
        } else [self save:NULL];

        [self lock];
        contextLocked = YES;
        thread.status = NSLocalizedString(@"Scanning database directory...", nil);
        
        NSMutableArray *filesArray = [[NSMutableArray alloc] initWithCapacity: 10000];
        
        // SCAN THE DATABASE FOLDER, TO BE SURE WE HAVE EVERYTHING!
        
        NSString	*aPath = [self dataDirPath];
        NSString	*incomingPath = [self incomingDirPath];
        long		totalFiles = 0;
        
        NSLog( @"Scan the Database folder");
        
        // In the DATABASE FOLDER, we have only folders! Move all files that are wrongly there to the INCOMING folder.... and then scan these folders containing the DICOM files
        
        NSArray	*dirContent = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:aPath error:NULL];
        @autoreleasepool
        {
            for( NSString *dir in dirContent)
            {
                NSString * itemPath = [aPath stringByAppendingPathComponent: dir];
                id fileType = [[[NSFileManager defaultManager] attributesOfItemAtPath:itemPath error:NULL] objectForKey:NSFileType];
                if ([fileType isEqual:NSFileTypeRegular])
                {
                    [[NSFileManager defaultManager] moveItemAtPath:itemPath toPath:[incomingPath stringByAppendingPathComponent: [itemPath lastPathComponent]] error:NULL];
                }
                else totalFiles += [[[[NSFileManager defaultManager] attributesOfItemAtPath:itemPath error:NULL] objectForKey: NSFileReferenceCount] intValue];
            }
        }
        
        dirContent = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:aPath error:NULL];
        
        NSLog( @"Start Rebuild");
        
        for( NSString *name in dirContent)
        {
            @autoreleasepool
            {
                NSString *curDir = [aPath stringByAppendingPathComponent: name];
                NSArray *subDir = [[NSFileManager defaultManager] contentsOfDirectoryAtPath: [aPath stringByAppendingPathComponent: name] error:NULL];
                
                for( NSString *subName in subDir)
                {
                    if ([subName characterAtIndex: 0] != '.')
                        [filesArray addObject: [curDir stringByAppendingPathComponent: subName]];
                }
            }
        }
        
        // ** DICOM ROI SR FOLDER
        @autoreleasepool
        {
            dirContent = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:self.roisDirPath error:NULL];
            for (NSString *name in dirContent)
                if ([name characterAtIndex:0] != '.')
                    [filesArray addObject: [self.roisDirPath stringByAppendingPathComponent: name]];
        }
        
        // ** Finish the rebuild
        
        thread.status = [NSString stringWithFormat:NSLocalizedString(@"Adding %@...", @"rebuild database thread status: Adding %@ (%@ = '120 files')"), N2LocalizedSingularPluralCount(filesArray.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil))];
        
        @autoreleasepool
        {
            [self addFilesAtPaths: filesArray postNotifications: NO dicomOnly: [[NSUserDefaults standardUserDefaults] boolForKey: @"onlyDICOM"] rereadExistingItems: NO generatedByOsiriX: NO returnArray: NO];
        }
        
        NSLog(@"End Rebuild");
        
        [filesArray release];
        
        if (!complete) {
            thread.status = NSLocalizedString(@"Checking for missing files...", nil);
            
            // remove non-available images
            for (DicomImage* aFile in [self objectsForEntity:self.imageEntity]) {
                FILE* fp = fopen(aFile.completePath.UTF8String, "r");
                if (fp)
                    fclose( fp);
                else [self.managedObjectContext deleteObject:aFile];
            }
            
            // remove empty studies
            thread.status = NSLocalizedString(@"Checking for empty studies...", nil);
            for (DicomStudy* study in [self objectsForEntity:self.studyEntity]) {
                [self checkForExistingReportForStudy:study];
                if (study.series.count == 0 || study.noFiles.intValue == 0)
                    [self.managedObjectContext deleteObject: study];
            }
        }
        else
        {
            //Restore albums
            if( [[NSFileManager defaultManager] fileExistsAtPath: savedAlbumsPath])
            {
                [self loadAlbumsFromPath: savedAlbumsPath];
                [[NSFileManager defaultManager] removeItemAtPath: savedAlbumsPath error: nil];
            }
        }
        
        NSError *saveError = nil;
        if (![self save:&saveError])
            @throw [NSException exceptionWithName:@"DatabaseRebuildFailure" reason:saveError.localizedDescription userInfo:saveError ? @{NSUnderlyingErrorKey: saveError} : nil];

        thread.status = NSLocalizedString(@"Checking reports consistency...", nil);
        [self checkReportsConsistencyWithDICOMSR];
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
        NSString *description;
        if (recoveryFolder)
            description = [NSString stringWithFormat:NSLocalizedString(@"Database reconstruction stopped: %@\nRecovery files: %@", nil), e.reason, recoveryFolder];
        else if (complete)
            description = [NSString stringWithFormat:NSLocalizedString(@"Database reconstruction stopped before the index could be backed up: %@", nil), e.reason];
        else
            description = [NSString stringWithFormat:NSLocalizedString(@"Database maintenance stopped: %@", nil), e.reason];
        NSError *error = [NSError errorWithDomain:@"HorosDatabaseRebuild" code:1 userInfo:@{NSLocalizedDescriptionKey: description}];
        dispatch_async(dispatch_get_main_queue(), ^{ [NSApp presentError:error]; });
    } @finally {
        if (contextLocked) [self unlock];
        [_importFilesFromIncomingDirLock unlock];
    }
}

-(void)checkReportsConsistencyWithDICOMSR {
    // Find all studies with reportURL
    [self.managedObjectContext lock];
    
    @try {
        NSPredicate *predicate = [NSPredicate predicateWithFormat:  @"reportURL != NIL"];
        NSFetchRequest *dbRequest = [[[NSFetchRequest alloc] init] autorelease];
        dbRequest.entity = [self.managedObjectModel.entitiesByName objectForKey:@"Study"];
        dbRequest.predicate = predicate;
        
        NSError	*error = nil;
        NSArray *studiesArray = [self.managedObjectContext executeFetchRequest:dbRequest error:&error];
        
        for (DicomStudy *s in studiesArray)
            [s archiveReportAsDICOMSR];
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    } @finally {
        [self.managedObjectContext unlock];
    }
}

-(void)checkForExistingReportForStudy:(DicomStudy*)study {
#ifndef OSIRIX_LIGHT
    NSString *attached = study.reportURL;
    if (attached.length && ([attached hasPrefix:@"http://"] || [attached hasPrefix:@"https://"] ||
        [NSFileManager.defaultManager fileExistsAtPath:attached])) return;
    @try { // is there a report?
        NSArray* filenames = [NSArray arrayWithObjects: [Reports getUniqueFilename:study], [Reports getOldUniqueFilename:study], NULL];
        NSArray* extensions = [NSArray arrayWithObjects: @"pages", @"odt", @"doc", @"docx", @"rtf", NULL];
        for (NSString* filename in filenames)
            for (NSString* extension in extensions) {
                NSString* reportPath = [self.reportsDirPath stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.%@", filename, extension]];
                if ([NSFileManager.defaultManager fileExistsAtPath:reportPath]) {
                    study.reportURL = reportPath;
                    return;
                }
            }
    } @catch ( NSException *e) {
        N2LogExceptionWithStackTrace(e);
    }
#endif
}

-(BOOL)allowAutoroutingWithPostNotifications:(BOOL)postNotifications rereadExistingItems:(BOOL)rereadExistingItems
{
    return YES;
}

-(void)alertToApplyRoutingRules:(NSArray*)routingRules toImages:(NSArray*)images
{
    [self applyRoutingRules:nil toImages:images];
}

-(void)dumpSqlFile {
    //WaitRendering *splash = [[WaitRendering alloc] init:NSLocalizedString(@"Dumping SQL Index file...", nil)]; // TODO: status
    //[splash showWindow:self];
    
    @try {
        NSString* repairedDBFile = [self.sqlFilePath stringByAppendingPathExtension:@"dump"];
        
        [NSFileManager.defaultManager removeItemAtPath:repairedDBFile error:nil];
        [NSFileManager.defaultManager createFileAtPath:repairedDBFile contents:[NSData data] attributes:nil];
        
        NSTask* theTask = [[NSTask alloc] init];
        [theTask setLaunchPath: @"/usr/bin/sqlite3"];
        [theTask setStandardOutput:[NSFileHandle fileHandleForWritingAtPath:repairedDBFile]];
        [theTask setArguments:[NSArray arrayWithObjects: self.sqlFilePath, @".dump", nil]];
        
        [theTask launch];
        
        while( [theTask isRunning])
            [NSThread sleepForTimeInterval: 0.1];
        
        //[theTask waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
        
        int dumpStatus = [theTask terminationStatus];
        [theTask release];
        
        if (dumpStatus == 0) {
            NSString* repairedDBFinalFile = [repairedDBFile stringByAppendingPathExtension: @"sql"];
            [NSFileManager.defaultManager removeItemAtPath:repairedDBFinalFile error:nil];
            
            theTask = [[NSTask alloc] init];
            [theTask setLaunchPath:@"/usr/bin/sqlite3"];
            [theTask setStandardInput:[NSFileHandle fileHandleForReadingAtPath:repairedDBFile]];
            [theTask setArguments:[NSArray arrayWithObjects: repairedDBFinalFile, nil]];		
            
            [theTask launch];
            while( [theTask isRunning])
                [NSThread sleepForTimeInterval: 0.1];
            
            //[theTask waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
            
            if ([theTask terminationStatus] == 0) {
                [[NSFileManager defaultManager] trashItemAtURL:[NSURL fileURLWithPath:self.sqlFilePath] resultingItemURL:NULL error:NULL];
                [NSFileManager.defaultManager moveItemAtPath:repairedDBFinalFile toPath:self.sqlFilePath error:nil];
            }
            
            [theTask release];
        }
        
        [[NSFileManager defaultManager] removeItemAtPath: repairedDBFile error: nil];
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    }
    
    //	[splash close];
    //	[splash autorelease];
}

-(void)rebuildSqlFile {
    [_importFilesFromIncomingDirLock lock];
    
    [self save:NULL];
    self.managedObjectContext = nil;
    
    [self dumpSqlFile];
    //	[self upgradeSqlFileFromModelVersion:CurrentDatabaseVersion]; // removing this line reflects antoine's commit 9758
    
    self.managedObjectContext = [self contextAtPath:self.sqlFilePath];
    
    [self checkReportsConsistencyWithDICOMSR];
    
    [_importFilesFromIncomingDirLock unlock];
}

-(void)checkForHtmlTemplates {
    // directory
    NSString* htmlTemplatesDirectory = [self htmlTemplatesDirPath];
    if ([[NSFileManager defaultManager] fileExistsAtPath:htmlTemplatesDirectory] == NO)
        [[NSFileManager defaultManager] createDirectoryAtPath:htmlTemplatesDirectory withIntermediateDirectories:YES attributes:nil error:NULL];
    
    // HTML templates
    NSString *templateFile;
    
    templateFile = [htmlTemplatesDirectory stringByAppendingPathComponent:@"QTExportPatientsTemplate.html"];
    //	NSLog( @"%@", templateFile);
    if ([[NSFileManager defaultManager] fileExistsAtPath:templateFile] == NO)
        [[NSFileManager defaultManager] copyItemAtPath:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"QTExportPatientsTemplate.html"] toPath:templateFile error:NULL];
    
    templateFile = [htmlTemplatesDirectory stringByAppendingPathComponent:@"QTExportStudiesTemplate.html"];
    //	NSLog( @"%@", templateFile);
    if ([[NSFileManager defaultManager] fileExistsAtPath:templateFile] == NO)
        [[NSFileManager defaultManager] copyItemAtPath:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"QTExportStudiesTemplate.html"] toPath:templateFile error:NULL];
    
    templateFile = [htmlTemplatesDirectory stringByAppendingPathComponent:@"QTExportSeriesTemplate.html"];
    //	NSLog( @"%@", templateFile);
    if ([[NSFileManager defaultManager] fileExistsAtPath:templateFile] == NO)
        [[NSFileManager defaultManager] copyItemAtPath:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"QTExportSeriesTemplate.html"] toPath:templateFile error:NULL];
    
    // HTML-extra directory
    NSString *htmlExtraDirectory = [htmlTemplatesDirectory stringByAppendingPathComponent:@"html-extra/"];
    if ([[NSFileManager defaultManager] fileExistsAtPath:htmlExtraDirectory] == NO)
        [[NSFileManager defaultManager] createDirectoryAtPath:htmlExtraDirectory withIntermediateDirectories:YES attributes:nil error:NULL];
    
    // CSS file
    NSString *cssFile = [htmlExtraDirectory stringByAppendingPathComponent:@"style.css"];
    if ([[NSFileManager defaultManager] fileExistsAtPath:cssFile] == NO)
        [[NSFileManager defaultManager] copyItemAtPath:[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"QTExportStyle.css"] toPath:cssFile error:NULL];
    
}

@end
