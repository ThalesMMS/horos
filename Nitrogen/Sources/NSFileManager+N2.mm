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


#import "Horos-Swift.h"
#import "NSFileManager+N2.h"
#import "NSString+N2.h"
#import "NSString+SymlinksAndAliases.h"
#import <sys/stat.h>
#import <errno.h>
#import <stdlib.h>
#import <string.h>
#import <unistd.h>

@implementation NSFileManager (N2)

// Hands the item to the system Trash of its own volume (#613).
//
// This used to build ~/.Trash/<name> by hand and *delete* whatever was already
// there under that name before moving the item in - so trashing a file could
// permanently destroy an earlier, unrelated item the user had discarded. It
// also sent items on other volumes to the home Trash as a cross-volume copy.
// The system picks the destination, renames on collision, and on failure the
// item stays where it was: nothing is ever deleted as a fallback.
- (void)moveItemAtPathToTrash: (NSString*) path
{
    NSError *error = nil;
    if (![self moveItemAtPathToTrash:path resultingPath:NULL error:&error] && path.length)
        NSLog(@"Could not move %@ to the Trash; it was left where it is: %@", path, error.localizedDescription);
}

- (BOOL)moveItemAtPathToTrash:(NSString*)path resultingPath:(NSString**)resultingPath error:(NSError**)error
{
    if (resultingPath) *resultingPath = nil;
    if (path.length == 0) {
        if (error) *error = [NSError errorWithDomain:NSCocoaErrorDomain code:NSFileNoSuchFileError userInfo:@{NSLocalizedDescriptionKey: @"No item was named to move to the Trash."}];
        return NO;
    }
    NSURL *resulting = nil;
    if (![self trashItemAtURL:[NSURL fileURLWithPath:path] resultingItemURL:&resulting error:error])
        return NO;
    if (resultingPath) *resultingPath = resulting.path;
    return YES;
}

-(NSString*)findSystemFolderOfType:(int)folderType forDomain:(int)domain {
    FSRef folder;
    NSString* result = NULL;
	
    OSErr err = FSFindFolder(domain, folderType, kCreateFolder, &folder);
    if (err == noErr) {
        CFURLRef url = CFURLCreateFromFSRef(kCFAllocatorDefault, &folder);
        result = [(NSURL*)url path];
		CFRelease(url);
    } else [NSException raise:NSGenericException format:@"FSFindFolder error %d", err];
	
    return result;
}

-(NSString*)userApplicationSupportFolderForApp {
    NSURL *url = [[self URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask] firstObject];
	NSString* path = url.path;
	[self confirmDirectoryAtPath:path];
	return path;
}

-(NSString*)tmpFilePathInDir:(NSString*)dirPath {
    if (!dirPath.length)
        [NSException raise:NSInvalidArgumentException format:@"A temporary file requires a parent directory."];
    NSString *pattern = [dirPath stringByAppendingPathComponent:@"file-XXXXXX"];
    char *buffer = strdup(pattern.fileSystemRepresentation);
    if (!buffer) [NSException raise:NSMallocException format:@"Could not allocate a temporary file path."];
    int descriptor = mkstemp(buffer);
    int code = errno;
    NSString *path = nil;
    if (descriptor >= 0) {
        path = [self stringWithFileSystemRepresentation:buffer length:strlen(buffer)];
        // The API returns a reserved pathname, not an open file descriptor.
        close(descriptor);
    }
    free(buffer);
    if (!path) [NSException raise:NSGenericException format:@"Could not create a temporary file (%d).", code];
    return path;
}

-(NSString*)tmpDirPath {
    NSString* path = [NSTemporaryDirectory() stringByAppendingPathComponent:[NSString stringWithFormat:@"%@_%@", [[NSBundle mainBundle] objectForInfoDictionaryKey:(NSString*)kCFBundleNameKey], NSUserName()]];
    [self confirmDirectoryAtPath:path];
    return path;
}

