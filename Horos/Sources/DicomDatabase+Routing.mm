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


#import "DicomDatabase+Routing.h"
#import "DicomImage.h"
#import "QueryController.h"
#import "N2Debug.h"
#import "DCMTKStoreSCU.h"
#import "NSUserDefaults+OsiriX.h"
#import "NSThread+N2.h"
#import "DCMTKStudyQueryNode.h"
#import "ThreadsManager.h"
#import "N2Stuff.h"
#import "Horos-Swift.h"


@interface DicomDatabase (RoutingPrivate)

-(NSMutableArray*)routingSendQueues;
-(NSRecursiveLock*)routingLock;

+(void)_syncRoutingTimer;

@end

@implementation DicomDatabase (Routing)

-(void)initRouting {
    if (self.isMainDatabase) {
        _routingSendQueues = [[NSMutableArray alloc] init];
        _routingLock = [[NSRecursiveLock alloc] init];
    } else {
        _routingSendQueues = [[self.mainDatabase routingSendQueues] retain];
        _routingLock = [[self.mainDatabase routingLock] retain];
    }
    
	[DicomDatabase _syncRoutingTimer];
}

-(void)deallocRouting {
	NSRecursiveLock* temp;
	
    if (self.isMainDatabase) {
        temp = _routingLock;
        [temp lock]; // if currently routing, wait until finished
        _routingLock = nil;
        [temp unlock];
        [temp release];
    } else {
        [_routingLock release];
    }
	
	[_routingSendQueues release]; _routingSendQueues = nil;
}

-(NSMutableArray*)routingSendQueues {
    return _routingSendQueues;
}

-(NSRecursiveLock*)routingLock {
    return _routingLock;
}

+(void)_syncRoutingTimer {
	static NSTimer* routingTimer = nil;
	
	if (routingTimer)
		return;
	
	routingTimer = [[NSTimer timerWithTimeInterval:10 target:self selector:@selector(_routingTimerCallback:) userInfo:nil repeats:YES] retain];
	[[NSRunLoop mainRunLoop] addTimer:routingTimer forMode:NSModalPanelRunLoopMode];
	[[NSRunLoop mainRunLoop] addTimer:routingTimer forMode:NSDefaultRunLoopMode];
}

+(void)_routingTimerCallback:(NSTimer*)timer {
	for (DicomDatabase* dbi in [self allDatabases])
		if (dbi.isLocal)
			[dbi initiateRoutingUnlessAlreadyRouting];
}

-(void)initiateRoutingUnlessAlreadyRouting {
	if ([_routingLock tryLock])
		@try {
			[self performSelectorInBackground:@selector(_routingThread) withObject:nil];
		} @catch (NSException* e) {
			N2LogExceptionWithStackTrace(e);
		} @finally {
			[_routingLock unlock];
		}
	//else NSLog(@"Warning: couldn't initiate routing"); // who cares
}

// A rule that cannot say where a study goes. Reported the way a failed send is,
// because it is the same thing from the user's side - files that did not arrive -
// and it used to be one N2LogError line while the files were dropped.
-(void)_routingDestinationProblem:(NSString*)problem {
	NSLog( @"**** Autorouting suspended: %@", problem);
	
	if (![NSUserDefaults.standardUserDefaults boolForKey:@"ShowErrorMessagesForAutorouting"] || [NSUserDefaults.standardUserDefaults boolForKey: @"hideListenerError"]) return;
	
	NSAlert* alert = [[NSAlert new] autorelease];
	[alert setMessageText: NSLocalizedString( @"Autorouting Error", nil)];
	[alert setInformativeText: problem];
	[alert setShowsSuppressionButton: YES];
	[alert runModal];
	if ([[alert suppressionButton] state] == NSOnState)
		[[NSUserDefaults standardUserDefaults] setBool:NO forKey: @"ShowErrorMessagesForAutorouting"];
}

