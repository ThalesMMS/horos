#!/usr/bin/env python3
"""Where the Nitrogen helpers #618 considers removing are still named (#618).

The candidates are what the donor fork removed from Nitrogen in bd47b643 (classes
and methods without use there) and 6d5f2076 (the collection helpers behind the
preference copies). For each, lists every textual use outside its own files in
the sources the project builds (Objective-C, Swift, headers, XIBs), string
lookups (NSClassFromString, NSSelectorFromString, objc_getClass, @selector),
project file references, whether its header is exported to the plugin SDK
(Horos/Scripts/Horos/API-Headers.pl copies every header of Nitrogen/Sources into
Horos.framework/Headers), whether the embedded plugins' binaries name it, and
whether extra plugin source folders (--plugin-sources) name it. Receivers are not
resolved here: a selector hit is a place to read, and the build resolves the
static ones.

    python3 tools/inventory-nitrogen-candidates.py --revision <sha> [--plugin-sources DIR ...] [--json out.json]

--revision scans the tree of that commit (the state before the removal); without
it, the working tree.
"""
import argparse
import json
import re
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ["Horos", "Nitrogen", "Preference Panes", "DicomImporter", "Decompress", "FinderPreview", "DICOMPrint",
          "API", "DCM Framework", "MSRG", "LetsMoveAndDock", "cocoahttpserver", "FeedbackReporter", "NSFont_OpenGL"]
PROJECTS = ["Horos.xcodeproj/project.pbxproj", "Nitrogen/Nitrogen.xcodeproj/project.pbxproj"]
SUFFIXES = {".h", ".m", ".mm", ".swift", ".xib", ".pch", ".c", ".cpp", ".html", ".js", ".plist", ".py", ".sh",
            ".applescript"}


def candidate(name, kind, files, pattern, origin, definition=None):
    # `definition`: how its own files declare it, where the use pattern names a receiver.
    return {"name": name, "kind": kind, "files": files, "pattern": pattern, "origin": origin,
            "definition": definition or pattern}


