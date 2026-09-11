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

#import "DicomFileDCMTKCategory.h"
// This file is also compiled into the Decompress helper, which has no Swift and
// therefore no generated header. The helper does not export metadata; there, a
// keyword is looked up in the one spelling it was written in.
#if __has_include("Horos-Swift.h")
#import "Horos-Swift.h"
#define HOROS_KEYWORD_SPELLINGS 1
#endif
#import "DCMAbstractSyntaxUID.h"
#import "DICOMToNSString.h"
#import "DCMCharacterSet.h"
#import "MutableArrayCategory.h"
#import "DicomStudy.h"
#import "SRAnnotation.h"
#import "N2Debug.h"
#import "HorosDerivedUID.h"
#import "DICOMDataDictionary.h"

#include "HorosDCMTKCompatibility.h"
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dcfilefo.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/ofstd/ofstd.h>

#include <dcmtk/dcmdata/dctk.h>
#include "HorosDCMTKCompatibility.h"
#include <dcmtk/dcmdata/cmdlnarg.h>
#include <dcmtk/ofstd/ofconapp.h>
#include <dcmtk/dcmdata/dcuid.h>       /* for dcmtk version name */
#include <dcmtk/dcmjpeg/djdecode.h>    /* for dcmjpeg decoders */
#include <dcmtk/dcmjpeg/dipijpeg.h>    /* for dcmimage JPEG plugin */

#ifdef OSIRIX_VIEWER
#ifndef OSIRIX_LIGHT
#include <NrrdIO.h> // part of ITK
#endif
#endif

#include <string>

extern NSRecursiveLock *PapyrusLock;

@implementation DicomFile (DicomFileDCMTKCategory)

+ (NSArray*) getEncodingArrayForFile: (NSString*) file
{
    DcmFileFormat fileformat;
    NSArray *encodingArray = nil;
    
    OFCondition status = fileformat.loadFile( [file UTF8String], EXS_Unknown, EGL_noChange, DCM_MaxReadLength, ERM_autoDetect);
    
    DcmDataset *dataset = fileformat.getDataset();
    
    const char *string = NULL;
    
    if( dataset && dataset->findAndGetString(DCM_SpecificCharacterSet, string, OFFalse).good() && string != NULL)
    {
        encodingArray = [[NSString stringWithCString:string encoding: NSISOLatin1StringEncoding] componentsSeparatedByString:@"\\"];
    }
    
    if( encodingArray == nil)
    {
        // The same choice as at index time: a file that states nothing is read as
        // whatever DefaultCharacterSetWhenAbsent names, and as Latin-1 when it
        // names nothing.
        NSString *chosen = [DCMCharacterSet characterSetWhenAbsent];
        encodingArray = [NSArray arrayWithObject: chosen.length ? chosen : @"ISO_IR 100"];
    }
    
    return encodingArray;
}

+ (BOOL) isDICOMFileDCMTK:(NSString *) file{
    DcmFileFormat fileformat;
    OFCondition status = fileformat.loadFile([file UTF8String]);
    if (status.good())
        return YES;
    return NO;
}

+ (BOOL) isNRRDFile:(NSString *) file
{
    int success = NO;
    NSString	*extension = [[file pathExtension] lowercaseString];
    
    if( [extension isEqualToString:@"nrrd"])
    {
        success = YES;
    }
    return success;
}

+ (NSString*) getDicomFieldForGroup:(int) gr element: (int) el forDcmFileFormat: (void*) ff
{
    NSString *returnedValue = nil;
    DcmFileFormat *fileformat = (DcmFileFormat*) ff;
    
    if( fileformat)
    {
        @try
        {
            OFString string;
            DcmDataset *dataset = fileformat->getDataset();
            
            DcmTagKey dcmkey( gr, el);
            
            if( dataset && dataset->findAndGetOFString( dcmkey, string, OFFalse).good() && string.length() > 0)
                returnedValue = [NSString stringWithCString:string.c_str() encoding: NSISOLatin1StringEncoding];
            
            if( returnedValue == nil)
            {
                //Maybe in the metadata?
                DcmMetaInfo *metaset = fileformat->getMetaInfo();
                
                if( metaset && metaset->findAndGetOFString( dcmkey, string, OFFalse).good() && string.length() > 0)
                    returnedValue = [NSString stringWithCString:string.c_str() encoding: NSISOLatin1StringEncoding];
            }
            
        }
        @catch (NSException *exception) {
            N2LogException( exception);
        }
    }
    
    return returnedValue;
}

+ (NSDictionary*) valuesForDicomFields: (NSArray*) fields forFile: (NSString*) path
{
    if( fields.count == 0 || path.length == 0) return @{};
    
    DcmFileFormat fileformat;
    [PapyrusLock lock];
    OFCondition status = fileformat.loadFile( [path fileSystemRepresentation], EXS_Unknown, EGL_noChange, DCM_MaxReadLength, ERM_autoDetect);
    [PapyrusLock unlock];
    if( status.bad()) return @{};
    
    DcmDataset *dataset = fileformat.getDataset();
    DcmMetaInfo *metaset = fileformat.getMetaInfo();
    
    // The bytes of a name are in the file's own character set, and reading them
    // as Latin-1 turns a Japanese or Greek name into rubbish that then goes into
    // the file somebody opens in a spreadsheet.
    NSStringEncoding encoding = NSISOLatin1StringEncoding;
    const char *declared = NULL;
    if( dataset && dataset->findAndGetString( DCM_SpecificCharacterSet, declared, OFFalse).good() && declared != NULL)
    {
        NSString *first = [[[NSString stringWithCString: declared encoding: NSISOLatin1StringEncoding]
                            componentsSeparatedByString: @"\\"] firstObject];
        if( first.length)
            encoding = [NSString encodingForDICOMCharacterSet: [first stringByTrimmingCharactersInSet: [NSCharacterSet whitespaceCharacterSet]]];
    }
    
    NSMutableDictionary *values = [NSMutableDictionary dictionary];
    for( NSString *field in fields)
    {
        DcmTagKey key( 0xffff, 0xffff);
        unsigned group = 0, element = 0;
        NSString *trimmed = [field stringByTrimmingCharactersInSet: [NSCharacterSet characterSetWithCharactersInString: @"() \t"]];
        
        if( sscanf( [trimmed UTF8String], "%x,%x", &group, &element) == 2)
            key = DcmTagKey( group, element);
        else
        {
            unsigned resolvedGroup = 0xffff, resolvedElement = 0xffff;
            if( HorosResolveDicomKeyword( field, &resolvedGroup, &resolvedElement))
                key = DcmTagKey( resolvedGroup, resolvedElement);
        }
        
        if( key.getGroup() == 0xffff && key.getElement() == 0xffff)
            continue;                                   // not a field this can name
        
        OFString text;
        BOOL found = (dataset && dataset->findAndGetOFStringArray( key, text, OFFalse).good());
        if( !found)
            found = (metaset && metaset->findAndGetOFStringArray( key, text, OFFalse).good());
        
        if( found)
        {
            NSString *value = [[NSString alloc] initWithBytes: text.c_str() length: text.length() encoding: encoding];
            if( value == nil)                           // the declared set does not decode these bytes
                value = [[NSString alloc] initWithBytes: text.c_str() length: text.length() encoding: NSISOLatin1StringEncoding];
            if( value) [values setObject: value forKey: field];
            [value release];
        }
    }
    
    return values;
}

+ (NSString*) newSeriesUID
{
    char buffer[100];
    dcmGenerateUniqueIdentifier( buffer, SITE_SERIES_UID_ROOT);
    return [NSString stringWithUTF8String: buffer];
}

// The crop writer asks a Swift type where the cropped image sits, so it belongs
// to the target that has Swift. The Decompress helper, which also compiles this
// file, does not crop.
#ifdef HOROS_KEYWORD_SPELLINGS

static NSError *cropFailure( NSString *reason)
{
    return [NSError errorWithDomain: @"HorosCrop" code: 1
                           userInfo: @{NSLocalizedDescriptionKey: reason}];
}

