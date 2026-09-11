#include "HorosStructuredReportBridge.h"
#include <dcmtk/dcmsr/dsrdoc.h>
#include <dcmtk/dcmdata/dcdatset.h>
#include <dcmtk/dcmsr/dsrcontn.h>
#include <dcmtk/dcmsr/dsrimgtn.h>
#include <map>
#include <sstream>
#include <algorithm>

struct HorosSRDocument::Impl {
    explicit Impl(DSRTypes::E_DocumentType type) : document(type) {}
    DSRDocument document;
    // Separate getter storage preserves legacy pointer lifetimes between fields.
    std::map<OFString, OFString> strings;
};
HorosSRDocument::HorosSRDocument(DSRTypes::E_DocumentType type) : impl_(new Impl(type)) {}
HorosSRDocument::~HorosSRDocument() = default;
HorosSRTree HorosSRDocument::getTree() { return HorosSRTree(&impl_->document.getTree()); }
DSRCodingSchemeIdentificationList& HorosSRDocument::getCodingSchemeIdentification() { return impl_->document.getCodingSchemeIdentification(); }
DSRSOPInstanceReferenceList& HorosSRDocument::getCurrentRequestedProcedureEvidence() { return impl_->document.getCurrentRequestedProcedureEvidence(); }
DSRTypes::E_CompletionFlag HorosSRDocument::getCompletionFlag() const { return impl_->document.getCompletionFlag(); }
DSRTypes::E_VerificationFlag HorosSRDocument::getVerificationFlag() const { return impl_->document.getVerificationFlag(); }
OFBool HorosSRDocument::containsExtendedCharacters() const {
    DcmDataset dataset;
    // The diagnostic print omits metadata such as the series description.
    // Inspect the serialized DICOM strings, including nested content, instead.
    return impl_->document.write(dataset).good() && dataset.containsExtendedCharacters();
}
OFCondition HorosSRDocument::read(DcmItem& value) { return impl_->document.read(value); }
OFCondition HorosSRDocument::write(DcmItem& value) { return impl_->document.write(value); }
OFCondition HorosSRDocument::createNewDocument(DSRTypes::E_DocumentType value) { return impl_->document.createNewDocument(value); }
OFCondition HorosSRDocument::createNewSeriesInStudy(const OFString& value) { return impl_->document.createNewSeriesInStudy(value); }
OFCondition HorosSRDocument::createRevisedVersion(OFBool value) { return impl_->document.createRevisedVersion(value); }
OFCondition HorosSRDocument::completeDocument(const OFString& value) { return impl_->document.completeDocument(value); }
OFCondition HorosSRDocument::verifyDocument(const OFString& name, const OFString& organization) { return impl_->document.verifyDocument(name, organization); }
OFCondition HorosSRDocument::setSpecificCharacterSetType(DSRTypes::E_CharacterSet value) { return impl_->document.setSpecificCharacterSetType(value); }
OFCondition HorosSRDocument::readXML(const char* path, size_t flags) { return impl_->document.readXML(path, flags); }
OFCondition HorosSRDocument::writeXML(std::ostream& out, size_t flags) { return impl_->document.writeXML(out, flags); }
OFCondition HorosSRDocument::renderHTML(std::ostream& out, size_t flags, const char* style) { return impl_->document.renderHTML(out, flags, style); }
OFCondition HorosSRDocument::print(std::ostream& out, size_t flags) { return impl_->document.print(out, flags); }
const char* HorosSRDocument::getAccessionNumber() { auto& value = impl_->strings["getAccessionNumber"]; impl_->document.getAccessionNumber(value); return value.c_str(); }
const char* HorosSRDocument::getContentDate() { auto& value = impl_->strings["getContentDate"]; impl_->document.getContentDate(value); return value.c_str(); }
const char* HorosSRDocument::getInstanceNumber() { auto& value = impl_->strings["getInstanceNumber"]; impl_->document.getInstanceNumber(value); return value.c_str(); }
const char* HorosSRDocument::getManufacturer() { auto& value = impl_->strings["getManufacturer"]; impl_->document.getManufacturer(value); return value.c_str(); }
const char* HorosSRDocument::getPatientID() { auto& value = impl_->strings["getPatientID"]; impl_->document.getPatientID(value); return value.c_str(); }
const char* HorosSRDocument::getPatientsBirthDate() { auto& value = impl_->strings["getPatientsBirthDate"]; impl_->document.getPatientBirthDate(value); return value.c_str(); }
const char* HorosSRDocument::getPatientsName() { auto& value = impl_->strings["getPatientsName"]; impl_->document.getPatientName(value); return value.c_str(); }
const char* HorosSRDocument::getSOPClassUID() { auto& value = impl_->strings["getSOPClassUID"]; impl_->document.getSOPClassUID(value); return value.c_str(); }
const char* HorosSRDocument::getSOPInstanceUID() { auto& value = impl_->strings["getSOPInstanceUID"]; impl_->document.getSOPInstanceUID(value); return value.c_str(); }
const char* HorosSRDocument::getSeriesDescription() { auto& value = impl_->strings["getSeriesDescription"]; impl_->document.getSeriesDescription(value); return value.c_str(); }
const char* HorosSRDocument::getSeriesInstanceUID() { auto& value = impl_->strings["getSeriesInstanceUID"]; impl_->document.getSeriesInstanceUID(value); return value.c_str(); }
const char* HorosSRDocument::getSeriesNumber() { auto& value = impl_->strings["getSeriesNumber"]; impl_->document.getSeriesNumber(value); return value.c_str(); }
const char* HorosSRDocument::getSpecificCharacterSet() { auto& value = impl_->strings["getSpecificCharacterSet"]; impl_->document.getSpecificCharacterSet(value); return value.c_str(); }
const char* HorosSRDocument::getStudyInstanceUID() { auto& value = impl_->strings["getStudyInstanceUID"]; impl_->document.getStudyInstanceUID(value); return value.c_str(); }
OFCondition HorosSRDocument::setAccessionNumber(const OFString& value) { return impl_->document.setAccessionNumber(value); }
OFCondition HorosSRDocument::setContentDate(const OFString& value) { return impl_->document.setContentDate(value); }
OFCondition HorosSRDocument::setContentTime(const OFString& value) { return impl_->document.setContentTime(value); }
OFCondition HorosSRDocument::setInstanceNumber(const OFString& value) { return impl_->document.setInstanceNumber(value); }
OFCondition HorosSRDocument::setManufacturer(const OFString& value) { return impl_->document.setManufacturer(value); }
OFCondition HorosSRDocument::setPatientID(const OFString& value) { return impl_->document.setPatientID(value); }
OFCondition HorosSRDocument::setPatientsBirthDate(const OFString& value) { return impl_->document.setPatientBirthDate(value); }
OFCondition HorosSRDocument::setPatientsName(const OFString& value) { return impl_->document.setPatientName(value); }
OFCondition HorosSRDocument::setPatientsSex(const OFString& value) { return impl_->document.setPatientSex(value); }
OFCondition HorosSRDocument::setReferringPhysiciansName(const OFString& value) { return impl_->document.setReferringPhysicianName(value); }
OFCondition HorosSRDocument::setSeriesDescription(const OFString& value) { return impl_->document.setSeriesDescription(value); }
OFCondition HorosSRDocument::setSeriesNumber(const OFString& value) { return impl_->document.setSeriesNumber(value); }
OFCondition HorosSRDocument::setSpecificCharacterSet(const OFString& value) { return impl_->document.setSpecificCharacterSet(value); }
OFCondition HorosSRDocument::setStudyDescription(const OFString& value) { return impl_->document.setStudyDescription(value); }
OFCondition HorosSRDocument::setStudyID(const OFString& value) { return impl_->document.setStudyID(value); }

