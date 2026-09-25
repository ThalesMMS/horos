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

#import "BonjourPublisher.h"
#import "BonjourBrowser.h"
#import "DCMPix.h"
#import "Horos-Swift.h"
#import "DCMTKStoreSCU.h"
#import "SendController.h"
#import "DicomStudy.h"
#import "NSUserDefaultsController+OsiriX.h"
#import "NSUserDefaultsController+N2.h"
#import "N2Debug.h"
#import "DicomDatabase.h"
#import "DicomImage.h"
#import "AppController.h"
#import "NSFileManager+N2.h"
#import "N2Locker.h"

// imports required for socket initialization
#import <sys/socket.h>
#import <netinet/in.h>
#import <unistd.h>

// BY DEFAULT OSIRIX USES 8780 PORT

#include <netdb.h>
#include <unistd.h>
#include <netinet/in.h>
#include <arpa/inet.h>

extern const char *GetPrivateIP(void);


// One request of one client (#615). It used to be an N2Connection, whose run loop called
// -handleData: as bytes arrived and sent what was written in the background. It now runs
// synchronously on a worker of HorosDatabaseServer: it reads from its HorosDatabasePeer
// until the request is complete, answers, and ends the stream. The request handlers below
// are unchanged; the methods they called on N2Connection are provided here over the peer.
@interface O2DatabaseConnection : NSObject {
    int _mode, _hdi;
    BOOL _authorized;
    BOOL _closed; // the request was refused or broke the protocol: nothing more is read or sent
    NSMutableArray* _stack;
    NSMutableData* _readBuffer;
    NSUInteger _readOffset; // bytes of _readBuffer the handlers consumed, removed once per pass
    HorosDatabasePeer* _peer;
    HorosSharedDatabaseRequestPaths *_requestPaths; // the folders this request's paths resolve against (#637)
    NSMutableSet *_linkedPaths; // its absolute paths outside them
}

+ (void)servePeer:(HorosDatabasePeer*)peer;

@end

@interface BonjourPublisher () <HorosDatabaseServerDelegate>
@end


@implementation BonjourPublisher

+ (BonjourPublisher*) currentPublisher // __deprecated
{
    return [[AppController sharedAppController] bonjourPublisher];
}

- (id)init
{
    if ((self = [super init]))
    {
        [[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forValuesKey:OsirixBonjourSharingIsActiveDefaultsKey options:NSKeyValueObservingOptionInitial context:NULL];
        [[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forValuesKey:OsirixBonjourSharingNameDefaultsKey options:NSKeyValueObservingOptionInitial context:NULL];
        [[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forValuesKey:OsirixBonjourSharingIsPasswordProtectedDefaultsKey options:NSKeyValueObservingOptionInitial context:NULL];
        [[NSUserDefaultsController sharedUserDefaultsController] addObserver:self forValuesKey:OsirixBonjourSharingPasswordDefaultsKey options:NSKeyValueObservingOptionInitial context:NULL];
    }
    return self;
}

- (void) dealloc
{
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forValuesKey:OsirixBonjourSharingIsActiveDefaultsKey];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forValuesKey:OsirixBonjourSharingNameDefaultsKey];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forValuesKey:OsirixBonjourSharingIsPasswordProtectedDefaultsKey];
    [[NSUserDefaultsController sharedUserDefaultsController] removeObserver:self forValuesKey:OsirixBonjourSharingPasswordDefaultsKey];
    
    [dicomSendLock release];
    //	self.serviceName = NULL;
    
    _listener.delegate = nil;
    [_listener stop];
    [_listener release]; _listener = nil;
    [_advertisement stop];
    [_advertisement release]; _advertisement = nil;
    [_bonjour release];
    
    [super dealloc];
}

-(void)observeValueForKeyPath:(NSString*)keyPath ofObject:(id)object change:(NSDictionary*)change context:(void*)context {
    if (object == [NSUserDefaultsController sharedUserDefaultsController]) {
        keyPath = [keyPath substringFromIndex:7];
        if ([keyPath isEqualToString:OsirixBonjourSharingIsActiveDefaultsKey]) {
            [self toggleSharing:NSUserDefaults.bonjourSharingIsActive];
            return;
        } else
            if ([keyPath isEqualToString:OsirixBonjourSharingNameDefaultsKey]) {
                // The advertisement carries the name: a new one replaces it (-updateBonjour).
                [self updateBonjour];
                return;
            } else
                if ([keyPath isEqualToString:OsirixBonjourSharingIsPasswordProtectedDefaultsKey]) {
                    return;
                } else
                    if ([keyPath isEqualToString:OsirixBonjourSharingPasswordDefaultsKey]) {
                        return;
                    }
    }
    
    [super observeValueForKeyPath:keyPath ofObject:object change:change context:context];
}

- (int) OsiriXDBCurrentPort // __deprecated
{
    return (int)[_listener port];
}

- (void)toggleSharing:(BOOL)activate
{
    @try {
        if (activate && !_listener) {
            // The listener reports ready or failed on the main queue; the advertisement is published
            // only once it is ready (-databaseServerDidStart:), never for a port nothing listens on.
            _listener = [[HorosDatabaseServer alloc] initWithPort:8780 handler:^(HorosDatabasePeer *peer) {
                [O2DatabaseConnection servePeer:peer];
            }];
            _listener.delegate = self;
            [_listener start];
        }
        
        if (!activate && _listener) {
            _listener.delegate = nil;
            [_listener stop];
            [_listener release];
            _listener = nil;
        }
        
        [self updateBonjour];
    } @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    }
}

- (void)databaseServerDidStart:(HorosDatabaseServer*)server {
    if (server != _listener) return; // a stopped server's late callback
    NSLog(@"Horos database shared on port %ld", (long)server.port);
    [self updateBonjour];
}

- (void)databaseServer:(HorosDatabaseServer*)server didFailWithPOSIXError:(int)posixError description:(NSString*)description {
    if (server != _listener) return;
    NSLog(@"Warning: unable to share the Horos database on port 8780: %@", description);
    // The server stopped itself. Without a listener the advertisement goes (#389, #392): the
    // user is told why, and turning sharing off and on again tries the port once more.
    [[AppController sharedAppController] reportListenBindFailureForService:HorosListenBindFailure.databaseSharingService
                                                                      port:8780
                                                                 errnoCode:posixError];
    _listener.delegate = nil;
    [_listener release];
    _listener = nil;
    [self updateBonjour];
}

