#pragma once

#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dcddirif.h>
#include <dcmtk/dcmdata/dcdicdir.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcfilefo.h>
#include <dcmtk/dcmdata/dcdatset.h>
#include <dcmtk/dcmjpeg/ddpiimpl.h>
#include <algorithm>

// Series thumbnails are Horos export policy. Build them through public DCMTK
// records after writing the directory, rather than modifying the vendor class.
class HorosDicomDirIcons : public DicomDirInterface
{
public:
    OFCondition addSeriesIcons(const char* directoryPath, const char* sourceRoot)
    {
        DcmDicomDir directory(directoryPath);
        if (directory.error().bad()) return directory.error();
        DicomDirImageImplementation images;
        addImageSupport(&images);
        visit(directory.getRootRecord(), sourceRoot);
        return directory.write(EXS_LittleEndianExplicit, EET_ExplicitLength, EGL_withoutGL);
    }

private:
    void visit(DcmDirectoryRecord& record, const char* sourceRoot)
    {
        if (record.getRecordType() == ERT_Series && record.cardSub())
        {
            DcmDirectoryRecord* image = record.getSub(record.cardSub() / 2);
            if (!image || image->getRecordType() != ERT_Image) return;
            OFString relative;
            if (image->findAndGetOFStringArray(DCM_ReferencedFileID, relative).bad()) return;
            for (size_t index = 0; index < relative.size(); ++index)
                if (relative[index] == '\\') relative[index] = '/';
            const OFString source = OFString(sourceRoot) + "/" + relative;
            DcmFileFormat file;
            if (file.loadFile(source.c_str()).good())
                addIconImage(&record, file.getDataset(), 128, source.c_str());
            return;
        }
        for (unsigned long index = 0; index < record.cardSub(); ++index)
            if (DcmDirectoryRecord* child = record.getSub(index)) visit(*child, sourceRoot);
    }
};
