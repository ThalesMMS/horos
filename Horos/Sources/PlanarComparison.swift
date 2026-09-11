import AppKit
import MetalKit

@objc(HorosPlanarSource)
public protocol PlanarSource: AnyObject {
    func planarHostWindow() -> NSWindow?
    func planarHostView() -> NSView?
    func horosVolumeSession() -> VolumeSession?
    func planarSnapshot() -> NSDictionary
}

/// The worker retains decoded values and tokens only, never the viewer/database.
/// At most one active and one pending frame: rapid scroll replaces queued work.
final class PlanarRenderWorker: @unchecked Sendable {
    private struct Job {
        let frame: PlanarFrame, width: Int, height: Int, token: VolumeLoadToken
        let completion: (Result<MTLTexture, Error>) -> Void
    }
    private let lock = NSLock()
    private let queue = DispatchQueue(label: "org.horos.planar.prepare", qos: .userInitiated)
    private let device: MTLDevice
    private var pending: Job?
    private var running = false
    private var renderer: PlanarMetalRenderer?
    init(device: MTLDevice) { self.device = device }

    func submit(frame: PlanarFrame, width: Int, height: Int, token: VolumeLoadToken,
                completion: @escaping (Result<MTLTexture, Error>) -> Void) {
        lock.lock()
        pending?.token.cancel()
        pending = Job(frame: frame, width: width, height: height, token: token, completion: completion)
        let start = !running; running = true
        lock.unlock()
        if start { queue.async { self.drain() } }
    }
    func cancel() {
        lock.lock(); pending?.token.cancel(); pending = nil; lock.unlock()
    }
    private func drain() {
        while true {
            lock.lock()
            guard let job = pending else { running = false; lock.unlock(); return }
            pending = nil; lock.unlock()
            if job.token.isCancelled { continue }
            let result: Result<MTLTexture, Error> = Result {
                if renderer == nil { renderer = try PlanarMetalRenderer(device: device) }
                try renderer!.update(job.frame)
                return try renderer!.renderTexture(width: job.width, height: job.height)
            }
            renderer?.clear()
            DispatchQueue.main.async { if !job.token.isCancelled { job.completion(result) } }
        }
    }
}

@MainActor @objc(HorosPlanarComparison)
public final class PlanarComparison: NSObject {
    private static var windows: [ObjectIdentifier: PlanarComparisonWindow] = [:]

    @objc(openWithSource:)
    public static func open(source: PlanarSource) {
        let key = ObjectIdentifier(source)
        if let existing = windows[key] { existing.showWindow(nil); return }
        guard let device = MTLCreateSystemDefaultDevice() else {
            let alert = NSAlert(); alert.messageText = PlanarMetalRenderer.failure().localizedDescription
            alert.runModal(); return
        }
        do {
            let controller = try PlanarComparisonWindow(source: source, device: device)
            windows[key] = controller
            controller.onClose = { windows.removeValue(forKey: key) }
            controller.showWindow(nil); controller.refresh()
        } catch {
            let alert = NSAlert(); alert.messageText = error.localizedDescription
            alert.runModal()
        }
    }
    @objc(refreshForHostView:)
    public static func refresh(hostView: NSView) {
        for controller in windows.values where controller.source?.planarHostView() === hostView {
            controller.scheduleRefresh()
        }
    }
}

@MainActor private final class PlanarComparisonWindow: NSWindowController, NSWindowDelegate, MTKViewDelegate {
    weak var source: PlanarSource?
    var onClose: (() -> Void)?
    private let canvas: MTKView
    private let status = NSTextField(wrappingLabelWithString: "")
    private let worker: PlanarRenderWorker
    private let displayQueue: MTLCommandQueue
    private var token: VolumeLoadToken?
    private var texture: MTLTexture?
    private var scheduled: DispatchWorkItem?
    private var observers: [NSObjectProtocol] = []
    private var closed = false

