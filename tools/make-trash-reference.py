#!/usr/bin/env python3
"""Write the reference implementation the #613 measurement compares against.

The revision before #613 is faster only because it did what the issue removes:
it chose ~/.Trash by hand and deleted whatever already had the name. The correct
behaviour is the system's, so the valid reference is the system call itself.
This takes NSFileManager+N2.mm as given and reduces both Trash methods to a bare
-trashItemAtURL:resultingItemURL:error: call, nothing around it, so compiling it
with the app's command and comparing it with the delivered file measures only
what the delivered wrapper adds.

    python3 tools/make-trash-reference.py <NSFileManager+N2.mm> <output.mm>
"""
import re
import sys
from pathlib import Path

source, output = Path(sys.argv[1]), Path(sys.argv[2])
text = source.read_bytes().decode("latin1")
start = text.index("- (void)moveItemAtPathToTrash: (NSString*) path\n")
end = text.index("-(NSString*)findSystemFolderOfType:")
reference = '''- (void)moveItemAtPathToTrash: (NSString*) path
{
    [self trashItemAtURL:[NSURL fileURLWithPath:path] resultingItemURL:NULL error:NULL];
}

- (BOOL)moveItemAtPathToTrash:(NSString*)path resultingPath:(NSString**)resultingPath error:(NSError**)error
{
    NSURL *resulting = nil;
    BOOL ok = [self trashItemAtURL:[NSURL fileURLWithPath:path] resultingItemURL:&resulting error:error];
    if (resultingPath) *resultingPath = resulting.path;
    return ok;
}

'''
output.write_bytes((text[:start] + reference + text[end:]).encode("latin1"))
print(f"reference written to {output}")
