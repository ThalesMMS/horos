#pragma once

#import "DCMObject.h"
#import "DCMTransferSyntax.h"
#include <dcmtk/dcmdata/dcfilefo.h>
#include <dcmtk/dcmdata/dcdatset.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcostrmb.h>
#include <dcmtk/dcmdata/dcistrmb.h>
#include <dcmtk/dcmjpls/djrparam.h>
#include <climits>

// JPEG2000 belonged to the former patched DCMTK JPEG registration. Reuse the
// host's DCM/OpenJPEG codec without adding policy or codec patches upstream.
// The bridge operates on the current dataset in memory, preserving edits and
// leaving publication and source-file ownership with the caller.
inline OFCondition HorosChooseDICOMRepresentation(DcmFileFormat& file,
    E_TransferSyntax target, const DcmRepresentationParameter* parameters = NULL, int quality = 0)
{
    DcmDataset* dataset = file.getDataset();
    const E_TransferSyntax original = dataset->getOriginalXfer();
    const bool fromJPEG2000 = original == EXS_JPEG2000 || original == EXS_JPEG2000LosslessOnly;
    const bool toJPEG2000 = target == EXS_JPEG2000 || target == EXS_JPEG2000LosslessOnly;
    if (fromJPEG2000 || toJPEG2000)
    {
        @autoreleasepool {
            @try {
                E_TransferSyntax inputSyntax = original;
                // Let upstream decode its own compressed codecs. DCM is only
                // responsible for JPEG2000, including when the source was BE.
                if (!fromJPEG2000) {
                    OFCondition decoded = dataset->chooseRepresentation(EXS_LittleEndianExplicit, NULL);
                    if (decoded.bad()) return decoded;
                    inputSyntax = EXS_LittleEndianExplicit;
                }
                if (!dataset->canWriteXfer(inputSyntax)) inputSyntax = EXS_LittleEndianExplicit;
                OFCondition result = file.validateMetaInfo(inputSyntax, EWM_updateMeta);
                if (result.bad()) return result;
                const Uint32 length = file.calcElementLength(inputSyntax, EET_ExplicitLength);
                // DCMDataContainer uses signed int offsets. Refuse oversized
                // bridges rather than wrapping an offset or modifying a source.
                if (!length || length > INT_MAX - 65536) return EC_MemoryExhausted;
                NSMutableData* input = [NSMutableData dataWithLength:size_t(length) + 65536];
                DcmOutputBufferStream output(input.mutableBytes, input.length);
                file.transferInit();
                result = file.write(output, inputSyntax, EET_ExplicitLength, NULL,
                    EGL_recalcGL, EPD_withoutPadding, 0, 0, 0, EWM_updateMeta);
                file.transferEnd();
                if (result.bad()) return result;
                void* serialized = NULL;
                offile_off_t serializedLength = 0;
                output.flushBuffer(serialized, serializedLength);
                [input setLength:size_t(serializedLength)];
                DCMObject* object = [DCMObject objectWithData:input decodingPixelData:NO];
                if (!object) return EC_CannotChangeRepresentation;
                // Decode JPEG2000 to native before asking upstream for another
                // compressed codec. Encoding JPEG2000 uses the existing host path.
                const E_TransferSyntax intermediate = toJPEG2000 ? target : EXS_LittleEndianExplicit;
                DCMTransferSyntax* syntax = [[[DCMTransferSyntax alloc]
                    initWithTS:[NSString stringWithUTF8String:DcmXfer(intermediate).getXferID()]] autorelease];
                NSData* converted = [object writeDatasetWithTransferSyntax:syntax
                    quality:intermediate == EXS_JPEG2000LosslessOnly ? 0 : quality];
                if (!converted.length || converted.length > INT_MAX) return EC_CannotChangeRepresentation;
                DcmInputBufferStream stream;
                stream.setBuffer(converted.bytes, converted.length); stream.setEos();
                DcmDataset replacement;
                replacement.transferInit();
                result = replacement.read(stream, intermediate, EGL_noChange, DCM_MaxReadLength);
                replacement.transferEnd();
                if (result.good()) result = replacement.loadAllDataIntoMemory();
                if (result.bad()) return result;
                for (DcmTagKey key : {DCM_SOPClassUID, DCM_SOPInstanceUID}) {
                    OFString before, after;
                    if (dataset->findAndGetOFStringArray(key, before).bad() ||
                        replacement.findAndGetOFStringArray(key, after).bad() || before != after)
                        return EC_CannotChangeRepresentation;
                }
                // The DCM writer may normalize text encodings or other tags.
                // Only its pixel encoding belongs in the caller's dataset.
                // Preserve every other element, including private sequences
                // and changes the caller made after reading the source file.
                auto pixelEncoding = [](DcmTagKey key) {
                    return key == DCM_PixelData || key == DCM_PhotometricInterpretation ||
                        key == DCM_PlanarConfiguration || key == DCM_SamplesPerPixel ||
                        key == DCM_BitsAllocated || key == DCM_BitsStored ||
                        key == DCM_HighBit || key == DCM_PixelRepresentation ||
                        key == DCM_LossyImageCompression || key == DCM_LossyImageCompressionRatio ||
                        key == DCM_LossyImageCompressionMethod;
                };
                for (unsigned long i = replacement.card(); i > 0; --i)
                    if (!pixelEncoding(replacement.getElement(i - 1)->getTag().getXTag()))
                        delete replacement.remove(i - 1);
                for (unsigned long i = 0; i < dataset->card(); ++i) {
                    DcmElement* element = dataset->getElement(i);
                    if (!pixelEncoding(element->getTag().getXTag())) {
                        result = replacement.insert(static_cast<DcmElement*>(element->clone()), OFTrue);
                        if (result.bad()) return result;
                    }
                }
                result = dataset->copyFrom(replacement);
                if (result.bad() || toJPEG2000) return result;
            } @catch (NSException* exception) {
                return EC_CannotChangeRepresentation;
            }
        }
    }
    if (target == EXS_JPEGLSLossless || target == EXS_JPEGLSLossy) {
        // The former JPEG parameter class is not a JPEG-LS parameter object.
        DJLSRepresentationParameter jpegLS(Uint16(quality < 0 ? 0 : quality),
            target == EXS_JPEGLSLossless || quality == 0);
        return dataset->chooseRepresentation(target, &jpegLS);
    }
    return dataset->chooseRepresentation(target, parameters);
}
