#include "HorosDIMSEAssociation.h"
#include "HorosDICOMStoreSource.h"
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
 *
 *  Copyright (C) 1993-2005, OFFIS
 *
 *  This software and supporting documentation were developed by
 *
 *    Kuratorium OFFIS e.V.
 *    Healthcare Information and Communication Systems
 *    Escherweg 2
 *    D-26121 Oldenburg, Germany
 *
 *  THIS SOFTWARE IS MADE AVAILABLE,  AS IS,  AND OFFIS MAKES NO  WARRANTY
 *  REGARDING  THE  SOFTWARE,  ITS  PERFORMANCE,  ITS  MERCHANTABILITY  OR
 *  FITNESS FOR ANY PARTICULAR USE, FREEDOM FROM ANY COMPUTER DISEASES  OR
 *  ITS CONFORMITY TO ANY SPECIFICATION. THE ENTIRE RISK AS TO QUALITY AND
 *  PERFORMANCE OF THE SOFTWARE IS WITH THE USER.
 *
 *  Module:  dcmqrdb
 *
 *  Author:  Marco Eichelberg
 *
 *  Purpose: class HorosDICOMMoveContext
 *
 *  Last Update:      $Author: lpysher $
 *  Update Date:      $Date: 2006/03/01 20:16:07 $
 *  Source File:      $Source: /cvsroot/osirix/osirix/Binaries/dcmtk-source/dcmqrdb/dcmqrcbm.cc,v $
 *  CVS/RCS Revision: $Revision: 1.1 $
 *  Status:           $State: Exp $
 *
 *  CVS/RCS Log at end of file
 *
 */

#import <Cocoa/Cocoa.h>
#import "DCMNetServiceDelegate.h"
#import "SendController.h"
#import "BrowserController.h"
#import "DCMObject.h"
#import "DCM.h"
#import "DCMTransferSyntax.h"

#include "HorosDCMTKCompatibility.h"
#include <dcmtk/config/osconfig.h>    /* make sure OS specific configuration is included first */
#include "HorosDICOMMoveContext.h"

#include <dcmtk/dcmqrdb/dcmqrcnf.h>
#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmqrdb/dcmqropt.h>
#include <dcmtk/dcmnet/diutil.h>
#include <dcmtk/dcmdata/dcfilefo.h>
#include <dcmtk/dcmqrdb/dcmqrdbs.h>
#include <dcmtk/dcmqrdb/dcmqrdbi.h>

#include <dcmtk/ofstd/ofstring.h>
#include <dcmtk/dcmnet/dimse.h>
#include <dcmtk/dcmnet/diutil.h>
#include <dcmtk/dcmdata/dcdatset.h>
#include <dcmtk/dcmdata/dcmetinf.h>
#include <dcmtk/dcmdata/dcfilefo.h>
#include "HorosDCMTKCompatibility.h"
#include <dcmtk/dcmdata/dcuid.h>
#include <dcmtk/dcmdata/dcdict.h>
#include <dcmtk/dcmdata/dcdeftag.h>

#include <dcmtk/ofstd/ofconapp.h>
#include <dcmtk/dcmdata/dcuid.h>     /* for dcmtk version name */
#include <dcmtk/dcmnet/dicom.h>     /* for DICOM_APPLICATION_REQUESTOR */
#include <dcmtk/dcmdata/dcostrmz.h>  /* for dcmZlibCompressionLevel */
#include <dcmtk/dcmnet/dcasccfg.h>  /* for class DcmAssociationConfiguration */
#include <dcmtk/dcmnet/dcasccff.h>  /* for class DcmAssociationConfigurationFile */


#include <dcmtk/dcmjpeg/djdecode.h>  /* for dcmjpeg decoders */
#include <dcmtk/dcmjpeg/djencode.h>  /* for dcmjpeg encoders */
#include <dcmtk/dcmdata/dcrledrg.h>  /* for DcmRLEDecoderRegistration */
#include <dcmtk/dcmdata/dcrleerg.h>  /* for DcmRLEEncoderRegistration */
#include <dcmtk/dcmjpeg/djrploss.h>
#include <dcmtk/dcmjpeg/djrplol.h>
#include <dcmtk/dcmdata/dcpixel.h>
#include <dcmtk/dcmdata/dcrlerp.h>

BEGIN_EXTERN_C
#ifdef HAVE_FCNTL_H
#include <fcntl.h>       /* needed on Solaris for O_RDONLY */
#endif
END_EXTERN_C

