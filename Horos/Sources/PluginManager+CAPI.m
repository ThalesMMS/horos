/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation, ùversion 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE. ùSee the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos. ùIf not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program: ù OsiriX
 ùCopyright (c) OsiriX Team
 ùAll rights reserved.
 ùDistributed under GNU - LGPL
 ù
 ùSee http://www.osirix-viewer.com/copyright.html for details.
 ù ù This software is distributed WITHOUT ANY WARRANTY; without even
 ù ù the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
 ù ù PURPOSE.
 ============================================================================*/

// The part of PluginManager that stays in Objective-C. The class is implemented
// in Swift since #720 (PluginManager.swift). Here are:
// - gPluginsAlertAlreadyDisplayed and sortPluginArray, which the former
//   PluginManager.m defined and the executable exports;
// - the plugin helpers of HorosPluginLoadDiagnostics.h, HorosPluginSignature.h,
//   HorosPluginInstall.h and HorosPluginCatalogTransport.h, which those headers
//   define as static functions for manual retain/release, called through
//   functions Swift can reach. This file is their only includer in the app, so
//   the load outcomes are recorded and read in one dictionary, as they were in
//   PluginManager.m;
// - -[NSBundle loadAndReturnError:] and -preflightAndReturnError:, called with
//   the error pointer, so a failure without an error still leaves it nil.
// PluginManager.h declares these functions to Swift, under HOROS_BRIDGING_HEADER.

#import <Foundation/Foundation.h>
#import "HorosPluginCatalogTransport.h"
#import "HorosPluginLoadDiagnostics.h"
#import "HorosPluginSignature.h"
#import "HorosPluginInstall.h"

extern BOOL gPluginsAlertAlreadyDisplayed;
NSInteger sortPluginArray(id plugin1, id plugin2, void *context);
void PluginManagerCAPIRecordLoad(NSString *path, NSString *state, NSString *reason);
NSDictionary *PluginManagerCAPILoadOutcome(NSString *path, BOOL active);
BOOL PluginManagerCAPISignatureAllowsLoading(NSString *path, NSError **error);
BOOL PluginManagerCAPIInstallPlugin(NSString *source, NSString *destination, NSError **error);
NSArray *PluginManagerCAPILoadCatalog(NSURL *url, NSTimeInterval timeout, NSError **error);
NSString *PluginManagerCAPIDownloadName(id plugin);
BOOL PluginManagerCAPIVersionIsValid(id version);
NSComparisonResult PluginManagerCAPICompareVersions(id left, id right);
BOOL PluginManagerCAPILoadBundle(NSBundle *bundle, NSError **error);
BOOL PluginManagerCAPIPreflightBundle(NSBundle *bundle, NSError **error);

__attribute__((used)) BOOL gPluginsAlertAlreadyDisplayed = NO;

NSInteger sortPluginArray(id plugin1, id plugin2, void *context)
{
    NSString *name1 = [plugin1 objectForKey:@"name"];
    NSString *name2 = [plugin2 objectForKey:@"name"];
    
	return [name1 compare:name2 options: NSCaseInsensitiveSearch];
}

void PluginManagerCAPIRecordLoad(NSString *path, NSString *state, NSString *reason)
{
    HorosRecordPluginLoad(path, state, reason);
}

NSDictionary *PluginManagerCAPILoadOutcome(NSString *path, BOOL active)
{
    return HorosPluginLoadOutcome(path, active);
}

BOOL PluginManagerCAPISignatureAllowsLoading(NSString *path, NSError **error)
{
    return HorosPluginSignatureAllowsLoading(path, error);
}

BOOL PluginManagerCAPIInstallPlugin(NSString *source, NSString *destination, NSError **error)
{
    return HorosInstallPlugin(source, destination, error);
}

NSArray *PluginManagerCAPILoadCatalog(NSURL *url, NSTimeInterval timeout, NSError **error)
{
    return HorosLoadPluginCatalog(url, timeout, error);
}

NSString *PluginManagerCAPIDownloadName(id plugin)
{
    return HorosPluginDownloadName(plugin);
}

BOOL PluginManagerCAPIVersionIsValid(id version)
{
    return HorosPluginVersionIsValid(version);
}

NSComparisonResult PluginManagerCAPICompareVersions(id left, id right)
{
    return HorosComparePluginVersions(left, right);
}

BOOL PluginManagerCAPILoadBundle(NSBundle *bundle, NSError **error)
{
    #ifdef MACAPPSTORE
    return NO;
#else
    return [bundle loadAndReturnError:error];
#endif
}

BOOL PluginManagerCAPIPreflightBundle(NSBundle *bundle, NSError **error)
{
    #ifdef MACAPPSTORE
    return NO;
#else
    return [bundle preflightAndReturnError:error];
#endif
}