BITMAP = ["NSBitmapImageRep+N2.h", "NSBitmapImageRep+N2.mm"]
STRING = ["NSString+N2.h", "NSString+N2.mm"]
DATA = ["NSData+N2.h", "NSData+N2.mm"]
SHELL = ["N2Shell.h", "N2Shell.mm"]
CANDIDATES = [
    candidate("N2CSV", "class", ["N2CSV.h", "N2CSV.mm"], r"\bN2CSV\b", "bd47b643"),
    candidate("N2Pair", "class", ["N2Pair.h", "N2Pair.mm"], r"\bN2Pair\b", "bd47b643"),
    candidate("N2SingletonObject", "class", ["N2SingletonObject.h", "N2SingletonObject.mm"], r"\bN2SingletonObject\b",
              "bd47b643"),
    candidate("N2Task", "class", ["N2Task.h", "N2Task.mm"], r"\bN2Task\b", "bd47b643"),
    candidate("NSURL+N2 (N2URLParts, -parts, +URLWithParts:)", "class and category", ["NSURL+N2.h", "NSURL+N2.mm"],
              r"\bN2URLParts\b|URLWithParts:|NSURL\+N2\.h|\bparts\]|\.parts\b", "bd47b643"),
    candidate("ISO8601DateFormatter (Nitrogen)", "class", ["ISO8601DateFormatter.h", "ISO8601DateFormatter.m"],
              r"ISO8601DateFormatter\.h|\[ISO8601DateFormatter\b|\[\[ISO8601DateFormatter\b", "bd47b643"),
    candidate("+[N2Shell execute:...]", "selector", SHELL, r"N2Shell\s+execute:|self\s+execute:", "bd47b643",
              r"\+\s*\(NSString\s*\*\)\s*execute:"),
    candidate("+[N2Shell hostname]", "selector", SHELL, r"N2Shell\s+hostname\]|N2Shell\.hostname\b", "bd47b643",
              r"\+\s*\(NSString\s*\*\)\s*hostname\b"),
    candidate("+[N2Shell ip]", "selector", SHELL, r"N2Shell\s+ip\]|N2Shell\.ip\b", "bd47b643",
              r"\+\s*\(NSString\s*\*\)\s*ip\b"),
    candidate("+[N2Shell mac]", "selector", SHELL, r"N2Shell\s+mac\]|N2Shell\.mac\b", "bd47b643",
              r"\+\s*\(NSString\s*\*\)\s*mac\b"),
    candidate("+[N2Shell userId]", "selector", SHELL, r"N2Shell\s+userId\]|N2Shell\.userId\b", "bd47b643",
              r"\+\s*\(int\)\s*userId\b"),
    candidate("+[N2Shell hostnameAwareOfSlowness:] (private)", "selector", SHELL, r"hostnameAwareOfSlowness:",
              "bd47b643"),
    candidate("-[NSBitmapImageRep repUsingColorSpaceName:]", "selector", BITMAP, r"repUsingColorSpaceName:", "bd47b643"),
    candidate("-[NSBitmapImageRep ATMask:]", "selector", BITMAP, r"\bATMask:", "bd47b643"),
    candidate("-[NSBitmapImageRep smoothen:]", "selector", BITMAP, r"\bsmoothen:", "bd47b643"),
    candidate("-[NSBitmapImageRep _spp] (private)", "selector", BITMAP, r"\b_spp\b", "bd47b643"),
    candidate("+[NSData dataWithBase64:]", "selector", DATA, r"dataWithBase64:", "bd47b643"),
    candidate("-[NSData initWithBase64:]", "selector", DATA, r"initWithBase64:", "bd47b643"),
    candidate("-[NSData base64]", "selector", DATA, r"\bbase64\]|\.base64\b", "bd47b643"),
    candidate("-[NSString markedString]", "selector", STRING, r"\bmarkedString\b", "bd47b643"),
    candidate("+[NSString sizeString:]", "selector", STRING, r"\bsizeString:", "bd47b643"),
    candidate("+[NSString dateString:]", "selector", STRING, r"\bdateString:", "bd47b643"),
    candidate("-[NSString stringByTrimmingStartAndEnd]", "selector", STRING, r"\bstringByTrimmingStartAndEnd\b",
              "bd47b643"),
    candidate("-[NSString urlEncodedString]", "selector", STRING, r"\burlEncodedString\b", "bd47b643"),
    candidate("-[NSString xmlEscapedString]", "selector", STRING, r"\bxmlEscapedString\b", "bd47b643"),
    candidate("-[NSString xmlUnescapedString]", "selector", STRING, r"\bxmlUnescapedString\b", "bd47b643"),
    candidate("-deepMutableCopy (NSArray, NSDictionary)", "selector",
              ["NSArray+N2.h", "NSArray+N2.mm", "NSDictionary+N2.h", "NSDictionary+N2.mm"], r"\bdeepMutableCopy\b",
              "6d5f2076"),
    candidate("-[NSDictionary objectForKey:ofClass:]", "selector", ["NSDictionary+N2.h", "NSDictionary+N2.mm"],
              r"(?<!SMTP_)objectForKey:[^\]]*ofClass:", "6d5f2076"),
    candidate("-[NSDictionary keyForObject:]", "selector",
              ["NSDictionary+N2.h", "NSDictionary+N2.mm", "NSMutableDictionary+N2.mm"], r"\bkeyForObject:", "6d5f2076"),
    candidate("-[NSMutableDictionary removeObject:]", "selector", ["NSMutableDictionary+N2.h", "NSMutableDictionary+N2.mm"],
              r"\bremoveObject:", "6d5f2076"),
    candidate("-[NSMutableDictionary setBool:forKey:]", "selector",
              ["NSMutableDictionary+N2.h", "NSMutableDictionary+N2.mm"], r"\bsetBool:[^\]]*forKey:", "6d5f2076"),
    candidate("NSMutableDictionary+N2.h", "header", ["NSMutableDictionary+N2.h", "NSMutableDictionary+N2.mm"],
              r"NSMutableDictionary\+N2\.h", "6d5f2076"),
]


def materialize(revision: str, destination: Path) -> Path:
    paths = [path for path in SEARCH + PROJECTS + ["Binaries/EmbeddedPlugins"]
             if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{revision}:{path}"],
                               capture_output=True).returncode == 0]
    archive = destination / "tree.tar"
    subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "-o", str(archive), revision, "--"] + paths,
                   check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(destination / "tree", filter="data")
    archive.unlink()
    return destination / "tree"


def sources(base: Path, folders):
    for folder in folders:
        root = base / folder
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in SUFFIXES:
                yield path


# Mach-O (thin and universal, both byte orders), binary property lists and nibs, XML.
CODE_AND_ARCHIVES = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce",
                     b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"bplist", b"<?xml")