extern char currentDestinationMoveAET[ 60];


static void moveSubOpProgressCallback(void *callbackData, 
    T_DIMSE_StoreProgress *progress,
    T_DIMSE_C_StoreRQ * /*req*/)
{
  HorosDICOMMoveContext *context = OFstatic_cast(HorosDICOMMoveContext *, callbackData);
  if (context->isVerbose())
  {
    switch (progress->state)
    {
      case DIMSE_StoreBegin:
        printf("XMIT:");
        break;
      case DIMSE_StoreEnd:
        printf("\n");
        break;
      default:
        putchar('.');
        break;
    }
    fflush(stdout);
  }
}

OFBool HorosDICOMMoveContext::isVerbose() const 
{ 
  return DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL) ? OFTrue : OFFalse; 
}

void HorosDICOMMoveContext::callbackHandler(
	/* in */ 
	OFBool cancelled, 
	T_DIMSE_C_MoveRQ *request, 
	DcmDataset *requestIdentifiers, 
	int responseCount,
	/* out */
	T_DIMSE_C_MoveRSP *response,
	 DcmDataset **stDetail,	
	DcmDataset **responseIdentifiers)
{
//	printf("HorosDICOMMoveContext::callbackHandler\n");
    OFCondition cond = EC_Normal;
    OFCondition dbcond = EC_Normal;
    DcmQueryRetrieveDatabaseStatus dbStatus(priorStatus);
    
    if (responseCount == 1) {
        /* start the database search */
	if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL)) {
	    printf("Move SCP Request Identifiers:\n");
	    requestIdentifiers->print(COUT);
        }
		
		if (request->MoveDestination[0])
			strcpy( currentDestinationMoveAET, request->MoveDestination);
		else
			strcpy( currentDestinationMoveAET, "");
			
        dbcond = dbHandle.startMoveRequest(
	    request->AffectedSOPClassUID, requestIdentifiers, &dbStatus);
        if (dbcond.bad()) {
	    HorosDIMSEError("moveSCP: Database: startMoveRequest Failed (%s):",
		DU_cmoveStatusString(dbStatus.status()));
        }

        if (dbStatus.status() == STATUS_Pending) {
            /* If we are going to be performing sub-operations, build
             * a new association to the move destination.
             */
	    cond = buildSubAssociation(request);
	    if (cond == QR_EC_InvalidPeer) {
	        dbStatus.setStatus(STATUS_MOVE_Failed_MoveDestinationUnknown);
	    } else if (cond.bad()) {
	        /* failed to build association, must fail move */
		failAllSubOperations(&dbStatus);
	    }
        }
    }
    
    /* only cancel if we have pending status */
    if (cancelled && dbStatus.status() == STATUS_Pending) {
	dbHandle.cancelMoveRequest(&dbStatus);
    }

    if (dbStatus.status() == STATUS_Pending) {
        moveNextImage(&dbStatus);
    }

    if (dbStatus.status() != STATUS_Pending) {
	/*
	 * Tear down sub-association (if it exists).
	 */
	closeSubAssociation();

	/*
	 * Need to adjust the final status if any sub-operations failed or
	 * had warnings 
	 */
	if (dbStatus.status() == STATUS_Success && (nFailed > 0 || nWarning > 0)) {
	    dbStatus.setStatus(STATUS_MOVE_Warning_SubOperationsCompleteOneOrMoreFailures);
	}
        /*
         * if all the sub-operations failed then we need to generate a failed or refused status.
         * cf. DICOM part 4, C.4.2.3.1
         * we choose to generate a "Refused - Out of Resources - Unable to perform suboperations" status.
         */
        if (dbStatus.status() == STATUS_MOVE_Warning_SubOperationsCompleteOneOrMoreFailures &&
            (nFailed > 0) && ((nCompleted + nWarning) == 0)) {
	    dbStatus.setStatus(STATUS_MOVE_Refused_OutOfResourcesSubOperations);
	}
    }
    
    if (dbStatus.status() != STATUS_Success && 
        dbStatus.status() != STATUS_Pending) {
	/* 
	 * May only include response identifiers if not Success 
	 * and not Pending 
	 */
	buildFailedInstanceList(responseIdentifiers);
    }

    /* set response status */
    response->DimseStatus = dbStatus.status();
    response->NumberOfRemainingSubOperations = nRemaining;
    response->NumberOfCompletedSubOperations = nCompleted;
    response->NumberOfFailedSubOperations = nFailed;
    response->NumberOfWarningSubOperations = nWarning;
    *stDetail = dbStatus.extractStatusDetail();

    if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL)) {
        printf("Move SCP Response %d [status: %s]\n", responseCount,
	    DU_cmoveStatusString(dbStatus.status()));
    }
    if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL)) {
        DIMSE_printCMoveRSP(stdout, response);
        if (DICOM_PENDING_STATUS(dbStatus.status()) && (*responseIdentifiers != NULL)) {
            printf("Move SCP Response Identifiers:\n");
            (*responseIdentifiers)->print(COUT);
        }
        if (*stDetail) {
            printf("Status detail:\n");
            (*stDetail)->print(COUT);
        }
    }    
}

