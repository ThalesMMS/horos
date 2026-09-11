#import "HorosDIMSEClient.h"
#import <Foundation/Foundation.h>
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
**  Copyright (C) 1993/1994, OFFIS, Oldenburg University and CERIUM
**  
**  This software and supporting documentation were
**  developed by 
**  
**    Institut OFFIS
**    Bereich Kommunikationssysteme
**    Westerstr. 10-12
**    26121 Oldenburg, Germany
**    
**    Fachbereich Informatik
**    Abteilung Prozessinformatik
**    Carl von Ossietzky Universitaet Oldenburg 
**    Ammerlaender Heerstr. 114-118
**    26111 Oldenburg, Germany
**    
**    CERIUM
**    Laboratoire SIM
**    Faculte de Medecine
**    2 Avenue du Pr. Leon Bernard
**    35043 Rennes Cedex, France
**  
**  for CEN/TC251/WG4 as a contribution to the Radiological 
**  Society of North America (RSNA) 1993 Digital Imaging and 
**  Communications in Medicine (DICOM) Demonstration.
**  
**  THIS SOFTWARE IS MADE AVAILABLE, AS IS, AND NEITHER OFFIS,
**  OLDENBURG UNIVERSITY NOR CERIUM MAKE ANY WARRANTY REGARDING 
**  THE SOFTWARE, ITS PERFORMANCE, ITS MERCHANTABILITY OR 
**  FITNESS FOR ANY PARTICULAR USE, FREEDOM FROM ANY COMPUTER 
**  DISEASES OR ITS CONFORMITY TO ANY SPECIFICATION.  THE 
**  ENTIRE RISK AS TO QUALITY AND PERFORMANCE OF THE SOFTWARE   
**  IS WITH THE USER. 
**  
**  Copyright of the software and supporting documentation
**  is, unless otherwise stated, jointly owned by OFFIS,
**  Oldenburg University and CERIUM and free access is hereby
**  granted as a license to use this software, copy this
**  software and prepare derivative works based upon this
**  software. However, any distribution of this software
**  source code or supporting documentation or derivative
**  works (source code and supporting documentation) must
**  include the three paragraphs of this copyright notice. 
** 
*/
/*
**
** Author: Andrew Hewett                Created: 03-06-93
** 
** Module: dimmove
**
** Purpose: 
**      This file contains the routines which help with
**      query/retrieve services using the C-MOVE operation.
**
**      Module Prefix: DIMSE_
**
** Last Update:         $Author: lpysher $
** Update Date:         $Date: 2006/03/01 20:15:50 $
** Source File:         $Source: /cvsroot/osirix/osirix/Binaries/dcmtk-source/dcmnet/dimmove.cc,v $
** CVS/RCS Revision:    $Revision: 1.1 $
** Status:              $State: Exp $
**
** CVS/RCS Log at end of file
*/

/* 
** Include Files
*/

#include "HorosDCMTKCompatibility.h"
#include <dcmtk/config/osconfig.h>    /* make sure OS specific configuration is included first */

#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <dcmtk/ofstd/ofstdinc.h>
#include <dcmtk/ofstd/oftimer.h>

#ifdef HAVE_FCNTL_H
#include <fcntl.h>
#endif

#include <dcmtk/dcmnet/diutil.h>
#include <dcmtk/dcmnet/dimse.h>              /* always include the module header */
#include <dcmtk/dcmnet/cond.h>

/*
**
*/

static int
selectReadable(T_ASC_Association *assoc, 
    T_ASC_Network *net, T_ASC_Association *subAssoc,
    T_DIMSE_BlockingMode blockMode, int timeout)
{
    T_ASC_Association *assocList[2];
    int assocCount = 0;
    
    if (net != NULL && subAssoc == NULL) {
        if (ASC_associationWaiting(net, 0)) {
            /* association request waiting on network */
            return 2;
        }
    } 
    assocList[0] = assoc; 
    assocCount = 1;
    assocList[1] = subAssoc;
    if (subAssoc != NULL) assocCount++;
    // Poll even a silent peer so local cancellation does not need a response.
    timeout = 1;
    if (!ASC_selectReadableAssociation(assocList, assocCount, timeout)) {
        /* none readable */
        return 0;
    }
    if (assocList[0] != NULL) {
        /* main association readable */
        return 1;
    }
    if (assocList[1] != NULL) {
        /* sub association readable */
        return 2;
    }
    /* should not be reached */
    return 0;
}

