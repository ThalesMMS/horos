import AppKit
import Vision

/// What the patient list window needs from the database and the
/// Query/Retrieve (#703): BrowserController answers it.
@objc(HorosPatientListAlbumHost)
public protocol PatientListAlbumHost: NSObjectProtocol {
    /// The local studies of the patient a list entry names: those whose patient
    /// ID is `identifier`, those whose name has the words of `name`, and the
    /// other studies of the patients found. One dictionary per study, with
    /// `objectID`, `patientUID`, `patientID`, `name`, `dateOfBirth`, `sex`, `date`.
    @objc(patientListCandidatesForIdentifier:name:)
    func patientListCandidates(identifier: String?, name: String) -> [[String: Any]]

    /// Re-reads each study, refuses if its patient ID or name is no longer the
    /// one in `expected` (same order as `studies`), and creates the album.
    /// Returns the album's name, made unique.
    @objc(patientListCreateAlbumNamed:studies:expected:error:)
    func patientListCreateAlbum(named: String, studies: [Any], expected: [[String: Any]]) throws -> String

    /// Opens the Query/Retrieve window on this patient, by identifier when there
    /// is one, else by name, keeping the user's own filters.
    @objc(patientListQueryPACSWithIdentifier:name:)
    func patientListQueryPACS(identifier: String?, name: String)
}

/// Text recognition of the image, on this Mac only.
@objc(HorosPatientListRecognizer)
public final class PatientListRecognizer: NSObject {
    /// Lines, top to bottom, and the lowest confidence of the words on each.
    @objc public static func recognize(_ image: NSImage, completion: @escaping ([String], [NSNumber], String?) -> Void) {
        guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            completion([], [], NSLocalizedString("The clipboard image cannot be read.", comment: "Patient list import"))
            return
        }
        DispatchQueue.global(qos: .userInitiated).async {
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            // A correction dictionary turns unfamiliar names into words.
            request.usesLanguageCorrection = false
            request.recognitionLanguages = languages(for: request)
            var lines: [String] = [], confidences: [NSNumber] = [], problem: String?
            do {
                try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
                (lines, confidences) = group(request.results ?? [])
            } catch {
                problem = error.localizedDescription
            }
            DispatchQueue.main.async { completion(lines, confidences, problem) }
        }
    }

    /// The user's languages the recognizer knows, then English.
    static func languages(for request: VNRecognizeTextRequest) -> [String] {
        let supported = (try? request.supportedRecognitionLanguages()) ?? ["en-US"]
        var chosen: [String] = []
        for preferred in Locale.preferredLanguages {
            let language = preferred.split(separator: "-").first.map(String.init) ?? preferred
            if let match = supported.first(where: { $0 == preferred }) ?? supported.first(where: { $0.hasPrefix(language) }),
               !chosen.contains(match) {
                chosen.append(match)
            }
        }
        if !chosen.contains("en-US"), supported.contains("en-US") { chosen.append("en-US") }
        return chosen.isEmpty ? supported : chosen
    }

    /// Words whose centres are within half a line height of each other are one
    /// line, read left to right.
    static func group(_ observations: [VNRecognizedTextObservation]) -> ([String], [NSNumber]) {
        struct Word { let text: String; let box: CGRect; let confidence: Float }
        let words = observations.compactMap { observation -> Word? in
            guard let best = observation.topCandidates(1).first else { return nil }
            return Word(text: best.string, box: observation.boundingBox, confidence: best.confidence)
        }.sorted { $0.box.midY > $1.box.midY }
        var lines: [[Word]] = []
        for word in words {
            if let last = lines.last, let first = last.first,
               abs(first.box.midY - word.box.midY) < 0.45 * max(first.box.height, word.box.height) {
                lines[lines.count - 1].append(word)
            } else {
                lines.append([word])
            }
        }
        let ordered = lines.map { $0.sorted { $0.box.minX < $1.box.minX } }
        return (ordered.map { $0.map(\.text).joined(separator: " ") },
                ordered.map { NSNumber(value: Double($0.map(\.confidence).min() ?? 0)) })
    }
}

/// The review: every entry the image gave, what the database found for it,
/// and why to look. Nothing is created until the user asks.
@objc(HorosPatientListAlbumWindowController)
public final class PatientListAlbumWindowController: NSWindowController, NSTableViewDataSource, NSTableViewDelegate, NSWindowDelegate {
    final class Row {
        let entry: PatientListEntry
        var candidates: [[String: Any]] = []
        var decision = PatientListDecision()
        var include = false
        init(entry: PatientListEntry) { self.entry = entry }
    }

    private static var open: Set<PatientListAlbumWindowController> = []
    private weak var host: PatientListAlbumHost?
    private var rows: [Row] = []
    private let table = NSTableView()
    private let albumName = NSTextField()
    private let status = NSTextField(labelWithString: "")