void HorosDICOMMoveContext::addFailedUIDInstance(const char *sopInstance)
{
    int len;

    if (failedUIDs == NULL) {
	if ((failedUIDs = (char*)malloc(DIC_UI_LEN+1)) == NULL) {
	    HorosDIMSEError("malloc failure: addFailedUIDInstance");
	    return;
	}
	strcpy(failedUIDs, sopInstance);
    } else {
	len = strlen(failedUIDs);
	if ((failedUIDs = (char*)realloc(failedUIDs, 
	    (len+strlen(sopInstance)+2))) == NULL) {
	    HorosDIMSEError("realloc failure: addFailedUIDInstance");
	    return;
	}
	/* tag sopInstance onto end of old with '\' between */
	strcat(failedUIDs, "\\");
	strcat(failedUIDs, sopInstance);
    }
}

OFCondition HorosDICOMMoveContext::performMoveSubOp(DIC_UI sopClass, DIC_UI sopInstance, char *fname)
{
    OFCondition cond = EC_Normal;
    T_DIMSE_C_StoreRQ req;
    T_DIMSE_C_StoreRSP rsp;
    DIC_US msgId;
    T_ASC_PresentationContextID presId;
    DcmDataset *stDetail = NULL;

    HorosDICOMStoreSource source(fname);
    cond = source.prepare(subAssoc, sopClass, fname, false);
    if (cond.bad())
    {
        ++nFailed;
        addFailedUIDInstance(sopInstance);
        return cond;
    }
    msgId = subAssoc->nextMsgID++;
    presId = source.presentationID;

    req.MessageID = msgId;
    strcpy(req.AffectedSOPClassUID, sopClass);
    strcpy(req.AffectedSOPInstanceUID, sopInstance);
    req.DataSetType = DIMSE_DATASET_PRESENT;
    req.Priority = priority;
    req.opts = (O_STORE_MOVEORIGINATORAETITLE | O_STORE_MOVEORIGINATORID);
    strcpy(req.MoveOriginatorApplicationEntityTitle, origAETitle);
    req.MoveOriginatorID = origMsgId;

    if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL)) {
	printf("Store SCU RQ: MsgID %d, (%s)\n", 
	    msgId, dcmSOPClassUIDToModality(sopClass));
    }

    cond = DIMSE_storeUser(subAssoc, presId, &req,
        source.datasetToSend ? NULL : fname, source.datasetToSend, moveSubOpProgressCallback, this, 
	options_.blockMode_, options_.dimse_timeout_, 
	&rsp, &stDetail);
	

	
    if (cond.good()) {
        if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL)) {
	    printf("Move SCP: Received Store SCU RSP [Status=%s]\n",
	        DU_cstoreStatusString(rsp.DimseStatus));
        }
	if (rsp.DimseStatus == STATUS_Success) {
	    /* everything ok */
	    nCompleted++;
	} else if ((rsp.DimseStatus & 0xf000) == 0xb000) {
	    /* a warning status message */
	    nWarning++;
	    HorosDIMSEError("Move SCP: Store Waring: Response Status: %s", 
		DU_cstoreStatusString(rsp.DimseStatus));
	} else {
	    nFailed++;
	    addFailedUIDInstance(sopInstance);
	    /* print a status message */
	    HorosDIMSEError("Move SCP: Store Failed: Response Status: %s", 
		DU_cstoreStatusString(rsp.DimseStatus));
	}
    } else {
	nFailed++;
	addFailedUIDInstance(sopInstance);
	HorosDIMSEError("Move SCP: storeSCU: Store Request Failed:");
	DimseCondition::dump(cond);
    }
    if (stDetail != NULL) {
        if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL)) {
	    printf("  Status Detail:\n");
	    stDetail->print(COUT);
	}
        delete stDetail;
    }
    return cond;
}

