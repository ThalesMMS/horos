#!/usr/bin/env python3
"""Build a synthetic native plugin against the built public Horos framework.

The output is local; this command never installs into the user's plugin folder.
Pass --proof-directory inside local-validation. A preexisting event file makes
the plugin refuse to arm, preserving old evidence across launches.
"""
import argparse
from pathlib import Path
import plistlib
import subprocess

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
p.add_argument('--proof-directory', type=Path, required=True)
p.add_argument('--products', type=Path, default=root/'build/Build/Products/Release')
a = p.parse_args()
proof = a.proof_directory.resolve()
if root/'local-validation' not in proof.parents:
    p.error('proof directory must be inside this checkout/local-validation')
if a.output.exists():
    p.error('output must not exist')
proof.mkdir(parents=True, exist_ok=True)
bundle = a.output.resolve()
executable = bundle/'Contents/MacOS/QAHorosLifetime'
executable.parent.mkdir(parents=True)
subprocess.run(['xcrun','clang','-fno-objc-arc','-O2','-bundle','-undefined','dynamic_lookup',
    '-F'+str(a.products.resolve()),'-framework','AppKit',
    str(root/'tools/probe-planar-host-lifetime.m'),'-o',str(executable)],check=True)
info = {'CFBundleExecutable':'QAHorosLifetime','CFBundleIdentifier':'org.horosproject.qa.lifetime373',
        'CFBundleName':'QAHorosLifetime','CFBundleVersion':'1.0','CFBundlePackageType':'BNDL',
        'NSPrincipalClass':'QAHorosLifetime','pluginType':'imageFilter',
        'MenuTitles':['Capture Lifetime Pixels','Capture Lifetime Registry'],
        'ProofDirectory':str(proof)}
(bundle/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
subprocess.run(['codesign','--force','--sign','-',str(bundle)],check=True,capture_output=True)
print(bundle)
