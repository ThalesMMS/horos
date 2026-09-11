#import "HorosQueryRetrieveServer.h"
#import "HorosDIMSEClient.h"
#import "DicomDatabase.h"
/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation,  version 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE.  See the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos.  If not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program:   OsiriX
  Copyright (c) OsiriX Team
  All rights reserved.
  Distributed under GNU - LGPL
  
  See http://www.osirix-viewer.com/copyright.html for details.
     This software is distributed WITHOUT ANY WARRANTY; without even
     the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
     PURPOSE.
 ============================================================================*/

#import "DCMTKQueryRetrieveSCP.h"
#import "AppController.h"
#import "DICOMTLS.h"
#import "Horos-Swift.h"
#import "ContextCleaner.h"

#undef verify

#include "HorosDCMTKCompatibility.h"
#include "HorosTLSConfiguration.h"
#include <dcmtk/config/osconfig.h>    /* make sure OS specific configuration is included first */

#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <cerrno>
#include <ctime>
#include <unistd.h>
#include <dcmtk/ofstd/ofstdinc.h>

BEGIN_EXTERN_C
#ifdef HAVE_SYS_FILE_H
#include <sys/file.h>
#endif
#ifdef HAVE_SYS_TYPES_H
#include <sys/types.h>
#endif
#ifdef HAVE_SYS_WAIT_H
#include <sys/wait.h>
#endif
#ifdef HAVE_SYS_TIME_H
#include <sys/time.h>
#endif
#ifdef HAVE_SYS_RESOURCE_H
#include <sys/resource.h>
#endif
#ifdef HAVE_SYS_PARAM_H
#include <sys/param.h>
#endif
#ifdef HAVE_SYS_ERRNO_H
#include <sys/errno.h>
#endif
#ifdef HAVE_IO_H
#include <io.h>
#endif
#ifdef HAVE_PWD_H
#include <pwd.h>
#endif
#ifdef HAVE_GRP_H
#include <grp.h>
#endif
END_EXTERN_C

#include <dcmtk/dcmnet/dicom.h>
#include <dcmtk/dcmqrdb/dcmqropt.h>
#include <dcmtk/dcmnet/dimse.h>
#include <dcmtk/dcmqrdb/dcmqrcnf.h>
#include <dcmtk/dcmqrdb/dcmqrsrv.h>
#include <dcmtk/dcmdata/dcdict.h>
#include "HorosDCMTKCompatibility.h"
#include "HorosTLSConfiguration.h"
#include <dcmtk/dcmdata/cmdlnarg.h>
#include <dcmtk/ofstd/ofconapp.h>
#include <dcmtk/dcmdata/dcuid.h>       /* for dcmtk version name */

//#ifdef WITH_SQL_DATABASE
#include "dcmqrdbq.h"
//#else
//#include <dcmtk/dcmqrdb/dcmqrdbi.h>
//#endif

#define OPENSSL_DISABLE_OLD_DES_SUPPORT // joris

#ifdef WITH_OPENSSL // joris
#ifdef UI
#undef UI // For MacOS 10.7 compilation
#endif
#include <dcmtk/dcmtls/tlstrans.h>
#include <dcmtk/dcmtls/tlslayer.h>
#endif

#ifdef WITH_ZLIB
#include <zlib.h>        /* for zlibVersion() */
#endif

#ifndef OFFIS_CONSOLE_APPLICATION
#define OFFIS_CONSOLE_APPLICATION "dcmqrscp"
#endif

#define APPLICATIONTITLE    "DCMQRSCP"

//const char *opt_configFileName = "dcmqrscp.cfg";
//OFBool      opt_checkFindIdentifier = OFFalse;
//OFBool      opt_checkMoveIdentifier = OFFalse;
//OFCmdUnsignedInt opt_port = 0;

HorosQueryRetrieveServer *scp = nil;
HorosQueryRetrieveServer *scptls = nil;

OFCondition mainStoreSCP(T_ASC_Association* assoc, T_DIMSE_C_StoreRQ* request, T_ASC_PresentationContextID presId, DcmQueryRetrieveDatabaseHandle* dbHandle)
{
    DcmQueryRetrieveOptions options;
    options.blockMode_ = DIMSE_NONBLOCKING;
    options.dimse_timeout_ = (int)[[NSUserDefaults standardUserDefaults] integerForKey:@"DICOMTimeout"];
    return HorosStoreSCP(assoc, *request, presId, *dbHandle, options);
}


