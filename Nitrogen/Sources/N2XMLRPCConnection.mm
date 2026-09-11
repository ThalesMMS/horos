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

#import "N2XMLRPCConnection.h"
#import "N2Debug.h"
#import "N2XMLRPC.h"
#import "NSInvocation+N2.h"
#import "Horos-Swift.h"

#import "N2Shell.h"

@implementation N2XMLRPCConnection

@synthesize delegate = _delegate;
@synthesize dontSpecifyStringType = _dontSpecifyStringType;

-(NSUInteger)N2XMLRPCOptions {
    NSUInteger o = 0;
    if (self.dontSpecifyStringType)
        o |= N2XMLRPCDontSpecifyStringTypeOptionMask;
    return o;
}

-(id)initWithAddress:(NSString*)address port:(NSInteger)port tls:(BOOL)tlsFlag is:(NSInputStream*)is os:(NSOutputStream*)os {
	if ((self = [super initWithAddress:address port:port tls:tlsFlag is:is os:os])) {
		[self setCloseOnRemoteClose:YES];
	}
	
	return self;
}

-(void)dealloc {
	[self setDelegate:NULL];
    [_doc release];
	[super dealloc];
}

-(void)open {
	@synchronized (self) {
        [_timeout invalidate];
        _timeout = [NSTimer scheduledTimerWithTimeInterval:10 target:self selector:@selector(timeout:) userInfo:NULL repeats:NO];
    }

    [super open];
}

-(void)close {
	@synchronized (self) {
        [_timeout invalidate];
        _timeout = NULL;
    }
    
	[super close];
}

-(void)timeout:(NSTimer*)timer {
	@synchronized (self) {
        _timeout = NULL;
    }

    [self close];
}

-(void)handleData:(NSMutableData*)data {
	if (_executed) return;
	
	CFHTTPMessageRef request = CFHTTPMessageCreateEmpty(kCFAllocatorDefault, TRUE);
	CFHTTPMessageAppendBytes(request, (uint8*)[data bytes], [data length]);

	if (!CFHTTPMessageIsHeaderComplete(request))
    {
        CFRelease(request);
		return;
	}
	
    // Before the body is read, and so before anything in it is parsed or
    // dispatched. A refused request costs one response and nothing else.
    NSString* requestVersion = [(id)CFHTTPMessageCopyVersion(request) autorelease];
    if (!requestVersion) requestVersion = (NSString*)kCFHTTPVersion1_1;
    if (![self shouldHandleRequest:request version:requestVersion])
    {
        _executed = YES;
        CFRelease(request);
        return;
    }
	
	NSString* contentLength = (NSString*)CFHTTPMessageCopyHeaderFieldValue(request, (CFStringRef)@"Content-Length");
	if (contentLength) [contentLength autorelease];
	NSData* content = [(NSData*)CFHTTPMessageCopyBody(request) autorelease];
	
	if (contentLength && [content length] < [contentLength intValue])
    {
		CFRelease(request);
        return;
	}
    
	/*NSString* version = [(NSString*)CFHTTPMessageCopyVersion(request) autorelease];
    if (!version) version = (NSString*)kCFHTTPVersion1_1;
	
    NSString* method = [(NSString*)CFHTTPMessageCopyRequestMethod(request) autorelease];
    if (!method)
    {
        [self writeAndReleaseResponse:CFHTTPMessageCreateResponse(kCFAllocatorDefault, 400, NULL, (CFStringRef)version)];
        CFRelease(request);
        return;
    }
	
	if (![method isEqualToString:@"POST"])
    {
		[self writeAndReleaseResponse:CFHTTPMessageCreateResponse(kCFAllocatorDefault, 405, NULL, (CFStringRef)version)];
        CFRelease(request);
		return;
	}*/
	
	_executed = YES;
	[self handleRequest:request];
	
	CFRelease(request);
}

-(BOOL)shouldHandleRequest:(CFHTTPMessageRef)request version:(NSString*)version {
    return YES;
}

