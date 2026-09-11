#pragma once

// DICOM SR stays in stock DCMTK. Its C++ DicomImage type must not enter the
// Objective-C++ translation units that use Horos's public DicomImage class.
// These non-owning tree/item views forward to the document owned below.
#ifdef __cplusplus
#include <dcmtk/config/osconfig.h>
#include <dcmtk/dcmdata/dcitem.h>
#include <dcmtk/dcmsr/dsrtypes.h>
#include <dcmtk/dcmsr/dsrcodvl.h>
#include <dcmtk/dcmsr/dsrcsidl.h>
#include <dcmtk/dcmsr/dsrsoprf.h>
#include <dcmtk/dcmsr/dsrimgfr.h>
#include <memory>
#include <iosfwd>

class HorosSRImageReference {
public:
    HorosSRImageReference(const OFString& sopClass = "", const OFString& instance = "")
        : sopClass_(sopClass), instance_(instance) {}
    const OFString& getSOPClassUID() const { return sopClass_; }
    const OFString& getSOPInstanceUID() const { return instance_; }
    DSRImageFrameList& getFrameList() { return frames_; }
    const DSRImageFrameList& getFrameList() const { return frames_; }
private:
    OFString sopClass_, instance_;
    DSRImageFrameList frames_;
};

class HorosSRItem {
public:
    explicit HorosSRItem(void* item) : item_(item) {}
    DSRCodedEntryValue getConceptName() const;
    OFString getStringValue() const;
    HorosSRImageReference getImageReference() const;
    OFCondition setConceptName(const DSRCodedEntryValue&);
    OFCondition setStringValue(const OFString&);
    OFCondition setImageReference(const HorosSRImageReference&);
private:
    void* item_;
};

class HorosSRTree {
public:
    explicit HorosSRTree(void* tree) : tree_(tree) {}
    HorosSRItem getCurrentContentItem();
    size_t addContentItem(DSRTypes::E_RelationshipType, DSRTypes::E_ValueType,
        DSRTypes::E_AddMode = DSRTypes::AM_afterCurrent);
    size_t goUp();
    size_t gotoRoot();
    size_t iterate();
    size_t gotoNamedNode(const DSRCodedEntryValue&, OFBool = OFTrue, OFBool = OFFalse);
    size_t gotoNextNamedNode(const DSRCodedEntryValue&, OFBool = OFTrue);
    void clear();
    OFString currentImageSOPInstanceUID() const;
private:
    void* tree_;
};

class HorosSRDocument {
public:
    explicit HorosSRDocument(DSRTypes::E_DocumentType = DSRTypes::DT_BasicTextSR);
    ~HorosSRDocument();
    HorosSRDocument(const HorosSRDocument&) = delete;
    HorosSRDocument& operator=(const HorosSRDocument&) = delete;
    HorosSRTree getTree();
    DSRCodingSchemeIdentificationList& getCodingSchemeIdentification();
    DSRSOPInstanceReferenceList& getCurrentRequestedProcedureEvidence();
    DSRTypes::E_CompletionFlag getCompletionFlag() const;
    DSRTypes::E_VerificationFlag getVerificationFlag() const;
    OFBool containsExtendedCharacters() const;
    OFCondition read(DcmItem&);
    OFCondition write(DcmItem&);
    OFCondition createNewDocument(DSRTypes::E_DocumentType);
    OFCondition createNewSeriesInStudy(const OFString&);
    OFCondition createRevisedVersion(OFBool);
    OFCondition completeDocument(const OFString&);
    OFCondition verifyDocument(const OFString&, const OFString&);
    OFCondition setSpecificCharacterSetType(DSRTypes::E_CharacterSet);
    OFCondition readXML(const char*, size_t = 0);
    OFCondition writeXML(std::ostream&, size_t = 0);
    OFCondition renderHTML(std::ostream&, size_t = 0, const char* = nullptr);
    OFCondition print(std::ostream&, size_t = 0);
    const char* getAccessionNumber();
    const char* getContentDate();
    const char* getInstanceNumber();
    const char* getManufacturer();
    const char* getPatientID();
    const char* getPatientsBirthDate();
    const char* getPatientsName();
    const char* getSOPClassUID();
    const char* getSOPInstanceUID();
    const char* getSeriesDescription();
    const char* getSeriesInstanceUID();
    const char* getSeriesNumber();
    const char* getSpecificCharacterSet();
    const char* getStudyInstanceUID();
    OFCondition setAccessionNumber(const OFString&);
    OFCondition setContentDate(const OFString&);
    OFCondition setContentTime(const OFString&);
    OFCondition setInstanceNumber(const OFString&);
    OFCondition setManufacturer(const OFString&);
    OFCondition setPatientID(const OFString&);
    OFCondition setPatientsBirthDate(const OFString&);
    OFCondition setPatientsName(const OFString&);
    OFCondition setPatientsSex(const OFString&);
    OFCondition setReferringPhysiciansName(const OFString&);
    OFCondition setSeriesDescription(const OFString&);
    OFCondition setSeriesNumber(const OFString&);
    OFCondition setSpecificCharacterSet(const OFString&);
    OFCondition setStudyDescription(const OFString&);
    OFCondition setStudyID(const OFString&);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
#endif
