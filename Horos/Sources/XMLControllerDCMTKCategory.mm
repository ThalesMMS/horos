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

#import "XMLControllerDCMTKCategory.h"
#import "BrowserController.h"
#undef verify

#include "HorosDCMTKCompatibility.h"
#include <dcmtk/config/osconfig.h>
#include "mdfconen.h"
#import "N2Debug.h"

#include <dcmtk/dcmdata/dcvrsl.h>
#include <dcmtk/ofstd/ofcast.h>
#include <dcmtk/ofstd/ofstd.h>
#include <dcmtk/dcmdata/dctk.h>
#include <dcmtk/dcmdata/dcuid.h>

#include <cstdio>
#include <dcmtk/ofstd/ofstdinc.h>


#import "DicomFile.h"
#import "DICOMToNSString.h"
#import "DicomFileDCMTKCategory.h"
#import "DICOMDataDictionary.h"
#import "DCMAttributeTag.h"
#include <sstream>
#include <string>
#include <vector>
#include <GDCM/gdcmReader.h>
#include <GDCM/gdcmDefs.h>
#include <GDCM/gdcmAnonymizer.h>
#include <GDCM/gdcmWriter.h>
#include <GDCM/gdcmSequenceOfItems.h>
#include <GDCM/gdcmItem.h>

extern NSRecursiveLock *PapyrusLock;

// One sequence to descend on the way to an element: which sequence, and which
// of its items. Kept as numbers rather than gdcm types so the parser below has
// no dependency beyond Foundation.
typedef struct
{
    unsigned short group;
    unsigned short element;
    unsigned int item;
} HorosTagPathStep;

// One requested change to one element. Removing an element and emptying it are
// different requests and were not distinguished before: everything became a
// replacement, so a request to delete a tag left it present and empty.
typedef struct
{
    unsigned short group;
    unsigned short element;
    bool removes;
    std::string value;
    // Empty for a top-level element. Otherwise the sequences to descend,
    // outermost first, before group/element names an element inside the last
    // item.
    std::vector<HorosTagPathStep> path;
} HorosTagEdit;

// Reads the loosely typed argument several callers build: an entry of one
// element removes that tag, an entry of two replaces it with the second, and an
// empty string is a legitimate replacement value. NSNull in the second position
// is a removal too, because that is how the metadata editor already marks a row
// as "to be deleted". Entries that are not shaped like that are counted and
// skipped rather than raising, because the argument arrives from callers that
// assemble it by hand.
static std::vector<HorosTagEdit> HorosTagEditsFromEntries( NSArray *entries, NSStringEncoding encoding, NSUInteger *rejected)
{
    std::vector<HorosTagEdit> edits;
    
    for( id entry in entries)
    {
        if( [entry isKindOfClass: [NSArray class]] == NO || [(NSArray*) entry count] == 0)
        {
            if( rejected) (*rejected)++;
            continue;
        }
        
        NSArray *fields = (NSArray*) entry;
        id first = [fields objectAtIndex: 0];
        
        HorosTagEdit edit;
        
        // A tag names an element at the top level. A path names one inside a
        // sequence, which the metadata editor addresses as
        // (0054,0016)[0].(0018,1074): reading only its first tag sent the edit
        // to the sequence element instead of to the value.
        if( [first respondsToSelector: @selector(steps)] && [first respondsToSelector: @selector(group)])
        {
            id path = first;
            edit.group = (unsigned short) [[path valueForKey: @"group"] unsignedShortValue];
            edit.element = (unsigned short) [[path valueForKey: @"element"] unsignedShortValue];
            
            bool readable = true;
            for( id step in [path valueForKey: @"steps"])
            {
                NSInteger item = [[step valueForKey: @"item"] integerValue];
                if( item < 0)
                {
                    readable = false;
                    break;
                }
                
                HorosTagPathStep descent;
                descent.group = (unsigned short) [[step valueForKey: @"group"] unsignedShortValue];
                descent.element = (unsigned short) [[step valueForKey: @"element"] unsignedShortValue];
                descent.item = (unsigned int) item;
                edit.path.push_back( descent);
            }
            
            if( !readable)
            {
                if( rejected) (*rejected)++;
                continue;
            }
        }
        else if( [first isKindOfClass: [DCMAttributeTag class]])
        {
            DCMAttributeTag *tag = (DCMAttributeTag*) first;
            edit.group = tag.group;
            edit.element = tag.element;
        }
        else
        {
            if( rejected) (*rejected)++;
            continue;
        }

        edit.removes = (fields.count < 2) || [[fields objectAtIndex: 1] isKindOfClass: [NSNull class]];
        
        if( edit.removes == false)
        {
            id value = [fields objectAtIndex: 1];
            
            if( [value isKindOfClass: [NSString class]] == NO)
            {
                if( rejected) (*rejected)++;
                continue;
            }
            
            const char *bytes = [(NSString*) value cStringUsingEncoding: encoding];
            
            if( bytes == NULL) // Not representable in the file's character set.
            {
                if( rejected) (*rejected)++;
                continue;
            }
            
            edit.value = std::string( bytes);
        }
        
        edits.push_back( edit);
    }
    
    return edits;
}

