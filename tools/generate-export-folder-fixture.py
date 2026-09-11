#!/usr/bin/env python3
"""Synthetic single-image patients for ordinary export naming and collisions."""
import argparse
import importlib.util
import tempfile
from pathlib import Path
from pydicom import dcmread


def generate(output, hierarchy=False, empty=False):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    spec = importlib.util.spec_from_file_location('fusion', Path(__file__).with_name('generate-fusion-window-fixture.py'))
    fusion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fusion)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / 'source'
        fusion.generate(source)
        names = ['QA^Hierarchy'] * 4 if hierarchy else ['Chr-P03R', 'ChrP03R', 'Chr_P03R', 'QA-A/B', 'QA-A:B']
        if empty:
            names = [':', '*']
        for index, name in enumerate(names):
            ds = dcmread(source / '01-00.dcm')
            ds.PatientName = name
            ds.PatientID = f'LOCAL-EXPORT-FOLDER-{index}'
            ds.StudyDescription = 'Export Folder Acceptance'
            ds.StudyID = 'FOLDER'
            ds.SeriesDescription = 'Series-Test_1'
            for keyword in ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID', 'FrameOfReferenceUID']:
                setattr(ds, keyword, fusion.uid(f'export-folder-{index}-{keyword}'))
            if hierarchy:
                ds.PatientID = 'LOCAL-EXPORT-HIERARCHY'
                ds.StudyDescription = ['StudyCollision-A:B', 'StudyCollision-A*B'][index // 2]
                ds.SeriesDescription = ['SeriesCollision-A:B', 'SeriesCollision-A*B'][index % 2]
                ds.StudyInstanceUID = fusion.uid(f'export-hierarchy-v2-study-{index // 2}')
                ds.SeriesInstanceUID = fusion.uid(f'export-hierarchy-v2-series-{index}')
                ds.SOPInstanceUID = fusion.uid(f'export-hierarchy-v2-image-{index}')
                ds.FrameOfReferenceUID = fusion.uid(f'export-hierarchy-v2-frame-{index // 2}')
            if empty:
                ds.PatientID = f'LOCAL-EXPORT-EMPTY-{index}'
                ds.SeriesDescription = 'EmptyNameAcceptance'
                for keyword in ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID', 'FrameOfReferenceUID']:
                    setattr(ds, keyword, fusion.uid(f'export-empty-{index}-{keyword}'))
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            ds.save_as(output / f'{index}.dcm', enforce_file_format=True)
    print('Generated two patients whose names sanitize to empty.' if empty else
          'Generated four images with colliding study and series folders.' if hierarchy else
          'Generated five synthetic patients; the last two sanitize to the same folder.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--empty', action='store_true', help='Generate fully filtered patient names')
    modes.add_argument('--hierarchy', action='store_true', help='Generate study/series collisions within one patient')
    args = parser.parse_args()
    generate(args.output, args.hierarchy, args.empty)
