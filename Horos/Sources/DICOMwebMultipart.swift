import Foundation

/// Streaming extraction of WADO-RS application/dicom parts into an owned staging directory.
/// Nothing reaches the database until the complete multipart envelope has been validated.
enum DICOMwebMultipart {
    enum Failure: Error { case invalidContentType, malformedEnvelope, cancelled, emptyResponse }

    static func boundary(_ contentType: String) throws -> String {
        guard contentType.lowercased().hasPrefix("multipart/related;") else { throw Failure.invalidContentType }
        let pattern = #"(?:^|;)\s*boundary\s*=\s*(?:"([^"]+)"|([^;\s]+))"#
        let regex = try NSRegularExpression(pattern: pattern, options: .caseInsensitive)
        let range = NSRange(contentType.startIndex..., in: contentType)
        guard let match = regex.firstMatch(in: contentType, range: range),
              let valueRange = Range(match.range(at: match.range(at: 1).location == NSNotFound ? 2 : 1), in: contentType)
        else { throw Failure.invalidContentType }
        let value = String(contentType[valueRange])
        guard !value.isEmpty, value.utf8.count <= 70,
              value.utf8.allSatisfy({ $0 >= 32 && $0 < 127 }), !value.hasSuffix(" ")
        else { throw Failure.invalidContentType }
        return value
    }

    static func extract(from input: URL, contentType: String, into directory: URL,
                        chunkSize: Int = 64 * 1024, cancelled: () -> Bool = { false }) throws -> [URL] {
        let token = try boundary(contentType)
        let marker = Data(("\r\n--" + token).utf8)
        let initial = Data(("--" + token + "\r\n").utf8)
        let separator = Data([13,10,13,10])
        let manager = FileManager.default
        // Never remove a caller-owned existing directory on a parsing failure.
        guard !manager.fileExists(atPath: directory.path), chunkSize > 0 else { throw Failure.malformedEnvelope }
        try manager.createDirectory(at: directory, withIntermediateDirectories: false)
        var success = false
        var output: FileHandle?
        defer {
            try? output?.close()
            if !success { try? manager.removeItem(at: directory) }
        }
        let source = try FileHandle(forReadingFrom: input)
        defer { try? source.close() }
        enum State { case start, headers, body, finished }
        var state = State.start
        var buffer = Data()
        var files: [URL] = []
        var atEnd = false
        while state != .finished {
            if cancelled() { throw Failure.cancelled }
            let chunk = try source.read(upToCount: chunkSize) ?? Data()
            atEnd = chunk.isEmpty
            buffer.append(chunk)
            var progress = true
            while progress && state != .finished {
                if cancelled() { throw Failure.cancelled }
                progress = false
                switch state {
                case .start:
                    if let found = buffer.range(of: initial) {
                        guard found.lowerBound <= 65536 else { throw Failure.malformedEnvelope }
                        buffer.removeSubrange(..<found.upperBound)
                        state = .headers; progress = true
                    } else if buffer.count > 65536 + initial.count { throw Failure.malformedEnvelope }
                case .headers:
                    if let found = buffer.range(of: separator) {
                        guard found.lowerBound - buffer.startIndex <= 65536,
                              let headers = String(data: buffer[..<found.lowerBound], encoding: .ascii)
                        else { throw Failure.malformedEnvelope }
                        let types = headers.components(separatedBy: "\r\n").compactMap { line -> String? in
                            guard let colon = line.firstIndex(of: ":"),
                                  line[..<colon].lowercased() == "content-type" else { return nil }
                            return line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
                        }
                        guard types.count == 1,
                              types[0].components(separatedBy: ";")[0].trimmingCharacters(in: .whitespaces).lowercased() == "application/dicom"
                        else { throw Failure.invalidContentType }
                        let file = directory.appendingPathComponent("\(files.count).dcm")
                        guard manager.createFile(atPath: file.path, contents: nil) else { throw Failure.malformedEnvelope }
                        output = try FileHandle(forWritingTo: file); files.append(file)
                        buffer.removeSubrange(..<found.upperBound)
                        state = .body; progress = true
                    } else if buffer.count > 65536 { throw Failure.malformedEnvelope }
                case .body:
                    if let found = buffer.range(of: marker) {
                        guard buffer.endIndex - found.upperBound >= 2 else { break }
                        let suffix = buffer[found.upperBound..<(found.upperBound + 2)]
                        let closing = suffix == Data([45,45])
                        if closing && buffer.endIndex - found.upperBound < 4 && !atEnd { break }
                        let validClose = closing && ((atEnd && buffer.endIndex - found.upperBound == 2)
                            || (buffer.endIndex - found.upperBound >= 4 && buffer[(found.upperBound + 2)..<(found.upperBound + 4)] == Data([13,10])))
                        if validClose || suffix == Data([13,10]) {
                            try output?.write(contentsOf: buffer[..<found.lowerBound])
                            try output?.close(); output = nil
                            buffer.removeSubrange(..<(found.upperBound + 2))
                            state = suffix == Data([45,45]) ? .finished : .headers
                            progress = true
                        } else {
                            // A delimiter-looking byte sequence in PixelData is still payload.
                            let end = found.lowerBound + 1
                            try output?.write(contentsOf: buffer[..<end])
                            buffer.removeSubrange(..<end); progress = true
                        }
                    } else {
                        let keep = marker.count + 2
                        if buffer.count > keep {
                            let end = buffer.endIndex - keep
                            try output?.write(contentsOf: buffer[..<end])
                            buffer.removeSubrange(..<end)
                        }
                    }
                case .finished: break
                }
            }
            if atEnd && state != .finished { throw Failure.malformedEnvelope }
        }
        guard !files.isEmpty else { throw Failure.emptyResponse }
        if cancelled() { throw Failure.cancelled }
        success = true
        return files
    }
}
