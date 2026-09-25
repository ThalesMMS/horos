import Foundation

/// What a query term may say in the log.
///
/// The Query/Retrieve log is read to find out what a query asked a node, and
/// that is worth keeping: a node that ignores an attribute answers with
/// everything, and from the answers alone that looks exactly like an attribute
/// that was never sent. But the values are patient names, identifiers,
/// accession numbers and birth dates, and the system log is readable by every
/// process of the user and travels in sysdiagnose reports.
///
/// So a value is written only for the technical keys that cannot identify a
/// patient - modality, level, dates and times of the study, UIDs - and every
/// other value is replaced by its shape: how long it is, and whether it has a
/// wildcard, which is what the diagnosis needed from it.
@objc(HorosQueryLog)
public final class QueryLog: NSObject {
    /// Keys whose values are written as they are. Lowercased: the code spells
    /// the same attribute `ModalitiesinStudy` and `ModalitiesInStudy`.
    static let technicalKeys: Set<String> = [
        "modality", "modalitiesinstudy", "querylevel", "queryretrievelevel",
        "studydate", "studytime", "seriesdate", "seriestime",
        "studyinstanceuid", "seriesinstanceuid", "sopinstanceuid",
        "sopclassuid", "sopclassesinstudy", "seriesnumber", "instancenumber",
    ]

    /// A value as the log may show it.
    @objc(describeValue:forKey:)
    public static func describe(_ value: Any?, forKey key: String?) -> String {
        guard let value = value, !(value is NSNull) else { return "<none>" }
        if let key = key, technicalKeys.contains(key.lowercased()) {
            return "\(value)"
        }
        guard let text = value as? String else {
            return "<\(type(of: value))>"
        }
        let length = text.count
        var shape = "<\(length) character\(length == 1 ? "" : "s")"
        if text.contains("*") || text.contains("?") {
            shape += ", wildcard"
        }
        return shape + ">"
    }

    /// `Key=value`, with the value as the log may show it.
    @objc(termWithKey:value:)
    public static func term(key: String?, value: Any?) -> String {
        return "\(key ?? "?")=\(describe(value, forKey: key))"
    }

    /// The parameters of an XML-RPC `Retrieve`: the node, the mode, and each
    /// `filterKey`/`filterValue` pair as a term, in the order `Retrieve` reads them.
    @objc(describeRetrieveParameters:)
    public static func describeRetrieveParameters(_ parameters: [String: Any]?) -> String {
        guard let parameters = parameters else { return "<none>" }
        var terms: [String] = []
        for key in ["serverName", "retrieveMode"] where parameters[key] != nil {
            terms.append("\(key)=\(parameters[key]!)")
        }
        for index in 1..<10 {
            let suffix = index == 1 ? "" : String(index)
            guard let filterKey = parameters["filterKey" + suffix] as? String else { continue }
            terms.append(term(key: filterKey, value: parameters["filterValue" + suffix]))
        }
        return terms.joined(separator: ", ")
    }
}