// A temporary directory, made by mkdtemp, inside a directory of the caller's
// choosing. -tmpFilePathInDir: is the wrong thing to ask for when a directory is
// wanted: mkstemp creates the file and leaves it there, so
// -confirmDirectoryAtPath: on the same path then finds a file in its way and
// raises. That took down a whole medium scan when a disc carried a ZIP.
-(NSString*)tmpDirectoryPathInDir:(NSString*)dirPath {
    if (!dirPath.length)
        [NSException raise:NSInvalidArgumentException format:@"A temporary directory requires a parent directory."];
    [self confirmDirectoryAtPath:dirPath];
    NSString *pattern = [dirPath stringByAppendingPathComponent:@"directory-XXXXXX"];
    char *buffer = strdup(pattern.fileSystemRepresentation);
    if (!buffer) [NSException raise:NSMallocException format:@"Could not allocate a temporary directory path."];
    NSString *path = nil;
    if (mkdtemp(buffer)) path = [self stringWithFileSystemRepresentation:buffer length:strlen(buffer)];
    int code = errno;
    free(buffer);
    if (!path) [NSException raise:NSGenericException format:@"Could not create a temporary directory (%d).", code];
    return path;
}

-(NSString*)tmpDirectoryPathInTmp {
    return [self tmpDirectoryPathInDir:[self tmpDirPath]];
}

-(NSString*)tmpFilePathInTmp {
	return [self tmpFilePathInDir:[self tmpDirPath]];
}

-(NSString*)confirmDirectoryAtPath:(NSString*)dirPath subDirectory: (BOOL) subDirectory
{
	if( dirPath == nil) return nil;
	NSString* parentDirPath = [dirPath stringByDeletingLastPathComponent];
    
	if (![dirPath isEqualToString:parentDirPath])
		[self confirmDirectoryAtPath:parentDirPath subDirectory: YES];
    
	BOOL isDir, create = NO;
	NSError* error = NULL;
    
    //NSLog(@"==> %@",dirPath);
    
	if (![self fileExistsAtPath:dirPath isDirectory:&isDir])
		create = YES;
	else
    {
        if (!isDir)
        {
            if ([dirPath isEqualToString:@"/tmp"] == NO)
            {
                // A directory request must never destroy an existing file,
                // including a file encountered in a parent path (#705, #793, #801).
                [NSException raise:NSGenericException
                            format:@"Cannot create directory: an existing file occupies %@", dirPath];
            }
            else
            {
                NSLog(@"/tmp issue workaround");
            }
        }
    }
	
	if (create) {
		[self createDirectoryAtPath:dirPath withIntermediateDirectories:YES attributes:NULL error:&error];
		// The file system answers "you don't have permission" for an ejected
		// disk, which sends the reader to permissions they never changed. And
		// the message named no path at all, so there was nothing to act on.
		if (error) [NSException raise:NSGenericException format:@"%@", [HorosStorageFailure reasonForError: error path: dirPath]];
	}
    
    if( subDirectory == NO && [self isWritableFileAtPath: dirPath] == NO)
    {
        // Every part of the database asks for its directory, so a read-only
        // volume produced this line more than twenty times per launch and
        // buried whatever else was said. Once per place is the information.
        static NSMutableSet *reported = nil;
        static dispatch_once_t once;
        dispatch_once( &once, ^{ reported = [[NSMutableSet alloc] init]; });
        @synchronized( reported)
        {
            if( [reported containsObject: dirPath] == NO)
            {
                [reported addObject: dirPath];
                NSLog( @"-------- confirmDirectoryAtPath %@ is writable == NO", dirPath);
            }
        }
    }
    
	return dirPath;
}

-(NSString*)confirmDirectoryAtPath:(NSString*)dirPath
{
    return [self confirmDirectoryAtPath: dirPath subDirectory: NO];
}

