#!/usr/bin/env python3
"""The browser preview consumes the window policy (#608).

Source level, with `<git revision>` as an optional argument for the negative
control:

* the pair of window numbers `previewSliderAction:` used to read and throw away
  now goes through `HorosPreviewWindowPolicy`, on every branch and on the first
  display of a selection;
* a person moving the window in the preview is told apart from the policy
  putting a default back, so scrolling cannot undo an adjustment;
* a width of zero reaches the automatic branch instead of coming out as a
  window two units wide, and a colour frame's lookup table no longer divides by
  its own width;
* the frames the view is drawing are not reverted underneath it;
* a thumbnail batch published after the selection changed is discarded by
  generation, not only by the address of the array;
* one burst of scroll events costs one preview decode;
* the viewer's own clinical windowing is not touched.
"""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


def method(source, signature, terminator='\n}\n'):
    start = source.find(signature)
    if start < 0:
        return ''
    return source[start:source.find(terminator, start) + len(terminator)]


failures = []
browser = read('Horos/Sources/BrowserController.m')
preview = read('Horos/Sources/PreviewView.m')
previewHeader = read('Horos/Sources/PreviewView.h')
pix = read('Horos/Sources/DCMPix.m')
view = read('Horos/Sources/DCMView.m')

try:
    policy = read('Horos/Sources/PreviewWindowing.swift')
except subprocess.CalledProcessError:
    policy = ''

# --- the policy exists and is reachable from Objective-C --------------------
for symbol in ['@objc(HorosPreviewWindowPolicy)', '@objc(HorosPreviewAutomaticWindow)',
               '@objc(HorosPreviewRedrawCoalescer)', '@objc(HorosPreviewWindow)']:
    if symbol not in policy:
        failures.append('%s is missing from the preview window policy' % symbol)

# --- every entry point asks the policy --------------------------------------
slider = method(browser, '- (void) previewSliderAction:(id) sender')
if not slider:
    failures.append('previewSliderAction: was not found')
if slider.count('applyPreviewWindowForImage:') != 3:
    failures.append('the three branches of previewSliderAction: do not all apply the policy (%d do)'
                    % slider.count('applyPreviewWindowForImage:'))
if 'getWLWW:&wl :&ww' in slider:
    failures.append('previewSliderAction: still reads a window it never uses')
if 'applyPreviewWindowForImage: nil pix: nil' not in browser:
    failures.append('the first display of a selection does not apply the policy')

apply = method(browser, '- (void) applyPreviewWindowForImage: (DicomImage*) imageObj pix: (DCMPix*) dcmPix')
if not apply:
    failures.append('applyPreviewWindowForImage:pix: was not found')
for fragment, reason in [
        ('beginFrameWithSeriesKey:', 'the policy is not told which frame is coming'),
        ('series.seriesDICOMUID', 'the series is not identified by its DICOM UID'),
        ('parsedFileCacheKey', 'the file revision (#603) is not part of the identity'),
        ('needsAutomaticWindowForModality:', 'the pixels are sampled even when the ladder cannot use it'),
        ('manualWindow', 'a manual adjustment is not reapplied when the defaults stand'),
        ('isColorPreviewFrame', 'a colour frame is not told apart'),
        ('frameRangePreviewWindow', "a frame with nothing to sample falls straight to the stored bit range")]:
    if fragment not in apply:
        failures.append(reason)
if 'automatic == nil && isColor == NO' not in apply:
    failures.append('the frame range is computed even when the ladder cannot reach it')
if 'currentWW == window.width && currentWL == window.level' not in apply:
    failures.append('the same window is applied again, reloading the textures for nothing')

# --- a manual adjustment is told apart from a default -----------------------
if 'PreviewViewWindowDelegate' not in previewHeader:
    failures.append('PreviewView does not report window changes')
setter = method(preview, '- (void) setWLWW:(float) wl :(float) ww')
if 'applyingPreviewWindow == 0' not in setter or 'didRequestWindowLevel:' not in setter:
    failures.append('PreviewView cannot tell a manual adjustment from a default')
applied = method(preview, '- (void) applyPreviewWindow: (HorosPreviewWindow*) window')
if 'applyingPreviewWindow++' not in applied or 'applyingPreviewWindow--' not in applied:
    failures.append('applying a default is reported back as a manual adjustment')