// A bare status line with the headers a client needs to act on it, and no body:
// used for the responses that are not XML-RPC documents, such as the 401 that
// carries the authentication challenge.
-(void)writeStatus:(NSInteger)status headers:(NSDictionary*)headers version:(NSString*)version {
    CFHTTPMessageRef response = CFHTTPMessageCreateResponse(kCFAllocatorDefault, status, NULL, (CFStringRef)version);
    for (NSString* field in headers)
        CFHTTPMessageSetHeaderFieldValue(response, (CFStringRef)field, (CFStringRef)[headers objectForKey:field]);
    CFHTTPMessageSetHeaderFieldValue(response, (CFStringRef)@"Content-Length", (CFStringRef)@"0");
    [self writeAndReleaseResponse:response];
}

-(NSString*)selectorStringForXMLRPCRequestMethodName:(NSString*)name isValidated:(BOOL*)isValidated {
    NSString* sel = nil;
    
    if ([_delegate respondsToSelector:@selector(selectorStringForXMLRPCRequestMethodName:)])
        sel = [_delegate selectorStringForXMLRPCRequestMethodName:name];
    if (sel)
        if (isValidated) *isValidated = YES;
    
    if (!sel) {
        sel = [NSString stringWithFormat:@"%@:error:", name];
        if (![_delegate respondsToSelector:NSSelectorFromString(sel)])
            sel = [NSString stringWithFormat:@"%@:", name];
        if (isValidated) *isValidated = NO;
    }
    
    return sel;
}

-(void)handleRequest:(CFHTTPMessageRef)request {
	NSString* contentLengthString = (NSString*)CFHTTPMessageCopyHeaderFieldValue(request, (CFStringRef)@"Content-Length");
	if (contentLengthString) [contentLengthString autorelease];
	NSInteger contentLength = contentLengthString? [contentLengthString intValue] : 0;
	NSData* content = [(NSData*)CFHTTPMessageCopyBody(request) autorelease];
    
    NSString* version = [(id)CFHTTPMessageCopyVersion(request) autorelease];
    if (!version) version = (NSString*)kCFHTTPVersion1_1;
	
	if (contentLengthString && contentLength < [content length])
		content = [content subdataWithRange:NSMakeRange(0, contentLength)];
	
	@try {
        if (_doc) [_doc release];
        NSError *error = nil;
		_doc = [[NSXMLDocument alloc] initWithData:content options:NSXMLNodeOptionsNone error: &error];
        if (!_doc)
        {
            if( content.length)
                NSLog( @"--- incomplete/corrupted XML document: %@", error.localizedDescription);
            // A Content-Length that has been satisfied means the body is all
            // there, so it is malformed rather than incomplete. Saying so beats
            // waiting for the rest of a request that has already arrived and
            // then closing the connection without a word.
            if (contentLengthString)
                [self writeDocument:[[HorosXMLRPCRequestContract faultForUnparsableRequest:[error localizedDescription]] document] version:version];
            return; // data is incomplete, try later with more data
        }
//        DLog(@"Handling XMLRPC request: %@", [doc XMLString]);
        
		NSArray* methodCalls = [_doc nodesForXPath:@"methodCall" error:NULL];
		if ([methodCalls count] != 1)
			[NSException raise:NSGenericException format:@"request contains %d method calls", (int) [methodCalls count]];
		NSXMLElement* methodCall = [methodCalls objectAtIndex:0];
        
        [_inputStream close]; [_inputStream release]; _inputStream = nil;
        
       // [self performSelectorInBackground:@selector(handleXmlrpcMethodCall:) withObject:[NSArray arrayWithObjects: methodCall, version, nil]]; // naaah we're already in a dedicated thread
        [self performSelector:@selector(handleXmlrpcMethodCall:) withObject:[NSArray arrayWithObjects: methodCall, version, nil]];
	} @catch (NSException* e) {
		NSLog(@"Warning: [N2XMLRPCConnection handleRequest:] %@", [e reason]);
        [self writeDocument:[[HorosXMLRPCRequestContract faultForUnparsableRequest:[e reason]] document] version:version];
	}
}

