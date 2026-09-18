#!/usr/bin/env python3
"""The Metal 4 pilot is chosen explicitly and falls back out loud (#609).

Source level, with `<git revision>` as an optional argument for the negative
control:

* the host picks a backend from a preference that is off unless somebody turns
  it on, never from availability alone;
* a device or a system without Metal 4, or a pilot that cannot be built, gets
  the backend already in use and a reason, not a silent downgrade and not a
  missing picture;
* both backends share the shader, the frame type and the window/CLUT
  arithmetic, so the pilot cannot drift into a second renderer;
* the OpenGL composition still waits for the GPU before the quad is drawn:
  neither backend hands over a target that is still being written;
* the pilot builds its commit options per submission, holds its own per-frame
  slots, and releases them only on feedback;
* the viewer, MPR, volume rendering, registration and printing are untouched.
"""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


failures = []
try:
    pilot = read('Horos/Sources/PlanarMetal4Renderer.swift')
except subprocess.CalledProcessError:
    pilot = ''
host = read('Horos/Sources/PlanarHostRenderer.swift')
legacy = read('Horos/Sources/PlanarMetalRenderer.swift')
bridge = read('Horos/Sources/PlanarHostBridge.m')

# --- the choice is explicit -------------------------------------------------
if 'HorosPlanarMetal4Pilot' not in host:
    failures.append('there is no preference that asks for the pilot')
if 'UserDefaults.standard.bool(forKey: PlanarBackend.pilotDefaultsKey)' not in host:
    failures.append('the backend is not chosen from the preference')
if 'guard wantsPilot else' not in host:
    failures.append('the pilot is used without being asked for')
if 'PlanarMetal4Renderer.isSupported(device)' not in host:
    failures.append('availability is not checked before the pilot is built')

make = host[host.find('static func make(device:'):host.find('var device: MTLDevice')]
if make.count('PlanarMetalRenderer(device: device)') < 3:
    failures.append('an unsupported device or a failed pilot does not fall back to the existing backend')
if 'error.localizedDescription' not in make:
    failures.append('a pilot that cannot be built produces no reason')
if 'NSLocalizedString' not in make:
    failures.append('the fallback reason is not localisable')

# --- one renderer, two submission paths -------------------------------------
if 'PlanarMetalRenderer.shader' not in pilot:
    failures.append('the pilot does not use the same shader source')
if 'PlanarFrame' not in pilot:
    failures.append('the pilot does not use the host frame type')
for forbidden in ['metal_stdlib', 'fragment float4', 'windowWidth']:
    if forbidden in pilot:
        failures.append('the pilot carries its own image maths (%s)' % forbidden)
if 'static let shader' not in legacy:
    failures.append('the shared shader is no longer on the existing renderer')

# --- the composition still waits --------------------------------------------
render = host[host.find('func render(into target: MTLTexture) throws -> Double'):host.find('@MainActor @objc(HorosPlanarHostRenderer)')]
if 'waitUntilCompleted' not in render:
    failures.append('the existing backend no longer waits before the composition')
if 'renderer.render(into: target)' not in render:
    failures.append('the pilot is not waited for before the composition')
if 'glFinish()' not in host:
    failures.append('the OpenGL read is no longer completed before the Metal write')

# --- per-submission options, per-frame slots --------------------------------
submit = pilot[pilot.find('func submit(into target:'):pilot.find('/// One completion per submission')]
if 'let options = MTL4CommitOptions()' not in submit:
    failures.append('the commit options are reused across submissions; the origin recorded a hang')
if 'slot.allocator.reset()' not in submit or 'beginCommandBuffer(allocator: slot.allocator)' not in submit:
    failures.append('submissions do not get their own command allocator')
if 'slot.retained = [textures.image, textures.clut, target]' not in submit or \
        'slot.retained += [fused.image, fused.clut]' not in submit:
    failures.append('a submission does not retain what it reads and writes')
if 'useResidencySet' not in submit:
    failures.append('residency is not made explicit')
if any(binding not in submit for binding in ['argumentTable.setTexture(textures.image.gpuResourceID, index: 0)',
                                              'argumentTable.setTexture(textures.clut.gpuResourceID, index: 1)',
                                              'fusionTable.setTexture(fused.image.gpuResourceID, index: 0)',
                                              'fusionTable.setTexture(fused.clut.gpuResourceID, index: 1)']):
    failures.append('texture bindings are not set on every draw, so a stale one can survive')
if 'once.claim()' not in pilot:
    failures.append('a submission can report completion more than once')
if 'slot.release()' not in pilot:
    failures.append('a slot is never given back')

# --- the cache holds compiled artefacts only --------------------------------
cache = pilot[pilot.find('final class PipelineCache'):pilot.find('/// One in-flight submission')]
if 'struct Key: Hashable' not in cache:
    failures.append('the pipeline cache has no key type')
for field in ['colorFormat', 'sampleCount', 'blending', 'vertexFunction', 'fragmentFunction']:
    if field not in cache:
        failures.append('the cache key ignores %s' % field)
if 'let state = try compiler.makeRenderPipelineState(descriptor: descriptor)' not in cache:
    failures.append('the cache does not build the pipeline itself')
if cache.find('pipelines[key] = state') < cache.find('let state = try compiler.makeRenderPipelineState'):
    failures.append('the cache records a pipeline before it is built')

# --- nothing else moved -----------------------------------------------------
for name in ['Horos/Sources/VRView.mm', 'Horos/Sources/DCMView.m']:
    source = read(name)
    if 'MTL4' in source or 'PlanarMetal4Renderer' in source:
        failures.append('%s was migrated; this issue is a planar pilot only' % name)
if 'MTL4' in bridge:
    failures.append('the host bridge encodes Metal 4 itself instead of asking the renderer')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: the pilot is opt-in, falls back with a reason and shares the image maths')