OFCondition HorosDICOMMoveContext::buildSubAssociation(T_DIMSE_C_MoveRQ *request)
{
    OFCondition cond = EC_Normal;
    DIC_NODENAME dstHostName;
    int dstPortNumber;
    DIC_NODENAME localHostName;
    T_ASC_Parameters *params;

    strcpy(dstAETitle, request->MoveDestination);

    /*
     * We must map the destination AE Title into a host name and port
     * address.  Further, we must make sure that the RSNA'93 demonstration
     * rules are observed regarding move destinations. 
     */

    DIC_AE aeTitle;
    aeTitle[0] = '\0';
    ASC_getAPTitles(origAssoc->params, origAETitle, sizeof(origAETitle), aeTitle, sizeof(aeTitle), NULL, 0);
    ourAETitle = aeTitle;

    ASC_getPresentationAddresses(origAssoc->params, origHostName, sizeof(origHostName), NULL, 0);
	
    if (!mapMoveDestination(origHostName, origAETitle, request->MoveDestination, dstHostName, &dstPortNumber))
	{
		return QR_EC_InvalidPeer;
    }

    if (cond.good())
	{
		cond = ASC_createAssociationParameters(&params, ASC_DEFAULTMAXPDU, options_.acse_timeout_);
		if (cond.bad())
		{
			HorosDIMSEError("moveSCP: Cannot create Association-params for sub-ops:");
			DimseCondition::dump(cond);
		}
    }
	
    if (cond.good())
	{
		gethostname(localHostName, sizeof(localHostName) - 1);
		cond = HorosDIMSESetPeerAddress(params, localHostName, dstHostName, dstPortNumber);
        if (cond.bad()) { ASC_destroyAssociationParameters(&params); return cond; }
		ASC_setAPTitles(params, ourAETitle.c_str(), dstAETitle,NULL);
	
		cond = addAllStoragePresentationContexts(params);
		if (cond.bad())
		{
			DimseCondition::dump(cond);
		}
		if (DCM_dcmnetLogger.isEnabledFor(OFLogger::DEBUG_LOG_LEVEL))
		{
			printf("Request Parameters:\n");
			ASC_dumpParameters(params, COUT);
		}
    }
	
    if (cond.good()) {
	/* create association */
	if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL))
	    printf("Requesting Sub-Association\n");
	cond = HorosDIMSERequestAssociation(options_.net_, params,
				      &subAssoc);
	if (cond.bad()) {
	    if (cond == DUL_ASSOCIATIONREJECTED) {
			T_ASC_RejectParameters rej;

			ASC_getRejectParameters(params, &rej);
			HorosDIMSEError("moveSCP: Sub-Association Rejected");
			ASC_printRejectParameters(stderr, &rej);
			fprintf(stderr, "\n");
	    } else {
			HorosDIMSEError("moveSCP: Sub-Association Request Failed:");
			DimseCondition::dump(cond);
		
	    }
	}
    }

    if (cond.good()) {
	assocStarted = OFTrue;
    }    
    return cond;
}

OFCondition HorosDICOMMoveContext::closeSubAssociation()
{
    OFCondition cond = EC_Normal;

    if (subAssoc != NULL) {
	/* release association */
	if (DCM_dcmnetLogger.isEnabledFor(OFLogger::INFO_LOG_LEVEL))
	    printf("Releasing Sub-Association\n");
	cond = ASC_releaseAssociation(subAssoc);
	if (cond.bad()) {
	    HorosDIMSEError("moveSCP: Sub-Association Release Failed:");
	    DimseCondition::dump(cond);
	}
	cond = ASC_dropAssociation(subAssoc);
	if (cond.bad()) {
	    HorosDIMSEError("moveSCP: Sub-Association Drop Failed:");
	    DimseCondition::dump(cond);
	}
	cond = ASC_destroyAssociation(&subAssoc);
	if (cond.bad()) {
	    HorosDIMSEError("moveSCP: Sub-Association Destroy Failed:");
	    DimseCondition::dump(cond);
	}

    }

    if (assocStarted) {
	assocStarted = OFFalse;
    }

    return cond;
}

