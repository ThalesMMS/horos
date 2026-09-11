/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation, version 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE. See the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos. If not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program:  OsiriX
 Copyright (c) OsiriX Team
 All rights reserved.
 Distributed under GNU - LGPL
 
 See http://www.osirix-viewer.com/copyright.html for details.
   This software is distributed WITHOUT ANY WARRANTY; without even
   the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
   PURPOSE.
 ============================================================================*/


#import "PluginManager.h"
#import "HorosPluginCatalogTransport.h"
#import "HorosPluginLoadDiagnostics.h"
#import "HorosPluginSignature.h"
#import "HorosPluginInstall.h"
#import "AppController.h"
#import "BrowserController.h"
#import "BLAuthentication.h"
#import "PluginManagerController.h"
#import "Notifications.h"
#import "NSFileManager+N2.h"
#import "NSString+SymlinksAndAliases.h"
#import "Horos-Swift.h"
#import "NSMutableDictionary+N2.h"
#import "PreferencesWindowController.h"
#import "N2Debug.h"
#import "url.h"
#import "NSString+SymlinksAndAliases.h"

static NSMutableDictionary		*plugins = nil, *pluginsDict = nil, *fileFormatPlugins = nil;
static NSMutableDictionary		*reportPlugins = nil, *pluginsBundleDictionnary = nil;

static NSMutableArray			*preProcessPlugins = nil;
static NSMenu					*fusionPluginsMenu = nil;
static NSMutableArray			*fusionPlugins = nil;
static NSMutableDictionary		*pluginsNames = nil;
static BOOL						ComPACSTested = NO, isComPACS = NO;

BOOL gPluginsAlertAlreadyDisplayed = NO;

@interface PluginManager (Dummy)

- (void)executeFilter:(id)sender;

@end

@implementation PluginManager

@synthesize downloadQueue;

+ (void) startProtectForCrashWithFilter: (id) filter
{
//    *(long*)0 = 0xDEADBEEF;
    
    for( NSBundle *bundle in [pluginsBundleDictionnary allValues])
    {
        if( [NSStringFromClass( [filter class]) isEqualToString: NSStringFromClass( [bundle principalClass])])
        {
            [PluginManager startProtectForCrashWithPath: [bundle bundlePath]];
           
//            *(long*)0 = 0xDEADBEEF;
            
            return;
        }
    }
    
    // principalClass belongs to NSBundle, and this argument is the filter the
    // loop above compares by -class. Asking the filter for it raised
    // NSInvalidArgumentException out of applicationWillFinishLaunching:, which
    // silently skipped DCMTK, the store SCP, the database and browser classes,
    // the Web Portal, the Bonjour publisher and the XML-RPC interface.
    NSLog( @"***** unknown plugin - startProtectForCrashWithFilter - %@", NSStringFromClass( [filter class]));
}

+ (NSString*) crashMarkerPath
{
    // Beside the plugins themselves, not in /tmp: that one is writable by
    // everybody on the machine and shared by every Horos and OsiriX on it.
    NSString *directory = [[PluginManager userActivePluginsDirectoryPath] stringByDeletingLastPathComponent];
    return [HorosPluginQuarantine markerPathInDirectory: directory
                                              forBundle: [[NSBundle mainBundle] bundleIdentifier]];
}

+ (void) startProtectForCrashWithPath: (NSString*) path
{
    NSString *marker = [PluginManager crashMarkerPath];
    [[NSFileManager defaultManager] createDirectoryAtPath: [marker stringByDeletingLastPathComponent]
                              withIntermediateDirectories: YES attributes: nil error: NULL];
    [path writeToFile: marker atomically: YES encoding: NSUTF8StringEncoding error: nil];
}

+ (void) endProtectForCrash
{
    [[NSFileManager defaultManager] removeItemAtPath: [PluginManager crashMarkerPath] error: nil];
}

+ (int) compareVersion:(NSString*)v1 withVersion:(NSString*)v2
{
    return (int)HorosComparePluginVersions(v1, v2);
}

+ (BOOL) isComPACS
{
	if( ComPACSTested == NO)
	{
		ComPACSTested = YES;
		
		if( [[PluginManager plugins] valueForKey:@"ComPACS"])
			isComPACS = YES;
		else
			isComPACS = NO;
	}
	return isComPACS;
}

+ (NSMutableDictionary*) plugins
{
	return plugins;
}

+ (NSMutableDictionary*) pluginsDict
{
	return pluginsDict;
}

+ (NSMutableDictionary*) fileFormatPlugins
{
	return fileFormatPlugins;
}

+ (NSMutableDictionary*) reportPlugins
{
	return reportPlugins;
}

+ (NSArray*) preProcessPlugins
{
	return preProcessPlugins;
}

+ (NSMenu*) fusionPluginsMenu
{
	return fusionPluginsMenu;
}

+ (NSArray*) fusionPlugins
{
	return fusionPlugins;
}

#ifdef OSIRIX_VIEWER

+(void)sortMenu:(NSMenu*)menu
{
    // [CH] Get an array of all menu items.
    NSArray* items = [menu itemArray];
    [menu removeAllItems];
    // [CH] Sort the array
    items = [items sortedArrayUsingDescriptors:[NSArray arrayWithObjects:[NSSortDescriptor sortDescriptorWithKey:@"title" ascending:YES selector:@selector(localizedCaseInsensitiveCompare:)], nil]];
    // [CH] ok, now set it back.
    for(NSMenuItem* item in items)
    {
        [menu addItem:item];
        /**
         * [CH] The following code fixes NSPopUpButton's confusion that occurs when
         * we sort this list. NSPopUpButton listens to the NSMenu's add notifications
         * and hides the first item. Sorting this blows it up.
         **/
        if(item.isHidden){
            [item setHidden: false];
        }
    }
}



