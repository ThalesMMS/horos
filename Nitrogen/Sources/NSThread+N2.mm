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


#import "NSThread+N2.h"
#import "N2Debug.h"
//#import "NSException+N2.h"

// Kept (#626): replacing this subclass with -[NSThread initWithBlock:] (and a
// block around the caller's for the pool and the exception) or with
// -initWithTarget:selector:object: started every thread 1-5 % slower, measured.
@interface N2BlockThread : NSThread {
    void (^_block)();
}

-(id)initWithBlock:(void(^)())block;

@end

@implementation NSThread (N2)

+(NSThread*)performBlockInBackground:(void(^)())block {
    N2BlockThread* bt = [[[N2BlockThread alloc] initWithBlock:block] autorelease];
    [bt start];
    return bt;
}

// The keys below are notified by hand, only when the value read changes. Left
// automatic, KVO also wrapped each setter in a notification of its own, so every
// call notified, changed or not, and a change notified twice (#626).
+(BOOL)automaticallyNotifiesObserversOfUniqueId { return NO; }
+(BOOL)automaticallyNotifiesObserversOfIsCancelled { return NO; }
+(BOOL)automaticallyNotifiesObserversOfSupportsCancel { return NO; }
+(BOOL)automaticallyNotifiesObserversOfSupportsBackgrounding { return NO; }
+(BOOL)automaticallyNotifiesObserversOfStatus { return NO; }
+(BOOL)automaticallyNotifiesObserversOfProgress { return NO; }
+(BOOL)automaticallyNotifiesObserversOfProgressDetails { return NO; }

-(NSComparisonResult)compare:(id)obj {
	//NSException *e = [NSException exceptionWithName: @"NSThread compare" reason: @"compare:" userInfo: nil];	
	//[e printStackTrace];
	return NSOrderedSame;
}

NSString* const NSThreadNameKey = @"name";

#pragma mark Id

NSString* const NSThreadUniqueIdKey = @"uniqueId";

-(NSString*)uniqueId {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
    
    NSString* uniqueId = nil;
	
	@synchronized (self) {
		uniqueId = [[[self.threadDictionary objectForKey:NSThreadUniqueIdKey] copy] autorelease];
	}
	
	return uniqueId;
}

-(void)setUniqueId:(NSString*)uniqueId {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;

	if ([uniqueId isEqualToString:self.uniqueId])
		return;
	
	@synchronized (self) {
		[self willChangeValueForKey:NSThreadUniqueIdKey];
		[self.threadDictionary setObject:uniqueId forKey:NSThreadUniqueIdKey];
		[self didChangeValueForKey:NSThreadUniqueIdKey];
	}
}

NSString* const NSThreadIsCancelledKey = @"isCancelled";

-(void)setIsCancelled:(BOOL)isCancelled {
	if (self.isFinished)
		return;
	if (self.isCancelled)
		return;
	
	if (isCancelled == self.isCancelled) return;
	
	@synchronized (self) {
		[self willChangeValueForKey:NSThreadIsCancelledKey];
		[self cancel];
		[self didChangeValueForKey:NSThreadIsCancelledKey];
	}
}

#pragma mark Stack

static NSString* const NSThreadStackArrayKey = @"NSThreadStackArrayKey";

-(NSMutableArray*)stackArray {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
	
    if (self.isFinished)
        return nil;
    
	NSMutableArray* a = nil;
	
	@synchronized (self) {
		a = [self.threadDictionary objectForKey:NSThreadStackArrayKey];
		if (!a) {
			a = [NSMutableArray array];
			[self.threadDictionary setObject:a forKey:NSThreadStackArrayKey];
			if ([self.threadDictionary objectForKey:NSThreadStackArrayKey])
                [self enterOperation];
		}
	}
	
	return a;
}

static NSString* const NSThreadSubRangeKey = @"subRange";

-(NSMutableDictionary*)currentOperationDictionary {
    
    @synchronized (self) {
        return [[[self.stackArray lastObject] retain] autorelease];
    }
}

static NSString* const SuperThreadProgressKey = @"SuperThreadProgress";
static NSString* const SuperThreadNameKey = @"SuperThreadName";

-(void)enterOperation {
	@synchronized (self) {
        NSNumber* n = [NSNumber numberWithFloat:self.progress];
		[self.stackArray addObject:[NSMutableDictionary dictionary]];
        [self.currentOperationDictionary setObject:n forKey:SuperThreadProgressKey];
        if (self.name) [self.currentOperationDictionary setObject:self.name forKey:SuperThreadNameKey];
		self.progress = -1;
	}
}

-(void)enterOperationIgnoringLowerLevels {
	@synchronized (self) {
		[self enterOperation];
		[self.currentOperationDictionary setObject:[NSNull null] forKey:NSThreadSubRangeKey];
        self.progress = -1;
    }
}

