import AppKit

/// The Listener preferences' door to the XML-RPC network policy.
///
/// The preference pane has no free row left around the XML-RPC controls, and
/// the choice being made here - publishing the database to the network - wants
/// more than a checkbox anyway: it needs a password and it needs to say what it
/// exposes. So the pane gets one small button in the empty space beside the port
/// field, and the button opens a sheet.
///
/// The button is installed by walking the view tree for the port field's
/// binding, the same way the pane already installs its port formatters, so this
/// works in every localization without touching a nib.
@objc(HorosXMLRPCRemoteAccessPanel)
public final class XMLRPCRemoteAccessPanel: NSObject {
    /// What the sheet is editing.
    public struct Settings: Equatable {
        public var allowRemote: Bool
        public var username: String
        public var password: String

        public init(allowRemote: Bool, username: String, password: String) {
            self.allowRemote = allowRemote
            self.username = username
            self.password = password
        }

        /// Why these values cannot be saved, or `nil` when they can.
        ///
        /// Turning remote access off never needs a credential; turning it on
        /// always does, because the listener would otherwise stay on loopback
        /// and the setting would silently do nothing.
        public var refusal: String? {
            guard allowRemote else { return nil }
            guard XMLRPCServerAccess.basicHeader(username: username, password: password) != nil else {
                return NSLocalizedString(
                    "Enter a user name without a colon and a password before letting the XML-RPC "
                        + "interface answer other network interfaces.",
                    comment: "XML-RPC credential refusal")
            }
            return nil
        }
    }

    static let buttonWidth: CGFloat = 108
    static let buttonGap: CGFloat = 8

    /// Adds the button beside the XML-RPC port field, and returns it.
    ///
    /// Returns `nil` when the field is not in this tree, or when the space to
    /// its right is too narrow to hold the button - a pane that has been
    /// rearranged should lose the button rather than draw it over something.
    @objc(installInView:)
    @discardableResult
    public static func install(in view: NSView) -> NSButton? {
        guard let field = portField(in: view), let parent = field.superview else { return nil }
        if let existing = parent.subviews.first(where: { $0.identifier == identifier }) as? NSButton {
            return existing
        }
        let left = field.frame.maxX + buttonGap
        guard left + buttonWidth <= parent.bounds.width else { return nil }

        let button = NSButton(frame: NSRect(x: left,
                                            y: field.frame.midY - 8,
                                            width: buttonWidth,
                                            height: 16))
        button.identifier = identifier
        button.bezelStyle = .rounded
        button.controlSize = .small
        button.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        button.title = NSLocalizedString("Network Access…", comment: "XML-RPC network access button")
        button.autoresizingMask = [.maxXMargin, .minYMargin]
        button.target = shared
        button.action = #selector(open(_:))
        parent.addSubview(button)
        return button
    }

    static let identifier = NSUserInterfaceItemIdentifier("HorosXMLRPCNetworkAccess")

    static func portField(in view: NSView) -> NSTextField? {
        if let field = view as? NSTextField,
           let observed = field.infoForBinding(.value)?[NSBindingInfoKey.observedKeyPath] as? String,
           observed == "values.httpXMLRPCServerPort" {
            return field
        }
        for child in view.subviews {
            if let field = portField(in: child) { return field }
        }
        return nil
    }

    static let shared = XMLRPCRemoteAccessPanel()

    private var sheet: NSWindow?
    private var remoteCheckbox: NSButton?
    private var usernameField: NSTextField?
    private var passwordField: NSSecureTextField?
    private var refusalLabel: NSTextField?

    @objc func open(_ sender: NSButton) {
        guard let host = sender.window else { return }
        let stored = XMLRPCServerCredential.username ?? ""
        let sheet = makeSheet(settings: Settings(
            allowRemote: UserDefaults.standard.bool(forKey: XMLRPCServerAccess.allowRemoteKey),
            username: stored,
            password: ""))
        self.sheet = sheet
        host.beginSheet(sheet) { [weak self] _ in self?.sheet = nil }
    }