- (void)databaseServer:(HorosDatabaseServer*)server isWaitingWithPOSIXError:(int)posixError description:(NSString*)description {
    if (server != _listener) return;
    NSLog(@"Horos database sharing is waiting for the network: %@", description);
    [self updateBonjour]; // port 0: the advertisement is withdrawn until the listener is ready again
}

- (void)updateBonjour {
    // A service created while sharing is disabled retains port zero forever.
    // Drop inactive/stale advertisements and create one only for a listener that is ready,
    // under the name the preferences hold now.
    if (!_listener.port || (_bonjour && (_bonjour.port != _listener.port || ![_bonjour.name isEqualToString:[NSUserDefaults bonjourSharingName]]))) {
        _bonjour.delegate = nil;
        [_bonjour stop];
        [_bonjour release];
        _bonjour = nil;
        [_advertisement stop];
        [_advertisement release];
        _advertisement = nil;
    }
    if (!_listener.port) {
        Class directService = NSClassFromString(@"HorosDirectTransferService");
        if ([directService respondsToSelector:@selector(sharedService)])
            [[directService sharedService] stop];
        return;
    }
    if (!_bonjour) {
        // The advertisement is DNSServiceRegister (#606): it refuses a port no
        // listener is on, takes the name the daemon gives it on a collision, and
        // retries only a transient daemon failure. The deprecated -netService
        // accessor keeps returning an NSNetService for its remaining callers.
        _advertisement = [[HorosBonjourAdvertisement alloc] initWithName:[NSUserDefaults bonjourSharingName]
                                                                    type:@"_osirixdb._tcp."
                                                                    port:[_listener port]];
        _bonjour = [[NSNetService alloc] initWithDomain:@"" type:@"_osirixdb._tcp." name:[NSUserDefaults bonjourSharingName] port:[_listener port]];
        _bonjour.delegate = self;
    }
    
    NSMutableDictionary* txtrec = [NSMutableDictionary dictionary];
#define EitherOr(a, b) (a? a : b)
    [txtrec setObject: EitherOr([[NSUserDefaults standardUserDefaults] stringForKey:@"AETITLE"], @"OSIRIX") forKey:@"AETitle"];
    [txtrec setObject: EitherOr([[NSUserDefaults standardUserDefaults] stringForKey: @"AEPORT"], @"11112") forKey:@"port"];
#undef EitherOr
    if ([AppController UID])
        [txtrec setObject:[AppController UID] forKey:@"UID"];

    Class directPolicy = NSClassFromString(@"HorosDirectTransferPolicy");
    Class directService = NSClassFromString(@"HorosDirectTransferService");
    if ([directService respondsToSelector:@selector(sharedService)])
        [[directService sharedService] startIfSharingActive];
    if ([directPolicy respondsToSelector:@selector(bonjourTXTFields)])
    {
        NSDictionary *capability = [directPolicy bonjourTXTFields];
        NSString *version = [capability objectForKey:@"HorosDirectTransferVersion"];
        if ([version isKindOfClass:[NSString class]] && [version length])
            [txtrec setObject:version forKey:@"HorosDirectTransferVersion"];
        NSString *directPort = [capability objectForKey:@"HorosDirectTransferPort"];
        if ([directPort isKindOfClass:[NSString class]] && [directPort length])
            [txtrec setObject:directPort forKey:@"HorosDirectTransferPort"];
    }
    
    if( [_bonjour setTXTRecordData:[NSNetService dataFromTXTRecordDictionary:txtrec]] == NO)
        NSLog(@"Warning: Horos Bonjour net service setTXTRecordData FAILED");
    
    if (_listener.port)
        [_advertisement publishWithTXTRecord: txtrec];
    else
        [_advertisement stop];
}

- (HorosBonjourAdvertisement*)advertisement {
    return _advertisement;
}

- (NSNetService*)netService { // __deprecated
    return _bonjour;
}

- (void)netService:(NSNetService*)sender didNotPublish:(NSDictionary*)errorDict
{
    if (sender != _bonjour) return; // a delayed callback from an earlier service
    NSLog(@"Warning: Horos Bonjour net service did not publish, %@", errorDict);
    _bonjour.delegate = nil;
    [_bonjour stop];
    [_bonjour release];
    _bonjour = nil;
}

- (void) netServiceDidStop:(NSNetService *)sender
{
    NSLog(@"Horos Bonjour net service did stop");
}


//- (void)connectionOpened:(NSNotification*)notification {
//	N2Connection* connection = [[notification userInfo] objectForKey:N2ConnectionListenerOpenedConnection];
//	[connection setDelegate:self];
//}

+(NSDictionary*)dictionaryFromXTRecordData:(NSData*)data {
    NSMutableDictionary* d = [NSMutableDictionary dictionary];
    NSDictionary* dict = [NSNetService dictionaryFromTXTRecordData:data];
    
    for (NSString* key in dict) {
        NSData* data = [dict objectForKey:key];
        if ([key isEqualToString:@"AETitle"])
            [d setObject:[[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] autorelease] forKey:key];
        else if ([key isEqualToString:@"port"])
            [d setObject:[[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] autorelease] forKey:key];
        else if ([key isEqualToString:@"UID"])
            [d setObject:[[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] autorelease] forKey:key];
        else [d setObject:data forKey:key];
    }
    
    return d;
}

- (void) sendDICOMFilesToOsiriXNode:(NSDictionary*) todo
{
    @autoreleasepool
    {
        if (dicomSendLock == nil)
            dicomSendLock = [[NSLock alloc] init];
        
        [dicomSendLock lock];
        @try {
            DCMTKStoreSCU *storeSCU = [[DCMTKStoreSCU alloc]	initWithCallingAET: [[NSUserDefaults standardUserDefaults] stringForKey: @"AETITLE"]
                                                                      calledAET: [todo objectForKey:@"AETitle"]
                                                                       hostname: [todo objectForKey:@"Address"]
                                                                           port: [[todo objectForKey:@"Port"] intValue]
                                                                    filesToSend: [todo valueForKey: @"Files"]
                                                                 transferSyntax: [[todo objectForKey:@"TransferSyntax"] intValue]
                                                                    compression: 1.0
                                                                extraParameters: [NSDictionary dictionaryWithObject:[DicomDatabase defaultDatabase] forKey:@"DicomDatabase"]]; // nil == TLS not supported !
            
            @try
            {
                [storeSCU run: nil];
            }
            
            @catch (NSException *ne)
            {
                NSLog( @"Bonjour DICOM Send FAILED");
                NSLog( @"%@", [ne name]);
                NSLog( @"%@", [ne reason]);
            }
            
            [storeSCU release];
            storeSCU = nil;
        } @catch (NSException* e) {
            N2LogExceptionWithStackTrace(e);
        } @finally {
            [dicomSendLock unlock];
        }
    }
}

