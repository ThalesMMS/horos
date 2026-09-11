#!/usr/bin/env python3
"""Product binaries stay arm64-only; Intel-only plugins and helpers are named."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def compile_binary(destination, architectures):
    source = destination.with_suffix('.c')
    source.write_text('int main(void) { return 0; }\n')
    command = ['xcrun', 'clang']
    for architecture in architectures:
        command += ['-arch', architecture]
    subprocess.run(command + [str(source), '-o', str(destination)], check=True)


code = r'''
import Foundation

func expect(_ ok: Bool, _ message: String) {
    precondition(ok, message)
}

func packedPlugin(at folder: URL, name: String, executable: String) -> String {
    let bundle = folder.appendingPathComponent(name + ".horosplugin")
    let macos = bundle.appendingPathComponent("Contents/MacOS")
    try! FileManager.default.createDirectory(at: macos, withIntermediateDirectories: true)
    try! FileManager.default.copyItem(atPath: executable, toPath: macos.appendingPathComponent(name).path)
    let info: [String: Any] = [
        "CFBundleExecutable": name,
        "CFBundleIdentifier": "org.horosproject.qa." + name,
        "NSPrincipalClass": name
    ]
    (info as NSDictionary).write(to: bundle.appendingPathComponent("Contents/Info.plist"), atomically: true)
    return bundle.path
}

let folder = URL(fileURLWithPath: CommandLine.arguments[1])
let arm = folder.appendingPathComponent("Horos").path
let universal = folder.appendingPathComponent("HorosUniversal").path
let intel = folder.appendingPathComponent("dciodvfy").path
let pluginIntel = packedPlugin(at: folder, name: "QAIntel",
                                executable: folder.appendingPathComponent("plugin-intel").path)
let pluginArm = packedPlugin(at: folder, name: "QAArm",
                             executable: folder.appendingPathComponent("plugin-arm").path)
let pluginUniversal = packedPlugin(at: folder, name: "QAUniversal",
                                   executable: folder.appendingPathComponent("plugin-universal").path)

let productOK = HorosArchitectureAudit.productDiagnosis(at: arm)
expect(productOK.accepted && productOK.architectures == ["arm64"],
       "arm64 product is accepted: \(productOK.diagnosis)")

let productUniversal = HorosArchitectureAudit.productDiagnosis(at: universal)
expect(!productUniversal.accepted && productUniversal.diagnosis.contains("Intel slices"),
       "universal product is a publication path: \(productUniversal.diagnosis)")

let pluginRefused = HorosArchitectureAudit.pluginDiagnosis(at: pluginIntel)
expect(pluginRefused == "This plugin is Intel-only (x86_64) and cannot load in this arm64 Horos process. Obtain an arm64 plugin from its author.",
       "Intel-only plugin is named before load: \(pluginRefused ?? "nil")")
expect(HorosArchitectureAudit.pluginDiagnosis(at: pluginArm) == nil,
       "arm64 plugin stays loadable")
expect(HorosArchitectureAudit.pluginDiagnosis(at: pluginUniversal) == nil,
       "universal plugin that includes arm64 still loads")

let helper = HorosArchitectureAudit.helperDiagnosis(at: intel)
expect(helper?.contains("dciodvfy is Intel-only") == true, "helper keeps a named diagnosis: \(helper ?? "nil")")
expect(helper?.contains("not launched under Rosetta") == true, "Rosetta is not the product path")
expect(HorosArchitectureAudit.helperDiagnosis(at: arm) == nil, "arm64 helper may run")
expect(HorosArchitectureAudit.helperDiagnosis(at: folder.appendingPathComponent("missing").path) == nil,
       "missing helper is not an architecture diagnosis")

print("PASS: arm64 product; Intel plugin/helper named; universal plugin with arm64 still loads")
'''

with tempfile.TemporaryDirectory(prefix='horos-arm64-dist-') as directory:
    folder = Path(directory)
    compile_binary(folder / 'Horos', ['arm64'])
    compile_binary(folder / 'HorosUniversal', ['arm64', 'x86_64'])
    compile_binary(folder / 'dciodvfy', ['x86_64'])
    compile_binary(folder / 'plugin-intel', ['x86_64'])
    compile_binary(folder / 'plugin-arm', ['arm64'])
    compile_binary(folder / 'plugin-universal', ['arm64', 'x86_64'])
    main = folder / 'main.swift'
    main.write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/HorosArchitectureAudit.swift'),
        str(main), '-o', str(folder / 'test')
    ], check=True)
    subprocess.run([str(folder / 'test'), str(folder)], check=True)