static const char *HorosIncomingAssociationProfile = "HOROS_INCOMING";
static const char *HorosIncomingPresentationContexts = "HOROS_INCOMING_CONTEXTS";
static const char *HorosIncomingTransferSyntaxes = "HOROS_INCOMING_TRANSFER_SYNTAXES";
static const char *HorosIncomingRoles = "HOROS_INCOMING_ROLES";

static OFBool HorosSupportsIncomingTransferSyntax(E_TransferSyntax syntax)
{
    const int syntaxValue = OFstatic_cast(int, syntax);
    if (syntaxValue < OFstatic_cast(int, EXS_LittleEndianImplicit) ||
        syntaxValue > OFstatic_cast(int, EXS_HighThroughputJPEG2000))
        return OFFalse;

    if (syntax == EXS_BigEndianImplicit || syntax == EXS_JPIPReferenced ||
        syntax == EXS_JPIPReferencedDeflate)
        return OFFalse;

    DcmXfer xfer(syntax);
    return xfer.isValid() && xfer.getXferID()[0] != '\0' &&
           xfer.getStreamCompression() != ESC_unsupported;
}

static OFCondition HorosAddIncomingTransferSyntax(DcmAssociationConfiguration &configuration,
                                                   OFBool *addedSyntaxes,
                                                   E_TransferSyntax syntax)
{
    if (!HorosSupportsIncomingTransferSyntax(syntax))
        return EC_Normal;

    const int syntaxValue = OFstatic_cast(int, syntax);
    if (addedSyntaxes[syntaxValue])
        return EC_Normal;

    DcmXfer xfer(syntax);
    OFCondition condition = configuration.addTransferSyntax(HorosIncomingTransferSyntaxes,
                                                             xfer.getXferID());
    if (condition.good())
        addedSyntaxes[syntaxValue] = OFTrue;
    return condition;
}

static OFCondition HorosConfigureIncomingAssociationProfile(DcmAssociationConfiguration &configuration,
                                                             E_TransferSyntax preferredSyntax)
{
    // Most C-STORE senders use the default requestor-SCU role, while C-GET
    // requires the requestor to act as Storage SCP. Accept both forms.
    configuration.setAlwaysAcceptDefaultRole(OFTrue);

    OFBool addedSyntaxes[OFstatic_cast(int, EXS_HighThroughputJPEG2000) + 1];
    memset(addedSyntaxes, 0, sizeof(addedSyntaxes));

    OFCondition condition = HorosAddIncomingTransferSyntax(configuration, addedSyntaxes,
                                                            preferredSyntax);
    if (condition.good())
        condition = HorosAddIncomingTransferSyntax(configuration, addedSyntaxes,
                                                    EXS_LittleEndianExplicit);
    if (condition.good())
        condition = HorosAddIncomingTransferSyntax(configuration, addedSyntaxes,
                                                    EXS_BigEndianExplicit);
    if (condition.good())
        condition = HorosAddIncomingTransferSyntax(configuration, addedSyntaxes,
                                                    EXS_LittleEndianImplicit);

    for (int syntaxValue = OFstatic_cast(int, EXS_LittleEndianImplicit);
         condition.good() && syntaxValue <= OFstatic_cast(int, EXS_HighThroughputJPEG2000);
         ++syntaxValue)
    {
        condition = HorosAddIncomingTransferSyntax(configuration, addedSyntaxes,
                                                    OFstatic_cast(E_TransferSyntax, syntaxValue));
    }

    for (int index = 0; condition.good() && index < numberOfDcmAllStorageSOPClassUIDs; ++index)
    {
        const char *sopClass = dcmAllStorageSOPClassUIDs[index];
        condition = configuration.addPresentationContext(HorosIncomingPresentationContexts,
                                                         sopClass,
                                                         HorosIncomingTransferSyntaxes,
                                                         OFFalse);
        if (condition.good())
            condition = configuration.addRole(HorosIncomingRoles, sopClass, ASC_SC_ROLE_SCUSCP);
    }

    if (condition.good())
        condition = configuration.addProfile(HorosIncomingAssociationProfile,
                                             HorosIncomingPresentationContexts,
                                             HorosIncomingRoles);
    return condition;
}