+ (void) setMenus:(NSMenu*) filtersMenu :(NSMenu*) roisMenu :(NSMenu*) othersMenu :(NSMenu*) dbMenu
{
    [filtersMenu removeAllItems];
    [roisMenu removeAllItems];
    [othersMenu removeAllItems];
    [dbMenu removeAllItems];
	
	NSEnumerator *enumerator = [pluginsDict objectEnumerator];
	NSBundle *plugin;
	
	while ((plugin = [enumerator nextObject]))
	{
		NSString	*pluginName = [[plugin infoDictionary] objectForKey:@"CFBundleExecutable"];
		NSString	*pluginType = [[plugin infoDictionary] objectForKey:@"pluginType"];
		NSArray		*menuTitles = [[plugin infoDictionary] objectForKey:@"MenuTitles"];
		
        [PluginManager startProtectForCrashWithPath: [plugin bundlePath]];
        
		if( menuTitles)
		{
			if( [menuTitles count] > 1)
			{
				// Create a sub menu item
				
				NSMenu  *subMenu = [[[NSMenu alloc] initWithTitle: pluginName] autorelease];
				
				for( NSString *menuTitle in menuTitles)
				{
					NSMenuItem *item;
					
					if ([menuTitle isEqual:@"(-"])
					{
						item = [NSMenuItem separatorItem];
					}
					else
					{
						item = [[[NSMenuItem alloc] init] autorelease];
						[item setTitle:menuTitle];
						
						if( [pluginType rangeOfString: @"fusionFilter"].location != NSNotFound)
						{
							[fusionPlugins addObject:[item title]];
							[item setAction:@selector(endBlendingType:)];
						}
						else if( [pluginType rangeOfString: @"Database"].location != NSNotFound || [pluginType rangeOfString: @"Report"].location != NSNotFound)
						{
							[item setTarget: [BrowserController currentBrowser]];	//  browserWindow responds to DB plugins
							[item setAction:@selector(executeFilterDB:)];
						}
						else
						{
							[item setTarget:nil];	// FIRST RESPONDER !
							[item setAction:@selector(executeFilter:)];
						}
 					}
					
					[subMenu insertItem:item atIndex:[subMenu numberOfItems]];
				}
				
				// Only assigned when the item is new. When the menu already carries
				// this plugin name the setRepresentedObject: below still runs, and
				// without this it wrote through an uninitialised pointer; nil makes
				// that path the no-op that leaving the existing item alone implies.
				id  subMenuItem = nil;
				
				if( [pluginType rangeOfString: @"imageFilter"].location != NSNotFound)
				{
					if( [filtersMenu indexOfItemWithTitle: pluginName] == -1)
					{
						subMenuItem = [filtersMenu insertItemWithTitle:pluginName action:nil keyEquivalent:@"" atIndex:[filtersMenu numberOfItems]];
						[filtersMenu setSubmenu:subMenu forItem:subMenuItem];
					}
				}
				else if( [pluginType rangeOfString: @"roiTool"].location != NSNotFound)
				{
					if( [roisMenu indexOfItemWithTitle: pluginName] == -1)
					{
						subMenuItem = [roisMenu insertItemWithTitle:pluginName action:nil keyEquivalent:@"" atIndex:[roisMenu numberOfItems]];
						[roisMenu setSubmenu:subMenu forItem:subMenuItem];
					}
				}
				else if( [pluginType rangeOfString: @"fusionFilter"].location != NSNotFound)
				{
					if( [fusionPluginsMenu indexOfItemWithTitle: pluginName] == -1)
					{
						subMenuItem = [fusionPluginsMenu insertItemWithTitle:pluginName action:nil keyEquivalent:@"" atIndex:[fusionPluginsMenu numberOfItems]];
						[fusionPluginsMenu setSubmenu:subMenu forItem:subMenuItem];
					}
				}
				else if( [pluginType rangeOfString: @"Database"].location != NSNotFound)
				{
					if( [dbMenu indexOfItemWithTitle: pluginName] == -1)
					{
						subMenuItem = [dbMenu insertItemWithTitle:pluginName action:nil keyEquivalent:@"" atIndex:[dbMenu numberOfItems]];
						[dbMenu setSubmenu:subMenu forItem:subMenuItem];
					}
				} 
				else
				{
					if( [othersMenu indexOfItemWithTitle: pluginName] == -1)
					{
						subMenuItem = [othersMenu insertItemWithTitle:pluginName action:nil keyEquivalent:@"" atIndex:[othersMenu numberOfItems]];
						[othersMenu setSubmenu:subMenu forItem:subMenuItem];
					}
				}
                
                [subMenuItem setRepresentedObject:plugin];
			}
			else
			{
				// Create a menu item
				
				NSMenuItem *item = [[[NSMenuItem alloc] init] autorelease];
				
				[item setTitle: [menuTitles objectAtIndex: 0]];	//pluginName];
                [item setRepresentedObject:plugin];
				
				if( [pluginType rangeOfString: @"fusionFilter"].location != NSNotFound)
				{
					[fusionPlugins addObject:[item title]];
					[item setAction:@selector(endBlendingType:)];
				}
				else if( [pluginType rangeOfString: @"Database"].location != NSNotFound || [pluginType rangeOfString: @"Report"].location != NSNotFound)
				{
					[item setTarget:[BrowserController currentBrowser]];	//  browserWindow responds to DB plugins
					[item setAction:@selector(executeFilterDB:)];
				}
				else
				{
					[item setTarget:nil];	// FIRST RESPONDER !
					[item setAction:@selector(executeFilter:)];
				}
				
				if( [pluginType rangeOfString: @"imageFilter"].location != NSNotFound)
					[filtersMenu insertItem:item atIndex:[filtersMenu numberOfItems]];
				
				else if( [pluginType rangeOfString: @"roiTool"].location != NSNotFound)
					[roisMenu insertItem:item atIndex:[roisMenu numberOfItems]];
				
				else if( [pluginType rangeOfString: @"fusionFilter"].location != NSNotFound)
					[fusionPluginsMenu insertItem:item atIndex:[fusionPluginsMenu numberOfItems]];
				
				else if( [pluginType rangeOfString: @"Database"].location != NSNotFound)
					[dbMenu insertItem:item atIndex:[dbMenu numberOfItems]];
				
				else
					[othersMenu insertItem:item atIndex:[othersMenu numberOfItems]];
			}
		}
        
        [PluginManager endProtectForCrash];
	}
	
	if( [filtersMenu numberOfItems] < 1)
	{
		NSMenuItem *item = [[[NSMenuItem alloc] init] autorelease];
		[item setTitle:NSLocalizedString(@"No plugins available for this menu", nil)];
		[item setTarget:self];
		[item setAction:@selector(noPlugins:)]; 
		
		[filtersMenu insertItem:item atIndex:0];
	}
	
	if( [roisMenu numberOfItems] < 1)
	{
		NSMenuItem *item = [[[NSMenuItem alloc] init] autorelease];
		[item setTitle:NSLocalizedString(@"No plugins available for this menu", nil)];
		[item setTarget:self];
		[item setAction:@selector(noPlugins:)];
		
		[roisMenu insertItem:item atIndex:0];
	}
	
	if( [othersMenu numberOfItems] < 1)
	{
		NSMenuItem *item = [[[NSMenuItem alloc] init] autorelease];
		[item setTitle:NSLocalizedString(@"No plugins available for this menu", nil)];
		[item setTarget:self];
		[item setAction:@selector(noPlugins:)];
		
		[othersMenu insertItem:item atIndex:0];
	}
	
	if( [fusionPluginsMenu numberOfItems] <= 1)
	{
		NSMenuItem *item = [[[NSMenuItem alloc] init] autorelease];
		[item setTitle:NSLocalizedString(@"No plugins available for this menu", nil)];
		[item setTarget:self];
		[item setAction:@selector(noPlugins:)];
		
		[fusionPluginsMenu removeItemAtIndex: 0];
		[fusionPluginsMenu insertItem:item atIndex:0];
	}
	
	if( [dbMenu numberOfItems] < 1)
	{
		NSMenuItem *item = [[[NSMenuItem alloc] init] autorelease];
		[item setTitle:NSLocalizedString(@"No plugins available for this menu", nil)];
		[item setTarget:self];
		[item setAction:@selector(noPlugins:)];
		
		[dbMenu insertItem:item atIndex:0];
	}
	
    [PluginManager sortMenu: dbMenu];
    [PluginManager sortMenu: roisMenu];
    [PluginManager sortMenu: filtersMenu];
    [PluginManager sortMenu: othersMenu];
    
	NSEnumerator *pluginEnum = [plugins objectEnumerator];
	PluginFilter *pluginFilter;
	
	while( pluginFilter = [pluginEnum nextObject])
    {
        [PluginManager startProtectForCrashWithFilter: pluginFilter];
        
        @try
        {
            [pluginFilter setMenus];
        }
        @catch (NSException *e)
        {
            NSLog( @"***** exception in %s: %@", __PRETTY_FUNCTION__, e);
        }
        
        [PluginManager endProtectForCrash];
	}

    NSMutableArray *shortcutMenus = [NSMutableArray arrayWithObjects: filtersMenu, roisMenu, othersMenu, dbMenu, nil];
    if (fusionPluginsMenu)
        [shortcutMenus addObject: fusionPluginsMenu];
    if ([NSApp mainMenu])
        [shortcutMenus addObject: [NSApp mainMenu]];
    [HorosMenuShortcutCatalog applyStoredAssignmentsToMenus: shortcutMenus];
}