// A response an XML-RPC client can read: the document in the body, with its
// length, under the 200 the specification asks for even when the document is a
// fault. What used to go out instead was a status line carrying the whole
// document as its reason phrase, and no body at all.
-(void)writeDocument:(NSString*)document version:(NSString*)version {
    NSData* body = [document dataUsingEncoding:NSUTF8StringEncoding];
    CFHTTPMessageRef response = CFHTTPMessageCreateResponse(kCFAllocatorDefault, 200, NULL, (CFStringRef)version);
    CFHTTPMessageSetHeaderFieldValue(response, (CFStringRef)@"Content-Type", (CFStringRef)@"text/xml; charset=utf-8");
    CFHTTPMessageSetHeaderFieldValue(response, (CFStringRef)@"Content-Length", (CFStringRef)[NSString stringWithFormat:@"%d", (int)[body length]]);
    CFHTTPMessageSetBody(response, (CFDataRef)body);
    [self writeAndReleaseResponse:response];
}

-(void)handleXmlrpcMethodCall:(NSArray*)args {
    NSAutoreleasePool* pool = [[NSAutoreleasePool alloc] init];
    
    NSString* version = [args objectAtIndex:1];
    
    NSString* methodName = nil;
    
    @try {
        NSXMLElement* methodCall = [args objectAtIndex:0];
        
        NSArray* methodNames = [methodCall nodesForXPath:@"methodName" error:NULL];
        if ([methodNames count] != 1)
            [NSException raise:NSGenericException format:@"method call contains %d method names", (int) [methodNames count]];
        methodName = [[methodNames objectAtIndex:0] stringValue];
        
        DLog(@"XMLRPC call: %@", methodName);
        
        //		NSArray* methodParameterNames = [doc nodesForXPath:@"methodCall/params//member/name" error:NULL];
        //		NSMutableArray* methodParameterValues = [[doc nodesForXPath:@"methodCall/params//member/value" error:NULL] mutableArray];
        //		if ([methodParameterNames count] != [methodParameterValues count])
        //			[NSException raise:NSGenericException format:@"request parameters inconsistent", [methodNames count]];
        NSArray* params = [methodCall nodesForXPath:@"params/param/value" error:NULL];
        
        //		NSMutableDictionary* methodParameters = [NSMutableDictionary dictionaryWithCapacity:[methodParameterNames count]];
        //		for (int i = 0; i < [methodParameterNames count]; ++i)
        //			[methodParameters setObject:[[methodParameterValues objectAtIndex:i] objectValue] forKey:[[methodParameterNames objectAtIndex:i] objectValue]];
        
        NSMutableArray* objcparams = [NSMutableArray array];
        for (NSXMLNode* param in params)
            [objcparams addObject:[N2XMLRPC ParseElement:param]];
        
        NSError* error = nil;
        
        NSDate* dateBeforeCall = [NSDate date];
        NSObject* result = [self methodCall:methodName params:objcparams error:&error];
        
        if (error) {
            NSLog(@"Warning: [N2XMLRPCConnection handleRequest:] %@", [error localizedDescription]);
            [self writeDocument:[HorosXMLRPCRequestContract responseDocumentForError:error] version:version];
            return;
        }
        
        DLog(@"\tXMLRPC done, took %f seconds.", -[dateBeforeCall timeIntervalSinceNow]);
        
        NSData* responseData = [[N2XMLRPC responseWithValue:result options:[self N2XMLRPCOptions]] dataUsingEncoding:NSUTF8StringEncoding];
        
        CFHTTPMessageRef response = CFHTTPMessageCreateResponse(kCFAllocatorDefault, 200, NULL, (CFStringRef)version);
        CFHTTPMessageSetHeaderFieldValue(response, (CFStringRef)@"Content-Length", (CFStringRef)[NSString stringWithFormat:@"%d", (int) [responseData length]]);
        CFHTTPMessageSetBody(response, (CFDataRef)responseData);
        [self writeAndReleaseResponse:response];
    } @catch (NSException* e) {
		NSLog(@"Warning: [N2XMLRPCConnection handleRequest:] %@", [e reason]);
        [self writeDocument:[[HorosXMLRPCRequestContract faultForFailedMethodName:methodName reason:[e reason]] document] version:version];
	} @finally {
        [pool release];
    }
}