void errmsg(const char* msg, ...)
{
    va_list args;

    fprintf(stderr, "%s: ", OFFIS_CONSOLE_APPLICATION);
    va_start(args, msg);
    vfprintf(stderr, msg, args);
    va_end(args);
    fprintf(stderr, "\n");
}

@interface DCMTKQueryRetrieveSCP (Dummy)

- (void)displayUpdateMessage:(id)dummy;
- (void)displayListenerError:(id)dummy;

@end

@implementation DCMTKQueryRetrieveSCP

+ (BOOL) storeSCP
{
	if( scp || scptls || [[NSUserDefaults standardUserDefaults] boolForKey:@"NinjaSTORESCP"]) // some undefined external entity is running a DIOCM listener...
		return YES;
	else
		return NO;
}

- (BOOL) running
{
	return running;
}

- (int) port
{
	return _port;
}

- (NSString*) aeTitle
{
	return _aeTitle;
}

- (id)initWithPort:(int)port aeTitle:(NSString *)aeTitle  extraParamaters:(NSDictionary *)params{
	if (self = [super init]) {
		_port = port;
		_aeTitle = [aeTitle retain];
		_params = [params retain];
	}
    
#ifdef NONETWORKFUNCTIONS
    return nil;
#endif
    
	return self;
}

- (void)dealloc
{
	[_aeTitle release];
	[_params release];
	[super dealloc];
}

