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

#import "StringTexture.h"
#import "N2Debug.h"
#import <math.h>

// OpenGL receives a single, explicit interleaved premultiplied RGBA8 layout.
// Focused-view captures can instead contain floating-point or 16-bit samples.
static NSBitmapImageRep *TextureUploadBitmap(NSBitmapImageRep *source)
{
    if( source == nil) return nil;
    if( source.bitsPerSample == 8 && source.bitsPerPixel == 32 &&
        source.samplesPerPixel == 4 && source.hasAlpha && !source.isPlanar &&
        source.bitmapFormat == 0 && source.bytesPerRow % 4 == 0)
        return source;

    NSBitmapImageRep *result = [[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
        pixelsWide:source.pixelsWide pixelsHigh:source.pixelsHigh bitsPerSample:8
        samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSCalibratedRGBColorSpace
        bitmapFormat:0 bytesPerRow:0 bitsPerPixel:32] autorelease];
    if( result == nil) return nil;
    memset(result.bitmapData, 0, result.bytesPerRow * result.pixelsHigh);
    NSGraphicsContext *context = [NSGraphicsContext graphicsContextWithBitmapImageRep:result];
    if( context == nil) return nil;
    [NSGraphicsContext saveGraphicsState];
    @try
    {
        [NSGraphicsContext setCurrentContext:context];
        [context setCompositingOperation:NSCompositingOperationCopy];
        if( ![source drawInRect:NSMakeRect(0, 0, source.pixelsWide, source.pixelsHigh)])
            return nil;
    }
    @finally { [NSGraphicsContext restoreGraphicsState]; }
    result.size = source.size;
    return result;
}

@implementation StringTexture

- (void) deleteTexture
{
	NSOpenGLContext *c = [NSOpenGLContext currentContext];
	
	NSUInteger index = [ctxArray indexOfObjectIdenticalTo: c];
	
	if( c && index != NSNotFound)
	{
		GLuint t = [[textArray objectAtIndex: index] intValue];
		CGLContextObj cgl_ctx = [c CGLContextObj];
		
        if( cgl_ctx)
        {
            if( t)
                (*cgl_ctx->disp.delete_textures)(cgl_ctx->rend, 1, &t);
            else
                N2LogStackTrace( @"deleteTexture");
		}
        else
            N2LogStackTrace( @"deleteTexture");
        
		[ctxArray removeObjectAtIndex: index];
		[textArray removeObjectAtIndex: index];
	}
}

- (void) deleteTexture:(NSOpenGLContext*) c
{
	NSUInteger index = [ctxArray indexOfObjectIdenticalTo: c];
	
	if( c && index != NSNotFound)
	{
		GLuint t = [[textArray objectAtIndex: index] intValue];
		CGLContextObj cgl_ctx = [c CGLContextObj];
		
        if( cgl_ctx)
        {
            if( t)
                (*cgl_ctx->disp.delete_textures)(cgl_ctx->rend, 1, &t);
            else
                N2LogStackTrace( @"deleteTexture");
		}
        else
            N2LogStackTrace( @"deleteTexture");
        
		[ctxArray removeObjectAtIndex: index];
		[textArray removeObjectAtIndex: index];
	}
}

// designated initializer
- (id) initWithAttributedString:(NSAttributedString *)attributedString withTextColor:(NSColor *)text withBoxColor:(NSColor *)box withBorderColor:(NSColor *)border
{
	self = [super init];
	antialiasing = NO;
	texSize.width = 0.0f;
	texSize.height = 0.0f;
	string = [attributedString copy];
	textColor = [text retain];
	boxColor = [box retain];
	borderColor = [border retain];
	staticFrame = NO;
	marginSize.width = 4.0f;
	marginSize.height = 2.0f;
	ctxArray = [[NSMutableArray arrayWithCapacity: 10] retain];
	textArray = [[NSMutableArray arrayWithCapacity: 10] retain];
	// all other variables 0 or NULL
	return self;
}

