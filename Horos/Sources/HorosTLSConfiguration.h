#pragma once

#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmtls/tlslayer.h>
#include <dcmtk/dcmtls/tlsciphr.h>
#include <dcmtk/ofstd/oflist.h>

// Keep cipher configuration local to an association. An empty saved selection
// uses the current DICOM TLS profile; explicit selections must all be accepted.
static inline OFCondition HorosConfigureTLSCipherSuites(
    DcmTLSTransportLayer& layer, const OFList<OFString>& selected)
{
    OFCondition result = EC_Normal;
    if (selected.empty())
        result = layer.setTLSProfile(TSP_Profile_BCP_195_RFC_8996);
    else
    {
        layer.clearTLSProfile();
        for (OFListConstIterator(OFString) suite = selected.begin(); suite != selected.end(); ++suite)
        {
            result = layer.addCipherSuite(suite->c_str());
            if (result.bad()) return result;
        }
    }
    return result.good() ? layer.activateCipherSuites() : result;
}

#ifdef __OBJC__
#import <Foundation/Foundation.h>
static inline OFCondition HorosConfigureTLSCipherSuites(
    DcmTLSTransportLayer& layer, NSArray* selected)
{
    OFList<OFString> suites;
    for (NSString* suite in selected) suites.push_back([suite UTF8String]);
    return HorosConfigureTLSCipherSuites(layer, suites);
}
#endif