- (id)init
{
	if (self = [super init])
	{
		// Set DefaultROINames *before* initializing plugins (which may change these)
		
		NSMutableArray *defaultROINames = [NSMutableArray array];
		
		[defaultROINames addObject:@"ROI 1"];
		[defaultROINames addObject:@"ROI 2"];
		[defaultROINames addObject:@"ROI 3"];
		[defaultROINames addObject:@"ROI 4"];
		[defaultROINames addObject:@"ROI 5"];
		
		[ViewerController setDefaultROINames: defaultROINames];
		
		[PluginManager discoverPlugins];
		
		[[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(downloadNext:)
                                                     name:AppPluginDownloadInstallDidFinishNotification
                                                   object:nil];
	}
	return self;
}

+ (NSString*) pathResolved:(NSString*) inPath
{
    return [inPath stringByResolvingAlias];
}

+ (void) releaseInstanciedObjectsOfClass: (Class) class
{
    for( int i = 0; i < [preProcessPlugins count]; i++)
    {
        if( [[preProcessPlugins objectAtIndex: i] class] == class)
        {
            NSObject *filter = [preProcessPlugins objectAtIndex: i];
            
            if( [filter respondsToSelector: @selector(willUnload)])
                [filter performSelector: @selector(willUnload)];
            
            [preProcessPlugins removeObjectAtIndex: i];
            i--;
        }
    }
    
    for( NSString *key in [plugins allKeys])
    {
        if( [[plugins valueForKey: key] class] == class)
        {
            NSObject *filter = [plugins valueForKey: key];
            
            if( [filter respondsToSelector: @selector(willUnload)])
                [filter performSelector: @selector(willUnload)];
            
            [plugins removeObjectForKey: key];
        }
    }
}



+ (void) unloadPluginBundle:(NSBundle*) bundle
{
//    NSLog( @"--- will unloadplugin: %@", [bundle bundlePath]);
//    @try
//    {
//        [PluginManager startProtectForCrashWithPath: [bundle bundlePath]];
//        
//        Class filterClass = [bundle principalClass];
//                
//        [PluginManager releaseInstanciedObjectsOfClass: filterClass];
//        
//        [PreferencesWindowController removePluginPaneWithBundle: bundle];
//        
//        [pluginsNames removeObjectForKey: [[[bundle bundlePath] lastPathComponent] stringByDeletingPathExtension]];
//        [fileFormatPlugins removeObject: bundle];
//        [pluginsDict removeObject: bundle];
//        [reportPlugins removeObject: bundle];
//        
//        [PluginManager endProtectForCrash];
//        
//        if( [bundle unload] == NO) unload crash, if KVO Bindings is used in a plugin...
//        {
//            NSLog( @"***** failed to unload plugin: %@", [bundle bundlePath]);
//        }
//        else
//        {
//            for( NSString *key in [pluginsBundleDictionnary allKeys])
//            {
//                if( [pluginsBundleDictionnary valueForKey: key] == bundle)
//                {
//                    [pluginsBundleDictionnary removeObjectForKey: key];
//                    return;
//                }
//            }
//        }
//    }
//    @catch (NSException *e)
//    {
//        NSLog( @"***** exception in %s: %@", __PRETTY_FUNCTION__, e);
//    }
}


+ (void) unloadPluginWithName: (NSString*) name
{
    for( NSBundle *bundle in [pluginsBundleDictionnary allValues])
    {
        if( [[[[bundle bundlePath] lastPathComponent] stringByDeletingPathExtension] isEqualToString: name])
            [PluginManager unloadPluginBundle:bundle];
    }
}


+ (BOOL) isPluginBundleSignatureValid:(NSString*) path
{
    NSError *error = nil;
    BOOL allowed = HorosPluginSignatureAllowsLoading(path, &error);
    if (!allowed) {
        NSString *reason = [NSString stringWithFormat:NSLocalizedString(@"The plugin signature is invalid: %@. Reinstall an intact copy from its author.", nil), error.localizedDescription];
        HorosRecordPluginLoad([path stringByResolvingAlias], NSLocalizedString(@"Blocked", nil), reason);
        NSLog(@"Plugin signature validation failed (%@ %ld): %@", error.domain, (long)error.code, reason);
    }
    return allowed;
}


+ (void) loadPluginBundle:(NSString*) path
{
    NSString *diagnosticPath = [path stringByResolvingAlias];
    HorosRecordPluginLoad(diagnosticPath, NSLocalizedString(@"Blocked", nil), NSLocalizedString(@"Loading is disabled by protected mode or the plugin signature policy. Check protected mode and obtain a compatible plugin from its author.", nil));
    if ([DCMPix isRunOsiriXInProtectedModeActivated] == NO && [PluginManager isPluginBundleSignatureValid:path])
    {
        NSString *name = [path lastPathComponent];
        
        path = [path stringByDeletingLastPathComponent];
        
        [pluginsNames setValue: path forKey: [[name lastPathComponent] stringByDeletingPathExtension]];
        
        
        
        @try
        {
            NSString *pathResolved = [[path stringByAppendingPathComponent:name] stringByResolvingAlias];
            
            [PluginManager startProtectForCrashWithPath: pathResolved];

            NSString *archReason = [HorosArchitectureAudit pluginDiagnosisAtPath:pathResolved];
            if (archReason.length) {
                HorosRecordPluginLoad(diagnosticPath, NSLocalizedString(@"Incompatible", nil), archReason);
                NSLog(@"%@", archReason);
            }
            else
            {
            NSBundle *plugin = [NSBundle bundleWithPath: pathResolved];
            
            if( plugin == nil) {
                NSString *t2Reason = [T2FitMapCompatibility diagnosticForBundleAtPath:pathResolved loadErrorDomain:nil loadErrorCode:0];
                NSString *roiReason = [ROIEnhancementCompatibility diagnosticForBundleAtPath:pathResolved loadErrorDomain:nil loadErrorCode:0];
                NSString *specific = t2Reason.length ? t2Reason : roiReason;
                HorosRecordPluginLoad(diagnosticPath, NSLocalizedString(@"Incompatible", nil), specific.length ? specific : NSLocalizedString(@"The plugin bundle could not be opened. Reinstall a complete compatible copy from its author.", nil));
                NSLog( @"**** Bundle opening failed for plugin: %@", [path stringByAppendingPathComponent:name]);
            }
            else
            {
                NSString *principalName = [[[plugin.infoDictionary objectForKey:@"NSPrincipalClass"] copy] autorelease];
                NSError *loadError = nil;
                if (![plugin loadAndReturnError:&loadError])
                {
                    NSString *reason = [NSString stringWithFormat:NSLocalizedString(@"%@ Obtain a plugin compatible with this Mac and Horos from its author.", nil), loadError.localizedDescription ?: NSLocalizedString(@"The bundle loader refused the plugin.", nil)];
                    NSString *t2Reason = [T2FitMapCompatibility diagnosticForBundleAtPath:pathResolved loadErrorDomain:loadError.domain loadErrorCode:loadError.code];
                    NSString *roiReason = [ROIEnhancementCompatibility diagnosticForBundleAtPath:pathResolved loadErrorDomain:loadError.domain loadErrorCode:loadError.code];
                    if (t2Reason.length)
                        reason = t2Reason;
                    else if (roiReason.length)
                        reason = roiReason;
                    NSString *state = [loadError.domain isEqualToString:NSCocoaErrorDomain] && loadError.code == NSExecutableArchitectureMismatchError ? NSLocalizedString(@"Incompatible", nil) : NSLocalizedString(@"Load failed", nil);
                    HorosRecordPluginLoad(diagnosticPath, state, reason);
                    NSLog( @"Plugin load failed: %@ (%@ %ld)", reason, loadError.domain, (long)loadError.code);
                }
                else
                {
                    Class filterClass = principalName.length ? [plugin classNamed:principalName] : [plugin principalClass];
                    
                    if( filterClass)
                    {
                        
                        NSString *version = [[plugin infoDictionary] valueForKey: (NSString*) kCFBundleVersionKey];
                        
                        if( version == nil)
                        {
                            version = [[plugin infoDictionary] valueForKey: @"CFBundleShortVersionString"];
                        }
                        
                        NSLog( @"Registering: %@, vers: %@ (%@)", [name stringByDeletingPathExtension], version, path);
                        
                        if( filterClass == NSClassFromString( @"ARGS"))
                        {
                            [pluginsBundleDictionnary setObject: plugin forKey: pathResolved];
                            HorosRecordPluginLoad(diagnosticPath, NSLocalizedString(@"Loaded", nil), NSLocalizedString(@"The bundle and its principal class loaded in this session.", nil));
                            return;
                        }
                        
                        if ([[[plugin infoDictionary] objectForKey:@"pluginType"] rangeOfString:@"Pre-Process"].location != NSNotFound)
                        {
                            PluginFilter *filter = [filterClass filter];
                            [preProcessPlugins addObject: filter];
                        }
                        else if ([[plugin infoDictionary] objectForKey:@"FileFormats"])
                        {
                            NSEnumerator *enumerator = [[[plugin infoDictionary] objectForKey:@"FileFormats"] objectEnumerator];
                            NSString *fileFormat;
                            while (fileFormat = [enumerator nextObject])
                            {
                                //we will save the bundle rather than a filter.  Each file decode will require a separate decoder
                                [fileFormatPlugins setObject:plugin forKey:fileFormat];
                            }
                        }
                        else if ( [filterClass instancesRespondToSelector:@selector(filterImage:)])
                        {
                            NSArray *menuTitles = [[plugin infoDictionary] objectForKey:@"MenuTitles"];
                            PluginFilter *filter = [filterClass filter];
                            
                            if( menuTitles)
                            {
                                for( NSString *menuTitle in menuTitles)
                                {
                                    [plugins setObject:filter forKey:menuTitle];
                                    [pluginsDict setObject:plugin forKey:menuTitle];
                                }
                            }
                            
                            NSArray *toolbarNames = [[plugin infoDictionary] objectForKey:@"ToolbarNames"];
                            
                            if( toolbarNames)
                            {
                                for( NSString *toolbarName in toolbarNames)
                                {
                                    [plugins setObject:filter forKey:toolbarName];
                                    [pluginsDict setObject:plugin forKey:toolbarName];
                                }
                            }
                        }
                        
                        if ([[[plugin infoDictionary] objectForKey:@"pluginType"] rangeOfString: @"Report"].location != NSNotFound)
                        {
                            [reportPlugins setObject: plugin forKey:[[plugin infoDictionary] objectForKey:@"CFBundleExecutable"]];
                        }
                        [pluginsBundleDictionnary setObject: plugin forKey: pathResolved];
                        HorosRecordPluginLoad(diagnosticPath, NSLocalizedString(@"Loaded", nil), NSLocalizedString(@"The bundle and its principal class loaded and registration completed in this session.", nil));
                    }
                    else
                    {
                        HorosRecordPluginLoad(diagnosticPath, NSLocalizedString(@"Incompatible", nil), NSLocalizedString(@"The principal class is missing. Obtain a corrected plugin from its author.", nil));
                        NSLog( @"********* principal class not found for: %@ - %@", name, [plugin principalClass]);
                    }
                }
            }
            }
            
            
            
        }
        @catch( NSException *e)
        {
            HorosRecordPluginLoad(diagnosticPath, NSLocalizedString(@"Load failed", nil), [NSString stringWithFormat:NSLocalizedString(@"Plugin initialization failed: %@. Obtain an updated plugin from its author.", nil), e.reason ?: e.name]);
            NSLog( @"******** Plugin loading exception: %@", e);
        }
        @finally
        {
            [PluginManager endProtectForCrash];
        }
    }
}


+ (void) loadHorosPluginAtPath:(NSString*) path
{
    [self loadPluginBundle:path];
}


+ (void) loadOsiriXPluginAtPath:(NSString*) path
{
    [self loadPluginBundle:path];
}


+ (void) loadPluginAtPath: (NSString*) path
{
    NSString *name = [path lastPathComponent];
    
    
    if ([pluginsNames valueForKey: [[name lastPathComponent] stringByDeletingPathExtension]])
    {
        HorosRecordPluginLoad([path stringByResolvingAlias], NSLocalizedString(@"Blocked", nil), NSLocalizedString(@"Another plugin with this name was selected for loading. Remove the duplicate through Plugin Manager and restart Horos.", nil));
        NSLog( @"***** Multiple plugins: %@", [name lastPathComponent]);
        
        NSString *message = NSLocalizedString(@"Warning! Multiple instances of the same plugin have been found. Only one instance will be loaded. Check the Plugin Manager (Plugins menu) for multiple identical plugins.", nil);
        
        message = [message stringByAppendingFormat:@"\r\r%@", [name lastPathComponent]];
        
        NSRunAlertPanel( NSLocalizedString(@"Plugins", nil), @"%@" , nil, nil, nil, message);
        
        return;
    }
    
    
    
    if ( [[name pathExtension] isEqualToString:@"horosplugin"] )
    {
        [PluginManager loadHorosPluginAtPath:path];
    }
    else if ( [[name pathExtension] isEqualToString:@"osirixplugin"] )
    {
        [PluginManager loadOsiriXPluginAtPath:path];
    }
    else if ( [[name pathExtension] isEqualToString:@"plugin"] )
    {
        //[PluginManager loadUnknownPluginAtPath:path];
    }

    NSDictionary *outcome = HorosPluginLoadOutcome([path stringByResolvingAlias], YES);
    if ([outcome[@"loadState"] isEqualToString:NSLocalizedString(@"Loaded", nil)])
        [HorosPluginUpdateRecovery discardPreviousForDestination:path];
}


+ (void) deployHorosCloudPluginAtPath:(NSString*) path deployedPlugins:(NSMutableArray*) deployedPlugins
{
    if ([[NSFileManager defaultManager] fileExistsAtPath:path] == NO)
        [[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:nil];

    BOOL activeContainsCloud = NO;
    for (NSString *candidate in deployedPlugins)
    {
        NSString *name = [[[NSBundle bundleWithPath:candidate] infoDictionary] objectForKey:@"CFBundleName"];
        if (!name.length)
            name = [candidate lastPathComponent];
        if ([HorosPluginUpdateRecovery isCloudPluginName:name])
        {
            activeContainsCloud = YES;
            break;
        }
    }
    BOOL inactiveContainsCloud = NO;
    for (NSString *directory in [PluginManager inactiveDirectories])
    {
        for (NSString *entry in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:directory error:NULL])
        {
            if ([HorosPluginUpdateRecovery isCloudPluginName:entry])
            {
                inactiveContainsCloud = YES;
                break;
            }
        }
    }
    BOOL alreadyDeployed = [[NSUserDefaults standardUserDefaults] boolForKey:@"HOROSCLOUD_PLUGIN_DEPLOYED"];
    if (activeContainsCloud || inactiveContainsCloud)
        [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"HOROSCLOUD_PLUGIN_DEPLOYED"];
    if (![HorosPluginUpdateRecovery shouldDeployBundledCloudWithAlreadyDeployed:alreadyDeployed
                                                           activeContainsCloud:activeContainsCloud
                                                         inactiveContainsCloud:inactiveContainsCloud])
        return;

    NSString *archive = [[NSBundle mainBundle] pathForResource:@"HorosCloud.horosplugin" ofType:@"zip"];
    NSError *error = nil;
    NSString *prepared = [HorosPluginUpdateRecovery prepareBundledCloudFromArchive:archive
                                                                              into:path
                                                                   alreadyDeployed:alreadyDeployed
                                                               activeContainsCloud:activeContainsCloud
                                                             inactiveContainsCloud:inactiveContainsCloud
                                                                             error:&error];
    if (!prepared.length)
        return;

    NSString *destination = [path stringByAppendingPathComponent:@"HorosCloud.horosplugin"];
    if (HorosInstallPlugin(prepared, destination, &error))
    {
        [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"HOROSCLOUD_PLUGIN_DEPLOYED"];
        [deployedPlugins addObject:destination];
    }
    else
        NSLog(@"**** Bundled Horos Cloud could not be published: %@", error);
    [[NSFileManager defaultManager] removeItemAtPath:[prepared stringByDeletingLastPathComponent] error:NULL];
}


+ (void) discoverPlugins
{
	@try
	{
		NSString	*appSupport = @"Library/Application Support/Horos/";
        NSString	*appAppStoreSupport = @"Library/Application Support/Horos App/";
		NSString	*appPath = [[NSBundle mainBundle] builtInPlugInsPath];
        NSString	*userAppStorePath = [NSHomeDirectory() stringByAppendingPathComponent:appAppStoreSupport];
		NSString	*userPath = [NSHomeDirectory() stringByAppendingPathComponent:appSupport];
		NSString	*sysPath = [@"/" stringByAppendingPathComponent:appSupport];
		
		appSupport = [appSupport stringByAppendingPathComponent :@"Plugins/"];
		appAppStoreSupport = [appAppStoreSupport stringByAppendingPathComponent :@"Plugins/"];
		
		userPath = [NSHomeDirectory() stringByAppendingPathComponent:appSupport];
        userAppStorePath = [NSHomeDirectory() stringByAppendingPathComponent:appAppStoreSupport];
		sysPath = [@"/" stringByAppendingPathComponent:appSupport];
		
		NSArray* paths = [NSArray arrayWithObjects: [NSNull null], appPath, userPath, userAppStorePath, sysPath, nil]; // [NSNull null] is a placeholder for launch parameters load commands
		
        for( NSBundle *bundle in [pluginsBundleDictionnary allValues])
            [PluginManager unloadPluginBundle: bundle];
        
		[plugins release];
		[pluginsDict release];
		[fileFormatPlugins release];
		[preProcessPlugins release];
		[reportPlugins release];
		[fusionPlugins release];
		[fusionPluginsMenu release];
		[pluginsNames  release];
        [pluginsBundleDictionnary release];
        
        pluginsBundleDictionnary = [[NSMutableDictionary alloc] init];
		plugins = [[NSMutableDictionary alloc] init];
		pluginsDict = [[NSMutableDictionary alloc] init];
		fileFormatPlugins = [[NSMutableDictionary alloc] init];
		preProcessPlugins = [[NSMutableArray alloc] initWithCapacity:0];
		reportPlugins = [[NSMutableDictionary alloc] init];
		pluginsNames = [[NSMutableDictionary alloc] init];
		fusionPlugins = [[NSMutableArray alloc] initWithCapacity:0];
		
		fusionPluginsMenu = [[NSMenu alloc] initWithTitle:@""];
		[fusionPluginsMenu insertItemWithTitle:NSLocalizedString(@"Select a fusion plug-in", nil) action:nil keyEquivalent:@"" atIndex:0];
		
		NSLog( @"|||||||||||||||||| Plugins loading START ||||||||||||||||||");
        #ifndef OSIRIX_LIGHT
		
        NSString *pluginCrash = [PluginManager crashMarkerPath];
        if ([[NSFileManager defaultManager] fileExistsAtPath: pluginCrash] && ![[NSUserDefaults standardUserDefaults] boolForKey:@"DoNotDeleteCrashingPlugins"])
        {
            NSString *pluginCrashPath = [NSString stringWithContentsOfFile: pluginCrash encoding: NSUTF8StringEncoding error: nil];
            if ([HorosPluginUpdateRecovery shouldEnterPluginLessModeWithMarkerExists: YES])
                [DCMPix setRunOsiriXInProtectedMode: YES];
            [HorosPluginUpdateRecovery adoptLeftoverStagingInDirectory: [pluginCrashPath stringByDeletingLastPathComponent]];
            NSString *inactivePath = [HorosPluginQuarantine inactivePathForPluginAt: pluginCrashPath
                                                                            active: [PluginManager activeDirectories]
                                                                          inactive: [PluginManager inactiveDirectories]];
            BOOL canRestore = [[NSFileManager defaultManager] fileExistsAtPath: [HorosPluginUpdateRecovery previousPathForDestination: pluginCrashPath]];
            NSString *explanation = [HorosPluginUpdateRecovery explanationWithPluginNamed: [pluginCrashPath lastPathComponent]
                                                                               canRestore: canRestore
                                                                               canDisable: inactivePath != nil];
            NSString *defaultButton = canRestore ? NSLocalizedString(@"Restore Previous", nil) : (inactivePath ? NSLocalizedString(@"Disable Plugin", nil) : NSLocalizedString(@"OK", nil));
            NSString *alternateButton = canRestore ? (inactivePath ? NSLocalizedString(@"Disable Plugin", nil) : NSLocalizedString(@"Continue", nil)) : (inactivePath ? NSLocalizedString(@"Continue", nil) : nil);
            NSString *otherButton = canRestore && inactivePath ? NSLocalizedString(@"Continue", nil) : nil;
            int result = NSRunInformationalAlertPanel(NSLocalizedString(@"Horos crashed", nil), @"%@",
                                                      defaultButton, alternateButton, otherButton, explanation);
            if (canRestore && result == NSAlertDefaultReturn)
                [HorosPluginUpdateRecovery restorePreviousForDestination: pluginCrashPath];
            else if (inactivePath && ((canRestore && result == NSAlertAlternateReturn) || (!canRestore && result == NSAlertDefaultReturn)))
            {
                [PluginManager movePluginFromPath: pluginCrashPath toPath: inactivePath];
                if( [[NSFileManager defaultManager] fileExistsAtPath: inactivePath])
                    NSLog( @"Plugin disabled after a crash: %@ -> %@", pluginCrashPath, inactivePath);
                else
                    NSLog( @"**** Could not disable the plugin that was loading: %@", pluginCrashPath);
            }
            [[NSFileManager defaultManager] removeItemAtPath: pluginCrash error: nil];
        }
        
        NSMutableArray* pathsOfPluginsToLoad = [NSMutableArray array];
        NSMutableArray* dontLoadOtherWithTheseNames = [NSMutableArray array];
        
        for (id path in paths)
            @try {
                NSArray* donotloadnames = nil;
                if (![path isKindOfClass:[NSNull class]]) {
                    donotloadnames = [[NSString stringWithContentsOfFile:[path stringByAppendingPathComponent:@"DoNotLoad.txt"] usedEncoding:NULL error:NULL] componentsSeparatedByCharactersInSet:[NSCharacterSet newlineCharacterSet]];
                    if ([donotloadnames containsObject:@"*"])
                        break;
                }

                NSEnumerator* e = nil;
                if ([path isKindOfClass:[NSString class]])
                {
                    NSArray<NSString *>* pluginsInDir = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:path error:NULL];
                    e = [[pluginsInDir filteredArrayUsingPredicate:[NSPredicate predicateWithBlock:^BOOL(NSString* plugin, NSDictionary* bindings) {
                        BOOL listed = [dontLoadOtherWithTheseNames containsObject:plugin];
                        if (listed)
                            NSLog(@"Won't load %@ from %@ in favor of %@", plugin, path, [[pathsOfPluginsToLoad filteredArrayUsingPredicate:[NSPredicate predicateWithFormat:@"lastPathComponent = %@", plugin]] lastObject]);
                        return !listed;
                    }]] objectEnumerator];
                }
                else if (path == [NSNull null])
                {
                    path = @"/";
                    NSMutableArray* cl = [NSMutableArray array];
                    NSArray* args = [[NSProcessInfo processInfo] arguments];
                    for (NSInteger i = 0; i < [args count]; ++i)
                        if ([[args objectAtIndex:i] isEqualToString:@"--LoadPlugin"] && [args count] > i+1) {
                            NSString* pluginpath = [args objectAtIndex:++i];
                            [cl addObject:pluginpath];
                            [dontLoadOtherWithTheseNames addObject:pluginpath.lastPathComponent];
                        }
                    e = [cl objectEnumerator];
                }
                
                NSString* name;
                while (name = [e nextObject])
                    if ([donotloadnames containsObject:[name stringByDeletingPathExtension]] == NO)
                        [pathsOfPluginsToLoad addObject:[[path stringByAppendingPathComponent:name] stringByResolvingSymlinksAndAliases]];
            } @catch (NSException* e) {
                N2LogExceptionWithStackTrace(e);
            }
        
//        NSLog(@"paths: %@", pathsOfPluginsToLoad);

        [self deployHorosCloudPluginAtPath:userPath deployedPlugins:pathsOfPluginsToLoad];
        
        // some plugins require other plugins to be loaded before them
        for (__block NSInteger i = pathsOfPluginsToLoad.count-1; i >= 0; --i) {
            
            
            NSBundle* bundle = [NSBundle bundleWithPath:[pathsOfPluginsToLoad objectAtIndex:i]];
            NSString* name = [bundle.infoDictionary objectForKey:@"CFBundleName"];
            if (!name) name = [[[pathsOfPluginsToLoad objectAtIndex:i] lastPathComponent] stringByDeletingPathExtension];
//            
//            NSLog(@"for %@", name);
            
            // list of requirements
            for (NSString* req in [bundle.infoDictionary objectForKey:@"Requirements"]) {
                // make sure they're loaded before this plugin
                NSIndexSet* is = [pathsOfPluginsToLoad indexesOfObjectsPassingTest:^BOOL(id obj, NSUInteger idx, BOOL *stop) {
                    NSBundle* bundle = [NSBundle bundleWithPath:obj];
                    NSString* name = [bundle.infoDictionary objectForKey:@"CFBundleName"];
                    if (!name) name = [[obj lastPathComponent] stringByDeletingPathExtension];
                    return [name isEqualToString:req];
                }];
                if (!is.count)
                    NSLog(@"Warning: plugin requirement %@ not available for %@", req, name); // we actually may decide not to load this plugin, since it requires something that apparently isn't available, but hopefully it'll just raise an exception and end up not being loaded...
                [is enumerateIndexesUsingBlock:^(NSUInteger idx, BOOL *stop) {
                    if (idx > i) {
                        id o = [[[pathsOfPluginsToLoad objectAtIndex:idx] retain] autorelease];
                        [pathsOfPluginsToLoad removeObjectAtIndex:idx];
                        [pathsOfPluginsToLoad insertObject:o atIndex:i++];
                    }
                }];
            }
            
//            NSLog(@"paths: %@", pathsOfPluginsToLoad);
        }
        
        for (id path in pathsOfPluginsToLoad)
            [PluginManager loadPluginAtPath:path];
            
		#endif
		
        [T2FitMapFilter registerIn:plugins];
        [ROIEnhancementFilter registerIn:plugins];
        NSLog( @"|||||||||||||||||| Plugins loading END ||||||||||||||||||");
	}
	@catch (NSException * e)
	{
        N2LogExceptionWithStackTrace(e);
	}
}