- (id) initWithString:(NSString *)aString withAttributes:(NSDictionary *)attribs withTextColor:(NSColor *)text withBoxColor:(NSColor *)box withBorderColor:(NSColor *)border
{
	if( aString == nil) aString = @"";
	return [self initWithAttributedString:[[[NSAttributedString alloc] initWithString:aString attributes:attribs] autorelease] withTextColor:text withBoxColor:box withBorderColor:border];
}

// basic methods that pick up defaults
- (id) initWithAttributedString:(NSAttributedString *)attributedString;
{
	if( attributedString == nil) attributedString = [[[NSAttributedString alloc] initWithString: @""] autorelease];
	return [self initWithAttributedString:attributedString withTextColor:[NSColor colorWithDeviceRed:1.0f green:1.0f blue:1.0f alpha:1.0f] withBoxColor:[NSColor colorWithDeviceRed:1.0f green:1.0f blue:1.0f alpha:0.0f] withBorderColor:[NSColor colorWithDeviceRed:1.0f green:1.0f blue:1.0f alpha:0.0f]];
}

- (id) initWithString:(NSString *)aString withAttributes:(NSDictionary *)attribs
{
	if( aString == nil) aString = @"";
	return [self initWithAttributedString:[[[NSAttributedString alloc] initWithString:aString attributes:attribs] autorelease] withTextColor:[NSColor colorWithDeviceRed:1.0f green:1.0f blue:1.0f alpha:1.0f] withBoxColor:[NSColor colorWithDeviceRed:0.0f green:0.0f blue:0.0f alpha:0.0f] withBorderColor:[NSColor colorWithDeviceRed:0.0f green:0.0f blue:0.0f alpha:0.0f]];
}

- (oneway void)release
{
    if (![NSThread isMainThread])
        [self performSelectorOnMainThread:@selector(release) withObject:nil waitUntilDone:NO];
    else
        [super release];
}

- (void) mainThreadAutorelease
{
    [self retain];
    [self autorelease];
}

- (id) autorelease
{
    if (![NSThread isMainThread])
        [self performSelectorOnMainThread:@selector(mainThreadAutorelease) withObject:nil waitUntilDone:NO];

    return [super autorelease];
}

- (void) dealloc
{
    if( [NSThread isMainThread] == NO)
        N2LogStackTrace( @"StringTexture dealloc NOT on main thread !");
    
	while( [ctxArray count]) [self deleteTexture: [ctxArray lastObject]];
	[ctxArray release]; ctxArray = nil;
	if( [textArray count]) NSLog( @"** not all texture were deleted...");
	[textArray release]; textArray = nil;
	
	[textColor release]; textColor = nil;
	[boxColor release]; boxColor = nil;
	[borderColor release]; borderColor = nil;
	[string release]; string = nil;
	[bitmap release]; bitmap = nil;
	
	[super dealloc];
}


- (NSSize) texSize
{
	return texSize;
}

- (NSColor *) textColor
{
	return textColor;
}

- (NSColor *) boxColor
{
	return boxColor;
}

- (NSColor *) borderColor
{
	return borderColor;
}

- (NSSize) frameSize
{
	if ((NO == staticFrame) && (0.0f == frameSize.width) && (0.0f == frameSize.height)) { // find frame size if we have not already found it
		frameSize = [string size]; // current string size
		frameSize.width += marginSize.width * 2.0f; // add padding
		frameSize.height += marginSize.height * 2.0f;
        frameSize.width = ceil(frameSize.width);
        frameSize.height = ceil(frameSize.height);
	}
	return frameSize;
}

- (NSSize) marginSize
{
	return marginSize;
}

- (BOOL) staticFrame
{
	return staticFrame;
}

- (void) setAntiAliasing:(BOOL) a
{
	antialiasing = a;
}

- (GLuint) genTexture;
{
    NSLog( @"******** WE SHOULD NOT BE HERE, use genTextureWithBackingScaleFactor instead");
    
    return [self genTextureWithBackingScaleFactor: [[NSScreen mainScreen] backingScaleFactor]];
}

