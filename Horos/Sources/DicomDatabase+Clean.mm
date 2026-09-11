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

#import "DicomDatabase+Clean.h"
#import "N2Debug.h"
#import "AppController.h"
#import "ThreadsManager.h"
#import "DicomImage.h"
#import "DicomStudy.h"
#import "DicomSeries.h"
#import "BrowserController.h"
#import "Notifications.h"
#import "NSThread+N2.h"
#import "PreferencesWindowController.h"

#define MAXSTUDYDELETE 50

@interface DicomDatabase (Private)

-(NSRecursiveLock*)cleanLock;

+(void)_syncCleanTimer;

@end

@implementation DicomDatabase (Clean)

-(void)initClean {
	if (self.isMainDatabase) {
        _cleanLock = [[NSRecursiveLock alloc] init];
    } else {
        _cleanLock = [[self.mainDatabase cleanLock] retain];
    }
	[DicomDatabase _syncCleanTimer];
}

-(void)deallocClean {
	NSRecursiveLock* temp;
	
    if (self.isMainDatabase) {
        temp = _cleanLock;
        [temp lock]; // if currently cleaning, wait until finished
        _cleanLock = nil;
        [temp unlock];
        [temp release];
    } else {
        [_cleanLock release];
    }
}

-(NSRecursiveLock*)cleanLock {
    return _cleanLock;
}

+(void)_syncCleanTimer {
	static NSTimer* cleanTimer = nil;
	
	if (cleanTimer)
		return;
	
	cleanTimer = [[NSTimer timerWithTimeInterval:15*60+2.5 target:self selector:@selector(_cleanTimerCallback:) userInfo:nil repeats:YES] retain];
	[[NSRunLoop mainRunLoop] addTimer:cleanTimer forMode:NSModalPanelRunLoopMode];
	[[NSRunLoop mainRunLoop] addTimer:cleanTimer forMode:NSDefaultRunLoopMode];
}

+(void)_cleanTimerCallback:(NSTimer*)timer {
	for (DicomDatabase* dbi in [self allDatabases])
		if (dbi.isLocal)
			[dbi initiateCleanUnlessAlreadyCleaning];
}

-(void)initiateCleanUnlessAlreadyCleaning {
	if ([_cleanLock tryLock])
		@try {
			[self performSelectorInBackground:@selector(_cleanThread) withObject:nil];
		} @catch (NSException* e) {
			N2LogExceptionWithStackTrace(e);
		} @finally {
			[_cleanLock unlock];
		}
	else NSLog(@"Warning: couldn't initiate clean");
}

-(void)_cleanThread {
	NSAutoreleasePool* pool = [NSAutoreleasePool new];
	@try {
		NSThread* thread = [NSThread currentThread];
		thread.name = NSLocalizedString(@"Cleaning...", nil);
		[self.independentDatabase cleanOldStuff];
	} @catch (NSException * e) {
		N2LogExceptionWithStackTrace(e);
	} @finally {
		[pool release];
	}
}