-(void)enterOperationWithRange:(CGFloat)rangeLoc :(CGFloat)rangeLen
{
	@synchronized (self) {
		[self enterOperation];
		[self.currentOperationDictionary setObject:[NSValue valueWithPoint:NSMakePoint(rangeLoc,rangeLen)] forKey:NSThreadSubRangeKey];
		//	NSLog(@"entering level %d subthread", self.subthreadsArray.count);
		self.progress = 0;
	}
}

// The details -progressDetails shows for the operation at `index` when it has
// none of its own: the innermost ones of the operations around it.
static NSString* N2ProgressDetailsAround(NSArray* stack, NSUInteger index) {
	for (NSInteger i = (NSInteger)index-1; i >= 0; --i) {
		NSString* details = [[stack objectAtIndex:i] objectForKey:NSThreadProgressDetailsKey];
		if (details)
			return details;
	}
	return nil;
}

static BOOL N2SameProgressDetails(NSString* a, NSString* b) {
	return a == b || [a isEqualToString:b];
}

-(void)exitOperation {
	@synchronized (self) {
		if (self.stackArray.count > 1) {
            // Leaving an operation shows the details of the one around it again:
            // observers of the details hear of it when what they read changes,
            // as observers of the status do (#626).
            BOOL detailsChange = !N2SameProgressDetails(self.progressDetails, N2ProgressDetailsAround(self.stackArray, self.stackArray.count-1));
            [self willChangeValueForKey:NSThreadStatusKey];
            if (detailsChange) [self willChangeValueForKey:NSThreadProgressDetailsKey];
			NSNumber* temp = [[[self.currentOperationDictionary objectForKey:SuperThreadProgressKey] retain] autorelease];
			NSString* name = [[[self.currentOperationDictionary objectForKey:SuperThreadNameKey] retain] autorelease];
            
            [self.stackArray removeLastObject];
            if (detailsChange) [self didChangeValueForKey:NSThreadProgressDetailsKey];
            [self didChangeValueForKey:NSThreadStatusKey];
            
            self.name = name;
            if (temp) self.progress = temp.floatValue;
            else self.progress = 1;
        }
		self.progress = 1;
	}
}

-(void)enterSubthreadWithRange:(CGFloat)rangeLoc :(CGFloat)rangeLen { // __deprecated
	@synchronized (self) {
		[self enterOperationWithRange:rangeLoc:rangeLen];
	}
}

-(void)exitSubthread { // __deprecated
	[self exitOperation];
}

#pragma mark Properties

NSString* const NSThreadSupportsCancelKey = @"supportsCancel";

-(BOOL)supportsCancel {
	if (self.isFinished)
		return NO;
	if (self.isCancelled)
		return NO;
	
	@synchronized (self) {
		return [[self.currentOperationDictionary objectForKey:NSThreadSupportsCancelKey] boolValue];
	}
	
	return NO;
}

-(void)setSupportsCancel:(BOOL)supportsCancel {
	if (self.isFinished)
		return;
	if (self.isCancelled)
		return;
    
    if ([self isMainThread])
        return;
	
	if (supportsCancel == self.supportsCancel)
		return;
	
	@synchronized (self) {
		[self willChangeValueForKey:NSThreadSupportsCancelKey];
		[self.currentOperationDictionary setObject:[NSNumber numberWithBool:supportsCancel] forKey:NSThreadSupportsCancelKey];
		[self didChangeValueForKey:NSThreadSupportsCancelKey];
	}
}

NSString* const NSThreadSupportsBackgroundingKey = @"supportsBackgrounding";

-(BOOL)supportsBackgrounding {
	@synchronized (self) {
		return [[self.currentOperationDictionary objectForKey:NSThreadSupportsBackgroundingKey] boolValue];
	}
	
	return NO;
}

-(void)setSupportsBackgrounding:(BOOL)supportsBackgrounding {
    if ([self isMainThread])
        return;
	
	if (supportsBackgrounding == self.supportsBackgrounding)
		return;
	
	@synchronized (self) {
		[self willChangeValueForKey:NSThreadSupportsBackgroundingKey];
		[self.currentOperationDictionary setObject:[NSNumber numberWithBool:supportsBackgrounding] forKey:NSThreadSupportsBackgroundingKey];
		[self didChangeValueForKey:NSThreadSupportsBackgroundingKey];
	}
}


NSString* const NSThreadStatusKey = @"status";

-(NSString*)status {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
    
	@synchronized (self) {
		for (int i = (long)self.stackArray.count-1; i >= 0; --i) {
			NSDictionary* d = [self.stackArray objectAtIndex:i];
			NSString* status = [d objectForKey:NSThreadStatusKey];
			if (status)
				return [[status copy] autorelease];
		}
		
		return nil;
	}
	
	return nil;
}