+ (BOOL) writeCropOfFile: (NSString*) source
                  toPath: (NSString*) destination
                  column: (int) column row: (int) row
                   width: (int) width height: (int) height
               seriesUID: (NSString*) seriesUID
            seriesNumber: (int) seriesNumber
                   error: (NSError**) error
{
// Variadic, because some of the reasons are built with stringWithFormat: and a
    // comma inside an argument ends a macro argument.
#define FAIL( ...) { if( error) *error = cropFailure( __VA_ARGS__); return NO; }
    DcmFileFormat fileformat;
    [PapyrusLock lock];
    OFCondition status = fileformat.loadFile( [source fileSystemRepresentation], EXS_Unknown, EGL_noChange, DCM_MaxReadLength, ERM_autoDetect);
    [PapyrusLock unlock];
    if( status.bad())
        FAIL( [NSString stringWithFormat: @"%s could not be read", source.lastPathComponent.UTF8String])
    
    DcmDataset *dataset = fileformat.getDataset();
    if( dataset == NULL) FAIL( @"that file has no data set")
    
    // Encapsulated pixel data is a codec\'s business, not a memcpy\'s. Say so
    // rather than writing a file whose pixels are a compressed stream cut in half.
    E_TransferSyntax original = dataset->getOriginalXfer();
    DcmXfer xfer( original);
    if( xfer.isEncapsulated())
        FAIL( @"that image is compressed; decompress it before cropping")
    
    Uint16 rows = 0, columns = 0, allocated = 0, samples = 1;
    if( dataset->findAndGetUint16( DCM_Rows, rows).bad() ||
        dataset->findAndGetUint16( DCM_Columns, columns).bad() ||
        dataset->findAndGetUint16( DCM_BitsAllocated, allocated).bad())
        FAIL( @"that image does not say how big it is")
    dataset->findAndGetUint16( DCM_SamplesPerPixel, samples);
    if( samples < 1) samples = 1;
    if( allocated != 8 && allocated != 16)
        FAIL( [NSString stringWithFormat: @"%u bits per sample is not handled here", allocated])
    
    NSArray *inside = [HorosCroppedImageGeometry rectangleInsideColumns: columns rows: rows
                                                                 column: column row: row
                                                                  width: width height: height];
    int left = [inside[0] intValue], top = [inside[1] intValue];
    int cropWidth = [inside[2] intValue], cropHeight = [inside[3] intValue];
    if( cropWidth <= 0 || cropHeight <= 0)
        FAIL( @"that rectangle is outside the image")
    
    const Uint8 *pixels = NULL;
    unsigned long length = 0;
    if( dataset->findAndGetUint8Array( DCM_PixelData, pixels, &length).bad() || pixels == NULL)
        FAIL( @"that file has no pixel data")
    
    const unsigned long bytesPerPixel = (allocated / 8) * samples;
    const unsigned long frames = length / ((unsigned long) rows * columns * bytesPerPixel);
    if( frames == 0) FAIL( @"the pixel data is shorter than one frame")
    
    NSMutableData *cropped = [NSMutableData dataWithLength: (NSUInteger) frames * cropWidth * cropHeight * bytesPerPixel];
    Uint8 *out = (Uint8*) cropped.mutableBytes;
    for( unsigned long frame = 0; frame < frames; frame++)
    {
        const Uint8 *frameStart = pixels + frame * rows * columns * bytesPerPixel;
        for( int y = 0; y < cropHeight; y++)
            memcpy( out + ((frame * cropHeight) + y) * cropWidth * bytesPerPixel,
                   frameStart + (((unsigned long)(top + y)) * columns + left) * bytesPerPixel,
                   (size_t) cropWidth * bytesPerPixel);
    }
    
    // The new first pixel is somewhere else, and everything measured against this
    // image depends on saying so.
    OFString positionText, orientationText, spacingText;
    if( dataset->findAndGetOFStringArray( DCM_ImagePositionPatient, positionText).good() &&
        dataset->findAndGetOFStringArray( DCM_ImageOrientationPatient, orientationText).good() &&
        dataset->findAndGetOFStringArray( DCM_PixelSpacing, spacingText).good())
    {
        NSArray *position = [[NSString stringWithUTF8String: positionText.c_str()] componentsSeparatedByString: @"\\"];
        NSArray *orientation = [[NSString stringWithUTF8String: orientationText.c_str()] componentsSeparatedByString: @"\\"];
        NSArray *spacing = [[NSString stringWithUTF8String: spacingText.c_str()] componentsSeparatedByString: @"\\"];
        NSArray *moved = [HorosCroppedImageGeometry positionForPosition: [position valueForKey: @"doubleValue"]
                                                            orientation: [orientation valueForKey: @"doubleValue"]
                                                                spacing: [spacing valueForKey: @"doubleValue"]
                                                                 column: left row: top];
        if( moved.count == 3)
            dataset->putAndInsertString( DCM_ImagePositionPatient,
                [[NSString stringWithFormat: @"%.6f\\%.6f\\%.6f", [moved[0] doubleValue], [moved[1] doubleValue], [moved[2] doubleValue]] UTF8String]);
    }
    
    dataset->putAndInsertUint16( DCM_Rows, cropHeight);
    dataset->putAndInsertUint16( DCM_Columns, cropWidth);
    dataset->putAndInsertUint8Array( DCM_PixelData, (const Uint8*) cropped.bytes, (unsigned long) cropped.length);
    
    // A derived instance, with the original named as its source, and its own
    // identity: the same identifiers would make it the original as far as any
    // other reader is concerned.
    OFString sourceClass, sourceInstance;
    dataset->findAndGetOFString( DCM_SOPClassUID, sourceClass);
    dataset->findAndGetOFString( DCM_SOPInstanceUID, sourceInstance);
    
    char newInstance[100];
    dcmGenerateUniqueIdentifier( newInstance, SITE_INSTANCE_UID_ROOT);
    dataset->putAndInsertString( DCM_SOPInstanceUID, newInstance);
    if( seriesUID.length)
        dataset->putAndInsertString( DCM_SeriesInstanceUID, [seriesUID UTF8String]);
    dataset->putAndInsertString( DCM_SeriesNumber, [[NSString stringWithFormat: @"%d", seriesNumber] UTF8String]);
    dataset->putAndInsertString( DCM_ImageType, "DERIVED\\SECONDARY");
    dataset->putAndInsertString( DCM_DerivationDescription,
        [[NSString stringWithFormat: @"Cropped to %d x %d at (%d, %d) of %u x %u",
          cropWidth, cropHeight, left, top, columns, rows] UTF8String]);
    dataset->putAndInsertString( DCM_SeriesDescription,
        [[NSString stringWithFormat: @"Cropped %d x %d", cropWidth, cropHeight] UTF8String]);
    
    DcmItem *reference = NULL;
    if( dataset->findOrCreateSequenceItem( DCM_SourceImageSequence, reference, -2).good() && reference)
    {
        reference->putAndInsertString( DCM_ReferencedSOPClassUID, sourceClass.c_str());
        reference->putAndInsertString( DCM_ReferencedSOPInstanceUID, sourceInstance.c_str());
    }
    
    fileformat.getMetaInfo()->putAndInsertString( DCM_MediaStorageSOPInstanceUID, newInstance);
    
    [PapyrusLock lock];
    OFCondition written = fileformat.saveFile( [destination fileSystemRepresentation], EXS_LittleEndianExplicit);
    [PapyrusLock unlock];
    if( written.bad())
        FAIL( [NSString stringWithFormat: @"the cropped file could not be written (%s)", written.text()])
    
    return YES;
#undef FAIL
}

#endif  // HOROS_KEYWORD_SPELLINGS

+ (NSDictionary*) acquisitionTimingForFile: (NSString*) path
{
    if( path.length == 0) return @{};
    DcmFileFormat fileformat;
    [PapyrusLock lock];
    OFCondition status = fileformat.loadFile( [path fileSystemRepresentation], EXS_Unknown, EGL_noChange, DCM_MaxReadLength, ERM_autoDetect);
    [PapyrusLock unlock];
    if( status.bad()) return @{};

    // Read the four ASCII temporal tags together, preserving their original precision.
    NSMutableDictionary *record = [NSMutableDictionary dictionary];
    NSArray *names = @[@"AcquisitionDateTime", @"AcquisitionDate", @"AcquisitionTime", @"TimezoneOffsetFromUTC"];
    const Uint16 elements[] = {0x002a, 0x0022, 0x0032, 0x0201};
    for( NSUInteger i = 0; i < names.count; i++)
    {
        OFString value;
        if( fileformat.getDataset()->findAndGetOFStringArray( DcmTagKey(0x0008, elements[i]), value).good())
        {
            NSString *text = [NSString stringWithCString: value.c_str() encoding: NSASCIIStringEncoding];
            if( text) [record setObject: text forKey: [names objectAtIndex: i]];
        }
    }
    return record;
}

+ (NSString*) getDicomField: (NSString*) field forFile: (NSString*) path
{
    if( field.length <= 0)
        return nil;
    
    unsigned group = 0xffff, element = 0xffff;
    if( !HorosResolveDicomKeyword( field, &group, &element))
        return nil;
    DcmTagKey dcmkey( group, element);
    
    if( dcmkey.getGroup() != 0xffff && dcmkey.getElement() != 0xffff)
    {
        [PapyrusLock lock];
        
        DcmFileFormat fileformat;
        
        OFCondition status = fileformat.loadFile( [path UTF8String],  EXS_Unknown, EGL_noChange, DCM_MaxReadLength, ERM_autoDetect);
        
        [PapyrusLock unlock];
        
        if (status.good())
            return [DicomFile getDicomFieldForGroup: dcmkey.getGroup()  element:dcmkey.getElement() forDcmFileFormat: &fileformat];
    }
    
    return nil;
}

