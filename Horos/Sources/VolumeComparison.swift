import AppKit
import Metal
import MetalKit

/// What the 3D host hands the comparison window (#375): where it lives, a
/// signature of the state that decides the picture, and a render of that
/// state at a requested size. The host keeps the volume, the camera, the
/// transfer function and every tool; the window only shows Metal's picture.
@objc(HorosVolumeSource)
public protocol VolumeSource: AnyObject {
    func volumeHostWindow() -> NSWindow?
    func volumeHostView() -> NSView?
    /// Changes whenever the camera, window, CLUT, opacity, mode, clipping,
    /// shading or crop change; the comparison re-renders on a change only.
    func volumeStateSignature() -> String
    /// BGRA bytes of `width × height`, or nil with a reason in `reason`.
    func volumeMetalRender(width: Int, height: Int, reason: AutoreleasingUnsafeMutablePointer<NSString?>?) -> Data?
}

@MainActor @objc(HorosVolumeComparison)
public final class VolumeComparison: NSObject {
    private static var windows: [ObjectIdentifier: VolumeComparisonWindow] = [:]

    @objc(openWithSource:)
    public static func open(source: VolumeSource) {
        let key = ObjectIdentifier(source)
        if let existing = windows[key] { existing.showWindow(nil); return }
        guard let device = MTLCreateSystemDefaultDevice() else {
            let alert = NSAlert(); alert.messageText = PlanarMetalRenderer.failure().localizedDescription
            alert.runModal(); return
        }
        do {
            let controller = try VolumeComparisonWindow(source: source, device: device)
            windows[key] = controller
            controller.onClose = { windows.removeValue(forKey: key) }
            controller.showWindow(nil); controller.refresh()
        } catch {
            let alert = NSAlert(); alert.messageText = error.localizedDescription
            alert.runModal()
        }
    }

    @objc(isOpenForSource:)
    public static func isOpen(source: VolumeSource) -> Bool { windows[ObjectIdentifier(source)] != nil }

    @objc(refreshForSource:)
    public static func refresh(source: VolumeSource) { windows[ObjectIdentifier(source)]?.scheduleRefresh() }
}

@MainActor private final class VolumeComparisonWindow: NSWindowController, NSWindowDelegate, MTKViewDelegate {
    weak var source: VolumeSource?
    var onClose: (() -> Void)?
    private let canvas: MTKView
    private let status = NSTextField(wrappingLabelWithString: "")
    private let device: MTLDevice
    private let displayQueue: MTLCommandQueue
    private var texture: MTLTexture?
    private var scheduled: DispatchWorkItem?
    private var observers: [NSObjectProtocol] = []
    private var poll: Timer?
    private var lastSignature = ""
    private var closed = false

