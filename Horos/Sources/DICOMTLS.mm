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

#import "DICOMTLS.h"
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmtls/tlsciphr.h>

@implementation DICOMTLS

#pragma mark Cipher Suites

+ (NSArray*)availableCipherSuites;
{
    NSMutableArray *cipherSuites = [NSMutableArray array];
    for (size_t index = 0; index < DcmTLSCiphersuiteHandler::getNumberOfCipherSuites(); ++index)
    {
        const char *name = DcmTLSCiphersuiteHandler::getTLSCipherSuiteName(index);
        if (name) [cipherSuites addObject:[NSString stringWithUTF8String:name]];
    }
	return cipherSuites;
}

+ (NSArray*)defaultCipherSuites;
{
	NSArray *availableCipherSuites = [DICOMTLS availableCipherSuites];
	NSMutableArray *cipherSuites = [NSMutableArray arrayWithCapacity:[availableCipherSuites count]];
	
	for (NSString *suite in availableCipherSuites)
	{
		[cipherSuites addObject:[NSMutableDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithBool:NO], @"Supported", suite, @"Cipher", nil]];
	}
	
	return [NSArray arrayWithArray:cipherSuites];
}

#pragma mark Keychain Access

static NSMutableString *TLS_PRIVATE_KEY_PASSWORD = nil;

+ (void) eraseKeys
{
    for( NSString *path in [[NSFileManager defaultManager] contentsOfDirectoryAtPath: @"/tmp" error: nil])
    {
        path = [@"/tmp/" stringByAppendingPathComponent: path];
        
        if( [path hasPrefix: TLS_SEED_FILE] || [path hasPrefix: [NSString stringWithUTF8String: TLS_WRITE_SEED_FILE]] || [path hasPrefix: TLS_PRIVATE_KEY_FILE] || [path hasPrefix: TLS_CERTIFICATE_FILE] || [path hasPrefix: TLS_TRUSTED_CERTIFICATES_DIR])
        {
            [[NSFileManager defaultManager] removeItemAtPath: path error: nil];
        }
    }
}

+ (NSString*) TLS_PRIVATE_KEY_PASSWORD
{
    if( TLS_PRIVATE_KEY_PASSWORD == nil)
    {
        NSString *letters = @"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
        
        TLS_PRIVATE_KEY_PASSWORD = [[NSMutableString string] retain];
        
        for (int i=0; i<10; i++) {
            [TLS_PRIVATE_KEY_PASSWORD appendFormat: @"%C", [letters characterAtIndex: arc4random() % [letters length]]];
        }
    }
    
    return TLS_PRIVATE_KEY_PASSWORD;
}

+ (void)generateCertificateAndKeyForLabel:(NSString*)label withStringID:(NSString*)stringID;
{	
	SecIdentityRef identity = [DDKeychain identityForLabel:label];
	if( identity)
	{
		// identity to certificate
		[DDKeychain KeychainAccessExportCertificateForIdentity:identity toPath:[[DICOMTLS certificatePathForLabel:label] stringByAppendingFormat:@"%@", stringID]];
		// identity to private key
		[DDKeychain KeychainAccessExportPrivateKeyForIdentity:identity toPath:[[DICOMTLS keyPathForLabel:label] stringByAppendingFormat:@"%@", stringID] cryptWithPassword: [DICOMTLS TLS_PRIVATE_KEY_PASSWORD]];
		CFRelease(identity);
	}
}

+ (void)generateCertificateAndKeyForLabel:(NSString*)label;
{
	[DICOMTLS generateCertificateAndKeyForLabel:label withStringID:@""];
}

+ (void)generateCertificateAndKeyForServerAddress:(NSString*)address port:(int)port AETitle:(NSString*)aetitle withStringID:(NSString*)stringID;
{	
	[DICOMTLS generateCertificateAndKeyForLabel:[DICOMTLS uniqueLabelForServerAddress:address port:[NSString stringWithFormat:@"%d",port] AETitle:aetitle] withStringID:stringID];
}

+ (void)generateCertificateAndKeyForServerAddress:(NSString*)address port:(int)port AETitle:(NSString*)aetitle;
{	
	[DICOMTLS generateCertificateAndKeyForServerAddress:address port:port AETitle:aetitle withStringID:@""];
}

+ (NSString*)uniqueLabelForServerAddress:(NSString*)address port:(NSString*)port AETitle:(NSString*)aetitle;
{
	NSMutableString *label = [NSMutableString string];
	[label appendString:TLS_KEYCHAIN_IDENTITY_NAME_CLIENT];
	[label appendString:@"."];
	[label appendString:address];
	[label appendString:@"."];
	[label appendString:port];
	[label appendString:@"."];
	[label appendString:aetitle];
	
	return [NSString stringWithString:label];
}

+ (NSString*)keyPathForLabel:(NSString*)label withStringID:(NSString*)stringID;
{
	return [NSString stringWithFormat:@"%@.%@.%@", TLS_PRIVATE_KEY_FILE, label, stringID];
}

+ (NSString*)keyPathForLabel:(NSString*)label;
{
	return [DICOMTLS keyPathForLabel:label withStringID:@""];
}

+ (NSString*)keyPathForServerAddress:(NSString*)address port:(int)port AETitle:(NSString*)aetitle withStringID:(NSString*)stringID;
{
	return [DICOMTLS keyPathForLabel:[DICOMTLS uniqueLabelForServerAddress:address port:[NSString stringWithFormat:@"%d",port] AETitle:aetitle] withStringID:stringID];
}

+ (NSString*)keyPathForServerAddress:(NSString*)address port:(int)port AETitle:(NSString*)aetitle;
{
	return [DICOMTLS keyPathForServerAddress:address port:port AETitle:aetitle withStringID:@""];
}

+ (NSString*)certificatePathForLabel:(NSString*)label withStringID:(NSString*)stringID;
{
	return [NSString stringWithFormat:@"%@.%@.%@", TLS_CERTIFICATE_FILE, label, stringID];
}

+ (NSString*)certificatePathForLabel:(NSString*)label;
{
	return [DICOMTLS certificatePathForLabel:label withStringID:@""];
}

+ (NSString*)certificatePathForServerAddress:(NSString*)address port:(int)port AETitle:(NSString*)aetitle withStringID:(NSString*)stringID;
{
	return [DICOMTLS certificatePathForLabel:[DICOMTLS uniqueLabelForServerAddress:address port:[NSString stringWithFormat:@"%d",port] AETitle:aetitle] withStringID:stringID];
}

+ (NSString*)certificatePathForServerAddress:(NSString*)address port:(int)port AETitle:(NSString*)aetitle
{
	return [DICOMTLS certificatePathForServerAddress:address port:port AETitle:aetitle withStringID:@""];
}

@end