    /// Reads the clipboard's image, recognises it, and shows the review.
    @objc public static func begin(host: PatientListAlbumHost, parent: NSWindow?) {
        guard let image = NSPasteboard.general.readObjects(forClasses: [NSImage.self])?.first as? NSImage else {
            alert(NSLocalizedString("There is no image on the clipboard.", comment: "Patient list import"),
                  NSLocalizedString("Copy a screenshot of the patient list, then try again.", comment: "Patient list import"))
            return
        }
        PatientListRecognizer.recognize(image) { lines, confidences, problem in
            if let problem {
                alert(NSLocalizedString("The text of the image could not be recognised.", comment: "Patient list import"), problem)
                return
            }
            let format = PatientListFormat.fromDefaults()
            let entries = PatientListParser.entries(lines: lines, confidences: confidences, format: format)
            guard !entries.isEmpty else {
                alert(NSLocalizedString("No patient was found in the image.", comment: "Patient list import"),
                      NSLocalizedString("Each patient needs a line with a name of two words or more.", comment: "Patient list import"))
                return
            }
            let controller = PatientListAlbumWindowController(host: host, entries: entries, formatProblem: format.problem)
            open.insert(controller)
            controller.showWindow(nil)
            controller.window?.makeKeyAndOrderFront(nil)
        }
    }

    static func alert(_ message: String, _ detail: String) {
        let alert = NSAlert()
        alert.messageText = message
        alert.informativeText = detail
        alert.runModal()
    }

