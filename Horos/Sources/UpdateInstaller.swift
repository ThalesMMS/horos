//  Copyright (c) 2026 Thales Matheus M Santos (ThalesMMS)
//
//  This file is part of a fork of Horos (https://github.com/ThalesMMS/horos).
//
//  It is free software: you can redistribute it and/or modify it under the
//  terms of the GNU Lesser General Public License as published by the Free
//  Software Foundation, version 3 of the License.
//
//  It is distributed in the hope that it will be useful, but WITHOUT ANY
//  WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
//  A PARTICULAR PURPOSE. See the GNU Lesser General Public License for details.

#if !MACAPPSTORE
import AppKit

/// The window shown while a release is downloaded, verified and installed.
@MainActor private final class UpdateProgressPanel: NSObject {
    private let panel: NSPanel
    private let label = NSTextField(labelWithString: "")
    private let detail = NSTextField(labelWithString: "")
    private let indicator = NSProgressIndicator()
    private let button = NSButton(title: NSLocalizedString("Cancel", comment: ""), target: nil, action: nil)
    private let formatter = ByteCountFormatter()
    var onCancel: (() -> Void)?

    override init() {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 440, height: 130),
                        styleMask: [.titled], backing: .buffered, defer: true)
        super.init()
        panel.title = NSLocalizedString("Software Update", comment: "Update progress window title")
        panel.isReleasedWhenClosed = false
        panel.hidesOnDeactivate = false
        // The application stays usable during the download; keep the progress over its windows.
        panel.level = .floating
        formatter.countStyle = .file
        indicator.style = .bar
        indicator.minValue = 0
        indicator.maxValue = 1
        detail.textColor = .secondaryLabelColor
        detail.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        label.lineBreakMode = .byTruncatingTail
        button.target = self
        button.action = #selector(cancel(_:))
        button.keyEquivalent = "\u{1b}"
        let footer = NSStackView(views: [detail, NSView(), button])
        footer.orientation = .horizontal
        let stack = NSStackView(views: [label, indicator, footer])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.edgeInsets = NSEdgeInsets(top: 18, left: 20, bottom: 16, right: 20)
        stack.translatesAutoresizingMaskIntoConstraints = false
        let content = NSView()
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            content.widthAnchor.constraint(equalToConstant: 440),
            indicator.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40),
            footer.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40)
        ])
        panel.contentView = content
    }

    func show(_ text: String) {
        label.stringValue = text
        indicator.isIndeterminate = true
        indicator.startAnimation(nil)
        panel.center()
        panel.makeKeyAndOrderFront(nil)
    }

    func showProgress(_ received: Int64, of expected: Int64) {
        indicator.isIndeterminate = false
        indicator.doubleValue = expected > 0 ? Double(received) / Double(expected) : 0
        detail.stringValue = String(format: NSLocalizedString("%@ of %@", comment: "Downloaded bytes of total bytes"),
                                    formatter.string(fromByteCount: received), formatter.string(fromByteCount: expected))
    }

    /// A step that cannot be interrupted halfway.
    func showActivity(_ text: String) {
        label.stringValue = text
        detail.stringValue = ""
        indicator.isIndeterminate = true
        indicator.startAnimation(nil)
        button.isEnabled = false
    }

    func close() { panel.close() }

    @objc private func cancel(_ sender: Any?) { onCancel?() }
}

/// Downloads a published release, verifies it and puts it in place of the
/// running copy, which then quits and reopens. One installation at a time.
@MainActor @objc(HorosUpdateInstaller)
final class UpdateInstaller: NSObject {
    private static var current: UpdateInstaller?
    private static let team = UpdateBundle.developerIDTeam(of: Bundle.main.bundleURL)

    /// Development copies carry no release build number to compare, so they
    /// are neither told about releases on their own nor replaced by one.
    @objc static var isReleaseCopy: Bool { team != nil }

    static var isBusy: Bool { current != nil }

    /// The build the user was last told about and left for later. The hourly
    /// check does not ask about it again before the application is reopened.
    static var postponedBuild: String?

    static func canInstall(_ release: UpdateRelease) -> Bool {
        guard release.archive != nil, team != nil, current == nil else { return false }
        if let minimum = release.minimumSystemVersion, !ProcessInfo.processInfo.isOperatingSystemAtLeast(minimum) {
            return false
        }
        if case .replaceable = UpdateBundle.location(of: Bundle.main.bundleURL) { return true }
        return false
    }

    /// `confirmQuit` asks the application whether it may quit now and prepares
    /// it to; `quit` then ends it without asking again.
    static func install(_ release: UpdateRelease, confirmQuit: @escaping @MainActor () -> Bool,
                        quit: @escaping @MainActor () -> Void) {
        let destination = Bundle.main.bundleURL.standardizedFileURL
        guard current == nil, let archive = release.archive, let team,
              let identifier = Bundle.main.bundleIdentifier,
              case .replaceable(let authorization) = UpdateBundle.location(of: destination) else { return }
        // A folder on the volume of the installed copy, so that the new one is renamed into place.
        let folder: URL
        do {
            folder = try FileManager.default.url(for: .itemReplacementDirectory, in: .userDomainMask,
                                                 appropriateFor: destination, create: true)
        } catch {
            report(.download(error.localizedDescription))
            return
        }
        let installer = UpdateInstaller(release: release, archive: archive, destination: destination,
                                        authorization: authorization, identifier: identifier, team: team,
                                        folder: folder, confirmQuit: confirmQuit, quit: quit)
        current = installer
        installer.start()
    }