-(void) noPlugins:(id) sender
{
	[[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:URL_HOROS_PLUGINS]];
}



#pragma mark -
#pragma mark Plugin user management

#pragma mark directories

+ (NSString*)activePluginsDirectoryPath;
{
    #ifdef MACAPPSTORE
	return @"Library/Application Support/Horos App/Plugins/";
    #else
    return @"Library/Application Support/Horos/Plugins/";
    #endif
}



+ (NSString*)inactivePluginsDirectoryPath;
{
    #ifdef MACAPPSTORE
	return @"Library/Application Support/Horos App/Plugins Disabled/";
    #else
    return @"Library/Application Support/Horos/Plugins Disabled/";
    #endif
}



+ (NSString*)userActivePluginsDirectoryPath;
{
	return [NSHomeDirectory() stringByAppendingPathComponent:[PluginManager activePluginsDirectoryPath]];
}



+ (NSString*)userInactivePluginsDirectoryPath;
{
	return [NSHomeDirectory() stringByAppendingPathComponent:[PluginManager inactivePluginsDirectoryPath]];
}



+ (NSString*)systemActivePluginsDirectoryPath;
{
	NSString *s = @"/";
	return [s stringByAppendingPathComponent:[PluginManager activePluginsDirectoryPath]];
}



+ (NSString*)systemInactivePluginsDirectoryPath;
{
	NSString *s = @"/";
	return [s stringByAppendingPathComponent:[PluginManager inactivePluginsDirectoryPath]];
}