-(void)setStatus:(NSString*)status {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
    
	@synchronized (self) {
		NSString* previousStatus = self.status;
		if (previousStatus == status || [status isEqualToString:previousStatus])
			return;
		
		[self willChangeValueForKey:NSThreadStatusKey];
		if (status)
			[self.currentOperationDictionary setObject:[[status copy] autorelease] forKey:NSThreadStatusKey];
		else [self.currentOperationDictionary removeObjectForKey:NSThreadStatusKey];
		[self didChangeValueForKey:NSThreadStatusKey];
	}
	
}

NSString* const NSThreadProgressKey = @"progress";
NSString* const NSThreadSubthreadsAwareProgressKey = @"subthreadsAwareProgress";

-(CGFloat)progress {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
    
	@synchronized (self) {
		NSNumber* progress = [self.threadDictionary objectForKey:NSThreadProgressKey];
		return progress? progress.floatValue : -1;
	}
	
	return -1;
}

-(void)setProgress:(CGFloat)progress {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
    
	@synchronized (self) {
        if (self.progress == progress)
            return;
        
		[self willChangeValueForKey:NSThreadProgressKey];
		[self willChangeValueForKey:NSThreadSubthreadsAwareProgressKey];
		[self.threadDictionary setObject:[NSNumber numberWithFloat:progress] forKey:NSThreadProgressKey];
		[self didChangeValueForKey:NSThreadProgressKey];
		[self didChangeValueForKey:NSThreadSubthreadsAwareProgressKey];
	}
}

-(CGFloat)subthreadsAwareProgress {
	@synchronized (self) {
		if (self.isFinished)
            return 1;
        CGFloat progress = self.progress;
		if (progress < 0)
			return progress;
		
		NSPoint range = NSMakePoint(0,1);
		for (NSDictionary* i in self.stackArray) {
			NSValue* iv = [i objectForKey:NSThreadSubRangeKey];
			if ([iv isKindOfClass:[NSValue class]]) {
				NSPoint ir = [iv pointValue];
				range = NSMakePoint(range.x+range.y*ir.x, range.y*ir.y);
			} else if ([iv isKindOfClass:[NSNull class]]) {
                range = NSMakePoint(0,1);
            }
		}
		
		return range.x+range.y*self.progress;
	}
	
	return -1;
}

NSString* const NSThreadProgressDetailsKey = @"progressDetails";

-(NSString*)progressDetails {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
    
	@synchronized (self) {
		for (int i = (long)self.stackArray.count-1; i >= 0; --i) {
			NSDictionary* d = [self.stackArray objectAtIndex:i];
			NSString* progressDetails = [d objectForKey:NSThreadProgressDetailsKey];
			if (progressDetails)
				return [[progressDetails copy] autorelease];
		}
		
		return nil;
	}
	
	return nil;
}

-(void)setProgressDetails:(NSString*)progressDetails {
//    if (self.isFinished)
//    	return nil;
//    if (self.isCancelled)
//    	return nil;
    
	@synchronized (self) {
		NSMutableArray* stack = self.stackArray;
		NSMutableDictionary* operation = stack.lastObject;
		if (!operation || N2SameProgressDetails([operation objectForKey:NSThreadProgressDetailsKey], progressDetails))
			return;

		// Observers hear of a change when what -progressDetails returns changes
		// (#626). The details used to be compared with the status instead, which
		// dropped a detail that read like the status and repeated an unchanged
		// one; and nil in a nested operation shows the details around it.
		NSString* next = progressDetails? progressDetails : N2ProgressDetailsAround(stack, stack.count-1);
		BOOL change = !N2SameProgressDetails(self.progressDetails, next);

		if (change) [self willChangeValueForKey:NSThreadProgressDetailsKey];
		if (progressDetails)
			[operation setObject:[[progressDetails copy] autorelease] forKey:NSThreadProgressDetailsKey];
		else [operation removeObjectForKey:NSThreadProgressDetailsKey];
		if (change) [self didChangeValueForKey:NSThreadProgressDetailsKey];
	}
	
}

@end

@implementation N2BlockThread

-(id)initWithBlock:(void(^)())block
{
    if ((self = [super init]))
    {
        _block = [block copy];
    }
    
    return self;
}

-(void)main
{
    @autoreleasepool
    {
        @try
        {
            _block();
        }
        @catch (NSException* e)
        {
            N2LogExceptionWithStackTrace(e);
        }
        @finally
        {
            [_block release];
            _block = nil;
        }
    }
}


-(void)dealloc
{
    [_block release];
    _block = nil;
    
    [super dealloc];
}

@end

