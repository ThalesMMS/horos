#!/usr/bin/env python3
"""C-GET diagnostics retain all standard outcomes after the upstream migration."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
expected = {
                '0000': 'Success',
                'ff00': 'Pending',
                'a701': 'Refused: OutOfResourcesNumberOfMatches',
                'a702': 'Refused: OutOfResourcesSubOperations',
                'a800': 'Failed: SOPClassNotSupported',
                'a900': 'Failed: IdentifierDoesNotMatchSOPClass',
                'fe00': 'Cancel: SubOperationsTerminatedDueToCancelIndication',
                # The one a partial retrieval ends on.
                'b000': 'Warning: SubOperationsCompleteOneOrMoreFailures',
                # Failure is a whole nibble, not one code.
                'c000': 'Failed: UnableToProcess',
                'c123': 'Failed: UnableToProcess',
                # And anything outside the standard still says what it was.
                '1234': 'Unknown Status: 0x1234',
            }
checks = '\n'.join('precondition(HorosDIMSEPolicy.cGetStatusDescription(0x' + code + ') == "' + text + '")' for code, text in expected.items())
with tempfile.TemporaryDirectory(prefix='horos-get-status-') as folder:
    folder = Path(folder)
    (folder / 'Check.swift').write_text('@main struct Check { static func main() {\n' + checks + '\n} }')
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(root / 'Horos/Sources/HorosDIMSEPolicy.swift'), str(folder / 'Check.swift'), '-o', str(folder / 'check')], check=True)
    subprocess.run([str(folder / 'check')], check=True)
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_text(encoding='latin1')
assert '[HorosDIMSEPolicy cGetStatusDescription:rsp.DimseStatus]' in node
assert 'DU_cgetStatusString(' not in node
print('PASS: C-GET status names and the active native diagnostic call site')
