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




#import "ROIWindow.h"
#import "HorosCalibration.h"
#import "HistogramWindow.h"
#import "PlotWindow.h"
#import "DCMView.h"
#import "DCMPix.h"
#import "Notifications.h"

@implementation ROIWindow

- (void)comboBoxWillPopUp:(NSNotification *)notification
{
	NSLog(@"will display...");
	NSArray *updatedNames = [[curController generateROINamesArray] copy];
	[roiNames release];
	roiNames = updatedNames;
	[[notification object] setDataSource: self];
	
	[[notification object] noteNumberOfItemsChanged];
	[[notification object] reloadData];
}

- (NSUInteger)comboBox:(NSComboBox *)aComboBox indexOfItemWithStringValue:(NSString *)aString
{
	if( roiNames == nil) roiNames = [[curController generateROINamesArray] copy];
	
	long i;
	
	for(i = 0; i < [roiNames count]; i++)
	{
		if( [[roiNames objectAtIndex: i] isEqualToString: aString]) return i;
	}
	
	return NSNotFound;
}

- (NSInteger)numberOfItemsInComboBox:(NSComboBox *)aComboBox
{
	if( roiNames == nil) roiNames = [[curController generateROINamesArray] copy];
	return [roiNames count];
}

- (id)comboBox:(NSComboBox *)aComboBox objectValueForItemAtIndex:(NSInteger)index
{
    if ( index >= 0 )
    {
		if( roiNames == nil) roiNames = [[curController generateROINamesArray] copy];
		if ((NSUInteger)index < [roiNames count]) return [roiNames objectAtIndex:index];
    }
    
    return nil;
}


- (IBAction) roiSaveCurrent: (id) sender
{
	NSSavePanel     *panel = [NSSavePanel savePanel];
	
	NSMutableArray  *selectedROIs = [NSMutableArray  arrayWithObject:curROI];
	
	[panel setCanSelectHiddenExtension:NO];
	[panel setAllowedFileTypes:@[@"roi"]];
	
    panel.nameFieldStringValue = [[selectedROIs objectAtIndex:0] name];
    
    [panel beginWithCompletionHandler:^(NSInteger result) {
        if (result != NSFileHandlingPanelOKButton)
            return;
        
        [NSArchiver archiveRootObject: selectedROIs toFile:panel.URL.path];
    }];
}

- (void) dealloc
{
    [[NSNotificationCenter defaultCenter] removeObserver: self];
	[previousName release];
	previousName = nil;
    [roiNames release];
    roiNames = nil;
	
	[super dealloc];
}

- (void) CloseViewerNotification :(NSNotification*) note
{
	if( [note object] == curController)
	{
		[self close];
	}
}

- (void) removeROI :(NSNotification*) note
{
	if( [note object] == curROI)
	{
        // The removal notification can be sent from ROI dealloc. Do not write back to it.
        curROI = nil;
		[self close];
	}
}

