#!/usr/bin/env python3
"""Exercise the A295 verifier with real local captures and corrupt controls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

if len(sys.argv) < 2:
    print('skipped: needs the local native A295 capture directory',file=sys.stderr)
    raise SystemExit(2)
root = Path(__file__).resolve().parents[1]
directory = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('crosshair_verify',root/'tools/verify-native-patient-crosshair.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)
result = verify.verify(directory)
positive = json.loads((directory/'policy-restored.json').read_text())

def rejected(name, mutation):
    state = deepcopy(positive)
    mutation(state)
    try:
        verify.verify_capture(state,directory,name)
    except (ValueError,OSError):
        return
    raise AssertionError('Verifier accepted '+name)

rejected('wrong-patient-point',lambda s: s['point'].__setitem__(0,s['point'][0]+1))
rejected('wrong-plane-projection',lambda s: s['viewers'][0]['projectedSliceMM'].__setitem__(0,99))
rejected('wrong-frame-admission',lambda s: verify.viewer(s,'Axial Pair C (7)').__setitem__('frameUID',verify.COMMON_FRAME))
rejected('orphaned-source',lambda s: s.__setitem__('sourceOwner','0xDEADBEEF'))
rejected('nonfinite-point',lambda s: s['point'].__setitem__(1,float('nan')))
rejected('missing-buffer',lambda s: s['viewers'][0].__setitem__('bufferFile','absent-native-buffer.bgra'))
# A real pre-fix native frame remains visible even though admission is false.
# Supply this optional historical control to prove that model-only checks do
# not conceal a stale GL overlay; it is not part of the accepted capture set.
if len(sys.argv) > 2:
    stale = json.loads(Path(sys.argv[2]).read_text())
    try:
        verify.verify_capture(stale,directory,'stale-native-overlay')
    except ValueError as error:
        assert 'stale marker pixels' in str(error), error
    else:
        raise AssertionError('Verifier accepted the pre-fix native stale marker')
print('PASS: '+str(result['captures'])+' native captures; six corrupt controls rejected'+
      ('; pre-fix native stale overlay rejected' if len(sys.argv)>2 else ''))