@end

@implementation O2DatabaseConnection

+ (void)servePeer:(HorosDatabasePeer*)peer {
    O2DatabaseConnection *connection = [[O2DatabaseConnection alloc] initWithPeer:peer];
    @try {
        [connection run];
    } @finally {
        [connection release];
    }
}

- (instancetype)initWithPeer:(HorosDatabasePeer*)peer {
    if ((self = [super init])) {
        _peer = [peer retain];
        _stack = [[NSMutableArray alloc] init];
        _readBuffer = [[NSMutableData alloc] init];
    }
    
    return self;
}

- (void)dealloc {
    [_peer release];
    [_readBuffer release];
    [_stack release];
    [_requestPaths release];
    [_linkedPaths release];
    [super dealloc];
}

enum Modes {
    NONE = 0, DONE,
    DATAB,
    DBSIZ,
    GETDI,
    VERSI,
    DBVER,
    ISPWD,
    PASWD,
    SENDD,
    SENDG,
    NEWMS,
    ADDAL,
    REMAL,
    SETVA,
    MFILE,
    DCMSE,
    DICOM
};

static NSString* const O2NotEnoughData = @"O2NotEnoughData";
// A request that breaks the protocol (#614): the connection is closed, nothing
// further of it is read or executed.
static NSString* const O2InvalidRequest = @"O2InvalidRequest";

- (void)_rejectRequest:(NSString*)reason {
    [NSException raise:O2InvalidRequest format:@"%@", reason];
}

// Everything still unconsumed in the receive buffer for the current request.
// Reads arrive in blocks, and a block bounds nothing about the request. This is
// asked for every block of an upload, so the limits are read once.
static NSInteger O2BufferLimitAwaitingCommand, O2BufferLimitUpload, O2BufferLimitOther, O2MaximumFileLength;

+ (void)initialize {
    if (self != [O2DatabaseConnection class])
        return;
    O2MaximumFileLength = HorosSharedDatabaseWire.maximumFileLength;
    O2BufferLimitAwaitingCommand = HorosSharedDatabaseWire.maximumBufferedBytesAwaitingCommand;
    O2BufferLimitUpload = HorosSharedDatabaseWire.maximumBufferedBytesForUpload;
    O2BufferLimitOther = HorosSharedDatabaseWire.maximumBufferedBytesForOtherRequests;
}

- (NSInteger)_maximumBufferedBytes {
    switch (_mode) {
        case NONE: return O2BufferLimitAwaitingCommand;
        case SENDD: case SENDG: return O2BufferLimitUpload;
        default: return O2BufferLimitOther;
    }
}

- (void)_closeIfBufferExceedsLimit {
    if (self.availableSize > [self _maximumBufferedBytes]) {
        NSLog(@"Shared database: request from %@ closed: more than %ld bytes buffered", self.address, (long)[self _maximumBufferedBytes]);
        [self close];
    }
}

// The request, on this worker, from its first byte to the end of its answer. Every wait for the
// network ends: the peer times out after its idle limit of monotonic time, fails with the
// connection, or is cancelled when sharing stops. Nothing thrown here reaches the Swift worker.
- (void)run {
    @try {
        while (_mode != DONE && !_closed) {
            @autoreleasepool {
                NSError *error = nil;
                NSUInteger before = _readBuffer.length;
                if (![_peer appendReceivedDataTo:_readBuffer error:&error]) {
                    NSLog(@"Shared database: request from %@ ended: %@", self.address, error.localizedDescription);
                    return;
                }
                if (_readBuffer.length == before) {
                    // A client that goes away in the middle of a request never completes it.
                    if (_mode != NONE || self.availableSize)
                        NSLog(@"Shared database: %@ disconnected before completing its request", self.address);
                    return;
                }
                [self handleData:_readBuffer];
                // Consumed bytes go once per pass: removing them read by read moved the
                // rest of the request every time, which for 2000 paths cost more than
                // parsing them.
                if (_readOffset) {
                    [_readBuffer replaceBytesInRange:NSMakeRange(0, _readOffset) withBytes:NULL length:0];
                    _readOffset = 0;
                }
            }
        }
        if (_closed)
            return;
        NSError *error = nil;
        if (![_peer finishWithError:&error])
            NSLog(@"Shared database: answer to %@ not completed: %@", self.address, error.localizedDescription);
    } @catch (NSException *exception) {
        N2LogExceptionWithStackTrace(exception);
    } @finally {
        [_peer cancel];
    }
}

// What the handlers used of N2Connection, over the peer.
- (NSString*)address { return _peer.address; }
- (NSInteger)availableSize { return (NSInteger)(_readBuffer.length - _readOffset); }

// The unread part of the request, as a view valid until the buffer changes.
- (NSData*)readBuffer {
    return [NSData dataWithBytesNoCopy:(char*)_readBuffer.mutableBytes + _readOffset length:_readBuffer.length - _readOffset freeWhenDone:NO];
}

- (NSData*)readData:(NSInteger)size {
    NSData *data = [_readBuffer subdataWithRange:NSMakeRange(_readOffset, (NSUInteger)size)];
    _readOffset += (NSUInteger)size;
    return data;
}

- (NSInteger)readData:(NSInteger)size toBuffer:(void*)buffer {
    [_readBuffer getBytes:buffer range:NSMakeRange(_readOffset, (NSUInteger)size)];
    _readOffset += (NSUInteger)size;
    return size;
}

