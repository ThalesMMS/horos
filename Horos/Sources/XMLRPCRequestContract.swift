import Foundation

/// A fault, in the sense XML-RPC gives the word: the answer to a request the
/// server parsed but will not carry out. The specification puts it in the
/// response body of an ordinary `200`, as a `methodResponse` holding a struct
/// with `faultCode` and `faultString`, which is what every client knows how to
/// read.
///
/// Horos used to answer those requests with an HTTP status line and no body at
/// all - `500 -[NSInvocation setArgument:atIndex:]: index (4) out of bounds`
/// for a call with one parameter too many, and `400` followed by an entire XML
/// document sitting in the reason phrase for a call missing a parameter. Nothing
/// on the other end could read either.
@objc(HorosXMLRPCFault)
public final class XMLRPCFault: NSObject {
    @objc public let code: Int
    @objc public let string: String

    @objc public init(code: Int, string: String) {
        self.code = code
        self.string = string
        super.init()
    }

    /// A complete `methodResponse`, ready to be the body of a response.
    @objc public var document: String {
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?><methodResponse><fault><value>"
            + "<struct>"
            + "<member><name>faultCode</name><value><int>\(code)</int></value></member>"
            + "<member><name>faultString</name><value><string>"
            + XMLRPCFault.escaped(string)
            + "</string></value></member>"
            + "</struct></value></fault></methodResponse>"
    }

    static func escaped(_ text: String) -> String {
        var escaped = ""
        escaped.reserveCapacity(text.count)
        for character in text {
            switch character {
            case "&": escaped += "&amp;"
            case "<": escaped += "&lt;"
            case ">": escaped += "&gt;"
            default: escaped.append(character)
            }
        }
        return escaped
    }
}

/// What an XML-RPC request has to look like before it is dispatched, and what to
/// answer when it does not.
///
/// The codes are the ones from the fault code interoperability convention the
/// XML-RPC community settled on, so a client that recognises any of them
/// recognises these.
@objc(HorosXMLRPCRequestContract)
public final class XMLRPCRequestContract: NSObject {
    static let parseError = -32700
    static let methodNotFound = -32601
    static let invalidParameters = -32602
    static let applicationError = -32500

    /// The request named a method this interface does not publish.
    ///
    /// It is worth being strict about: the dispatcher used to fall back to any
    /// selector the delegate happened to respond to, which made every inherited
    /// one-argument method - `-isEqualTo:`, `-valueForKey:`, `-performSelector:`
    /// - reachable from a socket that asks for no credentials.
    @objc(faultForUnknownMethodName:)
    public static func fault(forUnknownMethodName name: String) -> XMLRPCFault {
        return XMLRPCFault(code: methodNotFound,
                           string: "There is no XML-RPC method named \(quoted(name)).")
    }

    /// The parameters do not fit the method.
    ///
    /// `accepted` is what the selector takes, so this is where a call carrying
    /// more parameters than that is stopped - before `NSInvocation` is asked to
    /// write past the end of the method signature. Every method this interface
    /// publishes takes a single struct, and a parameter of any other type
    /// reaches the method as an object it will send `objectForKey:` to.
    @objc(faultForParameters:methodName:acceptedCount:)
    public static func fault(forParameters parameters: [Any],
                             methodName: String,
                             acceptedCount: Int) -> XMLRPCFault? {
        if parameters.count > acceptedCount {
            return XMLRPCFault(
                code: invalidParameters,
                string: "The XML-RPC method \(quoted(methodName)) takes "
                    + "\(countOfParameters(acceptedCount)); the request supplied "
                    + "\(parameters.count).")
        }
        for (index, parameter) in parameters.enumerated() where !(parameter is NSDictionary) {
            return XMLRPCFault(
                code: invalidParameters,
                string: "Parameter \(index + 1) of the XML-RPC method "
                    + "\(quoted(methodName)) has to be a struct; the request "
                    + "supplied \(described(parameter)).")
        }
        return nil
    }

    /// The request was not XML-RPC at all.
    @objc(faultForUnparsableRequest:)
    public static func fault(forUnparsableRequest reason: String) -> XMLRPCFault {
        return XMLRPCFault(code: parseError, string: reason)
    }

    /// The method was dispatched and threw.
    @objc(faultForFailedMethodName:reason:)
    public static func fault(forFailedMethodName name: String?, reason: String?) -> XMLRPCFault {
        let what = reason ?? "the method raised an exception"
        guard let name = name, !name.isEmpty else {
            return XMLRPCFault(code: applicationError, string: what)
        }
        return XMLRPCFault(code: applicationError,
                           string: "The XML-RPC method \(quoted(name)) failed: \(what)")
    }

    /// The body to answer with when a method reports an `NSError`.
    ///
    /// The methods of this interface report an application-level failure by
    /// putting a complete `methodResponse` in the error's description - that is
    /// the `{error: "400"}` struct their callers already read, and the same
    /// value the in-process AppleScript and `horos://` callers get. It is
    /// returned unchanged, so those requests are answered with the document they
    /// were always meant to be answered with rather than with an empty body.
    /// Anything else becomes a fault.
    @objc(responseDocumentForError:)
    public static func responseDocument(for error: NSError) -> String {
        let description = error.localizedDescription
        if description.contains("<methodResponse") {
            return description
        }
        return XMLRPCFault(code: applicationError, string: description).document
    }

    static func quoted(_ name: String) -> String {
        return "\"" + name + "\""
    }

    static func countOfParameters(_ count: Int) -> String {
        return count == 1 ? "1 parameter" : "\(count) parameters"
    }

    static func described(_ parameter: Any) -> String {
        switch parameter {
        case is String: return "a string"
        case is NSNumber: return "a number"
        case is [Any]: return "an array"
        case is Date: return "a date"
        case is Data: return "base64 data"
        default: return "a \(type(of: parameter))"
        }
    }
}