-(void)_routingErrorMessage:(NSDictionary*)dict {
	NSException	*ne = [dict objectForKey: @"exception"];
	NSDictionary *server = [dict objectForKey:@"server"];
	
	// Logged whether or not it is shown, so how many alerts a run would raise
	// can be counted without a screen.
	NSLog( @"**** Autorouting error reported for %@@%@:%@ - %@", [server objectForKey:@"AETitle"], [server objectForKey:@"Address"], [server objectForKey:@"Port"], [ne reason]);
	
	if (![NSUserDefaults.standardUserDefaults boolForKey:@"ShowErrorMessagesForAutorouting"] || [NSUserDefaults.standardUserDefaults boolForKey: @"hideListenerError"]) return;
	
	
	NSString	*message = [NSString stringWithFormat:@"%@\r\r%@\r%@\r\rServer:%@-%@:%@", NSLocalizedString(@"Autorouting DICOM StoreSCU operation failed.\rI will try again in 30 secs.", nil), [ne name], [ne reason], [server objectForKey:@"AETitle"], [server objectForKey:@"Address"], [server objectForKey:@"Port"]];
	
	NSAlert* alert = [[NSAlert new] autorelease];
	[alert setMessageText: NSLocalizedString(@"Autorouting Error",nil)];
	[alert setInformativeText: message];
	[alert setShowsSuppressionButton:YES];
	[alert runModal];
	if ([[alert suppressionButton] state] == NSOnState)
		[[NSUserDefaults standardUserDefaults] setBool:NO forKey: @"ShowErrorMessagesForAutorouting"];
}

-(void)_routingExecuteSend:(NSArray*)samePatientArray server:(NSDictionary*)server dictionary:(NSDictionary*)dict {
	if (!samePatientArray.count)
		return;
	
	NSLog( @" Autorouting: %@ - %@", [[samePatientArray objectAtIndex: 0] valueForKeyPath:@"series.study.studyName"], N2SingularPluralCount(samePatientArray.count, @"object", @"objects"));
	
    NSMutableDictionary* xp = [NSMutableDictionary dictionaryWithObject:[NSNumber numberWithBool:NO] forKey:@"threadStatus"];
    [xp addEntriesFromDictionary:server];
    [xp setObject:self forKey:@"DicomDatabase"];
    
	DCMTKStoreSCU* storeSCU = [[DCMTKStoreSCU alloc] initWithCallingAET: [NSUserDefaults defaultAETitle] 
															  calledAET: [server objectForKey:@"AETitle"] 
															   hostname: [server objectForKey:@"Address"] 
																   port: [[server objectForKey:@"Port"] intValue] 
															filesToSend: [samePatientArray valueForKey: @"completePath"]
														 transferSyntax: [[server objectForKey:@"TransferSyntax"] intValue] 
															compression: 1.0
														extraParameters: xp];
	
	NSString *destination = [NSString stringWithFormat: @"%@@%@:%@", [server objectForKey:@"AETitle"], [server objectForKey:@"Address"], [server objectForKey:@"Port"]];
	
	@try {
        NSThread.currentThread.supportsCancel = YES;
		[storeSCU run: nil];
		[HorosSuspendedRoutingRules clearProblemsForDestination: destination];
	} @catch (NSException *ne) {
		NSLog( @"Autorouting FAILED : %@ - %@", ne, [samePatientArray valueForKey: @"completePath"]);
		
		// A destination that is down fails every batch, and every failure used
		// to raise a modal alert on the main thread: a queue of forty batches
		// was forty alerts to dismiss before the application could be used.
		// The first is shown, the repeats are in the log above.
		if( [HorosSuspendedRoutingRules shouldReportProblem: [ne reason] forDestination: destination])
			[self performSelectorOnMainThread:@selector(_routingErrorMessage:) withObject: [NSDictionary dictionaryWithObjectsAndKeys: ne, @"exception", server, @"server", nil] waitUntilDone: NO];
		
		NSThread.currentThread.status = NSLocalizedString( @"Sending failed. Will re-try later...", nil);
		[NSThread sleepForTimeInterval: 4];
		
		// We will try again later...
		
		if ([[dict valueForKey: @"failureRetry"] intValue] > 0) {
			NSLog( @"Autorouting for %@ : failure count: %d", [[samePatientArray objectAtIndex: 0] valueForKeyPath:@"series.study.name"], [[dict valueForKey: @"failureRetry"] intValue]);
			@synchronized (_routingSendQueues) {
				[_routingSendQueues addObject: [NSDictionary dictionaryWithObjectsAndKeys: 
                                                [NSMutableArray arrayWithArray:[samePatientArray valueForKey:@"objectID"]], @"objectIDs",
                                                [server objectForKey:@"Description"], @"server", 
                                                [dict valueForKey:@"routingRule"], @"routingRule", 
                                                [NSNumber numberWithInt: [[dict valueForKey:@"failureRetry"] intValue]-1], @"failureRetry", nil]];
			}
		}
	}
	
	[storeSCU release];
	storeSCU = nil;
}

