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


#import "ROIVolumeManagerController.h"
#import "ROIVolume.h"
#import "Notifications.h"
//#import "ColorWellCell.h"

@implementation ROIVolumeManagerController

- (id) initWithViewer:(Window3DController*) v
{
    self = [super initWithWindowNibName:@"ROIVolumeManager"];
    
	roiVolumes = [[NSMutableArray alloc] initWithCapacity:0];
	[roiVolumes setArray:[v roiVolumes]];
	
	viewer = v;
		
//	[self setRoiVolumes:[v roiVolumes]];
	
	//[[self window] setFrameAutosaveName:@"ROIVolumeManagerWindow"];
	
	// register to notification
	NSNotificationCenter *nc;
    nc = [NSNotificationCenter defaultCenter];	
	[nc addObserver: self
           selector: @selector(Window3DClose:)
               name: OsirixWindow3dCloseNotification
             object: nil];
//	[nc addObserver: self
//           selector: @selector(roiListModification:)
//               name: OsirixROIChangeNotification
//             object: nil];
//	[nc addObserver: self
//           selector: @selector(fireUpdate:)
//               name: OsirixRemoveROINotification
//             object: nil];
//	[nc addObserver: self
//           selector: @selector(roiListModification:)
//               name: OsirixDCMUpdateCurrentImageNotification
//             object: nil];
//	[nc addObserver: self
//           selector: @selector(roiListModification:)
//               name: OsirixROISelectedNotification
//             object: nil];
	[tableView setDataSource:self];
	//[tableView setDelegate:self];

	return self;
}

- (void)windowDidLoad
{
    [super windowDidLoad];
    [tableView setDelegate:self];
    [tableView setRowHeight:26.0];
    for (NSTableColumn *column in [tableView tableColumns])
    {
        NSString *key = [[column identifier] isEqualToString:@"display"] ? @"visible" : [column identifier];
        [column setSortDescriptorPrototype:[NSSortDescriptor sortDescriptorWithKey:
            [@"properties." stringByAppendingString:key] ascending:YES]];
    }
}

- (ROIVolume *)volumeAtRow:(NSInteger)row
{
    NSArray *volumes = [roiVolumesController arrangedObjects];
    return row >= 0 && row < (NSInteger)[volumes count] ? [volumes objectAtIndex:row] : nil;
}

- (NSInteger)numberOfRowsInTableView:(NSTableView *)aTableView
{
    return [[roiVolumesController arrangedObjects] count];
}

- (NSView *)tableView:(NSTableView *)aTableView viewForTableColumn:(NSTableColumn *)column row:(NSInteger)row
{
    ROIVolume *volume = [self volumeAtRow:row];
    if (!volume) return nil;

    NSString *identifier = [column identifier];
    BOOL checkbox = [identifier isEqualToString:@"display"] || [identifier isEqualToString:@"texture"];
    BOOL slider = [identifier isEqualToString:@"red"] || [identifier isEqualToString:@"green"] ||
                  [identifier isEqualToString:@"blue"] || [identifier isEqualToString:@"opacity"];
    NSTableCellView *cell = [aTableView makeViewWithIdentifier:identifier owner:self];
    NSControl *control = (NSControl *)[cell viewWithTag:1];
    if (!cell)
    {
        cell = [[[NSTableCellView alloc] initWithFrame:NSMakeRect(0, 0, [column width], [aTableView rowHeight])] autorelease];
        [cell setIdentifier:identifier];
        if (slider)
        {
            // A cell-only slider uses the entire NSTableView as its controlView.
            // Give each slider its own view so drawing and tracking share bounds.
            NSSlider *valueSlider = [NSSlider sliderWithValue:0 minValue:0 maxValue:1
                                                    target:self action:@selector(changeROIVolume:)];
            [valueSlider setContinuous:YES];
            control = valueSlider;
        }
        else if (checkbox)
            control = [NSButton checkboxWithTitle:@"" target:self action:@selector(changeROIVolume:)];
        else
        {
            NSTextField *text = [[[NSTextField alloc] initWithFrame:NSZeroRect] autorelease];
            [text setBordered:NO];
            [text setDrawsBackground:NO];
            [text setEditable:[[column dataCell] isEditable]];
            [text setSelectable:YES];
            [text setFont:[NSFont systemFontOfSize:[NSFont smallSystemFontSize]]];
            [text setLineBreakMode:NSLineBreakByTruncatingTail];
            [cell setTextField:text];
            control = text;
        }
        [control setTag:1];
        [control setControlSize:NSControlSizeSmall];
        [control setTarget:self];
        [control setAction:@selector(changeROIVolume:)];
        [control setTranslatesAutoresizingMaskIntoConstraints:NO];
        [cell addSubview:control];
        [NSLayoutConstraint activateConstraints:@[
            [[control centerYAnchor] constraintEqualToAnchor:[cell centerYAnchor]],
            [[control heightAnchor] constraintEqualToConstant:20.0]
        ]];
        if (checkbox)
            [NSLayoutConstraint activateConstraints:@[
                [[control centerXAnchor] constraintEqualToAnchor:[cell centerXAnchor]]
            ]];
        else
            [NSLayoutConstraint activateConstraints:@[
                [[control leadingAnchor] constraintEqualToAnchor:[cell leadingAnchor] constant:4.0],
                [[control trailingAnchor] constraintEqualToAnchor:[cell trailingAnchor] constant:-4.0]
            ]];
    }
    NSString *key = [identifier isEqualToString:@"display"] ? @"visible" : identifier;
    [control setObjectValue:[[volume properties] objectForKey:key]];
    NSString *label = [[column headerCell] stringValue];
    if (![label length]) label = NSLocalizedString(@"Visible", nil);
    [control setAccessibilityLabel:[NSString stringWithFormat:@"%@, %@", label,
                                   [[volume properties] objectForKey:@"name"]]];
    return cell;
}

