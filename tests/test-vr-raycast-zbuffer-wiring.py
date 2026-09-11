#!/usr/bin/env python3
"""The Horos ray-cast mapper sanitizes Z before CastRays; VTK is not rebuilt."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
mapper = (root / 'Horos/Sources/vtkHorosFixedPointVolumeRayCastMapper.cxx').read_text(encoding='latin1')
header = (root / 'Horos/Sources/vtkHorosFixedPointVolumeRayCastMapper.h').read_text(encoding='latin1')
guard = root / 'Horos/Sources/VRRayCastZBufferGuard.h'
swift = (root / 'Horos/Sources/VRRayCastZBuffer.swift').read_text(encoding='utf-8')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='latin1')
failures = []

if 'VRRayCastZBufferGuard.h' not in mapper:
    failures.append('mapper.cxx does not include VRRayCastZBufferGuard.h')
if 'SanitizeRayCastZBuffer' not in mapper:
    failures.append('mapper.cxx has no SanitizeRayCastZBuffer')
if 'SanitizeRayCastZBuffer' not in header:
    failures.append('mapper.h does not declare SanitizeRayCastZBuffer')

init_at = mapper.find('this->PerSubVolumeInitialization')
cast_at = mapper.find('this->RenderSubVolume()')
sanitize_at = mapper.find('SanitizeRayCastZBuffer')
if init_at < 0 or cast_at < 0 or sanitize_at < 0:
    failures.append('cannot locate PerSubVolumeInitialization / RenderSubVolume / sanitize')
elif not (init_at < sanitize_at < cast_at):
    failures.append('Z-buffer sanitizer must run after CaptureZBuffer and before CastRays')

if 'HorosRayCastZBufferIsUsable' not in mapper:
    failures.append('mapper does not call HorosRayCastZBufferIsUsable')
if 'UseZBufferOff' not in mapper:
    failures.append('invalid Z buffer is not turned off')
if 'VTK/' in mapper and 'vtkFixedPointRayCastImage.cxx' in mapper:
    failures.append('do not patch VTK sources from the Horos mapper')

if not guard.is_file():
    failures.append('VRRayCastZBufferGuard.h is missing')
else:
    text = guard.read_text(encoding='utf-8')
    if 'HorosRayCastZBufferIsUsable' not in text:
        failures.append('guard header is missing HorosRayCastZBufferIsUsable')
    if 'width > 0' not in text or 'height > 0' not in text:
        failures.append('guard must refuse a zero-size Z buffer')

if 'classifyFailure' not in swift or 'GetZBufferValue' not in swift:
    failures.append('Swift classifier does not name GetZBufferValue')
if 'abi-plugin-load' not in swift or 'raycast-zbuffer' not in swift:
    failures.append('Swift must keep ABI load distinct from the Z-buffer crash')
if 'cbct-ready' not in swift:
    failures.append('Swift must name a CBCT volume that may ray-cast')

if 'VRRayCastZBuffer.swift' not in pbx:
    failures.append('VRRayCastZBuffer.swift is not in the Xcode project')
if 'VRRayCastZBufferGuard.h' not in pbx:
    failures.append('VRRayCastZBufferGuard.h is not in the Xcode project')

vtk_image = (root / 'VTK/Rendering/Volume/vtkFixedPointRayCastImage.cxx').read_text(encoding='latin1')
# The in-tree VTK copy is the vendor tree; Horos must not require a rebuild
# to close this issue. The guard lives in Horos/Sources.
if 'HorosRayCastZBuffer' in vtk_image:
    failures.append('do not modify VTK vtkFixedPointRayCastImage.cxx')

for failure in failures:
    print('FAIL:', failure, file=sys.stderr)
if failures:
    sys.exit(1)
print('PASS: Horos mapper sanitizes Z before CastRays without a VTK rebuild')
