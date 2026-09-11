#!/usr/bin/env python3
"""Wire selected-image insertion into the Pages/Word report menu.

The placement math lives in ReportImagePlacement.swift. This check is the host
contract: the File > Report action, the study-local report, and a refusal that
does not walk the Pages→PDF path owned by #129.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
failures = []

swift = (root / 'Horos/Sources/ReportImagePlacement.swift').read_text()
for needle, reason in (
    ('end of body text', 'Pages must insert inline so a reopen cannot slide a box'),
    ('inline picture', 'Word must insert an inline picture, not a floating shape'),
    ('defaultBox', 'the figure size has to be one predictable box'),
    ('writeCopy', 'the source image has to be copied, not rewritten'),
    ('replaceItemAt', 'the original report is published only after a successful copy'),
    ('com.apple.Pages', 'modern Pages is asked for by identifier'),
    ('Microsoft Word', 'Word is a first-class report target, not a Pages leftover'),
    ('repeat with attempt from 1 to 60', 'the editor script must wait for the private copy'),
    ('on error errorMessage number errorNumber', 'a refused insert must capture the AppleScript number'),
    ('error -1712', 'a timeout is not swallowed as a generic insert failure'),
    ('error -609', 'a dropped Automation connection is not swallowed'),
    ('error -10024', 'a Pages container refusal must keep its number'),
):
    if needle not in swift:
        failures.append(reason)

browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/BrowserController.h').read_bytes().decode('latin1')
if 'insertSelectedImagesIntoReport:' not in header:
    failures.append('BrowserController.h does not expose the insertion action')
if '- (IBAction)insertSelectedImagesIntoReport:' not in browser:
    failures.append('BrowserController does not implement the insertion action')
start = browser.find('- (IBAction)insertSelectedImagesIntoReport:')
action = browser[start:browser.find('\n#endif', start)] if start >= 0 else ''
if 'HorosReportImageInsertion' not in action:
    failures.append('the action does not call the Swift inserter')
if 'lastErrorMessage' not in action:
    failures.append('a failed insert does not show the captured AppleScript error')
if 'nsimage:NO' not in action:
    failures.append('a front viewer does not contribute the displayed image')
if 'filesForDatabaseMatrixSelection' not in action:
    failures.append('database thumbnails are not the selected images when no viewer is open')
if 'selector(insertSelectedImagesIntoReport:)' not in browser:
    failures.append('validateMenuItem does not know the new action')

# Stay off the #129 Pages→PDF files and the conversion selectors.
report_mm = (root / 'Horos/Sources/DicomStudy+Report.mm').read_bytes().decode('latin1')
if 'HorosReportImageInsertion' in report_mm or 'insertSelectedImagesIntoReport' in report_mm:
    failures.append('image insertion was wired through DicomStudy+Report, the #129 PDF path')
if 'convertReportToPDF' in browser[browser.find('- (IBAction)insertSelectedImagesIntoReport:'):browser.find('- (IBAction)insertSelectedImagesIntoReport:')+2500]:
    failures.append('insertion calls the PDF converter')

pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'ReportImagePlacement.swift in Sources' not in pbx:
    failures.append('ReportImagePlacement.swift is not in the app target')

menus = list((root / 'Horos/Resources').glob('*.lproj/MainMenu.xib'))
if len(menus) < 4:
    failures.append('localized main menus are missing')
for menu in menus:
    tree = ET.parse(menu)
    report = tree.find('.//menu[@id="12354"]')
    if report is None:
        failures.append(f'{menu} has no Report submenu')
        continue
    actions = report.findall('.//action[@selector="insertSelectedImagesIntoReport:"]')
    if len(actions) != 1 or actions[0].attrib.get('target') != '898':
        failures.append(f'{menu} does not expose one insertion action on the browser')
    pdf = report.findall('.//action[@selector="convertReportToPDF:"]')
    if len(pdf) != 1:
        failures.append(f'{menu} lost the existing PDF conversion item')

if failures:
    raise SystemExit('FAIL:\n- ' + '\n- '.join(failures))
print('PASS: File > Report inserts selected images into Pages/Word without touching the PDF path')