- (void)changeROIVolume:(NSControl *)sender
{
    NSInteger row = [tableView rowForView:sender];
    NSInteger column = [tableView columnForView:sender];
    if (row < 0 || column < 0) return;
    [self tableView:tableView setObjectValue:[sender objectValue]
        forTableColumn:[[tableView tableColumns] objectAtIndex:column] row:row];
}

- (void)tableView:(NSTableView *)aTableView setObjectValue:(id)value forTableColumn:(NSTableColumn *)column row:(NSInteger)row
{
    ROIVolume *volume = [self volumeAtRow:row];
    if (!volume) return;
    NSString *identifier = [column identifier];
    if ([identifier isEqualToString:@"display"])
    {
        [volume setVisible:[value boolValue]];
        if ([value boolValue]) [viewer displayROIVolume:volume];
        else [viewer hideROIVolume:volume];
    }
    else if ([identifier isEqualToString:@"red"]) [volume setRed:[value floatValue]];
    else if ([identifier isEqualToString:@"green"]) [volume setGreen:[value floatValue]];
    else if ([identifier isEqualToString:@"blue"]) [volume setBlue:[value floatValue]];
    else if ([identifier isEqualToString:@"opacity"]) [volume setOpacity:[value floatValue]];
    else if ([identifier isEqualToString:@"texture"]) [volume setTexture:[value boolValue]];
    else
    {
        // Preserve the name/volume fields' former properties-dictionary bindings.
        [[volume properties] setValue:value forKey:identifier];
        return;
    }
    [[viewer view] display];
    // Reloading here would replace a continuous slider while it is tracking.
}

- (void)tableView:(NSTableView *)aTableView sortDescriptorsDidChange:(NSArray *)oldDescriptors
{
    ROIVolume *selected = [self volumeAtRow:[aTableView selectedRow]];
    [roiVolumesController setSortDescriptors:[aTableView sortDescriptors]];
    [aTableView reloadData];
    NSUInteger row = selected ? [[roiVolumesController arrangedObjects] indexOfObjectIdenticalTo:selected] : NSNotFound;
    if (row != NSNotFound)
        [aTableView selectRowIndexes:[NSIndexSet indexSetWithIndex:row] byExtendingSelection:NO];
}

// delegate method

-(void) Window3DClose:(NSNotification*) note
{	
	if( [note object] == viewer)
	{
		NSLog( @"ROIVolumeManager Window3DClose");
		[[self window] close];
	}
}

- (void) windowWillClose:(NSNotification *)notification
{
	[[self window] setAcceptsMouseMovedEvents: NO];
	
	[[NSNotificationCenter defaultCenter] removeObserver: self];
	NSLog( @"ROIVolumeManager windowWillClose");
	[tableView setDelegate:nil];
	[tableView setDataSource: nil];
	[controllerAlias setContent: nil];	// To allow the dealloc of MPRController ! otherwise memory leak
    
	[self autorelease];
}

- (void) dealloc
{
	NSLog( @"ROIVolumeManager dealloc");
	viewer = nil;
	[roiVolumes release];
    [[NSNotificationCenter defaultCenter] removeObserver: self];
	[super dealloc];
}

- (void) setRoiVolumes: (NSMutableArray*) volumes
{
//	NSLog(@"setRoiVolumes : [volumes count] : %d", [volumes count]);
	[roiVolumes setArray:volumes];
//	NSLog(@"setRoiVolumes : [roiVolumes count] : %d", [roiVolumes count]);
//	NSLog(@"setRoiVolumes : [[self roiVolumes] count] : %d", [[self roiVolumes] count]);
}

- (NSMutableArray*) roiVolumes
{
	return roiVolumes;
}

@end
