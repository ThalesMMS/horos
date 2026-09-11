#import "HorosDIMSEClient.h"
/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation, Êversion 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE. ÊSee the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos. ÊIf not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program: Ê OsiriX
 ÊCopyright (c) OsiriX Team
 ÊAll rights reserved.
 ÊDistributed under GNU - LGPL
 Ê
 ÊSee http://www.osirix-viewer.com/copyright.html for details.
 Ê Ê This software is distributed WITHOUT ANY WARRANTY; without even
 Ê Ê the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
 Ê Ê PURPOSE.
 ============================================================================*/
/*
**
** Author: Andrew Hewett                Created: 1998.09.03
** 
** Module: dimget
**
** Purpose: 
**      This file contains the routines which help with
**      query/retrieve services using the C-GET operation.
**
**      Module Prefix: DIMSE_
**
** Last Update:         $Author: lpysher $
** Update Date:         $Date: 2006/03/01 20:15:50 $
** Source File:         $Source: /cvsroot/osirix/osirix/Binaries/dcmtk-source/dcmnet/dimget.cc,v $
** CVS/RCS Revision:    $Revision: 1.1 $
** Status:              $State: Exp $
**
** CVS/RCS Log at end of file
*/

/* 
** Include Files
*/

#import "DicomDatabase.h"
#include "HorosDCMTKCompatibility.h"
#include <dcmtk/config/osconfig.h>    /* make sure OS specific configuration is included first */

#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <dcmtk/ofstd/ofstdinc.h>

#ifdef HAVE_FCNTL_H
#include <fcntl.h>
#endif

#include <dcmtk/dcmnet/diutil.h>
#include <dcmtk/dcmnet/dimse.h>              /* always include the module header */
#include <dcmtk/dcmnet/cond.h>

#include "dcmqrdbq.h"
#include <dcmtk/dcmqrdb/dcmqrcnf.h>
#include <dcmtk/dcmqrdb/dcmqropt.h>
#include <dcmtk/dcmqrdb/dcmqrsrv.h>

/*
**
*/

static int
selectReadable(T_ASC_Association *assoc, T_DIMSE_BlockingMode blockMode, int timeout)
{
    // C-GET responses and C-STORE suboperations share this association. The
    // listener must not steal readiness or create a busy loop for this request.
    T_ASC_Association *associations[] = {assoc};
    const int pollSeconds = (blockMode == DIMSE_NONBLOCKING && timeout <= 0) ? 0 : 1;
    return ASC_selectReadableAssociation(associations, 1, pollSeconds) && associations[0] ? 1 : 0;
}

extern BOOL forkedProcess;