// gdcm::Anonymizer::Replace refuses every non-empty value for a private
// element: "Only one operation is allowed: making a private tag empty". The
// metadata editor lists private elements and lets them be typed into, so an
// edit to one was reported as a file that could not be written. A private
// element the file already carries is written straight into the dataset
// instead, under the VR and the private creator block the file already gives
// it, so nothing is invented and no block is reshuffled.
//
// Returns false with a reason for the elements this cannot do: one that is not
// in the file, a sequence, and the binary value representations, whose length
// and byte order the editor's text has no way to express.
static bool HorosReplacePrivateValue( gdcm::File &file, const gdcm::Tag &tag, const std::string &value, std::string *reason)
{
    gdcm::DataSet &dataset = file.GetDataSet();
    
    if( dataset.FindDataElement( tag) == false)
    {
        if( reason) *reason = "the file does not carry this private element";
        return false;
    }
    
    const gdcm::DataElement &existing = dataset.GetDataElement( tag);
    gdcm::VR vr = existing.GetVR();
    
    if( vr == gdcm::VR::SQ)
    {
        if( reason) *reason = "a sequence cannot be given a text value";
        return false;
    }
    
    // UN is what an implicit VR file leaves behind for an element no private
    // dictionary describes. DICOM reads it as a byte string, which is what the
    // editor shows and what it hands back, so it is written as one.
    if( vr != gdcm::VR::UN && (vr & gdcm::VR::VRASCII) == 0)
    {
        if( reason)
        {
            std::ostringstream message;
            message << "value representation " << vr << " is not editable as text";
            *reason = message.str();
        }
        return false;
    }
    
    // A DICOM value field has an even length. Text pads with a space, UI with
    // a null, which is the rule gdcm follows for public elements.
    std::string padded = value;
    if( padded.size() % 2)
        padded += (vr == gdcm::VR::UI) ? '\0' : ' ';
    
    gdcm::DataElement replacement( tag);
    replacement.SetVR( vr);
    replacement.SetByteValue( padded.c_str(), (uint32_t) padded.size());
    dataset.Replace( replacement);
    
    return true;
}

// Writes an element that lives inside a sequence item.
//
// gdcm::Anonymizer addresses the top level only, and the editor's address for a
// row inside a sequence - (0054,0016)[0].(0018,1074) - used to be read for its
// first tag alone, so an edit to the total dose was addressed to the
// radiopharmaceutical sequence itself. It could not be applied, and reopening
// the file showed the value it started with.
//
// Descends one step at a time and writes the sequence back on the way out, so
// the change reaches the file whether or not the item's dataset is shared with
// the element that holds it, and so a sibling item is not touched.
static bool HorosWriteInDataSet( gdcm::DataSet &dataset,
                                 const HorosTagEdit &edit,
                                 size_t depth,
                                 std::string *reason)
{
    gdcm::Tag tag( edit.group, edit.element);
    
    if( depth == edit.path.size())
    {
        if( dataset.FindDataElement( tag) == false)
        {
            if( reason) *reason = "that item does not carry this element";
            return false;
        }
        
        if( edit.removes)
        {
            dataset.Remove( tag);
            return dataset.FindDataElement( tag) == false;
        }
        
        const gdcm::DataElement &existing = dataset.GetDataElement( tag);
        gdcm::VR vr = existing.GetVR();
        
        if( vr == gdcm::VR::SQ)
        {
            if( reason) *reason = "a sequence cannot be given a text value";
            return false;
        }
        
        if( vr != gdcm::VR::UN && (vr & gdcm::VR::VRASCII) == 0)
        {
            if( reason)
            {
                std::ostringstream message;
                message << "value representation " << vr << " is not editable as text";
                *reason = message.str();
            }
            return false;
        }
        
        std::string padded = edit.value;
        if( padded.size() % 2)
            padded += (vr == gdcm::VR::UI) ? '\0' : ' ';
        
        gdcm::DataElement replacement( tag);
        replacement.SetVR( vr);
        replacement.SetByteValue( padded.c_str(), (uint32_t) padded.size());
        dataset.Replace( replacement);
        
        return true;
    }
    
    const HorosTagPathStep &step = edit.path[ depth];
    gdcm::Tag sequenceTag( step.group, step.element);
    
    if( dataset.FindDataElement( sequenceTag) == false)
    {
        if( reason)
        {
            std::ostringstream message;
            message << "the file does not carry the sequence (" << sequenceTag << ")";
            *reason = message.str();
        }
        return false;
    }
    
    gdcm::DataElement sequenceElement = dataset.GetDataElement( sequenceTag);
    gdcm::SmartPointer<gdcm::SequenceOfItems> sequence = sequenceElement.GetValueAsSQ();
    
    if( !sequence)
    {
        if( reason) *reason = "that element is not a sequence";
        return false;
    }
    
    if( step.item >= sequence->GetNumberOfItems())
    {
        if( reason)
        {
            std::ostringstream message;
            message << "the sequence has " << sequence->GetNumberOfItems()
                    << " item(s), and item " << step.item << " was asked for";
            *reason = message.str();
        }
        return false;
    }
    
    // gdcm numbers items from one.
    gdcm::Item &item = sequence->GetItem( step.item + 1);
    
    if( HorosWriteInDataSet( item.GetNestedDataSet(), edit, depth + 1, reason) == false)
        return false;
    
    sequenceElement.SetValue( *sequence);
    sequenceElement.SetVLToUndefined();
    dataset.Replace( sequenceElement);
    
    return true;
}