void HorosDICOMMoveContext::moveNextImage(DcmQueryRetrieveDatabaseStatus* status)
{
    DIC_UI sopClass = {}, sopInstance = {};
    char path[MAXPATHLEN + 1] = {};
    OFCondition result = dbHandle.nextMoveResponse(sopClass, sizeof(sopClass), sopInstance, sizeof(sopInstance),
        path, sizeof(path), &nRemaining, status);
    if (result.bad())
    {
        status->setStatus(STATUS_MOVE_Refused_OutOfResourcesSubOperations);
        return;
    }
    if (status->status() != STATUS_Pending) return;
    result = performMoveSubOp(sopClass, sopInstance, path);
    if (result.bad() && result != DIMSE_NOVALIDPRESENTATIONCONTEXTID && result != EC_CannotChangeRepresentation)
    {
        DcmQueryRetrieveDatabaseStatus cleanup;
        dbHandle.cancelMoveRequest(&cleanup);
        status->setStatus(STATUS_MOVE_Refused_OutOfResourcesSubOperations);
    }
}

void HorosDICOMMoveContext::failAllSubOperations(DcmQueryRetrieveDatabaseStatus * dbStatus)
{
    OFCondition dbcond = EC_Normal;
    DIC_UI subImgSOPClass;	/* sub-operation image SOP Class */
    DIC_UI subImgSOPInstance;	/* sub-operation image SOP Instance */
    char subImgFileName[MAXPATHLEN + 1];	/* sub-operation image file */

    /* clear out strings */
    bzero(subImgFileName, sizeof(subImgFileName));
    bzero(subImgSOPClass, sizeof(subImgSOPClass));
    bzero(subImgSOPInstance, sizeof(subImgSOPInstance));

    while (dbStatus->status() == STATUS_Pending) {
        /* get DB response */
        dbcond = dbHandle.nextMoveResponse(
	    subImgSOPClass, sizeof(subImgSOPClass), subImgSOPInstance, sizeof(subImgSOPInstance), subImgFileName, sizeof(subImgFileName),
	    &nRemaining, dbStatus);
        if (dbcond.bad()) {
	    HorosDIMSEError("moveSCP: Database: nextMoveResponse Failed (%s):",
	        DU_cmoveStatusString(dbStatus->status()));
        }

	if (dbStatus->status() == STATUS_Pending) {
	    nFailed++;
	    addFailedUIDInstance(subImgSOPInstance);
	}
    }
    dbStatus->setStatus(STATUS_MOVE_Warning_SubOperationsCompleteOneOrMoreFailures);    
}

void HorosDICOMMoveContext::buildFailedInstanceList(DcmDataset ** rspIds)
{
    OFBool ok;

    if (failedUIDs != NULL) {
	*rspIds = new DcmDataset();
	ok = DU_putStringDOElement(*rspIds, DCM_FailedSOPInstanceUIDList,
	    failedUIDs);
	if (!ok) {
	    HorosDIMSEError("moveSCP: failed to build DCM_FailedSOPInstanceUIDList");
	}
	free(failedUIDs);
	failedUIDs = NULL;
    }
}