-(short) getNRRDFile
{
#ifdef OSIRIX_VIEWER
#ifndef OSIRIX_LIGHT
    int			success = 0;
    NSString	*extension = [[filePath pathExtension] lowercaseString];
    char		*err = nil;
    
    if( [extension isEqualToString:@"nrrd"])
    {
        Nrrd *nin;
        
        /* create a nrrd; at this point this is just an empty container */
        nin = nrrdNew();
        
        /* read in the nrrd from file */
        if (nrrdLoad(nin, [filePath UTF8String], NULL))
        {
            err = biffGetDone(NRRD);
            fprintf(stderr, "trouble reading \"%s\":\n%s", [filePath UTF8String], err);
            free(err);
            return success;
        }
        
        printf("\"%s\" is a %d-dimensional nrrd of type %d (%s)\n",
               [filePath UTF8String], nin->dim, nin->type,
               airEnumStr(nrrdType, nin->type));
        
        printf("the array contains %d elements, each %d bytes in size\n",
               (int)nrrdElementNumber(nin), (int)nrrdElementSize(nin));
        
        if( nin->dim > 1)
        {
            height = 512;
            width = 512;
            
            NoOfSeries = 1;
            
            imageID = [[NSString alloc] initWithString: [[NSDate date] description]];
            self.serieID = [[NSDate date] description];
            
            unsigned int random = (unsigned int)time(NULL);
            studyID = [[NSString alloc] initWithFormat:@"%d", random];
            
            name = [[NSString alloc] initWithString:[filePath lastPathComponent]];
            patientID = [[NSString alloc] initWithString:name];
            study = [[NSString alloc] initWithString:[filePath lastPathComponent]];
            Modality = [[NSString alloc] initWithString:@"RD"];
            date = [[NSCalendarDate date] retain];
            serie = [[NSString alloc] initWithString:[filePath lastPathComponent]];
            fileType = [@"IMAGE" retain];
            
            
            NoOfFrames = 1;
            
            [dicomElements setObject:studyID forKey:@"studyID"];
            [dicomElements setObject:study forKey:@"studyDescription"];
            [dicomElements setObject:date forKey:@"studyDate"];
            [dicomElements setObject:Modality forKey:@"modality"];
            [dicomElements setObject:patientID forKey:@"patientID"];
            [dicomElements setObject:name forKey:@"patientName"];
            [dicomElements setObject:[self patientUID] forKey:@"patientUID"];
            [dicomElements setObject:self.serieID forKey:@"seriesID"];
            [dicomElements setObject:name forKey:@"seriesDescription"];
            [dicomElements setObject:[NSNumber numberWithInt: 0] forKey:@"seriesNumber"];
            [dicomElements setObject:imageID forKey:@"SOPUID"];
            [dicomElements setObject:[NSNumber numberWithInt:[imageID intValue]] forKey:@"imageID"];
            [dicomElements setObject:fileType forKey:@"fileType"];
        }
        
        nrrdNuke(nin);
        
        // ********** Now, test the IO of ITK
        
        //		typedef itk::Image<char,4> TestImageType; // pixel type doesn't matter for current purpose
        //		typedef itk::ImageFileReader<TestImageType> TestFileReaderType; // reader for testing a file
        //		TestFileReaderType::Pointer onefileReader = TestFileReaderType::New();
        //
        //		onefileReader->SetFileName([filePath UTF8String]);
        //
        //		try
        //		{
        //			onefileReader->GenerateOutputInformation();
        //		}
        //		catch(itk::ExceptionObject &excp)
        //		{
        //			return -1;
        //		}
        //
        //		// grab the ImageIO instance for the reader
        //		itk::ImageIOBase *imageIO = onefileReader->GetImageIO();
        //		unsigned int NumberOfDimensions =  imageIO->GetNumberOfDimensions();
        //		//std::endl;
        //		unsigned dims[32];   // almost always no more than 4 dims, but ...
        //		unsigned origin[32];
        //		double spacing[32];
        //		std::vector<double> directions[32];
        //		for(unsigned i = 0; i < NumberOfDimensions && i < 32; i++)
        //		 {
        //		 dims[i] = imageIO->GetDimensions(i);
        //		 origin[i] = imageIO->GetOrigin(i);
        //		 spacing[i] = imageIO->GetSpacing(i);
        //		 directions[i] = imageIO->GetDirection(i);
        //		 }
        ////		// PixelType is SCALAR, RGB, RGBA, VECTOR, COVARIANTVECTOR, POINT,INDEX
        ////		itk::ImageIOBase::PixelType pixelType = imageIO->GetPixelType();
        ////		// IOComponentType is UCHAR, CHAR, USHORT, SHORT, UINT, INT, ULONG,LONG, FLOAT, DOUBLE
        ////		itk::ImageIOBase::IOComponentType componentType = imageIO->GetIOComponentType();
        ////		const std::type_info &typeinfo typeInfo = imageIO->GetComponentTypeInfo();
        ////		// NumberOfComponents is usually one, but for non-scalar pixel types, it can be anything
        //		unsigned int NumberOfComponents = imageIO->GetNumberOfComponents();
    }
    
    if (success)
        return 0;
    else
#endif
#endif
        return -1;
}

