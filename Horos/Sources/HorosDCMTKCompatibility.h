#pragma once

#ifdef __cplusplus
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcuid.h>
#include <dcmtk/dcmdata/dcerror.h>
#include <dcmtk/ofstd/ofstd.h>
#include <dcmtk/ofstd/ofconsol.h>
#include <dcmtk/ofstd/ofstream.h>
using std::endl;
// Historical keyword spellings used by host and plugin facades. Numeric tags
// and UIDs stay identical; these do not add code or policy to the vendor.
// Historical private ROI tag, retained for reading existing local archives.
#define DCM_OsirixROI DcmTagKey(0x0071, 0x0011)
#define DCM_AcquisitionDatetime DCM_AcquisitionDateTime
#define DCM_ReferringPhysiciansName DCM_ReferringPhysicianName
#define DCM_PerformingPhysiciansName DCM_PerformingPhysicianName
#define DCM_ManufacturersModelName DCM_ManufacturerModelName
#define DCM_PatientsName DCM_PatientName
#define DCM_PatientsBirthDate DCM_PatientBirthDate
#define DCM_PatientsBirthTime DCM_PatientBirthTime
#define DCM_PatientsSex DCM_PatientSex
#define DCM_OtherPatientIDs DCM_RETIRED_OtherPatientIDs
#define DCM_PatientsAge DCM_PatientAge
#define DCM_PatientsSize DCM_PatientSize
#define DCM_PatientsWeight DCM_PatientWeight
#define DCM_EthnicGroup DCM_RETIRED_EthnicGroup
#define DCM_CardiacTriggerSequence DCM_CardiacSynchronizationSequence
#define DCM_OtherStudyNumbers DCM_RETIRED_OtherStudyNumbers
#define DCM_TriggerDelayTime DCM_NominalCardiacTriggerDelayTime
#define DCM_FramesOfInterestDescription DCM_FrameOfInterestDescription
#define DCM_StudyComments DCM_RETIRED_StudyComments
#define DCM_InterpretationStatusID DCM_RETIRED_InterpretationStatusID
#define UID_FINDPatientStudyOnlyQueryRetrieveInformationModel UID_RETIRED_FINDPatientStudyOnlyQueryRetrieveInformationModel
#define UID_GETPatientStudyOnlyQueryRetrieveInformationModel UID_RETIRED_GETPatientStudyOnlyQueryRetrieveInformationModel

#include <dcmtk/dcmnet/cond.h>
#include <dcmtk/dcmnet/diutil.h>
#include <dcmtk/dcmnet/assoc.h>
#include <dcmtk/dcmtls/tlslayer.h>
#include <dcmtk/dcmtls/tlsciphr.h>
#include <cstdarg>
#include <cstdio>
#define OFM_imagectn OFM_dcmqrdb
// Preserve the historical diagnostic calls through public DCMTK loggers.
static inline void HorosDIMSEWarning(T_ASC_Association*, const char* format, ...) {
    char message[2048]; va_list args; va_start(args, format);
    std::vsnprintf(message, sizeof(message), format, args); va_end(args);
    DCMNET_WARN(message);
}
static inline void HorosDIMSEError(const char* format, ...) {
    char message[2048]; va_list args; va_start(args, format);
    std::vsnprintf(message, sizeof(message), format, args); va_end(args);
    DCMNET_ERROR(message);
}
#define EXS_JPEGProcess10_12TransferSyntax EXS_JPEGProcess10_12
#define EXS_JPEGProcess11_13TransferSyntax EXS_JPEGProcess11_13
#define EXS_JPEGProcess14SV1TransferSyntax EXS_JPEGProcess14SV1
#define EXS_JPEGProcess14TransferSyntax EXS_JPEGProcess14
#define EXS_JPEGProcess15TransferSyntax EXS_JPEGProcess15
#define EXS_JPEGProcess16_18TransferSyntax EXS_JPEGProcess16_18
#define EXS_JPEGProcess17_19TransferSyntax EXS_JPEGProcess17_19
#define EXS_JPEGProcess1TransferSyntax EXS_JPEGProcess1
#define EXS_JPEGProcess20_22TransferSyntax EXS_JPEGProcess20_22
#define EXS_JPEGProcess21_23TransferSyntax EXS_JPEGProcess21_23
#define EXS_JPEGProcess24_26TransferSyntax EXS_JPEGProcess24_26
#define EXS_JPEGProcess25_27TransferSyntax EXS_JPEGProcess25_27
#define EXS_JPEGProcess28TransferSyntax EXS_JPEGProcess28
#define EXS_JPEGProcess29TransferSyntax EXS_JPEGProcess29
#define EXS_JPEGProcess2_4TransferSyntax EXS_JPEGProcess2_4
#define EXS_JPEGProcess3_5TransferSyntax EXS_JPEGProcess3_5
#define EXS_JPEGProcess6_8TransferSyntax EXS_JPEGProcess6_8
#define EXS_JPEGProcess7_9TransferSyntax EXS_JPEGProcess7_9

#endif