DSRCodedEntryValue HorosSRItem::getConceptName() const { return static_cast<DSRContentItem*>(item_)->getConceptName(); }
OFString HorosSRItem::getStringValue() const { return static_cast<DSRContentItem*>(item_)->getStringValue(); }
HorosSRImageReference HorosSRItem::getImageReference() const {
    const auto& image = static_cast<DSRContentItem*>(item_)->getImageReference();
    HorosSRImageReference result(image.getSOPClassUID(), image.getSOPInstanceUID());
    result.getFrameList() = image.getFrameList();
    return result;
}
OFCondition HorosSRItem::setConceptName(const DSRCodedEntryValue& value) { return static_cast<DSRContentItem*>(item_)->setConceptName(value); }
OFCondition HorosSRItem::setStringValue(const OFString& value) { return static_cast<DSRContentItem*>(item_)->setStringValue(value); }
OFCondition HorosSRItem::setImageReference(const HorosSRImageReference& value) {
    DSRImageReferenceValue image(value.getSOPClassUID(), value.getSOPInstanceUID());
    image.getFrameList() = value.getFrameList();
    return static_cast<DSRContentItem*>(item_)->setImageReference(image);
}
HorosSRItem HorosSRTree::getCurrentContentItem() { return HorosSRItem(&static_cast<DSRDocumentTree*>(tree_)->getCurrentContentItem()); }
size_t HorosSRTree::addContentItem(DSRTypes::E_RelationshipType relation, DSRTypes::E_ValueType value, DSRTypes::E_AddMode mode) { return static_cast<DSRDocumentTree*>(tree_)->addContentItem(relation, value, mode); }
size_t HorosSRTree::goUp() { return static_cast<DSRDocumentTree*>(tree_)->goUp(); }
size_t HorosSRTree::gotoRoot() { return static_cast<DSRDocumentTree*>(tree_)->gotoRoot(); }
size_t HorosSRTree::iterate() { return static_cast<DSRDocumentTree*>(tree_)->iterate(); }
size_t HorosSRTree::gotoNamedNode(const DSRCodedEntryValue& value, OFBool root, OFBool deep) { return static_cast<DSRDocumentTree*>(tree_)->gotoNamedNode(value, root, deep); }
size_t HorosSRTree::gotoNextNamedNode(const DSRCodedEntryValue& value, OFBool deep) { return static_cast<DSRDocumentTree*>(tree_)->gotoNextNamedNode(value, deep); }
void HorosSRTree::clear() { static_cast<DSRDocumentTree*>(tree_)->clear(); }
OFString HorosSRTree::currentImageSOPInstanceUID() const {
    const auto& item = static_cast<DSRDocumentTree*>(tree_)->getCurrentContentItem();
    if (item.getValueType() != DSRTypes::VT_Image) return "";
    return item.getImageReference().getSOPInstanceUID();
}
