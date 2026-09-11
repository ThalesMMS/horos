// Temporary LaunchServices setup for #299 native validation; not part of Horos.
// No argument: read the handler. One bundle identifier: explicitly set it.
// Save both output lines before changing it; restore and compare after testing.
import AppKit
import CoreServices

precondition(CommandLine.arguments.count <= 2, "usage: handler [bundle-identifier]")
if CommandLine.arguments.count == 2 {
    let status = LSSetDefaultHandlerForURLScheme("horos" as CFString,
                                                CommandLine.arguments[1] as CFString)
    precondition(status == noErr, "setting handler failed: \(status)")
}
guard let application = NSWorkspace.shared.urlForApplication(toOpen: URL(string: "horos://test")!),
      let identifier = Bundle(url: application)?.bundleIdentifier else {
    fatalError("No registered horos:// handler; do not change it without a restoration plan")
}
print(identifier)
print(application.path)
