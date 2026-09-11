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

#import "WebPortalSession.h"
#import "Horos-Swift.h"


NSString* const SessionCookieName = @"OSID";
NSString* const SessionUserIDKey = @"UserID"; // NSManagedObjectID
NSString* const SessionUsernameKey = @"Username"; // NSString
NSString* const SessionTokensDictKey = @"Tokens"; // NSMutableDictionary
NSString* const SessionChallengeKey = @"Challenge"; // NSString
NSString* const SessionLastActivityDateKey = @"LastActivityDate"; // NSDate

@implementation WebPortalSession

@synthesize sid, dict;

-(id)initWithId:(NSString*)isid {
	self = [super init];
	sid = [isid retain];
	dictLock = [[NSLock alloc] init];
	dict = [[NSMutableDictionary alloc] initWithCapacity:8];
	return self;
}

-(void)dealloc {
	[dict release];
	[sid release];
	[dictLock release];
	[super dealloc];
}


-(void)setObject:(id)o forKey:(NSString*)k {
	[dictLock lock];
	if (o) [dict setObject:o forKey:k];
	else [dict removeObjectForKey:k];
	[dictLock unlock];
}

-(id)objectForKey:(NSString*)k {
	[dictLock lock];
	id value = [dict objectForKey:k];
	[dictLock unlock];
	return value;
}

-(id)valueForKey:(NSString*)key {
	return [self objectForKey:key];
}

-(NSMutableDictionary*)tokensDictionary {
	[dictLock lock];
	NSMutableDictionary* tdict = [dict objectForKey:SessionTokensDictKey];
	if (!tdict) [dict setObject: tdict = [NSMutableDictionary dictionary] forKey:SessionTokensDictKey];
	[dictLock unlock];
	return tdict;
}

-(NSString*)createToken {
	NSMutableDictionary* tokensDictionary = [self tokensDictionary];
	[dictLock lock];
	
	// A token authorises a Weasis launch on this session's behalf. It used to be
	// the MD5 of the instant it was created, so guessing it meant guessing when it
	// was made rather than searching the 128 bits its length suggests. The loop
	// stays as the invariant it always was - two live tokens are never equal - and
	// with random bytes it ends on the first pass.
	NSString* token;
	do {
		token = [HorosWebPortalIdentifier unguessable];
	} while ([tokensDictionary objectForKey: token] != nil);
	
	[tokensDictionary setObject:[NSDate date] forKey:token];
	
	[dictLock unlock];
	return token;
}

-(BOOL)containsToken:(NSString*)token {
	NSMutableDictionary* tokensDictionary = [self tokensDictionary];
	[dictLock lock];
	
	NSDate *date = [tokensDictionary objectForKey: token];
	BOOL ok = NO;
    if( date)
    {
        if( [date timeIntervalSinceNow] > -30*60) // Token are valid for 30 min
            ok = YES;
        else
            [tokensDictionary removeObjectForKey:token];
    }
    
	[dictLock unlock];
	return ok;
}

-(BOOL)consumeToken:(NSString*)token {
	NSMutableDictionary* tokensDictionary = [self tokensDictionary];
	[dictLock lock];
	
	NSDate *date = [tokensDictionary objectForKey: token];
	BOOL ok = NO;
    if( date)
    {
        if( [date timeIntervalSinceNow] > -30*60) // Token are valid for 30 min
            ok = YES;
        
        [tokensDictionary removeObjectForKey:token];
    }
	
	[dictLock unlock];
	return ok;
}

-(NSString*)newChallenge {
	// Built the same way as the token was, and replaced for the same reason.
	NSString* challenge = [HorosWebPortalIdentifier unguessable];
	[dict setObject:challenge forKey:SessionChallengeKey];
	return challenge;
}

-(NSString*)challenge {
	return [self objectForKey:SessionChallengeKey];
}

-(void)deleteChallenge {
	return [dict removeObjectForKey:SessionChallengeKey];
}



@end
