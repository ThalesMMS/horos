#!/usr/bin/env python3
"""A disc's worth of DICOM: several series, and a DICOMDIR that may not list it all.

Media arrives with an index - DICOMDIR - that is supposed to name every instance
on it. Some discs carry one that lists fewer, and an application that trusts the
index instead of the disc copies only what the index names. So this writes the
same tree twice over: once with a DICOMDIR that lists everything, once with one
that lists only the first series.

    <destination>/PT000000/…       the instances the index names
    <destination>/EXTRA/SER0000n/  the instances it leaves out
    <destination>/DICOMDIR         the index
"""
import argparse
import json
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.fileset import FileSet
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the disc')
parser.add_argument('--series', type=int, default=3)
parser.add_argument('--instances', type=int, default=4)
parser.add_argument('--index', default='complete', choices=('complete', 'partial', 'none'),
                    help='what the DICOMDIR lists')
parser.add_argument('--size', type=int, default=32,
                    help='rows and columns of each instance; a disc worth timing needs '
                         'instances the size of real ones')
parser.add_argument('--zip-duplicate', action='store_true',
                    help='also write EXPANDED/ with a copy of every instance and expanded.zip '
                         'holding the same files, so the medium carries each SOP instance twice: '
                         'once loose and once inside an archive')
parser.add_argument('--damaged', action='store_true',
                    help='add a BROKEN folder of files no parser can read: truncated, empty, '
                         'a text file wearing a .dcm extension, a DICOM whose transfer syntax '
                         'does not exist, and a link to nothing')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

study = generate_uid()
ramp = numpy.tile(numpy.linspace(0, 4000, arguments.size),
                  (arguments.size, 1)).astype(numpy.uint16)


def instance(series_number, series_uid, number):
    uid = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = uid
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = uid
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = series_uid
    dataset.PatientName = 'MEDIA^DISC'
    dataset.PatientID = 'MEDIA-59'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'MEDIA59'
    dataset.StudyID = '59'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = number
    dataset.Modality = 'CT'
    dataset.StudyDescription = 'a disc with %d series' % arguments.series
    dataset.SeriesDescription = 'series %d' % series_number
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [0.0, 0.0, float(number)]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = [0.5, 0.5]
    dataset.SliceThickness = 1.0

    dataset.Rows = arguments.size
    dataset.Columns = arguments.size
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.WindowCenter = 2000.0
    dataset.WindowWidth = 4000.0
    dataset.PixelData = ramp.tobytes()
    dataset['PixelData'].VR = 'OW'
    return dataset


# Everything the disc holds, whether or not the index names it.
staging = arguments.destination / '.staging'
staging.mkdir()
written = []
for series_number in range(1, arguments.series + 1):
    series_uid = generate_uid()
    for number in range(1, arguments.instances + 1):
        dataset = instance(series_number, series_uid, number)
        path = staging / ('s%02d-i%02d.dcm' % (series_number, number))
        dataset.save_as(str(path), enforce_file_format=True)
        written.append({'staged': path, 'sopInstanceUID': str(dataset.SOPInstanceUID),
                        'series': series_number})

listed = []
if arguments.index == 'none':
    for entry in written:
        folder = arguments.destination / 'DICOM' / ('SER%05d' % entry['series'])
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / entry['staged'].name
        entry['staged'].replace(destination)
        entry['placed'] = destination
