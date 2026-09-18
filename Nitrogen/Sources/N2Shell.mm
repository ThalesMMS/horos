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


#import "N2Shell.h"
#import <IOKit/IOTypes.h>


@implementation N2Shell

+(NSString*)execute:(NSString*)path {
	return [N2Shell execute:path arguments:NULL];
}

+(NSString*)execute:(NSString*)path arguments:(NSArray*)arguments {
	return [N2Shell execute:path arguments:arguments expectedStatus:0];
}

+(NSString*)execute:(NSString*)path arguments:(NSArray*)arguments outStatus:(int*)outStatus {
	if (!arguments) arguments = [NSArray array];
	
//	int r = random();
//	NSLog(@"%d [N2Shell execute:] %@ %@", r, path, [arguments componentsJoinedByString:@" "]);
	
	NSTask* task = [[[NSTask alloc] init] autorelease];
	[task setLaunchPath:path];
	[task setArguments:arguments];
	[task setStandardOutput:[NSPipe pipe]];
	[task setStandardError:[NSPipe pipe]];
	
	[task launch];
	while( [task isRunning])
        [NSThread sleepForTimeInterval: 0.1];
    
    //[aTask waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
	
	NSString* stdout = [[[[NSString alloc] initWithData:[[[task standardOutput] fileHandleForReading] readDataToEndOfFile] encoding:NSUTF8StringEncoding] autorelease] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
//	NSString* stderr = [[[[NSString alloc] initWithData:[[[task standardError] fileHandleForReading] readDataToEndOfFile] encoding:NSUTF8StringEncoding] autorelease] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
	
//	
//	NSLog(@"%d STDOUT:\n\n%@\n\n", r, stdout);
//	NSLog(@"%d STDERR:\n\n%@\n\n", r, stderr);
	
	if (outStatus)
		*outStatus = [task terminationStatus];
	
	return stdout;
}

+(NSString*)execute:(NSString*)path arguments:(NSArray*)arguments expectedStatus:(int)expectedStatus {
	int status;
	NSString* r = [self execute:path arguments:arguments outStatus:&status];
	
	if (status != expectedStatus)
		[NSException raise:NSGenericException format:@"Task %@ exited with status %d", path, status];
	
	return r;
}

+(NSString*)hostname {
	char hostname[128];
	gethostname(hostname, 127);
	hostname[127] = 0;
	return [NSString stringWithCString:hostname encoding:NSUTF8StringEncoding];
}

+(NSString*)serialNumber {
    io_service_t platformExpert = IOServiceGetMatchingService(kIOMasterPortDefault, IOServiceMatching("IOPlatformExpertDevice"));
    if (platformExpert) {
        NSString* serialNumber = [(NSString*)IORegistryEntryCreateCFProperty(platformExpert, CFSTR(kIOPlatformSerialNumberKey), kCFAllocatorDefault, 0) autorelease];
        IOObjectRelease(platformExpert);
        return serialNumber;
    }
    
    return nil;
}

@end