-(void)_routingThread
{
	NSAutoreleasePool* pool = [NSAutoreleasePool new];
	@try
    {
        BOOL isQueueEmpty = YES;
        @synchronized (_routingSendQueues)
        {
			if( _routingSendQueues.count)
                isQueueEmpty = NO;
        }
        
        if( isQueueEmpty == NO)
        {
            NSThread* thread = [NSThread currentThread];
            thread.name = NSLocalizedString(@"Routing...", nil);
            [self.independentDatabase routing];
        }
	}
    @catch (NSException * e)
    {
		N2LogExceptionWithStackTrace(e);
	}
    @finally
    {
		[pool release];
	}
}

-(void)routing {
	[_routingLock lock];
	@try {
		NSThread* thread = [NSThread currentThread];
		
		NSArray* serversArray = [[NSUserDefaults standardUserDefaults] arrayForKey:@"SERVERS"];
		
		NSArray* routingSendQueues = nil;
		@synchronized (_routingSendQueues) {
			routingSendQueues = [[_routingSendQueues copy] autorelease];
			[_routingSendQueues removeAllObjects];
		}
		
		if (routingSendQueues.count) {
			[ThreadsManager.defaultManager addThreadAndStart:thread];
			
			NSInteger total = 0;
			for (NSDictionary *copy in routingSendQueues)
				if( [[HorosRoutingDestination destinationNamed: [copy objectForKey:@"server"]
													inServers: serversArray
													 ruleName: [[copy objectForKey:@"routingRule"] valueForKey:@"name"]] resolved])
					total += [[copy objectForKey:@"objectIDs"] count];
            
            NSLog(@"______________________________________________");
			NSLog(@" Autorouting Queue START: %@, %@", N2SingularPluralCount(routingSendQueues.count, @"list", @"lists"), N2SingularPluralCount(total, @"item", @"items"));
			for (NSDictionary *copy in routingSendQueues)
				NSLog(@"   list: rule \"%@\" -> %@, %d item(s)",
                      [[copy objectForKey:@"routingRule"] valueForKey:@"name"],
                      [copy objectForKey:@"server"],
                      (int) [[copy objectForKey:@"objectIDs"] count]);
			
			NSInteger sent = 0;
			for (NSDictionary* copy in routingSendQueues) {
				NSArray* objectIDs = [copy objectForKey:@"objectIDs"];
                NSArray* objectsToSend = [self objectsWithIDs:objectIDs];
                
                // A row that has gone from the database between queueing and
                // sending. Silently sending fewer images than were queued is
                // exactly how "only part of the study reached the PACS" looks.
                if( objectsToSend.count != objectIDs.count)
                    NSLog( @" Autorouting: %d of %d queued image(s) are no longer in the database",
                          (int) (objectIDs.count - objectsToSend.count), (int) objectIDs.count);
				
				[thread enterOperationWithRange:1.0*sent/total:1.0*objectsToSend.count/total];
				sent += objectsToSend.count;
				
				NSString* serverName = [copy objectForKey:@"server"];
				thread.status = [NSString stringWithFormat:NSLocalizedString(@"Forwarding %@ to %@", nil), N2LocalizedSingularPluralCount(objectsToSend.count, NSLocalizedString(@"file", nil), NSLocalizedString(@"files", nil)), serverName];
				
				NSString* ruleName = [[copy objectForKey:@"routingRule"] valueForKey:@"name"];
				HorosRoutingDestination* destination = [HorosRoutingDestination destinationNamed: serverName
																					  inServers: serversArray
																					   ruleName: ruleName];
				NSDictionary* server = destination.server;
				
				if( server)
				{
					NSLog(@" Autorouting destination: %@ - %@", [server objectForKey:@"Description"], [server objectForKey:@"Address"]);
					[HorosSuspendedRoutingRules resumeRule: ruleName];
				}
				else if( [HorosSuspendedRoutingRules suspendRule: ruleName because: destination.problem])
				{
					// Only the first time: the same unanswerable question is
					// asked again on every import until the nodes are fixed.
					[self performSelectorOnMainThread: @selector(_routingDestinationProblem:) withObject: destination.problem waitUntilDone: NO];
				}
				
				if (server) {
					@try {
						NSSortDescriptor	*sort = [[[NSSortDescriptor alloc] initWithKey:@"series.study.patientID" ascending:YES] autorelease];
						NSArray				*sortDescriptors = [NSArray arrayWithObject: sort];
						
						objectsToSend = [objectsToSend sortedArrayUsingDescriptors: sortDescriptors];
						
						NSString			*previousPatientUID = nil;
						NSMutableArray		*samePatientArray = [NSMutableArray arrayWithCapacity: [objectsToSend count]];
						NSInteger			missingFiles = 0;
						
						for( NSManagedObject *objectToSend in objectsToSend)
						{
							@try
							{
								if( [[NSFileManager defaultManager] fileExistsAtPath: [objectToSend valueForKey: @"completePath"]] == NO)
								{
									// The database row is there and the file is
									// not. Nothing said so before, and this is
									// what a partial delivery looks like from
									// the receiving end.
									missingFiles++;
									if( missingFiles <= 10)
										NSLog( @" Autorouting: not sending %@ - the file is not there",
											  [objectToSend valueForKey: @"completePath"]);
								}
								else
								{
									if( previousPatientUID && [previousPatientUID isEqualToString: [objectToSend valueForKeyPath:@"series.study.patientID"]])
									{
										[samePatientArray addObject: objectToSend];
									}
									else
									{
										// Send the collected files from the same patient
										
										if( [samePatientArray count]) [self _routingExecuteSend: samePatientArray server: server dictionary: copy];
										
										// Reset
										[samePatientArray removeAllObjects];
										[samePatientArray addObject: objectToSend];
										
										previousPatientUID = [objectToSend valueForKeyPath:@"series.study.patientID"];
									}
								}
							}
							@catch( NSException *ne)
							{
								NSLog( @"----- Autorouting Prepare exception: %@", ne);
							}
						}
						
						if (samePatientArray.count)
							[self _routingExecuteSend:samePatientArray server:server dictionary:copy];
						
						if( missingFiles)
							NSLog( @" Autorouting: %d of %d image(s) were not sent because their files are not there",
								  (int) missingFiles, (int) objectsToSend.count);
					} @catch (NSException* e) {
						N2LogExceptionWithStackTrace(e);
					}
				} else {
					N2LogError(@"Autorouting destination unresolved: %@", destination.problem);
				}
				
				[thread exitOperation];
				
				if (thread.isCancelled)
					break;
			}
			
			NSLog(@"______________________________________________");
		}
		
	} @catch (NSException* e) {
		N2LogExceptionWithStackTrace(e);
	} @finally {
		[_routingLock unlock];
	}
}

