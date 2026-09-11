#include "HorosDICOMIdentity.h"
#include "HorosDIMSEAssociation.h"
#include "HorosDICOMStoreSource.h"
#import "HorosDIMSEClient.h"
#import "HorosDICOMMoveContext.h"
#import "Horos-Swift.h"
#import "AppController.h"
#import "ContextCleaner.h"
#import "DCMNetServiceDelegate.h"
#import "DicomDatabase.h"
#import "NSThread+N2.h"
#import "ThreadsManager.h"
#import "HorosDICOMGlobalAbort.h"
#include "HorosQueryRetrieveServer.h"

#include <dcmtk/dcmdata/dctk.h>
#include <dcmtk/dcmnet/scpthrd.h>
#include <dcmtk/dcmqrdb/dcmqrcbf.h>
#include <dcmtk/dcmqrdb/dcmqrcbm.h>
#include <dcmtk/dcmqrdb/dcmqrcbs.h>
#include <dcmtk/dcmqrdb/dcmqrdbs.h>
#include <dcmtk/ofstd/ofstd.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <mutex>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <sys/file.h>
#include <sys/param.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

NSManagedObjectContext* staticContext = nil;
BOOL forkedProcess = NO;
static std::atomic<unsigned> activeAssociations{0};

class HorosAssociationProcesses
{
public:
    std::atomic<unsigned> active{0};
    std::atomic<bool> stopping{false};

    void addThread(NSThread* thread)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        threads_.push_back([thread retain]);
    }
    void removeThread(NSThread* thread)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto found = std::find(threads_.begin(), threads_.end(), thread);
        if (found != threads_.end()) { [*found release]; threads_.erase(found); }
    }
    void requestStop()
    {
        stopping = true;
        std::lock_guard<std::mutex> lock(mutex_);
        for (NSThread* thread : threads_) [thread cancel];
    }

    size_t countChildProcesses() const
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return processes_.size();
    }
    bool haveProcessWithWriteAccess(const char* calledAE) const
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return std::any_of(processes_.begin(), processes_.end(), [&](const Process& process) {
            return process.canStore && process.calledAE == calledAE;
        });
    }
    void addProcessToTable(pid_t pid, T_ASC_Association* association)
    {
        bool canStore = false;
        for (int index = 0; index < ASC_countPresentationContexts(association->params); ++index)
        {
            T_ASC_PresentationContext context;
            if (ASC_getPresentationContext(association->params, index, &context).good() &&
                context.resultReason == ASC_P_ACCEPTANCE && dcmIsaStorageSOPClassUID(context.abstractSyntax) &&
                context.acceptedRole != ASC_SC_ROLE_SCP)
                canStore = true;
        }
        std::lock_guard<std::mutex> lock(mutex_);
        processes_.push_back({pid, association->params->DULparams.calledAPTitle, canStore});
    }
    void finishProcess(pid_t pid)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        processes_.erase(std::remove_if(processes_.begin(), processes_.end(),
            [pid](const Process& process) { return process.id == pid; }), processes_.end());
    }
private:
    struct Process { pid_t id; OFString calledAE; bool canStore; };
    mutable std::mutex mutex_;
    std::vector<Process> processes_;
    std::vector<NSThread*> threads_;
};

static void HorosStartForkMonitor(pid_t pid, NSPersistentStoreCoordinator* coordinator,
    NSString* peer, HorosAssociationProcesses& processes);

namespace {

class GetContext
{
public:
    GetContext(DcmQueryRetrieveDatabaseHandle& database, const DcmQueryRetrieveOptions& options,
               T_ASC_Association* association, T_ASC_PresentationContextID presentationID)
        : database_(database), options_(options), association_(association), presentationID_(presentationID) {}

    static void callback(void* data, OFBool cancelled, T_DIMSE_C_GetRQ* request,
                         DcmDataset* identifiers, int responseCount, T_DIMSE_C_GetRSP* response,
                         DcmDataset** detail, DcmDataset** responseIdentifiers)
    {
        static_cast<GetContext*>(data)->respond(cancelled, request, identifiers, responseCount,
                                               response, detail, responseIdentifiers);
    }

private:
    void respond(OFBool cancelled, T_DIMSE_C_GetRQ* request, DcmDataset* identifiers,
                 int responseCount, T_DIMSE_C_GetRSP* response, DcmDataset** detail,
                 DcmDataset** responseIdentifiers)
    {
        DcmQueryRetrieveDatabaseStatus status(STATUS_Pending);
        OFCondition result = EC_Normal;
        if (responseCount == 1)
            result = database_.startMoveRequest(request->AffectedSOPClassUID, identifiers, &status);
        if (result.bad() && status.status() == STATUS_Pending)
            status.setStatus(STATUS_GET_Refused_OutOfResourcesNumberOfMatches);

        cancelled = cancelled || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested();
        if (cancelled && status.status() == STATUS_Pending)
            cancel(status);
        if (status.status() == STATUS_Pending)
        {
            DIC_UI sopClass = {}, sopInstance = {};
            char path[MAXPATHLEN + 1] = {};
            result = database_.nextMoveResponse(sopClass, sizeof(sopClass), sopInstance, sizeof(sopInstance),
                path, sizeof(path), &remaining_, &status);
            if (result.bad())
                status.setStatus(STATUS_GET_Refused_OutOfResourcesSubOperations);
            else if (status.status() == STATUS_Pending)
                sendImage(request, sopClass, sopInstance, path, status);
        }

        // Do not turn a cancellation or database error into success/warning.
        if (status.status() == STATUS_Success && (failed_ || warnings_))
            status.setStatus((Uint16)[HorosDIMSEPolicy finalGetStatusProposed:status.status()
                completed:completed_ failed:failed_ warnings:warnings_ cancelled:NO]);
        if (status.status() != STATUS_Success && status.status() != STATUS_Pending && !failedUIDs_.empty())
        {
            *responseIdentifiers = new DcmDataset;
            (*responseIdentifiers)->putAndInsertString(DCM_FailedSOPInstanceUIDList, failedUIDs_.c_str());
        }
        response->DimseStatus = status.status();
        response->NumberOfRemainingSubOperations = remaining_;
        response->NumberOfCompletedSubOperations = completed_;
        response->NumberOfFailedSubOperations = failed_;
        response->NumberOfWarningSubOperations = warnings_;
        *detail = status.extractStatusDetail();
    }

