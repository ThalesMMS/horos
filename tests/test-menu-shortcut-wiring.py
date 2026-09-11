#!/usr/bin/env python3
"""Plugin menus, 3D reconstructions and the Hot Keys pane share one catalog."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []


def read(path):
    return (root / path).read_text(errors='replace')


catalog = read('Horos/Sources/MenuShortcutCatalog.swift')
pref = read('Horos/Sources/MenuShortcutPref.swift')
plugin = read('Horos/Sources/PluginManager.m')
prefs_window = read('Horos/Sources/PreferencesWindowController.mm')
project = read('Horos.xcodeproj/project.pbxproj')
hotkeys = read('Preference Panes/OSIHotKeysPreferencePane/OSIHotKeysPref.m')
main_menu = read('Horos/Resources/en.lproj/MainMenu.xib')

checks = [
    ('@objc(HorosMenuShortcutCatalog)' in catalog, 'Swift catalog is the new component'),
    ('HorosMenuShortcuts' in catalog, 'assignments persist in UserDefaults'),
    ('reconstruction.3dMPR' in catalog and 'reconstruction.vr' in catalog,
     'MPR and VR are first-class assignable commands'),
    ('plugin.' in catalog and 'menuTitle' in catalog, 'plugin menu titles are addressable'),
    ('kind' in catalog and 'occupied' in catalog.lower(),
     'a clash with an existing command is detected'),
    ('@objc(HorosMenuShortcutPref)' in pref, 'configuration lives in a Horos preference pane'),
    ('MenuShortcutCatalog' in pref, 'the pane writes through the catalog'),
    ('HorosMenuShortcutPref' in prefs_window, 'the pane is registered next to Hot Keys'),
    ('applyStoredAssignments' in plugin, 'plugin menus receive stored shortcuts after they are built'),
    ('MenuShortcutCatalog.swift in Sources' in project, 'the catalog is compiled into Horos'),
    ('MenuShortcutPref.swift in Sources' in project, 'the preference pane is compiled into Horos'),
    ('setObject: key forKey:@"key"' in hotkeys, 'the existing viewer Hot Keys pane is unchanged'),
    ('selector="mprViewer:"' in main_menu and 'selector="VRViewer:"' in main_menu,
     '3D MPR and VR remain the reconstruction menu actions'),
    ('ViewerReferenceLines' not in catalog and 'Viewer.xib' not in catalog,
     'reference-line work is left alone'),
]

for ok, what in checks:
    if not ok:
        failures.append(what)

if failures:
    print('FAIL')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)
print('ok: plugin and reconstruction shortcuts are wired through the catalog and preferences')
