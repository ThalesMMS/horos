#!/usr/bin/env python3
"""Real SR round trip and series icons through the application-owned adapters."""
import subprocess
import tempfile
from pathlib import Path
from dcmtk_build import ROOT, dcmtk_flags

code = r'''
#include "HorosStructuredReportBridge.h"
#include "HorosDicomDirIcons.h"
#include <dcmtk/dcmdata/dcuid.h>
#include <cassert>
#include <cstring>
#include <sstream>
#include <vector>
#include <unistd.h>
void check(OFCondition condition){if(condition.bad()){fprintf(stderr,"%s\n",condition.text());exit(1);}}
void inspect(DcmDirectoryRecord&record,int&series,int&images){
 if(record.getRecordType()==ERT_Series){
  ++series;DcmItem*icon=NULL;check(record.findAndGetSequenceItem(DCM_IconImageSequence,icon,0));assert(icon);
  Uint16 rows=0,columns=0;check(icon->findAndGetUint16(DCM_Rows,rows));check(icon->findAndGetUint16(DCM_Columns,columns));
  assert(rows==128&&columns==128);const Uint8*pixels=NULL;unsigned long length=0;
  check(icon->findAndGetUint8Array(DCM_PixelData,pixels,&length));assert(length==128*128);
  bool varied=false;for(unsigned long i=1;i<length;i++)if(pixels[i]!=pixels[0])varied=true;assert(varied);
 }
 if(record.getRecordType()==ERT_Image)++images;
 for(unsigned long i=0;i<record.cardSub();i++)inspect(*record.getSub(i),series,images);
}
int main(int argc,char**argv){assert(argc==2&&chdir(argv[1])==0);
 HorosSRDocument report(DSRTypes::DT_EnhancedSR);
 check(report.setPatientsName("SYNTHETIC^SR"));check(report.setPatientID("LOCAL371"));
 check(report.setSpecificCharacterSetType(DSRTypes::CS_Latin1));
 check(report.setSeriesDescription("S\351rie"));
 auto tree=report.getTree();assert(tree.addContentItem(DSRTypes::RT_isRoot,DSRTypes::VT_Container));
 check(tree.getCurrentContentItem().setConceptName(DSRCodedEntryValue("18748-4","LN","Diagnostic imaging study")));
 assert(tree.addContentItem(DSRTypes::RT_contains,DSRTypes::VT_Text,DSRTypes::AM_belowCurrent));
 check(tree.getCurrentContentItem().setConceptName(DSRCodedEntryValue("121106","DCM","Comment")));
 check(tree.getCurrentContentItem().setStringValue("Synthetic text"));
 assert(tree.addContentItem(DSRTypes::RT_contains,DSRTypes::VT_Image));
 check(tree.getCurrentContentItem().setConceptName(DSRCodedEntryValue("111030","DCM","Image Region")));
 HorosSRImageReference reference(UID_UltrasoundMultiframeImageStorage,"1.2.826.0.1.3680043.8.498.37199");
 reference.getFrameList().addItem(2);reference.getFrameList().addItem(4);
 check(tree.getCurrentContentItem().setImageReference(reference));
 check(report.completeDocument(""));assert(report.containsExtendedCharacters());
 check(report.setSpecificCharacterSetType(DSRTypes::CS_Latin1));
 DcmDataset dataset;check(report.write(dataset));
 HorosSRDocument decoded;check(decoded.read(dataset));
 assert(!strcmp(decoded.getPatientsName(),"SYNTHETIC^SR"));
 const char*patient=decoded.getPatientsName();const char*title=decoded.getSeriesDescription();
 assert(!strcmp(patient,"SYNTHETIC^SR")&&!strcmp(title,"S\351rie"));
 auto read=decoded.getTree();read.gotoRoot();bool found=false;
 do{if(read.currentImageSOPInstanceUID()==reference.getSOPInstanceUID()){
  const auto frames=read.getCurrentContentItem().getImageReference();
  std::ostringstream a,b;check(frames.getFrameList().print(a));check(reference.getFrameList().print(b));
  assert(a.str()==b.str());found=true;
 }}while(read.iterate());assert(found);
 DicomDirInterface directory;directory.disableConsistencyCheck();directory.disableTransferSyntaxCheck();directory.enableInventMode(OFTrue);
 check(directory.createNewDicomDir(DicomDirInterface::AP_USBandFlashJPEG,"DICOMDIR","FIXTURE"));
 for(int n=0;n<6;n++){
  DcmFileFormat file;auto*d=file.getDataset();char uid[80],path[20];snprintf(path,sizeof(path),"IM%06d",n);
  snprintf(uid,sizeof(uid),"1.2.826.0.1.3680043.8.498.371.%d",n+1);
  d->putAndInsertString(DCM_SOPClassUID,UID_CTImageStorage);d->putAndInsertString(DCM_SOPInstanceUID,uid);
  d->putAndInsertString(DCM_StudyInstanceUID,"1.2.826.0.1.3680043.8.498.371.100");
  d->putAndInsertString(DCM_SeriesInstanceUID,n<3?"1.2.826.0.1.3680043.8.498.371.101":"1.2.826.0.1.3680043.8.498.371.102");
  d->putAndInsertString(DCM_PatientName,"SYNTHETIC^DIR");d->putAndInsertString(DCM_PatientID,"LOCAL371");
  d->putAndInsertString(DCM_StudyDate,"20260912");d->putAndInsertString(DCM_StudyTime,"120000");
  d->putAndInsertString(DCM_StudyID,"371");d->putAndInsertString(DCM_Modality,"CT");
  d->putAndInsertString(DCM_SeriesNumber,n<3?"1":"2");d->putAndInsertString(DCM_InstanceNumber,std::to_string(n+1).c_str());
  d->putAndInsertUint16(DCM_Rows,32);d->putAndInsertUint16(DCM_Columns,33);d->putAndInsertUint16(DCM_SamplesPerPixel,1);
  d->putAndInsertString(DCM_PhotometricInterpretation,"MONOCHROME2");
  d->putAndInsertUint16(DCM_BitsAllocated,16);d->putAndInsertUint16(DCM_BitsStored,12);d->putAndInsertUint16(DCM_HighBit,11);d->putAndInsertUint16(DCM_PixelRepresentation,0);
  std::vector<Uint16>pixels(32*33);for(size_t i=0;i<pixels.size();i++)pixels[i]=i*(n+1)%4096;
  d->putAndInsertUint16Array(DCM_PixelData,pixels.data(),pixels.size());check(file.saveFile(path,EXS_LittleEndianExplicit));
  check(directory.addDicomFile(path,"."));
 }
 check(directory.writeDicomDir());HorosDicomDirIcons icons;check(icons.addSeriesIcons("DICOMDIR","."));
 DcmDicomDir written("DICOMDIR");check(written.error());int series=0,images=0;inspect(written.getRootRecord(),series,images);assert(series==2&&images==6);
 puts("PASS: SR metadata, content and referenced frames round-trip; two real 128x128 series icons index six images");
}
'''
with tempfile.TemporaryDirectory(prefix='horos-sr-directory-') as directory:
    p=Path(directory); (p/'main.cc').write_text(code)
    subprocess.run(['xcrun', 'clang++', '-std=c++11', str(p/'main.cc'),
        str(ROOT/'Horos/Sources/HorosStructuredReportBridge.cpp'),
        *dcmtk_flags('dcmsr', 'dcmjpeg', 'dcmimage', 'dcmimgle', 'ijg8', 'ijg12', 'ijg16'),
        '-lxml2', '-o', str(p/'check')], check=True)
    subprocess.run([str(p/'check'), str(p)], check=True)