// The unread bytes and a step past them, for the length and string readers: a view object
// or a copy per string cost more than parsing it.
- (const uint8_t*)_unreadBytes { return (const uint8_t*)_readBuffer.bytes + _readOffset; }
- (void)_skipBytes:(NSUInteger)size { _readOffset += size; }

// Sends before returning, in blocks the peer waits for: a slow reader holds the request back
// instead of an ever larger buffer. A failed send ends the request.
- (void)writeData:(NSData*)data {
    if (_closed || !data.length)
        return;
    NSError *error = nil;
    if (![_peer writeData:data error:&error]) {
        NSLog(@"Shared database: sending to %@ failed: %@", self.address, error.localizedDescription);
        [self close];
    }
}

- (NSInteger)writeBufferSize { return 0; } // written synchronously: nothing is ever left queued

// Refuses the request: nothing more of it is read or answered, and the stream is not ended
// cleanly, so the client sees the connection close without a response.
- (void)close {
    _closed = YES;
    [_peer cancel];
}

- (void)handleData:(NSMutableData*)data {
    _hdi = 0;

    @try {
        // The request is complete and its answer may still be on its way out:
        // anything more the client sends is not part of it, and kept it would
        // grow the buffer for as long as the answer takes.
        if (_mode == DONE) {
            if (self.availableSize)
                [self readData:self.availableSize];
            return;
        }

        if (_mode == NONE) {
            if (self.availableSize < 6)
                return;
            BOOL protected = NSUserDefaults.bonjourSharingIsPasswordProtected;
            if (memcmp(self.readBuffer.bytes, "AUTHR", 6) == 0) {
                NSInteger length = [HorosSharedDatabaseAuthorization authorizedPrefixLength:self.readBuffer password:NSUserDefaults.bonjourSharingPassword required:protected];
                if (length == 0) return;
                if (length < 0) { [self close]; return; }
                [self readData:length];
                _authorized = YES;
            }
            char command[6];
            [self readData:6 toBuffer:command];
            if (command[5] != 0) { [self close]; return; }
            NSString *name = [NSString stringWithUTF8String:command];
            if (!name) { [self close]; return; }
            if (protected && !_authorized && ![HorosSharedDatabaseAuthorization isPublicCommand:name]) {
                [self close];
                return;
            }
            if (strcmp(command, "AUTHV") == 0) {
                unsigned int version = NSSwapHostIntToBig(1);
                [self writeData:[NSData dataWithBytes:&version length:4]];
                _mode = DONE;
                return;
            }
            
            if (strcmp(command, "DATAB") == 0)
                _mode = DATAB;
            else if (strcmp(command, "DBSIZ") == 0)
                _mode = DBSIZ;
            else if (strcmp(command, "GETDI") == 0)
                _mode = GETDI;
            else if (strcmp(command, "VERSI") == 0)
                _mode = VERSI;
            else if (strcmp(command, "DBVER") == 0)
                _mode = DBVER;
            else if (strcmp(command, "ISPWD") == 0)
                _mode = ISPWD;
            else if (strcmp(command, "PASWD") == 0)
                _mode = PASWD;
            else if (strcmp(command, "SENDD") == 0)
                _mode = SENDD;
            else if (strcmp(command, "SENDG") == 0)
                _mode = SENDG;
            else if (strcmp(command, "NEWMS") == 0)
                _mode = NEWMS;
            else if (strcmp(command, "ADDAL") == 0)
                _mode = ADDAL;
            else if (strcmp(command, "REMAL") == 0)
                _mode = REMAL;
            else if (strcmp(command, "SETVA") == 0)
                _mode = SETVA;
            else if (strcmp(command, "MFILE") == 0)
                _mode = MFILE;
            else if (strcmp(command, "DCMSE") == 0)
                _mode = DCMSE;
            else if (strcmp(command, "DICOM") == 0)
                _mode = DICOM;
            
            if (_mode == NONE)
                [self close];
        }
        
        switch (_mode) {
            case DATAB:
                return [self DATAB];
            case DBSIZ:
                return [self DBSIZ];
            case GETDI:
                return [self GETDI];
            case VERSI:
                return [self VERSI];
            case DBVER:
                return [self DBVER];
            case ISPWD:
                return [self ISPWD];
            case PASWD:
                return [self PASWD];
            case SENDD:
                return [self SEND];
            case SENDG:
                return [self SEND];
            case NEWMS:
                return [self NEWMS];
            case ADDAL:
                return [self ADDAL];
            case REMAL:
                return [self REMAL];
            case SETVA:
                return [self SETVA];
            case MFILE:
                return [self MFILE];
            case DCMSE:
                return [self DCMSE];
            case DICOM:
                return [self DICOM];
        }
    } @catch (NSException* e) {
        if ([e.name isEqualToString:O2NotEnoughData]) {
            [self _closeIfBufferExceedsLimit];
            return;
        }
        if ([e.name isEqualToString:O2InvalidRequest]) {
            NSLog(@"Shared database: request from %@ closed: %@", self.address, e.reason);
            [self close];
            return;
        }
        @throw e;
    }
    // A complete request (DONE) is answered by now: -run ends the stream.
}

- (void)_stackObject:(id)o {
    [_stack addObject:o];
    ++_hdi;
}

- (id)_stackedObject {
    if (_stack.count <= _hdi)
        return nil;
    return [_stack objectAtIndex:_hdi++];
}

- (void)_unstack {
    [_stack removeObjectAtIndex:--_hdi];
}

- (void)_requireDataSize:(NSInteger)size {
    if (size < 0)
        [self _rejectRequest:@"negative data size"];
    if (self.availableSize < size)
        [NSException raise:O2NotEnoughData format:@""];
}

// A 32-bit length or count, validated before anything is consumed: a negative
// value, or one above what the command can really carry, rejects the request.
- (NSInteger)_readLengthUpTo:(NSInteger)maximum what:(NSString*)what {
    [self _requireDataSize:4];

    uint32_t raw;
    memcpy(&raw, [self _unreadBytes], 4);
    NSInteger value = [HorosSharedDatabaseWire validatedValue:raw maximum:maximum];
    if (value < 0)
        [self _rejectRequest:[NSString stringWithFormat:@"invalid %@ (%d)", what, (int)NSSwapBigIntToHost(raw)]];
    [self _skipBytes:4];

    return value;
}