+ (NSString*)appActivePluginsDirectoryPath;
{
	return [[NSBundle mainBundle] builtInPlugInsPath];
}



+ (NSString*)appInactivePluginsDirectoryPath;
{
	NSMutableString *appPath = [NSMutableString stringWithString:[[NSBundle mainBundle] builtInPlugInsPath]];
	[appPath appendString:@" Disabled"];
	return appPath;
}



+ (NSArray*)activeDirectories;
{
	return [NSArray arrayWithObjects:[PluginManager userActivePluginsDirectoryPath], [PluginManager systemActivePluginsDirectoryPath], [PluginManager appActivePluginsDirectoryPath], nil];
}



+ (NSArray*)inactiveDirectories;
{
	return [NSArray arrayWithObjects:[PluginManager userInactivePluginsDirectoryPath], [PluginManager systemInactivePluginsDirectoryPath], [PluginManager appInactivePluginsDirectoryPath], nil];
}

#pragma mark activation

//- (BOOL)pluginIsActiveForName:(NSString*)pluginName;
//{
//	NSMutableArray *paths = [NSMutableArray array];
//	[paths addObjectsFromArray:[self activeDirectories]];
//	
//	NSEnumerator *pathEnum = [paths objectEnumerator];
//    NSString *path;
//	while(path=[pathEnum nextObject])
//	{
//		NSEnumerator *e = [[[NSFileManager defaultManager] directoryContentsAtPath:path] objectEnumerator];
//		NSString *name;
//		while(name = [e nextObject])
//		{
//			if([[name stringByDeletingPathExtension] isEqualToString:pluginName])
//			{
//				return YES;
//			}
//		}
//	}
//	
//	return NO;
//}



+ (void)movePluginFromPath:(NSString*)sourcePath toPath:(NSString*)destinationPath;
{
	if([sourcePath isEqualToString:destinationPath]) return;
	
	if(![[NSFileManager defaultManager] fileExistsAtPath:[destinationPath stringByDeletingLastPathComponent]])
		[[NSFileManager defaultManager] createDirectoryAtPath:[destinationPath stringByDeletingLastPathComponent] withIntermediateDirectories:YES attributes:nil error:NULL];

    NSMutableArray *args = [NSMutableArray array];
	[args addObject:@"-f"];
    [args addObject:sourcePath];
    [args addObject:destinationPath];

	[[BLAuthentication sharedInstance] executeCommand:@"/bin/mv" withArgs:args];
    
    // A copy is not a successful move: it can leave a disabled plugin active.
    // The authorization helper does not reliably report the child exit status.
    if( [[NSFileManager defaultManager] fileExistsAtPath: sourcePath] ||
        [[NSFileManager defaultManager] fileExistsAtPath: destinationPath] == NO)
    {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Plugin", nil),
            NSLocalizedString(@"The plugin could not be moved. Its activation or location change was not completed. Check folder permissions and try again.", nil),
            NSLocalizedString(@"OK", nil), nil, nil);
    }
}



+ (void)activatePluginWithName:(NSString*)pluginName;
{
	NSMutableArray *activePaths = [NSMutableArray arrayWithArray:[PluginManager activeDirectories]];
	NSMutableArray *inactivePaths = [NSMutableArray arrayWithArray:[PluginManager inactiveDirectories]];
	
	NSEnumerator *activePathEnum = [activePaths objectEnumerator];
    NSString *activePath;
    NSString *inactivePath;
    
	for(inactivePath in inactivePaths)
	{
		activePath = [activePathEnum nextObject];
        NSEnumerator *e = [[[NSFileManager defaultManager] contentsOfDirectoryAtPath:inactivePath error:NULL] objectEnumerator];
		NSString *name;
		while(name = [e nextObject])
		{
			if([[name stringByDeletingPathExtension] isEqualToString:pluginName])
			{
				NSString *sourcePath = [NSString stringWithFormat:@"%@/%@", inactivePath, name];
				NSString *destinationPath = [NSString stringWithFormat:@"%@/%@", activePath, name];
				[PluginManager movePluginFromPath:sourcePath toPath:destinationPath];
			}
		}
	}
    
    if( !gPluginsAlertAlreadyDisplayed)
        NSRunInformationalAlertPanel(NSLocalizedString(@"Plugins", @""), NSLocalizedString( @"Restart Horos to apply the changes to the plugins.", @""), NSLocalizedString(@"OK", @""), nil, nil);
    gPluginsAlertAlreadyDisplayed = YES;
}



