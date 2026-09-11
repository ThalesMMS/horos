import AppKit
import ObjectiveC

/// Undo Cocoa bindings that still observe a viewer File's Owner when its window
/// closes. Viewer.xib binds controls to File's Owner; AppKit records those on
/// `NSAutounbinder` without retaining the controller. Closing then extra-
/// releases `ViewerController` (`[self autorelease]`), the controller dies, and
/// Autounbinder's later `dealloc` releases it again.
@objc(HorosViewerBindingTeardown)
public final class ViewerBindingTeardown: NSObject {

    /// Inbound File's Owner key paths in Viewer.xib. The helper unbinds every
    /// binding it finds, not only these; this is the known set.
    @objc public static let fileOwnerBindingKeyPaths = [
        "self.thicknessInMm",
        "KeyImageCounter",
        "injectionDateTime",
        "self.windowsStateName",
    ]

    @objc(unbindFileOwnerBindingsOn:)
    public static func unbindFileOwnerBindings(on owner: AnyObject) {
        var roots: [Any] = [owner]
        if let controller = owner as? NSWindowController, let window = controller.window {
            roots.append(window)
        }
        roots.append(contentsOf: objectIvars(of: owner))

        var seen = Set<ObjectIdentifier>()
        for root in roots {
            visit(root, seen: &seen)
        }
        unbindAll(on: owner)
    }

    private static func objectIvars(of owner: AnyObject) -> [AnyObject] {
        var roots: [AnyObject] = []
        var cls: AnyClass? = object_getClass(owner)
        while let current = cls, current != NSObject.self {
            var count: UInt32 = 0
            guard let ivars = class_copyIvarList(current, &count) else {
                cls = class_getSuperclass(current)
                continue
            }
            for index in 0..<Int(count) {
                let ivar = ivars[index]
                guard let encoding = ivar_getTypeEncoding(ivar), encoding.pointee == 0x40 else { continue }
                guard let value = object_getIvar(owner, ivar) as AnyObject? else { continue }
                if value is NSView || value is NSWindow || value is NSToolbar {
                    roots.append(value)
                }
            }
            free(ivars)
            cls = class_getSuperclass(current)
        }
        return roots
    }

    private static func visit(_ node: Any, seen: inout Set<ObjectIdentifier>) {
        let object = node as AnyObject
        let identity = ObjectIdentifier(object)
        if seen.contains(identity) { return }
        seen.insert(identity)
        unbindAll(on: object)
        if let window = node as? NSWindow {
            if let content = window.contentView { visit(content, seen: &seen) }
            if let toolbar = window.toolbar { visit(toolbar, seen: &seen) }
            return
        }
        if let toolbar = node as? NSToolbar {
            for item in toolbar.items {
                if let view = item.view { visit(view, seen: &seen) }
            }
            return
        }
        if let view = node as? NSView {
            if let control = view as? NSControl, let cell = control.cell {
                unbindAll(on: cell)
            }
            for subview in view.subviews {
                visit(subview, seen: &seen)
            }
        }
    }

    private static func unbindAll(on object: AnyObject) {
        guard let bindable = object as? NSObject else { return }
        for name in bindable.exposedBindings where bindable.infoForBinding(name) != nil {
            bindable.unbind(name)
        }
    }
}