OFBool HorosDICOMMoveContext::mapMoveDestination(
  const char *origPeer, const char *origAE,
  const char *dstAE, char *dstPeer, int *dstPort)
{
    // use AETitle to get port and hostname
	NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    NSString *moveDestination = [NSString stringWithCString:dstAE encoding:NSISOLatin1StringEncoding];
	NSArray *serversArray = [DCMNetServiceDelegate DICOMServersListSendOnly:NO QROnly:NO];
	
    //	NSLog( @"***** C-MOVE SCP: Map Move Destination: %@", moveDestination);
	
	NSString *hostname;
	NSString *port;
	
	NSPredicate *serverPredicate = [NSPredicate predicateWithFormat: @"AETitle == %@", moveDestination];
	NSArray *serverSelection = [serversArray filteredArrayUsingPredicate:serverPredicate];
	
	//if empty. Try NSNetService
	if ([serverSelection count] == 0)
	{
		serverPredicate = [NSPredicate predicateWithFormat:@"name == %@", moveDestination];
		serverSelection = [serversArray filteredArrayUsingPredicate:serverPredicate];
	}
	
    
	if ([serverSelection count] > 0) {
		id server = [serverSelection objectAtIndex:0];
		{
			preferredTS = EXS_LittleEndianExplicit;
			
			hostname = [server objectForKey:@"Address"];
			port = [server objectForKey:@"Port"];
			//set preferred Syntax
			NSNumber *tsIndex = [server objectForKey:@"TransferSyntax"];
			if (tsIndex)
			{
				switch ([tsIndex intValue])
				{
					case SendExplicitLittleEndian: preferredTS = EXS_LittleEndianExplicit;
						break;
					case SendJPEG2000Lossless: preferredTS = EXS_JPEG2000LosslessOnly;
						break;
					case SendJPEG2000Lossy10:
					case SendJPEG2000Lossy20:
					case SendJPEG2000Lossy50: preferredTS = EXS_JPEG2000;
                        break;
                    case SendJPEGLSLossless: preferredTS = EXS_JPEGLSLossless;
						break;
					case SendJPEGLSLossy10:
					case SendJPEGLSLossy20:
					case SendJPEGLSLossy50: preferredTS = EXS_JPEGLSLossy;
                        break;
					case SendJPEGLossless: preferredTS = EXS_JPEGProcess14SV1TransferSyntax;
						break;
					case SendJPEGLossy9:
					case SendJPEGLossy8:
					case SendJPEGLossy7: preferredTS = EXS_JPEGProcess2_4TransferSyntax;
						break;
					case SendImplicitLittleEndian: preferredTS = EXS_LittleEndianImplicit;
						break;
					case SendRLE: preferredTS = EXS_RLELossless;
						break;
					case SendExplicitBigEndian: preferredTS = EXS_BigEndianExplicit;
						break;
					case SendBZip: preferredTS = EXS_DeflatedLittleEndianExplicit;
						break;
				}
			}
			else
				preferredTS = EXS_LittleEndianExplicit;
		}
		
		*dstPort = [port intValue];
		strcpy(dstPeer, [hostname cStringUsingEncoding:NSISOLatin1StringEncoding]);
	}
	else
		return OFFalse;
	
	[pool release];
    return OFTrue;
}

//OFCondition HorosDICOMMoveContext::addAllStoragePresentationContexts(T_ASC_Parameters *params, E_TransferSyntax preferredSyntax){
//  // this would be the place to add support for compressed transfer syntaxes
//    OFCondition cond = EC_Normal;
//
//    int i;
//    int pid = 1;
//
//    const char* transferSyntaxes[] = { NULL, NULL, NULL, NULL };
//    int numTransferSyntaxes = 0;
//	
//    switch (preferredSyntax)
//    {
//      case EXS_LittleEndianImplicit:
//        /* we only support Little Endian Implicit */
//        transferSyntaxes[0]  = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 1;
//        break;
//      case EXS_LittleEndianExplicit:
//        /* we prefer Little Endian Explicit */
//        transferSyntaxes[0] = UID_LittleEndianExplicitTransferSyntax;
//        transferSyntaxes[1] = UID_BigEndianExplicitTransferSyntax;
//        transferSyntaxes[2]  = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//        break;
//      case EXS_BigEndianExplicit:
//        /* we prefer Big Endian Explicit */
//        transferSyntaxes[0] = UID_BigEndianExplicitTransferSyntax;
//        transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//        transferSyntaxes[2]  = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//        break;
//    case EXS_JPEGProcess14SV1TransferSyntax:
//      /* we prefer JPEGLossless:Hierarchical-1stOrderPrediction (default lossless) */
//      transferSyntaxes[0] = UID_JPEGProcess14SV1TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEGProcess1TransferSyntax:
//      /* we prefer JPEGBaseline (default lossy for 8 bit images) */
//      transferSyntaxes[0] = UID_JPEGProcess1TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEGProcess2_4TransferSyntax:
//      /* we prefer JPEGExtended (default lossy for 12 bit images) */
//      transferSyntaxes[0] = UID_JPEGProcess2_4TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEG2000LosslessOnly:
//      /* we prefer JPEG 2000 lossless */
//      transferSyntaxes[0] = UID_JPEG2000LosslessOnlyTransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEG2000:
//      /* we prefer JPEG 2000 lossy or lossless */
//      transferSyntaxes[0] = UID_JPEG2000TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//#ifdef WITH_ZLIB
//    case EXS_DeflatedLittleEndianExplicit:
//      /* we prefer deflated transmission */
//      transferSyntaxes[0] = UID_DeflatedExplicitVRLittleEndianTransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//#endif
//    case EXS_RLELossless:
//      /* we prefer RLE Lossless */
//      transferSyntaxes[0] = UID_RLELosslessTransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    default:
//        /* We prefer explicit transfer syntaxes.
//         * If we are running on a Little Endian machine we prefer
//         * LittleEndianExplicitTransferSyntax to BigEndianTransferSyntax.
//         */
//        if (gLocalByteOrder == EBO_LittleEndian)  /* defined in dcxfer.h */
//        {
//          transferSyntaxes[0] = UID_LittleEndianExplicitTransferSyntax;
//          transferSyntaxes[1] = UID_BigEndianExplicitTransferSyntax;
//        } else {
//          transferSyntaxes[0] = UID_BigEndianExplicitTransferSyntax;
//          transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//        }
//        transferSyntaxes[2] = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//        break;
//    }
//	
//    for (i=0; i<numberOfDcmLongSCUStorageSOPClassUIDs && cond.good(); i++)
//	{
//		cond = ASC_addPresentationContext(params, pid, dcmLongSCUStorageSOPClassUIDs[i],  transferSyntaxes, numTransferSyntaxes);
//		pid += 2;	/* only odd presentation context id's */
//    }
//    return cond;
//
//}

