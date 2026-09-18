import Foundation
import Metal

/// Compute pipelines compiled once per device and shader configuration, shared by every MPR and VR engine on
/// that device (#622). Each engine compiled its library and pipelines when it was made, so every new MPR or VR
/// window compiled them again.
///
/// Only compiled artefacts live here. Command queues, buffers, textures, uploaded volumes and whatever a
/// reconstruction or a render changes stay with their engine, and nothing here refers to an engine, a volume
/// or a view. The planar Metal 4 renderer keeps its own cache (#609).
///
/// - The key is the device (its registry ID), the shader source itself (another revision of the source is
///   another entry), the preprocessor macros that change the compiled code (VR's hardware filtering and
///   empty-space skipping, as the device resolves them) and the functions made into pipelines. These engines
///   use Metal 3 pipeline states; a Metal 4 backend would be another configuration, never this one.
/// - One compilation per key at a time: an engine asking while another compiles the same key waits for it and
///   gets its pipelines instead of compiling them again.
/// - A failure publishes nothing. The engine that compiled gets the error and the next request compiles again.
/// - Entries last as long as the process. There is one per configuration the engines use, the MPR kernel and
///   VR's four option combinations, so at most five per device.
public final class MetalComputePipelineCache {
    public struct Configuration: Hashable {
        public let source: String
        public let macros: [String: Bool]
        public let functions: [String]
        /// IEEE arithmetic instead of fast math: no reassociation, no
        /// approximate division. For a consumer whose result has to equal a
        /// CPU loop bit for bit, as the planar thick slab does (#659).
        public let safeMath: Bool

        public init(source: String, macros: [String: Bool] = [:], functions: [String], safeMath: Bool = false) {
            self.source = source; self.macros = macros; self.functions = functions; self.safeMath = safeMath
        }
    }

    private struct Key: Hashable {
        let device: UInt64
        let configuration: Configuration
    }

    private final class Entry {
        /// Held while this key compiles, so a second request waits for the first.
        let compiling = NSLock()
        var pipelines: [String: MTLComputePipelineState]?
    }

    private static let lock = NSLock()
    private static var entries: [Key: Entry] = [:]
    private static var compilationCount = 0, attemptCount = 0, hitCount = 0

    /// The pipelines of `configuration` on `device`, and whether this call compiled them.
    public static func pipelines(device: MTLDevice, configuration: Configuration)
        throws -> (pipelines: [String: MTLComputePipelineState], compiled: Bool) {
        let key = Key(device: device.registryID, configuration: configuration)
        let entry = lock.withLock { () -> Entry in
            if let existing = entries[key] { return existing }
            let created = Entry()
            entries[key] = created
            return created
        }
        entry.compiling.lock()
        defer { entry.compiling.unlock() }
        if let pipelines = entry.pipelines {
            lock.withLock { hitCount += 1 }
            return (pipelines, false)
        }
        lock.withLock { attemptCount += 1 }
        var options: MTLCompileOptions?
        if !configuration.macros.isEmpty || configuration.safeMath {
            options = MTLCompileOptions()
            if !configuration.macros.isEmpty {
                options?.preprocessorMacros = configuration.macros.mapValues { NSNumber(value: $0) }
            }
            if configuration.safeMath { options?.mathMode = .safe }
        }
        let library = try device.makeLibrary(source: configuration.source, options: options)
        var made = [String: MTLComputePipelineState]()
        for name in configuration.functions {
            guard let function = library.makeFunction(name: name) else {
                throw ResliceFailure.device("The compute function \(name) is missing.")
            }
            made[name] = try device.makeComputePipelineState(function: function)
        }
        entry.pipelines = made
        lock.withLock { compilationCount += 1 }
        return (made, true)
    }

    /// Libraries compiled into pipelines so far, in this process.
    public static var compilations: Int { lock.withLock { compilationCount } }
    /// Compilations started, including the ones that failed.
    public static var attempts: Int { lock.withLock { attemptCount } }
    /// Requests served by pipelines another engine compiled.
    public static var hits: Int { lock.withLock { hitCount } }

    /// Forgets every entry; for measuring a cold compilation. Engines keep the pipelines they already hold.
    public static func removeAll() {
        lock.withLock { entries.removeAll() }
    }
}
