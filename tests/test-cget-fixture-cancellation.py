#!/usr/bin/env python3
"""A consumed pynetdicom cancellation must not start another fixture store."""
import ast
from pathlib import Path
from types import SimpleNamespace
from threading import Lock
import time

path = Path(__file__).resolve().parents[1] / 'tools/serve-cget-fixture.py'
function = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == 'on_get')
class Event:
    identifier = SimpleNamespace(QueryRetrieveLevel='STUDY', StudyInstanceUID='1', SeriesInstanceUID='', SOPInstanceUID='')
    assoc = SimpleNamespace(dimse=SimpleNamespace(send_msg=lambda *args: None))
    queued = True
    @property
    def is_cancelled(self):
        result, self.queued = self.queued, False
        return result

namespace = dict(time=time, lock=Lock(), record={}, FAILING=set(),
    arguments=SimpleNamespace(repair_flag=None, omit_instance=-1, duplicate_instance=-1, stall_after=-1, instance_delay=.2),
    INSTANCES=[SimpleNamespace(StudyInstanceUID='1', SeriesInstanceUID='2', SOPInstanceUID='3', InstanceNumber=1)])
exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
answers = list(namespace['on_get'](Event()))
assert answers == [1, (0xFE00, None)], answers
print('PASS: one observed C-CANCEL produces a terminal cancellation without another C-STORE')