OFCondition HorosDICOMMoveContext::addAllStoragePresentationContexts(T_ASC_Parameters *params)
{
    OFCondition cond = EC_Normal;

    int i;
    int pid = 1;

    const char* transferSyntaxes[ 10] = { NULL, NULL, NULL, NULL,NULL, NULL, NULL, NULL,NULL, NULL };
    int numTransferSyntaxes = 0;
	
	transferSyntaxes[0] = UID_LittleEndianExplicitTransferSyntax;
	transferSyntaxes[1] = UID_BigEndianExplicitTransferSyntax;
	transferSyntaxes[2] = UID_LittleEndianImplicitTransferSyntax;
	
	if( [[NSUserDefaults standardUserDefaults] boolForKey: @"DontSupportJPEGForCSMove"])
	{
		transferSyntaxes[3] = UID_JPEG2000TransferSyntax;
		transferSyntaxes[4] = UID_JPEG2000LosslessOnlyTransferSyntax;
		numTransferSyntaxes = 5;
		
        // A transfer-syntax preference must not change CT stored values or rescale metadata.
	}
	else
	{
		transferSyntaxes[3] = UID_JPEGProcess14SV1TransferSyntax;
		transferSyntaxes[4] = UID_JPEGProcess1TransferSyntax;
		transferSyntaxes[5] = UID_JPEGProcess2_4TransferSyntax;
		transferSyntaxes[6] = UID_JPEG2000TransferSyntax;
		transferSyntaxes[7] = UID_JPEG2000LosslessOnlyTransferSyntax;
		transferSyntaxes[8] = UID_RLELosslessTransferSyntax;
		numTransferSyntaxes = 9;
	}
	

//#ifdef DISABLE_COMPRESSION_EXTENSION
//    /* gLocalByteOrder is defined in dcxfer.h */
//    if (gLocalByteOrder == EBO_LittleEndian) {
//    /* we are on a little endian machine */
//        transferSyntaxes[0] = UID_LittleEndianExplicitTransferSyntax;
//        transferSyntaxes[1] = UID_BigEndianExplicitTransferSyntax;
//        transferSyntaxes[2] = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//    } else {
//        /* we are on a big endian machine */
//        transferSyntaxes[0] = UID_BigEndianExplicitTransferSyntax;
//        transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//        transferSyntaxes[2] = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//    }
//#else
//    switch ( preferredTS)
//    {
//      case EXS_LittleEndianImplicit:
//        /* we only support Little Endian Implicit */
//        transferSyntaxes[0]  = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 1;
//        break;
//      case EXS_LittleEndianExplicit:
//        /* we prefer Little Endian Explicit */
//        transferSyntaxes[0] = UID_LittleEndianExplicitTransferSyntax;
//        transferSyntaxes[1] = UID_BigEndianExplicitTransferSyntax;
//        transferSyntaxes[2]  = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//        break;
//      case EXS_BigEndianExplicit:
//        /* we prefer Big Endian Explicit */
//        transferSyntaxes[0] = UID_BigEndianExplicitTransferSyntax;
//        transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//        transferSyntaxes[2]  = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//        break;
//    case EXS_JPEGProcess14SV1TransferSyntax:
//      /* we prefer JPEGLossless:Hierarchical-1stOrderPrediction (default lossless) */
//      transferSyntaxes[0] = UID_JPEGProcess14SV1TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEGProcess1TransferSyntax:
//      /* we prefer JPEGBaseline (default lossy for 8 bit images) */
//      transferSyntaxes[0] = UID_JPEGProcess1TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEGProcess2_4TransferSyntax:
//      /* we prefer JPEGExtended (default lossy for 12 bit images) */
//      transferSyntaxes[0] = UID_JPEGProcess2_4TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEG2000LosslessOnly:
//      /* we prefer JPEG 2000 lossless */
//      transferSyntaxes[0] = UID_JPEG2000LosslessOnlyTransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    case EXS_JPEG2000:
//      /* we prefer JPEG 2000 lossy or lossless */
//      transferSyntaxes[0] = UID_JPEG2000TransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//#ifdef WITH_ZLIB
//    case EXS_DeflatedLittleEndianExplicit:
//      /* we prefer deflated transmission */
//      transferSyntaxes[0] = UID_DeflatedExplicitVRLittleEndianTransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//#endif
//    case EXS_RLELossless:
//      /* we prefer RLE Lossless */
//      transferSyntaxes[0] = UID_RLELosslessTransferSyntax;
//      transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//      transferSyntaxes[2] = UID_BigEndianExplicitTransferSyntax;
//      transferSyntaxes[3] = UID_LittleEndianImplicitTransferSyntax;
//      numTransferSyntaxes = 4;
//      break;
//    default:
//        /* We prefer explicit transfer syntaxes.
//         * If we are running on a Little Endian machine we prefer
//         * LittleEndianExplicitTransferSyntax to BigEndianTransferSyntax.
//         */
//        if (gLocalByteOrder == EBO_LittleEndian)  /* defined in dcxfer.h */
//        {
//          transferSyntaxes[0] = UID_LittleEndianExplicitTransferSyntax;
//          transferSyntaxes[1] = UID_BigEndianExplicitTransferSyntax;
//        } else {
//          transferSyntaxes[0] = UID_BigEndianExplicitTransferSyntax;
//          transferSyntaxes[1] = UID_LittleEndianExplicitTransferSyntax;
//        }
//        transferSyntaxes[2] = UID_LittleEndianImplicitTransferSyntax;
//        numTransferSyntaxes = 3;
//        break;
//    }
//#endif
	
    for (i=0; i<numberOfDcmLongSCUStorageSOPClassUIDs && cond.good(); i++) {
	cond = ASC_addPresentationContext(
	    params, pid, dcmLongSCUStorageSOPClassUIDs[i],
	    transferSyntaxes, numTransferSyntaxes);
	pid += 2;	/* only odd presentation context id's */
    }
    return cond;
}


