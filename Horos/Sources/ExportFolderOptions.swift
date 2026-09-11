import AppKit

/// Adds field choices to the existing export accessory without duplicating its controls.
@objc(HorosExportFolderOptions)
public final class ExportFolderOptions: NSView {
    private let patient = NSPopUpButton()
    private let study = NSPopUpButton()
    private let series = NSPopUpButton()
    private let custom = NSButton(checkboxWithTitle: NSLocalizedString("Customize folder names", comment: ""), target: nil, action: nil)
    private var observer: NSObjectProtocol?
    private static let preference = "DICOMExportFolderFields"

    @objc(initWithLegacyView:)
    public init(legacyView: NSView) {
        let height = legacyView.frame.height
        super.init(frame: NSRect(x: 0, y: 0, width: max(540, legacyView.frame.width), height: height + 158))
        legacyView.setFrameOrigin(.zero)
        addSubview(legacyView)
        custom.frame = NSRect(x: 16, y: height + 130, width: 500, height: 22)
        custom.target = self
        custom.action = #selector(updateControls)
        addSubview(custom)
        let fields: [(String, NSPopUpButton, [String])] = [
            ("Patient folder:", patient, ["Patient name", "Patient ID"]),
            ("Study folder:", study, ["Description and Study ID", "Study description", "Study Instance UID"]),
            ("Series folder:", series, ["Description and number", "Series description", "Series number", "Series Instance UID"])
        ]
        for (index, field) in fields.enumerated() {
            let y = height + 100 - CGFloat(index * 29)
            let label = NSTextField(labelWithString: NSLocalizedString(field.0, comment: ""))
            label.frame = NSRect(x: 18, y: y + 3, width: 135, height: 20)
            addSubview(label)
            field.1.frame = NSRect(x: 155, y: y, width: frame.width - 175, height: 26)
            field.1.autoresizingMask = [.width]
            field.1.addItems(withTitles: field.2.map { NSLocalizedString($0, comment: "") })
            field.1.setAccessibilityLabel(NSLocalizedString(field.0, comment: ""))
            addSubview(field.1)
        }
        let note = NSTextField(labelWithString: NSLocalizedString("DICOMDIR uses standard names. Custom names include a stable reference.", comment: ""))
        note.frame = NSRect(x: 18, y: height + 10, width: frame.width - 36, height: 20)
        note.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        note.textColor = .secondaryLabelColor
        addSubview(note)
        if let saved = UserDefaults.standard.dictionary(forKey: Self.preference) {
            custom.state = (saved["enabled"] as? Bool == true) ? .on : .off
            for (key, popup) in [("patient", patient), ("study", study), ("series", series)] {
                if let index = saved[key] as? Int, (0..<popup.numberOfItems).contains(index) { popup.selectItem(at: index) }
            }
        }
        observer = NotificationCenter.default.addObserver(forName: UserDefaults.didChangeNotification, object: nil, queue: .main) { [weak self] _ in
            self?.updateControls()
        }
        updateControls()
    }

    required init?(coder: NSCoder) { fatalError("Use init(legacyView:)") }
    deinit { if let observer { NotificationCenter.default.removeObserver(observer) } }

    @objc private func updateControls() {
        let ordinary = !UserDefaults.standard.bool(forKey: "AddDICOMDIRForExport")
        custom.isEnabled = ordinary
        for popup in [patient, study, series] { popup.isEnabled = ordinary && custom.state == .on }
    }

    /// Persist only after the export panel is accepted. Other export flows never read this preference.
    @objc public func acceptedOptions() -> NSDictionary? {
        let values: [String: Any] = ["enabled": custom.state == .on, "patient": patient.indexOfSelectedItem,
                                     "study": study.indexOfSelectedItem, "series": series.indexOfSelectedItem]
        UserDefaults.standard.set(values, forKey: Self.preference)
        return custom.state == .on && !UserDefaults.standard.bool(forKey: "AddDICOMDIRForExport") ? values as NSDictionary : nil
    }
}