-(short) getDicomFileDCMTK
{
    int i;
    long cardiacTime = -1;
    
    NSStringEncoding encoding[ 10];
    NSString *echoTime = nil;
    const char *string = NULL;
    NSMutableArray *imageTypeArray = nil;
    
    DcmFileFormat fileformat;
    [PapyrusLock lock];
    
    OFCondition status = fileformat.loadFile([filePath UTF8String],  EXS_Unknown, EGL_noChange, DCM_MaxReadLength, ERM_autoDetect);
    
    [PapyrusLock unlock];
    
    if (status.good())
    {
        for( i = 0; i < 10; i++) encoding[ i] = 0;
        // Not Latin-1 outright: a file that states no Specific Character Set is
        // read as whatever DefaultCharacterSetWhenAbsent names, which is empty by
        // default and then means Latin-1 as before.
        encoding[ 0] = [NSString encodingForDICOMCharacterSet: nil];
        
        DcmDataset *dataset = fileformat.getDataset();
        
        //TransferSyntax
        // Both MPEG-2 syntaxes, Main Level and High Level: the viewer decodes
        // neither, and only the first was being recognised.
        static NSSet *mpeg2Syntaxes = nil;
        if( mpeg2Syntaxes == nil)
            mpeg2Syntaxes = [[NSSet setWithObjects: @"1.2.840.10008.1.2.4.100", @"1.2.840.10008.1.2.4.101", nil] retain];

        if (fileformat.getMetaInfo()->findAndGetString(DCM_TransferSyntaxUID, string, OFFalse).good() && string != NULL
            && [mpeg2Syntaxes containsObject: [NSString stringWithCString:string encoding: NSASCIIStringEncoding]])
        {
            fileType = [@"DICOMMPEG2" retain];
            [dicomElements setObject:fileType forKey:@"fileType"];
        }
        else
        {
            fileType = [@"DICOM" retain];
            [dicomElements setObject:fileType forKey:@"fileType"];
        }
        
        // PrivateInformationCreatorUID
        if (fileformat.getMetaInfo()->findAndGetString(DCM_PrivateInformationCreatorUID, string, OFFalse).good() && string != NULL) {
            [dicomElements setObject:[NSString stringWithCString:string encoding:NSISOLatin1StringEncoding] forKey:@"PrivateInformationCreatorUID"];
        }
        
        //Character Set
        if (dataset->findAndGetString(DCM_SpecificCharacterSet, string, OFFalse).good() && string != NULL)
        {
            NSArray	*c = [[NSString stringWithCString:string encoding: NSISOLatin1StringEncoding] componentsSeparatedByString:@"\\"];
            
            if( [c count] >= 10) NSLog( @"Encoding number >= 10 ???");
            
            if( [c count] < 10)
            {
                for( i = 0; i < [c count]; i++) encoding[ i] = [NSString encodingForDICOMCharacterSet: [c objectAtIndex: i]];
                for( i = (int)[c count]; i < 10; i++) encoding[ i] = [NSString encodingForDICOMCharacterSet: [c lastObject]];
            }
        }
        
        if ([self autoFillComments]  == YES) // ||[self checkForLAVIM] == YES)
        {
            if( [self autoFillComments])
            {
                NSString *commentsField = nil;
                DcmItem *dicomItems = nil;
                
                if( [self commentsGroup] && [self commentsElement])
                {
                    DcmTagKey key = DcmTagKey([self commentsGroup], [self commentsElement]);
                    
                    if( [self commentsGroup] == 2) // MetaHeader
                        dicomItems = fileformat.getMetaInfo();
                    else
                        dicomItems = dataset;
                    
                    if( dicomItems->findAndGetString(key, string, OFFalse).good() && string != NULL)
                        commentsField = [DicomFile stringWithBytes: (char*) string encodings:encoding];
                }
                
                if( [self commentsGroup2] && [self commentsElement2])
                {
                    DcmTagKey key = DcmTagKey([self commentsGroup2], [self commentsElement2]);
                    
                    if( [self commentsGroup2] == 2) // MetaHeader
                        dicomItems = fileformat.getMetaInfo();
                    else
                        dicomItems = dataset;
                    
                    if( dicomItems->findAndGetString(key, string, OFFalse).good() && string != NULL)
                    {
                        if( commentsField)
                            commentsField = [commentsField stringByAppendingFormat: @" / %@", [DicomFile stringWithBytes: (char*) string encodings:encoding]];
                        else
                            commentsField = [DicomFile stringWithBytes: (char*) string encodings:encoding];
                        [dicomElements setObject:commentsField forKey:@"commentsAutoFill"];
                    }
                }
                
                if( [self commentsGroup3] && [self commentsElement3])
                {
                    DcmTagKey key = DcmTagKey([self commentsGroup3], [self commentsElement3]);
                    
                    if( [self commentsGroup3] == 2) // MetaHeader
                        dicomItems = fileformat.getMetaInfo();
                    else
                        dicomItems = dataset;
                    
                    if( dicomItems->findAndGetString(key, string, OFFalse).good() && string != NULL)
                    {
                        if( commentsField)
                            commentsField = [commentsField stringByAppendingFormat: @" / %@", [DicomFile stringWithBytes: (char*) string encodings:encoding]];
                        else
                            commentsField = [DicomFile stringWithBytes: (char*) string encodings:encoding];
                        [dicomElements setObject:commentsField forKey:@"commentsAutoFill"];
                    }
                }
                
                if( [self commentsGroup4] && [self commentsElement4])
                {
                    DcmTagKey key = DcmTagKey([self commentsGroup4], [self commentsElement4]);
                    
                    if( [self commentsGroup4] == 2) // MetaHeader
                        dicomItems = fileformat.getMetaInfo();
                    else
                        dicomItems = dataset;
                    
                    if( dicomItems->findAndGetString(key, string, OFFalse).good() && string != NULL)
                    {
                        if( commentsField)
                            commentsField = [commentsField stringByAppendingFormat: @" / %@", [DicomFile stringWithBytes: (char*) string encodings:encoding]];
                        else
                            commentsField = [DicomFile stringWithBytes: (char*) string encodings:encoding];
                        [dicomElements setObject:commentsField forKey:@"commentsAutoFill"];
                    }
                }
                
                if( commentsField)
                    [dicomElements setObject:commentsField forKey:@"commentsAutoFill"];
            }
            
            //			if([self checkForLAVIM] == YES)
            //			{
            //				NSString	*album = nil;
            //				if (dataset->findAndGetString(DCM_ImageComments, string, OFFalse).good() && string != NULL)
            //				{
            //					album = [NSString stringWithUTF8String:string encoding: NSISOLatin1StringEncoding];
            //					if( [album length] >= 2)
            //					{
            //						if( [[album substringToIndex:2] isEqualToString: @"LV"])
            //						{
            //							album = [album substringFromIndex:2];
            //							[dicomElements setObject:album forKey:@"album"];
            //						}
            //					}
            //				}
            //
            //				DcmTagKey albumKey = DcmTagKey(0x0040, 0x0280);
            //				if (dataset->findAndGetString(albumKey, string, OFFalse).good() && string != NULL)
            //				{
            //					album = [NSString stringWithUTF8String:string encoding: NSISOLatin1StringEncoding];
            //					if( [album length] >= 2)
            //					{
            //						if( [[album substringToIndex:2] isEqualToString: @"LV"])
            //						{
            //							album = [album substringFromIndex:2];
            //							[dicomElements setObject:album forKey:@"album"];
            //						}
            //					}
            //				}
            //
            //				 albumKey = DcmTagKey(0x0040, 0x1400);
            //				 if (dataset->findAndGetString(albumKey, string, OFFalse).good() && string != NULL)
            //				 {
            //					album = [NSString stringWithUTF8String:string encoding: NSISOLatin1StringEncoding];
            //					if( [album length] >= 2)
            //					{
            //						if( [[album substringToIndex:2] isEqualToString: @"LV"])
            //						{
            //							album = [album substringFromIndex:2];
            //							[dicomElements setObject:album forKey:@"album"];
            //						}
            //					}
            //				}
            //			}  //ckeck LAVIN
            
        } //check autofill and album
        
        //SOPClass
        NSString *sopClassUID = nil;
        if (dataset->findAndGetString(DCM_SOPClassUID, string, OFFalse).good() && string != NULL)
        {
            [dicomElements setObject:[NSString stringWithCString:string encoding: NSASCIIStringEncoding] forKey:@"SOPClassUID"];
            sopClassUID = [NSString stringWithCString: string encoding: NSASCIIStringEncoding] ;
        }
        
        //Image Type
        if (dataset->findAndGetString(DCM_ImageType, string, OFFalse).good() && string != NULL)
        {
            imageTypeArray = [NSMutableArray arrayWithArray: [[NSString stringWithCString:string encoding: NSISOLatin1StringEncoding] componentsSeparatedByString:@"\\"]];
            
            if( [imageTypeArray count] > 2)
            {
                imageType = [[imageTypeArray objectAtIndex: 2] retain];
                [dicomElements setObject:imageType forKey:@"imageType"];
            }
        }
        else
            imageType = nil;
        
        if( imageType) [dicomElements setObject:imageType forKey:@"imageType"];
        
        //SOPInstanceUID
        if (dataset->findAndGetString(DCM_SOPInstanceUID, string, OFFalse).good() && string != NULL)
        {
            SOPUID = [[NSString stringWithCString:string encoding: NSISOLatin1StringEncoding] retain];
        }
        else
            SOPUID = nil;
        if (SOPUID) [dicomElements setObject:SOPUID forKey:@"SOPUID"];
        
        //Study Description
        if (dataset->findAndGetString(DCM_StudyDescription, string, OFFalse).good() && string != NULL)
            study = [[DicomFile stringWithBytes: (char*) string encodings:encoding] retain];
        else
        {
            DcmItem *item = NULL;
            if (dataset->findAndGetSequenceItem(DCM_ProcedureCodeSequence, item).good())
            {
                if( item->findAndGetString(DCM_CodeMeaning, string, OFFalse).good() && string != NULL)
                    study = [[DicomFile stringWithBytes: (char*) string encodings:encoding] retain];
            }
        }
        if( !study)
            study = [[NSString alloc] initWithString: @"unnamed"];
        [dicomElements setObject:study forKey: @"studyDescription"];
        
        //Modality
        if (dataset->findAndGetString(DCM_Modality, string, OFFalse).good() && string != NULL)
        {
            Modality = [[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding];
        }
        else
            Modality = [[NSString alloc] initWithString:@"OT"];
        [dicomElements setObject:Modality forKey:@"modality"];
        
        
        //Acquistion Date
        NSString *studyDate = nil;
        if (dataset->findAndGetString(DCM_AcquisitionDate, string, OFFalse).good() && string != NULL && strlen( string) > 0)
            studyDate = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        else if (dataset->findAndGetString(DCM_ContentDate, string, OFFalse).good() && string != NULL && strlen( string) > 0)
            studyDate = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        else if (dataset->findAndGetString(DCM_SeriesDate, string, OFFalse).good() && string != NULL && strlen( string) > 0)
            studyDate = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        else if (dataset->findAndGetString(DCM_StudyDate, string, OFFalse).good() && string != NULL && strlen( string) > 0)
            studyDate = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        if( [studyDate length] != 8) studyDate = [studyDate stringByReplacingOccurrencesOfString:@"." withString:@""];
        
        NSString* studyTime = nil;
        if (dataset->findAndGetString(DCM_AcquisitionTime, string, OFFalse).good() && string != NULL && strlen( string) > 0 && atof( string) > 0)
            studyTime = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        else if (dataset->findAndGetString(DCM_ContentTime, string, OFFalse).good() && string != NULL && strlen( string) > 0 && atof( string) > 0)
            studyTime = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        else if (dataset->findAndGetString(DCM_SeriesTime, string, OFFalse).good() && string != NULL && strlen( string) > 0 && atof( string) > 0)
            studyTime = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        else if (dataset->findAndGetString(DCM_StudyTime, string, OFFalse).good() && string != NULL && strlen( string) > 0 && atof( string) > 0)
            studyTime = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
        
        studyTime = [studyTime stringByReplacingOccurrencesOfString:@":" withString:@""];
        
        if( studyDate && studyTime)
        {
            NSString *completeDate = [studyDate stringByAppendingString:studyTime];
            
            if( [studyTime length] >= 6)
                date = [[NSCalendarDate alloc] initWithString:completeDate calendarFormat:@"%Y%m%d%H%M%S"];
            else
                date = [[NSCalendarDate alloc] initWithString:completeDate calendarFormat:@"%Y%m%d%H%M"];
        }
        else if( studyDate)
        {
            studyDate = [studyDate stringByAppendingString: @"120000"];
            date = [[NSCalendarDate alloc] initWithString:studyDate calendarFormat: @"%Y%m%d%H%M%S"];
        }
        else
            date = [[NSCalendarDate dateWithYear:1901 month:1 day:1 hour:0 minute:0 second:0 timeZone:nil] retain];
        
        // A date that is there and cannot be read ends the same way as no date
        // at all - the study is filed without one, because 1901 is the marker
        // the importer refuses to store. The difference is worth a line: one is
        // a study that never carried a date, the other is a file whose date this
        // could not make sense of.
        if( date == nil && (studyDate.length || studyTime.length))
            NSLog( @"---- %@: the study date could not be read (date \"%@\", time \"%@\"); the study is filed without one", [filePath lastPathComponent], studyDate? studyDate : @"", studyTime? studyTime : @"");
        
        if( date)
            [dicomElements setObject:date forKey:@"studyDate"];
        
        //Series Description
        if (dataset->findAndGetString(DCM_SeriesDescription, string, OFFalse).good() && string != NULL)
            serie = [[DicomFile stringWithBytes: (char*) string encodings:encoding] retain];
        else if (dataset->findAndGetString(DCM_PerformedProcedureStepDescription, string, OFFalse).good() && string != NULL)
            serie = [[DicomFile stringWithBytes: (char*) string encodings:encoding] retain];
        else if (dataset->findAndGetString(DCM_AcquisitionDeviceProcessingDescription, string, OFFalse).good() && string != NULL)
            serie = [[DicomFile stringWithBytes: (char*) string encodings:encoding] retain];
        else if( serie == nil)
            serie = [[NSString alloc] initWithString: @"unnamed"];
        
        [dicomElements setObject:serie forKey:@"seriesDescription"];
        
        //Institution Name
        if (dataset->findAndGetString(DCM_InstitutionName,  string, OFFalse).good() && string != NULL)
        {
            NSString *institution = [DicomFile stringWithBytes: (char*) string encodings:encoding];
            [dicomElements setObject:institution forKey:@"institutionName"];
        }
        
        //Referring Physician
        if (dataset->findAndGetString(DCM_ReferringPhysiciansName,  string, OFFalse).good() && string != NULL)
        {
            NSString *referringPhysiciansName = [DicomFile stringWithBytes: (char*) string encodings:encoding];
            [dicomElements setObject:referringPhysiciansName forKey:@"referringPhysiciansName"];
        }
        
        //Performing Physician
        if (dataset->findAndGetString(DCM_PerformingPhysiciansName,  string, OFFalse).good() && string != NULL)
        {
            NSString *performingPhysiciansName = [DicomFile stringWithBytes: (char*) string encodings:encoding];
            [dicomElements setObject:performingPhysiciansName forKey:@"performingPhysiciansName"];
        }
        
        //Accession Number
        if (dataset->findAndGetString(DCM_AccessionNumber,  string, OFFalse).good() && string != NULL)
        {
            NSString *accessionNumber = [DicomFile stringWithBytes: (char*) string encodings:encoding replaceBadCharacters: NO];
            [dicomElements setObject:accessionNumber forKey:@"accessionNumber"];
        }
        
        //Patients Name
        if (dataset->findAndGetString(DCM_PatientsName, string, OFFalse).good() && string != NULL)
        {
            name = [[DicomFile stringWithBytes: (char*) string encodings:encoding replaceBadCharacters:NO] retain];
            if(name == nil) name = [[NSString alloc] initWithCString: string encoding: encoding[ 0]];
        }
        else
            name = [[NSString alloc] initWithString: @"No name"];
        
        [dicomElements setObject:name forKey:@"patientName"];
        
        //Patient ID
        if (dataset->findAndGetString(DCM_PatientID, string, OFFalse).good() && string != NULL)
        {
            patientID  = [[DicomFile stringWithBytes: (char*) string encodings:encoding replaceBadCharacters: NO] retain];
            [dicomElements setObject:patientID forKey: @"patientID"];
        }
        
        //Patients Age
        if (dataset->findAndGetString(DCM_PatientsAge, string, OFFalse).good() && string != NULL)
        {
            NSString *patientAge  = [[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding];
            [dicomElements setObject:patientAge forKey:@"patientAge"];
            [patientAge  release];
        }
        
        //Patients BD
        if (dataset->findAndGetString(DCM_PatientsBirthDate, string, OFFalse).good() && string != NULL)
        {
            NSString		*patientDOB =  [[[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding] autorelease];
            NSCalendarDate	*DOB = [NSCalendarDate dateWithString: patientDOB calendarFormat:@"%Y%m%d"];
            if( DOB) [dicomElements setObject:DOB forKey:@"patientBirthDate"];
        }
        
        //Patients Sex
        if (dataset->findAndGetString(DCM_PatientsSex, string, OFFalse).good() && string != NULL)
        {
            NSString *patientSex  = [[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding];
            [dicomElements setObject:patientSex forKey:@"patientSex"];
            [patientSex  release];
        }
        
        
        //Cardiac Time
        if (dataset->findAndGetString(DCM_ScanOptions, string, OFFalse).good() && string != NULL){
            if( strlen( string) >= 4)
            {
                if( string[ 0] == 'T' && string[ 1] == 'P')
                {
                    if( string[ 2] >= '0' && string[ 2] <= '9')
                    {
                        if( string[ 3] >= '0' && string[ 3] <= '9')
                        {
                            cardiacTime = (string[ 2] - '0')*10;
                            cardiacTime += string[ 3] - '0';
                        }
                        else
                        {
                            cardiacTime = string[ 2] - '0';
                        }
                    }
                }
            }
            [dicomElements setObject:[NSNumber numberWithLong: cardiacTime] forKey:@"cardiacTime"];
        }
        
        //Protocol Name
        if (dataset->findAndGetString(DCM_ProtocolName, string, OFFalse).good() && string != NULL)
        {
            NSString *protocol = [DicomFile stringWithBytes: (char*) string encodings: encoding];
            if( protocol == nil) protocol = [[[NSString alloc] initWithCString: string encoding: encoding[ 0]]  autorelease];
            [dicomElements setObject:protocol  forKey:@"protocolName"];
        }
        
        //		//manufacturer
        //		if (dataset->findAndGetString(DCM_Manufacturer, string, OFFalse).good() && string != NULL)
        //		{
        //			NSString *manufacturer = [DicomFile stringWithBytes: (char*) string encodings: encoding];
        //			if( manufacturer == nil) manufacturer = [[[NSString alloc] initWithCString: string encoding: encoding[ 0]] autorelease];
        //
        //			if( [manufacturer hasPrefix: @"MAC:"])
        //				[dicomElements setObject: manufacturer forKey: @"manufacturer"];
        //		}
        
        //Echo Time
        if (dataset->findAndGetString(DCM_EchoTime, string, OFFalse).good() && string != NULL)
        {
            echoTime = [[[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding] autorelease];
        }
        
        //Image Number
        if (dataset->findAndGetString(DCM_InstanceNumber, string, OFFalse).good() && string != NULL)
        {
            int val = [[NSString stringWithCString:string encoding: NSASCIIStringEncoding] intValue];
            imageID = [[NSString alloc] initWithFormat:@"%5d", val];
        }
        else imageID = nil;
        
        // Compute slice location
        
        Float64		orientation[9];
        Float64		origin[ 3];
        Float64		location = 0;
        int count = 0;
        
        origin[0] = origin[1] = origin[2] = 0;
        
        while (count < 3 && dataset->findAndGetFloat64(DCM_ImagePositionPatient, origin[count], count, OFFalse).good())
            count++;
        
        orientation[ 0] = 1;	orientation[ 1] = 0;		orientation[ 2] = 0;
        orientation[ 3] = 0;	orientation[ 4] = 1;		orientation[ 5] = 0;
        
        count = 0;
        while (count < 6 && dataset->findAndGetFloat64(DCM_ImageOrientationPatient, orientation[count], count, OFFalse).good())
            count++;
        
        // Compute normal vector
        orientation[6] = orientation[1]*orientation[5] - orientation[2]*orientation[4];
        orientation[7] = orientation[2]*orientation[3] - orientation[0]*orientation[5];
        orientation[8] = orientation[0]*orientation[4] - orientation[1]*orientation[3];
        
        if( fabs( orientation[6]) > fabs(orientation[7]) && fabs( orientation[6]) > fabs(orientation[8])) location = origin[ 0];
        if( fabs( orientation[7]) > fabs(orientation[6]) && fabs( orientation[7]) > fabs(orientation[8])) location = origin[ 1];
        if( fabs( orientation[8]) > fabs(orientation[6]) && fabs( orientation[8]) > fabs(orientation[7])) location = origin[ 2];
        
        [dicomElements setObject:[NSNumber numberWithDouble: (double)location] forKey:@"sliceLocation"];
        
        if( imageID == nil || [imageID intValue] >= 99999)
        {
            int val = 10000 + location*10.;
            [imageID release];
            imageID = [[NSString alloc] initWithFormat:@"%5d", val];
        }
        [dicomElements setObject:[NSNumber numberWithLong: [imageID intValue]] forKey:@"imageID"];
        
        //Series Number
        if (dataset->findAndGetString(DCM_SeriesNumber, string, OFFalse).good() && string != NULL)
        {
            seriesNo = [[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding];
        }
        else
            seriesNo = [[NSString alloc] initWithString: @"0"];
        if( seriesNo) [dicomElements setObject:[NSNumber numberWithInt:[seriesNo intValue]]  forKey:@"seriesNumber"];
        
        //Series Instance UID
        if (dataset->findAndGetString(DCM_SeriesInstanceUID, string, OFFalse).good() && string != NULL)
        {
            self.serieID = [NSString stringWithCString:string encoding: NSASCIIStringEncoding];
            [dicomElements setObject:self.serieID forKey:@"seriesDICOMUID"];
        }
        else
            self.serieID = name;
        
        //Series ID
        
        if( cardiacTime != -1 && [self separateCardiac4D] == YES && [Modality isEqualToString: @"SC"] == NO)  // For new Cardiac-CT Siemens series
            self.serieID = [NSString stringWithFormat:@"%@ %2.2d", self.serieID , (int) cardiacTime];
        
        if( seriesNo)
            self.serieID = [NSString stringWithFormat:@"%8.8d %@", [seriesNo intValue] , self.serieID];
        
        if( imageType != 0 && [self useSeriesDescription])
            self.serieID = [NSString stringWithFormat:@"%@ %@", self.serieID , imageType];
        
        if( serie != nil && [self useSeriesDescription])
            self.serieID = [NSString stringWithFormat:@"%@ %@", self.serieID , serie];
        
        if( sopClassUID != nil && [[DCMAbstractSyntaxUID hiddenImageSyntaxes] containsObject: sopClassUID])
            self.serieID = [NSString stringWithFormat:@"%@ %@", self.serieID , sopClassUID];
        
        //Segregate by TE  values
        if( echoTime != nil && [self splitMultiEchoMR])
            self.serieID = [NSString stringWithFormat:@"%@ TE-%@", self.serieID , echoTime];
        
        //Study Instance UID
        if (dataset->findAndGetString(DCM_StudyInstanceUID, string, OFFalse).good() && string != NULL)
            studyID = [[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding];
        else
        {
            // The patient's name used to stand in for the identifier, and it is
            // what the C-FIND SCP then answers with as a UI. Derived from the
            // same name, so files that grouped together still do, but a value
            // that UI can hold.
            studyID = [[NSString alloc] initWithString: [HorosDerivedUID studyUIDForKey: name]];
            NSLog( @"---- %@ has no StudyInstanceUID; indexed under %@", [filePath lastPathComponent], studyID);
        }
        
        [dicomElements setObject:studyID forKey:@"studyID"];
        
        //StudyID
        if (dataset->findAndGetString(DCM_StudyID, string, OFFalse).good() && string != NULL)
            studyIDs = [[NSString alloc] initWithCString:string encoding: NSASCIIStringEncoding];
        else
            studyIDs = [[NSString alloc] initWithString:@"0"];
        
        if( studyIDs)
            [dicomElements setObject:studyIDs forKey:@"studyNumber"];
        
        if( [self commentsFromDICOMFiles])
        {
            if (dataset->findAndGetString( DCM_StudyComments, string, OFFalse).good() && string != NULL)
                [dicomElements setObject: [NSString stringWithCString:string encoding: NSASCIIStringEncoding] forKey:@"studyComments"];
            
            if (dataset->findAndGetString( DCM_ImageComments, string, OFFalse).good() && string != NULL)
                [dicomElements setObject: [NSString stringWithCString:string encoding: NSASCIIStringEncoding] forKey:@"seriesComments"];
            
            if (dataset->findAndGetString( DCM_InterpretationStatusID, string, OFFalse).good() && string != NULL)
                [dicomElements setObject: [NSNumber numberWithInt: [[NSString stringWithCString:string encoding: NSASCIIStringEncoding] intValue]] forKey:@"stateText"];
        }
        
        //Rows
        unsigned short rows = 0;
        if (dataset->findAndGetUint16(DCM_Rows, rows, OFFalse).good())
            height = rows;
        
        //Columns
        unsigned short columns = 0;
        if (dataset->findAndGetUint16(DCM_Columns, columns, OFFalse).good())
            width = columns;
        
        //Number of Frames
        if (dataset->findAndGetString(DCM_NumberOfFrames, string, OFFalse).good() && string != NULL)
            NoOfFrames = atoi(string);
        
        // An image object that declares a size and carries nothing to fill it is
        // indexed like any other and counted in the study's image total, and
        // nothing anywhere says it has no picture in it. That is a study whose
        // count does not match what can be looked at, with no way to tell which
        // instances are the empty ones. It stays indexed - refusing it would lose
        // everything else the file carries - but it is named.
        // A picture of no width or no height is not a picture, and an object that
        // declares one is dropped somewhere between here and the database without
        // anything saying so - the file is copied into the database folder and no
        // row is ever made for it.
        // An object that states Rows and Columns is claiming to be a picture,
        // whatever its SOP class is called. Asking the list of known image classes
        // instead left a hardcopy object - modality HC, in a mammography study -
        // indexed with no pixels and nothing said about it.
        BOOL claimsAPicture = (rows > 0 || columns > 0);
        
        if( claimsAPicture && (rows == 0 || columns == 0))
        {
            NSString *problem = [NSString stringWithFormat: @"it declares a picture of %d x %d",
                                 (int) columns, (int) rows];
            [dicomElements setObject: problem forKey: @"pixelDataProblem"];
            NSLog( @"---- %@: %@", [filePath lastPathComponent], problem);
        }
        else if( claimsAPicture)
        {
            unsigned short allocated = 0, samples = 1;
            dataset->findAndGetUint16( DCM_BitsAllocated, allocated, OFFalse);
            dataset->findAndGetUint16( DCM_SamplesPerPixel, samples, OFFalse);
            
            DcmElement *pixelData = NULL;
            OFCondition found = dataset->findAndGetElement( DCM_PixelData, pixelData, OFFalse);
            unsigned long carried = (found.good() && pixelData)? pixelData->getLength() : 0;
            
            // Encapsulated pixel data lives in fragments and the element itself
            // reports no length at all, so neither the emptiness test nor the
            // size test says anything about it: only the absence of the element
            // does.
            DcmXfer transfer( dataset->getOriginalXfer());
            BOOL storedAsRead = transfer.isNotEncapsulated();
            
            NSString *problem = nil;
            if( found.bad() || pixelData == NULL)
            {
                // Float Pixel Data and Double Float Pixel Data are pixel data, and
                // an object that carries them carries a picture. Nothing here reads
                // either one, which is worth saying - but saying the object has no
                // pixels is a different claim, and a false one.
                DcmElement *elsewhere = NULL;
                DcmItem *icon = NULL;
                if( dataset->findAndGetElement( DCM_FloatPixelData, elsewhere, OFFalse).good() && elsewhere)
                    problem = @"its pixels are in Float Pixel Data (7fe0,0008), which this application does not read";
                else if( dataset->findAndGetElement( DCM_DoubleFloatPixelData, elsewhere, OFFalse).good() && elsewhere)
                    problem = @"its pixels are in Double Float Pixel Data (7fe0,0009), which this application does not read";
                else if( dataset->findAndGetSequenceItem( DCM_IconImageSequence, icon, 0).good() && icon)
                {
                    // An icon is a preview of the image, not the image: PS 3.3
                    // C.7.6.1.1.6. Saying the object carries no picture when it
                    // carries a small one is the same mistake as showing the small
                    // one as though it were the study.
                    unsigned short iconRows = 0, iconColumns = 0;
                    icon->findAndGetUint16( DCM_Rows, iconRows, 0, OFFalse);
                    icon->findAndGetUint16( DCM_Columns, iconColumns, 0, OFFalse);
                    problem = [NSString stringWithFormat: @"its only picture is a %d x %d preview "
                               @"icon in Icon Image Sequence (0088,0200), not the %d x %d image it "
                               @"declares", (int) iconColumns, (int) iconRows, (int) columns, (int) rows];
                }
                else
                    problem = @"it carries no pixel data at all";
            }
            else if( storedAsRead)
            {
                if( carried == 0)
                    problem = @"its pixel data is empty";
                else if( allocated > 0 && samples > 0)
                {
                    unsigned long long expected = (unsigned long long) rows * columns * samples * ((allocated + 7) / 8) * MAX( 1, NoOfFrames);
                    if( carried < expected)
                        problem = [NSString stringWithFormat: @"its pixel data is %lu bytes where %llu are needed for %dx%d", carried, expected, (int) columns, (int) rows];
                }
            }
            
            if( problem)
            {
                [dicomElements setObject: problem forKey: @"pixelDataProblem"];
                NSLog( @"---- %@: %@; it is indexed and counted as an image anyway", [filePath lastPathComponent], problem);
            }
        }
        else if( sopClassUID.length &&
                 [DCMAbstractSyntaxUID isImageStorage: sopClassUID] == NO &&
                 [DCMAbstractSyntaxUID isStructuredReport: sopClassUID] == NO &&
                 [DCMAbstractSyntaxUID isPDF: sopClassUID] == NO &&
                 [DCMAbstractSyntaxUID isPresentationState: sopClassUID] == NO &&
                 [DCMAbstractSyntaxUID isRadiotherapy: sopClassUID] == NO &&
                 [DCMAbstractSyntaxUID isWaveform: sopClassUID] == NO &&
                 [DCMAbstractSyntaxUID isDirectory: sopClassUID] == NO)
        {
            // An instance that is not a picture and is not one of the kinds this
            // application shows is still received, still kept and still listed - as
            // a series with nothing to look at, and with nothing anywhere saying
            // why. Spectroscopy and private non-image classes arrive this way. The
            // SOP class it came as is what lets it be found again.
            NSString *problem = [NSString stringWithFormat:
                                 @"it is a %@ object, which this application keeps but cannot display",
                                 sopClassUID];
            [dicomElements setObject: problem forKey: @"pixelDataProblem"];
            NSLog( @"---- %@: %@", [filePath lastPathComponent], problem);
        }
        
        // Is it a multi frame DICOM files? We need to parse these sequences for the correct sliceLocation value !
        int i = 0;
        DcmItem *ditem = NULL;
        NSMutableArray *sliceLocationArray = [NSMutableArray array];
        NSMutableArray *imageCardiacTriggerArray = [NSMutableArray array];
        // Where each frame sits in its stack, if the acquisition says so. Without
        // it a frame's instance number is only its place in the file, so "sort by
        // instance" reproduces the encoding order and nothing else.
        NSMutableArray *stackPositionArray = [NSMutableArray array];
        
        double originMultiFrame[ 3] = {0, 0, 0}, orientationMultiFrame[ 9] = {1, 0, 0, 0, 1, 0};
        double sharedOrientation[ 6] = {1, 0, 0, 0, 1, 0};
        BOOL hasSharedOrientation = NO;
        
        // SHARED
        //
        // An Enhanced CT or MR states the orientation once, here, because every
        // frame shares it, and gives each frame only its position. Reading the
        // orientation from the per-frame item alone - which is what this did -
        // left every frame of such a study without a slice location, and the
        // stack fell back to the order the frames happen to be encoded in.
        //
        // ImageOrientationVolume also lives in PlaneOrientationVolumeSequence
        // (0020,930f), not in the position sequence beside it.
        if (dataset->findAndGetSequenceItem(DCM_SharedFunctionalGroupsSequence, ditem, 0).good())
        {
            DcmItem *eitem = NULL;
            
            if (ditem->findAndGetSequenceItem(DCM_PlaneOrientationSequence, eitem, 0).good())
            {
                int count = 0;
                while (count < 6 && eitem->findAndGetFloat64(DCM_ImageOrientationPatient, sharedOrientation[count], count, OFFalse).good())
                    count++;
                
                hasSharedOrientation = (count == 6);
            }
            
            if( hasSharedOrientation == NO && ditem->findAndGetSequenceItem(DCM_PlaneOrientationVolumeSequence, eitem, 0).good())
            {
                int count = 0;
                while (count < 6 && eitem->findAndGetFloat64(DCM_ImageOrientationVolume, sharedOrientation[count], count, OFFalse).good())
                    count++;
                
                hasSharedOrientation = (count == 6);
                
                if( count != 6 && count != 0)
                    NSLog( @"******* DCM_ImageOrientationVolume : count != 6 && count != 0");
            }
            
            if( hasSharedOrientation)
                memcpy( orientationMultiFrame, sharedOrientation, sizeof( sharedOrientation));
        }
        
        // PER FRAME
        do
        {
            if (dataset->findAndGetSequenceItem(DCM_PerFrameFunctionalGroupsSequence, ditem, i++).good())
            {
                int x = 0;
                DcmItem *eitem = NULL;
                do
                {
                    if (ditem->findAndGetSequenceItem(DCM_CardiacTriggerSequence, eitem, x).good())
                    {
                        Float64 triggerSequence = 0;
                        
                        if( eitem->findAndGetFloat64(DCM_TriggerDelayTime, triggerSequence, 0, OFFalse).good())
                            [imageCardiacTriggerArray addObject: [NSString stringWithFormat: @"%lf", triggerSequence]];
                    }
                    
                    if (x == 0 && ditem->findAndGetSequenceItem(DCM_FrameContentSequence, eitem, 0).good())
                    {
                        Uint32 inStackPosition = 0;
                        if( eitem->findAndGetUint32(DCM_InStackPositionNumber, inStackPosition, 0, OFFalse).good())
                            [stackPositionArray addObject: [NSNumber numberWithUnsignedInt: inStackPosition]];
                    }
                    
                    BOOL succeed = YES;
                    
                    if (ditem->findAndGetSequenceItem(DCM_PlanePositionVolumeSequence, eitem, x).good())
                    {
                        int count = 0;
                        while (count < 3 && eitem->findAndGetFloat64(DCM_ImagePositionVolume, originMultiFrame[count], count, OFFalse).good())
                            count++;
                        
                        if( count != 3)
                            succeed = NO;
                    }
                    else
                        succeed = NO;
                    
                    if( succeed == NO)
                    {
                        succeed = YES;
                        
                        if (ditem->findAndGetSequenceItem(DCM_PlanePositionSequence, eitem, x).good())
                        {
                            int count = 0;
                            while (count < 3 && eitem->findAndGetFloat64(DCM_ImagePositionPatient, originMultiFrame[count], count, OFFalse).good())
                                count++;
                            
                            if( count != 3)
                                succeed = NO;
                        }
                        else succeed = NO;
                        
                        if (ditem->findAndGetSequenceItem(DCM_PlaneOrientationSequence, eitem, x).good())
                        {
                            int count = 0;
                            while (count < 6 && eitem->findAndGetFloat64(DCM_ImageOrientationPatient, orientationMultiFrame[count], count, OFFalse).good())
                                count++;
                            
                            if( count != 6 && count != 0)
                                succeed = NO;
                        }
                        else if( hasSharedOrientation)
                        {
                            // The frame carries only its position, which is what the
                            // shared orientation is there for.
                            memcpy( orientationMultiFrame, sharedOrientation, sizeof( sharedOrientation));
                        }
                        else succeed = NO;
                    }
                    
                    if( succeed)
                    {
                        // Compute normal vector
                        orientationMultiFrame[ 6] = orientationMultiFrame[ 1]*orientationMultiFrame[ 5] - orientationMultiFrame[ 2]*orientationMultiFrame[ 4];
                        orientationMultiFrame[ 7] = orientationMultiFrame[ 2]*orientationMultiFrame[ 3] - orientationMultiFrame[ 0]*orientationMultiFrame[ 5];
                        orientationMultiFrame[ 8] = orientationMultiFrame[ 0]*orientationMultiFrame[ 4] - orientationMultiFrame[ 1]*orientationMultiFrame[ 3];
                        
                        float location = 0;
                        
                        if( fabs( orientationMultiFrame[ 6]) > fabs(orientationMultiFrame[ 7]) && fabs( orientationMultiFrame[ 6]) > fabs(orientationMultiFrame[ 8]))
                            location = originMultiFrame[ 0];
                        
                        if( fabs( orientationMultiFrame[ 7]) > fabs(orientationMultiFrame[ 6]) && fabs( orientationMultiFrame[ 7]) > fabs(orientationMultiFrame[ 8]))
                            location = originMultiFrame[ 1];
                        
                        if( fabs( orientationMultiFrame[ 8]) > fabs(orientationMultiFrame[ 6]) && fabs( orientationMultiFrame[ 8]) > fabs(orientationMultiFrame[ 7]))
                            location = originMultiFrame[ 2];
                        
                        [sliceLocationArray addObject: [NSNumber numberWithFloat: location]];
                    }
                    
                    x++;
                }
                while (eitem != NULL);
            }
        }
        while (ditem != NULL);
        
        if( sliceLocationArray.count)
        {
            if( NoOfFrames == sliceLocationArray.count)
                [dicomElements setObject: sliceLocationArray forKey:@"sliceLocationArray"];
            else
                NSLog( @"*** NoOfFrames != sliceLocationArray.count for MR/CT/US multiframe sliceLocation computation (%d, %d)", (int) NoOfFrames, (int) sliceLocationArray.count);
        }
        // Only if every frame said where it sits, and no two said the same thing:
        // an object with several stacks numbers each of them from one, and a
        // repeated number would sort no better than the frame index does.
        if( stackPositionArray.count == NoOfFrames && NoOfFrames > 1 &&
            [NSSet setWithArray: stackPositionArray].count == stackPositionArray.count)
            [dicomElements setObject: stackPositionArray forKey: @"instanceNumberArray"];
        
        if( imageCardiacTriggerArray.count)
        {
            if( NoOfFrames == imageCardiacTriggerArray.count)
                [dicomElements setObject: imageCardiacTriggerArray forKey:@"imageCommentPerFrame"];
            else
                NSLog( @"*** NoOfFrames != imageCardiacTriggerArray.count for MR/CT multiframe image type frame computation (%d, %d)", (int) NoOfFrames, (int) imageCardiacTriggerArray.count);
            
        }
        
        // Is it PDF DICOM file?
        if( [sopClassUID isEqualToString:[DCMAbstractSyntaxUID pdfStorageClassUID]])
        {
            const Uint8 *buffer = nil;
            unsigned long length;
            if (dataset->findAndGetUint8Array(DCM_EncapsulatedDocument, buffer, &length, OFFalse).good() && length > 0)
            {
                NSData *pdfData = [NSData dataWithBytes:buffer length:(unsigned)length];;
                NSPDFImageRep *rep = [NSPDFImageRep imageRepWithData:pdfData];
                
                NoOfFrames = [rep pageCount];
                
                NSImage *pdfImage = [[[NSImage alloc] init] autorelease];
                [pdfImage addRepresentation: rep];
                
                NSBitmapImageRep *bitRep = [NSBitmapImageRep imageRepWithData: [pdfImage TIFFRepresentation]];
                
                if( bitRep.pixelsWide > pdfImage.size.width)
                {
                    height = bitRep.pixelsHigh;
                    width = bitRep.pixelsWide;
                }
                else
                {
                    height = pdfImage.size.height;
                    width = pdfImage.size.width;
                }
            }
        }
        
#ifdef OSIRIX_VIEWER
#ifndef OSIRIX_LIGHT
        if( [sopClassUID hasPrefix: @"1.2.840.10008.5.1.4.1.1.88"])
        {
            if( [DicomStudy displaySeriesWithSOPClassUID: sopClassUID andSeriesDescription: [dicomElements objectForKey: @"seriesDescription"]])
            {
                NSPDFImageRep *rep = [self PDFImageRep];
                
                NoOfFrames = [rep pageCount];
                
                NSImage *pdfImage = [[[NSImage alloc] init] autorelease];
                [pdfImage addRepresentation: rep];
                
                NSBitmapImageRep *bitRep = [NSBitmapImageRep imageRepWithData: [pdfImage TIFFRepresentation]];
                
                if( bitRep.pixelsWide > pdfImage.size.width)
                {
                    height = bitRep.pixelsHigh;
                    width = bitRep.pixelsWide;
                }
                else
                {
                    height = pdfImage.size.height;
                    width = pdfImage.size.width;
                }
            }
            
            NSString *referencedSOPInstanceUID = [SRAnnotation getImageRefSOPInstanceUID: filePath];
            
            if( referencedSOPInstanceUID)
                [dicomElements setObject: referencedSOPInstanceUID forKey: @"referencedSOPInstanceUID"];
            
            @try
            {
                if( [[dicomElements objectForKey: @"seriesDescription"] hasPrefix: @"OsiriX ROI SR"])
                {
                    NSString *referencedSOPInstanceUID = [SRAnnotation getImageRefSOPInstanceUID: filePath];
                    if( referencedSOPInstanceUID)
                        [dicomElements setObject: referencedSOPInstanceUID forKey: @"referencedSOPInstanceUID"];
                    
                    int numberOfROIs = [[NSUnarchiver unarchiveObjectWithData: [SRAnnotation roiFromDICOM: filePath]] count];
                    [dicomElements setObject: [NSNumber numberWithInt: numberOfROIs] forKey: @"numberOfROIs"];
                }
            }
            @catch (NSException * e)
            {
                N2LogExceptionWithStackTrace(e);
            }
        }
#endif
#endif
        
        NoOfSeries = 1;
        
        if( patientID == nil) patientID = [[NSString alloc] initWithString:@""];
        
        if( NoOfFrames > 1) // SERIES ID MUST BE UNIQUE!!!!!
            self.serieID = [NSString stringWithFormat:@"%@-%@-%@", self.serieID, imageID, [dicomElements objectForKey:@"SOPUID"]];
        
        if( NoOfFrames <= 1 && [self noLocalizer] && ([self containsString: @"LOCALIZER" inArray: imageTypeArray] || [self containsString: @"REF" inArray: imageTypeArray] || [self containsLocalizerInString: serie]) && [DCMAbstractSyntaxUID isImageStorage: sopClassUID])
        {
            self.serieID = @"LOCALIZER";
            
            [serie release];
            serie = [[NSString alloc] initWithString: @"Localizers"];
            [dicomElements setObject:serie forKey:@"seriesDescription"];
            
            // seriesDICOMUID keeps the SeriesInstanceUID read from the file. It
            // used to be overwritten with "LOCALIZER" and the study identifier,
            // and that value is what the C-FIND SCP answers with: 74 characters
            // of letters and digits, where UI allows 64 and only digits and
            // dots. The grouping that puts the localizers of a study in one
            // series is serieID, above, which the importer matches on; the DICOM
            // identifier is stored beside it and is not what merges anything.
        }		
        
        [dicomElements setObject:[self patientUID] forKey:@"patientUID"];
        
        if( self.serieID == nil) self.serieID = name;
        
        // Same for the series. seriesDICOMUID is only set above when the file
        // carries one, so a file without it produced a series row whose DICOM
        // identifier was empty - and an empty UI in every C-FIND answer about
        // it. Derived from what the importer groups this series on, so the
        // grouping is unchanged and re-importing the file lands in the same
        // series.
        if( [[dicomElements objectForKey: @"seriesDICOMUID"] length] == 0)
        {
            NSString *derived = [HorosDerivedUID seriesUIDForKey: [NSString stringWithFormat: @"%@|%@", studyID, self.serieID]];
            [dicomElements setObject: derived forKey: @"seriesDICOMUID"];
            NSLog( @"---- %@ has no SeriesInstanceUID; indexed under %@", [filePath lastPathComponent], derived);
        }
        
        if( [Modality isEqualToString:@"US"] && [self oneFileOnSeriesForUS])
        {
            [dicomElements setObject: [self.serieID stringByAppendingString: [filePath lastPathComponent]] forKey:@"seriesID"];
        }
        else if ( [self combineProjectionSeries] && ([Modality isEqualToString:@"MG"] || [Modality isEqualToString:@"CR"] || [Modality isEqualToString:@"DR"] || [Modality isEqualToString:@"DX"] || [Modality  isEqualToString:@"RF"]))
        {
            if( [self combineProjectionSeriesMode] == 0)		// *******Combine all CR and DR Modality series in a study into one series
            {
                if( sopClassUID != nil && [[DCMAbstractSyntaxUID hiddenImageSyntaxes] containsObject: sopClassUID])
                    [dicomElements setObject:self.serieID forKey:@"seriesID"];
                else
                    [dicomElements setObject:studyID forKey:@"seriesID"];
                
                [dicomElements setObject:[NSNumber numberWithLong: [self.serieID intValue] * 1000 + [imageID intValue]] forKey:@"imageID"];
            }
            else if( [self combineProjectionSeriesMode] == 1)	// *******Split all CR and DR Modality series in a study into one series
            {
                [dicomElements setObject: [self.serieID stringByAppendingString: imageID] forKey:@"seriesID"];
            }
            else NSLog( @"ARG! ERROR !? Unknown combineProjectionSeriesMode");
        }
        else
            [dicomElements setObject:self.serieID forKey:@"seriesID"];
        
        if( studyID == nil)
        {
            studyID = [[NSString alloc] initWithString:name];
            [dicomElements setObject:studyID forKey:@"studyID"];
        }
        
        if( imageID == nil)
        {
            imageID = [[NSString alloc] initWithString:name];
            [dicomElements setObject:imageID forKey:@"SOPUID"];
        }
        
        if( date == nil)
        {
            date = [[NSCalendarDate dateWithYear:1901 month:1 day:1 hour:0 minute:0 second:0 timeZone:nil] retain];
            [dicomElements setObject:date forKey:@"studyDate"];
        }
        
        [dicomElements setObject:[NSNumber numberWithBool:YES] forKey:@"hasDICOM"];
        
        if( name != nil && studyID != nil && self.serieID != nil && imageID != nil && width != 0 && height != 0)
        {
            return 0;   // success
        }
    }
    
    return-1;
}
@end