- (GLuint) genTextureWithBackingScaleFactor: (float) backingScaleFactor; // generates the texture without drawing texture to current context
{
    if( backingScaleFactor != 1.0 && backingScaleFactor != 2.0)
    {
//        NSLog( @"******** genTextureWithBackingScaleFactor backingScaleFactor == %f", backingScaleFactor);
        backingScaleFactor = [[NSScreen mainScreen] backingScaleFactor];
    }
    
    sf = backingScaleFactor;
    
	NSOpenGLContext *currentContext = [NSOpenGLContext currentContext];
	CGLContextObj cgl_ctx = [currentContext CGLContextObj];
	
	if( currentContext == nil)
	{
		NSLog( @"********* NO CURRENT CONTEXT for genTexture");
		return 0;
	}
	
	[self deleteTexture: currentContext];
	if( staticFrame == NO && frameSize.width == 0 && frameSize.height == 0) // find frame size if we have not already found it
    {
		frameSize = [string size]; // current string size
		frameSize.width += marginSize.width * 2.0f; // add padding
		frameSize.height += marginSize.height * 2.0f;
        frameSize.width = ceil(frameSize.width);
        frameSize.height = ceil(frameSize.height);
	}
	
	GLuint texName = 0;
	
	[bitmap release];
	bitmap = nil;
    int pixelWidth = (int)ceil(frameSize.width * backingScaleFactor);
    int pixelHeight = (int)ceil(frameSize.height * backingScaleFactor);
	if( pixelWidth > 0 && pixelHeight > 0)
	{
        bitmap = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
            pixelsWide:pixelWidth pixelsHigh:pixelHeight bitsPerSample:8
            samplesPerPixel:4 hasAlpha:YES isPlanar:NO
            colorSpaceName:NSCalibratedRGBColorSpace bitmapFormat:0
            bytesPerRow:0 bitsPerPixel:32];
        if( bitmap == nil)
            return 0;
        memset(bitmap.bitmapData, 0, bitmap.bytesPerRow * bitmap.pixelsHigh);
        bitmap.size = frameSize;
        NSGraphicsContext *drawContext = [NSGraphicsContext graphicsContextWithBitmapImageRep:bitmap];
        if( drawContext == nil)
        {
            [bitmap release];
            bitmap = nil;
            return 0;
        }
        [NSGraphicsContext saveGraphicsState];
        @try
        {
            [NSGraphicsContext setCurrentContext:drawContext];
            [[NSGraphicsContext currentContext] setShouldAntialias: antialiasing];
            if ([boxColor alphaComponent])
            {
                [boxColor set];
                NSRectFill (NSMakeRect (0.0f, 0.0f, frameSize.width, frameSize.height));
            }
            if ([borderColor alphaComponent])
            {
                [borderColor set];
                NSFrameRect (NSMakeRect (0.0f, 0.0f, frameSize.width, frameSize.height));
            }
            [textColor set];
            [string drawAtPoint:NSMakePoint (marginSize.width, marginSize.height)];
        }
        @finally { [NSGraphicsContext restoreGraphicsState]; }

        NSBitmapImageRep *uploadBitmap = [TextureUploadBitmap(bitmap) retain];
        [bitmap release];
        bitmap = uploadBitmap;
        if( bitmap)
        {
            GLenum format = ([bitmap samplesPerPixel] == 4) ? GL_RGBA : GL_RGB;
            // Texture coordinates are in texels. Using logical size * scale
            // diverged from pixelsWide when NSImage did not honour the requested factor.
            texSize.width = [bitmap pixelsWide];
            texSize.height = [bitmap pixelsHigh];
            
            // Pixel-store state is shared with image, lens and plugin uploads.
            // A bound unpack buffer would interpret bitmapData as a buffer offset.
            const GLenum unpackNames[] = {GL_UNPACK_ALIGNMENT, GL_UNPACK_ROW_LENGTH,
                GL_UNPACK_SKIP_ROWS, GL_UNPACK_SKIP_PIXELS, GL_UNPACK_SWAP_BYTES,
                GL_UNPACK_LSB_FIRST, GL_UNPACK_CLIENT_STORAGE_APPLE};
            GLint unpackValues[7], unpackBuffer = 0;
            for( int i = 0; i < 7; i++) glGetIntegerv(unpackNames[i], &unpackValues[i]);
            glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING, &unpackBuffer);
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
            glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
            glPixelStorei(GL_UNPACK_SKIP_ROWS, 0);
            glPixelStorei(GL_UNPACK_SKIP_PIXELS, 0);
            glPixelStorei(GL_UNPACK_SWAP_BYTES, GL_FALSE);
            glPixelStorei(GL_UNPACK_LSB_FIRST, GL_FALSE);
            glGenTextures (1, &texName);
            glBindTexture (GL_TEXTURE_RECTANGLE_EXT, texName);
            glPixelStorei(GL_UNPACK_ROW_LENGTH, bitmap.bytesPerRow / (bitmap.bitsPerPixel >> 3));
            
            // This object replaces its single bitmap when another context uploads.
            // Existing textures must own their pixels beyond that replacement.
            glPixelStorei (GL_UNPACK_CLIENT_STORAGE_APPLE, GL_FALSE);
            glTexParameteri (GL_TEXTURE_RECTANGLE_EXT, GL_TEXTURE_STORAGE_HINT_APPLE, GL_STORAGE_CACHED_APPLE);
            
            glTexImage2D (GL_TEXTURE_RECTANGLE_EXT, 0, format, bitmap.pixelsWide, bitmap.pixelsHigh, 0, format, GL_UNSIGNED_BYTE, [bitmap bitmapData]);

            for( int i = 0; i < 7; i++) glPixelStorei(unpackNames[i], unpackValues[i]);
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, unpackBuffer);

            [ctxArray addObject: currentContext];
            [textArray addObject: [NSNumber numberWithInt: texName]];
        }
	}
	
	return texName;
}