- (void)run
{
	OFCondition cond = EC_Normal;
    OFCmdUnsignedInt overrideMaxPDU = 0;
    DcmQueryRetrieveOptions options;

	//verbose

	
	//single process
	options.singleProcess_ = [[NSUserDefaults standardUserDefaults] boolForKey: @"SingleProcessMultiThreadedListener"];
	
	//debug
//	options.debug_ = OFTrue;
//	DUL_Debug(OFTrue);
//	DIMSE_debug(OFTrue);
//	SetDebugLevel(3);
	
	//no restrictions on moves
	options.restrictMoveToSameAE_ = OFFalse;
    options.restrictMoveToSameHost_ = OFFalse;
    options.restrictMoveToSameVendor_ = OFFalse;
	
	//only suppport Study Root fornow
	options.supportPatientRoot_ = OFFalse;
	options.supportPatientStudyOnly_ = OFFalse;
	
	options.networkTransferSyntax_ = (E_TransferSyntax) [[NSUserDefaults standardUserDefaults] integerForKey: @"preferredSyntaxForIncoming"];
	
//	options.networkTransferSyntax_ = EXS_LittleEndianImplicit;		// See dcmqrsrv.mm
//	else options.networkTransferSyntax_ = EXS_LittleEndianExplicit;																								// See dcmqrsrv.mm
	
	options.networkTransferSyntaxOut_ =  EXS_LittleEndianExplicit;	//;	//EXS_LittleEndianExplicit;	//;		EXS_JPEG2000		// See dcmqrcbm.mm - NOT USED
	/*
	options.networkTransferSyntaxOut_ = EXS_LittleEndianExplicit;
	options.networkTransferSyntaxOut_ = EXS_BigEndianExplicit;
	options.networkTransferSyntaxOut_ = EXS_JPEGProcess14SV1TransferSyntax;
	options.networkTransferSyntaxOut_ = EXS_JPEGProcess1TransferSyntax;
	options.networkTransferSyntaxOut_ = EXS_JPEGProcess2_4TransferSyntax;
	options.networkTransferSyntaxOut_ = EXS_JPEG2000LosslessOnly;
	options.networkTransferSyntaxOut_ = EXS_JPEG2000;
	options.networkTransferSyntaxOut_ = EXS_RLELossless;
#ifdef WITH_ZLIB
	options.networkTransferSyntaxOut_ = EXS_DeflatedLittleEndianExplicit;
#endif
	options.networkTransferSyntaxOut_ = EXS_LittleEndianImplicit;
*/

	//timeout
	OFCmdSignedInt opt_timeout = [[NSUserDefaults standardUserDefaults] integerForKey:@"DICOMTimeout"];
    
    if( opt_timeout < 2)
        opt_timeout = 2;
    
    if( [[NSUserDefaults standardUserDefaults] integerForKey:@"DICOMConnectionTimeout"] > 0)
    {
        NSLog( @"--- DICOMConnectionTimeout: %d", (int) [[NSUserDefaults standardUserDefaults] integerForKey:@"DICOMConnectionTimeout"]);
        dcmConnectionTimeout.set( (Sint32) [[NSUserDefaults standardUserDefaults] integerForKey:@"DICOMConnectionTimeout"]);
    }
    else
        dcmConnectionTimeout.set( (Sint32) opt_timeout);
	
	//acse-timeout
	options.acse_timeout_ = OFstatic_cast(int, opt_timeout);
	
	//dimse-timeout
	options.dimse_timeout_ = OFstatic_cast(int, opt_timeout);
	options.blockMode_ = DIMSE_NONBLOCKING;
	
	//maxpdu
	//overrideMaxPDU = 
	
	//correct UID padding
	//options.correctUIDPadding_ = OFTrue
	
	//enble new VR
	dcmEnableUnknownVRGeneration.set(OFTrue);
	dcmEnableUnlimitedTextVRGeneration.set(OFTrue);
	
	//fix padding
	options.bitPreserving_ = OFFalse;
	
	//write metaheader
	options.useMetaheader_ = OFTrue;
	
	options.writeTransferSyntax_ = EXS_Unknown;
	
//	switch ( [[NSUserDefaults standardUserDefaults] integerForKey:@"ListenerCompressionSettings"]) //It's not a good idea, because it's a single process... no multi-threads
//	{
//		case 0:
//			options.writeTransferSyntax_ = EXS_Unknown;	//write with same syntax as it came in
//		break;
//			
//		case 1:
//			options.writeTransferSyntax_ = EXS_LittleEndianExplicit; //decompress
//		break;
//			
//		case 2:
//			options.writeTransferSyntax_ = EXS_JPEG2000;	// compress
//		break;
//	}
	
	//remove group lengths
	options.groupLength_ = EGL_withoutGL;
	
	//number of associations
	options.maxAssociations_ = 800;
	
	//port
//	opt_port = _port;
	
	//max PDU size
	options.maxPDU_ = ASC_DEFAULTMAXPDU;
	if (overrideMaxPDU > 0) options.maxPDU_ = overrideMaxPDU;	//;
	
	    /* make sure data dictionary is loaded */
    if (!dcmDataDict.isDictionaryLoaded())
	{
		fprintf(stderr, "Warning: no data dictionary loaded, check environment variable: %s\n",  DCM_DICT_ENVIRONMENT_VARIABLE);
		return;
    }

	//init the network
	dcmIncomingProtocolFamily.set(ASC_AF_UNSPEC);
	cond = ASC_initializeNetwork(NET_ACCEPTORREQUESTOR, (int)_port, options.acse_timeout_, &options.net_);
    if (cond.bad())
	{
		int bindErrno = errno;
		errmsg("Error initialising network:");
		DimseCondition::dump(cond);
		
		NSString *service = [[_params objectForKey:@"TLSEnabled"] boolValue] ? @"DICOM TLS listen" : @"DICOM listen";
        [[AppController sharedAppController] reportListenBindFailureForService:service
                                                                          port:_port
                                                                     errnoCode:bindErrno];
		return;
    }
	
#if defined(HAVE_SETUID) && defined(HAVE_GETUID)
    /* return to normal uid so that we can't do too much damage in case
     * things go very wrong.   Only relevant if the program is setuid root,
     * and run by another user.  Running as root user may be
     * potentially disasterous if this program screws up badly.
     */
    setuid(getuid());
#endif

#ifdef WITH_OPENSSL // joris
	
	DcmTLSTransportLayer *tLayer = NULL;
	
	if([[_params objectForKey:@"TLSEnabled"] boolValue])
	{
		tLayer = new DcmTLSTransportLayer(NET_ACCEPTOR, [TLS_SEED_FILE cStringUsingEncoding:NSUTF8StringEncoding], OFTrue); // joris DICOM_APPLICATION_ACCEPTOR for server!!
		if (tLayer == NULL)
		{
			[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: @"unable to create TLS transport layer" waitUntilDone: NO];
			return;
		}
		
		// Normalise first: the stored value is an unbounded intValue, and anything
		// that was not 0 or 1 used to fall into the else further down and turn peer
		// verification off. An unknown value now becomes the strictest.
		TLSCertificateVerificationType certVerification = (TLSCertificateVerificationType)[HorosTLSVerificationPolicy normalise: [[[NSUserDefaults standardUserDefaults] valueForKey:@"TLSStoreSCPCertificateVerification"] intValue]];
		
		if(certVerification==VerifyPeerCertificate || certVerification==RequirePeerCertificate)
		{
			NSString *trustedCertificatesDir = [NSString stringWithFormat:@"%@%@", TLS_TRUSTED_CERTIFICATES_DIR, @"StoreSCPTLS"];
			[DDKeychain KeychainAccessExportTrustedCertificatesToDirectory:trustedCertificatesDir];
			NSArray *trustedCertificates = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:trustedCertificatesDir error:nil];
			
			for (NSString *cert in trustedCertificates)
			{
				if (tLayer->addTrustedCertificateFile([[trustedCertificatesDir stringByAppendingPathComponent:cert] cStringUsingEncoding:NSUTF8StringEncoding], DCF_Filetype_PEM).bad())
				{
					NSString *errMessage = [NSString stringWithFormat: @"DICOM Network Failure (storescp TLS) : Unable to load certificate file %@. You can turn OFF TLS Listener in Preferences->Listener.", [trustedCertificatesDir stringByAppendingPathComponent:cert]];
					[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: errMessage waitUntilDone: NO];
					return;
				}
			}
			
			//--add-cert-dir //// add certificates in d to list of certificates
			//.... needs to use OpenSSL & rename files (see http://forum.dicom-cd.de/viewtopic.php?p=3237&sid=bd17bd76876a8fd9e7fdf841b90cf639 )
			
			//			if (cmd.findOption("--add-cert-dir", 0, OFCommandLine::FOM_First))
			//			{
			//				const char *current = NULL;
			//				do
			//				{
			//					app.checkValue(cmd.getValue(current));
			//					if (tLayer->addTrustedCertificateDir(current, opt_keyFileFormat).bad())
			//					{
			//						CERR << "warning unable to load certificates from directory '" << current << "', ignoring" << endl;
			//					}
			//				} while (cmd.findOption("--add-cert-dir", 0, OFCommandLine::FOM_Next));
			//			}
		}		
		
//		if (_dhparam && ! (tLayer->setTempDHParameters(_dhparam)))
//		{
//			localException = [NSException exceptionWithName:@"DICOM Network Failure (storescu TLS)" reason:[NSString stringWithFormat:@"Unable to load temporary DH parameter file %s", _dhparam] userInfo:nil];
//			[localException raise];
//		}
		
//		if (_doAuthenticate)
		{			
			tLayer->setPrivateKeyPasswd([[DICOMTLS TLS_PRIVATE_KEY_PASSWORD] cStringUsingEncoding:NSUTF8StringEncoding]);
			
			[DICOMTLS generateCertificateAndKeyForLabel:TLS_KEYCHAIN_IDENTITY_NAME_SERVER withStringID:@"StoreSCPTLS"]; // export certificate/key from the Keychain to the disk
			
			NSString *_privateKeyFile = [DICOMTLS keyPathForLabel:TLS_KEYCHAIN_IDENTITY_NAME_SERVER withStringID:@"StoreSCPTLS"]; // generates the PEM file for the private key
			NSString *_certificateFile = [DICOMTLS certificatePathForLabel:TLS_KEYCHAIN_IDENTITY_NAME_SERVER withStringID:@"StoreSCPTLS"]; // generates the PEM file for the certificate
			
			if (tLayer->setPrivateKeyFile([_privateKeyFile cStringUsingEncoding:NSUTF8StringEncoding], DCF_Filetype_PEM).bad())
			{
				NSString *errMessage = [NSString stringWithFormat: @"DICOM Network Failure (storescp TLS) : Unable to load private TLS key from %@. You can turn OFF TLS Listener in Preferences->Listener.", _privateKeyFile];
				[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: errMessage waitUntilDone: NO];
				return;
			}
			
			if (tLayer->setCertificateFile([_certificateFile cStringUsingEncoding:NSUTF8StringEncoding], DCF_Filetype_PEM, TSP_Profile_BCP_195_RFC_8996).bad())
			{
				NSString *errMessage = [NSString stringWithFormat: @"DICOM Network Failure (storescp TLS) : Unable to load certificate from %@. You can turn OFF TLS Listener in Preferences->Listener.", _certificateFile];
				[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: errMessage waitUntilDone: NO];
				return;
			}
			
			if (!tLayer->checkPrivateKeyMatchesCertificate())
			{
				NSString *errMessage = [NSString stringWithFormat: @"DICOM Network Failure (storescp TLS) : Unable to load certificate from private key '%@' and certificate '%@' do not match. You can turn OFF TLS Listener in Preferences->Listener.", _privateKeyFile, _certificateFile];
				[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: errMessage waitUntilDone: NO];
				return;
			}
		}
		
		NSArray *suites = [[NSUserDefaults standardUserDefaults] objectForKey:@"TLSStoreSCPCipherSuites"];
		NSMutableArray *selectedCipherSuites = [NSMutableArray array];
		
		for (NSDictionary *suite in suites)
		{
			if ([[suite objectForKey:@"Supported"] boolValue])
				[selectedCipherSuites addObject:[suite objectForKey:@"Cipher"]];
		}
		
		NSArray *_cipherSuites = [NSArray arrayWithArray:selectedCipherSuites];
		
        OFCondition cipherResult = HorosConfigureTLSCipherSuites(*tLayer, _cipherSuites);
        if (cipherResult.bad())
        {
            NSString *errMessage = [NSString stringWithFormat:@"DICOM Network Failure (storescp TLS): %s", cipherResult.text()];
            [[AppController sharedAppController] performSelectorOnMainThread:@selector(displayListenerError:) withObject:errMessage waitUntilDone:NO];
            delete tLayer;
            ASC_dropNetwork(&options.net_);
            return;
        }

		DcmCertificateVerification _certVerification;
		
		if(certVerification==RequirePeerCertificate)
			_certVerification = DCV_requireCertificate;
		else if(certVerification==VerifyPeerCertificate)
			_certVerification = DCV_checkCertificate;
		else
			_certVerification = DCV_ignoreCertificate;
		
		tLayer->setCertificateVerification(_certVerification);
		
		cond = ASC_setTransportLayer(options.net_, tLayer, 0);
		if (cond.bad())
		{
			DimseCondition::dump(cond);
			NSString *errMessage = [NSString stringWithFormat: @"DICOM Network Failure (storescp TLS) : ASC_setTransportLayer - %04x:%04x %s. You can turn OFF TLS Listener in Preferences->Listener.", cond.module(), cond.code(), cond.text()];
			[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: errMessage waitUntilDone: NO];
			return;
		}
	}
