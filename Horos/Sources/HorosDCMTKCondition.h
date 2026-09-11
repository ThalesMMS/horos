#pragma once

#import <Foundation/Foundation.h>

#include <dcmtk/dcmnet/assoc.h>
#include <dcmtk/dcmnet/cond.h>

static inline void HorosLogDIMSECondition(OFCondition condition)
{
    OFString description;
    DimseCondition::dump(description, condition);
    NSLog(@"%s", description.c_str());
}

static inline void HorosLogAssociationParameters(T_ASC_Parameters *parameters,
                                                  ASC_associateType direction)
{
    OFString description;
    ASC_dumpParameters(description, parameters, direction);
    NSLog(@"%s", description.c_str());
}

static inline void HorosLogAssociationConnection(T_ASC_Association *association)
{
    OFString description;
    ASC_dumpConnectionParameters(description, association);
    NSLog(@"%s", description.c_str());
}

static inline void HorosLogAssociationRejection(const T_ASC_RejectParameters *rejection)
{
    OFString description;
    ASC_printRejectParameters(description, rejection);
    NSLog(@"%s", description.c_str());
}
