#!/usr/bin/env python3
"""The thumbnail checker has to answer for a picture whose orientation is known.

A thumbnail is built once, when the series is indexed, and never rebuilt, so a
thumbnail built from a misread buffer is wrong for the life of the database.
tools/check-thumbnail-pixels.py is what measures that; this checks the measure
itself, on thumbnails written here, so the tool can be trusted when it is pointed
at a real database.
"""
from pathlib import Path
import io, sqlite3, subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
try:
    from PIL import Image
except ImportError:
    print('skipped: needs Pillow to write the thumbnails: PILLOW')
    sys.exit(2)

def gradient(size, horizontal, vertical):
    image = Image.new('L', (size, size))
    for y in range(size):
        for x in range(size):
            value = 30
            if horizontal == 'right':  value += int(200 * x / (size - 1))
            if horizontal == 'left':   value += int(200 * (size - 1 - x) / (size - 1))
            if vertical == 'down':     value += int(0.0)   # kept flat unless asked
            image.putpixel((x, y), min(value, 255))
    if vertical in ('down', 'up'):
        for y in range(size):
            for x in range(size):
                base = image.getpixel((x, y))
                step = int(200 * (y if vertical == 'down' else size - 1 - y) / (size - 1))
                image.putpixel((x, y), min(base // 2 + step, 255))
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=92)
    return buffer.getvalue()

cases = {
    'to the right': ('right', 'flat'),
    'to the left': ('left', 'flat'),
    'downwards': ('flat', 'down'),
    'upwards': ('flat', 'up'),
    'right and down': ('right', 'down'),
    'no picture': None,
}

with tempfile.TemporaryDirectory(prefix='horos-thumbnail-') as tmp:
    database = Path(tmp) / 'Database.sql'
    connection = sqlite3.connect(str(database))
    connection.execute('create table ZSERIES (ZNAME text, ZTHUMBNAIL blob)')
    for name, wanted in cases.items():
        blob = gradient(64, *wanted) if wanted else None
        connection.execute('insert into ZSERIES values (?, ?)', (name, blob))
    connection.commit()
    connection.close()

    expectations = [f'{name}={wanted[0]},{wanted[1]}' for name, wanted in cases.items() if wanted]
    command = [sys.executable, str(root / 'tools/check-thumbnail-pixels.py'), str(database)]
    for expectation in expectations:
        command += ['--expect', expectation]
    done = subprocess.run(command, capture_output=True, text=True)
    assert done.returncode == 0, f'the checker refused thumbnails it should accept:\n{done.stdout}'

    # And it has to refuse a wrong answer, or it measures nothing.
    wrong = subprocess.run([sys.executable, str(root / 'tools/check-thumbnail-pixels.py'),
                            str(database), '--expect', 'to the right=left,flat'],
                           capture_output=True, text=True)
    assert wrong.returncode != 0 and 'thumbnail runs right' in wrong.stdout, \
        f'a flipped thumbnail was accepted:\n{wrong.stdout}'
    missing = subprocess.run([sys.executable, str(root / 'tools/check-thumbnail-pixels.py'),
                              str(database), '--expect', 'no picture=right,flat'],
                             capture_output=True, text=True)
    assert missing.returncode != 0, 'a series with no thumbnail was accepted as having one'

print('PASS: horizontal and vertical direction measured through the JPEG, flips refused, '
      'a missing thumbnail refused')