// Both the preview and the executor use these selectors on the owning context thread.
- (NSArray *)dateCleanupCandidates
{
    NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
    NSArray             *studiesArray;
    NSDate              *now = [NSDate date];
    NSDate              *producedDate = [now dateByAddingTimeInterval: -[[defaults stringForKey:@"AUTOCLEANINGDATEPRODUCEDDAYS"] intValue]*60*60*24];
    NSDate              *openedDate = [now dateByAddingTimeInterval: -[[defaults stringForKey:@"AUTOCLEANINGDATEOPENEDDAYS"] intValue]*60*60*24];
    NSMutableArray      *toBeRemoved = [NSMutableArray array];
    BOOL                dontDeleteStudiesWithComments = [[NSUserDefaults standardUserDefaults] boolForKey: @"dontDeleteStudiesWithComments"];
    BOOL                dontDeleteStudiesIfInAlbum = [[NSUserDefaults standardUserDefaults] boolForKey:@"dontDeleteStudiesIfInAlbum"];

    @try {
        studiesArray = [[self objectsForEntity:self.studyEntity] sortedArrayUsingDescriptors:[NSArray arrayWithObject:[[[NSSortDescriptor alloc] initWithKey:@"patientUID" ascending:YES] autorelease]]];
        for (NSInteger i = 0; i < [studiesArray count]; i++)
        {
            NSString    *patientID = [[studiesArray objectAtIndex: i] valueForKey:@"patientUID"];
            NSDate      *studyDate = [[studiesArray objectAtIndex: i] valueForKey:@"date"];
            NSDate      *openedStudyDate = [[studiesArray objectAtIndex: i] valueForKey:@"dateOpened"];

            if( openedStudyDate == nil) openedStudyDate = [[studiesArray objectAtIndex: i] valueForKey:@"dateAdded"];

            int to, from = i;

            while( i < (long)[studiesArray count]-1 && [patientID compare: [[studiesArray objectAtIndex: i+1] valueForKey:@"patientUID"] options: NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch | NSWidthInsensitiveSearch] == NSOrderedSame)
            {
                i++;
                studyDate = [studyDate laterDate: [[studiesArray objectAtIndex: i] valueForKey:@"date"]];
                if( [[studiesArray objectAtIndex: i] valueForKey:@"dateOpened"]) openedStudyDate = [openedStudyDate laterDate: [[studiesArray objectAtIndex: i] valueForKey:@"dateOpened"]];
                else openedStudyDate = [openedStudyDate laterDate: [[studiesArray objectAtIndex: i] valueForKey:@"dateAdded"]];
            }
            to = i;

            BOOL dateProduced = YES, dateOpened = YES;

            if( [defaults boolForKey: @"AUTOCLEANINGDATEPRODUCED"])
                dateProduced = [producedDate compare: studyDate] == NSOrderedDescending;

            if( [defaults boolForKey: @"AUTOCLEANINGDATEOPENED"])
            {
                if( openedStudyDate == nil) openedStudyDate = [[studiesArray objectAtIndex: i] valueForKey:@"dateAdded"];

                dateOpened = [openedDate compare: openedStudyDate] == NSOrderedDescending;
            }

            if(  dateProduced == YES && dateOpened == YES)
            {
                for( int x = from; x <= to; x++)
                {
                    if( [[[studiesArray objectAtIndex: x] valueForKey:@"lockedStudy"] boolValue] == NO)
                    {
                        BOOL addIt = YES;
                        DicomStudy *dy = [studiesArray objectAtIndex: x];

                        if( dontDeleteStudiesIfInAlbum)
                        {
                            if( dy.albums.count > 0)
                                addIt = NO;
                        }

                        if( dontDeleteStudiesWithComments)
                        {
                            NSString *str = @"";

                            if( [dy valueForKey: @"comment"])
                                str = [str stringByAppendingString: [dy valueForKey: @"comment"]];
                            if( [dy valueForKey: @"comment2"])
                                str = [str stringByAppendingString: [dy valueForKey: @"comment2"]];
                            if( [dy valueForKey: @"comment3"])
                                str = [str stringByAppendingString: [dy valueForKey: @"comment3"]];
                            if( [dy valueForKey: @"comment4"])
                                str = [str stringByAppendingString: [dy valueForKey: @"comment4"]];

                            if( str.length > 0)
                                addIt = NO;
                        }

                        if( addIt)
                            [toBeRemoved addObject: [studiesArray objectAtIndex: x]];
                    }
                }
            }
        }

        for ( int i = 0; i < [toBeRemoved count]; i++) // Check if studies are in an album or added this week.  If so don't autoclean that study from the database (DDP: 051108).
        {
            if ( [[[toBeRemoved objectAtIndex: i] valueForKey: @"albums"] count] > 0 ||
                [[[toBeRemoved objectAtIndex: i] valueForKey: @"dateAdded"] timeIntervalSinceNow] > -60*60*7*24.0)  // within 7 days
            {
                [toBeRemoved removeObjectAtIndex: i];
                i--;
            }
        }

        if( [defaults boolForKey: @"AUTOCLEANINGCOMMENTS"])
        {
            for ( int i = 0; i < [toBeRemoved count]; i++)
            {
                NSString *comment = [[toBeRemoved objectAtIndex: i] valueForKey: @"comment"];

                if( comment == nil) comment = @"";

                if ([comment rangeOfString:[defaults stringForKey: @"AUTOCLEANINGCOMMENTSTEXT"] options:NSCaseInsensitiveSearch].location == NSNotFound)
                {
                    if( [defaults integerForKey: @"AUTOCLEANINGDONTCONTAIN"] == 0)
                    {
                        [toBeRemoved removeObjectAtIndex: i];
                        i--;
                    }
                }
                else
                {
                    if( [defaults integerForKey: @"AUTOCLEANINGDONTCONTAIN"] == 1)
                    {
                        [toBeRemoved removeObjectAtIndex: i];
                        i--;
                    }
                }
            }
        }
    }
    @catch (NSException *e) { @throw; }

    if (toBeRemoved.count > MAXSTUDYDELETE)
        [toBeRemoved removeObjectsInRange:NSMakeRange(MAXSTUDYDELETE, toBeRemoved.count - MAXSTUDYDELETE)];
    return toBeRemoved;
}