// Resolves "X" and "X.noindex" to the directory "X.noindex", moving a legacy
// "X" directory there when nothing occupies the new name yet (#612).
//
// The two branches used to be swapped: a suffixed path looked for a legacy
// "X.noindex.noindex", and an unsuffixed one cut eight characters off its own
// name - out of range for a short path. A regular file in the way was deleted.
// Nothing is deleted now. A file at the destination is an error the caller
// sees, and when both directories exist both are kept as they are: merging or
// replacing either one is not a decision a path helper can make.
-(NSString*)confirmNoIndexDirectoryAtPath:(NSString*)path {
	// An empty request creates and renames nothing.
	if (path.length == 0)
		return nil;

	NSString* const ext = @".noindex";

	// "INCOMING.noindex/" names the same directory as "INCOMING.noindex". This
	// runs for every file the database stores, so it reads one character
	// instead of searching.
	while (path.length > 1 && [path characterAtIndex:path.length-1] == '/')
		path = [path substringToIndex:path.length-1];

	NSString* pathWithExt;
	NSString* pathWithoutExt;

	if ([path hasSuffix:ext]) {
		pathWithExt = path;
		pathWithoutExt = [path substringToIndex:path.length-ext.length];
	} else {
		pathWithoutExt = path;
		pathWithExt = [path stringByAppendingString:ext];
	}

	BOOL pathWithExtIsDir = NO, pathWithExtExists = [self fileExistsAtPath:pathWithExt isDirectory:&pathWithExtIsDir];

	if (pathWithExtExists && !pathWithExtIsDir)
		[NSException raise:NSGenericException format:@"Cannot create directory at %@: a file already exists there and is left untouched", pathWithExt];

	// A last component that is only ".noindex" has no legacy name: its
	// "unsuffixed" form is the parent folder, which must never be moved into
	// itself. Read from the last character, without allocating a component.
	if (!pathWithExtExists && pathWithoutExt.length > 0 && [pathWithoutExt characterAtIndex:pathWithoutExt.length-1] != '/') {
		BOOL pathWithoutExtIsDir = NO, pathWithoutExtExists = [self fileExistsAtPath:pathWithoutExt isDirectory:&pathWithoutExtIsDir];
		if (pathWithoutExtExists && pathWithoutExtIsDir) {
			NSError* error = nil;
			BOOL moved = [self moveItemAtPath:pathWithoutExt toPath:pathWithExt error:&error];
			pathWithExtExists = [self fileExistsAtPath:pathWithExt isDirectory:&pathWithExtIsDir];
			// Another thread may have created the destination meanwhile: then
			// both directories exist and both are kept, which is not a failure.
			if (!pathWithExtExists || !pathWithExtIsDir)
				[NSException raise:NSGenericException format:@"Could not rename directory at %@ to %@: %@", pathWithoutExt, pathWithExt, error.localizedDescription ?: @"no reason given"];
			if (!moved)
				NSLog(@"Kept both %@ and %@: the second appeared while the first was being renamed (%@)", pathWithoutExt, pathWithExt, error.localizedDescription);
		}
	}

	return [self confirmDirectoryAtPath:pathWithExt];
}

-(NSUInteger)sizeAtPath:(NSString*)path {
	FSRef fsRef;
	CFURLGetFSRef((CFURLRef)[NSURL fileURLWithPath:path], &fsRef);
	return [self sizeAtFSRef:&fsRef];
}

