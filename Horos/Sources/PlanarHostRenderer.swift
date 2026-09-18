import AppKit
import CoreVideo
import Metal
import OpenGL
import OpenGL.GL

/// Which submission path presents the planar pixels (#609).
///
/// The pilot is chosen explicitly, never by availability alone, and a system or
/// device without Metal 4 falls back to the backend in use with a reason the
/// host can show. Nothing about the image, the geometry or the overlays differs
/// between the two: they share the shader, the textures and `PlanarFrame`.
enum PlanarBackend {
    case metal3(PlanarMetalRenderer)
    case metal4(PlanarMetal4Renderer)

    /// The user default that asks for the pilot. Absent means the backend in use.
    static let pilotDefaultsKey = "HorosPlanarMetal4Pilot"

    static func make(device: MTLDevice, wantsPilot: Bool) throws -> (PlanarBackend, String?) {
        guard wantsPilot else { return (.metal3(try PlanarMetalRenderer(device: device)), nil) }
        guard PlanarMetal4Renderer.isSupported(device) else {
            return (.metal3(try PlanarMetalRenderer(device: device)),
                    NSLocalizedString("This graphics device has no Metal 4; the viewer is using the existing renderer.",
                                      comment: ""))
        }
        do {
            return (.metal4(try PlanarMetal4Renderer(device: device)), nil)
        } catch {
            return (.metal3(try PlanarMetalRenderer(device: device)), error.localizedDescription)
        }
    }

    var device: MTLDevice {
        switch self {
        case .metal3(let renderer): return renderer.device
        case .metal4(let renderer): return renderer.device
        }
    }

    var name: String {
        switch self {
        case .metal3: return "Metal 3"
        case .metal4: return "Metal 4 pilot"
        }
    }

    func update(_ frame: PlanarFrame) throws {
        switch self {
        case .metal3(let renderer): try renderer.update(frame)
        case .metal4(let renderer): try renderer.update(frame)
        }
    }

    func clear() {
        switch self {
        case .metal3(let renderer): renderer.clear()
        case .metal4(let renderer): renderer.clear()
        }
    }

    /// Draw and wait. The OpenGL composition reads the same IOSurface, so the
    /// pixels have to be there before the quad is drawn; neither backend may
    /// hand over a target the GPU is still writing.
    func render(into target: MTLTexture) throws -> Double {
        switch self {
        case .metal3(let renderer):
            let traceStart = MetalPerformanceTrace.now()
            guard let command = renderer.queue.makeCommandBuffer() else { throw PlanarMetalRenderer.failure() }
            try renderer.encode(into: target, command: command)
            let committedAt = MetalPerformanceTrace.now()
            command.commit()
            command.waitUntilCompleted()
            let completedAt = MetalPerformanceTrace.now()
            MetalPerformanceTrace.record("planar.metal3.render", startedAt: traceStart, committedAt: committedAt,
                                         completedAt: completedAt, command: command, finishedAt: completedAt,
                                         extra: ["width": target.width, "height": target.height])
            guard command.status == .completed else { throw command.error ?? PlanarMetalRenderer.failure() }
            // A command buffer without timestamps is not a zero-millisecond draw:
            // -1 is what the host already reads as "not measured" (#619).
            let gpu = command.gpuEndTime - command.gpuStartTime
            return command.gpuStartTime > 0 && gpu >= 0 ? gpu * 1000 : -1
        case .metal4(let renderer):
            try renderer.render(into: target)
            return renderer.lastGPUMilliseconds
        }
    }
}

/// Pixel presentation inside the existing DCMView. The host still owns input,
/// geometry, overlays, ROIs and plugin notifications. No viewer/database is
/// retained here, and only immutable decoded snapshots reach Metal.
@MainActor @objc(HorosPlanarHostRenderer)
public final class PlanarHostRenderer: NSObject {
    private var renderer: PlanarBackend?
    private var buffer: CVPixelBuffer?
    private var target: MTLTexture?
    private var context: NSOpenGLContext?
    private var texture: GLuint = 0
    private var frame: PlanarFrame?
    private var identity: VolumeIdentity?
    private var sessionID: Int?
    @objc public private(set) var failureReason: String?