- (NSInteger)_stackReadLengthUpTo:(NSInteger)maximum what:(NSString*)what {
    if (_stack.count > _hdi)
        return [[self _stackedObject] integerValue];

    NSInteger value = [self _readLengthUpTo:maximum what:what];

    [self _stackObject:[NSNumber numberWithInteger:value]];

    return value;
}

- (NSInteger)_stackReadCount {
    return [self _stackReadLengthUpTo:HorosSharedDatabaseWire.maximumCount what:@"count"];
}

// Zero length is how the client sends nil, so nil and @"" stay distinct. The
// length prefix is left in the buffer until the whole string has arrived: a
// fragment boundary anywhere inside it resumes from the same place.
- (NSString*)_readString {
    [self _requireDataSize:4];

    uint32_t raw;
    memcpy(&raw, [self _unreadBytes], 4);
    NSInteger length = [HorosSharedDatabaseWire validatedValue:raw maximum:HorosSharedDatabaseWire.maximumStringLength];
    if (length < 0)
        [self _rejectRequest:[NSString stringWithFormat:@"invalid string length (%d)", (int)NSSwapBigIntToHost(raw)]];

    [self _requireDataSize:length + 4];

    HorosSharedDatabaseStringStatus status = HorosSharedDatabaseStringStatusValue;
    NSString *value = [HorosSharedDatabaseWire decodeBytes:[self _unreadBytes] + 4 length:length status:&status];
    if (status == HorosSharedDatabaseStringStatusUnterminated)
        [self _rejectRequest:@"string without its terminator"];
    if (status == HorosSharedDatabaseStringStatusEmbeddedNull)
        [self _rejectRequest:@"string with an embedded terminator"];
    if (status == HorosSharedDatabaseStringStatusInvalidUTF8)
        [self _rejectRequest:@"string that is not UTF-8"];

    [self _skipBytes:length + 4];

    return value;
}

// The resume stack cannot hold nil: a null string is stacked as NSNull and
// handed back as nil.
- (NSString*)_stackReadString {
    if (_stack.count > _hdi)
    {
        id value = [self _stackedObject];
        return value == [NSNull null] ? nil : value;
    }
    NSString* value = [self _readString];

    [self _stackObject:value ?: [NSNull null]];

    return value;
}

// For parameters a command cannot do without.
- (NSString*)_stackReadRequiredString:(NSString*)what {
    NSString* value = [self _stackReadString];
    if (!value)
        [self _rejectRequest:[NSString stringWithFormat:@"missing %@", what]];
    return value;
}

- (DicomDatabase*)_stackIndependentDatabase {
    if (_stack.count > _hdi)
    {
        return [self _stackedObject];
    }
    DicomDatabase* database = [[DicomDatabase defaultDatabase] independentDatabase];
    
    [self _stackObject:database];
    
    return database;
}

// The file a request names (#637). A relative path is an image of
// DATABASE.noindex by its name, or an older client's ROI; an absolute path is
// used as it is. A path of another shape, or with a `.` or `..` component, closes
// the request. An absolute path outside the database's folders is kept for
// -_requireLinkedPaths, which decides once every path of the request is known.
- (NSString*)_servedPathForRequestedPath:(NSString*)requested {
    if (!_requestPaths) {
        // Once per request: a DCMSE names a path per image.
        DicomDatabase *database = [DicomDatabase defaultDatabase];
        _requestPaths = [[HorosSharedDatabaseRequestPaths alloc] initWithDatabaseDirectory:[[database sqlFilePath] stringByDeletingLastPathComponent]
                                                                             dataDirectory:[database dataDirPath]
                                                                                folderSize:[BrowserController DefaultFolderSizeForDB]];
    }
    NSString *resolved = nil;
    HorosSharedDatabasePathKind kind = [_requestPaths kindOfRequestedPath:requested resolvedPath:&resolved];
    if (kind == HorosSharedDatabasePathKindRefused || !resolved)
        [self _rejectRequest:[NSString stringWithFormat:@"path %@ does not name a file of the database", requested]];
    if (kind == HorosSharedDatabasePathKindLinked) {
        if (!_linkedPaths)
            _linkedPaths = [[NSMutableSet alloc] init];
        [_linkedPaths addObject:resolved];
    }
    return resolved;
}

// Absolute paths outside the database's folders are read only for the images
// the index links in place, by exactly that path (HorosSharedDatabaseLinkedPaths
// keeps the ones it has confirmed); one unknown path closes the whole request,
// before any of it is answered.
- (void)_requireLinkedPaths {
    if (!_linkedPaths.count)
        return;
    DicomDatabase *database = [DicomDatabase defaultDatabase];
    BOOL known = [HorosSharedDatabaseLinkedPaths.sharedPaths containsAllPaths:_linkedPaths indexFile:[database sqlFilePath] lookup:^NSArray*(NSSet *paths) {
        // Only the paths, as dictionaries: no image is materialized.
        DicomDatabase *index = [database independentDatabase];
        NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"Image"];
        request.predicate = [NSPredicate predicateWithFormat:@"pathString IN %@", paths];
        request.resultType = NSDictionaryResultType;
        request.propertiesToFetch = @[@"pathString"];
        return [[[index managedObjectContext] executeFetchRequest:request error:NULL] valueForKey:@"pathString"] ?: @[];
    }];
    if (!known)
        [self _rejectRequest:[NSString stringWithFormat:@"a path outside the database that no image links to, among %@", _linkedPaths]];
}

