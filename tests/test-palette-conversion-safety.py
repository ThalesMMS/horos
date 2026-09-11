#!/usr/bin/env python3
"""Palettes that are truncated, extreme or absent, under AddressSanitizer.

`-[DCMPixelDataAttribute convertPaletteToRGB:]` trusted what the object told it.
Compiled out of the source and driven under AddressSanitizer and
UndefinedBehaviorSanitizer against thirteen palettes - 8- and 16-bit, indices of
0 and 65535, tables shorter than their descriptors, a descriptor with one value
instead of three, pixel data half as long as the picture, a segment claiming
60000 values in a stream of five, a linear segment with nothing before it - the
version before this reported:

    heap-buffer-overflow  x3   reading a lookup table past its end
    runtime error: load of null pointer of type 'unsigned char'
    SEGV on unknown address 0x000000000000

The null load and the crash are the blue table being read from the green
attribute when there is no green one. The overflows are a table read to the
number of entries the descriptor claims rather than the number it holds.

The same thirteen cases now produce no findings at all.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
source_path = root / 'DCM Framework/DCMPixelDataAttribute.mm'
driver_path = root / 'tools/exercise-palette-conversion.mm'


def body_end(text, at):
    opening = text.index('{', at)
    depth, index = 0, opening
    while index < len(text):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


if not driver_path.exists():
    failures.append('the driver that exercises the conversion is gone')
else:
    source = source_path.read_bytes().decode('latin1')
    at = source.find('- (NSData *)convertPaletteToRGB:')
    if at < 0:
        failures.append('-convertPaletteToRGB: is gone')
    else:
        # Whatever sits between the previous method and this one is helpers it calls.
        starts = [m.start() for m in re.finditer(r'(?m)^[-+] \(', source[:at])]
        helpers = source[body_end(source, starts[-1]) + 1:at] if starts else ''
        method = source[at:body_end(source, at) + 1]

        driver = driver_path.read_text()
        driver = driver.replace('CONVERT_PALETTE_TO_RGB', method)
        driver = driver.replace('@interface DCMAttribute : NSObject',
                                helpers + '\n@interface DCMAttribute : NSObject')

        with tempfile.TemporaryDirectory(prefix='horos-palette-asan-') as directory:
            main = Path(directory) / 'main.mm'
            main.write_text(driver)
            binary = Path(directory) / 'palette'
            build = subprocess.run(
                ['xcrun', 'clang++', '-std=c++11', '-w', '-fobjc-arc',
                 '-fsanitize=address,undefined', '-fsanitize-recover=address,undefined',
                 '-fno-omit-frame-pointer', '-g', '-framework', 'Foundation',
                 str(main), '-o', str(binary)],
                capture_output=True, text=True)
            if build.returncode != 0:
                failures.append('the conversion does not compile on its own:\n%s'
                                % build.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=300,
                                     env={'ASAN_OPTIONS': 'halt_on_error=0:exitcode=1',
                                          'UBSAN_OPTIONS': 'halt_on_error=0',
                                          'PATH': '/usr/bin:/bin'})
                output = run.stdout + run.stderr
                findings = [line for line in output.splitlines()
                            if 'ERROR: AddressSanitizer' in line or 'runtime error:' in line]
                for finding in findings:
                    failures.append('sanitizer: %s' % finding.strip()[:160])
                if 'WRONG SIZE' in output:
                    for line in output.splitlines():
                        if 'WRONG SIZE' in line:
                            failures.append('the conversion answered the wrong size: %s'
                                            % line.strip())
                cases = [line for line in output.splitlines() if 'bytes  (expected' in line]
                if len(cases) < 13:
                    failures.append('only %d of the 13 cases ran; the driver stopped early'
                                    % len(cases))
                if run.returncode != 0 and not findings:
                    failures.append('the driver exited %d with no sanitizer finding: %s'
                                    % (run.returncode, output[-500:]))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: thirteen truncated, extreme and absent palettes convert without reading or writing '
      'outside a buffer')
