/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation, Êversion 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE. ÊSee the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos. ÊIf not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program: Ê OsiriX
 ÊCopyright (c) OsiriX Team
 ÊAll rights reserved.
 ÊDistributed under GNU - LGPL
 Ê
 ÊSee http://www.osirix-viewer.com/copyright.html for details.
 Ê Ê This software is distributed WITHOUT ANY WARRANTY; without even
 Ê Ê the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
 Ê Ê PURPOSE.
 ============================================================================*/

#import "PreviewView.h"
#import "NSFont_OpenGL.h"
#import "Horos-Swift.h"

@implementation PreviewView

@synthesize windowDelegate;

- (void) setWLWW:(float) wl :(float) ww
{
    [super setWLWW: wl : ww];
    
    // Everything that is not the policy putting a default back is a person
    // moving the window, and must survive the next scroll (#608).
    if( applyingPreviewWindow == 0)
        [windowDelegate previewView: self didRequestWindowLevel: wl width: ww];
}

- (void) applyPreviewWindow: (HorosPreviewWindow*) window
{
    if( window == nil)
        return;
    
    applyingPreviewWindow++;
    @try
    {
        [self setWLWW: window.level : window.width];
    }
    @finally
    {
        applyingPreviewWindow--;
    }
}

- (void) updatePresentationStateFromSeriesOnlyImageLevel:(BOOL) onlyImage scale:(BOOL) scale offset:(BOOL) offset
{
    // In the preview this restores the window the view already has, or the one
    // the file carries. Either way nobody moved it: recording that as a manual
    // adjustment made the first frame of every selection look like a choice
    // somebody had made, and pinned it for the rest of the series (#610).
    applyingPreviewWindow++;
    @try
    {
        [super updatePresentationStateFromSeriesOnlyImageLevel: onlyImage scale: scale offset: offset];
    }
    @finally
    {
        applyingPreviewWindow--;
    }
}


- (void) changeGLFontNotification:(NSNotification*) note
{
	if( [note object] == self)
	{
		[[self openGLContext] makeCurrentContext];
		
		CGLContextObj cgl_ctx = [[NSOpenGLContext currentContext] CGLContextObj];
        if( cgl_ctx == nil)
            return;
        
		if( fontListGL)
			glDeleteLists (fontListGL, 150);
		fontListGL = glGenLists (150);
		
		[fontGL release];
		fontGL = [[NSFont systemFontOfSize: 12] retain];
		
		[fontGL makeGLDisplayListFirst:' ' count:150 base: fontListGL :fontListGLSize :1 :self.window.backingScaleFactor];
		stringSize = [self convertSizeToBacking: [DCMView sizeOfString:@"B" forFont:fontGL]];
		
		[DCMView purgeStringTextureCache];
		[stringTextureCache release];
		stringTextureCache = nil;
		
		[self setNeedsDisplay:YES];
	}
}


- (BOOL)is2DViewer
{
	return NO;
}

-(BOOL)actionForHotKey:(NSString *)hotKey
{
	NSLog(@"preview Hot Key");
	return [super actionForHotKey:(NSString *)hotKey];
}

@end