- (void)DATAB {
    DicomDatabase* idatabase = [self _stackIndependentDatabase];
    
    NSMutableData* representationToSend = nil;
    
    N2Locker* lock = [self _stackedObject];
    if (!lock) {
        [self _stackObject:[N2Locker lock:[[idatabase managedObjectContext] persistentStoreCoordinator]]]; // this object unlocks the persistentStoreCoordinator when released
        [idatabase save];
    }
    
    BOOL done = NO;
    
    @try
    {
        // we send the database SQL file
        NSString* databasePath = [idatabase sqlFilePath];
        
#if __LP64__
        representationToSend = [NSMutableData dataWithContentsOfFile: databasePath];
        done = YES;
#else
        NSNumber* fileSize = [self _stackedObject];
        if (!fileSize) {
            NSDictionary *fattrs = [[NSFileManager defaultManager] fileAttributesAtPath: databasePath traverseLink: YES];
            long long ll = [[fattrs objectForKey:NSFileSize] longLongValue];
            [self _stackObject:(fileSize = [NSNumber numberWithLongLong:ll])];
        }
        
        // read 200 MB per cycle
#define DATA_READ_SIZE 200L
        
        if (fileSize.longLongValue/1024/1024 > DATA_READ_SIZE)
        {
            NSFileHandle* dbFileHandle = [self _stackedObject];
            if (!dbFileHandle) {
                dbFileHandle = [NSFileHandle fileHandleForReadingAtPath: databasePath];
                [self _stackObject:dbFileHandle];
            }
            
            if (self.writeBufferSize > 0) // to optimize memory usage, don't queue additional data until the send buffer is empty
                return;
            
            NSData* chunk = [dbFileHandle readDataOfLength: DATA_READ_SIZE * 1024L*1024L];
            if ([chunk length]) {
                [self writeData: chunk];
                return;
            } else
                done = YES;
            
            [self _unstack];
        }
        else
        {
            representationToSend = [NSMutableData dataWithContentsOfFile: databasePath];
            done = YES;
        }
        
        [self _unstack];
#endif
    }
    @catch (NSException *e) {
        N2LogExceptionWithStackTrace(e);
    }
    @finally {
        if (done) {
            [self _unstack]; // -> release N2Locker, unlocks the persistentStoreCoordinator (this line may not be called, so the persistentStoreCoordinator will be unlocked when this connection object is released -- when the stack is released)
        }
    }
    
    if (representationToSend)
        [self writeData:representationToSend];
    
    NSLog(@"Bonjour connection received from %@", self.address);
    
    _mode = DONE;
}

- (void)DBSIZ {
    DicomDatabase* idatabase = [self _stackIndependentDatabase];
    
    unsigned long long fileSize = 0;
    
    [[[idatabase managedObjectContext] persistentStoreCoordinator] lock];
    @try
    {
        [idatabase save];
        
        NSString *databasePath = [idatabase sqlFilePath];
        
        NSDictionary *fattrs = [[NSFileManager defaultManager] attributesOfItemAtPath:databasePath error:NULL];
        
        fileSize = [[fattrs objectForKey:NSFileSize] unsignedLongLongValue];
    }
    @catch (NSException* e) {
        N2LogExceptionWithStackTrace(e);
    }
    @finally {
        [[[idatabase managedObjectContext] persistentStoreCoordinator] unlock];
    }
    
    // Four bytes, read unsigned by the client: an index of 4 GiB or more is
    // answered with the value that says so, never with its size wrapped (#637).
    uint32_t size = [HorosSharedDatabaseRequests replyForIndexSize:fileSize];
    if (size == HorosSharedDatabaseRequests.indexTooLargeForReply)
        NSLog(@"Shared database: the index (%llu bytes) is too large to be shared with %@", fileSize, self.address);
    size = NSSwapHostIntToBig(size);
    [self writeData:[NSData dataWithBytes:&size length:sizeof(size)]];
    
    _mode = DONE;
}

- (void)GETDI {
    NSDictionary* dictionary = [NSDictionary dictionaryWithObjectsAndKeys: [[NSUserDefaults standardUserDefaults] stringForKey: @"AETITLE"], @"AETitle", [[NSUserDefaults standardUserDefaults] stringForKey: @"AEPORT"], @"Port", [NSString stringWithFormat: @"%d", [DCMTKStoreSCU sendSyntaxForListenerSyntax: [[NSUserDefaults standardUserDefaults] integerForKey: @"preferredSyntaxForIncoming"]]], @"TransferSyntax", nil];
    
    [self writeData:[NSMutableData dataWithData: [NSArchiver archivedDataWithRootObject: dictionary]]];
    
    _mode = DONE;
}

- (void)VERSI {
    DicomDatabase* idatabase = [self _stackIndependentDatabase];
    
    NSTimeInterval val = [idatabase timeOfLastModification];
    
    NSSwappedDouble swappedValue = NSSwapHostDoubleToBig( val);
    
    if( sizeof( swappedValue.v) != 8) NSLog(@"********** warning sizeof( swappedValue) != 8");
    
    [self writeData:[NSMutableData dataWithBytes: &swappedValue.v length:sizeof(NSTimeInterval)]];
    
    _mode = DONE;
}

- (void)DBVER {
    NSString	*versString = [[NSUserDefaults standardUserDefaults] stringForKey: @"DATABASEVERSION"];
    
    [self writeData:[NSMutableData dataWithData: [versString dataUsingEncoding: NSASCIIStringEncoding]]];
    
    _mode = DONE;
}

- (void)ISPWD {
    // is this database protected by a password
    NSString* pswd = NSUserDefaults.bonjourSharingPassword;
    
    int val = 0;
    if (NSUserDefaults.bonjourSharingIsPasswordProtected)
        val = NSSwapHostIntToBig(1);
    
    [self writeData:[NSMutableData dataWithBytes:&val length:sizeof(int)]];
    
    _mode = DONE;
}

- (void)PASWD {
    [self _requireDataSize:4];
    unsigned int length; [self.readBuffer getBytes:&length length:4];
    length = NSSwapBigIntToHost(length);
    if (length == 0 || length > 4097) { [self close]; return; }
    [self _requireDataSize:(int)length + 4];
    [self readData:4];
    NSData *bytes = [self readData:length];
    if (((const unsigned char *)bytes.bytes)[length - 1] != 0) { [self close]; return; }
    NSString *incomingPswd = [[[NSString alloc] initWithBytes:bytes.bytes length:length - 1 encoding:NSUTF8StringEncoding] autorelease];
    
    // We read the string
    int val = 0;
    
    if (!NSUserDefaults.bonjourSharingIsPasswordProtected || (NSUserDefaults.bonjourSharingPassword.length && [incomingPswd isEqualToString:NSUserDefaults.bonjourSharingPassword]))
    {
        val = NSSwapHostIntToBig(1);
    }
    
    [self writeData:[NSMutableData dataWithBytes:&val length:sizeof(int)]];
    
    _mode = DONE;
}

