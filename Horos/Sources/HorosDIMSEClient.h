#pragma once

#include "HorosDCMTKCompatibility.h"
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmnet/dimse.h>
#include <dcmtk/dcmqrdb/dcmqropt.h>
#include <dcmtk/dcmqrdb/dcmqrdba.h>

// Application-owned loops add host cancellation and same-association C-STORE
// handling using DCMTK's public messaging API. Upstream providers stay stock.
OFCondition HorosDIMSEGetUser(T_ASC_Association*, T_ASC_PresentationContextID,
    T_DIMSE_C_GetRQ*, DcmDataset*, DIMSE_GetUserCallback, void*,
    T_DIMSE_BlockingMode, int, T_ASC_Network*, DIMSE_SubOpProviderCallback, void*,
    T_DIMSE_C_GetRSP*, DcmDataset**, DcmDataset**);
OFCondition HorosDIMSEMoveUser(T_ASC_Association*, T_ASC_PresentationContextID,
    T_DIMSE_C_MoveRQ*, DcmDataset*, DIMSE_MoveUserCallback, void*,
    T_DIMSE_BlockingMode, int, T_ASC_Network*, DIMSE_SubOpProviderCallback, void*,
    T_DIMSE_C_MoveRSP*, DcmDataset**, DcmDataset**, OFBool = OFFalse);
OFCondition HorosStoreSCP(T_ASC_Association*, T_DIMSE_C_StoreRQ&,
    T_ASC_PresentationContextID, DcmQueryRetrieveDatabaseHandle&,
    const DcmQueryRetrieveOptions&);