-(void)addImages:(NSArray*)_dicomImages toSendQueueForRoutingRule:(NSDictionary*)routingRule {
	@synchronized (_routingSendQueues) {
		NSMutableArray* dicomImages = [NSMutableArray arrayWithArray:_dicomImages];
		
		// are these images already in the queue, with same routingRule ?
		for (NSDictionary* order in _routingSendQueues)
			if ([routingRule isEqualToDictionary:[order valueForKey:@"routingRule"]]) {
                NSMutableArray* orderObjectIDs = [order valueForKey:@"objectIDs"];
                
				NSArray* orderFilePaths = [[self objectsWithIDs:orderObjectIDs] valueForKey:@"completePath"];
				
				// are the files already in queue for same filter?
				for (NSInteger i = (long)dicomImages.count-1; i >= 0; --i) {
                    DicomImage* image = [dicomImages objectAtIndex:i];
					if ([orderFilePaths containsObject:[image completePath]])
						[dicomImages removeObject:image];
				}
                
				[orderObjectIDs addObjectsFromArray:[dicomImages valueForKey:@"objectID"]];
                
				[dicomImages removeAllObjects];
			}
		
		if (dicomImages.count < _dicomImages.count)
			NSLog( @" Autorouting rule \"%@\": %d image(s) already queued for it, not queued again",
                  [routingRule valueForKey: @"name"], (int) (_dicomImages.count - dicomImages.count));
		
		if (dicomImages.count)
			[_routingSendQueues addObject:[NSDictionary dictionaryWithObjectsAndKeys:
                                           [NSMutableArray arrayWithArray:[dicomImages valueForKey:@"objectID"]], @"objectIDs",
                                           [routingRule objectForKey:@"server"], @"server", 
                                           routingRule, @"routingRule", 
                                           [routingRule valueForKey:@"failureRetry"], @"failureRetry", nil]];
	}
}