#endif
	
	
	

	NSString *storageArea = [[DicomDatabase activeLocalDatabase] incomingDirPath];
	NSString *configPath = [NSTemporaryDirectory() stringByAppendingPathComponent: [NSString stringWithFormat: @"Horos-dcmqrscp-%d-%@.cfg", (int) getpid(), _aeTitle]];
	NSString *configText = [NSString stringWithFormat:
		@"NetworkTCPPort %d\n"
		@"MaxPDUSize %lu\n"
		@"MaxAssociations %d\n"
		@"HostTable BEGIN\n"
		@"HostTable END\n"
		@"VendorTable BEGIN\n"
		@"VendorTable END\n"
		@"AETable BEGIN\n"
		@"%@ \"%@\" RW (20000, 1024mb) ANY\n"
		@"AETable END\n",
		_port,
		(unsigned long) options.maxPDU_,
		(int) options.maxAssociations_,
		_aeTitle,
		storageArea];

	if( [configText writeToFile: configPath atomically: YES encoding: NSUTF8StringEncoding error: nil] == NO)
	{
		[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: @"Unable to create DICOM listener configuration." waitUntilDone: NO];
		ASC_dropNetwork(&options.net_);
		return;
	}

DcmQueryRetrieveConfig config;
	if( !config.init( [configPath fileSystemRepresentation]))
	{
		[[AppController sharedAppController] performSelectorOnMainThread: @selector(displayListenerError:) withObject: @"Unable to read DICOM listener configuration." waitUntilDone: NO];
		ASC_dropNetwork(&options.net_);
		return;
	}
