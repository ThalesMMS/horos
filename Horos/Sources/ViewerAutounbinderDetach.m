#import "ViewerAutounbinderDetach.h"

#import <AppKit/NSWindowController.h>
#import <objc/runtime.h>

// Viewer.xib File's Owner bindings live on NSAutounbinder (an NSProxy stored
// in NSWindowController's _moreVars). AppKit does not retain the owner
// (_isRetainingBindingTarget = 0). -unbind: empties the binding list and
// leaves _bindingTarget set; Autounbinder's dealloc still releases it.
// After ViewerController's extra [self autorelease] on close, that is a
// zombie.
//
// retainBindingTargetAndUnbind is AppKit's teardown: it retains the owner
// and unbinds. The later Autounbinder dealloc then balances that retain
// instead of releasing a dead controller. Read _moreVars.autounbinder.
// Do not call -_autounbinder — that getter creates a proxy when none
// exists. Do not clear the slot here: dropping it while the proxy
// retains the owner races the extra autorelease (measured zombie).
void HorosDetachAutounbinder(id owner)
{
    if (![owner isKindOfClass:[NSWindowController class]])
        return;

    Ivar moreSlot = class_getInstanceVariable([NSWindowController class], "_moreVars");
    if (!moreSlot)
        return;
    id moreVars = object_getIvar(owner, moreSlot);
    if (!moreVars)
        return;

    Ivar binderSlot = class_getInstanceVariable(object_getClass(moreVars), "autounbinder");
    if (!binderSlot)
        return;
    id unbinder = object_getIvar(moreVars, binderSlot);
    if (!unbinder)
        return;

    SEL detach = NSSelectorFromString(@"retainBindingTargetAndUnbind");
    // NSAutounbinder is an NSProxy: -respondsToSelector: forwards to the
    // File's Owner, which does not implement this. Look at the class.
    if (!class_getInstanceMethod(object_getClass(unbinder), detach))
        return;
#if __has_feature(objc_arc)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
#endif
    [unbinder performSelector:detach];
#if __has_feature(objc_arc)
#pragma clang diagnostic pop
#endif
}
