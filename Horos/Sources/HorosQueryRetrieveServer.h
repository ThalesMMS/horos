#ifndef HOROS_QUERY_RETRIEVE_SERVER_H
#define HOROS_QUERY_RETRIEVE_SERVER_H

#include "HorosDCMTKCompatibility.h"
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmnet/dcasccfg.h>
#include <dcmtk/dcmqrdb/dcmqrdba.h>
#include <dcmtk/dcmqrdb/dcmqropt.h>
#include <memory>

class HorosAssociationProcesses;

// Application integration over stock DCMTK. DCMTK owns association/DIMSE
// processing; Horos supplies database access and per-image C-GET selection.
class HorosQueryRetrieveServer
{
public:
    HorosQueryRetrieveServer(const DcmQueryRetrieveConfig& config,
                             const DcmQueryRetrieveOptions& options,
                             const DcmQueryRetrieveDatabaseHandleFactory& factory,
                             const DcmAssociationConfiguration& associations,
                             OFBool secureConnection);
    ~HorosQueryRetrieveServer();

    OFCondition waitForAssociation(T_ASC_Network* network);

private:
    const DcmQueryRetrieveConfig& config_;
    const DcmQueryRetrieveOptions& options_;
    const DcmQueryRetrieveDatabaseHandleFactory& factory_;
    const DcmAssociationConfiguration& associations_;
    OFBool secureConnection_;
    std::unique_ptr<HorosAssociationProcesses> processes_;

    HorosQueryRetrieveServer(const HorosQueryRetrieveServer&) = delete;
    HorosQueryRetrieveServer& operator=(const HorosQueryRetrieveServer&) = delete;
};

#endif