OFCondition
HorosDIMSEMoveUser(
               /* in */
               T_ASC_Association *assoc,
               T_ASC_PresentationContextID presID,
               T_DIMSE_C_MoveRQ *request,
               DcmDataset *requestIdentifiers,
               DIMSE_MoveUserCallback callback, void *callbackData,
               /* blocking info for response */
               T_DIMSE_BlockingMode blockMode, int timeout,
               /* sub-operation provider callback */
               T_ASC_Network *net,
               DIMSE_SubOpProviderCallback subOpCallback, void *subOpCallbackData,
               /* out */
               T_DIMSE_C_MoveRSP *response, DcmDataset **statusDetail,
               DcmDataset **rspIds,
               OFBool ignorePendingDatasets)
{
    T_DIMSE_Message req, rsp;
    DIC_US msgId;
    int responseCount = 0;
    T_ASC_Association *subAssoc = NULL;
    DIC_US status = STATUS_Pending;
    OFBool firstLoop = OFTrue;
    
    if (requestIdentifiers == NULL) return DIMSE_NULLKEY;
    
    bzero((char*)&req, sizeof(req));
    bzero((char*)&rsp, sizeof(rsp));
    
    req.CommandField = DIMSE_C_MOVE_RQ;
    request->DataSetType = DIMSE_DATASET_PRESENT;
    req.msg.CMoveRQ = *request;
    
    msgId = request->MessageID;
    
    OFCondition cond = DIMSE_sendMessageUsingMemoryData(assoc, presID, &req, NULL, requestIdentifiers, NULL, NULL);
    if (cond != EC_Normal) {
        return cond;
    }
    
    /* receive responses */
    
    OFTimer timer;
    BOOL cancelSent = NO;
    NSTimeInterval cancelDeadline = 0;
    const T_ASC_PresentationContextID movePresentationContext = presID;
    while (cond == EC_Normal && status == STATUS_Pending) {
        const int readable = selectReadable(assoc, net, subAssoc, blockMode, timeout);
        // Observe cancellation that arrived during the readiness wait.
        if (NSThread.currentThread.isCancelled && !cancelSent) {
            cond = DIMSE_sendCancelRequest(assoc, movePresentationContext, msgId);
            if (cond.bad()) return cond;
            cancelSent = YES;
            cancelDeadline = NSProcessInfo.processInfo.systemUptime + 5.0;
        }
        if (cancelSent && NSProcessInfo.processInfo.systemUptime >= cancelDeadline)
            return makeDcmnetCondition(DIMSEC_RECEIVEFAILED, OF_error, "C-MOVE cancellation response timed out");
        
        /* if user wants, multiplex between net/subAssoc
         * and move responses over main assoc.
         */
        switch (readable) {
            case 0:
                /* none are readable, timeout */
                if (cancelSent || (blockMode == DIMSE_BLOCKING) || firstLoop) {
                    firstLoop = OFFalse;
                } else if ((blockMode == DIMSE_NONBLOCKING) && (timer.getDiff() > timeout)) {
                    ofConsole.lockCerr() << "timeout of " << timeout << " seconds elapsed while waiting for C-MOVE Responses" << endl;
                    ofConsole.unlockCerr();
                    return DIMSE_NODATAAVAILABLE;
                }
                continue;    /* continue with main loop */
            case 1:
                /* main association readable */
                firstLoop = OFFalse;
                break;
            case 2:
                /* net/subAssoc readable */
                if (subOpCallback) {
                    subOpCallback(subOpCallbackData, net, &subAssoc);
                }
                firstLoop = OFFalse;
                continue;    /* continue with main loop */
        }
        
        bzero((char*)&rsp, sizeof(rsp));
        
        cond = DIMSE_receiveCommand(assoc, cancelSent ? DIMSE_NONBLOCKING : blockMode, cancelSent ? 1 : timeout, &presID, &rsp, statusDetail);
        if (cond != EC_Normal) {
            return cond;
        }
        if (rsp.CommandField != DIMSE_C_MOVE_RSP) {
            char buf1[256];
            sprintf(buf1, "DIMSE: Unexpected Response Command Field: 0x%x", (unsigned)rsp.CommandField);
            return makeDcmnetCondition(DIMSEC_UNEXPECTEDRESPONSE, OF_error, buf1);
        }
        
        *response = rsp.msg.CMoveRSP;
        
        if (response->MessageIDBeingRespondedTo != msgId) {
            char buf2[256];
            sprintf(buf2, "DIMSE: Unexpected Response MsgId: %d (expected: %d)", response->MessageIDBeingRespondedTo, msgId);
            return makeDcmnetCondition(DIMSEC_UNEXPECTEDRESPONSE, OF_error, buf2);
        }
        
        status = response->DimseStatus;
        responseCount++;
        
        switch (status) {
            case STATUS_Pending:
                if (*statusDetail != NULL) {
                    ofConsole.lockCerr() << "moveUser: Pending with statusDetail, ignoring detail" << endl;
                    ofConsole.unlockCerr();
                    delete *statusDetail;
                    *statusDetail = NULL;
                }
                if (response->DataSetType != DIMSE_DATASET_NULL) {
                    ofConsole.lockCerr() << "moveUser: Status Pending, but DataSetType!=NULL" << endl;
                    ofConsole.unlockCerr();
                    if (! ignorePendingDatasets) {
                        // Some systems send an (illegal) dataset following C-MOVE-RSP messages
                        // with pending status, which is a protocol violation, but we need to
                        // handle this nevertheless. The MV300 has been reported to exhibit
                        // this behavior.
                        ofConsole.lockCerr() << "Reading but ignoring response identifier set" << endl;
                        ofConsole.unlockCerr();
                        DcmDataset *tempset = NULL;
                        cond = DIMSE_receiveDataSetInMemory(assoc, blockMode, timeout, &presID, &tempset, NULL, NULL);
                        delete tempset;
                        if (cond != EC_Normal) {
                            return cond;
                        }
                    } else {
                        // The alternative is to assume that the command set is wrong
                        // and not to read a dataset from the network association.
                        ofConsole.lockCerr() << "Assuming NO response identifiers are present" << endl;
                        ofConsole.unlockCerr();
                    }
                }
                
                /* execute callback */
                if (callback) {
                    callback(callbackData, request, responseCount, response);
                }
                break;
            default:
                if (response->DataSetType != DIMSE_DATASET_NULL) {
                    cond = DIMSE_receiveDataSetInMemory(assoc, blockMode, timeout, &presID, rspIds, NULL, NULL);
                    if (cond != EC_Normal) {
                        return cond;
                    }
                }
                break;
        }
        /* reset the timeout timer */
        timer.reset();
    }
    
    /* do remaining sub-association work, we may receive a non-pending
     * status before the sub-association has cleaned up.
     */
    while (subAssoc != NULL) {
        if (subOpCallback) {
            subOpCallback(subOpCallbackData, net, &subAssoc);
        }
    }
    
    return cond;
}