- (IBAction) recalibrate:(id) sender
{
    float pixels = 0;
    float length = curROI.points.count >= 2 ? [curROI MesureLength:&pixels] : 0;
    if (!isfinite(pixels) || pixels <= 0 || !isfinite(length))
    {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Error", nil),
            NSLocalizedString(@"Use a measurement line with a finite, nonzero length to calibrate the image.", nil),
            NSLocalizedString(@"OK", nil), nil, nil);
        return;
    }
    [recalibrateValue setStringValue:[NSString stringWithFormat:@"%0.3f", length]];
    [NSApp beginSheet:recalibrateWindow modalForWindow:[self window]
        modalDelegate:self didEndSelector:NULL contextInfo:NULL];
    NSInteger result = [NSApp runModalForWindow:recalibrateWindow];
    [NSApp endSheet:recalibrateWindow];
    [recalibrateWindow orderOut:NULL];
    if (!result) return;

    float requestedLength = 0;
    BOOL valid = HorosCalibrationFloat([recalibrateValue stringValue], [NSLocale currentLocale], &requestedLength) && requestedLength > 0;
    double resolution = (double)requestedLength * 10.0 / pixels; // Entered length is in cm; spacing is in mm.
    valid = valid && isfinite(resolution) && resolution > 0 && resolution <= FLT_MAX && (float)resolution > 0;
    NSArray *images = [curController pixList];
    NSMutableArray *verticalSpacings = [NSMutableArray arrayWithCapacity:images.count];
    // Validate the entire series before changing any image, including aspect-ratio overflow.
    for (DCMPix *pix in images)
    {
        double previousX = pix.pixelSpacingX;
        double previousY = pix.pixelSpacingY;
        double vertical = previousX == 0 ? resolution : previousY * resolution / previousX;
        valid = valid && isfinite(previousX) && previousX >= 0 &&
            isfinite(vertical) && vertical > 0 && vertical <= FLT_MAX && (float)vertical > 0;
        [verticalSpacings addObject:@(vertical)];
    }
    if (!valid)
    {
        NSRunCriticalAlertPanel(NSLocalizedString(@"Error", nil),
            NSLocalizedString(@"Enter a positive, finite length that produces valid pixel spacing for every image.", nil),
            NSLocalizedString(@"OK", nil), nil, nil);
        return;
    }
    for (NSUInteger i = 0; i < images.count; i++)
    {
        DCMPix *pix = [images objectAtIndex:i];
        [pix setPixelSpacingX:(float)resolution];
        [pix setPixelSpacingY:[[verticalSpacings objectAtIndex:i] floatValue]];
    }
    // Calibration changes physical units, not the ROI's image coordinates.
    // Update every ROI now; waiting for a draw leaves off-screen measurements stale.
    NSArray *seriesROIs = [curController roiList];
    for (NSUInteger i = 0; i < MIN(images.count, seriesROIs.count); i++)
    {
        DCMPix *pix = [images objectAtIndex:i];
        for (ROI *roi in [seriesROIs objectAtIndex:i])
        {
            roi.pixelSpacingX = pix.pixelSpacingX;
            roi.pixelSpacingY = pix.pixelSpacingY;
        }
    }
    [[NSNotificationCenter defaultCenter] postNotificationName:OsirixRecomputeROINotification object:curController userInfo:nil];
    [[NSNotificationCenter defaultCenter] postNotificationName:OsirixUpdateViewNotification object:curController userInfo:nil];
}

- (IBAction)acceptSheet:(id)sender
{
    [NSApp stopModalWithCode: [sender tag]];
}

- (BOOL) allWithSameName
{
	return [allWithSameName state]==NSOnState;
}

- (void) setROI: (ROI*) iroi :(ViewerController*) c
{
	if( curROI == iroi) return;
	
	@try
	{
		[curROI setComments: [NSString stringWithString: [comments string]]];	// stringWithString is very important - see NSText string !
		[curROI setName: [name stringValue]];
	}
	@catch (NSException *e)
	{
		NSLog( @"ROIWindow setROI: keeping previous name/comments after exception: %@ %@", e.name, e.reason);
	}
	
	[[NSNotificationCenter defaultCenter] postNotificationName: OsirixROIChangeNotification object:curROI userInfo: nil];

	curController = c;
	curROI = iroi;
	
	RGBColor	rgb = [curROI rgbcolor];
	// Match setColor: so applying the displayed color does not convert device RGB again.
	NSColor		*color = [NSColor colorWithCalibratedRed:rgb.red/65535. green: rgb.green/65535. blue:rgb.blue/65535. alpha:1.0];
	
	[colorButton setColor: color];
	
	[thicknessSlider setFloatValue: [curROI thickness]];
	[opacitySlider setFloatValue: [curROI opacity]];
	
	[name setStringValue:[curROI name]];
	[name selectText: self];
	[comments setString:[curROI comments]];
		
	if( [curROI type] == tMesure) [recalibrate setEnabled: YES];
	else [recalibrate setEnabled: NO];
	
	if( [curROI type] == tMesure) [xyPlot setEnabled: YES];
	else [xyPlot setEnabled: NO];

	if( [curROI type] == tLayerROI) [exportToXMLButton setEnabled:NO];
	else [exportToXMLButton setEnabled:YES];
}

