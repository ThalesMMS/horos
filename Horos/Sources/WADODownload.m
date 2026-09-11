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

#include "HorosDICOMGlobalAbort.h"
#import "WADODownload.h"
#import "BrowserController.h"
#import "DicomDatabase.h"
#import "NSThread+N2.h"
#include <libkern/OSAtomic.h>
#import "DicomFile.h"
#import "LogManager.h"
#import "N2Debug.h"
#import "NSString+N2.h"
#import "Horos-Swift.h"

@interface NSURLRequest (DummyInterface)
+ (BOOL)allowsAnyHTTPSCertificateForHost:(NSString*)host;
+ (void)setAllowsAnyHTTPSCertificate:(BOOL)allow forHost:(NSString*)host;
@end

@implementation WADODownload

@synthesize _abortAssociation, showErrorMessage, countOfSuccesses, WADOGrandTotal, WADOBaseTotal, baseStatus, receivedData, totalData;
@synthesize manifest;

+ (void) errorMessage:(NSArray*) msg
{
    NSString *alertSuppress = @"hideListenerError";
    
    if ([[NSUserDefaults standardUserDefaults] boolForKey: alertSuppress] == NO)
        NSRunCriticalAlertPanel( [msg objectAtIndex: 0], @"%@", [msg objectAtIndex: 2], nil, nil, [msg objectAtIndex: 1]) ;
    else
        NSLog( @"*** listener error (not displayed - hideListenerError): %@ %@ %@", [msg objectAtIndex: 0], [msg objectAtIndex: 1], [msg objectAtIndex: 2]);
}

- (void)connection:(NSURLConnection *)connection didReceiveResponse:(NSURLResponse *)response
{
	NSHTTPURLResponse *httpResponse = (NSHTTPURLResponse *)response;
	
	if( [httpResponse statusCode] >= 300)
	{
		NSLog( @"***** WADO http status code error: %d", (int) [httpResponse statusCode]);
		NSLog( @"***** WADO URL : %@", response.URL);
		
        // The alert waits for the end of the retrieval, where the manifest can
        // say how many instances are missing instead of repeating the status of
        // whichever one failed first.
        if( response.URL)
            [manifest recordFailureForURL: response.URL
                               statusCode: [httpResponse statusCode]
                                   reason: [NSString stringWithFormat: @"HTTP %d", (int) [httpResponse statusCode]]];
		
		[WADODownloadDictionary removeObjectForKey: [NSString stringWithFormat:@"%ld", (long) connection]];
	}
    else
        totalData += [[httpResponse.allHeaderFields valueForKey: @"Content-Length"] longLongValue];
}

- (void)connection:(NSURLConnection *)connection didReceiveData:(NSData *)data
{
	if( connection)
	{
		NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
		
		NSMutableData *d = [[WADODownloadDictionary objectForKey: [NSString stringWithFormat:@"%ld", (long) connection]] objectForKey: @"data"];
		[d appendData: data];
		
        receivedData += data.length;
        
        if( WADOTotal == 1) // Only one file: display progress in bytes
        {
            if( totalData > 0)
                [[NSThread currentThread] setProgress: (double) receivedData / (double) totalData];
            
            if( firstReceivedTime == 0)
                firstReceivedTime = [NSDate timeIntervalSinceReferenceDate];
            
            if( [NSDate timeIntervalSinceReferenceDate] - lastStatusUpdate > 1 && [NSDate timeIntervalSinceReferenceDate] - firstReceivedTime > 2)
            {
                lastStatusUpdate = [NSDate timeIntervalSinceReferenceDate];
                [NSThread currentThread].status = [NSString stringWithFormat: @"%@ - %@/s", self.baseStatus, [NSString sizeString: (double) receivedData / ([NSDate timeIntervalSinceReferenceDate] - firstReceivedTime)]];
            }
        }
        
		[pool release];
	}
}

- (void)connection:(NSURLConnection *)connection didFailWithError:(NSError *)error
{
	if( connection)
	{
		NSString *key = [NSString stringWithFormat:@"%ld", (long) connection];
		NSURL *url = [[WADODownloadDictionary objectForKey: key] objectForKey: @"url"];
		[WADODownloadDictionary removeObjectForKey: key];
		
		NSLog(@"***** WADO Retrieve error: %@", error);
		
        // No status: the request never got one. That is worth asking again.
        if( url)
            [manifest recordFailureForURL: url statusCode: 0 reason: [error localizedDescription]];
		
		WADOThreads--;
        
        int error = [[logEntry valueForKey: @"logNumberError"] intValue];
        error++;
        [logEntry setValue:[NSNumber numberWithInt: error] forKey:@"logNumberError"];
	}
    else
        N2LogStackTrace( @"connection == nil");
}

