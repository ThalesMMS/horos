"""Is there an accelerated OpenGL context to draw into?

Several checks here compile a probe that renders with OpenGL and reads the
pixels back. On a machine with no window server session - a CI runner, a build
bot - `NSOpenGLContext` cannot be created, and the probe dies with a message
about the context rather than about the thing under test. That is a missing
prerequisite, not a defect, so those checks skip; this is what they ask.

The answer is cached for the life of the process; each check is its own process
and pays the probe once, about a second.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

_PROBE = r'''
#import <Cocoa/Cocoa.h>
#import <OpenGL/OpenGL.h>
int main(void) {
    @autoreleasepool {
        NSOpenGLPixelFormatAttribute attributes[] = {
            NSOpenGLPFAAccelerated, NSOpenGLPFADoubleBuffer,
            NSOpenGLPFAColorSize, 24, NSOpenGLPFAAlphaSize, 8, 0
        };
        NSOpenGLPixelFormat *format =
            [[NSOpenGLPixelFormat alloc] initWithAttributes: attributes];
        if (!format) return 1;
        NSOpenGLContext *context =
            [[NSOpenGLContext alloc] initWithFormat: format shareContext: nil];
        return context ? 0 : 1;
    }
}
'''


def _measure():
    with tempfile.TemporaryDirectory(prefix='horos-gl-probe-') as tmp:
        directory = Path(tmp)
        (directory / 'probe.m').write_text(_PROBE)
        build = subprocess.run(
            ['xcrun', 'clang', '-fobjc-arc', '-framework', 'Cocoa', '-framework', 'OpenGL',
             str(directory / 'probe.m'), '-o', str(directory / 'probe')],
            capture_output=True, text=True)
        if build.returncode != 0:
            return False, 'the OpenGL probe does not build: %s' % build.stderr.strip()[-160:]
        run = subprocess.run([str(directory / 'probe')], capture_output=True, text=True)
        if run.returncode != 0:
            return False, 'no accelerated OpenGL context is available here'
        return True, ''


_answer = None


def available():
    """(True, '') when a context can be made, else (False, why).

    Cached for this process only. A cache on disk would outlive the thing it
    describes - connect a display and the stored "no" is simply wrong - and the
    probe costs about a second, which each check pays once.
    """
    global _answer
    if _answer is None:
        _answer = _measure()
    return _answer


def require():
    """Skip the calling check, the way this suite spells a skip, when there is none."""
    ok, reason = available()
    if not ok:
        print('skipped: %s' % reason, file=sys.stderr)
        raise SystemExit(2)