+ (void)deactivatePluginWithName:(NSString*)pluginName;
{
//    [PluginManager unloadPluginWithName: pluginName];
    
	NSMutableArray *activePaths = [NSMutableArray arrayWithArray:[PluginManager activeDirectories]];
	NSMutableArray *inactivePaths = [NSMutableArray arrayWithArray:[PluginManager inactiveDirectories]];
	
    NSString *activePath;
	NSEnumerator *inactivePathEnum = [inactivePaths objectEnumerator];
    NSString *inactivePath;
	
	for(activePath in activePaths)
	{
		inactivePath = [inactivePathEnum nextObject];
        NSEnumerator *e = [[[NSFileManager defaultManager] contentsOfDirectoryAtPath:activePath error:NULL] objectEnumerator];
		NSString *name;
		while(name = [e nextObject])
		{
			if([[name stringByDeletingPathExtension] isEqualToString:pluginName])
			{
				BOOL isDir = YES;
				if (![[NSFileManager defaultManager] fileExistsAtPath:inactivePath isDirectory:&isDir] && isDir)
					[PluginManager createDirectory:inactivePath];
				//	[[NSFileManager defaultManager] createDirectoryAtPath:inactivePath attributes:nil];
				NSString *sourcePath = [NSString stringWithFormat:@"%@/%@", activePath, name];
				NSString *destinationPath = [NSString stringWithFormat:@"%@/%@", inactivePath, name];
				[PluginManager movePluginFromPath:sourcePath toPath:destinationPath];
			}
		}
	}
    
    if( !gPluginsAlertAlreadyDisplayed)
        NSRunInformationalAlertPanel(NSLocalizedString(@"Plugins", @""), NSLocalizedString( @"Restart Horos to apply the changes to the plugins.", @""), NSLocalizedString(@"OK", @""), nil, nil);
    gPluginsAlertAlreadyDisplayed = YES;
}



+ (void)changeAvailabilityOfPluginWithName:(NSString*)pluginName to:(NSString*)availability;
{
    NSArray *availabilities = [PluginManager availabilities];
    
#ifdef MACAPPSTORE
    if([availability isEqualTo:[availabilities objectAtIndex:0]] == NO)
    {
        NSRunCriticalAlertPanel( NSLocalizedString(@"Plugin",nil),  NSLocalizedString( @"You cannot move the plugin to another location with this version of Horos.", nil), NSLocalizedString(@"OK",nil), nil, nil);
    }
#endif
    
	NSMutableArray *paths = [NSMutableArray array];
	[paths addObjectsFromArray:[PluginManager activeDirectories]];
	[paths addObjectsFromArray:[PluginManager inactiveDirectories]];

	NSEnumerator *pathEnum = [paths objectEnumerator];
    NSString *path;
	NSString *completePluginPath = nil;
	BOOL found = NO;
	
	while((path = [pathEnum nextObject]) && !found)
	{
        NSEnumerator *e = [[[NSFileManager defaultManager] contentsOfDirectoryAtPath:path error:NULL] objectEnumerator];
		NSString *name;
		while((name = [e nextObject]) && !found)
		{
			if([[name stringByDeletingPathExtension] isEqualToString:pluginName])
			{
				completePluginPath = [NSString stringWithFormat:@"%@/%@", path, name];
				found = YES;
			}
		}
	}
	
	NSString *directory = [completePluginPath stringByDeletingLastPathComponent];
	NSMutableString *newDirectory = [NSMutableString stringWithString:@""];
	
	
	if([availability isEqualTo:[availabilities objectAtIndex:0]])
	{
		[newDirectory setString:[PluginManager userActivePluginsDirectoryPath]];
	}
	else if(availabilities.count >= 1 && [availability isEqualTo:[availabilities objectAtIndex:1]])
	{
		[newDirectory setString:[PluginManager systemActivePluginsDirectoryPath]];
	}
	else if(availabilities.count >= 2 && [availability isEqualTo:[availabilities objectAtIndex:2]])
	{
		[newDirectory setString:[PluginManager appActivePluginsDirectoryPath]];
	}
	[newDirectory setString:[newDirectory stringByDeletingLastPathComponent]]; // remove /Plugins/
	[newDirectory setString:[newDirectory stringByAppendingPathComponent:[directory lastPathComponent]]]; // add /Plugins/ or /Plugins (off)/
	
	NSMutableString *newPluginPath = [NSMutableString stringWithString:@""];
	[newPluginPath setString:[newDirectory stringByAppendingPathComponent:[completePluginPath lastPathComponent]]];
	
	[PluginManager movePluginFromPath:completePluginPath toPath:newPluginPath];
}



+ (void)createDirectory:(NSString*)directoryPath;
{
	BOOL isDir = YES;
	BOOL directoryCreated = NO;
	if (![[NSFileManager defaultManager] fileExistsAtPath:directoryPath isDirectory:&isDir] && isDir)
		directoryCreated = [[NSFileManager defaultManager] createDirectoryAtPath:directoryPath withIntermediateDirectories:YES attributes:nil error:NULL];

	if(!directoryCreated)
	{
	    NSMutableArray *args = [NSMutableArray array];
		[args addObject:directoryPath];
		[[BLAuthentication sharedInstance] executeCommand:@"/bin/mkdir" withArgs:args];
	}
}




#pragma mark Instalation

+ (void) installPluginFromPath: (NSString*) path
{
    // Validate the candidate before touching an existing installation.
    NSString *archReason = [HorosArchitectureAudit pluginDiagnosisAtPath:path];
    if (archReason.length) {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Plugin", nil),
            NSLocalizedString(@"The plugin cannot be installed. The existing installation was preserved. %@", nil),
            NSLocalizedString(@"OK", nil), nil, nil,
            archReason);
        return;
    }
    NSBundle *candidate = [NSBundle bundleWithPath:path];
    NSError *candidateError = nil;
    if (!candidate || ![candidate preflightAndReturnError:&candidateError] ||
        ![PluginManager isPluginBundleSignatureValid:path])
    {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Plugin", nil),
            NSLocalizedString(@"The plugin cannot be installed. The existing installation was preserved. %@", nil),
            NSLocalizedString(@"OK", nil), nil, nil,
            candidateError.localizedDescription ?: NSLocalizedString(@"Check the plugin bundle, architecture and signature.", nil));
        return;
    }

    // move the plugin package into the plugins (active) directory
    NSString *destinationDirectory = nil;
    NSString *destinationPath = nil;
    
    NSMutableDictionary *active = [NSMutableDictionary dictionary];
	NSMutableDictionary *availabilities = [NSMutableDictionary dictionary];
	
    NSString *pluginBundleName = [[path lastPathComponent] stringByDeletingPathExtension];
    
    NSUInteger matchingInstallations = 0;
    for(NSDictionary *plug in [PluginManager pluginsList])
    {
        if([pluginBundleName isEqualToString: [plug objectForKey:@"name"]])
        {
            matchingInstallations++;
            [availabilities setObject: [plug objectForKey:@"availability"] forKey:path];
            [active setObject: [plug objectForKey:@"active"] forKey:path];
        }
    }
    
    if (matchingInstallations > 1) {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Plugin", nil),
            NSLocalizedString(@"Multiple installations of this plugin exist. Resolve the duplicates in Plugins Manager before updating. No installation was changed.", nil),
            NSLocalizedString(@"OK", nil), nil, nil);
        return;
    }

    NSString *availability = [availabilities objectForKey: path];
    BOOL isActive = [[active objectForKey:path] boolValue];
    
    if(!availability)
        isActive = YES;
    
    if([availability isEqualToString:[[PluginManager availabilities] objectAtIndex:0]])
    {
        if(isActive)
            destinationDirectory = [PluginManager userActivePluginsDirectoryPath];
        else
            destinationDirectory = [PluginManager userInactivePluginsDirectoryPath];
    }
#ifndef MACAPPSTORE
    else if([availability isEqualToString:[[PluginManager availabilities] objectAtIndex:1]])
    {
        if(isActive)
            destinationDirectory = [PluginManager systemActivePluginsDirectoryPath];
        else
            destinationDirectory = [PluginManager systemInactivePluginsDirectoryPath];
    }
    else if([availability isEqualToString:[[PluginManager availabilities] objectAtIndex:2]])
    {
        if(isActive)
            destinationDirectory = [PluginManager appActivePluginsDirectoryPath];
        else
            destinationDirectory = [PluginManager appInactivePluginsDirectoryPath];
    }
    else
#endif
    {
        if(isActive)
            destinationDirectory = [PluginManager userActivePluginsDirectoryPath];
        else
            destinationDirectory = [PluginManager userInactivePluginsDirectoryPath];
    }
    
    destinationPath = [destinationDirectory stringByAppendingPathComponent: [path lastPathComponent]];
    
    // Keep the actual installed extension when updating a legacy OsiriX bundle.
    for (NSString *extension in @[@"horosplugin", @"osirixplugin"]) {
        NSString *existingPath = [destinationDirectory stringByAppendingPathComponent:
            [pluginBundleName stringByAppendingPathExtension:extension]];
        if ([[NSFileManager defaultManager] fileExistsAtPath:existingPath]) {
            destinationPath = existingPath;
            break;
        }
    }

    NSError *installError = nil;
    if (!HorosInstallPlugin(path, destinationPath, &installError))
        NSRunCriticalAlertPanel(NSLocalizedString(@"Plugin", nil),
            NSLocalizedString(@"The plugin update could not be completed. The existing installation was preserved. Check destination permissions and available space. %@", nil),
            NSLocalizedString(@"OK", nil), nil, nil, installError.localizedDescription ?: @"");

}




#pragma mark Deletion

+ (NSString*) deletePluginWithName:(NSString*)pluginName;
{
	return [PluginManager deletePluginWithName: pluginName availability: nil isActive: YES];
}