- (void) setFlippedX: (BOOL) x Y:(BOOL) y
{
	xFlipped = x;
	yFlipped = y;
}

- (void) drawWithBounds:(NSRect)bounds
{
	NSOpenGLContext *currentContext = [NSOpenGLContext currentContext];
	GLuint texName = 0;
    
    if( sf != currentContext.view.window.backingScaleFactor)
    {
        while( [ctxArray count]) [self deleteTexture: [ctxArray lastObject]];
    }
    
	NSUInteger index = [ctxArray indexOfObjectIdenticalTo: currentContext];
    
	if( index != NSNotFound)
		texName = [[textArray objectAtIndex: index] intValue];
	
	if (!texName)
		texName = [self genTextureWithBackingScaleFactor: currentContext.view.window.backingScaleFactor];
	
	if (texName)
	{
		CGLContextObj cgl_ctx = [currentContext CGLContextObj];
		if( cgl_ctx == nil)
            return;
        
		glBindTexture (GL_TEXTURE_RECTANGLE_EXT, texName);
		
		glBegin (GL_QUADS);
		
		if( yFlipped == NO && xFlipped == NO)
		{
			glTexCoord2f (0.0f, 0.0f); // draw upper left in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y);
	
			glTexCoord2f (0.0f, texSize.height); // draw lower left in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y + bounds.size.height);

			glTexCoord2f (texSize.width, texSize.height); // draw upper right in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y + bounds.size.height);
	
			glTexCoord2f (texSize.width, 0.0f); // draw lower right in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y);

		}
		else if( yFlipped == YES && xFlipped == YES)
		{
			glTexCoord2f (0.0f, 0.0f); // draw upper left in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y + bounds.size.height);
	
			glTexCoord2f (0.0f, texSize.height); // draw lower left in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y);

			glTexCoord2f (texSize.width, texSize.height); // draw upper right in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y);
	
			glTexCoord2f (texSize.width, 0.0f); // draw lower right in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y + bounds.size.height);
		}
		else if( yFlipped == YES && xFlipped == NO)
		{
			glTexCoord2f (0.0f, 0.0f); // draw upper left in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y + bounds.size.height);
	
			glTexCoord2f (0.0f, texSize.height); // draw lower left in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y);

			glTexCoord2f (texSize.width, texSize.height); // draw upper right in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y);
	
			glTexCoord2f (texSize.width, 0.0f); // draw lower right in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y + bounds.size.height);
		}
		else if( yFlipped == NO && xFlipped == YES)
		{
			glTexCoord2f (0.0f, 0.0f); // draw upper left in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y);
            
			glTexCoord2f (0.0f, texSize.height); // draw lower left in world coordinates
			glVertex2f (bounds.origin.x + bounds.size.width, bounds.origin.y + bounds.size.height);
            
			glTexCoord2f (texSize.width, texSize.height); // draw upper right in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y + bounds.size.height);
            
			glTexCoord2f (texSize.width, 0.0f); // draw lower right in world coordinates
			glVertex2f (bounds.origin.x, bounds.origin.y);
		}
		
		glEnd ();
	}
}

