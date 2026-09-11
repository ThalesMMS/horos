/*=========================================================================
  Program:   OsiriX

  Copyright (c) OsiriX Team
  All rights reserved.
  Distributed under GNU - LGPL
  
  See http://www.osirix-viewer.com/copyright.html for details.

     This software is distributed WITHOUT ANY WARRANTY; without even
     the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
     PURPOSE.
=========================================================================*/

#import <Cocoa/Cocoa.h>


#undef verify
#include "HorosStructuredReportBridge.h"

/** \brief  DICOM  key object note */
@interface KeyObjectReport : NSObject {
	id _study;
	HorosSRDocument *_doc;
	NSArray *_keyImages;
	NSString *_keyDescription;
	int _title;
	NSString *_seriesUID;
}

 - (id) initWithStudy:(id)study  
				title:(int)title   
				description:(NSString *)keyDescription
				seriesUID:(NSString *)seriesUID;
 - (void)createKO;
 - (BOOL)writeFileAtPath:(NSString *)path;
 - (BOOL)writeHTMLAtPath:(NSString *)path;
 - (NSString *)sopInstanceUID;

@end
