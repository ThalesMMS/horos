#!/usr/bin/env python3
"""Execute production remote-history selection against controlled query responses."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
a=s.index('+ (NSArray*) queryStudiesForPatient:');b=s.index('+ (QueryController*) currentQueryController',a)
method=s[a:b]
# Production file uses MRC; compile the harness in MRC as well.
code=r'''
#import <Foundation/Foundation.h>
#define check(...) NSCAssert((__VA_ARGS__),@"failed: %s",#__VA_ARGS__)
static NSString *PatientID=@"PatientID", *PatientBirthDate=@"PatientBirthDate";
@interface DicomStudy:NSObject
@property(copy) NSString *name;
@property(copy) NSString *patientID;
@property(retain) NSDate *dateOfBirth;
@end
@implementation DicomStudy
@end
@interface DCMTKStudyQueryNode:DicomStudy
@end
@implementation DCMTKStudyQueryNode
@end
@interface DicomFile:NSObject
+ (NSString*)NSreplaceBadCharacter:(NSString*)value;
@end
@implementation DicomFile
+ (NSString*)NSreplaceBadCharacter:(NSString*)value { return value; }
@end
static NSArray *responses;
static NSDictionary *sentFilters;
static int queryCount;
@interface QueryController:NSObject
+ (NSMutableArray*)queryStudiesForFilters:(NSDictionary*)filters servers:(NSArray*)servers showErrors:(BOOL)errors;
+ (NSArray*)queryStudiesForPatient:(DicomStudy*)study usePatientID:(BOOL)i usePatientName:(BOOL)n usePatientBirthDate:(BOOL)b servers:(NSArray*)servers showErrors:(BOOL)e;
@end
@implementation QueryController
+ (NSMutableArray*)queryStudiesForFilters:(NSDictionary*)filters servers:(NSArray*)servers showErrors:(BOOL)errors {
 queryCount++;sentFilters=[filters copy];return [responses mutableCopy];
}
METHOD
@end
static DCMTKStudyQueryNode *node(NSString *id, NSString *name, NSDate *date) {
 DCMTKStudyQueryNode *n=[DCMTKStudyQueryNode new];n.patientID=id;n.name=name;n.dateOfBirth=date;return n;
}
static NSArray *query(DicomStudy *s,BOOL i,BOOL n,BOOL b) {
 return [QueryController queryStudiesForPatient:s usePatientID:i usePatientName:n usePatientBirthDate:b servers:@[] showErrors:NO];
}
int main(void) { @autoreleasepool {
 [NSTimeZone setDefaultTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
 NSDate *birth=[NSDate dateWithTimeIntervalSince1970:946684800];
 NSDate *other=[birth dateByAddingTimeInterval:86400];
 DicomStudy *target=node(@"QA*?",@"QA Patient",birth);
 id good=node(@"QA*?",@"QA Patient",birth);
 id wrongID=node(@"QA123",@"QA Patient",birth);
 id missingID=node(nil,@"QA Patient",birth);
 id wrongBirth=node(@"QA*?",@"QA Patient",other);
 id missingBirth=node(@"QA*?",@"QA Patient",nil);
 id wrongName=node(@"QA*?",@"Other Patient",birth);
 responses=@[good,wrongID,missingID,wrongBirth,missingBirth,wrongName];
 check([query(target,YES,YES,YES) isEqual:@[good]]);
 check([sentFilters[PatientID] isEqual:@"QA*?"] && [sentFilters[PatientBirthDate] isEqual:birth]);
 check([query(target,YES,NO,YES) isEqual:@[good,wrongName]]);
 check([query(target,YES,YES,NO) isEqual:@[good,wrongBirth,missingBirth]]);
 check([query(target,NO,YES,YES) isEqual:@[good,wrongID,missingID]]);
 int before=queryCount;
 check(query(target,NO,NO,NO)==nil);check(query(target,NO,YES,NO)==nil);
 check(query(node(nil,target.name,birth),YES,YES,YES)==nil);
 check(query(node(target.patientID,nil,birth),YES,YES,YES)==nil);
 check(query(node(target.patientID,target.name,nil),YES,YES,YES)==nil);
 check(queryCount==before);
 id sameDay=node(target.patientID,target.name,[birth dateByAddingTimeInterval:3600]);
 responses=@[sameDay];check([query(target,YES,YES,YES) isEqual:@[sameDay]]);
 responses=@[];check(query(target,YES,YES,YES).count==0);
 NSLog(@"PASS: remote history validates enabled identity fields; wrong/missing IDs and birthdates, wildcard IDs, optional name/birthdate, empty responses and invalid query guards");
} }
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-remote-comparative-') as t:
 p=Path(t);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