    void cancel(DcmQueryRetrieveDatabaseStatus& status)
    {
        database_.cancelMoveRequest(&status);
        status.setStatus(STATUS_GET_Cancel_SubOperationsTerminatedDueToCancelIndication);
    }

    void failed(const char* sopInstance)
    {
        ++failed_;
        if (sopInstance[0])
        {
            if (!failedUIDs_.empty()) failedUIDs_ += "\\";
            failedUIDs_ += sopInstance;
        }
    }

    void sendImage(T_DIMSE_C_GetRQ* request, const char* sopClass, const char* sopInstance,
                   const char* path, DcmQueryRetrieveDatabaseStatus& status)
    {
        HorosDICOMStoreSource source(path);
        OFCondition result = source.prepare(association_, sopClass, path);
        if (result.bad())
        {
            failed(sopInstance);
            DCMQRDB_ERROR("Horos C-GET: cannot prepare instance " << sopInstance << ": " << result.text());
            return;
        }

        T_DIMSE_C_StoreRQ storeRequest = {};
        storeRequest.MessageID = association_->nextMsgID++;
        storeRequest.Priority = request->Priority;
        storeRequest.DataSetType = DIMSE_DATASET_PRESENT;
        OFStandard::strlcpy(storeRequest.AffectedSOPClassUID, sopClass, sizeof(storeRequest.AffectedSOPClassUID));
        OFStandard::strlcpy(storeRequest.AffectedSOPInstanceUID, sopInstance, sizeof(storeRequest.AffectedSOPInstanceUID));
        T_DIMSE_C_StoreRSP response = {};
        T_DIMSE_DetectedCancelParameters cancellation = {};
        DcmDataset* detail = NULL;
        result = DIMSE_storeUser(association_, source.presentationID, &storeRequest,
            source.datasetToSend ? NULL : path, source.datasetToSend, NULL, NULL,
            options_.blockMode_, options_.dimse_timeout_, &response, &detail, &cancellation);
        delete detail;

        if (result.good() && response.DimseStatus == STATUS_Success)
            ++completed_;
        else if (result.good() && DICOM_WARNING_STATUS(response.DimseStatus))
            ++warnings_;
        else
        {
            failed(sopInstance);
            DCMQRDB_ERROR("Horos C-GET: store sub-operation failed: " << result.text()
                << ", status " << response.DimseStatus);
        }
        if (result.bad())
        {
            // A failed DIMSE exchange may have left the association unusable.
            // Stop rather than consuming the remaining database results.
            DcmQueryRetrieveDatabaseStatus cleanup;
            database_.cancelMoveRequest(&cleanup);
            status.setStatus(STATUS_GET_Refused_OutOfResourcesSubOperations);
        }
        if (cancellation.cancelEncountered && cancellation.presId == presentationID_ &&
            cancellation.req.MessageIDBeingRespondedTo == request->MessageID)
            cancel(status);
    }

