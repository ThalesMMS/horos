#pragma once

#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmnet/assoc.h>
#include <dcmtk/dcmnet/cond.h>
#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdlib>
#include <netdb.h>
#include <string>
#include <vector>

extern "C" bool HorosDIMSEAssociationPDUIsValid(const unsigned char *, ptrdiff_t) noexcept;

inline OFCondition HorosDIMSEValidateAssociationPDU(const void *bytes, unsigned long size) {
    if (HorosDIMSEAssociationPDUIsValid(static_cast<const unsigned char *>(bytes), size))
        return EC_Normal;
    return makeDcmnetCondition(DULC_ILLEGALPDULENGTH, OF_error,
                              "Malformed A-ASSOCIATE negotiation fields");
}

// Keep address selection in the application. Upstream selects only the first
// DNS answer; a dual-stack name must also work with an IPv4-only peer.
inline OFCondition HorosDIMSESetPeerAddress(T_ASC_Parameters *params,
                                           const char *localHost,
                                           const char *peerHost, int port) {
    if (!params || !peerHost || !*peerHost || port < 1 || port > 65535)
        return makeDcmnetCondition(DULC_ILLEGALSERVICEPARAMETER, OF_error,
                                   "Invalid DICOM peer address or port");
    std::string host(peerHost);
    if (host.size() > 2 && host.front() == '[' && host.back() == ']')
        host = host.substr(1, host.size() - 2);
    const std::string address = host + ":" + std::to_string(port);
    if (address.size() >= sizeof(params->DULparams.calledPresentationAddress))
        return makeDcmnetCondition(DULC_ILLEGALSERVICEPARAMETER, OF_error,
                                   "DICOM peer address exceeds the supported length");
    ASC_setProtocolFamily(params, ASC_AF_UNSPEC);
    return ASC_setPresentationAddresses(params, localHost, address.c_str());
}

inline OFCondition HorosDIMSERequestAssociation(T_ASC_Network *network,
                                                T_ASC_Parameters *params,
                                                T_ASC_Association **association) {
    if (!network || !params || !association) return ASC_NULLKEY;
    *association = NULL;
    const std::string address(params->DULparams.calledPresentationAddress);
    const auto colon = address.find_last_of(':');
    if (colon == std::string::npos) return makeDcmnetCondition(DULC_ILLEGALSERVICEPARAMETER, OF_error, "DICOM peer port is missing");
    const std::string host = address.substr(0, colon);
    const std::string port = address.substr(colon + 1);
    addrinfo hints = {};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    addrinfo *answers = NULL;
    const int result = getaddrinfo(host.c_str(), port.c_str(), &hints, &answers);
    if (result || !answers) {
        if (answers) freeaddrinfo(answers);
        return makeDcmnetCondition(DULC_UNKNOWNHOST, OF_error, gai_strerror(result));
    }
    std::vector<std::string> candidates;
    for (addrinfo *answer = answers; answer; answer = answer->ai_next) {
        char numeric[NI_MAXHOST] = {};
        if (getnameinfo(answer->ai_addr, answer->ai_addrlen, numeric,
                        sizeof(numeric), NULL, 0, NI_NUMERICHOST)) continue;
        const std::string candidate = std::string(numeric) + ":" + port;
        if (std::find(candidates.begin(), candidates.end(), candidate) == candidates.end())
            candidates.push_back(candidate);
    }
    freeaddrinfo(answers);
    const Sint32 originalTimeout = params->DULparams.tcpConnectTimeout;
    const auto started = std::chrono::steady_clock::now();
    OFCondition condition = makeDcmnetCondition(DULC_UNKNOWNHOST, OF_error, "No usable DICOM peer address");
    for (size_t index = 0; index < candidates.size(); ++index) {
        if (originalTimeout > 0) {
            const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - started).count();
            if (elapsed >= originalTimeout) break;
            params->DULparams.tcpConnectTimeout = originalTimeout - elapsed;
        }
        condition = ASC_setPresentationAddresses(params, NULL, candidates[index].c_str());
        if (condition.bad()) break;
        void *pdu = NULL;
        unsigned long pduSize = 0;
        condition = ASC_requestAssociation(network, params, association, &pdu, &pduSize);
        if (condition.good()) {
            condition = HorosDIMSEValidateAssociationPDU(pdu, pduSize);
            if (condition.bad()) ASC_closeTransportConnection(*association);
        }
        free(pdu);
        // Never repeat TLS negotiation, an AE rejection or a DIMSE operation.
        // Only a failed TCP connection can proceed to the next DNS address.
        if (condition.module() != OFM_dcmnet || condition.code() != DULC_TCPINITERROR ||
            index + 1 == candidates.size()) break;
        if (*association) {
            // ASC owns params once it allocates an association. Retain that
            // same public parameter object only for this TCP-only retry.
            (*association)->params = NULL;
            ASC_destroyAssociation(association);
        }
    }
    params->DULparams.tcpConnectTimeout = originalTimeout;
    return condition;
}
