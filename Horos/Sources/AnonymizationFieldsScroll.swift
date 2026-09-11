import AppKit

/// Keeps the field grid scrollable without moving the panel actions off screen.
@objc(HorosAnonymizationFieldsScroll)
public final class AnonymizationFieldsScroll: NSObject {
    @objc(installInBox:document:)
    public static func install(in box: NSBox, document: NSView) {
        guard let parent = document.superview else { return }
        let scroll = NSScrollView(frame: document.frame)
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false
        // The nib pins the grid through the box. Transfer those constraints to
        // the viewport; the document must retain its full content height.
        var replacements: [NSLayoutConstraint] = []
        var ancestor: NSView? = document
        while let view = ancestor {
            let constraints = view.constraints.filter {
                ($0.firstItem as? NSView) === document || ($0.secondItem as? NSView) === document
            }
            for constraint in constraints {
                let first = (constraint.firstItem as? NSView) === document ? scroll : constraint.firstItem!
                let second: Any? = (constraint.secondItem as? NSView) === document ? scroll : constraint.secondItem
                let replacement = NSLayoutConstraint(item: first, attribute: constraint.firstAttribute,
                    relatedBy: constraint.relation, toItem: second, attribute: constraint.secondAttribute,
                    multiplier: constraint.multiplier, constant: constraint.constant)
                replacement.priority = constraint.priority
                replacements.append(replacement)
            }
            NSLayoutConstraint.deactivate(constraints)
            if view === box { break }
            ancestor = view.superview
        }
        document.removeFromSuperview()
        parent.addSubview(scroll)
        document.translatesAutoresizingMaskIntoConstraints = true
        document.autoresizingMask = [.width]
        scroll.documentView = document
        NSLayoutConstraint.activate(replacements)
    }

    @objc(updateDocument:height:)
    public static func update(document: NSView, height: CGFloat) {
        guard let scroll = document.enclosingScrollView else { return }
        document.setFrameSize(NSSize(width: scroll.contentSize.width, height: max(height, scroll.contentSize.height)))
        scroll.reflectScrolledClipView(scroll.contentView)
    }
}