    init(source: PlanarSource, device: MTLDevice) throws {
        guard let displayQueue = device.makeCommandQueue() else { throw PlanarMetalRenderer.failure() }
        self.source = source; worker = PlanarRenderWorker(device: device)
        canvas = MTKView(frame: .zero, device: device)
        self.displayQueue = displayQueue
        let window = NSWindow(contentRect: NSRect(x:0,y:0,width:720,height:640),
            styleMask:[.titled,.closable,.resizable,.miniaturizable], backing:.buffered, defer:false)
        window.title = NSLocalizedString("Metal Comparison", comment: "")
        super.init(window: window)
        window.delegate = self; window.isReleasedWhenClosed = false
        if let host = source.planarHostWindow() { window.setFrameOrigin(NSPoint(x:host.frame.minX+35,y:host.frame.minY+35)) }
        canvas.colorPixelFormat = .bgra8Unorm; canvas.framebufferOnly = false
        canvas.isPaused = true; canvas.enableSetNeedsDisplay = true; canvas.delegate = self
        let original = NSButton(title:NSLocalizedString("Original Viewer", comment:""), target:self, action:#selector(originalViewer))
        let cancel = NSButton(title:NSLocalizedString("Close Comparison", comment:""), target:self, action:#selector(closeComparison))
        let controls = NSStackView(views:[original,cancel]); controls.orientation = .horizontal
        let stack = NSStackView(views:[status,canvas,controls]); stack.orientation = .vertical
        stack.alignment = .leading; stack.spacing = 8; stack.edgeInsets = NSEdgeInsets(top:10,left:10,bottom:10,right:10)
        window.contentView = stack
        canvas.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([canvas.widthAnchor.constraint(equalTo:stack.widthAnchor,constant:-20),
            canvas.heightAnchor.constraint(greaterThanOrEqualToConstant:120),
            status.widthAnchor.constraint(equalTo:canvas.widthAnchor)])
        let nc = NotificationCenter.default
        for name in ["CloseViewerNotification", "ViewerWillChangeNotification"] {
            observers.append(nc.addObserver(forName:Notification.Name(name),object:source,queue:.main) { [weak self] _ in
                MainActor.assumeIsolated { self?.invalidate() }
            })
        }
        if let host = source.planarHostWindow() {
            observers.append(nc.addObserver(forName:NSWindow.willCloseNotification,object:host,queue:.main) { [weak self] _ in self?.close() })
        }
    }
    required init?(coder:NSCoder) { fatalError("Use init(source:device:)") }
    @objc private func originalViewer() { source?.planarHostWindow()?.makeKeyAndOrderFront(nil) }
    @objc private func closeComparison() { close() }
    func scheduleRefresh() {
        guard !closed, scheduled == nil else { return }
        let work = DispatchWorkItem { [weak self] in self?.scheduled = nil; self?.refresh() }
        scheduled = work; DispatchQueue.main.async(execute:work)
    }
    private func invalidate() {
        token?.cancel(); token = nil; worker.cancel(); texture = nil
        status.stringValue = NSLocalizedString("Comparison paused. Use the original viewer for tools and overlays.",comment:"")
        canvas.setNeedsDisplay(canvas.bounds)
    }
    func refresh() {
        guard !closed, let source else { return }
        token?.cancel(); texture = nil
        do {
            guard let session = source.horosVolumeSession(), session.isOpen,
                  let next = VolumeSessionRegistry.shared.makeLoadToken(for:session) else { throw PlanarMetalRenderer.failure() }
            token = next
            let snapshot = source.planarSnapshot()
            if let error = snapshot["error"] as? String {
                throw NSError(domain:"HorosPlanar",code:3,userInfo:[NSLocalizedDescriptionKey:error])
            }
            let frame = try PlanarFrame(snapshot)
            status.stringValue = NSLocalizedString("Preparing comparison…",comment:"")
            let size = canvas.drawableSize
            worker.submit(frame:frame,width:max(1,Int(size.width)),height:max(1,Int(size.height)),token:next) { [weak self] result in
                guard let self, !self.closed, self.token === next, session.isOpen,
                      session.identity.isEqual(next.identity), next.deliver() else { return }
                switch result {
                case .success(let texture):
                    self.texture = texture
                    self.status.stringValue = NSLocalizedString("Metal comparison. Use the original viewer for tools and overlays.",comment:"")
                case .failure(let error): self.texture = nil; self.status.stringValue = error.localizedDescription
                }
                self.canvas.setNeedsDisplay(self.canvas.bounds)
            }
        } catch {
            token?.cancel(); status.stringValue = error.localizedDescription
            canvas.setNeedsDisplay(canvas.bounds)
        }
    }
    func mtkView(_ view:MTKView, drawableSizeWillChange size:CGSize) { scheduleRefresh() }
    func draw(in view:MTKView) {
        guard let drawable = view.currentDrawable, let command = displayQueue.makeCommandBuffer() else { return }
        if let texture, texture.width == drawable.texture.width, texture.height == drawable.texture.height,
           let blit = command.makeBlitCommandEncoder() {
            blit.copy(from:texture,to:drawable.texture); blit.endEncoding()
        } else {
            let pass = MTLRenderPassDescriptor(); pass.colorAttachments[0].texture = drawable.texture
            pass.colorAttachments[0].loadAction = .clear; pass.colorAttachments[0].storeAction = .store
            pass.colorAttachments[0].clearColor = MTLClearColorMake(0,0,0,1)
            command.makeRenderCommandEncoder(descriptor:pass)?.endEncoding()
        }
        command.present(drawable); command.commit()
    }
    func windowWillClose(_ notification:Notification) {
        closed = true; scheduled?.cancel(); scheduled = nil; invalidate()
        observers.forEach(NotificationCenter.default.removeObserver); observers.removeAll()
        canvas.delegate = nil; onClose?(); onClose = nil
    }
}