- (NSCachedURLResponse *)connection:(NSURLConnection *)connection willCacheResponse:(NSCachedURLResponse *)cachedResponse
{
	//We dont want to store the images in the cache! Caches/BUNDLE_IDENTIFIER/Cache.db
	return nil;
}

- (id) init
{
	self = [super init];
	
	showErrorMessage = YES;
	
    [[NSURLCache sharedURLCache] setDiskCapacity: 0];
    [[NSURLCache sharedURLCache] setMemoryCapacity: 0];
    
#ifdef NONETWORKFUNCTIONS
    return nil;
#endif

	return self;
}

- (void) dealloc
{
    self.baseStatus = nil;
    
    [WADODownloadDictionary release];
    WADODownloadDictionary = nil;
    
    [logEntry release];
    logEntry = nil;
    
    [super dealloc];
}

- (void)connectionDidFinishLoading:(NSURLConnection *)connection
{
	if( connection)
	{
		NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
        
		NSString *path = [[DicomDatabase activeLocalDatabase] incomingDirPath];
        
		NSString *key = [NSString stringWithFormat:@"%ld", (long) connection];
        
		NSMutableData *d = [[WADODownloadDictionary objectForKey: key] objectForKey: @"data"];
		
		NSString *extension = @"dcm";
		
		if( [d length] > 2)
		{
            NSURL *downloaded = [[WADODownloadDictionary objectForKey: key] objectForKey: @"url"];
            
			if( [[[[NSString alloc] initWithBytes:d.bytes length:2 encoding:NSUTF8StringEncoding] autorelease] isEqualToString: @"PK"])
				extension = @"osirixzip";
            
            // The name has to be unique across every file this process leaves in
            // the incoming directory. It used to be the remaining-thread count
            // and the object pointer, and the count restarts on every call:
            // -WADORetrieve: calls this object again for each batch of more than
            // 50 instances, so a batch overwrote files an earlier one had
            // written and the importer had not yet moved away. That is instances
            // downloaded and then lost, without a word anywhere.
            NSString *filename = [[@".WADO-" stringByAppendingString: [[NSUUID UUID] UUIDString]] stringByAppendingPathExtension: extension];
        
            [d writeToFile: [path stringByAppendingPathComponent: filename] atomically: YES];
            
            // A WADO endpoint behind a proxy answers 200 with a login page
            // often enough to be worth one check, and an empty or tiny reply
            // costs nothing to spot: a body with no DICOM magic is not a
            // received instance, whatever the status said. The check is the
            // magic and not a parse, because a parse of every downloaded file
            // would cost more than it saves; a body truncated after the magic
            // still gets through here and is caught by the importer.
            BOOL looksLikeDICOM = NO;
            if( d.length > 132)
                looksLikeDICOM = (strncmp( (const char*) d.bytes + 128, "DICM", 4) == 0);
            
            if( [extension isEqualToString: @"dcm"] && looksLikeDICOM == NO)
            {
                NSLog( @"***** WADO: what arrived is not a DICOM object (%d bytes): %@", (int) d.length, downloaded);
                [[NSFileManager defaultManager] removeItemAtPath: [path stringByAppendingPathComponent: filename] error: nil];
                if( downloaded)
                    [manifest recordFailureForURL: downloaded statusCode: 0 reason: [NSString stringWithFormat: @"what arrived is not a DICOM object (%d bytes)", (int) d.length]];
                
                [d setLength: 0];
                [WADODownloadDictionary removeObjectForKey: key];
                WADOThreads--;
                [pool release];
                return;
            }
            
            countOfSuccesses++;
            if( downloaded)
                [manifest recordSuccessForURL: downloaded];
            
            if( WADOThreads == WADOTotal) // The first file !
            {
                [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
                
                @try
                {
                    if (!logEntry && [DicomFile isDICOMFile: [path stringByAppendingPathComponent: filename]])
                    {
                        DicomFile *dcmFile = [[DicomFile alloc] init: [path stringByAppendingPathComponent: filename]];
                        
                        @try
                        {
                            logEntry = [[NSMutableDictionary dictionary] retain];
                            
                            [logEntry setValue: [NSString stringWithFormat: @"%lf", [[NSDate date] timeIntervalSince1970]] forKey:@"logUID"];
                            [logEntry setValue: [NSDate date] forKey:@"logStartTime"];
                            [logEntry setValue: @"Receive" forKey:@"logType"];
                            [logEntry setValue: [[[WADODownloadDictionary objectForKey: key] objectForKey: @"url"] host] forKey:@"logCallingAET"];
                            
                            if ([dcmFile elementForKey: @"patientName"])
                                [logEntry setValue: [dcmFile elementForKey: @"patientName"] forKey: @"logPatientName"];
                            
                            if ([dcmFile elementForKey: @"studyDescription"])
                                [logEntry setValue:[dcmFile elementForKey: @"studyDescription"] forKey:@"logStudyDescription"];
                            
                            [logEntry setValue:[NSNumber numberWithInt: WADOTotal] forKey:@"logNumberTotal"];
                        }
                        @catch (NSException *e) {
                            N2LogException( e);
                        }
                        [dcmFile release];
                    }
                }
                @catch (NSException *exception) {
                    N2LogException( exception);
                }
            }
            
            [logEntry setValue:[NSNumber numberWithInt: 1 + WADOTotal - WADOThreads] forKey:@"logNumberReceived"];
            
            [logEntry setValue:[NSDate date] forKey:@"logEndTime"];
            [logEntry setValue:@"In Progress" forKey:@"logMessage"];
            
            [[LogManager currentLogManager] addLogLine: logEntry];
            
            if( WADOGrandTotal)
                [[NSThread currentThread] setProgress: (float) ((WADOTotal - WADOThreads) + WADOBaseTotal) / (float) WADOGrandTotal];
            else if( WADOTotal)
                [[NSThread currentThread] setProgress: 1.0 - (float) WADOThreads / (float) WADOTotal];
            
            // To remove the '.'
            [[NSFileManager defaultManager] moveItemAtPath: [path stringByAppendingPathComponent: filename] toPath: [path stringByAppendingPathComponent: [filename substringFromIndex: 1]] error: nil];
        }
        
		[d setLength: 0]; // Free the memory immediately
		[WADODownloadDictionary removeObjectForKey: key];
		
		WADOThreads--;
		
		[pool release];
	}
    else
        N2LogStackTrace( @"connection == nil");
}

// One pass over a list of URLs. Returns NO when it gave up early - aborted,
// cancelled or timed out - because a pass that did not finish is not evidence
// that the instances it did not reach are missing.
- (BOOL) WADODownloadPass: (NSArray*) urlToDownload
{
    if( urlToDownload.count == 0)
    {
        NSLog( @"**** urlToDownload.count == 0 in WADODownload");
        return YES;
    }
    
    NSMutableArray *connectionsArray = [NSMutableArray array];
    
    NSAutoreleasePool *pool = [NSAutoreleasePool new];
    
    self.baseStatus = [[NSThread currentThread] status];
    
    @try
    {
        if( [urlToDownload count])
            urlToDownload = [[NSSet setWithArray: urlToDownload] allObjects]; // UNIQUE OBJECTS !
        
        if( [urlToDownload count])
        {
            NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
#ifndef NDEBUG
            NSLog( @"------ WADO downloading : %d files", (int) [urlToDownload count]);
#endif
            [WADODownloadDictionary release];
            WADODownloadDictionary = [[NSMutableDictionary dictionary] retain];
            
            int WADOMaximumConcurrentDownloads = [[NSUserDefaults standardUserDefaults] integerForKey: @"WADOMaximumConcurrentDownloads"];
            if( WADOMaximumConcurrentDownloads < 1)
                WADOMaximumConcurrentDownloads = 1;
            
            float timeout = [[NSUserDefaults standardUserDefaults] floatForKey: @"WADOTimeout"];
            if( timeout < 240) timeout = 240;
            
#ifndef NDEBUG
            NSLog( @"------ WADO parameters: timeout:%2.2f [secs] / WADOMaximumConcurrentDownloads:%d [URLRequests]", timeout, WADOMaximumConcurrentDownloads);
#endif
            const int passStart = countOfSuccesses; // successes accumulate across passes
            WADOTotal = WADOThreads = [urlToDownload count];
            
            NSTimeInterval retrieveStartingDate = [NSDate timeIntervalSinceReferenceDate];
            
            BOOL aborted = NO;
            for( NSURL *url in urlToDownload)
            {
                while( [WADODownloadDictionary count] >= WADOMaximumConcurrentDownloads) //Dont download more than XXX images at the same time
                {
                    [[NSRunLoop currentRunLoop] runUntilDate: [NSDate dateWithTimeIntervalSinceNow: 0.1]];
                    
                    if( _abortAssociation || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested() || [NSDate timeIntervalSinceReferenceDate] - retrieveStartingDate > timeout)
                    {
                        aborted = YES;
                        break;
                    }
                }
                if (aborted || _abortAssociation || NSThread.currentThread.isCancelled) { aborted = YES; break; }
                retrieveStartingDate = [NSDate timeIntervalSinceReferenceDate];
                
                @try
                {
                    if( [[url scheme] isEqualToString: @"https"])
                        [NSURLRequest setAllowsAnyHTTPSCertificate:YES forHost:[url host]];
                }
                @catch (NSException *e)
                {
                    NSLog( @"***** exception in %s: %@", __PRETTY_FUNCTION__, e);
                }
                
                NSURLConnection *downloadConnection = [NSURLConnection connectionWithRequest: [NSURLRequest requestWithURL: url cachePolicy: NSURLRequestReloadIgnoringLocalCacheData timeoutInterval: timeout] delegate: self];
                
                if( downloadConnection)
                {
                    [WADODownloadDictionary setObject: [NSDictionary dictionaryWithObjectsAndKeys: url, @"url", [NSMutableData data], @"data", nil] forKey: [NSString stringWithFormat:@"%ld", (long) downloadConnection]];
                    [downloadConnection start];
                    [connectionsArray addObject: downloadConnection];
                }
                
                if( downloadConnection == nil)
                    WADOThreads--;
                
                if( _abortAssociation || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested() || [NSDate timeIntervalSinceReferenceDate] - retrieveStartingDate > timeout)
                {
                    aborted = YES;
                    break;
                }
            }
            
            if( aborted == NO)
            {
                while( WADOThreads > 0)
                {
                    [[NSRunLoop currentRunLoop] runUntilDate: [NSDate dateWithTimeIntervalSinceNow: 0.1]];
                    
                    if( _abortAssociation || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested()  || [NSDate timeIntervalSinceReferenceDate] - retrieveStartingDate > timeout)
                    {
                        aborted = YES;
                        break;
                    }
                }
                
                if( aborted == NO && [[WADODownloadDictionary allKeys] count] > 0)
                    NSLog( @"**** [[WADODownloadDictionary allKeys] count] > 0");
                
                [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
            }
            
            if( aborted) [logEntry setValue:@"Incomplete" forKey:@"logMessage"];
            else [logEntry setValue:@"Complete" forKey:@"logMessage"];
            
            [[LogManager currentLogManager] addLogLine: logEntry];
            
            if( aborted)
            {
                for( NSURLConnection *connection in connectionsArray)
                    [connection cancel];
            }
            
            [WADODownloadDictionary release];
            WADODownloadDictionary = nil;
            
            [logEntry release];
            logEntry = nil;
            
            [pool release];
            
#ifndef NDEBUG
            if( aborted)
                NSLog( @"------ WADO downloading ABORTED");
            else
                NSLog( @"------ WADO downloading : %d files - finished (errors: %d / total: %d)", (int) [urlToDownload count], (int) ([urlToDownload count] - (countOfSuccesses - passStart)), (int) [urlToDownload count]);
#endif
            return aborted == NO;
        }
    }
    @catch (NSException *exception) {
        N2LogException( exception);
    }
    @finally {
        [pool release];
    }
    
    return YES;
}

- (void) WADODownload: (NSArray*) urlToDownload
{
    if( urlToDownload.count == 0)
    {
        NSLog( @"**** urlToDownload.count == 0 in WADODownload");
        return;
    }
    
    // The list is uniqued here rather than in the pass, so the manifest is built
    // from what will actually be asked for.
    NSArray *unique = [[NSSet setWithArray: urlToDownload] allObjects];
    
    [manifest release];
    manifest = [[HorosRetrieveManifest alloc] initWithURLs: unique];
    self.countOfSuccesses = 0;
    
    // An instance that did not arrive is worth asking for again when the reason
    // was transient; one the server refused is not, and repeating a whole study
    // to collect a handful of instances is what this replaces.
    NSInteger attempts = [[NSUserDefaults standardUserDefaults] integerForKey: @"WADORetryAttempts"];
    if( attempts < 0) attempts = 0;
    if( attempts > 5) attempts = 5;
    
    BOOL completed = [self WADODownloadPass: unique];
    
    for( NSInteger attempt = 0; completed && attempt < attempts; attempt++)
    {
        NSArray *again = [manifest retryableURLs];
        if( again.count == 0)
            break;
        
        NSLog( @"------ WADO retrying %d instance(s) that did not arrive (attempt %d of %d)", (int) again.count, (int) (attempt + 1), (int) attempts);
        completed = [self WADODownloadPass: again];
    }
    
    if( completed == NO)
    {
        // Nothing was heard about the rest, which is not the same as their
        // being absent.
        for( NSURL *url in unique)
            [manifest recordAbandonedURL: url];
    }
    
    if( manifest.isComplete == NO || manifest.duplicateObjectUIDs.count)
        NSLog( @"------ WADO retrieve incomplete: %@", [manifest detailWithLimit: 20]);
    
    if( manifest.isComplete == NO && showErrorMessage && !NSThread.currentThread.isCancelled)
        [WADODownload performSelectorOnMainThread: @selector(errorMessage:)
                                       withObject: [NSArray arrayWithObjects: NSLocalizedString( @"WADO Retrieve Incomplete", nil), manifest.summary, NSLocalizedString( @"Continue", nil), nil]
                                    waitUntilDone: NO];
}


@end