- (NSArray *)spaceCleanupCandidatesRecentlyAdded:(BOOL *)recentlyAdded
{
    if (recentlyAdded) *recentlyAdded = NO;
            NSMutableArray* studiesDates = [NSMutableArray array];

    //        BOOL dontDeleteStudiesIfInAlbum = [[NSUserDefaults standardUserDefaults] boolForKey:@"dontDeleteStudiesIfInAlbum"];
            BOOL flagDoNotDeleteIfComments = [[NSUserDefaults standardUserDefaults] boolForKey:@"dontDeleteStudiesWithComments"];
            NSInteger autocleanSpaceMode = [[[NSUserDefaults standardUserDefaults] objectForKey:@"AutocleanSpaceMode"] intValue];

            for (DicomStudy* study in [self objectsForEntity:self.studyEntity]) {
                // if study is locked, do not delete it
                if ([study.lockedStudy boolValue])
                    continue;
                // if the user told us not to delete studies with comments and there are comments, do not delete it
                if (flagDoNotDeleteIfComments)
                    if (study.comment.length || study.comment2.length || study.comment3.length || study.comment4.length)
                        continue;

                if( study.albums.count > 0)
                    continue;

                if ([study.dateAdded timeIntervalSinceNow] > -7200) {
                    if (recentlyAdded) *recentlyAdded = YES;
                    continue;
                }

                // study can be deleted
                NSDate* d = nil; // determine the delete priority date
                switch (autocleanSpaceMode) {
                    case 0: { // oldest Studies
                        d = study.date;
                    } break;
                    case 1: { // oldest unopened
                        if (study.dateOpened)
                            d = study.dateOpened;
                        else
                            if (study.dateAdded)
                                d = study.dateAdded;
                            else d = study.date;
                    } break;
                    case 2: { // least recently added
                        if (study.dateAdded)
                            d = study.dateAdded;
                        else d = study.date;
                    } break;
                }

                [studiesDates addObject:[NSArray arrayWithObjects: study, d, nil]];
            }

            // sort studiesDates by date
            [studiesDates sortUsingComparator: ^NSComparisonResult(id a, id b) {
                if ([a count] < 2 || [b count] < 2) return NSOrderedSame;
                return [[a objectAtIndex:1] compare:[b objectAtIndex:1]];
            }];

    return studiesDates;
}

- (NSInteger)cleanupThresholdForAttributes:(NSDictionary *)attributes
{
    double setting = [[NSUserDefaults.standardUserDefaults stringForKey:@"AUTOCLEANINGSPACESIZE"] doubleValue];
    double megabytes = setting < 0 ? -setting / 100 * ([attributes[NSFileSystemSize] unsignedLongLongValue] / 1048576) : setting;
    if (!isfinite(megabytes) || megabytes <= 0 || megabytes >= (double)NSIntegerMax) return 0;
    return (NSInteger)megabytes;
}