-(void) __applyRoutingRules:(NSArray*)autoroutingRules toImages:(NSArray*)newImagesOriginal
{
#ifndef OSIRIX_LIGHT
    if (!autoroutingRules)
        autoroutingRules = [[NSUserDefaults standardUserDefaults] arrayForKey:@"AUTOROUTINGDICTIONARY"];
    
    for (NSDictionary* routingRule in autoroutingRules)
        if (![routingRule valueForKey:@"activated"] || [[routingRule valueForKey:@"activated"] boolValue])
        {
            NSPredicate	*predicate = nil;
            NSArray *newImages = nil;
            
            @try {
                
                NSString *filter = [routingRule objectForKey: @"filter"];
                
                BOOL imagesOnly = [[routingRule objectForKey: @"imagesOnly"] boolValue];
                
                if( [[routingRule valueForKey: @"version"] intValue] < 1 && [[routingRule valueForKey: @"filterType"] intValue] != 0)
                    filter = @"";
                
                predicate = [DicomDatabase predicateForSmartAlbumFilter: filter];
                
                switch( [[routingRule objectForKey: @"filterType"] intValue])
                {
                    case 0:
                        // all images !
                        break;
                        
                    case 1:
                        predicate = [NSCompoundPredicate andPredicateWithSubpredicates: [NSArray arrayWithObjects: [NSPredicate predicateWithFormat:@"generatedByOsiriX == YES"], predicate, nil]];
                        break;
                        
                    case 2:
                        predicate = [NSCompoundPredicate andPredicateWithSubpredicates: [NSArray arrayWithObjects: [NSPredicate predicateWithFormat:@"importedFile == YES"], predicate, nil]];
                        break;
                }
                
                if( predicate)
                    newImages = [newImagesOriginal filteredArrayUsingPredicate:predicate];
                else
                    newImages = newImagesOriginal;
                
                if( imagesOnly)
                {
                    NSMutableArray *imagesOnlyArray = [NSMutableArray array];
                    
                    for( DicomImage *i in newImages)
                    {
                        if( i.isImageStorage.boolValue)
                            [imagesOnlyArray addObject: i];
                    }
                    
                    newImages = imagesOnlyArray;
                }
                
                if (newImages.count)
                {
                    if ([[routingRule valueForKey:@"previousStudies"] intValue] > 0)
                    {
                        NSDictionary *server = [HorosRoutingDestination destinationNamed: routingRule[@"server"]
                            inServers: [[NSUserDefaults standardUserDefaults] arrayForKey:@"SERVERS"] ?: @[]
                            ruleName: routingRule[@"name"]].server;
                        NSMutableArray *expanded = [NSMutableArray arrayWithArray:newImages];
                        NSSet *currentStudies = [NSSet setWithArray:[newImages valueForKeyPath:@"series.study"]];
                        NSMutableSet *selectedStudies = [NSMutableSet set];
                        for (id study in currentStudies)
                        {
                            NSString *patient = [study valueForKey:@"patientUID"];
                            if (!server || !patient.length) continue;
                            NSArray *candidates = [self objectsForEntity:self.studyEntity
                                predicate:[NSPredicate predicateWithFormat:@"patientUID == %@", patient]];
                            candidates = [candidates sortedArrayUsingDescriptors:@[
                                [NSSortDescriptor sortDescriptorWithKey:@"date" ascending:NO],
                                [NSSortDescriptor sortDescriptorWithKey:@"studyInstanceUID" ascending:YES]]];
                            NSInteger remaining = [routingRule[@"previousStudies"] integerValue];
                            NSDictionary *current = [study dictionaryWithValuesForKeys:@[@"date", @"modality", @"studyName"]];
                            for (id prior in candidates)
                            {
                                if ([currentStudies containsObject:prior]) continue;
                                if (![HorosPreviousRoutingStudies matchesStudy:
                                    [prior dictionaryWithValuesForKeys:@[@"date", @"modality", @"studyName"]]
                                    currentStudy:current modality:[routingRule[@"previousModality"] boolValue]
                                    description:[routingRule[@"previousDescription"] boolValue]]) continue;
                                if (remaining-- <= 0) break;
                                if ([selectedStudies containsObject:prior]) continue;
                                [selectedStudies addObject:prior];
                                NSMutableArray *priorImages = [NSMutableArray array];
                                for (id series in [prior valueForKey:@"series"])
                                    for (DicomImage *image in [series valueForKey:@"images"])
                                        if (!imagesOnly || image.isImageStorage.boolValue) [priorImages addObject:image];
                                if (priorImages.count && [HorosPreviousRoutingStudies reserveStudy:
                                    [prior valueForKey:@"studyInstanceUID"] ?: @"" server:server databasePath:self.dataBaseDirPath])
                                    [expanded addObjectsFromArray:priorImages];
                            }
                        }
                        newImages = expanded;
                    }
                    
                    if( [[routingRule valueForKey:@"cfindTest"] boolValue])
                    {
                        NSMutableDictionary *studies = [NSMutableDictionary dictionary];
                        
                        for( id im in newImages)
                        {
                            if( [studies objectForKey: [im valueForKeyPath:@"series.study.studyInstanceUID"]] == nil)
                                [studies setObject: [im valueForKeyPath:@"series.study"] forKey: [im valueForKeyPath:@"series.study.studyInstanceUID"]];
                        }
                        
                        for( NSString *studyUID in [studies allKeys])
                        {
                            NSArray *serversArray = [[NSUserDefaults standardUserDefaults] arrayForKey: @"SERVERS"];
                            
                            NSString		*serverName = [routingRule objectForKey:@"server"];
                            NSDictionary	*server = nil;
                            
                            for( NSDictionary *aServer in serversArray)
                            {
                                if( [[aServer objectForKey:@"Activated"] boolValue] && [[aServer objectForKey:@"Description"] isEqualToString: serverName])
                                {
                                    server = aServer;
                                    break;
                                }
                            }
                            
                            if( server)
                            {
                                NSArray *s = [QueryController queryStudyInstanceUID: studyUID server: server showErrors: NO];
                                
                                if( [s count])
                                {
                                    if( [s count] > 1)
                                        NSLog( @"Uh? multiple studies with same StudyInstanceUID on the distal node....");
                                    
                                    DCMTKStudyQueryNode* studyNode = [s lastObject];
                                    
                                    if( [[studyNode valueForKey:@"numberImages"] intValue] >= [[[studies objectForKey: studyUID] valueForKey: @"noFiles"] intValue])
                                    {
                                        // remove them, there are already there ! *probably*
                                        
                                        NSLog( @"Already available on the distant node : we will not send it.");
                                        
                                        NSMutableArray *r = [NSMutableArray arrayWithArray: newImages];
                                        
                                        for( int i = 0 ; i < [r count] ; i++)
                                        {
                                            if( [[[r objectAtIndex: i] valueForKeyPath: @"series.study.studyInstanceUID"] isEqualToString: studyUID])
                                            {
                                                [r removeObjectAtIndex: i];
                                                i--;
                                            }
                                        }
                                        
                                        newImages = r;
                                    }
                                }
                            }
                        }
                    }
                }
            } @catch (NSException* e) {
                N2LogExceptionWithStackTrace(e);
                newImages = nil;
            }
            
            // Which rule queued which images, so a send that surprises someone
            // can be traced to the rule that asked for it.
            NSLog( @" Autorouting rule \"%@\" -> %@: %d of %d image(s) matched%@",
                  [routingRule valueForKey: @"name"],
                  [routingRule objectForKey: @"server"],
                  (int) [newImages count], (int) [newImagesOriginal count],
                  [[routingRule objectForKey: @"filter"] length] ? [NSString stringWithFormat: @", filter: %@", [routingRule objectForKey: @"filter"]] : @"");
            
            if ([newImages count])
                [self addImages:newImages toSendQueueForRoutingRule:routingRule];
        }
    
#endif
}