    private static func report(_ error: UpdateInstallError) {
        guard error != .cancelled else { return }
        let button = HorosAlertPanel.run(title: NSLocalizedString("Update Not Installed", comment: ""),
                                         message: error.message,
                                         defaultButton: NSLocalizedString("OK", comment: ""),
                                         alternateButton: NSLocalizedString("View Fork Releases", comment: ""),
                                         otherButton: nil)
        if button == HorosAlertPanel.alternateResponse {
            NSWorkspace.shared.open(UpdateFeedClient.releasesURL)
        }
    }

    private let release: UpdateRelease
    private let archive: UpdateRelease.Archive
    private let destination: URL
    private let authorization: Bool
    private let identifier: String
    private let team: String
    private let folder: URL
    private let confirmQuit: @MainActor () -> Bool
    private let quit: @MainActor () -> Void
    private let panel = UpdateProgressPanel()
    private var download: UpdateDownload?

    private init(release: UpdateRelease, archive: UpdateRelease.Archive, destination: URL, authorization: Bool,
                 identifier: String, team: String, folder: URL,
                 confirmQuit: @escaping @MainActor () -> Bool, quit: @escaping @MainActor () -> Void) {
        self.release = release
        self.archive = archive
        self.destination = destination
        self.authorization = authorization
        self.identifier = identifier
        self.team = team
        self.folder = folder
        self.confirmQuit = confirmQuit
        self.quit = quit
    }

    private func start() {
        let name = String(format: "%@ (%@)", release.version ?? "", release.build)
        panel.show(String(format: NSLocalizedString("Downloading Isis DICOM Viewer %@…", comment: "Update download; version and build"), name))
        panel.onCancel = { [weak self] in self?.download?.cancel() }
        let download = UpdateDownload(archive: archive, destination: folder.appendingPathComponent("Horos.zip"),
            progress: { [weak self] received, expected in self?.panel.showProgress(received, of: expected) },
            completion: { [weak self] result in self?.downloaded(result) })
        self.download = download
        download.start()
    }

    private func downloaded(_ result: Result<URL, UpdateInstallError>) {
        download = nil
        guard case .success(let file) = result else {
            if case .failure(let error) = result { finish(error) }
            return
        }
        panel.showActivity(NSLocalizedString("Verifying the download…", comment: "Update verification"))
        let release = self.release, identifier = self.identifier, team = self.team
        let extracted = folder.appendingPathComponent("Extracted")
        let installed = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        // Hashing every file of the new bundle takes seconds; keep the window alive meanwhile.
        DispatchQueue.global(qos: .userInitiated).async {
            let outcome: Result<URL, UpdateInstallError>
            do {
                let application = try UpdateBundle.extract(file, into: extracted)
                try UpdateBundle.verify(application, release: release, identifier: identifier,
                                        installedBuild: installed, team: team)
                outcome = .success(application)
            } catch let error as UpdateInstallError {
                outcome = .failure(error)
            } catch {
                outcome = .failure(.extraction)
            }
            DispatchQueue.main.async { self.verified(outcome) }
        }
    }

    private func verified(_ outcome: Result<URL, UpdateInstallError>) {
        guard case .success(let application) = outcome else {
            if case .failure(let error) = outcome { finish(error) }
            return
        }
        panel.showActivity(NSLocalizedString("Installing the update…", comment: "Update installation"))
        // Nothing is replaced until the application has agreed to quit.
        while !confirmQuit() {
            let button = HorosAlertPanel.run(title: NSLocalizedString("New Stable Build Available", comment: ""),
                message: NSLocalizedString("Isis DICOM Viewer cannot quit now. Finish or close what is in progress, then install the update.", comment: "Update waiting for quit"),
                defaultButton: NSLocalizedString("Install Now", comment: "Update retry after quit was refused"),
                alternateButton: NSLocalizedString("Cancel", comment: ""), otherButton: nil)
            if button != HorosAlertPanel.defaultResponse {
                finish(.cancelled)
                return
            }
        }
        do {
            try UpdateBundle.replace(destination, with: application, authorization: authorization)
        } catch let error as UpdateInstallError {
            finish(error)
            return
        } catch {
            finish(.replacement(error.localizedDescription))
            return
        }
        // The new copy is in place: quit even if it cannot be reopened from here.
        do { try HorosNativeInstallOperations().relaunch(destination, diskImage: nil) }
        catch { NSLog("The updated application could not be scheduled to reopen: %@", error.localizedDescription) }
        discard()
        quit()
    }

    private func discard() {
        panel.close()
        // Only the unique folder this installation created.
        try? FileManager.default.removeItem(at: folder)
        Self.current = nil
    }

    private func finish(_ error: UpdateInstallError) {
        discard()
        Self.report(error)
    }
}

#endif
