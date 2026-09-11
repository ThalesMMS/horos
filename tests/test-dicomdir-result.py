#!/usr/bin/env python3
"""Exercise the actual Objective-C++ error boundary with controlled DCMTK outcomes."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/DicomDir.mm').read_bytes().decode('utf-8')
body=s[s.index('@implementation DicomDir'):]
code=r'''
#import <Foundation/Foundation.h>
#include <list>
#include <string>
#include <stdexcept>
#include <iostream>
#include <sys/stat.h>
#define N2LogException(e) ((void)0)
#define OFTrue true
#define DEFAULT_DICOMDIR_NAME "DICOMDIR"
#define DEFAULT_FILESETID "TEST"
#define DEFAULT_DESCRIPTOR_CHARSET ""
#define EET_ExplicitLength 0
#define EGL_withoutGL 0
#define OFList std::list
#define OFListIterator(T) std::list<T>::iterator
using OFString=std::string;
static int scenario;
static NSString *outputPath;
class OFCondition { bool ok; public: OFCondition(bool value=true):ok(value){} bool good(){return ok;} bool bad(){return !ok;} const char* text(){return "controlled DCMTK failure";} };
class DicomDirImageImplementation {};
class DicomDirInterface {
public:
 enum {AP_USBandFlashJPEG};
 DicomDirInterface(){if(scenario==4)throw std::runtime_error("controlled C++ failure");}
 void disableConsistencyCheck(){} void disableTransferSyntaxCheck(){} void enableInventMode(bool){}
 void enableOneIconPerSeriesMode(){} void setIconSize(int){} void addImageSupport(void*){}
 OFCondition createNewDicomDir(int,const char* path,const char*){outputPath=[NSString stringWithUTF8String:path];return OFCondition(scenario!=1);}
 void setFilesetDescriptor(void*,const char*){}
 OFCondition addDicomFile(const char* file,const char*){return OFCondition(scenario!=2 && std::string(file)=="IMAGE001");}
 OFCondition writeDicomDir(int,int){if(scenario!=3)[@"new index" writeToFile:outputPath atomically:YES encoding:NSUTF8StringEncoding error:NULL];return OFCondition(scenario!=3);}
};
class HorosDicomDirIcons {public: OFCondition addSeriesIcons(const char*,const char*){return OFCondition(scenario!=5);}};
class OFStandard {public:static void searchDirectoryRecursively(const char*,std::list<std::string>&files,void*,const char*){for(const char* file:{"IMAGE001","DICOMDIR","DICOMDIR.BAK",".DS_Store","SUB/._IMAGE001",".horos-zip-stale/archive.zip"})files.push_back(file);}};
@interface DicomDir:NSObject
+ (BOOL)createDicomDirAtDir:(NSString*)path error:(NSError**)error;
@end
BODY
int main(int argc,char **argv){@autoreleasepool{
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 for(scenario=0;scenario<6;scenario++) {
  NSString *folder=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"%d",scenario]];
  [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:NULL];
  NSString *index=[folder stringByAppendingPathComponent:@"DICOMDIR"];
  [@"old index" writeToFile:index atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  NSError *error=nil;BOOL result=[DicomDir createDicomDirAtDir:folder error:&error];
  if(![[NSString stringWithContentsOfFile:index encoding:NSUTF8StringEncoding error:NULL] isEqual:scenario==0?@"new index":@"old index"]){fputs("FAIL previous index preservation\n",stderr);return 1;}
  for(NSString *name in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:folder error:NULL])if([name hasPrefix:@".horos-zip-"]){fputs("FAIL staging cleanup\n",stderr);return 1;}
  if(result!=(scenario==0) || (!!error)!=(scenario!=0) || (error && !error.localizedFailureReason.length)) {
   fprintf(stderr,"FAIL scenario %d result %d error %s\n",scenario,result,[[error description] UTF8String]);return 1;
  }
 }
 puts("PASS: DICOMDIR success, create/add/write failures and C++ exception produce correct result/error");
}}
'''.replace('BODY',body)
with tempfile.TemporaryDirectory(prefix='horos-dicomdir-result-') as folder:
 p=Path(folder);(p/'test.mm').write_text(code)
 subprocess.run(['xcrun','swiftc','-emit-library','-emit-objc-header','-emit-objc-header-path',str(p/'Archive-Swift.h'),'-module-name','Archive',str(root/'Horos/Sources/ExportArchive.swift'),'-o',str(p/'libArchive.dylib')],check=True)
 subprocess.run(['xcrun','clang++','-include',str(p/'Archive-Swift.h'),'-L'+str(p),'-lArchive','-Wl,-rpath,'+str(p),'-std=c++11','-fsanitize=address',str(p/'test.mm'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'files')],check=True)