    init(host: PatientListAlbumHost, entries: [PatientListEntry], formatProblem: String?) {
        self.host = host
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 980, height: 460),
                              styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = NSLocalizedString("Album from Patient List", comment: "Patient list import")
        window.isReleasedWhenClosed = false
        super.init(window: window)
        window.delegate = self
        rows = entries.map(Row.init)
        build(in: window, formatProblem: formatProblem)
        refresh(nil)
        window.center()
    }

    required init?(coder: NSCoder) { nil }

    private func build(in window: NSWindow, formatProblem: String?) {
        let columns: [(String, String, CGFloat)] = [
            ("include", NSLocalizedString("Include", comment: "Patient list import"), 60),
            ("name", NSLocalizedString("Name", comment: "Patient list import"), 220),
            ("identifier", NSLocalizedString("Identifier", comment: "Patient list import"), 120),
            ("ageSex", NSLocalizedString("Age / Sex", comment: "Patient list import"), 80),
            ("local", NSLocalizedString("Local studies", comment: "Patient list import"), 110),
            ("warnings", NSLocalizedString("To check", comment: "Patient list import"), 360),
        ]
        for (identifier, title, width) in columns {
            let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(identifier))
            column.title = title
            column.width = width
            if identifier == "include" {
                let cell = NSButtonCell()
                cell.setButtonType(.switch)
                cell.title = ""
                column.dataCell = cell
            } else {
                let cell = NSTextFieldCell()
                cell.isEditable = identifier == "name" || identifier == "identifier"
                cell.lineBreakMode = .byTruncatingTail
                column.dataCell = cell
            }
            table.addTableColumn(column)
        }
        table.dataSource = self
        table.delegate = self
        table.usesAlternatingRowBackgroundColors = true
        let scroll = NSScrollView()
        scroll.documentView = table
        scroll.hasVerticalScroller = true

        albumName.stringValue = String(format: NSLocalizedString("Patient list %@", comment: "Patient list import, default album name"),
                                       DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .none))
        let nameLabel = NSTextField(labelWithString: NSLocalizedString("Album name:", comment: "Patient list import"))
        let search = NSButton(title: NSLocalizedString("Search PACS", comment: "Patient list import"), target: self, action: #selector(searchPACS(_:)))
        let refreshButton = NSButton(title: NSLocalizedString("Refresh", comment: "Patient list import"), target: self, action: #selector(refresh(_:)))
        let cancel = NSButton(title: NSLocalizedString("Cancel", comment: "Patient list import"), target: self, action: #selector(cancel(_:)))
        cancel.keyEquivalent = "\u{1b}"
        let create = NSButton(title: NSLocalizedString("Create Album", comment: "Patient list import"), target: self, action: #selector(create(_:)))
        create.keyEquivalent = "\r"
        status.lineBreakMode = .byTruncatingTail
        if let formatProblem { status.stringValue = formatProblem }

        let bottom = NSStackView(views: [nameLabel, albumName, search, refreshButton, cancel, create])
        bottom.orientation = .horizontal
        let stack = NSStackView(views: [scroll, status, bottom])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.edgeInsets = NSEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView = NSView()
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor),
            stack.bottomAnchor.constraint(equalTo: window.contentView!.bottomAnchor),
            scroll.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -24),
            albumName.widthAnchor.constraint(greaterThanOrEqualToConstant: 260),
        ])
    }

    /// Asks the database again for every entry, as after a retrieve.
    @objc func refresh(_ sender: Any?) {
        for row in rows { decide(row) }
        table.reloadData()
        updateStatus()
    }

    private func decide(_ row: Row) {
        row.candidates = host?.patientListCandidates(identifier: row.entry.identifier, name: row.entry.name) ?? []
        row.decision = PatientListMatching.decide(entry: row.entry, candidates: row.candidates, now: Date())
        row.include = row.decision.include
    }

    private func updateStatus() {
        let included = rows.filter { $0.include && !$0.decision.studies.isEmpty }
        let studies = included.reduce(0) { $0 + $1.decision.studies.count }
        status.stringValue = String(format: NSLocalizedString("%d of %d patients, %d studies will be in the album.", comment: "Patient list import"),
                                    included.count, rows.count, studies)
    }

    public func numberOfRows(in tableView: NSTableView) -> Int { rows.count }

    public func tableView(_ tableView: NSTableView, objectValueFor column: NSTableColumn?, row index: Int) -> Any? {
        let row = rows[index]
        switch column?.identifier.rawValue {
        case "include": return NSNumber(value: row.include ? 1 : 0)
        case "name": return row.entry.name
        case "identifier": return row.entry.identifier ?? ""
        case "ageSex":
            let age = row.entry.age >= 0 ? String(row.entry.age) : "–"
            return "\(age) / \(row.entry.sex ?? "–")"
        case "local":
            let count = row.decision.studies.count
            if count == 0 { return "–" }
            if count == 1 { return NSLocalizedString("1 study", comment: "Patient list import") }
            return String(format: NSLocalizedString("%d studies", comment: "Patient list import"), count)
        case "warnings": return row.decision.warnings.joined(separator: " ")
        default: return nil
        }
    }

    public func tableView(_ tableView: NSTableView, toolTipFor cell: NSCell, rect: NSRectPointer, tableColumn: NSTableColumn?,
                          row index: Int, mouseLocation: NSPoint) -> String {
        tableColumn?.identifier.rawValue == "warnings" && index < rows.count ? rows[index].decision.warnings.joined(separator: "\n") : ""
    }

    public func tableView(_ tableView: NSTableView, setObjectValue value: Any?, for column: NSTableColumn?, row index: Int) {
        let row = rows[index]
        switch column?.identifier.rawValue {
        case "include":
            // An entry with nothing found locally has nothing to include.
            row.include = (value as? NSNumber)?.boolValue == true && !row.decision.studies.isEmpty
        case "name":
            let name = (value as? String ?? "").trimmingCharacters(in: .whitespaces)
            if !name.isEmpty { row.entry.name = name; decide(row) }
        case "identifier":
            let identifier = (value as? String ?? "").trimmingCharacters(in: .whitespaces)
            row.entry.identifier = identifier.isEmpty ? nil : identifier
            decide(row)
        default: break
        }
        tableView.reloadData(forRowIndexes: IndexSet(integer: index), columnIndexes: IndexSet(integersIn: 0..<tableView.numberOfColumns))
        updateStatus()
    }

    @objc func searchPACS(_ sender: Any?) {
        guard table.selectedRow >= 0 else {
            NSSound.beep()
            return
        }
        let row = rows[table.selectedRow]
        host?.patientListQueryPACS(identifier: row.entry.identifier, name: row.entry.name)
    }

    @objc func cancel(_ sender: Any?) { window?.close() }

    @objc func create(_ sender: Any?) {
        window?.makeFirstResponder(nil)
        var studies: [Any] = [], expected: [[String: Any]] = []
        var seen = Set<NSObject>()
        for row in rows where row.include {
            for index in row.decision.studies.map(\.intValue) where index < row.candidates.count {
                let candidate = row.candidates[index]
                guard let objectID = candidate["objectID"] as? NSObject, !seen.contains(objectID) else { continue }
                seen.insert(objectID)
                studies.append(objectID)
                expected.append(["patientID": candidate["patientID"] ?? "", "name": candidate["name"] ?? ""])
            }
        }
        guard !studies.isEmpty else {
            NSSound.beep()
            return
        }
        let name = albumName.stringValue.trimmingCharacters(in: .whitespaces)
        do {
            _ = try host?.patientListCreateAlbum(named: name.isEmpty ? albumName.placeholderString ?? "Patient list" : name,
                                                 studies: studies, expected: expected)
            window?.close()
        } catch {
            Self.alert(NSLocalizedString("The album was not created.", comment: "Patient list import"), error.localizedDescription)
        }
    }

    public func windowWillClose(_ notification: Notification) {
        // The list is not kept: rows, names and identifiers go with the window.
        rows = []
        table.reloadData()
        Self.open.remove(self)
    }
}
