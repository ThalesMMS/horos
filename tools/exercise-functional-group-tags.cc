/*
 * Looks up the functional-group tags a multiframe's geometry is stored under in
 * the DCMTK the project compiles, and prints what the dictionary answers.
 *
 * The position of a frame is in PlanePositionSequence (0020,9113) and its
 * orientation in PlaneOrientationSequence (0020,9116); the volume-space pair is
 * PlanePositionVolumeSequence (0020,930e) and PlaneOrientationVolumeSequence
 * (0020,930f), holding ImagePositionVolume (0020,9301) and ImageOrientationVolume
 * (0020,9302). A tag the built-in dictionary does not know cannot be read from an
 * implicit-VR file at all, and the vendored dictionary was missing four of them.
 */
#include <dcmtk/dcmdata/dcdict.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcdicent.h>
#include <cstdio>

int main()
{
    const DcmTagKey keys[] = {
        DCM_PlanePositionSequence, DCM_PlaneOrientationSequence,
        DCM_PlanePositionVolumeSequence, DCM_PlaneOrientationVolumeSequence,
        DCM_ImagePositionVolume, DCM_ImageOrientationVolume,
        DCM_ImagePositionPatient, DCM_ImageOrientationPatient,
        DCM_FrameContentSequence, DCM_PixelMeasuresSequence
    };
    const unsigned count = sizeof(keys) / sizeof(keys[0]);

    DcmDataDictionary &dictionary = dcmDataDict.wrlock();
    for (unsigned i = 0; i < count; i++)
    {
        const DcmDictEntry *entry = dictionary.findEntry(keys[i], NULL);
        printf("%04x,%04x\t%s\t%s\t%d\t%d\n",
               keys[i].getGroup(), keys[i].getElement(),
               entry ? entry->getTagName() : "(absent)",
               entry ? DcmVR(entry->getEVR()).getVRName() : "-",
               entry ? entry->getVMMin() : -1,
               entry ? entry->getVMMax() : -1);
    }
    dcmDataDict.wrunlock();
    return 0;
}
