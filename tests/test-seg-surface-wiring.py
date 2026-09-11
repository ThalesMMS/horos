#!/usr/bin/env python3
"""#377 A surfaces reuse the #376 store and are compiled into Horos."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []
source = (root / 'Horos/Sources/HorosSEGSurface.swift').read_text()
seg = (root / 'Horos/Sources/DicomSEG.swift').read_text()
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text()

if 'HorosSEGSurface.swift' not in pbx:
    failures.append('HorosSEGSurface.swift is not in the Xcode project')
if 'HorosSEGSurface.swift in Sources' not in pbx:
    failures.append('HorosSEGSurface.swift is not in a Sources build phase')
if 'HorosSEGSurface' not in seg:
    failures.append('DicomSEG.swift does not point surface extraction at HorosSEGSurface')
if 'func remove(segment' not in seg:
    failures.append('DicomSEGStore is missing remove(segment:) for shared deletion')
if 'usesSharedSEGModel = true' not in source:
    failures.append('HorosSEGSurface must reuse the shared SEG model')
if 'buildsParallelROIStore = false' not in source:
    failures.append('HorosSEGSurface must not claim a parallel ROI store')
if 'nativeViewerOverlayImplemented = false' not in source:
    failures.append('native MPR/3D/scout overlay must stay an explicit gap')
if 'simplificationForcesSphericalTopology = false' not in source:
    failures.append('refinement must refuse spherical topology')
for view in ('.planar', '.mpr', '.volume', '.scout'):
    if view not in source:
        failures.append('missing shared view kind %s' % view)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    raise SystemExit(1)
print('ok: HorosSEGSurface is wired to the shared SEG store without a native overlay claim')