    /// The sheet, built in code: a checkbox, a credential, and a paragraph
    /// saying what turning this on publishes.
    func makeSheet(settings: Settings) -> NSWindow {
        let width: CGFloat = 460
        let content = NSView(frame: NSRect(x: 0, y: 0, width: width, height: 250))

        let title = label(NSLocalizedString("XML-RPC Network Access", comment: "XML-RPC sheet title"),
                          frame: NSRect(x: 20, y: 210, width: width - 40, height: 20))
        title.font = NSFont.boldSystemFont(ofSize: NSFont.systemFontSize)
        content.addSubview(title)

        let warning = label(XMLRPCServerAccess.exposureWarning,
                            frame: NSRect(x: 20, y: 140, width: width - 40, height: 62))
        warning.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        warning.textColor = .secondaryLabelColor
        warning.cell?.wraps = true
        content.addSubview(warning)

        let checkbox = NSButton(checkboxWithTitle: NSLocalizedString(
            "Answer other network interfaces, not only this machine",
            comment: "XML-RPC remote access checkbox"), target: nil, action: nil)
        checkbox.frame = NSRect(x: 20, y: 112, width: width - 40, height: 18)
        checkbox.state = settings.allowRemote ? .on : .off
        content.addSubview(checkbox)
        remoteCheckbox = checkbox

        let userLabel = label(NSLocalizedString("User name:", comment: "XML-RPC user name"),
                              frame: NSRect(x: 20, y: 84, width: 90, height: 17))
        userLabel.alignment = .right
        content.addSubview(userLabel)
        let username = NSTextField(frame: NSRect(x: 118, y: 82, width: width - 138, height: 22))
        username.stringValue = settings.username
        content.addSubview(username)
        usernameField = username

        let passwordLabel = label(NSLocalizedString("Password:", comment: "XML-RPC password"),
                                  frame: NSRect(x: 20, y: 54, width: 90, height: 17))
        passwordLabel.alignment = .right
        content.addSubview(passwordLabel)
        let password = NSSecureTextField(frame: NSRect(x: 118, y: 52, width: width - 138, height: 22))
        password.stringValue = settings.password
        content.addSubview(password)
        passwordField = password

        let refusal = label("", frame: NSRect(x: 20, y: 20, width: width - 200, height: 28))
        refusal.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        refusal.textColor = .systemRed
        refusal.cell?.wraps = true
        content.addSubview(refusal)
        refusalLabel = refusal

        let cancel = NSButton(title: NSLocalizedString("Cancel", comment: ""), target: self, action: #selector(cancel(_:)))
        cancel.bezelStyle = .rounded
        cancel.frame = NSRect(x: width - 190, y: 16, width: 80, height: 32)
        cancel.keyEquivalent = "\u{1b}"
        content.addSubview(cancel)

        let save = NSButton(title: NSLocalizedString("Save", comment: ""), target: self, action: #selector(save(_:)))
        save.bezelStyle = .rounded
        save.frame = NSRect(x: width - 100, y: 16, width: 80, height: 32)
        save.keyEquivalent = "\r"
        content.addSubview(save)

        let sheet = NSWindow(contentRect: content.frame,
                             styleMask: [.titled],
                             backing: .buffered,
                             defer: true)
        sheet.contentView = content
        return sheet
    }

    func label(_ text: String, frame: NSRect) -> NSTextField {
        let field = NSTextField(frame: frame)
        field.stringValue = text
        field.isEditable = false
        field.isSelectable = false
        field.isBezeled = false
        field.drawsBackground = false
        return field
    }

    /// What the sheet currently holds.
    var settings: Settings {
        return Settings(allowRemote: remoteCheckbox?.state == .on,
                        username: usernameField?.stringValue ?? "",
                        password: passwordField?.stringValue ?? "")
    }

    @objc func cancel(_ sender: Any?) {
        finish()
    }

    @objc func save(_ sender: Any?) {
        let settings = self.settings
        if let refusal = settings.refusal {
            refusalLabel?.stringValue = refusal
            return
        }
        apply(settings)
        finish()
    }

    /// Writes the credential before the preference, so the listener never sees
    /// remote access enabled without something to check requests against.
    func apply(_ settings: Settings) {
        if settings.allowRemote {
            do {
                try XMLRPCServerCredential.save(username: settings.username, password: settings.password)
            } catch {
                refusalLabel?.stringValue = error.localizedDescription
                return
            }
        } else if !settings.password.isEmpty || !settings.username.isEmpty {
            // Keep a credential the user typed but did not enable, so turning
            // remote access on again does not ask for it a second time.
            try? XMLRPCServerCredential.save(username: settings.username, password: settings.password)
        }
        UserDefaults.standard.set(settings.allowRemote, forKey: XMLRPCServerAccess.allowRemoteKey)
    }

    func finish() {
        guard let sheet = sheet, let host = sheet.sheetParent else { return }
        host.endSheet(sheet)
        self.sheet = nil
    }
}

extension XMLRPCServerCredential {
    /// The user name stored with the credential, decoded from the header, so
    /// the sheet can show it without the password.
    @objc public static var username: String? {
        guard let header = header, header.hasPrefix("Basic ") else { return nil }
        guard let decoded = Data(base64Encoded: String(header.dropFirst(6))),
              let joined = String(data: decoded, encoding: .utf8),
              let colon = joined.firstIndex(of: ":") else { return nil }
        return String(joined[joined.startIndex..<colon])
    }
}