- (void)roiChange:(NSNotification*)notification;
{
//	ROI* roi = [notification object];
//	[comments setString:[roi comments]];
//	[name setStringValue:[roi name]];
}

- (void) getName:(NSTimer*)theTimer
{
	if( [[name stringValue] isEqualToString: previousName] == NO)
	{
		[self setTextData: name];
		[previousName release];
		previousName = [[name stringValue] retain];
	}
}

- (id) initWithROI: (ROI*) iroi :(ViewerController*) c
{
	self = [super initWithWindowNibName:@"ROI"];
	
	[[self window] setFrameAutosaveName:@"ROIInfoWindow"];
	[[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(roiChange:) name:OsirixROIChangeNotification object:nil];
	[[NSNotificationCenter defaultCenter] addObserver:self selector: @selector(removeROI:) name: OsirixRemoveROINotification object: nil];
	[[NSNotificationCenter defaultCenter] addObserver:self selector: @selector(CloseViewerNotification:) name: OsirixCloseViewerNotification object: nil];
	
	getName = [[NSTimer scheduledTimerWithTimeInterval: 0.1 target:self selector:@selector(getName:) userInfo:0 repeats: YES] retain];
	
	[self setROI: iroi :c];
		
	return self;
}

- (void) windowWillClose:(NSNotification *)notification
{
    // Removal and viewer-close notifications can precede the window delegate callback.
    if (closing) return;
    closing = YES;
    [[NSNotificationCenter defaultCenter] removeObserver:self];
	[[self window] setAcceptsMouseMovedEvents: NO];
	
	[getName invalidate];
	[getName release];
	getName = nil;
	
	[ROI saveDefaultSettings];
	
	@try
	{
		[curROI setComments: [NSString stringWithString: [comments string]]]; 	// stringWithString is very important - see NSText string !
		[curROI setName: [name stringValue]];
	}
	@catch (NSException *e)
	{
		NSLog( @"ROIWindow windowWillClose: keeping previous name/comments after exception: %@ %@", e.name, e.reason);
	}
	curROI = nil;
    curController = nil;
	
	[[NSNotificationCenter defaultCenter] postNotificationName: OsirixROIChangeNotification object:curROI userInfo: nil];
	
	[self autorelease];
}

- (void) setAllMatchingROIsToSameParamsAs: (ROI*) iROI withNewName: (NSString*) newName
{
	[self setAllMatchingROIsToSameParamsAs: iROI matchingName: [iROI name] withNewName: newName];
}

- (void) setAllMatchingROIsToSameParamsAs: (ROI*) iROI matchingName: (NSString*) matchingName withNewName: (NSString*) newName
{	
	NSArray *roiSeriesList = [curController roiList];	
	NSString *oldName = [[matchingName copy] autorelease];
	NSMutableArray *renamed = [NSMutableArray array];
	
	@try
	{
		for ( NSArray *roiImageList in roiSeriesList )
		{
			for ( ROI *roi in roiImageList )
			{
				if ( roi == curROI ) continue;
				
				if ( [[roi name] isEqualToString: oldName] )
				{
					[roi setColor: [iROI rgbcolor]];
					[roi setThickness: [iROI thickness]];
					[roi setOpacity: [iROI opacity]];
					if ( newName )
					{
						[roi setName: newName];
						[renamed addObject: roi];
					}
					[[NSNotificationCenter defaultCenter] postNotificationName: OsirixROIChangeNotification object:roi userInfo: nil];
				}
			}
		}
	}
	@catch (NSException *e)
	{
		// A failure (typically NSMallocException under memory pressure) must not leave the series with
		// two names for the same structure: undo the renames already applied, then let the caller report.
		for ( ROI *roi in renamed )
		{
			@try { [roi setName: oldName]; }
			@catch (NSException *inner) { NSLog( @"ROIWindow: unable to restore name of %@: %@", roi, inner.reason); }
		}
		@throw;
	}
}

- (void) presentRenameFailure:(NSException*) exception previousName:(NSString*) previousName
{
	NSLog( @"ROIWindow: renaming failed (%@: %@); name kept as %@", exception.name, exception.reason, previousName);
	
	if ( previousName )
		[name setStringValue: previousName];
	
	NSAlert *alert = [[[NSAlert alloc] init] autorelease];
	alert.alertStyle = NSAlertStyleCritical;
	alert.messageText = NSLocalizedString( @"ROI Rename Error", nil);
	alert.informativeText = [exception.name isEqualToString: NSMallocException]
		? NSLocalizedString( @"There is not enough memory to rename the ROI. The previous name was kept.", nil)
		: [NSString stringWithFormat: NSLocalizedString( @"The ROI could not be renamed. The previous name was kept.\n\n%@", nil), exception.reason ?: @""];
	[alert runModal];
}

- (void) removeAllROIsWithName: (NSString*) roiName
{		
	NSArray *roiSeriesList = [curController roiList];	
	
	for ( NSMutableArray *roiImageList in roiSeriesList )
	{
		int j;
		
		for ( j = 0; j < [roiImageList count]; j++ )
		{
			ROI *roi = [roiImageList objectAtIndex: j ];
			
			if ( [[roi name] isEqualToString: roiName] )
			{
				[roiImageList removeObjectAtIndex: j];
				j--;
			}
		}
	}
	[[curController imageView] setNeedsDisplay: YES];
	
	[self windowWillClose: nil];
}

- (IBAction) setTextData:(id) sender
{
	NSString *newName = [sender stringValue];
	NSString *previous = [[[curROI name] copy] autorelease];
	
	@try
	{
		[curROI setName: newName];
		
		if ( [self allWithSameName] )
		{
			@try
			{
				[self setAllMatchingROIsToSameParamsAs: curROI matchingName: previous withNewName: newName];
			}
			@catch (NSException *e)
			{
				// The matching ROIs were restored by the callee; restore the edited ROI as well.
				@try { [curROI setName: previous]; }
				@catch (NSException *inner) { NSLog( @"ROIWindow: unable to restore name of %@: %@", curROI, inner.reason); }
				@throw;
			}
		}
	}
	@catch (NSException *e)
	{
		[self presentRenameFailure: e previousName: previous];
		return;
	}
	
	[[NSNotificationCenter defaultCenter] postNotificationName: OsirixROIChangeNotification object:curROI userInfo: nil];
}

- (IBAction) setThickness:(NSSlider*) sender
{
	[curROI setThickness: [sender floatValue]];
	[[NSNotificationCenter defaultCenter] postNotificationName: OsirixROIChangeNotification object:curROI userInfo: nil];
	
	if ( [self allWithSameName] ) [self setAllMatchingROIsToSameParamsAs: curROI withNewName: [curROI name]];
}

- (IBAction) setOpacity:(NSSlider*) sender
{
	[curROI setOpacity: [sender floatValue]];
	[[NSNotificationCenter defaultCenter] postNotificationName: OsirixROIChangeNotification object:curROI userInfo: nil];
	
	if ( [self allWithSameName] ) [self setAllMatchingROIsToSameParamsAs: curROI withNewName: [curROI name]];
}

- (IBAction) setColor:(NSColorWell*) sender
{
//	if( loaded == NO) return;
	
	CGFloat r, g, b;
	
	[[[sender color] colorUsingColorSpaceName: NSCalibratedRGBColorSpace] getRed:&r green:&g blue:&b alpha:nil];
	
	RGBColor c;
	
	c.red = r * 65535.;
	c.green = g * 65535.;
	c.blue = b * 65535.;
	
	[curROI setColor:c];
	[[NSNotificationCenter defaultCenter] postNotificationName: OsirixROIChangeNotification object:curROI userInfo: nil];
	
	if ( [self allWithSameName] ) [self setAllMatchingROIsToSameParamsAs: curROI withNewName: [curROI name]];

	[comments setTextColor:nil];
}

+ (void) addROIValues: (ROI*) r dictionary: (NSMutableDictionary*) d
{
    if( r.name.length)
        [d setObject: r.name forKey:@"Name"];
    
    if( r.comments.length)
        [d setObject: r.comments forKey:@"Comments"];
    
    NSMutableArray *ROIPoints = [NSMutableArray array];
    for( MyPoint *p in [r points])
        [ROIPoints addObject: NSStringFromPoint( [p point])];
    
    [d setObject: ROIPoints forKey:@"ROIPoints"];
    
    if( [r dataString])
        [d setObject:[r dataString] forKey:@"DataSummary"];
    
    if( [r dataValues])
        [d setObject:[r dataValues] forKey:@"DataValues"];
}

- (IBAction) exportData:(id) sender
{
	if([curROI type]==tPlain)
	{
		NSInteger confirm = NSRunInformationalAlertPanel(NSLocalizedString(@"Export to XML", @""), NSLocalizedString(@"Exporting this kind of ROI to XML will only export the contour line.", @""), NSLocalizedString(@"OK", @""), NSLocalizedString(@"Cancel", @""), nil);
		if(!confirm) return;
	}
	else if([curROI type]==tLayerROI)
	{
		NSRunAlertPanel(NSLocalizedString(@"Export to XML", @""), NSLocalizedString(@"This kind of ROI can not be exported to XML.", @""), NSLocalizedString(@"OK", @""), nil, nil);
		return;
	}
	
	NSSavePanel *panel = [NSSavePanel savePanel];
    panel.canSelectHiddenExtension = NO;
    panel.allowedFileTypes = @[@"xml"];
    panel.nameFieldStringValue = curROI.name;
    
    [panel beginWithCompletionHandler:^(NSInteger result) {
        if (result != NSFileHandlingPanelOKButton)
            return;

        NSMutableDictionary *xml = [NSMutableDictionary dictionary];
		
		if( [self allWithSameName])
		{
			NSArray *roiSeriesList = [curController roiList];
			NSMutableArray *roiArray = [NSMutableArray array];
			
			int i;			
			for ( i = 0; i < [roiSeriesList count]; i++ )
			{
				NSArray *roiImageList = [roiSeriesList objectAtIndex: i];
				
				for( ROI *roi in roiImageList )
				{
					if ( [[roi name] isEqualToString: [curROI name]])
					{
						NSMutableDictionary *roiData = [NSMutableDictionary dictionary];
						
                        [ROIWindow addROIValues: roi dictionary: roiData];
						[roiData setObject:[NSNumber numberWithInt: i + 1] forKey: @"Slice"];
						
						[roiArray addObject: roiData];
					}
				}
			}
			
			[xml setObject: roiArray forKey: @"ROI array"];
		}
		
		else // Output curROI only
            [ROIWindow addROIValues: curROI dictionary: xml];
		
		[xml writeToURL:panel.URL atomically:YES];
    }];
}

- (IBAction) histogram:(id) sender
{
	NSArray *winList = [NSApp windows];
	BOOL	found = NO;
	
	for( id loopItem in winList)
	{
		if( [[[loopItem windowController] windowNibName] isEqualToString:@"Histogram"])
		{
			if( [[loopItem windowController] curROI] == curROI)
			{
				found = YES;
				[[[loopItem windowController] window] makeKeyAndOrderFront:self];
			}
		}
	}
	
	if( found == NO)
	{
		if( [[curROI points] count] > 0)
		{
			HistoWindow* roiWin = [[HistoWindow alloc] initWithROI: curROI];
			[roiWin showWindow:self];
		}
		else NSRunAlertPanel(NSLocalizedString(@"Error", nil), NSLocalizedString(@"Cannot create an histogram from this ROI.", nil), nil, nil, nil);
	}
}

- (IBAction) plot:(id) sender
{
	NSArray *winList = [NSApp windows];
	BOOL	found = NO;
	
	for( id loopItem in winList)
	{
		if( [[[loopItem windowController] windowNibName] isEqualToString:@"Plot"])
		{
			if( [[loopItem windowController] curROI] == curROI)
			{
				found = YES;
				[[[loopItem windowController] window] makeKeyAndOrderFront:self];
			}
		}
	}
	
	if( found == NO)
	{
		PlotWindow* roiWin = [[PlotWindow alloc] initWithROI: curROI];
		[roiWin showWindow:self];
	}
}

-(ROI*) curROI {return curROI;}

@end
