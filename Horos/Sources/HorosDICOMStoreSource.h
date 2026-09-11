#pragma once

#include "HorosDCMTKCompatibility.h"
#include "HorosDICOMRepresentation.h"
#import "Horos-Swift.h"
#include <dcmtk/dcmdata/dctk.h>
#include <dcmtk/dcmnet/assoc.h>
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#include <vector>

// Both retrieve services read the original under a shared lock. Pixel
// conversion, when required by the negotiated syntax, stays in memory.
class HorosDICOMFileLock
{
public:
    HorosDICOMFileLock(const char* path, bool writing)
        : fd_(open(path, writing ? O_WRONLY | O_CREAT : O_RDONLY, 0666))
    {
        if (fd_ >= 0)
        {
            int result;
            do { result = flock(fd_, writing ? LOCK_EX : LOCK_SH); }
            while (result < 0 && errno == EINTR);
            if (result < 0)
            {
                close(fd_);
                fd_ = -1;
            }
        }
    }

    ~HorosDICOMFileLock()
    {
        if (fd_ >= 0)
        {
            flock(fd_, LOCK_UN);
            close(fd_);
        }
    }

    bool valid() const { return fd_ >= 0; }

private:
    int fd_;
    HorosDICOMFileLock(const HorosDICOMFileLock&) = delete;
    HorosDICOMFileLock& operator=(const HorosDICOMFileLock&) = delete;
};

struct HorosDICOMStoreSource
{
    explicit HorosDICOMStoreSource(const char* path) : lock(path, false) {}

    OFCondition prepare(T_ASC_Association* association, const char* sopClass, const char* path, bool reverseRole = true)
    {
        if (!lock.valid()) return EC_InvalidStream;
        OFCondition result = file.loadFileUntilTag(path, EXS_Unknown, EGL_noChange,
            DCM_MaxReadLength, ERM_autoDetect, DCM_PixelData);
        if (result.bad()) return result;

        const E_TransferSyntax original = file.getDataset()->getOriginalXfer();
        if (!DcmXfer(original).isValid()) return EC_UnknownTransferSyntax;
        struct Candidate { T_ASC_PresentationContextID id; E_TransferSyntax syntax; int rank; };
        std::vector<Candidate> candidates;
        for (int index = 0; index < ASC_countPresentationContexts(association->params); ++index)
        {
            T_ASC_PresentationContext context;
            if (ASC_getPresentationContext(association->params, index, &context).bad() ||
                context.resultReason != ASC_P_ACCEPTANCE || strcmp(context.abstractSyntax, sopClass) != 0 ||
                (reverseRole ? (context.acceptedRole != ASC_SC_ROLE_SCP && context.acceptedRole != ASC_SC_ROLE_SCUSCP) :
                    (context.acceptedRole == ASC_SC_ROLE_SCP || context.acceptedRole == ASC_SC_ROLE_NONE)))
                continue;

            const DcmXfer accepted(context.acceptedTransferSyntax);
            if (!accepted.isValid()) continue;
            const int rank = (int)[HorosDIMSEPolicy
                rankAccepted:[NSString stringWithUTF8String:accepted.getXferID()]
                original:[NSString stringWithUTF8String:DcmXfer(original).getXferID()]];
            candidates.push_back({context.presentationContextID, accepted.getXfer(), rank});
        }
        std::stable_sort(candidates.begin(), candidates.end(),
            [](const Candidate& lhs, const Candidate& rhs) { return lhs.rank < rhs.rank; });

        bool loaded = false;
        result = DIMSE_NOVALIDPRESENTATIONCONTEXTID;
        for (const Candidate& candidate : candidates)
        {
            const DcmXfer accepted(candidate.syntax);
            const DcmXfer source(original);
            // Exact matches stay on DCMTK's file-streaming path. Only pixel
            // representation changes need a fully loaded dataset and codecs.
            const bool convert = [HorosDIMSEPolicy
                requiresConversionAccepted:[NSString stringWithUTF8String:accepted.getXferID()]
                original:[NSString stringWithUTF8String:source.getXferID()]];
            if (convert)
            {
                if (!loaded)
                {
                    result = file.loadFile(path);
                    if (result.bad()) return result;
                    loaded = true;
                }
                DcmDataset* dataset = file.getDataset();
                if (!dataset->canWriteXfer(accepted.getXfer()))
                {
                    result = HorosChooseDICOMRepresentation(file, accepted.getXfer());
                    if (result.bad()) continue;
                }
                if (!dataset->canWriteXfer(accepted.getXfer()))
                {
                    result = DIMSE_SENDFAILED;
                    continue;
                }
                datasetToSend = dataset;
            }
            presentationID = candidate.id;
            return EC_Normal;
        }
        return result;
    }

    HorosDICOMFileLock lock;
    DcmFileFormat file;
    DcmDataset* datasetToSend = NULL;
    T_ASC_PresentationContextID presentationID = 0;
};