    /// For integration probes; GPU command time excludes the GL composition.
    @objc public private(set) var gpuMilliseconds: Double = 0
    @objc public private(set) var renderedFrameCount: Int = 0
    @objc public private(set) var encodedGPUCommand = false

    private func releaseSurface() {
        let previous = NSOpenGLContext.current
        if let context, texture != 0 {
            context.makeCurrentContext()
            // Metal must not overwrite/release storage still read by OpenGL.
            glFinish()
            glDeleteTextures(1, &texture)
        }
        if let previous { previous.makeCurrentContext() }
        else { NSOpenGLContext.clearCurrentContext() }
        texture = 0; target = nil; buffer = nil; context = nil; frame = nil
    }

    /// Which submission path drew the last frame, for the record and the trace.
    @objc public var backendName: String { renderer?.name ?? "" }

    @objc public func invalidate() {
        releaseSurface(); renderer?.clear(); identity = nil; sessionID = nil
    }

    private func prepareSurface(context: NSOpenGLContext, width: Int, height: Int) throws {
        if self.context === context, target?.width == width, target?.height == height { return }
        releaseSurface()
        var pixelBuffer: CVPixelBuffer?
        let attributes = [kCVPixelBufferMetalCompatibilityKey as String: true,
                          kCVPixelBufferOpenGLCompatibilityKey as String: true,
                          kCVPixelBufferIOSurfacePropertiesKey as String: [:]] as CFDictionary
        guard CVPixelBufferCreate(nil, width, height, kCVPixelFormatType_32BGRA,
                                  attributes, &pixelBuffer) == kCVReturnSuccess,
              let pixelBuffer, let surface = CVPixelBufferGetIOSurface(pixelBuffer)?.takeUnretainedValue(),
              let renderer else { throw PlanarMetalRenderer.failure() }
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm,
            width: width, height: height, mipmapped: false)
        descriptor.storageMode = .shared; descriptor.usage = .renderTarget
        guard let target = renderer.device.makeTexture(descriptor: descriptor, iosurface: surface, plane: 0),
              let cgl = context.cglContextObj else { throw PlanarMetalRenderer.failure() }
        self.context = context; self.buffer = pixelBuffer; self.target = target
        context.makeCurrentContext()
        glGenTextures(1, &texture)
        glBindTexture(GLenum(GL_TEXTURE_RECTANGLE_EXT), texture)
        guard CGLTexImageIOSurface2D(cgl, GLenum(GL_TEXTURE_RECTANGLE_EXT), GLenum(GL_RGBA),
            GLsizei(width), GLsizei(height), GLenum(GL_BGRA), GLenum(GL_UNSIGNED_INT_8_8_8_8_REV),
            surface, 0) == kCGLNoError else { throw PlanarMetalRenderer.failure() }
        // Metal already sampled intensities at the final backing-pixel centres.
        // A second linear interpolation here would mix discrete CLUT colours.
        glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT), GLenum(GL_TEXTURE_MIN_FILTER), GL_NEAREST)
        glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT), GLenum(GL_TEXTURE_MAG_FILTER), GL_NEAREST)
        glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT), GLenum(GL_TEXTURE_WRAP_S), GL_CLAMP_TO_EDGE)
        glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT), GLenum(GL_TEXTURE_WRAP_T), GL_CLAMP_TO_EDGE)
    }

    @objc(drawSnapshot:session:context:width:height:)
    public func draw(snapshot: NSDictionary, session: VolumeSession, context: NSOpenGLContext,
                     width: Int, height: Int) -> Bool {
        precondition(Thread.isMainThread)
        encodedGPUCommand = false
        failureReason = nil
        guard session.isOpen, !session.isStale, width > 0, height > 0,
              width <= 16384, height <= 16384, context.cglContextObj != nil else { return false }
        // All GL state modified by the interop quad is restored before host
        // annotations, plugin drawing and ROI tools run in this same context.
        context.makeCurrentContext()
        var program: GLint = 0
        glGetIntegerv(GLenum(GL_CURRENT_PROGRAM), &program)
        glPushAttrib(GLbitfield(GL_ALL_ATTRIB_BITS))
        glActiveTexture(GLenum(GL_TEXTURE0))
        for matrix in [GL_PROJECTION, GL_MODELVIEW, GL_TEXTURE] {
            glMatrixMode(GLenum(matrix)); glPushMatrix(); glLoadIdentity()
        }
        defer {
            for matrix in [GL_TEXTURE, GL_MODELVIEW, GL_PROJECTION] {
                glMatrixMode(GLenum(matrix)); glPopMatrix()
            }
            glUseProgram(GLuint(program)); glPopAttrib()
        }
        do {
            if identity?.isEqual(session.identity) != true || sessionID != session.sessionID { invalidate() }
            if renderer == nil {
                guard let device = MTLCreateSystemDefaultDevice() else { throw PlanarMetalRenderer.failure() }
                let wantsPilot = UserDefaults.standard.bool(forKey: PlanarBackend.pilotDefaultsKey)
                let (backend, reason) = try PlanarBackend.make(device: device, wantsPilot: wantsPilot)
                renderer = backend
                // A fallback says so; it is never silent.
                if let reason { NSLog("Horos planar: %@", reason) }
            }
            let next = try PlanarFrame(snapshot)
            try prepareSurface(context: context, width: width, height: height)
            guard let renderer, let target else { throw PlanarMetalRenderer.failure() }
            if frame != next {
                guard let token = VolumeSessionRegistry.shared.makeLoadToken(for: session) else {
                    throw PlanarMetalRenderer.failure()
                }
                defer { token.cancel() }
                // The two APIs have separate command queues. Complete the old
                // GL read, then the new Metal write, before drawing the quad.
                // No CPU pixel readback and no previous-frame/current-ROI mix.
                glFinish()
                try renderer.update(next)
                let gpu = try renderer.render(into: target)
                guard session.isOpen, !session.isStale,
                      session.identity.isEqual(token.identity), token.deliver() else {
                    throw PlanarMetalRenderer.failure()
                }
                gpuMilliseconds = gpu
                encodedGPUCommand = true
                renderedFrameCount += 1
                frame = next; identity = token.identity; sessionID = session.sessionID
            }
            glUseProgram(0)
            glDisable(GLenum(GL_TEXTURE_2D))
            glEnable(GLenum(GL_TEXTURE_RECTANGLE_EXT))
            glBindTexture(GLenum(GL_TEXTURE_RECTANGLE_EXT), texture)
            glTexEnvi(GLenum(GL_TEXTURE_ENV), GLenum(GL_TEXTURE_ENV_MODE), GL_REPLACE)
            for capability in [GL_BLEND, GL_DEPTH_TEST, GL_STENCIL_TEST, GL_CULL_FACE, GL_SCISSOR_TEST] {
                glDisable(GLenum(capability))
            }
            glColorMask(GLboolean(GL_TRUE), GLboolean(GL_TRUE), GLboolean(GL_TRUE), GLboolean(GL_TRUE))
            glViewport(0, 0, GLsizei(width), GLsizei(height))
            glBegin(GLenum(GL_QUADS))
            glTexCoord2f(0, 0); glVertex2f(-1, 1)
            glTexCoord2f(0, GLfloat(height)); glVertex2f(-1, -1)
            glTexCoord2f(GLfloat(width), GLfloat(height)); glVertex2f(1, -1)
            glTexCoord2f(GLfloat(width), 0); glVertex2f(1, 1)
            glEnd()
            return true
        } catch {
            failureReason = error.localizedDescription
            invalidate()
            return false
        }
    }

    deinit {
        // NSOpenGLContext is retained through the last GL texture deletion.
        let previous = NSOpenGLContext.current
        if let context, texture != 0 {
            context.makeCurrentContext(); glFinish(); glDeleteTextures(1, &texture)
        }
        if let previous { previous.makeCurrentContext() }
        else { NSOpenGLContext.clearCurrentContext() }
    }
}
