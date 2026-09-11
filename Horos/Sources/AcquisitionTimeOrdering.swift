import Foundation

/// A deterministic acquisition ordering; no conversion of DICOM text to Float.
@objc(HorosAcquisitionTimeOrdering)
public final class AcquisitionTimeOrdering: NSObject {
    private struct Stamp: Comparable {
        let seconds: Int64
        let microseconds: Int
        static func < (lhs: Stamp, rhs: Stamp) -> Bool {
            lhs.seconds == rhs.seconds ? lhs.microseconds < rhs.microseconds : lhs.seconds < rhs.seconds
        }
    }

    private static func unpad(_ text: String) -> String {
        String(text.reversed().drop(while: { $0 == " " }).reversed())
    }

    private static func offset(_ text: String) -> Int? {
        let b = Array(text.utf8)
        guard b.count == 5, b[0] == 43 || b[0] == 45,
              b.dropFirst().allSatisfy({ (48...57).contains($0) }) else { return nil }
        let hours = Int(b[1] - 48) * 10 + Int(b[2] - 48)
        let minutes = Int(b[3] - 48) * 10 + Int(b[4] - 48)
        let value = (hours * 60 + minutes) * (b[0] == 45 ? -1 : 1)
        guard minutes < 60, (-720...840).contains(value), text != "-0000" else { return nil }
        return value * 60
    }

    private static func parse(_ raw: String, zone: String) -> Stamp? {
        var text = unpad(raw)
        var zone = unpad(zone)
        if let sign = text.firstIndex(where: { $0 == "+" || $0 == "-" }) {
            zone = String(text[sign...])
            text = String(text[..<sign])
        }
        let utcOffset: Int
        if zone.isEmpty { utcOffset = 0 } // Floating local times use a common, deterministic calendar basis.
        else if let value = offset(zone) { utcOffset = value }
        else { return nil }
        let pieces = text.split(separator: ".", omittingEmptySubsequences: false)
        guard pieces.count <= 2 else { return nil }
        let digits = Array(pieces[0].utf8)
        guard [4, 6, 8, 10, 12, 14].contains(digits.count),
              digits.allSatisfy({ (48...57).contains($0) }) else { return nil }
        var micros = 0
        if pieces.count == 2 {
            let fraction = Array(pieces[1].utf8)
            guard digits.count == 14, (1...6).contains(fraction.count),
                  fraction.allSatisfy({ (48...57).contains($0) }) else { return nil }
            micros = fraction.reduce(0) { $0 * 10 + Int($1 - 48) }
            for _ in fraction.count..<6 { micros *= 10 }
        }
        func number(_ start: Int, _ count: Int, default fallback: Int) -> Int {
            guard digits.count >= start + count else { return fallback }
            return digits[start..<start+count].reduce(0) { $0 * 10 + Int($1 - 48) }
        }
        let year = number(0, 4, default: 0), month = number(4, 2, default: 1)
        let day = number(6, 2, default: 1), hour = number(8, 2, default: 0)
        let minute = number(10, 2, default: 0), second = number(12, 2, default: 0)
        guard year > 0, (1...12).contains(month), (1...31).contains(day),
              hour < 24, minute < 60, second <= 60 else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let components = DateComponents(year: year, month: month, day: day, hour: hour,
                                        minute: minute, second: min(second, 59))
        guard let date = calendar.date(from: components) else { return nil }
        let roundTrip = calendar.dateComponents([.year, .month, .day, .hour, .minute, .second], from: date)
        guard roundTrip == components else { return nil }
        // Preserve leap-second ordering after :59 and before the following minute.
        return Stamp(seconds: Int64(date.timeIntervalSince1970) - Int64(utcOffset),
                     microseconds: micros + (second == 60 ? 1_000_000 : 0))
    }

    private static func stamp(_ record: [String: String]) -> Stamp? {
        let zone = record["TimezoneOffsetFromUTC"] ?? ""
        if let value = parse(record["AcquisitionDateTime"] ?? "", zone: zone) { return value }
        let date = unpad(record["AcquisitionDate"] ?? "")
        let time = unpad(record["AcquisitionTime"] ?? "")
        guard date.utf8.count == 8, !time.isEmpty else { return nil }
        return parse(date + time, zone: zone)
    }

    /// Unknown/invalid timestamps sort last in both directions. Equal keys retain input order.
    @objc(orderedIndicesForRecords:ascending:)
    public static func orderedIndices(records: [[String: String]], ascending: Bool) -> [NSNumber] {
        let stamps = records.map(stamp)
        return records.indices.sorted { left, right in
            switch (stamps[left], stamps[right]) {
            case let (a?, b?) where a != b: return ascending ? a < b : b < a
            case (nil, .some): return false
            case (.some, nil): return true
            default: return left < right
            }
        }.map { NSNumber(value: $0) }
    }
}