/*
 * CVS Log
 * $Log: dcmqrcbm.cc,v $
 * Revision 1.1  2006/03/01 20:16:07  lpysher
 * Added dcmtkt ocvs not in xcode  and fixed bug with multiple monitors
 *
 * Revision 1.9  2005/12/20 11:21:30  meichel
 * Removed duplicate parameter
 *
 * Revision 1.8  2005/12/08 15:47:06  meichel
 * Changed include path schema for all DCMTK header files
 *
 * Revision 1.7  2005/11/29 10:54:52  meichel
 * Added minimal support for compressed transfer syntaxes to dcmqrscp.
 *   No on-the-fly decompression is performed, but compressed images can
 *   be stored and retrieved.
 *
 * Revision 1.6  2005/11/17 13:44:40  meichel
 * Added command line options for DIMSE and ACSE timeouts
 *
 * Revision 1.5  2005/10/25 08:56:18  meichel
 * Updated list of UIDs and added support for new transfer syntaxes
 *   and storage SOP classes.
 *
 * Revision 1.4  2005/08/30 08:37:52  meichel
 * Fixed syntax error reported by Visual Studio 2003
 *
 * Revision 1.3  2005/06/16 08:02:43  meichel
 * Added system include files needed on Solaris
 *
 * Revision 1.2  2005/04/04 14:39:54  meichel
 * Fixed warning on Win32 platform
 *
 * Revision 1.1  2005/03/30 13:34:53  meichel
 * Initial release of module dcmqrdb that will replace module imagectn.
 *   It provides a clear interface between the Q/R DICOM front-end and the
 *   database back-end. The imagectn code has been re-factored into a minimal
 *   class structure.
 *
 *
 */
