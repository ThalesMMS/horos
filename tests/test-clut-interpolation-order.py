#!/usr/bin/env python3
"""Interpolation happens after the CLUT, not before it (#373, criterion A111).

A111 asks that NM/PET intensities be interpolated *before* the colour lookup.
The legacy viewer does the opposite, and the two lines that prove it sit next to
each other in `DCMView.m`:

* with no colour transfer the texture is `GL_LUMINANCE_FLOAT32_APPLE` or
  `GL_INTENSITY8` — intensities, which `GL_LINEAR` interpolates correctly;
* with `localColorTransfer == YES`, which is the NM/PET case, the texture is
  `GL_RGBA`, so the CLUT was already applied on the CPU and `GL_LINEAR`
  interpolates **colours**.

With a discrete CLUT that produces colours the CLUT does not contain, and the
pixel on screen no longer corresponds to any intensity. This test states the
structure and then measures the consequence on the GPU, so the Metal renderer
that replaces this path has a number to beat rather than a claim to inherit.

It does not fix anything: see docs/clut-interpolation-order.md.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accelerated_opengl
accelerated_opengl.require()

root = Path(__file__).resolve().parents[1]
view = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
failures = []

# The structure the measurement below depends on. If the viewer starts uploading
# intensities with a colour transfer active, this test has to be revisited
# rather than left asserting a defect that is gone.
lines = view.splitlines()
if 'GL_TEXTURE_MIN_FILTER, GL_LINEAR' not in view:
    failures.append('the viewer no longer offers linear filtering')
colour = [line for line in lines if 'glTexImage2D' in line and 'localColorTransfer' in line]
if not colour:
    failures.append('no glTexImage2D is guarded by localColorTransfer any more: A111 may be '
                    'fixed, revisit this test')
elif not all('GL_RGBA' in line for line in colour):
    failures.append('the colour-transfer upload is no longer GL_RGBA: A111 may be fixed, revisit')
intensity = [line for line in lines
             if 'glTexImage2D' in line and ('GL_LUMINANCE_FLOAT32_APPLE' in line
                                            or 'GL_INTENSITY8' in line)]
if not intensity:
    failures.append('the greyscale upload no longer carries intensities')
print('colour-transfer uploads: %d, all GL_RGBA; intensity uploads: %d'
      % (len(colour), len(intensity)))

code = r'''
#import <Cocoa/Cocoa.h>
#import <OpenGL/gl.h>
#import <OpenGL/glext.h>
#include <math.h>
// A deliberately discrete CLUT: two entries, nothing between them. Any colour
// the framebuffer shows that is not one of these two was invented by the
// interpolator.
static const unsigned char kLow[3]  = {0, 0, 255};
static const unsigned char kHigh[3] = {255, 255, 0};
static void clut(unsigned char intensity, unsigned char *out) {
    const unsigned char *entry = intensity < 128 ? kLow : kHigh;
    out[0] = entry[0]; out[1] = entry[1]; out[2] = entry[2];
}
static void quad(void) {
    glBegin(GL_QUADS);
    glTexCoord2f(0.5f, 0.5f); glVertex2f(0, 0);
    glTexCoord2f(1.5f, 0.5f); glVertex2f(32, 0);
    glTexCoord2f(1.5f, 1.5f); glVertex2f(32, 16);
    glTexCoord2f(0.5f, 1.5f); glVertex2f(0, 16);
    glEnd();
}
int main() {@autoreleasepool{
 [NSApplication sharedApplication];
 NSOpenGLPixelFormatAttribute attrs[] = {NSOpenGLPFAAccelerated, NSOpenGLPFAColorSize, 32,
                                         NSOpenGLPFAAlphaSize, 8, 0};
 NSOpenGLContext *context = [[NSOpenGLContext alloc]
     initWithFormat:[[NSOpenGLPixelFormat alloc] initWithAttributes:attrs] shareContext:nil];
 if (!context) { fprintf(stderr, "FAIL: no OpenGL context\n"); return 1; }
 [context makeCurrentContext];
 GLuint fbo = 0, target = 0;
 glGenFramebuffersEXT(1, &fbo); glGenTextures(1, &target);
 glBindTexture(GL_TEXTURE_2D, target);
 glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 32, 16, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
 glBindFramebufferEXT(GL_FRAMEBUFFER_EXT, fbo);
 glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT, GL_COLOR_ATTACHMENT0_EXT, GL_TEXTURE_2D, target, 0);
 if (glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT) != GL_FRAMEBUFFER_COMPLETE_EXT) {
     fprintf(stderr, "FAIL: framebuffer incomplete\n"); return 1; }
 glViewport(0, 0, 32, 16);
 glMatrixMode(GL_PROJECTION); glLoadIdentity(); glOrtho(0, 32, 0, 16, -1, 1);
 glMatrixMode(GL_MODELVIEW); glLoadIdentity();
 glDisable(GL_BLEND);
 glColor4f(1, 1, 1, 1);
 glEnable(GL_TEXTURE_RECTANGLE_EXT);
 // Two source pixels, one at each end of the CLUT.
 const unsigned char intensities[2] = {0, 255};

 // (1) The viewer's order: CLUT first on the CPU, then GL_LINEAR on colours.
 unsigned char coloured[2][4];
 for (int i = 0; i < 2; i++) { clut(intensities[i], coloured[i]); coloured[i][3] = 255; }
 GLuint after = 0; glGenTextures(1, &after); glBindTexture(GL_TEXTURE_RECTANGLE_EXT, after);
 glTexParameteri(GL_TEXTURE_RECTANGLE_EXT, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
 glTexParameteri(GL_TEXTURE_RECTANGLE_EXT, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
 glTexImage2D(GL_TEXTURE_RECTANGLE_EXT, 0, GL_RGBA, 2, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, coloured);
 glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
 quad();
 unsigned char blendedColour[4] = {0,0,0,0};
 glReadPixels(16, 8, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, blendedColour);

 // (2) What A111 asks for: interpolate the intensity, then look it up. The
 // interpolation is the same GL_LINEAR; only the order changes.
 unsigned char grey[2] = {intensities[0], intensities[1]};
 GLuint before = 0; glGenTextures(1, &before); glBindTexture(GL_TEXTURE_RECTANGLE_EXT, before);
 glTexParameteri(GL_TEXTURE_RECTANGLE_EXT, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
 glTexParameteri(GL_TEXTURE_RECTANGLE_EXT, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
 glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
 glTexImage2D(GL_TEXTURE_RECTANGLE_EXT, 0, GL_INTENSITY8, 2, 1, 0, GL_LUMINANCE, GL_UNSIGNED_BYTE, grey);
 glClearColor(0, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
 quad();
 unsigned char blendedIntensity[4] = {0,0,0,0};
 glReadPixels(16, 8, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, blendedIntensity);
 if (glGetError() != GL_NO_ERROR) { fprintf(stderr, "FAIL: GL error\n"); return 1; }

 unsigned char lookedUp[3];
 clut(blendedIntensity[0], lookedUp);

 int isEntry = 0;
 for (int c = 0; c < 2; c++) {
     const unsigned char *entry = c ? kHigh : kLow;
     if (abs(blendedColour[0] - entry[0]) <= 2 && abs(blendedColour[1] - entry[1]) <= 2 &&
         abs(blendedColour[2] - entry[2]) <= 2) isEntry = 1;
 }
 printf("interpolated-after-CLUT  %d,%d,%d  in-CLUT=%s\n",
        blendedColour[0], blendedColour[1], blendedColour[2], isEntry ? "yes" : "NO");
 printf("interpolated-before-CLUT intensity %d -> %d,%d,%d  in-CLUT=yes\n",
        blendedIntensity[0], lookedUp[0], lookedUp[1], lookedUp[2]);
 if (isEntry) {
     fprintf(stderr, "FAIL: interpolating after the CLUT produced a CLUT entry; the "
                     "measurement no longer demonstrates A111\n");
     return 1;
 }
 if (blendedIntensity[0] < 100 || blendedIntensity[0] > 155) {
     fprintf(stderr, "FAIL: the intensity midpoint is %d, not near 128\n", blendedIntensity[0]);
     return 1;
 }
 puts("PASS: interpolating after a discrete CLUT invents a colour the CLUT does not "
      "contain; interpolating the intensity first lands on a CLUT entry");
}}
'''

with tempfile.TemporaryDirectory(prefix='horos-clut-order-') as folder:
    directory = Path(folder)
    (directory / 'test.m').write_text(code)
    built = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-deprecated-declarations',
                            '-framework', 'Cocoa', '-framework', 'OpenGL',
                            str(directory / 'test.m'), '-o', str(directory / 'test')],
                           capture_output=True, text=True)
    if built.returncode != 0:
        print(built.stderr or built.stdout, file=sys.stderr)
        raise SystemExit(built.returncode)
    run = subprocess.run([str(directory / 'test')], capture_output=True, text=True)
    sys.stdout.write(run.stdout)
    if run.returncode != 0:
        sys.stderr.write(run.stderr)
        failures.append('the GPU measurement failed')

if failures:
    for failure in failures:
        print('FAIL: %s' % failure, file=sys.stderr)
    raise SystemExit(1)