DcmAssociationConfiguration asccfg;

	OFCondition profileCondition = HorosConfigureIncomingAssociationProfile(asccfg,
	                                                                        options.networkTransferSyntax_);
	if (profileCondition.good())
		options.incomingProfile = HorosIncomingAssociationProfile;
	else
    {
        NSString *message = [NSString stringWithFormat:@"Unable to configure DICOM listener: %s",
                             profileCondition.text()];
        [[AppController sharedAppController] performSelectorOnMainThread:@selector(displayListenerError:)
                                                              withObject:message waitUntilDone:NO];
        ASC_dropNetwork(&options.net_);
#ifdef WITH_OPENSSL
        delete tLayer;
#endif
        return;
    }

    DcmQueryRetrieveOsiriXDatabaseHandleFactory factory;
	HorosQueryRetrieveServer *localSCP = new HorosQueryRetrieveServer(config, options, factory, asccfg,
        [[_params objectForKey:@"TLSEnabled"] boolValue]);
	
	if([[_params objectForKey:@"TLSEnabled"] boolValue])
		scptls = localSCP;
	else
		scp = localSCP;
	
	_abort = NO;
	running = YES;
		
	// ********* WARNING -- NEVER NEVER CALL ANY COCOA (NSobject) functions after this point... fork() will be used ! fork is INCOMPATIBLE with NSObject ! See http://www.cocoadev.com/index.pl?ForkSafety
	// Even a simple NSLog() will cause many many problems......
	
    /* loop waiting for associations */
	if(cond.good())
	{
		while(!_abort)
		{
			@try
			{
				try
				{
					if( _abort == NO)
						cond = localSCP->waitForAssociation(options.net_);
				}
				catch(...)
				{
					NSLog( @"***** C++ exception in %s", __PRETTY_FUNCTION__);
				}
			}
			@catch (NSException * e)
			{
				NSLog( @"***** exception in %s: %@", __PRETTY_FUNCTION__, e);
			}
		}
	}
	
    // The server cancels and joins its own association workers before releasing configuration.
    
	if( _abort)
		NSLog( @"---- store-SCP aborted");
    
	if( localSCP)
		delete localSCP;
	
	localSCP = NULL;
	
    if([[_params objectForKey:@"TLSEnabled"] boolValue])
		scptls = nil;
	else
		scp = nil;
    
	if (cond.bad())
		errmsg("****** cond.good() != normal ---- DCMTKQueryRetrieve");
	
	cond = ASC_dropNetwork(&options.net_);
    if (cond.bad()) {
        errmsg("Error dropping network:");
        DimseCondition::dump(cond);
    }
	
	running = NO;
	
#ifdef WITH_OPENSSL // joris
	if( tLayer)
		delete tLayer;
#endif
	
    if([[_params objectForKey:@"TLSEnabled"] boolValue])
    {
        [[NSFileManager defaultManager] removeItemAtPath:[DICOMTLS keyPathForLabel:TLS_KEYCHAIN_IDENTITY_NAME_SERVER withStringID:@"StoreSCPTLS"] error:NULL];
        [[NSFileManager defaultManager] removeItemAtPath:[DICOMTLS certificatePathForLabel:TLS_KEYCHAIN_IDENTITY_NAME_SERVER withStringID:@"StoreSCPTLS"] error:NULL];
        [[NSFileManager defaultManager] removeItemAtPath:[NSString stringWithFormat:@"%@%@", TLS_TRUSTED_CERTIFICATES_DIR, @"StoreSCPTLS"] error:NULL];
    }
	return;
}

-(void)abort
{
	NSLog( @"---- store-SCP abort !");
	_abort = YES;
}

@end