// Report a fault to the caller instead of raising. The in-process callers - the
// horos:// URL handler and the AppleScript bridge - pass no error pointer and no
// exception handler, so a raise there took the application down over a mistyped
// URL.
-(id)failWithFault:(HorosXMLRPCFault*)fault error:(NSError**)error {
    NSLog(@"Warning: [N2XMLRPCConnection methodCall:] %@", fault.string);
    if (error)
        *error = [NSError errorWithDomain:NSCocoaErrorDomain code:fault.code userInfo:[NSDictionary dictionaryWithObject:fault.document forKey:NSLocalizedDescriptionKey]];
    return nil;
}

-(id)methodCall:(NSString*)methodName params:(NSArray*)params error:(NSError**)error {
    BOOL methodSelectorIsValidated = NO;
    NSString* methodSelectorString = [self selectorStringForXMLRPCRequestMethodName:methodName isValidated:&methodSelectorIsValidated];
    SEL methodSelector = NSSelectorFromString(methodSelectorString);

    // Only a method the delegate publishes is callable. Dispatching to whatever
    // selector the delegate happened to respond to made every inherited
    // one-argument method reachable from a socket that asks for no credentials:
    // -isEqualTo: answered, -valueForKey: was invoked with a dictionary as its
    // key, and -performSelector: would have been handed one as a SEL. A delegate
    // that wants a name outside its own list dispatched has to say so through
    // -isSelectorAvailableToXMLRPC:.
    BOOL allowed = methodSelectorIsValidated;
    if (!allowed && [_delegate respondsToSelector:@selector(isSelectorAvailableToXMLRPC:)])
        allowed = [_delegate isSelectorAvailableToXMLRPC:methodSelectorString];
    if (!allowed || ![_delegate respondsToSelector:methodSelector])
        return [self failWithFault:[HorosXMLRPCRequestContract faultForUnknownMethodName:methodName] error:error];

    //		DLog(@"\tHandled by: %@", methodSelectorString);
    
    NSMethodSignature* signature = [_delegate methodSignatureForSelector:methodSelector];
    BOOL takesError = [methodSelectorString hasSuffix:@":error:"];
    NSInteger accepted = (NSInteger)[signature numberOfArguments] - 2 - (takesError? 1 : 0);
    if (accepted < 0)
        accepted = 0;
    
    if (params.count < 1)
        params = [NSArray arrayWithObject:[NSDictionary dictionary]];

    // One parameter too many used to walk off the end of the method signature:
    // the extra object went into the slot reserved for the NSError**, and the
    // error pointer then went one past the last argument, where NSInvocation
    // raised.
    HorosXMLRPCFault* fault = [HorosXMLRPCRequestContract faultForParameters:params methodName:methodName acceptedCount:accepted];
    if (fault)
        return [self failWithFault:fault error:error];

    NSInvocation* invocation = [NSInvocation invocationWithSelector:methodSelector target:_delegate];
   
    for (NSUInteger paramIndex = 0; paramIndex < [params count]; ++paramIndex)
        [invocation setArgumentObject:[params objectAtIndex:paramIndex] atIndex:paramIndex+2];
    
    if (takesError) {
        [invocation setArgument:&error atIndex:[signature numberOfArguments]-1];
    }
    
    [invocation invoke];
    
    return [invocation returnValue];
}

-(void)writeAndReleaseResponse:(CFHTTPMessageRef)response {
    self.closeWhenDoneSending = YES;
	[self writeData:[(NSData*)CFHTTPMessageCopySerializedMessage(response) autorelease]];
	_waitingToClose = YES;
	CFRelease(response);
}

-(void)connectionFinishedSendingData {
	if (_waitingToClose)
		[self close];
}

@end