    init(source: VolumeSource, device: MTLDevice) throws {
        guard let displayQueue = device.makeCommandQueue() else { throw PlanarMetalRenderer.failure() }
        self.source = source; self.device = device; self.displayQueue = displayQueue
        canvas = MTKView(frame: .zero, device: device)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 720, height: 640),
                              styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.title = NSLocalizedString("Metal Comparison", comment: "")
        super.init(window: window)
        window.delegate = self; window.isReleasedWhenClosed = false
        if let host = source.volumeHostWindow() { window.setFrameOrigin(NSPoint(x: host.frame.minX + 35, y: host.frame.minY + 35)) }
        canvas.colorPixelFormat = .bgra8Unorm; canvas.framebufferOnly = false
        canvas.isPaused = true; canvas.enableSetNeedsDisplay = true; canvas.delegate = self
        let original = NSButton(title: NSLocalizedString("Original Viewer", comment: ""), target: self, action: #selector(originalViewer))
        let cancel = NSButton(title: NSLocalizedString("Close Comparison", comment: ""), target: self, action: #selector(closeComparison))
        let controls = NSStackView(views: [original, cancel]); controls.orientation = .horizontal
        let stack = NSStackView(views: [status, canvas, controls]); stack.orientation = .vertical
        stack.alignment = .leading; stack.spacing = 8; stack.edgeInsets = NSEdgeInsets(top: 10, left: 10, bottom: 10, right: 10)
        window.contentView = stack
        canvas.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([canvas.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -20),
                                     canvas.heightAnchor.constraint(greaterThanOrEqualToConstant: 120),
                                     status.widthAnchor.constraint(equalTo: canvas.widthAnchor)])
        let nc = NotificationCenter.default
        // The host posts this from every camera path; window/CLUT/opacity
        // changes have no single notification, so a slow poll of the
        // signature covers them without re-rendering an unchanged state.
        if let hostView = source.volumeHostView() {
            observers.append(nc.addObserver(forName: Notification.Name("OsirixVRCameraDidChangeNotification"), object: hostView, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.scheduleRefresh() }
            })
        }
        if let host = source.volumeHostWindow() {
            observers.append(nc.addObserver(forName: NSWindow.willCloseNotification, object: host, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.close() }
            })
        }
        poll = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, !self.closed, let source = self.source else { return }
                if source.volumeStateSignature() != self.lastSignature { self.scheduleRefresh() }
            }
        }
    }
    required init?(coder: NSCoder) { fatalError("Use init(source:device:)") }
    @objc private func originalViewer() { source?.volumeHostWindow()?.makeKeyAndOrderFront(nil) }
    @objc private func closeComparison() { close() }

    func scheduleRefresh() {
        guard !closed, scheduled == nil else { return }
        let work = DispatchWorkItem { [weak self] in self?.scheduled = nil; self?.refresh() }
        scheduled = work; DispatchQueue.main.async(execute: work)
    }

    func refresh() {
        guard !closed, let source else { return }
        let size = canvas.drawableSize
        let width = max(1, Int(size.width)), height = max(1, Int(size.height))
        lastSignature = source.volumeStateSignature()
        var reason: NSString?
        let started = DispatchTime.now().uptimeNanoseconds
        if let bytes = source.volumeMetalRender(width: width, height: height, reason: &reason), bytes.count == width * height * 4 {
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm, width: width, height: height, mipmapped: false)
            descriptor.storageMode = .shared; descriptor.usage = [.shaderRead]
            if let texture = device.makeTexture(descriptor: descriptor) {
                bytes.withUnsafeBytes { raw in
                    texture.replace(region: MTLRegionMake2D(0, 0, width, height), mipmapLevel: 0, withBytes: raw.baseAddress!, bytesPerRow: width * 4)
                }
                self.texture = texture
            }
            let milliseconds = Double(DispatchTime.now().uptimeNanoseconds - started) / 1e6
            status.stringValue = String(format: NSLocalizedString("Metal comparison, %.1f ms. Use the original viewer for tools and overlays.", comment: ""), milliseconds)
        } else {
            texture = nil
            status.stringValue = (reason as String?) ?? NSLocalizedString("Metal comparison is unavailable. Use the original viewer.", comment: "")
        }
        canvas.setNeedsDisplay(canvas.bounds)
    }

    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) { scheduleRefresh() }
    func draw(in view: MTKView) {
        guard let drawable = view.currentDrawable, let command = displayQueue.makeCommandBuffer() else { return }
        if let texture, texture.width == drawable.texture.width, texture.height == drawable.texture.height,
           let blit = command.makeBlitCommandEncoder() {
            blit.copy(from: texture, to: drawable.texture); blit.endEncoding()
        } else {
            let pass = MTLRenderPassDescriptor(); pass.colorAttachments[0].texture = drawable.texture
            pass.colorAttachments[0].loadAction = .clear; pass.colorAttachments[0].storeAction = .store
            pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 1)
            command.makeRenderCommandEncoder(descriptor: pass)?.endEncoding()
        }
        command.present(drawable); command.commit()
    }
    func windowWillClose(_ notification: Notification) {
        closed = true; scheduled?.cancel(); scheduled = nil; texture = nil
        poll?.invalidate(); poll = nil
        observers.forEach(NotificationCenter.default.removeObserver); observers.removeAll()
        canvas.delegate = nil; onClose?(); onClose = nil
    }
}