def embedded_plugin_strings(base: Path):
    found = {}
    for archive in (base / "Binaries/EmbeddedPlugins").glob("*.zip"):
        with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(archive) as zipped:
            zipped.extractall(folder)
            text = []
            # zipfile does not restore the executable bit, and strings(1) finds words in
            # the bytes of an image: read the code and the property lists and nibs, by content.
            for path in Path(folder).rglob("*"):
                if path.is_file() and path.open("rb").read(8).startswith(CODE_AND_ARCHIVES):
                    output = subprocess.run(["strings", str(path)], capture_output=True, text=True, errors="replace")
                    text.append(output.stdout)
            found[archive.name] = "\n".join(text)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--revision")
    parser.add_argument("--plugin-sources", type=Path, action="append", default=[])
    parser.add_argument("--json", type=Path)
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="horos-nitrogen-inventory-") as temporary:
        base = materialize(arguments.revision, Path(temporary)) if arguments.revision else ROOT
        files = [(path.relative_to(base), path.read_bytes().decode("latin1")) for path in sources(base, SEARCH)]
        plugin_files = [(path, path.read_bytes().decode("latin1")) for folder in arguments.plugin_sources
                        for path in folder.rglob("*") if path.is_file()]
        projects = "\n".join((base / project).read_bytes().decode("latin1") for project in PROJECTS
                             if (base / project).exists())
        plugins = embedded_plugin_strings(base)
        exported = {path.name for path in (base / "Nitrogen/Sources").glob("*.h")}
        present = {path.name for path in (base / "Nitrogen/Sources").iterdir()}
    report = []
    for item in CANDIDATES:
        pattern = re.compile(item["pattern"])
        # The name a binary or a string lookup would carry: "execute:", "objectForKey:ofClass", "N2Task".
        bare = re.sub(r"^[-+]\[\w+\s+|\]$|\.\.\.", "", re.sub(r"\s*\(.*\)$", "", item["name"]))
        bare = bare.split(" ")[0].strip("-+").rstrip(":")
        word = re.compile(r"(?<![\w])" + re.escape(bare) + r"(?![\w])")
        uses, lookups, defined = [], [], False
        for path, text in files:
            if path.name in item["files"]:
                # Its own files still declare or implement it (a method outlives its file's removal).
                defined = defined or bool(re.search(item["definition"], text)) or item["kind"] in ("class", "class and category",
                                                                                                    "header")
                continue
            for number, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                if pattern.search(line):
                    uses.append(f"{path}:{number}: {stripped[:140]}")
                if re.search(r'(NSClassFromString|NSSelectorFromString|objc_getClass|sel_registerName)\(\s*@?"'
                             + re.escape(bare), line):
                    lookups.append(f"{path}:{number}")
        report.append({
            "candidate": item["name"], "kind": item["kind"], "origin": item["origin"],
            "present": any(name in present for name in item["files"]), "defined": defined, "uses": uses,
            "string_lookups": lookups,
            "project_references": len(re.findall(re.escape(item["files"][0]), projects)),
            "exported_to_plugin_sdk": any(name in exported for name in item["files"] if name.endswith(".h")),
            "embedded_plugins_naming_it": sorted(name for name, text in plugins.items()
                                                 if pattern.search(text) or word.search(text)),
            "plugin_sources_naming_it": sorted(str(path) for path, text in plugin_files
                                               if pattern.search(text) or word.search(text)),
        })
    print(f"# {'revision ' + arguments.revision if arguments.revision else 'working tree'}; "
          f"plugin sources: {[str(p) for p in arguments.plugin_sources] or 'none'}")
    for row in report:
        print(f"## {row['candidate']} ({row['kind']}, {row['origin']}){'' if row['defined'] else ' - not defined'}")
        print(f"  project references: {row['project_references']}, exported to the plugin SDK: {row['exported_to_plugin_sdk']}, "
              f"embedded plugins: {row['embedded_plugins_naming_it'] or 'none'}, "
              f"plugin sources: {row['plugin_sources_naming_it'] or 'none'}, string lookups: {row['string_lookups'] or 'none'}")
        for use in row["uses"] or ["(no use outside its own files)"]:
            print(f"  {use}")
    if arguments.json:
        arguments.json.write_text(json.dumps({"revision": arguments.revision, "candidates": report}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