# Restoring the stored presentation state re-asserts the window the view has;
# recording it as a choice pinned every first frame of a selection (#610).
restore = method(preview, '- (void) updatePresentationStateFromSeriesOnlyImageLevel:(BOOL) onlyImage scale:(BOOL) scale offset:(BOOL) offset')
if 'applyingPreviewWindow++' not in restore or 'super updatePresentationStateFromSeriesOnlyImageLevel:' not in restore:
    failures.append('a presentation-state restore is recorded as a manual adjustment')
delegate = method(browser, '- (void) previewView:(PreviewView*) view didRequestWindowLevel:(float) wl width:(float) ww')
if 'recordRequestedLevel:' not in delegate:
    failures.append('the browser does not record the adjustment a person made')
if '[imageView setWindowDelegate: self]' not in browser:
    failures.append('the preview view has no window delegate')

# --- a zero width means automatic, and colour keeps its own presentation -----
change = method(pix, '- (void) changeWLWW:(float)newWL :(float)newWW')
if 'newWW == 0 || isnan( newWW)' not in change:
    failures.append('a zero or non-finite width still produces a window two units wide')
if 'if( diff == 0) diff = 1;' not in pix:
    failures.append('a colour frame still divides by its own window width')

# --- one decode feeds the frame and its window ------------------------------
load = method(pix, '- (void) CheckLoadIn')
if 'atomic_fetch_add_explicit( &horosDecodedFrameCount' not in load:
    failures.append('decodes are not counted, so the sharing cannot be proved')
frame_range = method(pix, '- (id) frameRangePreviewWindow')
if 'computePixMinPixMax' not in frame_range:
    failures.append("the frame's own range is not read from its minimum and maximum")
if 'isRGB || fImage == nil' not in frame_range:
    failures.append('a colour frame or an empty frame gets a scalar frame range')

automatic = method(pix, '- (id) automaticPreviewWindow')
if 'HorosPreviewAutomaticWindow windowForValues:' not in automatic:
    failures.append('the automatic window is not computed from the decoded frame')
if automatic.count('[self CheckLoad]') != 1:
    failures.append('the automatic window does not share the single decode')
if 'isRGB || fImage == nil' not in automatic:
    failures.append('a colour frame or an empty frame is sampled anyway')

# --- the frame being drawn is not freed underneath the view ------------------
if slider.count('p != dcmPix && p != drawn') != 2:
    failures.append('the frame the view is drawing is still reverted underneath it')
if slider.count('DCMPix *drawn = [imageView curDCM]') != 2:
    failures.append('the drawn frame is not read back from the view')

# --- a stale thumbnail batch is discarded -----------------------------------
init = method(browser, '-(void) matrixInit:(long) noOfImages')
if 'previewPixGeneration++' not in init:
    failures.append('replacing the preview list does not move the generation')
icons = method(browser, '- (void)matrixLoadIcons: (NSDictionary*)dict')
if icons.count('previewPix == context && previewPixGeneration == generation') != 2:
    failures.append('a batch published after the selection changed is not discarded by generation')
if '@"Generation"' not in browser:
    failures.append('the loader thread does not carry the generation it started with')

# --- one burst of scroll events costs one decode ----------------------------
wheel = method(browser, '- (void)scrollWheel: (NSEvent *)theEvent')
if 'previewRedrawCoalescer requestRedraw:' not in wheel:
    failures.append('every scroll notch still decodes a frame')
if 'previewRedrawCoalescer flush' not in wheel:
    failures.append('the end of a gesture waits for the coalescing interval')

# --- the viewer's own windowing is untouched --------------------------------
for name, source in [('DCMView.m', view)]:
    if 'HorosPreviewWindowPolicy' in source or 'HorosPreviewAutomaticWindow' in source:
        failures.append('%s adopts the preview policy; the clinical window must not change' % name)
reapply = method(view, '- (void) reapplyWindowLevel')
if '[self.curDCM changeWLWW :curWL :curWW]' not in reapply:
    failures.append('the viewer no longer reapplies its own window level')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: the preview asks the policy, keeps manual adjustments and shares its decode')