-(NSUInteger)sizeAtFSRef:(FSRef*)theFileRef {
	FSIterator thisDirEnum = NULL;
	NSUInteger totalSize = 0;
	
	NSMutableArray* fsRefs = [NSMutableArray arrayWithCapacity:1];
	[fsRefs addObject:[NSData dataWithBytes:theFileRef length:sizeof(FSRef)]];

	@try {
		while (fsRefs.count) {
			NSData* d = [[fsRefs objectAtIndex:0] retain];
			[fsRefs removeObjectAtIndex:0];
			FSRef currFsRef;
			[d getBytes:&currFsRef length:sizeof(FSRef)];
			[d release];
			
			FSCatalogInfo fetchedInfos;
			//HFSUniStr255 outName;
			OSErr fsErr = FSGetCatalogInfo(&currFsRef, kFSCatInfoDataSizes|kFSCatInfoRsrcSizes|kFSCatInfoNodeFlags, &fetchedInfos, NULL, NULL, NULL);
			//NSLog(@"ok for %@", [NSString stringWithCharacters:outName.unicode length:outName.length]);
			
			if (fsErr == noErr)
				if (fetchedInfos.nodeFlags&kFSNodeIsDirectoryMask) {
					if (FSOpenIterator(&currFsRef, kFSIterateFlat, &thisDirEnum) == noErr) {
						const ItemCount kMaxEntriesPerFetch = 256;
						ItemCount actualFetched;
						FSRef fetchedRefs[kMaxEntriesPerFetch];
						FSCatalogInfo fetchedInfos[kMaxEntriesPerFetch];
						
						OSErr fsErr = FSGetCatalogInfoBulk(thisDirEnum, kMaxEntriesPerFetch, &actualFetched, NULL, kFSCatInfoDataSizes|kFSCatInfoRsrcSizes|kFSCatInfoNodeFlags, fetchedInfos, fetchedRefs, NULL, NULL);
						while ((fsErr == noErr) || (fsErr == errFSNoMoreItems)) {
							for (ItemCount thisIndex = 0; thisIndex < actualFetched; ++thisIndex)
								[fsRefs addObject:[NSData dataWithBytes:&fetchedRefs[thisIndex] length:sizeof(FSRef)]];
							if (fsErr == errFSNoMoreItems)
								break;
							fsErr = FSGetCatalogInfoBulk(thisDirEnum, kMaxEntriesPerFetch, &actualFetched, NULL, kFSCatInfoDataSizes|kFSCatInfoRsrcSizes|kFSCatInfoNodeFlags, fetchedInfos, fetchedRefs, NULL, NULL);
						}
						
						FSCloseIterator(thisDirEnum);
					}
				} else {
					totalSize += fetchedInfos.dataLogicalSize;
					totalSize += fetchedInfos.rsrcLogicalSize;
				}
			else
				NSLog(@"[NSFileManager sizeAtFSRef:] error: %d", fsErr);
		}
		
	} @catch (NSException* e) {
		NSLog(@"[NSFileManager sizeAtFSRef:] error: %@", e.description);
	}

	return totalSize;
}

-(BOOL)copyItemAtPath:(NSString*)srcPath toPath:(NSString*)dstPath byReplacingExisting:(BOOL)replace error:(NSError**)err {
	BOOL success = YES;
	NSMutableArray* pairs = [NSMutableArray arrayWithObject:[NSArray arrayWithObjects: srcPath, dstPath, NULL]];
	
	while (pairs.count) {
		NSArray* pair = [pairs objectAtIndex:0];
		[pairs removeObjectAtIndex:0];
		srcPath = [pair objectAtIndex:0];
		dstPath = [pair objectAtIndex:1];
		
		NSString* srcPathRes = [srcPath stringByExpandingTildeInPath];	//[srcPath resolvedPathString];
		NSString* dstPathRes = [dstPath stringByExpandingTildeInPath];	//[dstPath resolvedPathString];
		if (!dstPathRes)
			dstPathRes = [[dstPath stringByDeletingLastPathComponent] stringByAppendingPathComponent:[dstPath lastPathComponent]];
		
		/*BOOL srcPathIsDir, srcPathExists = [self fileExistsAtPath:srcPathRes isDirectory:&srcPathIsDir]*/;
		BOOL dstPathIsDir, dstPathExists = [self fileExistsAtPath:dstPathRes isDirectory:&dstPathIsDir];
		
		if (dstPathExists && replace) {
			[self removeItemAtPath:dstPath error:NULL];
			dstPathRes = dstPath;
			dstPathExists = [self fileExistsAtPath:dstPathRes isDirectory:&dstPathIsDir];
		}
	
		if (!dstPathExists)
			success = [self copyItemAtPath:srcPathRes toPath:dstPathRes error:err] && success;
		else if (dstPathIsDir)
			for (NSString* subPath in [self contentsOfDirectoryAtPath:srcPathRes error:NULL])
				[pairs addObject:[NSArray arrayWithObjects: [srcPath stringByAppendingPathComponent:subPath], [dstPath stringByAppendingPathComponent:subPath], NULL]];
	}

	return success;
}