+ (NSString*) deletePluginWithName:(NSString*)pluginName availability: (NSString*) availability isActive:(BOOL) isActive
{
    pluginName = [pluginName stringByDeletingPathExtension];
    
    // First unload the plugin, if currently running
//    [PluginManager unloadPluginWithName: pluginName];
    
	NSMutableArray *pluginsPaths = [NSMutableArray arrayWithArray:[PluginManager activeDirectories]];
	[pluginsPaths addObjectsFromArray:[PluginManager inactiveDirectories]];
	
    NSString *path, *returnPath = nil;
	NSString *trashDir = [NSHomeDirectory() stringByAppendingPathComponent:@".Trash"];
	
	NSString *directory = nil;
	NSArray *availabilities = [PluginManager availabilities];
	if( [availability isEqualToString:[availabilities objectAtIndex:0]])
	{
		if( isActive)
			directory = [PluginManager userActivePluginsDirectoryPath];
		else
			directory = [PluginManager userInactivePluginsDirectoryPath];
	}
	else if( availabilities.count >= 1 && [availability isEqualToString:[availabilities objectAtIndex:1]])
	{
		if(isActive)
			directory = [PluginManager systemActivePluginsDirectoryPath];
		else
			directory = [PluginManager systemInactivePluginsDirectoryPath];
	}
	else if( availabilities.count >= 2 && [availability isEqualToString:[availabilities objectAtIndex:2]])
	{
		if(isActive)
			directory = [PluginManager appActivePluginsDirectoryPath];
		else
			directory = [PluginManager appInactivePluginsDirectoryPath];
	}
	
	for(path in pluginsPaths)
	{
        NSEnumerator *e = [[[NSFileManager defaultManager] contentsOfDirectoryAtPath:path error:NULL] objectEnumerator];
		NSString *name;
		while(name = [e nextObject])
		{
			if([[name stringByDeletingPathExtension] isEqualToString: [pluginName stringByDeletingPathExtension]] && (directory == nil || [directory isEqualTo: path]))
			{
				NSInteger tag = 0;
				[[NSWorkspace sharedWorkspace] performFileOperation:NSWorkspaceRecycleOperation source:path destination:trashDir files:[NSArray arrayWithObject:name] tag:&tag];
				if(tag!=0)
				{
					NSLog( @"performFileOperation:NSWorkspaceRecycleOperation failed, will us mv");
					
					NSMutableArray *args = [NSMutableArray array];
					[args addObject:@"-f"];
					[args addObject:[NSString stringWithFormat:@"%@/%@", path, name]];
					[args addObject:[NSString stringWithFormat:@"%@/%@", trashDir, name]];
					[[BLAuthentication sharedInstance] executeCommand:@"/bin/mv" withArgs:args];

				}
				
				returnPath = path;
				
//				// delete
//				BOOL deleted = [[NSFileManager defaultManager] removeItemAtPath:[NSString stringWithFormat:@"%@/%@", path, name] error:NULL];
//				if(!deleted)
//				{
//					NSMutableArray *args = [NSMutableArray array];
//					[args addObject:@"-r"];
//					[args addObject:[NSString stringWithFormat:@"%@/%@", path, name]];
//					[[BLAuthentication sharedInstance] executeCommand:@"/bin/rm" withArgs:args];
//				}
			}
		}
	}
	
    if( !gPluginsAlertAlreadyDisplayed)
        NSRunInformationalAlertPanel(NSLocalizedString(@"Plugins", @""), NSLocalizedString( @"Restart Horos to apply the changes to the plugins.", @""), NSLocalizedString(@"OK", @""), nil, nil);
    gPluginsAlertAlreadyDisplayed = YES;
    
	return returnPath;
}




#pragma mark plugins

NSInteger sortPluginArray(id plugin1, id plugin2, void *context)
{
    NSString *name1 = [plugin1 objectForKey:@"name"];
    NSString *name2 = [plugin2 objectForKey:@"name"];
    
	return [name1 compare:name2 options: NSCaseInsensitiveSearch];
}



+ (NSArray*) pluginsList;
{
	NSString *userActivePath = [PluginManager userActivePluginsDirectoryPath];
	NSString *userInactivePath = [PluginManager userInactivePluginsDirectoryPath];
	NSString *sysActivePath = [PluginManager systemActivePluginsDirectoryPath];
	NSString *sysInactivePath = [PluginManager systemInactivePluginsDirectoryPath];

//	NSArray *paths = [NSArray arrayWithObjects:userActivePath, userInactivePath, sysActivePath, sysInactivePath, nil];
	
	NSMutableArray *paths = [NSMutableArray array];
	[paths addObjectsFromArray:[PluginManager activeDirectories]];
	[paths addObjectsFromArray:[PluginManager inactiveDirectories]];
    
    NSString *path;
	
    NSMutableArray *plugins = [NSMutableArray array];
	
    for (path in paths)
	{
//		BOOL active = ([path isEqualToString:userActivePath] || [path isEqualToString:sysActivePath]);
//		BOOL allUsers = ([path isEqualToString:sysActivePath] || [path isEqualToString:sysInactivePath]);
		BOOL active = [[PluginManager activeDirectories] containsObject:path];
		BOOL allUsers = ([path isEqualToString:sysActivePath] || [path isEqualToString:sysInactivePath] || [path isEqualToString:[PluginManager appActivePluginsDirectoryPath]] || [path isEqualToString:[PluginManager appInactivePluginsDirectoryPath]]);
		
		NSString *availability = nil;
		
        if([path isEqualToString:sysActivePath] || [path isEqualToString:sysInactivePath])
			availability = [[PluginManager availabilities] objectAtIndex:1];
		
        else if([path isEqualToString:[PluginManager appActivePluginsDirectoryPath]] || [path isEqualToString:[PluginManager appInactivePluginsDirectoryPath]])
			availability = [[PluginManager availabilities] objectAtIndex:2];
        
		else if([path isEqualToString:userActivePath] || [path isEqualToString:userInactivePath])
			availability = [[PluginManager availabilities] objectAtIndex:0];
		
        NSEnumerator *e = [[[NSFileManager defaultManager] contentsOfDirectoryAtPath:path error:NULL] objectEnumerator];
		
        NSString *name = nil;
		
        while(name = [e nextObject])
		{
			if(/* [[name pathExtension] isEqualToString:@"plugin"] || */ [[name pathExtension] isEqualToString:@"horosplugin"] || [[name pathExtension] isEqualToString:@"osirixplugin"])
			{
//				NSBundle *plugin = [NSBundle bundleWithPath:[PluginManager pathResolved:[path stringByAppendingPathComponent:name]]];
//				if (filterClass = [plugin principalClass])	
				{					
					NSMutableDictionary *pluginDescription = [NSMutableDictionary dictionaryWithCapacity:3];
					[pluginDescription setObject:[name stringByDeletingPathExtension] forKey:@"name"];
                    [pluginDescription addEntriesFromDictionary:HorosPluginLoadOutcome([[path stringByAppendingPathComponent:name] stringByResolvingAlias], active)];
					[pluginDescription setObject:[NSNumber numberWithBool:active] forKey:@"active"];
					[pluginDescription setObject:[NSNumber numberWithBool:allUsers] forKey:@"allUsers"];
					[pluginDescription setObject:availability forKey:@"availability"];
                    
                    if ([[name pathExtension] isEqualToString:@"osirixplugin"])
                    {
                        [pluginDescription setObject:[NSImage imageNamed:@"osirixplugin"] forKey:@"typeIcon"];
                    }
                    else
                    {
                        [pluginDescription setObject:[NSImage imageNamed:@"horosplugin"] forKey:@"typeIcon"];
                    }
					
					////////////////////////////////////
                    // plugin version and compatibility
					////////////////////////////////////
                    
					// taking the "version" through NSBundle is a BAD idea: Cocoa keeps the NSBundle in cache... thus for a same path you'll always have the same version
					NSURL *bundleURL = [NSURL fileURLWithPath:[[path stringByAppendingPathComponent:name] stringByResolvingAlias]];
					CFDictionaryRef bundleInfoDict = CFBundleCopyInfoDictionaryInDirectory((CFURLRef) bundleURL);
								
					//////////////
                    
                    CFStringRef versionString = nil;
					
                    if(bundleInfoDict != NULL)
					{
						versionString = CFDictionaryGetValue(bundleInfoDict, CFSTR("CFBundleVersion"));
					
						if(versionString == nil)
                        {
							versionString = CFDictionaryGetValue(bundleInfoDict, CFSTR("CFBundleShortVersionString"));
                        }
					}
					
                    NSString *pluginVersion = nil;
                    
					if(versionString != NULL)
						pluginVersion = (NSString*) versionString;
					else
						pluginVersion = @"";
						
					[pluginDescription setObject:pluginVersion forKey:@"version"];
					
                    
                    //////////////
                    
                    if ([[name pathExtension] isEqualToString:@"horosplugin"])
                    {
                        [pluginDescription setObject:@"YES" forKey:@"HorosCompatiblePlugin"];
                    }
                    else
                    {
                        NSNumber * horosCompatible = [NSNumber numberWithBool:NO];
                        
                        if (bundleInfoDict != NULL)
                        {
                            horosCompatible = CFDictionaryGetValue(bundleInfoDict, CFSTR("HorosCompatiblePlugin"));
                            
                            if (horosCompatible == nil)
                            {
                                horosCompatible = [NSNumber numberWithBool:NO];
                            }
                        }
                        
                        [pluginDescription setObject:[horosCompatible boolValue]?@"YES":@"NO" forKey:@"HorosCompatiblePlugin"];
                    }
                    
                    //////////////
                    
                    if(bundleInfoDict != NULL)
                    {
						CFRelease( bundleInfoDict);
                    }
					
                    ////////////////////////////////////
                    
                    
					// plugin description dictionary
					[plugins addObject:pluginDescription];
				}
			}
		}
	}
	
    NSArray *sortedPlugins = [plugins sortedArrayUsingFunction:sortPluginArray context:NULL];
    
	return sortedPlugins;
}



+ (NSArray*)availabilities;
{
	return [NSArray arrayWithObjects:NSLocalizedString(@"Current user", nil),
                                     NSLocalizedString(@"All users", nil),
                                     NSLocalizedString(@"Horos bundle", nil), nil];
}


#pragma mark -
#pragma mark auto update