-(void)applyRoutingRules:(NSArray*)autoroutingRules toImages:(NSArray*)newImagesOriginal
{
    if (!autoroutingRules)
    {
        autoroutingRules = [[NSUserDefaults standardUserDefaults] arrayForKey:@"AUTOROUTINGDICTIONARY"];
    }
    
    // Each rule is applied once, and a scheduled one is applied by itself when
    // its time comes. This loop used to call -__applyRoutingRules: with the
    // whole list once per activated rule, so N rules applied every rule N
    // times, and a rule with a schedule applied every other rule again when its
    // delay elapsed. The send queue's own de-duplication hid it only while the
    // earlier copy was still in the queue, and the routing timer drains that
    // every 10 seconds - after which the same images are queued and sent again.
    for (NSDictionary* routingRule in [HorosRoutingSchedule scheduledRulesIn: autoroutingRules])
    {
        {
            NSArray* thisRule = [NSArray arrayWithObject: routingRule];
            
            {
                if ([[routingRule valueForKey:@"scheduleType"] intValue] == 1)
                {
                    int64_t delayInSeconds = 3600 * [[routingRule valueForKey:@"delayTime"] integerValue];
                    dispatch_time_t popTime = dispatch_time(DISPATCH_TIME_NOW, delayInSeconds * NSEC_PER_SEC);
                    dispatch_after(popTime, dispatch_get_main_queue(),^{
                        [self __applyRoutingRules:thisRule toImages:newImagesOriginal];
                    });
                }
                else if ([[routingRule valueForKey:@"scheduleType"] intValue] == 2 &&
                         [routingRule valueForKey:@"fromTime"] &&
                         [routingRule valueForKey:@"toTime"])
                {
                    NSDateFormatter *dateFormatter = [[[NSDateFormatter alloc] init] autorelease];
                    //[dateFormatter setDefaultDate:[NSDate date]];
                    [dateFormatter setDateFormat: @"EEEE, dd MMMM yyyy HH:mm:ss zzzzzzzzz"];
                    
                    NSString* fromTimeString = [routingRule valueForKey:@"fromTime"];
                    //NSLog(@"fromTimeString = %@", fromTimeString);
                    NSDate* fromTime = [dateFormatter dateFromString:fromTimeString];
                    //  throwing out the year information (in fact, it is coming with 31 Dec 1969...)
                    [dateFormatter setDateFormat: @"HH:mm:ss"];
                    NSString *fromTimeString_justHHmm = [dateFormatter stringFromDate:fromTime];
                    //NSLog(@"fromTimeString_justHHmm = %@", fromTimeString_justHHmm);
                    fromTime = [dateFormatter dateFromString:fromTimeString_justHHmm];
                    
                    [dateFormatter setDateFormat: @"EEEE, dd MMMM yyyy HH:mm:ss zzzzzzzzz"];
                    
                    NSString* toTimeString = [routingRule valueForKey:@"toTime"];
                    //NSLog(@"toTimeString = %@", toTimeString);
                    NSDate* toTime = [dateFormatter dateFromString:toTimeString];
                    //  throwing out the year information (in fact, it is coming with 31 Dec 1969...)
                    [dateFormatter setDateFormat: @"HH:mm:ss"];
                    NSString *toTimeString_justHHmm = [dateFormatter stringFromDate:toTime];
                    //NSLog(@"toTimeString_justHHmm = %@", toTimeString_justHHmm);
                    toTime = [dateFormatter dateFromString:toTimeString_justHHmm];
                    
                    NSCalendar *calendar = [NSCalendar currentCalendar];
                    NSDateComponents *components = [calendar components:(NSHourCalendarUnit | NSMinuteCalendarUnit | NSSecondCalendarUnit) fromDate:[NSDate date]];
                    NSInteger currentHour = [components hour];
                    NSInteger currentMinute = [components minute];
                    NSInteger currentSecond = [components second];
                    NSDate* currentTime = [dateFormatter dateFromString:[NSString stringWithFormat:@"%2ld:%2ld:%2ld",currentHour,currentMinute,currentSecond]];
                    //NSLog(@"currentTime = %@", [dateFormatter stringFromDate:currentTime]);
                    
                    int64_t delayInSeconds = 0;

                    //  fromTime to toTime crosses a day
                    if ([toTime timeIntervalSinceDate:fromTime] < 0)
                    {
                        [toTime dateByAddingTimeInterval:60*60*24*1]; //Add 1 day to "toTime"
                    }
                    
                    //  Autorouting time interval is ahead. Let's schedule
                    if ([currentTime timeIntervalSinceDate:fromTime] <= 0)
                    {
                        delayInSeconds = fabs([fromTime timeIntervalSinceDate:currentTime]);
                        //NSLog(@"We are ahead of time. delayInSeconds = %lld", delayInSeconds);
                    }
                    else
                    {
                        //  We are inside the interval. Let's route immediately
                        if ([currentTime timeIntervalSinceDate:toTime] <= 0)
                        {
                            delayInSeconds = (long long) 0;
                        }
                        else    //  Autorouting time interval already passed. Let's schedule for tomorrow
                        {
                            //Add 1 day
                            delayInSeconds = (long long) fabs([fromTime timeIntervalSinceDate:currentTime]) + 60*60*24*1;
                            //NSLog(@"Time passed. Tomorrow we autoroute. delayInSeconds = %lld", delayInSeconds);
                        }
                    }
                    
                    dispatch_time_t popTime = dispatch_time(DISPATCH_TIME_NOW, delayInSeconds * NSEC_PER_SEC);
                    dispatch_after(popTime, dispatch_get_main_queue(),^{
                        [self __applyRoutingRules:thisRule toImages:newImagesOriginal];
                    });
                }
            }
        }
    }
    
    NSArray* immediate = [HorosRoutingSchedule immediateRulesIn: autoroutingRules];
    if (immediate.count)
        [self __applyRoutingRules:immediate toImages:newImagesOriginal];
}

@end