- (void)SEND {
    NSInteger fileNo = [self _stackReadCount];
    
    NSMutableArray* savedFiles = [self _stackedObject];
    if (!savedFiles) [self _stackObject:(savedFiles = [NSMutableArray array])];
    
    while (savedFiles.count < fileNo)
    {
        NSInteger fileSize = [self _stackReadLengthUpTo:O2MaximumFileLength what:@"file length"];
        // A file arrives in thousands of blocks, and waiting for the rest is the
        // usual state here: raising O2NotEnoughData for every block cost more
        // than receiving the upload. The resume stack is left exactly as the
        // exception would leave it.
        if (self.availableSize < fileSize) {
            [self _closeIfBufferExceedsLimit];
            return;
        }
        
        NSString* dstPath = [[[BrowserController currentBrowser] database] uniquePathForNewDataFileWithExtension:@"dcm"];
        
        [[self readData:fileSize] writeToFile:dstPath atomically:YES];
        
        [savedFiles addObject: dstPath];
        
        [self _unstack];
    }
    
    DicomDatabase* idatabase = [self _stackIndependentDatabase];
    
    NSArray *objects = [idatabase addFilesAtPaths: savedFiles postNotifications: YES dicomOnly: NO rereadExistingItems: YES generatedByOsiriX:(_mode == SENDG)];
    
    objects = [idatabase objectsWithIDs: objects];
    
    NSMutableData* representationToSend = [NSMutableData data];
    unsigned int temp = NSSwapHostIntToBig([objects count]);
    [representationToSend appendBytes:&temp length:4];
    for (DicomImage* image in objects) {
        unsigned int temp = NSSwapHostIntToBig(image.pathNumber.intValue);
        [representationToSend appendBytes:&temp length:4];
    }
    
    [self writeData:representationToSend];
    
    _mode = DONE;
}

- (void)NEWMS { // is this used ? nah
    NSInteger size = [self _stackReadLengthUpTo:HorosSharedDatabaseWire.maximumStringLength what:@"message length"];
    
    [self _requireDataSize:size];
    if (size) [self readData:size]; // readData:0 would take the whole buffer
    //    NSData* da = [self readData:size];
    
    //    NSDictionary* d = [NSPropertyListSerialization propertyListFromData:da mutabilityOption: NSPropertyListImmutable format: nil errorDescription: nil];
    //
    //    if (d)
    //    {
    //        NSString *message = [d objectForKey:@"message"];
    //    }
    
    _mode = DONE;
}

- (void)ADDAL {
    NSString* object = [self _stackReadRequiredString:@"album parameters"];
    
    NSDictionary* d = (NSDictionary*)[NSPropertyListSerialization
                                      propertyListFromData:[NSData dataWithBytesNoCopy:(void*)object.UTF8String length:strlen(object.UTF8String) freeWhenDone:NO]
                                      mutabilityOption:NSPropertyListImmutable
                                      format:NULL
                                      errorDescription:NULL];
    
    if (!d) [NSException raise:NSGenericException format:@"can't parse parameters"];
    
    NSArray *studies = [d objectForKey:@"albumStudies"];
    NSString *albumUID = [d objectForKey:@"albumUID"];
    
    DicomDatabase* idatabase = [self _stackIndependentDatabase];
    
    @try
    {
        DicomAlbum* album = [idatabase objectWithID:albumUID]; // [context objectWithID: [[context persistentStoreCoordinator] managedObjectIDForURIRepresentation: [NSURL URLWithString: albumUID]]];
        NSMutableSet* albumStudies = [album mutableSetValueForKey:@"studies"];
        
        for (NSString* uri in studies)
        {
            DicomStudy* study = [idatabase objectWithID:uri]; // (DicomStudy*) [context objectWithID: [[context persistentStoreCoordinator] managedObjectIDForURIRepresentation: [NSURL URLWithString: uri]]];
            [albumStudies addObject:study];
            [study archiveAnnotationsAsDICOMSR];
        }
        
        [idatabase save:nil];
        
        [[BrowserController currentBrowser] performSelectorOnMainThread:@selector(refreshDatabase:) withObject:self waitUntilDone:NO];
    }
    
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    
    _mode = DONE;
}

- (void)REMAL {
    NSString* object = [self _stackReadRequiredString:@"album parameters"];
    
    NSDictionary* d = (NSDictionary*)[NSPropertyListSerialization
                                      propertyListFromData:[NSData dataWithBytesNoCopy:(void*)object.UTF8String length:strlen(object.UTF8String) freeWhenDone:NO]
                                      mutabilityOption:NSPropertyListImmutable
                                      format:NULL
                                      errorDescription:NULL];
    
    if (!d) [NSException raise:NSGenericException format:@"can't parse parameters"];
    
    NSArray *studies = [d objectForKey:@"albumStudies"];
    NSString *albumUID = [d objectForKey:@"albumUID"];
    
    DicomDatabase* idatabase = [self _stackIndependentDatabase];
    
    @try
    {
        DicomAlbum* album = [idatabase objectWithID:albumUID]; // [context objectWithID: [[context persistentStoreCoordinator] managedObjectIDForURIRepresentation: [NSURL URLWithString: albumUID]]];
        NSMutableSet* albumStudies = [album mutableSetValueForKey: @"studies"];
        
        for (NSString* uri in studies)
        {
            DicomStudy* study = [idatabase objectWithID:uri]; // (DicomStudy*) [context objectWithID: [[context persistentStoreCoordinator] managedObjectIDForURIRepresentation: [NSURL URLWithString: uri]]];
            [albumStudies removeObject:study];
            [study archiveAnnotationsAsDICOMSR];
        }
        
        [idatabase save:nil];
        
        [[BrowserController currentBrowser] performSelectorOnMainThread:@selector(refreshDatabase:) withObject:self waitUntilDone:NO];
    }
    
    @catch (NSException * e)
    {
        N2LogExceptionWithStackTrace(e);
    }
    @finally {
    }
    
    _mode = DONE;
    
}