- (NSDictionary *)automaticCleanupPreview
{
    [_cleanLock lock];
    [self lock];
    @try {
        NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
        NSMutableArray *lines = [NSMutableArray array];
        NSMutableArray *rows = [NSMutableArray array];
        [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Database: %@", nil), self.dataBaseDirPath]];
        if (!self.isLocal || self.isReadOnly)
            return @{ @"summary": NSLocalizedString(@"Automatic cleanup is unavailable for this read-only or remote database.", nil), @"rows": rows };

        BOOL dateEnabled = [defaults boolForKey:@"AUTOCLEANINGDATE"];
        BOOL produced = [defaults boolForKey:@"AUTOCLEANINGDATEPRODUCED"];
        BOOL opened = [defaults boolForKey:@"AUTOCLEANINGDATEOPENED"];
        BOOL validDays = [defaults integerForKey:@"LOGCLEANINGDAYS"] > 1 &&
            [defaults integerForKey:@"AUTOCLEANINGDATEPRODUCEDDAYS"] > 1 &&
            [defaults integerForKey:@"AUTOCLEANINGDATEOPENEDDAYS"] > 1;
        [lines addObject:dateEnabled ? NSLocalizedString(@"Date cleanup: enabled (all checked conditions must match for the patient).", nil) : NSLocalizedString(@"Date cleanup: disabled.", nil)];
        if (dateEnabled && produced) [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Acquired more than %ld days ago.", nil), (long)[defaults integerForKey:@"AUTOCLEANINGDATEPRODUCEDDAYS"]]];
        if (dateEnabled && opened) [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Not opened in the last %ld days (falls back to date added).", nil), (long)[defaults integerForKey:@"AUTOCLEANINGDATEOPENEDDAYS"]]];
        if (dateEnabled && !produced && !opened) [lines addObject:NSLocalizedString(@"No date condition is selected; no date cleanup will run.", nil)];
        if (!validDays) [lines addObject:NSLocalizedString(@"Scheduled cleanup is paused: retention periods must be greater than one day.", nil)];
        if (dateEnabled && [defaults boolForKey:@"AUTOCLEANINGCOMMENTS"])
            [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Date comment filter: %@ “%@”.", nil),
                [defaults integerForKey:@"AUTOCLEANINGDONTCONTAIN"] == 1 ? NSLocalizedString(@"does not contain", nil) : NSLocalizedString(@"contains", nil),
                [defaults stringForKey:@"AUTOCLEANINGCOMMENTSTEXT"] ?: @""]];

        NSArray *dateCandidates = dateEnabled && validDays && (produced || opened) ? [self dateCleanupCandidates] : @[];
        NSMutableArray *orderedSpace = [NSMutableArray array];
        BOOL spaceEnabled = [defaults boolForKey:@"AUTOCLEANINGSPACE"];
        [lines addObject:spaceEnabled ? NSLocalizedString(@"Space cleanup: enabled.", nil) : NSLocalizedString(@"Space cleanup: disabled.", nil)];
        if (spaceEnabled) {
            NSDictionary *attrs = [NSFileManager.defaultManager attributesOfFileSystemForPath:self.dataBaseDirPath error:NULL];
            double setting = [[defaults stringForKey:@"AUTOCLEANINGSPACESIZE"] doubleValue];
            if (!attrs[NSFileSystemSize] || !attrs[NSFileSystemFreeSize] || !isfinite(setting))
                [lines addObject:NSLocalizedString(@"Space eligibility unavailable: cannot read a valid threshold and filesystem capacity.", nil)];
            else {
                unsigned long long requested = [self cleanupThresholdForAttributes:attrs];
                unsigned long long available = [attrs[NSFileSystemFreeSize] unsignedLongLongValue] / 1048576;
                [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Free space: %llu MB; cleanup threshold: %llu MB.", nil), available, requested]];
                NSArray *orderNames = @[NSLocalizedString(@"date acquired", nil), NSLocalizedString(@"date last opened (or added)", nil), NSLocalizedString(@"date added", nil)];
                NSInteger mode = [defaults integerForKey:@"AutocleanSpaceMode"];
                [lines addObject:[NSString stringWithFormat:NSLocalizedString(@"Space priority: oldest %@ first.", nil), mode >= 0 && mode < orderNames.count ? orderNames[mode] : NSLocalizedString(@"unspecified date", nil)]];
                if (available < requested) {
                    for (NSArray *entry in [self spaceCleanupCandidatesRecentlyAdded:NULL]) {
                        DicomStudy *study = entry[0];
                        if (![dateCandidates containsObject:study]) [orderedSpace addObject:study];
                        if (orderedSpace.count == MAXSTUDYDELETE) break;
                    }
                } else [lines addObject:requested ? NSLocalizedString(@"The space threshold is not reached; no space candidates now.", nil) : NSLocalizedString(@"The space threshold is zero or invalid; no space cleanup will run.", nil)];
            }
        }
        [lines addObject:NSLocalizedString(@"Locked studies and studies in albums are protected. Date cleanup excludes studies added in the last 7 days; space cleanup excludes the last 2 hours.", nil)];
        [lines addObject:[defaults boolForKey:@"dontDeleteStudiesWithComments"] ? NSLocalizedString(@"Studies with comments are protected.", nil) : NSLocalizedString(@"Studies with comments may be deleted.", nil)];
        [lines addObject:[defaults boolForKey:@"AUTOCLEANINGDELETEORIGINAL"] ? NSLocalizedString(@"Linked original files will also be deleted.", nil) : NSLocalizedString(@"Linked original files will be kept.", nil)];
        [lines addObject:NSLocalizedString(@"Up to 50 studies per rule per pass. Space cleanup stops as soon as enough space is available; date cleanup may free that space first. This list is a snapshot, not a scheduled deletion or a guarantee that every candidate will be removed.", nil)];
        for (NSUInteger kind = 0; kind < 2; kind++) {
            NSArray *candidates = kind == 0 ? dateCandidates : orderedSpace;
            for (DicomStudy *study in candidates) {
                [rows addObject:@{ @"rule": kind == 0 ? NSLocalizedString(@"Date", nil) : NSLocalizedString(@"Space priority", nil),
                    @"patient": [study valueForKey:@"name"] ?: study.patientID ?: @"",
                    @"study": study.studyName ?: @"", @"uid": study.studyInstanceUID ?: @"",
                    @"date": study.date ?: [NSNull null] }];
            }
        }
        return @{ @"summary": [lines componentsJoinedByString:@"\n"], @"rows": rows };
    } @catch (NSException *exception) {
        return @{ @"summary": NSLocalizedString(@"Preview unavailable: study eligibility could not be evaluated. No files were changed. Check the database and cleanup preferences.", nil), @"rows": @[], @"error": @YES };
    } @finally {
        [self unlock];
        [_cleanLock unlock];
    }
}

-(void)cleanOldStuff {
    if (self.isReadOnly)
        return;
	if (!self.isLocal) return;
	if ([AppController.sharedAppController isSessionInactive]) return;
    if( [[NSUserDefaults standardUserDefaults] integerForKey:@"LOGCLEANINGDAYS"] <= 1) return;
    if( [[NSUserDefaults standardUserDefaults] integerForKey:@"AUTOCLEANINGDATEPRODUCEDDAYS"] <= 1) return;
    if( [[NSUserDefaults standardUserDefaults] integerForKey:@"AUTOCLEANINGDATEOPENEDDAYS"] <= 1) return;
	
    N2ManagedObjectContext *context = (N2ManagedObjectContext *)self.managedObjectContext;
    if (![context respondsToSelector:@selector(performAtomicChanges:error:)] ||
        context.defersSaves || context.hasChanges)
        return;

	[_cleanLock lock];
	@try {
		NSUserDefaults	*defaults = [NSUserDefaults standardUserDefaults];
		
        // Commit log maintenance separately so study cleanup owns a clean context.
        NSError *logError = nil;
        if (![context performAtomicChanges:^BOOL(NSError **error) {
            NSDate *cutoff = [[NSDate date] dateByAddingTimeInterval:
                -[defaults integerForKey:@"LOGCLEANINGDAYS"] * 86400.0];
            NSPredicate *predicate = [NSPredicate predicateWithFormat:@"startTime <= %@", cutoff];
            for (id log in [self objectsForEntity:self.logEntryEntity predicate:predicate])
                [context deleteObject:log];
            return YES;
        } error:&logError]) {
            NSLog(@"Auto-clean stopped: log maintenance could not be saved: %@", logError);
            return;
        }

		if ([defaults boolForKey:@"AUTOCLEANINGDATE"] && ([defaults boolForKey:@"AUTOCLEANINGDATEPRODUCED"] || [defaults boolForKey:@"AUTOCLEANINGDATEOPENED"]))
        {
			if ([self tryLock])
				@try {
                    NSArray *toBeRemoved = [self dateCleanupCandidates];
					if( [toBeRemoved count] > 0)
					{
						NSLog(@"DicomDatabase Clean: will delete: %d studies", (int) [toBeRemoved count]);
						
						@try
						{
                            NSMutableSet *linkedPaths = [NSMutableSet set];
                            if ([defaults boolForKey:@"AUTOCLEANINGDELETEORIGINAL"]) {
                                for (DicomStudy *study in toBeRemoved)
                                    for (DicomSeries *series in study.series.allObjects)
                                        for (DicomImage *image in series.images.allObjects) {
                                            if ([[image valueForKey:@"inDatabaseFolder"] boolValue]) continue;
                                            NSString *path = image.completePath;
                                            if (!path.length) continue;
                                            [linkedPaths addObject:path];
                                            if ([path.pathExtension isEqualToString:@"hdr"])
                                                [linkedPaths addObject:[path.stringByDeletingPathExtension stringByAppendingPathExtension:@"img"]];
                                        }
                            }

                            NSError *saveError = nil;
                            if (![context performAtomicChanges:^BOOL(NSError **error) {
                                for (DicomStudy *study in toBeRemoved)
                                    [context deleteObject:study];
                                return YES;
                            } error:&saveError]) {
                                NSLog(@"Auto-clean stopped: date-based deletion could not be saved: %@", saveError);
                                return;
                            }
                            // Local image deletion is queued by validateForDelete only
                            // after the commit. Linked originals obey the same ordering.
                            for (NSString *path in linkedPaths) {
                                NSError *fileError = nil;
                                if (![NSFileManager.defaultManager removeItemAtPath:path error:&fileError] &&
                                    fileError.code != NSFileNoSuchFileError)
                                    NSLog(@"Auto-clean could not remove a committed linked file: %@", fileError);
                            }
						} @catch (NSException* e) {
                            N2LogExceptionWithStackTrace(e);
                            return;
						}
						
						// refresh database
						[NSNotificationCenter.defaultCenter postNotificationName:_O2AddToDBAnywayNotification object:self userInfo: nil];
						[NSNotificationCenter.defaultCenter postNotificationName:_O2AddToDBAnywayCompleteNotification object:self userInfo: nil];
						[NSNotificationCenter.defaultCenter postNotificationName:OsirixAddToDBNotification object:self userInfo: nil];
						[NSNotificationCenter.defaultCenter postNotificationName:OsirixAddToDBCompleteNotification object:self userInfo: nil];
					}
					
				} @catch (NSException* e) {
					N2LogExceptionWithStackTrace(e);
				} @finally {
					[self unlock];
				}
		}
		
		[self cleanForFreeSpace];
	} @catch (NSException* e) {
		N2LogExceptionWithStackTrace(e);
	} @finally {
		[_cleanLock unlock];
	}
	
}

-(void)cleanForFreeSpace {
	if (self.isReadOnly)
        return;
    
    [_cleanLock lock];
    
    NSThread* thread = [NSThread currentThread];
    [thread enterOperationIgnoringLowerLevels];
    thread.status = NSLocalizedString(@"Cleaning database...", nil);
    
	@try {
        
        if( [NSUserDefaults.standardUserDefaults boolForKey:@"AUTOCLEANINGSPACE"])
		{
            NSDictionary* fsattrs = [[NSFileManager defaultManager] attributesOfFileSystemForPath:self.dataBaseDirPath error:NULL];
            if (![fsattrs objectForKey:NSFileSystemSize]) {
                NSLog(@"Error: database cleaning mechanism couldn't obtain filesystem size information for %@", self.dataBaseDirPath);
                return;
            }
            
            NSInteger freeMemoryRequested = [self cleanupThresholdForAttributes:fsattrs];
			[self cleanForFreeSpaceMB:freeMemoryRequested];
		}
		
		// warn user if less than 1% / 300MB available
		[self updateStorageAvailabilityWarning];
		
	} @catch (NSException* e) {
		N2LogExceptionWithStackTrace(e);
	} @finally {
        [thread exitOperation];
		[_cleanLock unlock];
	}
}

static BOOL _errorCurrentlyDisplayed = NO;
static BOOL _cleanForFreeSpaceLimitSoonReachedDisplayed = NO;

- (void) _cleanForFreeSpaceLimitSoonReachedWarning
{
    if( _errorCurrentlyDisplayed)
        return;
    
    if([[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"] == NO)
    {
        if ([[NSUserDefaults standardUserDefaults] boolForKey: @"hideCleanForFreeSpaceLimitSoonReachedWarning"] == NO)
        {
            _errorCurrentlyDisplayed = YES;
            
            NSAlert* alert = [[NSAlert new] autorelease];
            [alert setMessageText: NSLocalizedString(@"Warning - Free Space", nil)];
            [alert setInformativeText: NSLocalizedString( @"Free space limit will be soon reached for your hard disk storing the database. Some studies will be deleted according to the rules specified in Preferences Database window (Database Auto-Cleaning).", nil)];
            [alert setShowsSuppressionButton:YES ];
            [alert addButtonWithTitle: NSLocalizedString( @"OK", nil)];
            [alert addButtonWithTitle: NSLocalizedString( @"See Preferences", nil)];
            
            if( [alert runModal] == NSAlertSecondButtonReturn)
            {
                [[PreferencesWindowController sharedPreferencesWindowController] showWindow: self];
                [[PreferencesWindowController sharedPreferencesWindowController] setCurrentContextWithResourceName: @"OSIDatabasePreferencePanePref"];
            }
            
            if ([[alert suppressionButton] state] == NSOnState)
                [[NSUserDefaults standardUserDefaults] setBool:YES forKey: @"hideCleanForFreeSpaceLimitSoonReachedWarning"];
            
            _errorCurrentlyDisplayed = NO;
        }
    }
}

- (void) _cleanDisplayWarningAboutTryingToDeleteRecentlyAddedStudy
{
    if( _errorCurrentlyDisplayed)
        return;
    
    if([[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"] == NO)
    {
        _errorCurrentlyDisplayed = YES;
        
        NSInteger r = NSRunCriticalAlertPanel( NSLocalizedString( @"Warning - Free Space", nil), NSLocalizedString( @"The current auto-cleaning rules cannot find studies to delete. Check the parameters in Preferences Database window (Database Auto-Cleaning), or delete other files from your hard disk.", nil), NSLocalizedString( @"OK", nil), NSLocalizedString( @"See Preferences", nil), nil);
        
        if( r == NSAlertAlternateReturn)
        {
            [[PreferencesWindowController sharedPreferencesWindowController] showWindow: self];
            [[PreferencesWindowController sharedPreferencesWindowController] setCurrentContextWithResourceName: @"OSIDatabasePreferencePanePref"];
        }
        
        _errorCurrentlyDisplayed = NO;
    }
}

-(void)cleanForFreeSpaceMB:(NSInteger)freeMemoryRequested {
	if (self.isReadOnly || !self.isLocal || freeMemoryRequested <= 0)
        return;

    N2ManagedObjectContext *context = (N2ManagedObjectContext *)self.managedObjectContext;
    // Never roll back unrelated work or treat a deferred save as a durable commit.
    if (![context respondsToSelector:@selector(performAtomicChanges:error:)] ||
        context.defersSaves || context.hasChanges)
        return;

	[_cleanLock lock];
    
    NSThread* thread = [NSThread currentThread];
    [thread enterOperation];
    
	@try {
        NSDictionary* fsattrs = [[NSFileManager defaultManager] attributesOfFileSystemForPath:self.dataBaseDirPath error:NULL];
		if ([fsattrs objectForKey:NSFileSystemFreeSize] == nil) {
			NSLog(@"Error: database cleaning mechanism couldn't obtain filesystem space information for %@", self.dataBaseDirPath);
			return;
		}
        
		unsigned long long free = [[fsattrs objectForKey:NSFileSystemFreeSize] unsignedLongLongValue]/1024/1024; // megabytes

/*		if (_lastFreeSpace != free && ([NSDate timeIntervalSinceReferenceDate] - _lastFreeSpaceLogTime) > 60*10) { // not more often than every ten minutes, log about the disk's free space
			_lastFreeSpace = free;
			_lastFreeSpaceLogTime = [NSDate timeIntervalSinceReferenceDate];
			NSLog(@"Info: database free space is %ld MB", (long)free);
		}*/
		
		if (free >= freeMemoryRequested)
        {
            if( free <= freeMemoryRequested * 1.2) // 20%
            {
                if( _cleanForFreeSpaceLimitSoonReachedDisplayed == NO)
                {
                    _cleanForFreeSpaceLimitSoonReachedDisplayed = YES;
                    [self performSelectorOnMainThread:@selector(_cleanForFreeSpaceLimitSoonReachedWarning) withObject:nil waitUntilDone:NO];
                }
            }
            
			return;
		}
        
		NSLog(@"Info: cleaning for space (%lld MB available, %lld MB requested)", free, (unsigned long long)freeMemoryRequested);
		
        unsigned long long initialDelta = freeMemoryRequested - free;
        
        BOOL displayError = NO;
        NSArray *studiesDates = [self spaceCleanupCandidatesRecentlyAdded:&displayError];

        NSString* dataBaseDirPathSlashed = self.dataBaseDirPath;
        if (![dataBaseDirPathSlashed hasSuffix:@"/"])
            dataBaseDirPathSlashed = [dataBaseDirPathSlashed stringByAppendingString:@"/"];
        
        BOOL flagDeleteLinkedImages = [[NSUserDefaults standardUserDefaults] boolForKey:@"AUTOCLEANINGDELETEORIGINAL"];
        
        int deletedStudies = 0;
        
        for (NSArray* sd in studiesDates)
        {
            @autoreleasepool
            {
                { CGFloat a = initialDelta, b = freeMemoryRequested, f = free; [NSThread currentThread].progress = (a-(b-f))/a; }
                
                DicomStudy* study = [sd objectAtIndex:0];
                
                NSLog(@"Info: study [%@ - %@ - %@] is being deleted for space (added %@, last opened %@)", study.studyName, study.patientID, study.date, study.dateAdded, study.dateOpened);
                
                // list images to be deleted
                NSMutableSet* pathsToDelete = [NSMutableSet set];
                for (DicomSeries* series in [[study series] allObjects])
                    for (DicomImage* image in series.images.allObjects)
                        if (flagDeleteLinkedImages || [image.completePath hasPrefix:dataBaseDirPathSlashed])
                        {
                            NSString *path = image.completePath;
                            if (path.length) {
                                [pathsToDelete addObject:path];
                                if ([path.pathExtension isEqualToString:@"hdr"])
                                    [pathsToDelete addObject:[path.stringByDeletingPathExtension stringByAppendingPathExtension:@"img"]];
                            }
                        }
                
                // Commit the index first. Failed validation or a full/read-only SQLite
                // store must leave both the study and its original bytes intact.
                NSError *saveError = nil;
                BOOL committed = [context performAtomicChanges:^BOOL(NSError **error) {
                    for (DicomSeries *series in study.series.allObjects) {
                        for (DicomImage *image in series.images.allObjects)
                            [context deleteObject:image];
                        [context deleteObject:series];
                    }
                    [context deleteObject:study];
                    return YES;
                } error:&saveError];
                if (!committed) {
                    NSLog(@"Auto-clean stopped: study deletion could not be saved: %@", saveError);
                    break;
                }
                deletedStudies++;

                // Paths were captured before deletion invalidated the managed objects.
                // Local files are also queued by validateForDelete after successful save;
                // remove them now so the next space measurement reflects this study.
                for (NSString *path in pathsToDelete) {
                    if (unlink(path.fileSystemRepresentation) != 0 && errno != ENOENT)
                        NSLog(@"Auto-clean could not remove a committed file (errno %d)", errno);
                }

                // did we free up enough space?
                
                NSDictionary* fsattrs = [[NSFileManager defaultManager] attributesOfFileSystemForPath:self.dataBaseDirPath error:NULL];
                if (![fsattrs objectForKey:NSFileSystemFreeSize]) {
                    NSLog(@"Auto-clean stopped: filesystem free space is no longer available");
                    break;
                }
                free = [[fsattrs objectForKey:NSFileSystemFreeSize] unsignedLongLongValue]/1024/1024;
                if (free >= freeMemoryRequested) // if so, stop deleting studies
                    break;
                
                if( deletedStudies >= MAXSTUDYDELETE) // To avoid HUGE loop with very large DB
                    break;
            }
        }
        
        if( deletedStudies > 0)
        {
            // refresh database
            [NSNotificationCenter.defaultCenter postNotificationName:_O2AddToDBAnywayNotification object:self userInfo: nil];
            [NSNotificationCenter.defaultCenter postNotificationName:_O2AddToDBAnywayCompleteNotification object:self userInfo: nil];
            [NSNotificationCenter.defaultCenter postNotificationName:OsirixAddToDBNotification object:self userInfo: nil];
            [NSNotificationCenter.defaultCenter postNotificationName:OsirixAddToDBCompleteNotification object:self userInfo: nil];
        }
        
		NSLog(@"Info: done cleaning for space, %lld MB are free", free);
        
        if( displayError)
            [self performSelectorOnMainThread:@selector( _cleanDisplayWarningAboutTryingToDeleteRecentlyAddedStudy) withObject:nil waitUntilDone:NO];
        
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    } @finally {
        [thread exitOperation];
        [_cleanLock unlock];
    }
}

@end
