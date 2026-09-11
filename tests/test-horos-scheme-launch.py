#!/usr/bin/env python3
"""LaunchServices, the browser prompt, and the parser are three different layers.

Chrome 94 started requiring a user gesture and an allow prompt before it will
hand a custom scheme to LaunchServices. A link that never becomes an Apple
Event is not a parse error. This compiles the same HorosSchemeURL type and
feeds it controlled snapshots so the diagnosis names the layer: parser,
launchServices, or browser.

A live LaunchServices read is taken too. It does not change handlers.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/HorosSchemeURL.swift'
application = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
info = (root / 'Horos/Info.plist').read_text()

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String?) {
    print(key + "\t" + (value ?? "nil").replacingOccurrences(of: "\n", with: " "))
}

func dump(_ key: String, _ diagnosis: HorosSchemeDiagnosis) {
    emit(key + ".layer", diagnosis.layer)
    emit(key + ".code", diagnosis.code)
    emit(key + ".message", diagnosis.message)
}

let studyURL = "horos://?methodName=DisplayStudy&StudyInstanceUID=2.25.1"
let badURL = "horos://?methodName=DisplayStudy"

let horosHandler = HorosSchemeLaunchSnapshot()
horosHandler.scheme = "horos"
horosHandler.candidateBundleIDs = ["org.horosproject.horos.local-development"]
horosHandler.chosenBundleID = "org.horosproject.horos.local-development"
horosHandler.chromeMajorVersion = 152
horosHandler.navigationHadUserGesture = true
horosHandler.appleEventDelivered = true

dump("delivered", HorosSchemeURL.diagnose(studyURL, snapshot: horosHandler))

let noHandler = HorosSchemeLaunchSnapshot()
noHandler.scheme = "horos"
noHandler.candidateBundleIDs = []
noHandler.chosenBundleID = nil
noHandler.chromeMajorVersion = 152
noHandler.navigationHadUserGesture = true
noHandler.appleEventDelivered = false
dump("noLS", HorosSchemeURL.diagnose(studyURL, snapshot: noHandler))

let otherApp = HorosSchemeLaunchSnapshot()
otherApp.scheme = "horos"
otherApp.candidateBundleIDs = ["com.example.other-viewer"]
otherApp.chosenBundleID = "com.example.other-viewer"
otherApp.chromeMajorVersion = 152
otherApp.navigationHadUserGesture = true
otherApp.appleEventDelivered = false
dump("otherLS", HorosSchemeURL.diagnose(studyURL, snapshot: otherApp))

let chromeBlock = HorosSchemeLaunchSnapshot()
chromeBlock.scheme = "horos"
chromeBlock.candidateBundleIDs = ["org.horosproject.horos"]
chromeBlock.chosenBundleID = "org.horosproject.horos"
chromeBlock.chromeExcludedSchemes = ["horos": true]
chromeBlock.chromeMajorVersion = 152
chromeBlock.navigationHadUserGesture = true
chromeBlock.appleEventDelivered = false
dump("excluded", HorosSchemeURL.diagnose(studyURL, snapshot: chromeBlock))

let noGesture = HorosSchemeLaunchSnapshot()
noGesture.scheme = "horos"
noGesture.candidateBundleIDs = ["org.horosproject.horos"]
noGesture.chosenBundleID = "org.horosproject.horos"
noGesture.chromeMajorVersion = 94
noGesture.navigationHadUserGesture = false
noGesture.appleEventDelivered = false
dump("gesture", HorosSchemeURL.diagnose(studyURL, snapshot: noGesture))

let prompt = HorosSchemeLaunchSnapshot()
prompt.scheme = "horos"
prompt.candidateBundleIDs = ["org.horosproject.horos"]
prompt.chosenBundleID = "org.horosproject.horos"
prompt.chromeMajorVersion = 152
prompt.navigationHadUserGesture = true
prompt.appleEventDelivered = false
dump("prompt", HorosSchemeURL.diagnose(studyURL, snapshot: prompt))

// A bad URL is a parser error even when Chrome would also have blocked it.
dump("parserWins", HorosSchemeURL.diagnose(badURL, snapshot: chromeBlock))

let prefs = """
{"protocol_handler":{"excluded_schemes":{"horos":true,"osirix":false}}}
"""
let fromPrefs = HorosSchemeLaunchSnapshot.chromeSnapshot(fromPreferencesJSON: prefs, majorVersion: 152)
fromPrefs.scheme = "horos"
fromPrefs.candidateBundleIDs = ["org.horosproject.horos"]
fromPrefs.chosenBundleID = "org.horosproject.horos"
fromPrefs.navigationHadUserGesture = true
fromPrefs.appleEventDelivered = false
dump("fromPrefs", HorosSchemeURL.diagnose(studyURL, snapshot: fromPrefs))

let live = HorosSchemeURL.liveSnapshot(forScheme: "horos")
emit("live.candidates", live.candidateBundleIDs.joined(separator: ","))
emit("live.chosen", live.chosenBundleID)
emit("live.chromeVersion", live.chromeMajorVersion == 0 ? "unknown" : String(live.chromeMajorVersion))
emit("live.excludedHoros", live.chromeExcludedSchemes["horos"].map { $0 ? "true" : "false" } ?? "absent")
dump("live", HorosSchemeURL.diagnose(studyURL, snapshot: live))
'''

swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
results = {}
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
elif not source.is_file():
    failures.append('HorosSchemeURL.swift is missing')
else:
    with tempfile.TemporaryDirectory(prefix='horos-scheme-launch-') as directory:
        driver = Path(directory) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(directory) / 'scheme-launch'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-framework', 'AppKit',
                                '-o', str(binary), str(source), str(driver)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('HorosSchemeURL.swift does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the launch driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value


def expect(key, value, detail):
    got = results.get(key)
    if got != value:
        failures.append('%s: expected %r, got %r (%s)' % (key, value, got, detail))


if results:
    expect('delivered.layer', 'accepted', 'an Apple Event that Horos received is accepted')
    expect('delivered.code', 'ok', 'accepted system delivery')

    expect('noLS.layer', 'launchServices', 'no handler is LaunchServices, not the parser')
    expect('noLS.code', 'no-handler', 'name the missing registration')

    expect('otherLS.layer', 'launchServices', 'another app owning the scheme is LaunchServices')
    if 'com.example.other-viewer' not in (results.get('otherLS.message') or ''):
        failures.append('other-app diagnosis does not name the chosen bundle: %r'
                        % results.get('otherLS.message'))

    expect('excluded.layer', 'browser', 'Chrome excluded_schemes is a browser policy')
    expect('excluded.code', 'chrome-excluded-scheme', 'name the Chrome key')
    if 'excluded_schemes' not in (results.get('excluded.message') or ''):
        failures.append('Chrome block does not name excluded_schemes: %r'
                        % results.get('excluded.message'))

    expect('gesture.layer', 'browser', 'Chrome 94+ without a gesture is a browser policy')
    expect('gesture.code', 'chrome-user-gesture', 'name the Chrome 94 user-gesture rule')

    expect('prompt.layer', 'browser', 'a click that never arrived is the external-protocol prompt')
    expect('prompt.code', 'chrome-external-protocol-prompt', 'name the prompt')

    expect('parserWins.layer', 'parser',
           'an invalid DisplayStudy stays a parser error when Chrome would also block')
    expect('parserWins.code', 'invalid-parameters', 'parser wins over browser')

    expect('fromPrefs.layer', 'browser', 'Chrome Preferences JSON is read, not rewritten')
    expect('fromPrefs.code', 'chrome-excluded-scheme', 'excluded_schemes.horos == true')

    # Live read is evidence, not a gate: this machine may have several Horos copies.
    live_layer = results.get('live.layer')
    if live_layer not in ('accepted', 'launchServices', 'browser'):
        failures.append('live diagnosis is not one of the three layers: %r' % live_layer)
    print('live candidates: %s' % results.get('live.candidates'))
    print('live chosen: %s' % results.get('live.chosen'))
    print('live chrome: %s excluded=%s → %s/%s'
          % (results.get('live.chromeVersion'), results.get('live.excludedHoros'),
             results.get('live.layer'), results.get('live.code')))

# getUrl must not rewrite LaunchServices.plist or Chrome preferences.
if 'com.apple.LaunchServices.plist' in application[application.find('getUrl:'):application.find('getUrl:') + 9000]:
    failures.append('getUrl: writes LaunchServices.plist again')
if 'LSSetDefaultHandlerForURLScheme' in application:
    failures.append('AppController still calls LSSetDefaultHandlerForURLScheme')

if 'LSIsAppleDefaultForType' not in info:
    failures.append('Info.plist no longer claims the default role for the schemes')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: diagnosis names LaunchServices, Chrome protocol policy, and the '
      'parser as separate layers, and never writes a browser or LS preference')