@implementation XMLController (XMLControllerDCMTKCategory)


+ (BOOL) modifyDicom:(NSArray*) tagAndValues dicomFiles:(NSArray*) dicomFiles
{
    return [XMLController modifyDicom: tagAndValues dicomFiles: dicomFiles reasons: NULL];
}

+ (BOOL) modifyDicom:(NSArray*) tagAndValues dicomFiles:(NSArray*) dicomFiles reasons:(NSArray**) reasons
{
    BOOL modifySuccess = YES;
    NSMutableArray *refusals = [NSMutableArray array];
    
    for (NSString* f in dicomFiles)
    {
        const char* filename = [f cStringUsingEncoding:[NSString defaultCStringEncoding]];
        
        gdcm::Reader reader;
        
        reader.SetFileName(filename);
        
        if( !reader.Read() )
        {
            std::cerr << "Can't read file for anonymization." << std::endl;
            
            modifySuccess = NO;
            
            continue;
        }
        else
        {
            gdcm::File &file = reader.GetFile();
            
            gdcm::MediaStorage ms;
            ms.SetFromFile(file);
            if( !gdcm::Defs::GetIODNameFromMediaStorage(ms) )
            {
                std::cerr << "The Media Storage Type is not supported for anonymization: " << ms << std::endl;
                
                modifySuccess = NO;
                
                continue;
            }
            else
            {
                NSStringEncoding encoding = [NSString defaultCStringEncoding];
                
                if ([dicomFiles lastObject] != nil)
                {
                    if ([[DicomFile getEncodingArrayForFile:[dicomFiles lastObject]] count] > 0)
                    {
                        encoding = [NSString encodingForDICOMCharacterSet:[[DicomFile getEncodingArrayForFile:[dicomFiles lastObject]] objectAtIndex: 0]];
                    }
                }
                
                NSUInteger rejected = 0;
                std::vector<HorosTagEdit> edits = HorosTagEditsFromEntries( tagAndValues, encoding, &rejected);
                
                if( rejected)
                {
                    NSLog( @"**** modifyDicom: %lu unreadable tag entries ignored", (unsigned long) rejected);
                    [refusals addObject: [NSString stringWithFormat:
                                          NSLocalizedString( @"%lu edits could not be read, and were not applied.", nil),
                                          (unsigned long) rejected]];
                    modifySuccess = NO;
                }
                
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                
                gdcm::Anonymizer anon;
                anon.SetFile( file );
                
                bool success = true;
                
                for( std::vector<HorosTagEdit>::const_iterator it2 = edits.begin(); it2 != edits.end(); ++it2)
                {
                    gdcm::Tag tag( it2->group, it2->element);
                    std::string reason;
                    bool applied;
                    
                    // An element inside a sequence item is addressed by the
                    // whole path, not by its tag: the same tag can appear in
                    // every item, and at the top level as well.
                    if( it2->path.empty() == false)
                        applied = HorosWriteInDataSet( file.GetDataSet(), *it2, 0, &reason);
                    // Removing and emptying are different requests: emptying keeps
                    // a Type 2 element present with no value, removing takes it out.
                    else if( it2->removes)
                    {
                        applied = anon.Remove( tag);
                        if( !applied) reason = "the element could not be removed";
                    }
                    else if( tag.IsPrivate() && tag.IsPrivateCreator() == false && it2->value.empty() == false)
                        applied = HorosReplacePrivateValue( file, tag, it2->value, &reason);
                    else
                    {
                        applied = anon.Replace( tag, it2->value.c_str());
                        if( !applied) reason = "the element could not be written";
                    }
                    
                    // One refused element used to stop nothing but still failed
                    // the whole file; the others are applied and named instead.
                    if( !applied)
                    {
                        [refusals addObject: [NSString stringWithFormat: @"(%04x,%04x): %s",
                                              it2->group, it2->element, reason.c_str()]];
                        success = false;
                    }
                }
                
                if (!success)
                {
                    modifySuccess = NO;
                }
                
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                /////////////////////////////
                
                const char* outfilename = filename;
                
                gdcm::Writer writer;
                writer.SetFileName( outfilename );
                writer.SetFile( file );
                
                if( !writer.Write() )
                {
                    std::cerr << "Could not Write : " << outfilename << std::endl;
                    if( strcmp(filename,outfilename) != 0 )
                    {
                        gdcm::System::RemoveFile( outfilename );
                    }
                    else
                    {
                        std::cerr << "gdcmanon just corrupted: " << filename << " (data lost)." << std::endl;
                        
                    }
                    
                    modifySuccess = NO;
                    
                    continue;
                }
            }
        }
    }
    
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    //////////////////////
    
    if( reasons)
    {
        // The same element is refused once per file; the caller wants the list
        // of fields, not the list of attempts.
        NSMutableArray *distinct = [NSMutableArray array];
        for( NSString *refusal in refusals)
        {
            if( [distinct containsObject: refusal] == NO)
                [distinct addObject: refusal];
        }
        *reasons = distinct;
    }
    
    return modifySuccess;
}


