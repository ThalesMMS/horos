#!/usr/bin/env python3
"""Exercise the production file validator and directory-collision method with real files."""
from pathlib import Path
import hashlib
import sqlite3
import subprocess
import tempfile
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'Nitrogen/Sources/NSFileManager+N2.mm').read_text()
start = source.index('-(NSString*)confirmDirectoryAtPath:(NSString*)dirPath subDirectory:')
end = source.index('\n-(NSString*)confirmNoIndexDirectoryAtPath:', start)
code = r'''
#import "HorosDatabaseFileValidation.h"
// HorosStorageFailure is Swift, and this compiles one extracted method on its
// own. The stub stands in for it so the method under test can be built here;
// what it returns is checked by tests/test-external-volume-storage.py, which
// drives the real one.
@interface HorosStorageFailure : NSObject
+(NSString*)reasonForError:(NSError*)error path:(NSString*)path;
@end
@implementation HorosStorageFailure
+(NSString*)reasonForError:(NSError*)error path:(NSString*)path {
 return [NSString stringWithFormat:@"cannot create %@: %@", path, error.localizedDescription];
}
@end
@interface NSFileManager(TestDirectory)
-(NSString*)confirmDirectoryAtPath:(NSString*)path;
@end
@implementation NSFileManager(TestDirectory)
METHODS
@end
int main(int argc, const char **argv) { @autoreleasepool {
 NSString *mode = @(argv[1]), *path = @(argv[2]);
 if ([mode isEqual:@"validate"]) return HorosIsDatabaseFile(path) ? 0 : 1;
 if ([mode isEqual:@"directory"]) {
  @try { [NSFileManager.defaultManager confirmDirectoryAtPath:path]; return 0; }
  @catch (NSException *e) { return 1; }
 }
 NSManagedObjectModel *model = [NSManagedObjectModel new];
 NSMutableArray *entities = [NSMutableArray new];
 for (NSString *name in @[@"Study", @"Series", @"Image", @"Album"]) {
  NSEntityDescription *entity = [NSEntityDescription new];
  entity.name = name; entity.managedObjectClassName = @"NSManagedObject";
  NSAttributeDescription *attribute = [NSAttributeDescription new];
  attribute.name = @"fixtureValue"; attribute.attributeType = NSStringAttributeType;
  entity.properties = @[attribute]; [entities addObject:entity];
 }
 model.entities = entities;
 if (argc > 3) model = [[NSManagedObjectModel alloc] initWithContentsOfURL:[NSURL fileURLWithPath:@(argv[3])]];
 if (!model) return 3;
 NSPersistentStoreCoordinator *coordinator = [[NSPersistentStoreCoordinator alloc] initWithManagedObjectModel:model];
 NSError *error = nil;
 NSPersistentStore *store = [coordinator addPersistentStoreWithType:NSSQLiteStoreType configuration:nil
  URL:[NSURL fileURLWithPath:path] options:@{NSSQLitePragmasOption:@{@"journal_mode":@"DELETE"}} error:&error];
 if (!store) { NSLog(@"%@",error); return 2; }
 return [coordinator removePersistentStore:store error:&error] ? 0 : 2;
}}
'''.replace('METHODS', source[start:end])
with tempfile.TemporaryDirectory(prefix='horos-file-safety-') as folder:
    work = Path(folder)
    (work / 'test.m').write_text(code)
    binary = work / 'test'
    subprocess.run(['xcrun', 'clang', '-I', str(root / 'Horos/Sources'), str(work / 'test.m'),
                    '-framework', 'Foundation', '-framework', 'CoreData', '-lsqlite3', '-o', str(binary)], check=True)
    def run(mode, path, expected):
        result = subprocess.run([str(binary), mode, str(path)], capture_output=True)
        assert result.returncode == expected, result.stderr.decode()
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    text = work / 'external.sql'
    text.write_text('CREATE TABLE valuable (id INTEGER);\n')
    external = work / 'external' / 'Horos Data' / 'Database.sql'
    external.parent.mkdir(parents=True)
    with sqlite3.connect(external) as connection:
        connection.execute('create table valuable (id integer)')
        connection.execute('insert into valuable values (42)')
    malformed = work / 'malformed' / 'Horos Data' / 'Database.sql'
    malformed.parent.mkdir(parents=True)
    malformed.write_bytes(b'SQLite format 3\0' + b'not a database' * 40)
    for path in (text, external, malformed):
        before = digest(path)
        run('validate', path, 1)
        run('directory', path, 1)
        run('directory', path / 'Horos Data' / 'nested', 1)
        assert path.is_file() and digest(path) == before, str(path)
    valid = work / 'valid' / 'Horos Data' / 'Database.sql'
    valid.parent.mkdir(parents=True)
    run('create', valid, 0)
    before = digest(valid)
    run('validate', valid, 0)
    assert digest(valid) == before
    renamed = valid.with_name('other.sql')
    renamed.write_bytes(valid.read_bytes())
    run('validate', renamed, 1)
    run('validate', work / 'missing.sql', 1)
    run('directory', work / 'new' / 'nested', 0)
    assert (work / 'new' / 'nested').is_dir()
    if len(sys.argv) > 1:
        models = sorted(Path(sys.argv[1]).glob('OsiriXDB*.mom'))
        assert models, 'No compiled Horos models found'
        for model in models:
            historical = work / model.stem / 'Horos Data' / 'Database.sql'
            historical.parent.mkdir(parents=True)
            subprocess.run([str(binary), 'create', str(historical), str(model)], check=True)
            before = digest(historical)
            run('validate', historical, 0)
            assert digest(historical) == before
            print('PASS model:', model.name)
    print('PASS: textual SQL, external SQLite, malformed SQLite, missing/renamed files, Core Data metadata, and direct/parent directory collisions')