- (NSArray*)checkForHorosPluginsUpdates:(id)sender
{
    NSMutableArray *pluginsToUpdate = [NSMutableArray array];
    
    
    NSArray *catalog = nil;
    NSError *catalogError = nil;
    NSArray *endpoints = [[NSOrderedSet orderedSetWithArray:@[HOROS_PLUGIN_LIST_URL, HOROS_PLUGIN_LIST_ALT_URL]] array];
    for (NSString *endpoint in endpoints) {
        catalog = HorosLoadPluginCatalog([NSURL URLWithString:endpoint], 10, &catalogError);
        if (catalog) break; // A valid empty catalog is a successful response.
    }
    if (!catalog) {
        NSLog(@"Plugin update catalog unavailable (%@ %ld): %@", catalogError.domain, (long)catalogError.code, catalogError.localizedDescription);
        return pluginsToUpdate;
    }
    NSMutableArray *onlinePlugins = [[catalog mutableCopy] autorelease];

    if ([onlinePlugins count] > 0)
    {
        NSArray *installedPlugins = [PluginManager pluginsList];
        
        for (NSDictionary *installedPlugin in installedPlugins)
        {
            NSString *pluginName = [installedPlugin valueForKey:@"name"];
            
            NSDictionary *onlinePlugin = nil;
            for (NSDictionary *plugin in onlinePlugins)
            {
                NSString *name = HorosPluginDownloadName(plugin);
                
                if([pluginName isEqualToString:name])
                {
                    onlinePlugin = plugin;
                    break;
                }
            }
            
            if( onlinePlugin)
            {
                NSString *currVersion = [installedPlugin objectForKey:@"version"];
                NSString *onlineVersion = [onlinePlugin objectForKey:@"version"];
                
                if (HorosPluginVersionIsValid(currVersion) && HorosPluginVersionIsValid(onlineVersion))
                {
                    if( [currVersion isEqualToString:onlineVersion] == NO && [PluginManager compareVersion: currVersion withVersion: onlineVersion] < 0)
                    {
                        NSLog( @"PLUGIN UPDATE NEEDED -------> current vers: %@ versus online vers: %@ - %@", currVersion, onlineVersion, pluginName);
                        NSMutableDictionary *modifiedOnlinePlugin = [NSMutableDictionary dictionaryWithDictionary:onlinePlugin];
                        [modifiedOnlinePlugin setObject:pluginName forKey:@"name"];
                        [pluginsToUpdate addObject:modifiedOnlinePlugin];
                    }
                }
                [onlinePlugins removeObject:onlinePlugin];
            }
        }
    }
    
    return pluginsToUpdate;
}


- (NSArray*) checkForOsiriXPluginsUpdates:(id)sender
{
    NSMutableArray *pluginsToUpdate = [NSMutableArray array];
    
    
    NSArray *catalog = nil;
    NSError *catalogError = nil;
    NSArray *endpoints = [[NSOrderedSet orderedSetWithArray:@[OSIRIX_PLUGIN_LIST_URL, OSIRIX_PLUGIN_LIST_ALT_URL]] array];
    for (NSString *endpoint in endpoints) {
        catalog = HorosLoadPluginCatalog([NSURL URLWithString:endpoint], 10, &catalogError);
        if (catalog) break; // A valid empty catalog is a successful response.
    }
    if (!catalog) {
        NSLog(@"Plugin update catalog unavailable (%@ %ld): %@", catalogError.domain, (long)catalogError.code, catalogError.localizedDescription);
        return pluginsToUpdate;
    }
    NSMutableArray *onlinePlugins = [[catalog mutableCopy] autorelease];

    if ([onlinePlugins count] > 0)
    {
        NSArray *installedPlugins = [PluginManager pluginsList];
        
        for (NSDictionary *installedPlugin in installedPlugins)
        {
            NSString *pluginName = [installedPlugin valueForKey:@"name"];
            
            NSDictionary *onlinePlugin = nil;
            for (NSDictionary *plugin in onlinePlugins)
            {
                NSString *name = HorosPluginDownloadName(plugin);
                
                if([pluginName isEqualToString:name])
                {
                    onlinePlugin = plugin;
                    break;
                }
            }
            
            if( onlinePlugin)
            {
                NSString *currVersion = [installedPlugin objectForKey:@"version"];
                NSString *onlineVersion = [onlinePlugin objectForKey:@"version"];
                
                if (HorosPluginVersionIsValid(currVersion) && HorosPluginVersionIsValid(onlineVersion))
                {
                    if( [currVersion isEqualToString:onlineVersion] == NO && [PluginManager compareVersion: currVersion withVersion: onlineVersion] < 0)
                    {
                        NSLog( @"PLUGIN UPDATE NEEDED -------> current vers: %@ versus online vers: %@ - %@", currVersion, onlineVersion, pluginName);
                        NSMutableDictionary *modifiedOnlinePlugin = [NSMutableDictionary dictionaryWithDictionary:onlinePlugin];
                        [modifiedOnlinePlugin setObject:pluginName forKey:@"name"];
                        [pluginsToUpdate addObject:modifiedOnlinePlugin];
                    }
                }
                [onlinePlugins removeObject:onlinePlugin];
            }
        }
    }
    
    return pluginsToUpdate;
}


- (IBAction)checkForUpdates:(id)sender
{
	NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
	
    [NSThread currentThread].name = @"Check for plugins updates";
    
	[NSThread sleepForTimeInterval: 10];
	
    NSMutableArray* pluginsToUpdate = [NSMutableArray arrayWithArray:[self checkForHorosPluginsUpdates:sender]];
    [pluginsToUpdate addObjectsFromArray:[self checkForOsiriXPluginsUpdates:sender]];
        
    //ici
    if([pluginsToUpdate count])
    {
        NSString *title;
        NSMutableString *message = [NSMutableString string];
        
        if([pluginsToUpdate count]==1)
        {
            title = NSLocalizedString(@"Plugin Update Available", @"");
            [message appendFormat:NSLocalizedString(@"A new version of the plugin \"%@\" is available.", @""), [[pluginsToUpdate objectAtIndex:0] objectForKey:@"name"]];
        }
        else
        {
            title = NSLocalizedString(@"Plugin Updates Available", @"");
            [message appendString:NSLocalizedString(@"New versions of the following plugins are available:\n", @"")];
            for (NSDictionary *plugin in pluginsToUpdate)
            {
                [message appendFormat:@"%@, ", [plugin objectForKey:@"name"]];
            }
            message = [NSMutableString stringWithString:[message substringToIndex:[message length]-2]];
        }
								
        NSDictionary *messageDictionary = [NSDictionary dictionaryWithObjects:[NSArray arrayWithObjects:title, message, pluginsToUpdate, nil] forKeys:[NSArray arrayWithObjects:@"title", @"body", @"plugins", nil]];
        
        [self performSelectorOnMainThread:@selector(displayUpdateMessage:) withObject:messageDictionary waitUntilDone: NO];
    }

	
	[pool release];
}




- (void) displayUpdateMessage:(NSDictionary*) messageDictionary;
{
	[messageDictionary retain];

	NSAutoreleasePool   *pool = [[NSAutoreleasePool alloc] init];
	
		int button = NSRunAlertPanel( [messageDictionary objectForKey:@"title"], @"%@", NSLocalizedString(@"Download", @""), NSLocalizedString( @"Cancel", @""), nil, [messageDictionary objectForKey:@"body"]);
			
		if (NSOKButton == button)
		{
			startedUpdateProcess = YES;
			PluginManagerController *pluginManagerController = [[BrowserController currentBrowser] pluginManagerController];

			if(pluginManagerController)
			{
				NSArray *pluginsToDownload = [messageDictionary objectForKey:@"plugins"];
				self.downloadQueue = [NSMutableArray arrayWithArray:pluginsToDownload];
				
				NSLog(@"Download Plugin : %@", [[pluginsToDownload objectAtIndex:0] objectForKey:@"download_url"]);
                
                NSString* pluginURL = [[pluginsToDownload objectAtIndex:0] objectForKey:@"download_url"];
                
                if ( [pluginURL containsString:@"horosplugin"] )
                {
                    [pluginManagerController setHorosPluginDownloadURL:pluginURL];
                    [pluginManagerController downloadHorosPlugin:self];
                    
                }
                else if ( [pluginURL containsString:@"osirixplugin"] )
                {
                    [pluginManagerController setOsiriXPluginDownloadURL:pluginURL];
                    [pluginManagerController downloadOsiriXPlugin:self];
                }
			}
		}
		else startedUpdateProcess = NO;
	
	[pool release];
	
	[messageDictionary release];
}



-(void) downloadNext:(NSNotification*) notification;
{
	if (!startedUpdateProcess)
        return;
	
	if([downloadQueue count]>1)
	{
		[downloadQueue removeObjectAtIndex:0];

		PluginManagerController *pluginManagerController = [[BrowserController currentBrowser] pluginManagerController];

		NSLog(@"Download Plugin : %@",[[downloadQueue objectAtIndex:0] objectForKey:@"download_url"]);
        
        NSString* pluginURL = [[downloadQueue objectAtIndex:0] objectForKey:@"download_url"];
        
        if ( [pluginURL containsString:@"horosplugin"] )
        {
            [pluginManagerController setHorosPluginDownloadURL:pluginURL];
            [pluginManagerController downloadHorosPlugin:self];

        }
        else if ( [pluginURL containsString:@"osirixplugin"] )
        {
            [pluginManagerController setOsiriXPluginDownloadURL:pluginURL];
            [pluginManagerController downloadOsiriXPlugin:self];
        }
	}
	else
	{
        if( !gPluginsAlertAlreadyDisplayed)
            NSRunInformationalAlertPanel(NSLocalizedString(@"Plugin Update Completed", @""), NSLocalizedString(@"All your plugins are now up to date. Restart Horos to use the new or updated plugins.", @""), NSLocalizedString(@"OK", @""), nil, nil);
		gPluginsAlertAlreadyDisplayed = YES;
        
        startedUpdateProcess = NO;
	}
}

#endif

@end