-(BOOL)applyFileModeOfParentToItemAtPath:(NSString*)path {
    struct stat st;
    if (stat([[path stringByDeletingLastPathComponent] fileSystemRepresentation], &st) == -1)
        return NO;
    
    if (chmod(path.fileSystemRepresentation, st.st_mode&0777) == -1)
        return NO;
        
    return YES;
}

-(NSString*)destinationOfAliasAtPath:(NSString*)inPath {
    if (inPath == nil)
        return nil;
    
	CFStringRef resolvedPath = nil;
    
	CFURLRef url = CFURLCreateWithFileSystemPath(nil /*allocator*/, (CFStringRef)inPath, kCFURLPOSIXPathStyle, NO /*isDirectory*/);
	if (url != nil) {
		FSRef fsRef;
		if (CFURLGetFSRef(url, &fsRef))
		{
			Boolean targetIsFolder, wasAliased;
			if (FSResolveAliasFile (&fsRef, true /*resolveAliasChains*/, &targetIsFolder, &wasAliased) == noErr && wasAliased)
			{
				CFURLRef resolvedurl = CFURLCreateFromFSRef(nil /*allocator*/, &fsRef);
				if (resolvedurl != nil)
				{
					resolvedPath = CFURLCopyFileSystemPath(resolvedurl, kCFURLPOSIXPathStyle);
					CFRelease(resolvedurl);
				}
			}
		}
		CFRelease(url);
	}
    
	return [(NSString*)resolvedPath autorelease];	
}

-(NSString*)destinationOfAliasOrSymlinkAtPath:(NSString*)path {
	return [self destinationOfAliasOrSymlinkAtPath:path resolved:NULL];
}

-(NSString*)destinationOfAliasOrSymlinkAtPath:(NSString*)path resolved:(BOOL*)r {
	//if (![self fileExistsAtPath:path]) {
		NSString* temp = [path stringByConditionallyResolvingAlias];
		if (temp) {
			if (r) *r = YES;
			return temp;
		}
		
	//	if (r) *r = NO;
	//	return path;
	//}
	
	NSDictionary* attrs = [self attributesOfItemAtPath:path error:NULL];
	if ([[attrs objectForKey:NSFileType] isEqualToString:NSFileTypeSymbolicLink]) {
		if (r) *r = YES;
		return [self destinationOfSymbolicLinkAtPath:path error:NULL];
	}
	
	if (r) *r = NO;
	return path;
}

-(NSDirectoryEnumerator*)enumeratorAtPath:(NSString*)path limitTo:(NSInteger)maxNumberOfFiles {
	return [[[N2DirectoryEnumerator alloc] initWithPath:path maxNumberOfFiles:maxNumberOfFiles] autorelease];
}

-(N2DirectoryEnumerator*)enumeratorAtPath:(NSString*)path filesOnly:(BOOL)filesOnly {
	return [self enumeratorAtPath:path filesOnly:filesOnly recursive:YES];
}


-(N2DirectoryEnumerator*)enumeratorAtPath:(NSString*)path filesOnly:(BOOL)filesOnly recursive:(BOOL)recursive {
	N2DirectoryEnumerator* de = [[[N2DirectoryEnumerator alloc] initWithPath:path maxNumberOfFiles:-1] autorelease];
	de.filesOnly = filesOnly;
	de.recursive = recursive;
	return de;
}


@end