OFCondition
HorosDIMSEGetUser(
        /* in */
        T_ASC_Association *assoc, 
        T_ASC_PresentationContextID presID,
        T_DIMSE_C_GetRQ *request,
        DcmDataset *requestIdentifiers,
        DIMSE_GetUserCallback callback, void *callbackData,
        /* blocking info for response */
        T_DIMSE_BlockingMode blockMode, int timeout,
        /* sub-operation provider callback */
        T_ASC_Network *net,
        DIMSE_SubOpProviderCallback subOpCallback, void *subOpCallbackData,
        /* out */
        T_DIMSE_C_GetRSP *response, DcmDataset **statusDetail,
        DcmDataset **rspIds)
{
    T_DIMSE_Message req, rsp;
    DIC_US msgId = 0;
    int responseCount = 0;
    DIC_US status = STATUS_Pending;

    if (requestIdentifiers == NULL) return DIMSE_NULLKEY;

    bzero((char*)&req, sizeof(req));
    bzero((char*)&rsp, sizeof(rsp));
    
    req.CommandField = DIMSE_C_GET_RQ;
    request->DataSetType = DIMSE_DATASET_PRESENT;
    req.msg.CGetRQ = *request;

    msgId = request->MessageID;

    OFCondition cond = DIMSE_sendMessageUsingMemoryData(assoc, presID, &req,
                                          NULL, requestIdentifiers, 
                                          NULL, NULL);
    if (cond != EC_Normal) {
        return cond;
    }

    /* receive responses */
	DcmQueryRetrieveOsiriXDatabaseHandleFactory factory;
	DcmQueryRetrieveDatabaseHandle *dbHandle = factory.createDBHandle( assoc->params->DULparams.calledAPTitle, assoc->params->DULparams.calledAPTitle, cond);
	
    if (!dbHandle || cond.bad()) { delete dbHandle; return cond.bad() ? cond : EC_IllegalCall; }
    // Receive on this C-GET association with request-owned storage state. No
    // listener, listening socket or global plaintext/TLS SCP is needed.
    DcmQueryRetrieveConfig storageConfig;
    DcmQueryRetrieveOptions storageOptions;
    storageOptions.blockMode_ = blockMode;
    storageOptions.dimse_timeout_ = timeout;
    storageOptions.singleProcess_ = OFTrue;
    storageOptions.groupLength_ = EGL_withoutGL;
    @try
    {
    int index = 0;
    const T_ASC_PresentationContextID getPresentationContext = presID;
    BOOL cancelSent = NO;
    NSTimeInterval cancelDeadline = 0;
    NSTimeInterval responseDeadline = NSProcessInfo.processInfo.systemUptime + MAX(0, timeout);
    
    while (cond == EC_Normal && status == STATUS_Pending) {
        const int readable = selectReadable(assoc, blockMode, timeout);
        // Cancellation may arrive while waiting for the next command. Send it
        // before accepting another storage sub-operation on this association.
        if ([NSThread currentThread].isCancelled && !cancelSent)
        {
            cond = DIMSE_sendCancelRequest(assoc, getPresentationContext, msgId);
            if (cond.bad()) return cond;
            cancelSent = YES;
            cancelDeadline = NSProcessInfo.processInfo.systemUptime + 5.0;
        }
        if (cancelSent && NSProcessInfo.processInfo.systemUptime >= cancelDeadline)
            return makeDcmnetCondition(DIMSEC_RECEIVEFAILED, OF_error, "C-GET cancellation response timed out");
		
        if (!readable)
        {
            if (cancelSent || blockMode == DIMSE_BLOCKING ||
                NSProcessInfo.processInfo.systemUptime < responseDeadline)
                continue;
            return DIMSE_NODATAAVAILABLE;
        }

        bzero((char*)&rsp, sizeof(rsp));

        cond = DIMSE_receiveCommand(assoc, cancelSent ? DIMSE_NONBLOCKING : blockMode, cancelSent ? 1 : timeout, &presID,
                &rsp, statusDetail);
        if (cond != EC_Normal)
		{
            return cond;
        }
		
        responseDeadline = NSProcessInfo.processInfo.systemUptime + MAX(0, timeout);
		switch (rsp.CommandField)
		{
			case DIMSE_C_GET_RSP:
				*response = rsp.msg.CGetRSP;
			
				if (response->MessageIDBeingRespondedTo != msgId)
				{
				  char buf2[256];
				  sprintf(buf2, "DIMSE: Unexpected Response MsgId: %d (expected: %d)", response->MessageIDBeingRespondedTo, msgId);
				  return makeDcmnetCondition(DIMSEC_UNEXPECTEDRESPONSE, OF_error, buf2);
				}
				
				status = response->DimseStatus;
				responseCount++;

				switch (status)
				{
				case STATUS_Pending:
					if (*statusDetail != NULL)
					{
						HorosDIMSEWarning(assoc, 
							"getUser: Pending with statusDetail, ignoring detail");
						delete *statusDetail;
						*statusDetail = NULL;
					}
					if (response->DataSetType != DIMSE_DATASET_NULL)
					{
						HorosDIMSEWarning(assoc, 
							"getUser: Status Pending, but DataSetType!=NULL");
						HorosDIMSEWarning(assoc, 
							"  Assuming NO response identifiers are present");
					}

					/* execute callback */
					if (callback) {
						callback(callbackData, request, responseCount, response);
					}
					break;
				default:
					if (response->DataSetType != DIMSE_DATASET_NULL)
					{
						cond = DIMSE_receiveDataSetInMemory(assoc, blockMode, timeout, &presID, rspIds, NULL, NULL);
						if (cond != EC_Normal)
						{
							return cond;
						}
					}
					break;
				}
			break;
			
			case DIMSE_C_STORE_RQ:
				 cond = HorosStoreSCP(assoc, rsp.msg.CStoreRQ, presID, *dbHandle, storageOptions);
                
                if( forkedProcess == NO && index == 0)
                    [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
                
                index++;
			break;
			
			default:
			{
				char buf1[256];
				sprintf(buf1, "DIMSE: Unexpected Response Command Field: 0x%x", (unsigned)rsp.CommandField);
				return makeDcmnetCondition(DIMSEC_UNEXPECTEDRESPONSE, OF_error, buf1);
			}
			
		}
    }

    if( forkedProcess == NO)
        [[DicomDatabase activeLocalDatabase] initiateImportFilesFromIncomingDirUnlessAlreadyImporting];
    
    return cond;
    }
    @finally
    {
        delete dbHandle;
    }
}