    DcmQueryRetrieveDatabaseHandle& database_;
    const DcmQueryRetrieveOptions& options_;
    T_ASC_Association* association_;
    T_ASC_PresentationContextID presentationID_;
    unsigned short remaining_ = 0, completed_ = 0, failed_ = 0, warnings_ = 0;
    OFString failedUIDs_;
};

void findCallback(void* data, OFBool cancelled, T_DIMSE_C_FindRQ* request, DcmDataset* identifiers,
                  int count, T_DIMSE_C_FindRSP* response, DcmDataset** detail, DcmDataset** responseIdentifiers)
{
    static_cast<DcmQueryRetrieveFindContext*>(data)->callbackHandler(
        cancelled || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested(),
        request, identifiers, count, response, detail, responseIdentifiers);
}

void moveCallback(void* data, OFBool cancelled, T_DIMSE_C_MoveRQ* request, DcmDataset* identifiers,
                  int count, T_DIMSE_C_MoveRSP* response, DcmDataset** detail, DcmDataset** responseIdentifiers)
{
    static_cast<HorosDICOMMoveContext*>(data)->callbackHandler(
        cancelled || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested(),
        request, identifiers, count, response, detail, responseIdentifiers);
}

struct HorosStoreCallbackContext
{
    DcmQueryRetrieveStoreContext* store;
    T_ASC_Association* association;
    bool aborted = false;
    bool preserveCompletedFile = false;
};

void storeCallback(void* data, T_DIMSE_StoreProgress* progress, T_DIMSE_C_StoreRQ* request,
                   char* path, DcmDataset** dataset, T_DIMSE_C_StoreRSP* response, DcmDataset** detail)
{
    auto* info = static_cast<HorosStoreCallbackContext*>(data);
    auto* context = info->store;
    // Cancellation stays on the receiving worker, including a streaming C-GET
    // sub-operation. No cancelled object may reach publication or inventory.
    if ([NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested())
    {
        context->setStatus(STATUS_STORE_Refused_OutOfResources);
        response->DimseStatus = STATUS_STORE_Refused_OutOfResources;
        if (!info->aborted)
        {
            info->aborted = true;
            ASC_closeTransportConnection(info->association);
        }
        return;
    }
    if (progress->state == DIMSE_StoreEnd && dataset && *dataset &&
        context->getStatus() == STATUS_Success) {
        char sopClass[65] = {}, sopInstance[65] = {};
        if (!HorosFindSOPClassAndInstanceInDataSet(*dataset, sopClass, sizeof(sopClass),
                sopInstance, sizeof(sopInstance)) || !sopClass[0] || !sopInstance[0])
            context->setStatus(STATUS_STORE_Error_CannotUnderstand);
    }
    if (context->getStatus() != STATUS_Success)
        response->DimseStatus = context->getStatus();
    const bool canPublish = context->getStatus() == STATUS_Success &&
        response->DimseStatus == STATUS_Success;
    context->callbackHandler(
        progress, request, path, dataset, response, detail);
    // Upstream deletes an incomplete write itself. If a complete, valid file
    // remains after publication fails, preserve it for diagnosis/recovery.
    if (progress->state == DIMSE_StoreEnd && canPublish &&
        response->DimseStatus == STATUS_STORE_Refused_OutOfResources)
        info->preserveCompletedFile = true;
    if (progress->state == DIMSE_StoreEnd && !forkedProcess)
    {
        OFString study, series;
        if (dataset && *dataset)
        {
            (*dataset)->findAndGetOFString(DCM_StudyInstanceUID, study);
            (*dataset)->findAndGetOFString(DCM_SeriesInstanceUID, series);
        }
        [[NSNotificationCenter defaultCenter] postNotificationName:@"HorosDICOMStoreCompleted" object:nil userInfo:@{
            @"uid":[NSString stringWithUTF8String:request->AffectedSOPInstanceUID] ?: @"",
            @"study":[NSString stringWithUTF8String:study.c_str()] ?: @"",
            @"series":[NSString stringWithUTF8String:series.c_str()] ?: @"",
            @"status":@(response->DimseStatus)}];
    }
}

class QueryRetrieveAssociation : public DcmThreadSCP
{
public:
    QueryRetrieveAssociation(T_ASC_Association* association, const DcmQueryRetrieveConfig& config,
                              const DcmQueryRetrieveOptions& options,
                              const DcmQueryRetrieveDatabaseHandleFactory& factory,
                              const DcmAssociationConfiguration& profiles,
                              HorosAssociationProcesses& processes, OFBool secureConnection)
        : association_(association), config_(config), options_(options), factory_(factory),
          profiles_(profiles), processes_(processes), secureConnection_(secureConnection)
    {
        setRespondWithCalledAETitle(OFTrue);
        forceAssociationRefuse(options_.refuse_);
        setACSETimeout(options_.acse_timeout_);
        setDIMSEBlockingMode(options_.blockMode_);
        setDIMSETimeout(options_.dimse_timeout_);
        setProgressNotificationMode(OFFalse);
    }

public:
    OFCondition lastFailure = EC_Normal;

protected:
    void notifyDIMSEError(const OFCondition& condition) override
    {
        lastFailure = condition;
        DcmSCP::notifyDIMSEError(condition);
        if (cancelled()) return;
        NSString* message = [NSString stringWithFormat:
            @"DICOM association from %.64s to %.64s ended: %04x:%04x %s",
            association_->params->DULparams.callingAPTitle,
            association_->params->DULparams.calledAPTitle,
            condition.module(), condition.code(), condition.text()];
        if (forkedProcess)
            [message writeToFile:[NSString stringWithFormat:@"/tmp/horos-dimse-error-%d", getpid()]
                     atomically:YES encoding:NSUTF8StringEncoding error:NULL];
        else
            [[AppController sharedAppController] performSelectorOnMainThread:@selector(displayListenerError:)
                withObject:message waitUntilDone:NO];
    }

    void notifyAssociationRequest(const T_ASC_Parameters& parameters, DcmSCPActionType& action) override
    {
        if ((options_.rejectWhenNoImplementationClassUID_ && !parameters.theirImplementationClassUID[0]) ||
            processes_.countChildProcesses() >= static_cast<size_t>(options_.maxAssociations_))
            action = DCMSCP_ACTION_REFUSE_ASSOCIATION;
    }

    OFBool checkCalledAETitleAccepted(const OFString& calledAE) override
    {
        const auto& parameters = association_->params->DULparams;
        return config_.peerInAETitle(calledAE.c_str(), parameters.callingAPTitle,
                                     parameters.callingPresentationAddress);
    }

    OFCondition negotiateAssociation() override
    {
        OFCondition result = profiles_.evaluateAssociationParameters(options_.incomingProfile.c_str(), *association_);
        if (result.bad())
        {
            DCMQRDB_ERROR("Horos listener: association profile failed: " << result.text());
            refuseAssociation(DCMSCP_INTERNAL_ERROR);
            return result;
        }
        std::vector<const char*> syntaxes;
        DcmXfer preferred(options_.networkTransferSyntax_);
        if (preferred.isValid()) syntaxes.push_back(preferred.getXferID());
        if (options_.networkTransferSyntax_ != EXS_LittleEndianImplicit)
        {
            syntaxes.push_back(UID_LittleEndianExplicitTransferSyntax);
            syntaxes.push_back(UID_BigEndianExplicitTransferSyntax);
            syntaxes.push_back(UID_LittleEndianImplicitTransferSyntax);
        }
        const char* services[] = {
            UID_VerificationSOPClass,
            UID_FINDPatientRootQueryRetrieveInformationModel, UID_MOVEPatientRootQueryRetrieveInformationModel,
            UID_GETPatientRootQueryRetrieveInformationModel,
            UID_FINDStudyRootQueryRetrieveInformationModel, UID_MOVEStudyRootQueryRetrieveInformationModel,
            UID_GETStudyRootQueryRetrieveInformationModel,
            UID_RETIRED_FINDPatientStudyOnlyQueryRetrieveInformationModel,
            UID_RETIRED_MOVEPatientStudyOnlyQueryRetrieveInformationModel,
            UID_RETIRED_GETPatientStudyOnlyQueryRetrieveInformationModel
        };
        std::vector<const char*> enabled(1, services[0]);
        const bool roots[] = {bool(options_.supportPatientRoot_), bool(options_.supportStudyRoot_),
                              bool(options_.supportPatientStudyOnly_)};
        for (int root = 0; root < 3; ++root)
            if (roots[root])
                for (int service = 0; service < (options_.disableGetSupport_ ? 2 : 3); ++service)
                    enabled.push_back(services[1 + root * 3 + service]);
        result = ASC_acceptContextsWithPreferredTransferSyntaxes(association_->params,
            enabled.data(), static_cast<int>(enabled.size()), syntaxes.data(), static_cast<int>(syntaxes.size()));
        if (result.bad()) return result;

        const char* calledAE = association_->params->DULparams.calledAPTitle;
        const bool refuseStorage = !config_.writableStorageArea(calledAE) ||
            (options_.refuseMultipleStorageAssociations_ && processes_.haveProcessWithWriteAccess(calledAE));
        for (int index = 0; index < ASC_countPresentationContexts(association_->params); ++index)
        {
            T_ASC_PresentationContext context;
            if (ASC_getPresentationContext(association_->params, index, &context).bad() ||
                context.resultReason != ASC_P_ACCEPTANCE) continue;
            if (refuseStorage && dcmIsaStorageSOPClassUID(context.abstractSyntax) &&
                context.acceptedRole != ASC_SC_ROLE_SCP)
                ASC_refusePresentationContext(association_->params, context.presentationContextID, ASC_P_USERREJECTION);
            if (options_.requireFindForMove_)
                for (int root = 0; root < 3; ++root)
                    if (strcmp(context.abstractSyntax, services[2 + root * 3]) == 0 &&
                        !ASC_findAcceptedPresentationContextID(association_, services[1 + root * 3]))
                        ASC_refusePresentationContext(association_->params, context.presentationContextID, ASC_P_USERREJECTION);
        }
        return EC_Normal;
    }

    bool cancelled() const
    {
        return processes_.stopping || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested();
    }

    void handleAssociation() override
    {
        bool child = false;
#ifdef HAVE_FORK
        if (!options_.singleProcess_)
        {
            // Preserve the separate Core Data context used by the legacy fork
            // mode. The parent holds its coordinator until the child has read
            // its query snapshot (OsiriXSCPDataHandler removes lock_process).
            DicomDatabase* database = [DicomDatabase defaultDatabase];
            NSPersistentStoreCoordinator* coordinator = [[database managedObjectContext] persistentStoreCoordinator];
            // Query committed state, as the threaded independent context does.
            // The main context must never be saved from this listener thread.
            NSURL* databaseURL = [NSURL fileURLWithPath:[database sqlFilePath]];
            [coordinator lock];
            // DicomImage resolves file paths through its context's database.
            // A plain NSManagedObjectContext loses that association in the child.
            NSManagedObjectContext* forkContext = [[N2ManagedObjectContext alloc]
                initWithDatabase:database concurrencyType:NSConfinementConcurrencyType];
            forkContext.undoManager = nil;
            forkContext.persistentStoreCoordinator = [[[NSPersistentStoreCoordinator alloc]
                initWithManagedObjectModel:[coordinator managedObjectModel]] autorelease];
            [DCMNetServiceDelegate DICOMServersList];
            const pid_t pid = fork();
            if (pid != 0)
            {
                [forkContext release];
                [coordinator unlock];
                if (pid < 0)
                {
                    notifyDIMSEError(EC_MemoryExhausted);
                    ASC_closeTransportConnection(association_);
                }
                else
                {
                    ASC_setParentProcessMode(association_);
                    processes_.addProcessToTable(pid, association_);
                    HorosStartForkMonitor(pid, coordinator,
                        [NSString stringWithUTF8String:association_->params->DULparams.callingPresentationAddress], processes_);
                }
                return;
            }
            child = true;
            staticContext = forkContext; // child-local; parallel listeners never share this context
            forkedProcess = YES;
            // An open SQLite connection cannot be inherited across fork. Open
            // this association's read-only store only in the child process.
            NSError* error = nil;
            if (![staticContext.persistentStoreCoordinator addPersistentStoreWithType:NSSQLiteStoreType
                configuration:nil URL:databaseURL options:@{NSReadOnlyPersistentStoreOption:@YES} error:&error])
            {
                notifyDIMSEError(EC_InvalidStream);
                dropAndDestroyAssociation();
                _Exit(3);
            }
            char path[128]; snprintf(path, sizeof(path), "/tmp/lock_process-%d", getpid());
            const int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
            if (fd >= 0) close(fd);
        }
#endif
        // Poll before receiving commands so idle connections can be cancelled.
        // The actual DIMSE receive retains its configured command timeout.
        OFCondition result = EC_Normal;
        auto idleSince = std::chrono::steady_clock::now();
        int idleTimeout = dcmConnectionTimeout.get() > 0 ? dcmConnectionTimeout.get() : 5;
        while (result.good() && !cancelled())
        {
            if (!ASC_dataWaiting(association_, 1))
            {
                if (idleTimeout > 0 && std::chrono::duration_cast<std::chrono::seconds>(
                    std::chrono::steady_clock::now() - idleSince).count() >= idleTimeout)
                    result = DIMSE_NODATAAVAILABLE;
                continue;
            }
            T_DIMSE_Message message = {};
            T_ASC_PresentationContextID id = 0;
            result = receiveDIMSECommand(&id, &message, NULL);
            if (result.good())
            {
                DcmPresentationContextInfo context;
                if (!getPresentationContextInfo(association_, id, context))
                    result = DIMSE_NOVALIDPRESENTATIONCONTEXTID;
                else result = handleIncomingCommand(&message, context);
                idleSince = std::chrono::steady_clock::now();
                idleTimeout = options_.dimse_timeout_;
            }
        }
        if (result == DUL_PEERREQUESTEDRELEASE)
        {
            notifyReleaseRequest();
            result = ASC_acknowledgeRelease(association_);
            if (result.bad()) notifyDIMSEError(result);
        }
        else if (result == DUL_PEERABORTEDASSOCIATION)
        {
            notifyAbortRequest();
            notifyDIMSEError(result);
        }
        else
        {
            if (!cancelled()) notifyDIMSEError(result);
            ASC_closeTransportConnection(association_);
        }
        database_.reset();
        if (child)
        {
            char path[128]; snprintf(path, sizeof(path), "/tmp/lock_process-%d", getpid()); unlink(path);
            snprintf(path, sizeof(path), "/tmp/process_state-%d", getpid()); unlink(path);
            dropAndDestroyAssociation();
            _Exit(result.good() || result == DUL_PEERREQUESTEDRELEASE ? 0 : 3);
        }
    }

    OFCondition handleIncomingCommand(T_DIMSE_Message* message, const DcmPresentationContextInfo& context) override
    {
        if (message->CommandField == DIMSE_C_CANCEL_RQ) return EC_Normal; // Late cancellation.
        if ((message->CommandField == DIMSE_C_GET_RQ &&
             ![[NSUserDefaults standardUserDefaults] boolForKey:@"activateCGETSCP"]) ||
            (message->CommandField == DIMSE_C_FIND_RQ &&
             ![[NSUserDefaults standardUserDefaults] boolForKey:@"activateCFINDSCP"]))
            return DIMSE_BADCOMMANDTYPE;
        const char* operation = message->CommandField == DIMSE_C_STORE_RQ ? "C-STORE" :
            message->CommandField == DIMSE_C_FIND_RQ ? "C-FIND" :
            message->CommandField == DIMSE_C_MOVE_RQ ? "C-MOVE" :
            message->CommandField == DIMSE_C_GET_RQ ? "C-GET" : "C-ECHO";
        NSString* progress = [NSString stringWithFormat:@"%s%s SCP...", operation, secureConnection_ ? " TLS" : ""];
        if (forkedProcess)
        {
            [progress writeToFile:[NSString stringWithFormat:@"/tmp/process_state-%d", getpid()]
                atomically:YES encoding:NSUTF8StringEncoding error:NULL];
            if (message->CommandField == DIMSE_C_ECHO_RQ || message->CommandField == DIMSE_C_STORE_RQ)
            {
                char path[128]; snprintf(path, sizeof(path), "/tmp/lock_process-%d", getpid()); unlink(path);
            }
        }
        else [NSThread currentThread].status = [NSString stringWithFormat:@"%s %@",
            association_->params->DULparams.callingPresentationAddress, progress];
        const char* sopClass = NULL;
        switch (message->CommandField)
        {
            case DIMSE_C_ECHO_RQ: sopClass = message->msg.CEchoRQ.AffectedSOPClassUID; break;
            case DIMSE_C_STORE_RQ: sopClass = message->msg.CStoreRQ.AffectedSOPClassUID; break;
            case DIMSE_C_FIND_RQ: sopClass = message->msg.CFindRQ.AffectedSOPClassUID; break;
            case DIMSE_C_MOVE_RQ: sopClass = message->msg.CMoveRQ.AffectedSOPClassUID; break;
            case DIMSE_C_GET_RQ: sopClass = message->msg.CGetRQ.AffectedSOPClassUID; break;
            default: return DIMSE_BADCOMMANDTYPE;
        }
        if (context.abstractSyntax != sopClass) return DIMSE_BADMESSAGE;
        T_ASC_PresentationContext accepted;
        if (ASC_findAcceptedPresentationContext(association_->params, context.presentationContextID, &accepted).bad() ||
            accepted.acceptedRole == ASC_SC_ROLE_SCP)
            return DIMSE_NOVALIDPRESENTATIONCONTEXTID;

        OFCondition result = EC_Normal;
        if (!database_)
        {
            database_.reset(factory_.createDBHandle(association_->params->DULparams.callingAPTitle,
                association_->params->DULparams.calledAPTitle, result));
            if (result.bad() || !database_) return result.bad() ? result : EC_IllegalCall;
            database_->setIdentifierChecking(OFFalse, OFFalse);
        }
        result = dispatch(message, context);
        if (!options_.keepDBHandleDuringAssociation_) database_.reset();
        return result;
    }

private:
    OFCondition dispatch(T_DIMSE_Message* message, const DcmPresentationContextInfo& context)
    {
        const auto id = context.presentationContextID;
        const char* calledAE = association_->params->DULparams.calledAPTitle;
        switch (message->CommandField)
        {
            case DIMSE_C_ECHO_RQ:
                return DcmSCP::handleIncomingCommand(message, context);
            case DIMSE_C_STORE_RQ:
                return HorosStoreSCP(association_, message->msg.CStoreRQ, id, *database_, options_);
            case DIMSE_C_FIND_RQ:
            {
                DcmQueryRetrieveFindContext find(*database_, options_, STATUS_Pending, config_.getCharacterSetOptions());
                find.setOurAETitle(calledAE);
                return DIMSE_findProvider(association_, id, &message->msg.CFindRQ, findCallback, &find,
                    options_.blockMode_, options_.dimse_timeout_);
            }
            case DIMSE_C_MOVE_RQ:
            {
                auto& request = message->msg.CMoveRQ;
                HorosDICOMMoveContext move(*database_, options_, &config_, STATUS_Pending,
                    association_, request.MessageID, request.Priority);
                move.setOurAETitle(calledAE);
                return DIMSE_moveProvider(association_, id, &request, moveCallback, &move,
                    options_.blockMode_, options_.dimse_timeout_);
            }
            case DIMSE_C_GET_RQ:
            {
                GetContext get(*database_, options_, association_, id);
                return DIMSE_getProvider(association_, id, &message->msg.CGetRQ, GetContext::callback, &get,
                    options_.blockMode_, options_.dimse_timeout_);
            }
            default:
                return DIMSE_BADCOMMANDTYPE;
        }
    }



    T_ASC_Association* association_; // Borrowed; DcmThreadSCP owns it after run().
    const DcmQueryRetrieveConfig& config_;
    const DcmQueryRetrieveOptions& options_;
    const DcmQueryRetrieveDatabaseHandleFactory& factory_;
    const DcmAssociationConfiguration& profiles_;
    HorosAssociationProcesses& processes_;
    OFBool secureConnection_;
    std::unique_ptr<DcmQueryRetrieveDatabaseHandle> database_;
};

} // namespace

@interface HorosAssociationTask : NSObject
{
@public
    QueryRetrieveAssociation* worker;
    T_ASC_Association* association;
    HorosAssociationProcesses* processes;
}
- (void)run;
@end

@implementation HorosAssociationTask
- (void)run
{
    @autoreleasepool
    {
        @try
        {
            try { worker->run(association); }
            catch (const std::exception& error) { NSLog(@"DICOM association failed: %s", error.what()); }
            catch (...) { NSLog(@"DICOM association failed with a C++ exception"); }
        }
        @catch (NSException* exception) { NSLog(@"DICOM association failed: %@", exception); }
        @finally
        {
            // DcmThreadSCP owns association after run, including refusal/errors.
            delete worker; worker = NULL;
            @try { [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting]; }
            @catch (NSException* exception) { NSLog(@"DICOM import scheduling failed: %@", exception); }
            processes->removeThread([NSThread currentThread]);
            --processes->active;
            --activeAssociations;
        }
    }
}
@end

static void HorosStartAssociationTask(QueryRetrieveAssociation* worker,
    T_ASC_Association* association, HorosAssociationProcesses& processes)
{
    HorosAssociationTask* task = [[HorosAssociationTask alloc] init];
    task->worker = worker; task->association = association; task->processes = &processes;
    ++processes.active; ++activeAssociations;
    NSThread* thread = nil;
    @try
    {
        thread = [[[NSThread alloc] initWithTarget:task selector:@selector(run) object:nil] autorelease];
        thread.name = NSLocalizedString(@"DICOM Services...", nil);
        thread.status = [NSString stringWithUTF8String:association->params->DULparams.callingPresentationAddress];
        thread.supportsCancel = YES;
        processes.addThread(thread);
        [[ThreadsManager defaultManager] addThreadAndStart:thread];
    }
    @catch (NSException* exception)
    {
        // UI registration can throw after NSThread already started. In that
        // case the worker still owns the association and its accounting.
        if (!thread.isExecuting && !thread.isFinished)
        {
            processes.removeThread(thread);
            ASC_dropAssociation(association); ASC_destroyAssociation(&association);
            delete worker;
            --processes.active; --activeAssociations;
        }
        @throw;
    }
    @finally { [task release]; }
}

@interface HorosDICOMForkMonitor : NSObject
+ (void)monitor:(NSDictionary*)parameters;
@end

@implementation HorosDICOMForkMonitor
+ (void)monitor:(NSDictionary*)parameters
{
    @autoreleasepool
    {
        const pid_t pid = [parameters[@"pid"] intValue];
        auto* processes = static_cast<HorosAssociationProcesses*>([parameters[@"processes"] pointerValue]);
        NSPersistentStoreCoordinator* coordinator = parameters[@"coordinator"];
        NSString* lockPath = [NSString stringWithFormat:@"/tmp/lock_process-%d", pid];
        NSString* statePath = [NSString stringWithFormat:@"/tmp/process_state-%d", pid];
        NSString* errorPath = [NSString stringWithFormat:@"/tmp/horos-dimse-error-%d", pid];
        [coordinator lock];
        BOOL locked = YES;
        const NSTimeInterval start = [NSDate timeIntervalSinceReferenceDate];
        @try
        {
            for (;;)
            {
                int status = 0;
                const pid_t result = waitpid(pid, &status, WNOHANG);
                if (result == pid || (result < 0 && errno == ECHILD)) break;
                if (result < 0 && errno != EINTR) break;
                const NSTimeInterval elapsed = [NSDate timeIntervalSinceReferenceDate] - start;
                if (locked && (elapsed >= 40 || (elapsed >= 0.6 &&
                    ![[NSFileManager defaultManager] fileExistsAtPath:lockPath])))
                { [coordinator unlock]; locked = NO; }
                NSString* state = [NSString stringWithContentsOfFile:statePath encoding:NSUTF8StringEncoding error:NULL];
                if (state.length) [NSThread currentThread].status = state;
                if (processes->stopping || [NSThread currentThread].isCancelled || HorosDICOMGlobalAbortRequested())
                    kill(pid, SIGTERM);
                [NSThread sleepForTimeInterval:0.1];
            }
            NSString* error = [NSString stringWithContentsOfFile:errorPath encoding:NSUTF8StringEncoding error:NULL];
            if (error.length && !processes->stopping && ![NSThread currentThread].isCancelled)
                [[AppController sharedAppController] performSelectorOnMainThread:@selector(displayListenerError:)
                    withObject:error waitUntilDone:NO];
        }
        @finally
        {
            if (locked) [coordinator unlock];
            for (NSString* path in @[lockPath, statePath, errorPath])
                [[NSFileManager defaultManager] removeItemAtPath:path error:NULL];
            processes->finishProcess(pid);
            @try { [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting]; }
            @catch (NSException* exception) { NSLog(@"DICOM import scheduling failed: %@", exception); }
            processes->removeThread([NSThread currentThread]);
            --processes->active; --activeAssociations;
        }
    }
}
@end

static void HorosStartForkMonitor(pid_t pid, NSPersistentStoreCoordinator* coordinator,
    NSString* peer, HorosAssociationProcesses& processes)
{
    ++processes.active; ++activeAssociations;
    NSThread* thread = nil;
    @try
    {
        thread = [[[NSThread alloc] initWithTarget:[HorosDICOMForkMonitor class]
            selector:@selector(monitor:) object:@{@"pid":@(pid), @"coordinator":coordinator,
            @"processes":[NSValue valueWithPointer:&processes]}] autorelease];
        thread.name = NSLocalizedString(@"DICOM Services...", nil);
        thread.status = peer;
        thread.supportsCancel = YES;
        processes.addThread(thread);
        [[ThreadsManager defaultManager] addThreadAndStart:thread];
    }
    @catch (NSException* exception)
    {
        if (!thread.isExecuting && !thread.isFinished)
        {
            // No monitor can reap this child. It has not been handed to another
            // owner, so close only this association's process and accounting.
            kill(pid, SIGKILL);
            while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
            processes.finishProcess(pid);
            processes.removeThread(thread);
            --processes.active; --activeAssociations;
        }
        @throw;
    }
}

@implementation ContextCleaner
+ (void)waitForHandledAssociations
{
    while (activeAssociations.load()) [NSThread sleepForTimeInterval:0.05];
}
@end

OFCondition HorosStoreSCP(T_ASC_Association* association, T_DIMSE_C_StoreRQ& request,
    T_ASC_PresentationContextID id, DcmQueryRetrieveDatabaseHandle& database,
    const DcmQueryRetrieveOptions& options)
{
        DcmFileFormat file;
        DcmQueryRetrieveStoreContext context(database, options, STATUS_Success, &file, options.correctUIDPadding_);
        char path[MAXPATHLEN + 1] = {};
        if (!dcmIsaStorageSOPClassUID(request.AffectedSOPClassUID))
            context.setStatus(STATUS_STORE_Refused_SOPClassNotSupported);
        else if (!options.ignoreStoreData_ && database.makeNewStoreFileName(request.AffectedSOPClassUID,
            request.AffectedSOPInstanceUID, path, sizeof(path)).bad())
            context.setStatus(STATUS_STORE_Refused_OutOfResources);
        if (!path[0] || context.getStatus() != STATUS_Success)
            OFStandard::strlcpy(path, NULL_DEVICE_NAME, sizeof(path));

        HorosDICOMFileLock lock(path, true);
        if (!lock.valid())
        {
            context.setStatus(STATUS_STORE_Refused_OutOfResources);
            OFStandard::strlcpy(path, NULL_DEVICE_NAME, sizeof(path));
        }
        context.setFileName(path);
        NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
        if ([defaults boolForKey:@"putSrcAETitleInSourceApplicationEntityTitle"])
            file.getMetaInfo()->putAndInsertString(DCM_SourceApplicationEntityTitle,
                association->params->DULparams.callingAPTitle);
        if ([defaults boolForKey:@"putDstAETitleInPrivateInformationCreatorUID"])
            file.getMetaInfo()->putAndInsertString(DCM_PrivateInformationCreatorUID,
                association->params->DULparams.calledAPTitle);
        DcmDataset* dataset = file.getDataset();
        HorosStoreCallbackContext callback;
        callback.store = &context;
        callback.association = association;
        // Even a refused store must consume the incoming dataset before replying.
        OFCondition result = DIMSE_storeProvider(association, id, &request,
            options.bitPreserving_ ? path : NULL, options.useMetaheader_,
            options.bitPreserving_ ? NULL : &dataset, storeCallback, &callback,
            options.blockMode_, options.dimse_timeout_);
        if (!options.ignoreStoreData_ && (result.bad() || context.getStatus() != STATUS_Success))
        {
            if (!callback.preserveCompletedFile && strcmp(path, NULL_DEVICE_NAME) != 0)
                OFStandard::deleteFile(path);
            database.pruneInvalidRecords();
        }
        return result;
    }

HorosQueryRetrieveServer::HorosQueryRetrieveServer(const DcmQueryRetrieveConfig& config,
    const DcmQueryRetrieveOptions& options, const DcmQueryRetrieveDatabaseHandleFactory& factory,
    const DcmAssociationConfiguration& associations, OFBool secureConnection)
    : config_(config), options_(options), factory_(factory), associations_(associations),
      secureConnection_(secureConnection), processes_(new HorosAssociationProcesses) {}

HorosQueryRetrieveServer::~HorosQueryRetrieveServer()
{
    processes_->requestStop();
    while (processes_->active.load()) [NSThread sleepForTimeInterval:0.05];
}

OFCondition HorosQueryRetrieveServer::waitForAssociation(T_ASC_Network* network)
{
    if (!ASC_associationWaiting(network, 1)) return EC_Normal;

    T_ASC_Association* association = NULL;
    void *pdu = NULL;
    unsigned long pduSize = 0;
    OFCondition result = ASC_receiveAssociation(network, &association, options_.maxPDU_, &pdu, &pduSize,
        secureConnection_, DUL_BLOCK, options_.acse_timeout_);
    if (result.good()) result = HorosDIMSEValidateAssociationPDU(pdu, pduSize);
    free(pdu);
    if (result.bad())
    {
        if (association)
        {
            ASC_dropAssociation(association);
            ASC_destroyAssociation(&association);
        }
        return result;
    }
    QueryRetrieveAssociation* worker = new QueryRetrieveAssociation(association, config_, options_, factory_,
        associations_, *processes_, secureConnection_);
    if (!options_.singleProcess_)
    {
        result = worker->run(association);
        if (result.good()) result = worker->lastFailure;
        delete worker;
        return result;
    }
    const NSInteger configured = [[NSUserDefaults standardUserDefaults]
        integerForKey:@"maximumNumberOfConcurrentDICOMAssociations"];
    const unsigned limit = configured > 0 ? (unsigned)configured : 8;
    if (processes_->active.load() >= limit || processes_->stopping)
    {
        T_ASC_RejectParameters reject = {ASC_RESULT_REJECTEDTRANSIENT,
            ASC_SOURCE_SERVICEPROVIDER_PRESENTATION_RELATED, ASC_REASON_SP_PRES_LOCALLIMITEXCEEDED};
        ASC_rejectAssociation(association, &reject);
        ASC_dropAssociation(association);
        ASC_destroyAssociation(&association);
        delete worker;
        return EC_Normal;
    }
    HorosStartAssociationTask(worker, association, *processes_);
    return EC_Normal;
}