- (void) drawAtPoint:(NSPoint)point ratio:(float) ratio
{
	NSOpenGLContext *currentContext = [NSOpenGLContext currentContext];
	GLuint texName = 0;
    // Refresh before deriving bounds from texSize on the first frame after a
    // display-scale change. drawWithBounds: also accepts caller-sized bounds.
    if( sf != currentContext.view.window.backingScaleFactor)
    {
        while( [ctxArray count]) [self deleteTexture: [ctxArray lastObject]];
    }

	NSUInteger index = [ctxArray indexOfObjectIdenticalTo: currentContext];
	if( index != NSNotFound)
		texName = [[textArray objectAtIndex: index] intValue];
	
	if (!texName)
		texName = [self genTextureWithBackingScaleFactor: currentContext.view.window.backingScaleFactor];
	
	if (texName) // if successful
		[self drawWithBounds:NSMakeRect (point.x, point.y, texSize.width, texSize.height*ratio)];

}

- (void) drawAtPoint:(NSPoint)point
{
	[self drawAtPoint: point ratio: 1.0];
}

- (void) setString:(NSAttributedString *)attributedString // set string after initial creation
{
	while( [ctxArray count]) [self deleteTexture: [ctxArray lastObject]];
	if( [textArray count]) NSLog( @"** not all texture were deleted...");
	
	[string release];
	string = [attributedString copy];
	if (NO == staticFrame) { // ensure dynamic frame sizes will be recalculated
		frameSize.width = 0.0f;
		frameSize.height = 0.0f;
	}
}

- (void) setString:(NSString *)aString withAttributes:(NSDictionary *)attribs; // set string after initial creation
{
	if( aString == nil) aString = @"";
	[self setString:[[[NSAttributedString alloc] initWithString:aString attributes:attribs] autorelease]];
}

- (void) setTextColor:(NSColor *)color // set default text color
{
	while( [ctxArray count]) [self deleteTexture: [ctxArray lastObject]];
	if( [textArray count]) NSLog( @"** not all texture were deleted...");
	
	[color retain];
	[textColor release];
	textColor = color;
}

- (void) setBoxColor:(NSColor *)color // set default text color
{
	while( [ctxArray count]) [self deleteTexture: [ctxArray lastObject]];
	if( [textArray count]) NSLog( @"** not all texture were deleted...");
	
	[color retain];
	[boxColor release];
	boxColor = color;
}

- (void) setBorderColor:(NSColor *)color // set default text color
{
	while( [ctxArray count]) [self deleteTexture: [ctxArray lastObject]];
	if( [textArray count]) NSLog( @"** not all texture were deleted...");
	
	[color retain];
	[borderColor release];
	borderColor = color;
}

@end