+ (int) modifyDicom:(NSArray*) params encoding: (NSStringEncoding) encoding
{
	int error_count = 0;
	
	@try 
	{
		int i, argc = [params count];
		char *argv[ argc];
		
		for( i = 0; i < argc; i++)
        {
            if ([params count] >= i+1)
                argv[ i] = (char*) [[params objectAtIndex: i] cStringUsingEncoding: encoding];
            else
                argv[ i] = (char*) [@"" cStringUsingEncoding: encoding];
        }
		
		MdfConsoleEngine engine( argc, argv,"dcmodify");
		
		error_count=engine.startProvidingService();
		
		if (error_count > 0)
			NSLog( @"------- XMLController modifyDicom : there were %d errors", error_count);
	}
	@catch (NSException * e) 
	{
		N2LogExceptionWithStackTrace(e);
	}
	
    return error_count;
}

-(int) getGroupAndElementForName:(NSString*) name group:(int*) gp element:(int*) el
{
    unsigned group = 0xffff, element = 0xffff;
    if( !HorosResolveDicomKeyword( name, &group, &element))
        return -1;
    *gp = (int) group;
    *el = (int) element;
    return 0;
}

- (void) prepareDictionaryArray
{
	DcmDictEntry* e = NULL;
	DcmDataDictionary& globalDataDict = dcmDataDict.wrlock();
	
	DcmDictEntryList list;
    DcmHashDictIterator iter(globalDataDict.normalBegin());
    for( int x = 0; x < globalDataDict.numberOfNormalTagEntries(); ++iter, x++)
    {
        if ((*iter)->getPrivateCreator() == NULL) // exclude private tags
        {
          e = new DcmDictEntry(*(*iter));
          list.insertAndReplace(e);
        }
    }
	
    /* output the list contents */
    DcmDictEntryListIterator listIter(list.begin());
    DcmDictEntryListIterator listLast(list.end());
    for (; listIter != listLast; ++listIter)
    {
		e = *listIter;
		
		if( e->getGroup() > 0)
		{
			NSString	*s = [NSString stringWithFormat:@"(0x%04x,0x%04x) %s", e->getGroup(), e->getElement(), e->getTagName()];
		
			[dictionaryArray addObject: s];
		}
    }
	
	dcmDataDict.wrunlock();
}
@end
