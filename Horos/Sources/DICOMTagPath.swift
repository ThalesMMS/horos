import Foundation

/// One step down into a sequence: which element the sequence is, and which of
/// its items to descend into.
@objc(HorosDICOMTagPathStep)
public final class DICOMTagPathStep: NSObject {
    @objc public let group: UInt16
    @objc public let element: UInt16
    /// Zero-based, as the metadata editor writes it.
    @objc public let item: Int

    @objc public init(group: UInt16, element: UInt16, item: Int) {
        self.group = group
        self.element = element
        self.item = item
        super.init()
    }

    public override var description: String {
        return String(format: "(%04x,%04x)[%d]", group, element, item)
    }

    public override func isEqual(_ object: Any?) -> Bool {
        guard let other = object as? DICOMTagPathStep else { return false }
        return other.group == group && other.element == element && other.item == item
    }

    public override var hash: Int {
        return Int(group) << 20 ^ Int(element) << 4 ^ item
    }
}

/// Where an element is, when it is not at the top level of the file.
///
/// The metadata editor already builds the address of the row being edited -
/// `(0054,0016)[0].(0018,1074)` for the total dose inside the first item of the
/// radiopharmaceutical sequence - but the writer read it with
/// `-[DCMAttributeTag initWithTagString:]`, which scans the first `(gggg,eeee)`
/// it finds and drops the rest. Every edit inside a sequence was therefore
/// addressed to the sequence element itself, so the edit did not reach the
/// value and reopening the file showed the old one.
@objc(HorosDICOMTagPath)
public final class DICOMTagPath: NSObject {
    /// The element being addressed: the last tag of the path.
    @objc public let group: UInt16
    @objc public let element: UInt16

    /// The sequences to descend, outermost first. Empty for a top-level tag.
    @objc public let steps: [DICOMTagPathStep]

    @objc public var isNested: Bool { return !steps.isEmpty }

    @objc public init(group: UInt16, element: UInt16, steps: [DICOMTagPathStep]) {
        self.group = group
        self.element = element
        self.steps = steps
        super.init()
    }

    /// Reads what `-[XMLController getPath:]` writes.
    ///
    /// Every component is `(gggg,eeee)`, optionally followed by `[n]` when it
    /// is a sequence being descended, and the components are joined with `.`.
    /// The last component addresses the element and must not carry an index;
    /// anything else is not an address this can act on, and returns nil rather
    /// than a tag that means something different.
    @objc(pathWithString:)
    public static func path(with text: String) -> DICOMTagPath? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        var steps: [DICOMTagPathStep] = []
        var leaf: (group: UInt16, element: UInt16)?
        let components = trimmed.split(separator: ".", omittingEmptySubsequences: false)

        for (index, component) in components.enumerated() {
            guard let parsed = parse(String(component)) else { return nil }
            let isLast = index == components.count - 1
            if isLast {
                guard parsed.item == nil else { return nil }
                leaf = (parsed.group, parsed.element)
            } else {
                guard let item = parsed.item else { return nil }
                steps.append(DICOMTagPathStep(group: parsed.group, element: parsed.element, item: item))
            }
        }

        guard let leaf = leaf else { return nil }
        return DICOMTagPath(group: leaf.group, element: leaf.element, steps: steps)
    }

    /// `(gggg,eeee)` or `(gggg,eeee)[n]`.
    static func parse(_ component: String) -> (group: UInt16, element: UInt16, item: Int?)? {
        guard component.hasPrefix("(") else { return nil }
        guard let close = component.firstIndex(of: ")") else { return nil }
        let inside = component[component.index(after: component.startIndex)..<close]
        let numbers = inside.split(separator: ",", omittingEmptySubsequences: false)
        guard numbers.count == 2,
              let group = hex(String(numbers[0])),
              let element = hex(String(numbers[1])) else { return nil }

        let rest = component[component.index(after: close)...]
        if rest.isEmpty { return (group, element, nil) }
        guard rest.hasPrefix("["), rest.hasSuffix("]") else { return nil }
        let digits = rest.dropFirst().dropLast()
        guard !digits.isEmpty, digits.allSatisfy({ $0.isNumber }),
              let item = Int(digits) else { return nil }
        return (group, element, item)
    }

    static func hex(_ text: String) -> UInt16? {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard trimmed.count == 4,
              trimmed.allSatisfy({ $0.isHexDigit }),
              let value = UInt16(trimmed, radix: 16) else { return nil }
        return value
    }

    public override var description: String {
        let prefix = steps.map { $0.description }.joined(separator: ".")
        let tag = String(format: "(%04x,%04x)", group, element)
        return prefix.isEmpty ? tag : prefix + "." + tag
    }

    public override func isEqual(_ object: Any?) -> Bool {
        guard let other = object as? DICOMTagPath else { return false }
        return other.group == group && other.element == element && other.steps == steps
    }

    public override var hash: Int {
        return Int(group) << 20 ^ Int(element) << 4 ^ steps.count
    }
}