else:
    # A burner writes the instances in its own layout and an index beside them.
    fileset = FileSet()
    for entry in written:
        entry['indexed'] = not (arguments.index == 'partial' and entry['series'] != 1)
        if entry['indexed']:
            fileset.add(str(entry['staged']))
            listed.append(entry['sopInstanceUID'])
    fileset.write(str(arguments.destination))

    # What the index leaves out is still on the disc, in a folder of its own.
    for entry in written:
        if entry['indexed']:
            continue
        folder = arguments.destination / 'EXTRA' / ('SER%05d' % entry['series'])
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / entry['staged'].name
        entry['staged'].replace(destination)
        entry['placed'] = destination

    # The FileSet copied what it indexed under its own names. Read each file once
    # and index by SOP Instance UID, rather than searching the tree per entry.
    if arguments.zip_duplicate:
        import pydicom
        placed = {}
        for candidate in arguments.destination.rglob('*'):
            if not candidate.is_file() or candidate.name in ('DICOMDIR', 'expected.json'):
                continue
            try:
                uid = str(pydicom.dcmread(str(candidate), stop_before_pixels=True).SOPInstanceUID)
            except Exception:
                continue
            placed.setdefault(uid, candidate)
        for entry in written:
            if entry['sopInstanceUID'] in placed:
                entry['placed'] = placed[entry['sopInstanceUID']]

# The same instances twice over: loose in a folder, and inside an archive beside
# it. An import that walks the medium meets both, and the SOP Instance UIDs have
# to bring them back together instead of doubling the study.
duplicated = []
if arguments.zip_duplicate:
    import zipfile
    folder = arguments.destination / 'EXPANDED'
    folder.mkdir(parents=True, exist_ok=True)
    archive = arguments.destination / 'expanded.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for entry in written:
            source = entry.get('placed')
            if source is None or not source.exists():
                continue
            name = '%s.dcm' % entry['sopInstanceUID'][-12:]
            (folder / name).write_bytes(source.read_bytes())
            bundle.write(str(folder / name), 'expanded/%s' % name)
            duplicated.append(entry['sopInstanceUID'])

# Files an import has to survive rather than index. They live outside the index,
# because a DICOMDIR that names a file no parser can read is a different fixture.
damaged = []
if arguments.damaged:
    folder = arguments.destination / 'BROKEN'
    folder.mkdir(parents=True, exist_ok=True)
    whole = instance(1, generate_uid(), 1)
    intact = folder / 'whole.tmp'
    whole.save_as(str(intact), enforce_file_format=True)
    body = intact.read_bytes()
    intact.unlink()

    # Cut off in the middle of the pixel data: the header parses, the pixels stop.
    (folder / 'truncated.dcm').write_bytes(body[:len(body) // 3])
    damaged.append('truncated.dcm')

    # Nothing at all. A transfer that never started looks like this.
    (folder / 'empty.dcm').write_bytes(b'')
    damaged.append('empty.dcm')

    # A name that promises DICOM over something that is not.
    (folder / 'notes.dcm').write_bytes(b'This is not a DICOM file.\n' * 40)
    damaged.append('notes.dcm')

    # Preamble and magic intact, transfer syntax nobody implements.
    invented = bytearray(body)
    at = invented.find(b'1.2.840.10008.1.2.1')
    if at > 0:
        invented[at:at + 19] = b'1.2.840.10008.9.9.9'
    (folder / 'unknown-syntax.dcm').write_bytes(bytes(invented))
    damaged.append('unknown-syntax.dcm')

    # A name in the directory with nothing behind it: the enumerator finds it,
    # every open fails.
    (folder / 'dangling.dcm').symlink_to('nowhere.dcm')
    damaged.append('dangling.dcm')

for leftover in staging.iterdir():
    leftover.unlink()
staging.rmdir()

(arguments.destination / 'expected.json').write_text(json.dumps(
    {'study': study, 'index': arguments.index,
     'instances': [e['sopInstanceUID'] for e in written],
     'listedInIndex': listed,
     'duplicatedInArchive': duplicated,
     'damaged': damaged}, indent=1))

print('%d instance(s) in %d series' % (len(written), arguments.series))
print('DICOMDIR: %s, listing %d of them' % (arguments.index, len(listed)))
if duplicated:
    print('%d instance(s) written twice: loose in EXPANDED/ and inside expanded.zip'
          % len(duplicated))
if damaged:
    print('%d file(s) no parser can read: %s' % (len(damaged), ', '.join(damaged)))
print('study %s' % study)