- (void)SETVA {
    NSString* objectId = [self _stackReadRequiredString:@"object identifier"];
    NSString* value = [self _stackReadString]; // nil is a value here: it clears reportURL
    NSString* key = [self _stackReadRequiredString:@"key"];
    
    // Only the keys the client sets, each with its type (#637): any other key
    // path closes the request before the database is touched.
    HorosSharedDatabaseSettableKey kind = [HorosSharedDatabaseRequests settableKindForKey:key];
    if (kind == HorosSharedDatabaseSettableKeyRefused)
        [self _rejectRequest:[NSString stringWithFormat:@"key %@ cannot be set remotely", key]];
    
    DicomDatabase* idatabase = [self _stackIndependentDatabase];
    
    @try
    {
        NSManagedObject* item = [idatabase objectWithID:objectId]; // [context objectWithID: [[context persistentStoreCoordinator] managedObjectIDForURIRepresentation: [NSURL URLWithString: object]]];
        
        if( item)
        {
            if (kind == HorosSharedDatabaseSettableKeyNumber)
                [item setValue:[NSNumber numberWithInt:[value intValue]] forKeyPath:key];
            else if (kind == HorosSharedDatabaseSettableKeyText)
                [item setValue:value forKeyPath:key];
            else // reportURL
            {
                NSString *reports = [idatabase reportsDirPath];
                if (value == nil)
                {
                    // The report file goes only if it is one of the database's reports.
                    NSString *current = [item valueForKey:@"reportURL"];
                    if ([HorosSharedDatabaseRequests isPath:current insideReportsDirectory:reports])
                        [[NSFileManager defaultManager] removeItemAtPath:current error:NULL];
                    else if (current)
                        NSLog(@"Shared database: %@ cleared a report outside the reports folder; the file is kept", self.address);
                }
                else
                {
                    value = [HorosSharedDatabaseRequests reportPathForName:value reportsDirectory:reports];
                    if (!value)
                        [self _rejectRequest:@"report name that does not stay in the reports folder"];
                }
                
                [item setValue:value forKey:@"reportURL"];
            }
        }
        
        [idatabase save:NULL];
    }
    
    @catch (NSException *e)
    {
        if ([e.name isEqualToString:O2InvalidRequest])
            @throw;
        N2LogExceptionWithStackTrace(e);
    }
    @finally {
    }
    
    [[BrowserController currentBrowser] performSelectorOnMainThread:@selector(refreshDatabase:) withObject:self waitUntilDone:NO];
    
    _mode = DONE;
}

- (void)MFILE {
    NSString* path = [self _stackReadRequiredString:@"path"];
    
    if( [path length])
    {
        if( [path characterAtIndex: 0] != '/')
            path = [[[DicomDatabase defaultDatabase] baseDirPath] stringByAppendingPathComponent: path];
    }
    path = [self _servedPathForRequestedPath:path];
    [self _requireLinkedPaths];
    
    NSDictionary *fattrs = [[NSFileManager defaultManager] attributesOfItemAtPath:path error:NULL];
    
    NSData	*content = [[[fattrs objectForKey:NSFileModificationDate] description] dataUsingEncoding: NSUnicodeStringEncoding];
    
    [self writeData:content];
    
    _mode = DONE;
}

- (void)DCMSE {
    NSString* AETitle = [self _stackReadRequiredString:@"AE title"];
    NSString* Address = [self _stackReadRequiredString:@"address"];
    NSString* Port = [self _stackReadRequiredString:@"port"];
    NSString* TransferSyntax = [self _stackReadRequiredString:@"transfer syntax"];
    
    NSInteger noOfFiles = [self _stackReadCount];
    
    NSMutableArray* localPaths = [self _stackedObject];
    if (!localPaths) [self _stackObject:(localPaths = [NSMutableArray array])];
    
    while (localPaths.count < noOfFiles)
    {
        NSString* path = [self _servedPathForRequestedPath:[self _stackReadRequiredString:@"path"]];
        
        [localPaths addObject: path];
        
        [self _unstack]; // the string
    }
    [self _requireLinkedPaths];
    
    if( [Address isEqualToString: @"127.0.0.1"])
    {
        Address = self.address;
    }
    
    NSDictionary *todo = [NSDictionary dictionaryWithObjectsAndKeys: Address, @"Address", TransferSyntax, @"TransferSyntax", Port, @"Port", AETitle, @"AETitle", localPaths, @"Files", nil];
    
    [NSThread detachNewThreadSelector:@selector(sendDICOMFilesToOsiriXNode:) toTarget:[[AppController sharedAppController] bonjourPublisher] withObject: todo];
    
    _mode = DONE;
}

- (void)DICOM
{
    @synchronized( self)
    {
        NSInteger noOfFiles = [self _stackReadCount];
        
        NSMutableArray* localPaths = [self _stackedObject];
        if (!localPaths) [self _stackObject:(localPaths = [NSMutableArray array])];
        NSMutableArray* dstPaths = [self _stackedObject];
        if (!dstPaths) [self _stackObject:(dstPaths = [NSMutableArray array])];
        
        while (localPaths.count < noOfFiles)
        {
            NSString* path = [self _servedPathForRequestedPath:[self _stackReadRequiredString:@"path"]];
            
            [localPaths addObject: path];
            
            
            [self _unstack]; // the string
        }
        
        while (dstPaths.count < noOfFiles)
        {
            NSString* path = [self _stackReadRequiredString:@"destination path"];
            
            [dstPaths addObject: path];
            
            
            [self _unstack]; // the string
        }
        
        // Nothing is written before every path is known to be served.
        [self _requireLinkedPaths];
        
        int temp = NSSwapHostIntToBig(noOfFiles);
        [self writeData:[NSData dataWithBytesNoCopy:&temp length:4 freeWhenDone:NO]];
        for (NSInteger i = 0; i < noOfFiles; i++)
        {
            NSString* path = [localPaths objectAtIndex: i];
            
            
            NSData* content = [NSData dataWithContentsOfMappedFile:path];
            int size = NSSwapHostIntToBig([content length]);
            [self writeData:[NSData dataWithBytesNoCopy:&size length:4 freeWhenDone:NO]];
            [self writeData:content];
            
            const char* string = [[dstPaths objectAtIndex:i] UTF8String];
            int stringSize = NSSwapHostIntToBig( strlen( string)+1);	// +1 to include the last 0 !
            [self writeData:[NSData dataWithBytesNoCopy:&stringSize length:4 freeWhenDone:NO]];
            [self writeData:[NSData dataWithBytesNoCopy:(void*)string length:strlen(string)+1 freeWhenDone:NO]];
        }
        
        _mode = DONE;
    }
}






@end
