/*=========================================================================
 This file is part of the Horos Project (www.horosproject.org)
 
 Horos is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License as published by
 the Free Software Foundation,  version 3 of the License.
 
 The Horos Project was based originally upon the OsiriX Project which at the time of
 the code fork was licensed as a LGPL project.  However, not all of the the source-code
 was properly documented and file headers were not all updated with the appropriate
 license terms. The Horos Project, originally was licensed under the  GNU GPL license.
 However, contributors to the software since that time have agreed to modify the license
 to the GNU LGPL in order to be conform to the changes previously made to the
 OsiriX Project.
 
 Horos is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY EXPRESS OR IMPLIED, INCLUDING ANY WARRANTY OF
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE OR USE.  See the
 GNU Lesser General Public License for more details.
 
 You should have received a copy of the GNU Lesser General Public License
 along with Horos.  If not, see http://www.gnu.org/licenses/lgpl.html
 
 Prior versions of this file were published by the OsiriX team pursuant to
 the below notice and licensing protocol.
 ============================================================================
 Program:   OsiriX
  Copyright (c) OsiriX Team
  All rights reserved.
  Distributed under GNU - LGPL
  
  See http://www.osirix-viewer.com/copyright.html for details.
     This software is distributed WITHOUT ANY WARRANTY; without even
     the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
     PURPOSE.
 ============================================================================*/
//
//  Copyright (c) 2026 Thales Matheus M Santos (ThalesMMS) — modifications in this fork

import Cocoa
import CoreData
import IOKit
import SystemConfiguration
import UserNotifications
import Synchronization
import os

fileprivate let MAXSCREENS = 10

// The thumbnails list panels, one per screen, stay the exported C array
// thumbnailsListPanel of AppController+CAPI.m, which ViewerController.m reads.
fileprivate func thumbnailsListPanelAt(_ index: Int) -> ThumbnailsListPanel? {
    return AppControllerCAPIThumbnailsListPanel(index)
}

fileprivate func setThumbnailsListPanelAt(_ index: Int, _ panel: ThumbnailsListPanel?) {
    AppControllerCAPISetThumbnailsListPanel(index, panel)
}

// The exported global USETOOLBARPANEL. Inside the class the name is the class
// method +USETOOLBARPANEL, so the global is read and written through here.
@MainActor fileprivate var useToolbarPanel: Bool {
    get { return USETOOLBARPANEL.boolValue }
    set { USETOOLBARPANEL = ObjCBool(newValue) }
}

// The former file sent messages whose receiver may be nil, and read values of
// type id: a message to nil answered 0, NO or nil. These say the same thing.
// The callers run inside HorosObjCException.perform where the former code had
// @try, so the exceptions an Objective-C method raises keep ending where they
// ended.
fileprivate enum ObjC {
    /// The argument of a "%@": nil prints (null).
    static func arg(_ value: Any?) -> CVarArg {
        guard let value = value else { return "(null)" as NSString }
        if let object = (value as AnyObject) as? NSObject { return object }
        return "\(value)" as NSString
    }

    /// [NSString stringWithFormat:format, ...] with object arguments.
    static func format(_ format: String, _ values: Any?...) -> String {
        return String(format: format, arguments: values.map { arg($0) })
    }

    /// The NSException an Objective-C call raised inside HorosObjCException.perform.
    static func exception(_ error: Error) -> NSException? {
        return (error as NSError).userInfo[HorosObjCExceptionKey] as? NSException
    }

    /// [value intValue]: 0 for nil.
    static func int(_ value: Any?) -> Int32 {
        if let number = value as? NSNumber { return number.int32Value }
        if let string = value as? NSString { return string.intValue }
        return 0
    }

    /// [value integerValue]: 0 for nil.
    static func integer(_ value: Any?) -> Int {
        if let number = value as? NSNumber { return number.intValue }
        if let string = value as? NSString { return string.integerValue }
        return 0
    }

    /// [value boolValue]: NO for nil.
    static func bool(_ value: Any?) -> Bool {
        if let number = value as? NSNumber { return number.boolValue }
        if let string = value as? NSString { return string.boolValue }
        return false
    }
}

/** \brief  NSApplication delegate
*
*  NSApplication delegate 
*  Primarily manages the user defaults and server
*  Also controls some general main items
*
*
*/
// Main actor: the application delegate, which owns the menus, the windows
// and the listeners' lifecycle. What the listener, import, web portal and
// update-check threads call is nonisolated and says so.
@MainActor
@objc(AppController)
public final class AppController: NSObject, NetServiceBrowserDelegate, NetServiceDelegate, NSSoundDelegate, NSMenuDelegate, UNUserNotificationCenterDelegate {

    // What the static variables of the former file held, with the same
    // first-call semantics: they belong to the class, not to an instance.
    @MainActor private enum State {
        static var mainMenuCLUTMenu: NSMenu? = nil, mainMenuWLWWMenu: NSMenu? = nil, mainMenuConvMenu: NSMenu? = nil, mainOpacityMenu: NSMenu? = nil
        static var previousWLWWKeys: NSDictionary? = nil, previousCLUTKeys: NSDictionary? = nil, previousConvKeys: NSDictionary? = nil, previousOpacityKeys: NSDictionary? = nil
        static var checkForPreferencesUpdate = true
        static var pluginManager: PluginManager? = nil
        static var LUT12toRGB: UnsafeMutablePointer<UInt8>? = nil
        static var canDisplay12Bit = false
        static var fill12BitBufferInvocation: AnyObject? = nil
        static var firstCall = true
        static var initialized = false
        // -updateScreenParameters
        static var previousScreenParameters: NSArray? = nil
        static var previousOrderedIdentifiers: NSArray? = nil
        // -notificationTitle:description:name:
        static var delivered: NSMutableDictionary? = nil, pending: NSMutableDictionary? = nil
        // -defaultWebPortalManagedObjectContext, which any thread may ask.
        nonisolated static let fakeContextLock = NSLock()
        // nonisolated(unsafe): read and written only inside
        // `fakeContextLock.withLock`.
        nonisolated(unsafe) static var fakeContext: NSManagedObjectContext? = nil
        // -_receivingIconSet:, from the listener threads.
        // nonisolated(unsafe): read and written only inside
        // objc_sync_enter(self)/objc_sync_exit(self) on the one AppController,
        // by -_receivingIconSet: and -_receivingIconUpdate.
        nonisolated(unsafe) static var receivingDict: NSMutableDictionary? = nil
    }

    // A study arrives in many batches and each batch reports itself. Posted under a
    // new identifier every time, that made hundreds of notifications per study, which
    // the Notification Center kept and saved again at each arrival until usernoted
    // ran at 220% CPU (#696). Each kind now has one identifier, so a notification
    // replaces the previous one of its kind, and a burst is delivered at most once
    // every HorosNotificationInterval seconds with the latest text. Only the first
    // of a burst makes a sound.
    private static let HorosNotificationInterval: TimeInterval = 10, HorosNotificationQuietSound: TimeInterval = 60

    // The former instance variables. The outlets are set by MainMenu.xib.
    @IBOutlet @objc private var browserController: BrowserController?

    @IBOutlet @objc public private(set) var filtersMenu: NSMenu!
    @IBOutlet @objc private var roisMenu: NSMenu?
    @IBOutlet @objc private var othersMenu: NSMenu?
    @IBOutlet @objc private var dbMenu: NSMenu?
    @IBOutlet @objc private var dbWindow: NSWindow?
    @IBOutlet @objc public private(set) var windowsTilingMenuRows: NSMenu!
    @IBOutlet @objc public private(set) var windowsTilingMenuColumns: NSMenu!
    @IBOutlet @objc public private(set) var recentStudiesMenu: NSMenu!

    private var previousDefaults: NSDictionary? = nil

    private var showRestartNeeded = false

    private var splashController: SplashScreen? = nil

    private var quitting = false
    private var verboseUpdateCheck = false
    private var BonjourDICOMService: NetService? = nil

    private var updateTimer: Timer? = nil
    @objc(XMLRPCServer) public private(set) var xmlrpcServer: XMLRPCInterface! = nil

    @objc public var checkAllWindowsAreVisibleIsOff = false
    /// Read by the database's cleaning and the browser, from any thread;
    /// written on the main thread when the session switches.
    private nonisolated let sessionInactive = Atomic<Bool>(false)
    @objc public nonisolated var isSessionInactive: Bool {
        get { sessionInactive.load(ordering: .relaxed) }
        set { sessionInactive.store(newValue, ordering: .relaxed) }
    }

    private var lastColumns: Int32 = 0, lastRows: Int32 = 0, lastCount: Int32 = 0

    /// Set once while launching, then read by the connection threads of the
    /// shared database: the lock publishes the reference, the object keeps its
    /// own locking.
    private nonisolated let _bonjourPublisher = OSAllocatedUnfairLock<BonjourPublisher?>(uncheckedState: nil)

    @objc public var dicomBonjourPublisher: NetService! {
        return BonjourDICOMService
    }

    @objc public nonisolated var bonjourPublisher: BonjourPublisher! {
        return _bonjourPublisher.withLockUnchecked { $0 }
    }

    @objc nonisolated class func operatingSystemVersion() -> OperatingSystemVersion {
        let info = ProcessInfo.processInfo
        if info.responds(to: #selector(getter: ProcessInfo.operatingSystemVersion)) {
            return info.operatingSystemVersion
        }

        // Gestalt, which Swift does not import: AppController+CAPI.m.
        return AppControllerCAPIGestaltSystemVersion()
    }

    @objc nonisolated public class func hasMacOSX1083() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion == 10 && v.minorVersion == 8 && v.patchVersion == 3)
    }

    @objc nonisolated class func hasMacOSXSierra() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 12)
    }

    @objc nonisolated class func hasMacOSXElCapitan() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 11)
    }

    @objc nonisolated public class func hasMacOSXYosemite() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 10)
    }

    @objc nonisolated public class func hasMacOSXMaverick() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 9)
    }

    @objc nonisolated public class func hasMacOSXMountainLion() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 8)
    }

    @objc nonisolated public class func hasMacOSXLion() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 7)
    }

    @objc nonisolated public class func hasMacOSXSnowLeopard() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 6)
    }

    @objc nonisolated public class func hasMacOSXLeopard() -> Bool {
        let v = self.operatingSystemVersion()
        return (v.majorVersion > 10 || v.minorVersion >= 5)
    }

    @available(*, deprecated) @objc(createNoIndexDirectoryIfNecessary:) public class func createNoIndexDirectoryIfNecessary(_ path: String!) { // __deprecated
        FileManager.default.confirmNoIndexDirectory(atPath: path)
    }

    @available(*, deprecated) @objc(pause) nonisolated public class func pause() {
        // The instance method -pause has the same selector as this class method.
        AppController.shared()?.performSelector(onMainThread: NSSelectorFromString("pause"), with: nil, waitUntilDone: false)
    }

    @objc(applicationDidChangeScreenParameters:) func applicationDidChangeScreenParameters(_ aNotification: Notification!) {
        self.updateScreenParameters()
    }

    @objc public func updateScreenParameters() {
        let screenParameters = NSMutableArray()
        let screenIdentifiers = NSMutableArray()
        let screens = NSScreen.screens
        if screens.count == 0 {
            NSLog("updateScreenParameters: ignoring transient empty display list")
            return
        }
        for screen in screens {
            // During a display reconfiguration AppKit can transiently report a 0x0 screen. Rescaling or
            // closing windows from such a snapshot corrupts window frames; wait for the final notification.
            if NSIsEmptyRect(screen.frame) || !screen.frame.origin.x.isFinite || !screen.frame.origin.y.isFinite || !screen.frame.size.width.isFinite || !screen.frame.size.height.isFinite {
                NSLog("updateScreenParameters: ignoring transient empty screen frame")
                return
            }

            let identifier: Any = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] ?? NSNumber(value: Int32(0))
            screenIdentifiers.add(identifier)
            screenParameters.add([identifier, NSValue(rect: screen.frame), NSValue(rect: screen.visibleFrame)] as NSArray)
        }

        // NSScreen order can change when focus/main screen changes. Compare by the
        // stable display identifier so reordering cannot close open studies/ROIs.
        let orderedIdentifiers = screenIdentifiers.copy() as! NSArray
        screenParameters.sort(comparator: { left, right in
            return ((left as! NSArray).object(at: 0) as! NSNumber).compare((right as! NSArray).object(at: 0) as! NSNumber)
        })
        screenIdentifiers.sort(using: #selector(NSNumber.compare(_:)))

        // static NSArray *previousScreenParameters, *previousOrderedIdentifiers: State
        let geometryChanged = !screenParameters.isEqual(State.previousScreenParameters)
        let panelMappingChanged = !orderedIdentifiers.isEqual(State.previousOrderedIdentifiers)
        if !geometryChanged && !panelMappingChanged { return }

        // Publish before moving any windows: AppKit can synchronously send another
        // screen notification while the new layout is being applied.
        State.previousScreenParameters = screenParameters.copy() as? NSArray
        State.previousOrderedIdentifiers = orderedIdentifiers
        if panelMappingChanged { AppController.resetThumbnailsList() }
        BrowserController.currentBrowser()?.recoverWindowsAfterScreenChange()
    }

    @objc class func resetThumbnailsList() {
        let numberOfScreens = min(MAXSCREENS, NSScreen.screens.count + 1) //Just in case, we connect a second monitor when using Horos.

        for i in 0..<MAXSCREENS {
            thumbnailsListPanelAt(i)?.prepareForScreenReconfiguration()
            setThumbnailsListPanelAt(i, nil)
        }

        for i in 0..<numberOfScreens {
            setThumbnailsListPanelAt(i, ThumbnailsListPanel(forScreen: i))
        }
    }

    @objc(resizeWindowWithAnimation:newSize:) public class func resizeWindow(withAnimation window: NSWindow!, newSize newWindowFrame: NSRect) {
        if UserDefaults.standard.bool(forKey: "NSWindowsSetFrameAnimate") {
            do {
                try HorosObjCException.perform {
                    // dictionaryWithObjectsAndKeys: stopped at a nil window and made an empty dictionary.
                    var windowResize: [NSViewAnimation.Key: Any] = [:]
                    if let window = window {
                        windowResize = [NSViewAnimation.Key.target: window,
                                        NSViewAnimation.Key.endFrame: NSValue(rect: newWindowFrame)]
                    }

                    if accumulateAnimations.boolValue {
                        if accumulateAnimationsArray == nil { accumulateAnimationsArray = NSMutableArray() }
                        accumulateAnimationsArray.add(windowResize as NSDictionary)
                    } else {
                        OSIWindowController.setDontEnterWindowDidChangeScreen(true)

                        let animation = NSViewAnimation(viewAnimations: [windowResize])
                        animation.animationBlockingMode = .blocking
                        animation.duration = 0.15
                        animation.start()

                        OSIWindowController.setDontEnterWindowDidChangeScreen(false)
                    }
                }
            } catch {
                NSLog("resizeWindowWithAnimation exception: %@", ObjC.arg(ObjC.exception(error)))
            }
        } else {
            window?.setFrame(newWindowFrame, display: true)
        }
    }

    //+(ToolbarPanelController*)toolbarForScreen:(NSScreen*)screen
    //{
    //    NSArray* screens = [NSScreen screens];
    //    NSUInteger i = [screens indexOfObject:screen];
    //
    //    if( i == NSNotFound)
    //        return nil;
    //
    //    if( i>= MAXSCREENS)
    //        return nil;
    //
    //    return toolbarPanel[i];
    //}

    @objc(thumbnailsListPanelForScreen:) public class func thumbnailsListPanel(for screen: NSScreen!) -> ThumbnailsListPanel! {
        let screens = NSScreen.screens as NSArray
        // indexOfObject:nil answered NSNotFound.
        let i: Int = screen.map { screens.index(of: $0) } ?? NSNotFound

        if i == NSNotFound {
            return nil
        }

        if i >= MAXSCREENS {
            return nil
        }

        return thumbnailsListPanelAt(i)
    }

    // +displayImportantNotice: (WITH_IMPORTANT_NOTICE, not defined) is in AppController+CAPI.m.

    // Kept for plugins. JPEG 2000 goes through the DCMTK codec (#740); there is no
    // other engine to choose (#742).
    @objc nonisolated public class func isKDUEngineAvailable() -> Bool {
        return false
    }

    @objc(checkForPreferencesUpdate:) public class func checkForPreferencesUpdate(_ b: Bool) {
        State.checkForPreferencesUpdate = b
    }

    @objc nonisolated class func cleanOsiriXSubProcesses() {
        let kPIDArrayLength: Int32 = 100

        var MyArray = [pid_t](repeating: 0, count: Int(kPIDArrayLength))
        var NumberOfMatches: UInt32 = 0
        let Error: Int32

        // Every candidate below is matched on its BSD process name, which is shared
        // by anything else of that name this user is running. Only a process
        // launched from inside our own bundle may be signalled.
        let bundlePath = (Bundle.main.bundlePath as NSString).fileSystemRepresentation

        // The listener no longer forks a process per association (#967): there
        // are no children of ours to end here.

        Error = GetAllPIDsForProcessName("CrashReporter", &MyArray, UInt32(kPIDArrayLength), &NumberOfMatches, nil)

        if Error == 0 {
            for Counter in 0..<Int(NumberOfMatches) {
                if MyArray[Counter] != getpid() && AppControllerCAPIProcessIsOurs(MyArray[Counter], bundlePath) {
                    NSLog("Child Process to kill (CrashReporter): %d (PID)", MyArray[Counter])
                    kill(MyArray[Counter], 15)
                }
            }
        }
    }

    @objc(UID) nonisolated public class func uid() -> String! {
        return ObjC.format("%@|%@", N2Shell.serialNumber(), NSUserName())
    }

    @objc(setUSETOOLBARPANEL:) public class func setUSETOOLBARPANEL(_ b: Bool) {
        useToolbarPanel = b
    }

    @objc(USETOOLBARPANEL) public class func usetoolbarpanel() -> Bool {
        return useToolbarPanel
    }

    @objc(sharedAppController) nonisolated public class func shared() -> AppController! {
        return appController
    }

    @objc(DNSResolve:) nonisolated class func DNSResolve(_ o: Any!) {
        NSLog("start DNSResolve")

        for s in DefaultsOsiriX.currentHost()?.names ?? [] {
            NSLog("%@", s as NSString)
        }

        NSLog("end DNSResolve")
    }

    @available(*, deprecated) @objc(printStackTrace:) nonisolated public class func printStackTrace(_ e: NSException!) -> String! {
        let r = NSMutableString()

        do {
            try HorosObjCException.perform {
                let addresses = e?.callStackReturnAddresses ?? []
                if addresses.count > 0 {
                    var backtrace_frames = [UnsafeMutableRawPointer?](repeating: nil, count: addresses.count)
                    var i = 0
                    for address in addresses {
                        backtrace_frames[i] = UnsafeMutableRawPointer(bitPattern: address.uintValue)
                        i += 1
                    }

                    var frameStrings = backtrace_symbols(&backtrace_frames, Int32(addresses.count))

                    if frameStrings != nil {
                        for x in 0..<addresses.count {
                            let frame_description = frameStrings?[x].flatMap { NSString(utf8String: $0) }
                            NSLog("------- %@", ObjC.arg(frame_description))
                            r.appendFormat("%@\r", ObjC.arg(frame_description))
                        }
                        free(frameStrings)
                        frameStrings = nil
                    }
                }
            }
        } catch {
            if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, true, "+[AppController printStackTrace:]") }
        }

        return r as String
    }

    @objc nonisolated public class func willExecutePlugin() -> Bool {
        return self.willExecutePlugin(nil)
    }

    @objc(willExecutePlugin:) nonisolated public class func willExecutePlugin(_ filter: Any!) -> Bool {
        let returnValue = true

        return returnValue
    }

    @objc func pause() { // __deprecated
        // Keep the legacy plugin pause on the database queue.
        N2ManagedObjectContextPerformAndWait(BrowserController.currentBrowser()?.database?.managedObjectContext) {
            sleep(2)
        }
    }

    // Plugins installation
    @objc(installPlugins:) public func installPlugins(_ pluginsArray: [Any]!) {
        #if !MACAPPSTORE
        var pluginNames = NSMutableString()
        var replacingPlugins = NSMutableString()

        let replacing = NSLocalizedString(" will be replaced by ", comment: "")
        let strVersion = NSLocalizedString(" version ", comment: "")

        // -appendString: sent as a message, so a nil or non-string argument raises as it did.
        func appendToReplacingPlugins(_ s: Any?) {
            _ = replacingPlugins.perform(#selector(NSMutableString.append(_:)), with: s)
        }

        for pathObject in pluginsArray ?? [] {
            let path = pathObject as! NSString

            pluginNames.appendFormat("%@, ", (path.lastPathComponent as NSString).deletingPathExtension as NSString)

            let pluginBundleName = (path.lastPathComponent as NSString).deletingPathExtension

            let bundleURL = URL(fileURLWithPath: path.resolvingAlias())
            let bundleInfoDict = CFBundleCopyInfoDictionaryInDirectory(bundleURL as CFURL) as NSDictionary?

            var versionString: Any? = nil
            if bundleInfoDict != nil {
                versionString = bundleInfoDict?.object(forKey: "CFBundleVersion")

                if versionString == nil {
                    versionString = bundleInfoDict?.object(forKey: "CFBundleShortVersionString")
                }
            }

            var pluginBundleVersion: Any? = nil
            if versionString != nil {
                pluginBundleVersion = versionString
            } else {
                pluginBundleVersion = ""
            }

            // (if (bundleInfoDict != NULL) CFRelease(bundleInfoDict); — Swift manages the dictionary)

            for case let plug as NSDictionary in PluginManager.pluginsList() ?? [] {
                if pluginBundleName == (plug.object(forKey: "name") as? String) {
                    appendToReplacingPlugins(plug.object(forKey: "name"))
                    appendToReplacingPlugins(strVersion)
                    appendToReplacingPlugins(plug.object(forKey: "version"))
                    appendToReplacingPlugins(replacing)
                    appendToReplacingPlugins(pluginBundleName)
                    appendToReplacingPlugins(strVersion)
                    appendToReplacingPlugins(pluginBundleVersion)
                    appendToReplacingPlugins(".\n\n")
                }
            }

            // (if( bundleInfoDict) CFRelease( bundleInfoDict); — Swift manages the dictionary)
        }

        pluginNames = NSMutableString(string: pluginNames.substring(to: pluginNames.length - 2))
        if replacingPlugins.length > 0 { replacingPlugins = NSMutableString(string: replacingPlugins.substring(to: replacingPlugins.length - 2)) }

        var msg: String
        let areYouSure = NSLocalizedString("Are you sure you want to install", comment: "")

        if (pluginsArray?.count ?? 0) == 1 {
            msg = ObjC.format(NSLocalizedString("%@ the plugin named : %@ ?", comment: ""), areYouSure, pluginNames)
        } else {
            msg = ObjC.format(NSLocalizedString("%@ the following plugins : %@ ?", comment: ""), areYouSure, pluginNames)
        }

        if replacingPlugins.length > 0 {
            msg = ObjC.format("%@\n\n%@", msg, replacingPlugins)
        }

        let res = HorosAlertPanel.run(title: NSLocalizedString("Plugins Installation", comment: ""), message: msg, defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: NSLocalizedString("Cancel", comment: ""), otherButton: nil)

        if res != 0 {
            for path in pluginsArray ?? [] {
                PluginManager.installPlugin(fromPath: path as? String)
            }

            PluginManager.setMenus(filtersMenu, roisMenu, othersMenu, dbMenu)

            // refresh the plugin manager window (if open)
            let winList = NSApp.windows
            for window in winList {
                if window.windowController is PluginManagerController {
                    (window.windowController as? PluginManagerController)?.refreshPluginList()
                }
            }
        }
        #endif
    }

    @objc nonisolated func computerName() -> String! {
        return SCDynamicStoreCopyComputerName(nil, nil) as String?
    }

    @objc nonisolated public func privateIP() -> String! {
        return String(utf8String: GetPrivateIP())
    }

    @IBAction @objc(cancelModal:) public func cancelModal(_ sender: Any!) {
        NSApp.abortModal()
    }

    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    @IBAction @objc(okModal:) public func okModal(_ sender: Any!) {
        NSApp.stopModal()
    }

    @IBAction @objc(autoQueryRefresh:) public func autoQueryRefresh(_ sender: Any!) {
        QueryController.currentAuto()?.refreshAutoQR(sender)
    }

    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    // MARK: -

    @IBAction @objc(openHorosWebPage:) public func openHorosWebPage(_ sender: Any!) {
        NSWorkspace.shared.open(URL(string: "https://github.com/ThalesMMS/horos")!) // URL_HOROS_WEB_PAGE
    }

    @IBAction @objc(help:) public func help(_ sender: Any!) {
        NSWorkspace.shared.open(URL(string: "https://github.com/ThalesMMS/horos")!) // URL_HOROS_LEARNING
    }

    @IBAction @objc(openHorosSupport:) public func openHorosSupport(_ sender: Any!) {
        NSWorkspace.shared.open(URL(string: "https://github.com/ThalesMMS/horos/issues")!) // URL_HOROS_SUPPORT_PAGE
    }

    @IBAction @objc(openCommunityPage:) public func openCommunityPage(_ sender: Any!) {
        NSWorkspace.shared.open(URL(string: "https://github.com/ThalesMMS/horos/issues")!) // URL_HOROS_COMMUNITY
    }

    @IBAction @objc(openBugReportPage:) public func openBugReportPage(_ sender: Any!) {
        NSWorkspace.shared.open(URL(string: "https://github.com/ThalesMMS/horos/issues")!) // URL_HOROS_BUG_REPORT_PAGE
    }

    @IBAction @objc(sendEmail:) public func sendEmail(_ sender: Any!) {
        // The original project's mailbox is not this application's support address.
        NSWorkspace.shared.open(URL(string: "https://github.com/ThalesMMS/horos/issues")!) // URL_HOROS_SUPPORT_PAGE
    }

    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    // MARK: -

    @objc(waitForPID:) nonisolated func waitForPID(_ pidNumber: NSNumber!) {
        let pid = ObjC.int(pidNumber)
        var rc: Int32, state: Int32 = 0
        var threadStateChanged = false
        let path = String(format: "%s/process_state-%d", HorosDICOMProcessFolder(), pid)

        repeat {
            if threadStateChanged == false {
                if FileManager.default.fileExists(atPath: path) && ((try? NSString(contentsOfFile: path, encoding: String.Encoding.utf8.rawValue))?.length ?? 0) > 0 {
                    Thread.current.status = (Thread.current.status as NSString?)?.appendingFormat(NSLocalizedString(" - %@", comment: "") as NSString, ObjC.arg(try? NSString(contentsOfFile: path, usedEncoding: nil))) as String?
                    Thread.sleep(forTimeInterval: 1)
                    threadStateChanged = true
                }
            }

            rc = waitpid(pid, &state, WNOHANG)
            Thread.sleep(forTimeInterval: 0.1)
        } while rc >= 0
    }


    @objc nonisolated func setAETitleToHostname() {
        var s = [CChar](repeating: 0, count: Int(_POSIX_HOST_NAME_MAX) + 1)
        gethostname(&s, Int(_POSIX_HOST_NAME_MAX))
        var c: NSString? = NSString(utf8String: s)
        // A nil c answered the range {0, 0}.
        let range = c?.range(of: ".") ?? NSRange(location: 0, length: 0)
        if range.location != NSNotFound { c = c?.substring(to: range.location) as NSString? }

        if (c?.length ?? 0) > 16 {
            c = c?.substring(to: 16) as NSString?
        }

        if (c?.length ?? 0) == 0 {
            c = "ISIS"
        }

        UserDefaults.standard.set(c, forKey: "AETITLE")
    }

    @objc(runPreferencesUpdateCheck:) public func runPreferencesUpdateCheck(_ timer: Timer!) {
        updateTimer?.invalidate()
        updateTimer = nil

        var restartListener = false
        var refreshDatabase = false
        var refreshColumns = false
        var recomputePETBlending = false
        var refreshViewer = false
        var revertViewer = false

        let defaults = UserDefaults.standard

        if Thread.isMainThread == false { return }

        let dictionaryRepresentation = defaults.dictionaryRepresentation() as NSDictionary

        if dictionaryRepresentation.isEqual(previousDefaults) { return }

        do {
            try HorosObjCException.perform {
                let seriesListModeChanged = ObjC.bool(previousDefaults?.value(forKey: "UseFloatingThumbnailsList")) != defaults.bool(forKey: "UseFloatingThumbnailsList")
                let seriesListKeyWindow: NSWindow? = seriesListModeChanged ? NSApp.keyWindow : nil
                if seriesListModeChanged {
                    // Return every borrowed list before changing any viewer's dock.
                    // In particular, detaching still works after the preference is NO.
                    for i in 0..<MAXSCREENS {
                        thumbnailsListPanelAt(i)?.prepareForScreenReconfiguration()
                    }
                    for case let v as ViewerController in (ViewerController.get2DViewers() ?? NSMutableArray()) {
                        v.updateSeriesListMode()
                    }
                }
                if seriesListModeChanged || Int(ObjC.int(previousDefaults?.value(forKey: "SeriesListVisible"))) != defaults.integer(forKey: "SeriesListVisible") {
                    if UserDefaults.standard.bool(forKey: "UseFloatingThumbnailsList") {
                        AppController.shared()?.tileWindows(nil)
                        for s in NSScreen.screens {
                            let v: ViewerController? = ViewerController.frontMostDisplayed2DViewer(for: s)
                            v?.window?.makeKeyAndOrderFront(self)
                            v?.redrawToolbar()
                        }
                    } else {
                        for case let v as ViewerController in (ViewerController.getDisplayed2DViewers() ?? NSMutableArray()) {
                            v.setMatrixVisible(defaults.integer(forKey: "SeriesListVisible") != 0)
                        }
                        if seriesListModeChanged {
                            AppController.shared()?.tileWindows(nil)
                        }
                    }
                    // Changing a preference must not leave its window behind a viewer.
                    if seriesListKeyWindow?.isVisible == true {
                        seriesListKeyWindow?.makeKeyAndOrderFront(self)
                    }
                }

                if Int(ObjC.int(previousDefaults?.value(forKey: "DisplayDICOMOverlays"))) != defaults.integer(forKey: "DisplayDICOMOverlays") {
                    revertViewer = true
                }
                if ObjC.bool(previousDefaults?.value(forKey: "ROIPRIMARYMEASUREMENTONLY")) != defaults.bool(forKey: "ROIPRIMARYMEASUREMENTONLY") {
                    refreshViewer = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "ROITEXTNAMEONLY"))) != defaults.integer(forKey: "ROITEXTNAMEONLY") {
                    refreshViewer = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "ROITEXTIFSELECTED"))) != defaults.integer(forKey: "ROITEXTIFSELECTED") {
                    refreshViewer = true
                }
                // A string preference without a previous value (a key seen for the
                // first time) is not an error: only a value of another type is logged.
                if let previous = previousDefaults?.value(forKey: "PET Blending CLUT") as? NSString {
                    if previous.isEqual(defaults.string(forKey: "PET Blending CLUT")) == false {
                        recomputePETBlending = true
                    }
                }
                else if previousDefaults?.value(forKey: "PET Blending CLUT") != nil { NSLog("*** isKindOfClass NSString") }
                if Int(ObjC.int(previousDefaults?.value(forKey: "COPYSETTINGS"))) != defaults.integer(forKey: "COPYSETTINGS") {
                    refreshViewer = true
                }
                if let previous = previousDefaults?.value(forKey: "DBDateFormat2") as? NSString {
                    if previous.isEqual(defaults.string(forKey: "DBDateFormat2")) == false {
                        refreshDatabase = true
                    }
                }
                else if previousDefaults?.value(forKey: "DBDateFormat2") != nil { NSLog("*** isKindOfClass NSString") }
                if let previous = previousDefaults?.value(forKey: "DBDateOfBirthFormat2") as? NSString {
                    if previous.isEqual(defaults.string(forKey: "DBDateOfBirthFormat2")) == false {
                        refreshDatabase = true
                    }
                }
                else if previousDefaults?.value(forKey: "DBDateOfBirthFormat2") != nil { NSLog("*** isKindOfClass NSString") }
                if Int(ObjC.int(previousDefaults?.value(forKey: "DICOMTimeout"))) != defaults.integer(forKey: "DICOMTimeout") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "DICOMConnectionTimeout"))) != defaults.integer(forKey: "DICOMConnectionTimeout") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "UseHostNameForAETitle"))) != defaults.integer(forKey: "UseHostNameForAETitle") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "preferredSyntaxForIncoming"))) != defaults.integer(forKey: "preferredSyntaxForIncoming") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "httpXMLRPCServer"))) != defaults.integer(forKey: "httpXMLRPCServer") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "httpXMLRPCServerPort"))) != defaults.integer(forKey: "httpXMLRPCServerPort") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "httpXMLRPCServerAllowRemote"))) != defaults.integer(forKey: "httpXMLRPCServerAllowRemote") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "httpWebServer"))) != defaults.integer(forKey: "httpWebServer") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "httpWebServerPort"))) != defaults.integer(forKey: "httpWebServerPort") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "encryptedWebServer"))) != defaults.integer(forKey: "encryptedWebServer") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "LISTENERCHECKINTERVAL"))) != defaults.integer(forKey: "LISTENERCHECKINTERVAL") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "activateCGETSCP"))) != defaults.integer(forKey: "activateCGETSCP") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "activateCFINDSCP"))) != defaults.integer(forKey: "activateCFINDSCP") {
                    restartListener = true
                }

                if let previous = previousDefaults?.value(forKey: "AETITLE") as? NSString {
                    if previous.isEqual(defaults.string(forKey: "AETITLE")) == false {
                        restartListener = true
                    }
                }
                else if previousDefaults?.value(forKey: "AETITLE") != nil { NSLog("*** isKindOfClass NSString") }
                if let previous = previousDefaults?.value(forKey: "STORESCPEXTRA") as? NSString {
                    if previous.isEqual(defaults.string(forKey: "STORESCPEXTRA")) == false {
                        restartListener = true
                    }
                }
                else if previousDefaults?.value(forKey: "STORESCPEXTRA") != nil { NSLog("*** isKindOfClass NSString") }
                if Int(ObjC.int(previousDefaults?.value(forKey: "AEPORT"))) != defaults.integer(forKey: "AEPORT") {
                    restartListener = true
                }
                if let previous = previousDefaults?.value(forKey: "AETransferSyntax") as? NSString {
                    if previous.isEqual(defaults.string(forKey: "AETransferSyntax")) == false {
                        restartListener = true
                    }
                }
                else if previousDefaults?.value(forKey: "AETransferSyntax") != nil { NSLog("*** isKindOfClass NSString") }
                if Int(ObjC.int(previousDefaults?.value(forKey: OsirixCanActivateDefaultDatabaseOnlyDefaultsKey))) != defaults.integer(forKey: OsirixCanActivateDefaultDatabaseOnlyDefaultsKey) {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "STORESCP"))) != defaults.integer(forKey: "STORESCP") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "USESTORESCP"))) != defaults.integer(forKey: "USESTORESCP") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "HIDEPATIENTNAME"))) != defaults.integer(forKey: "HIDEPATIENTNAME") {
                    refreshDatabase = true
                }
                if ((previousDefaults?.value(forKey: "COLUMNSDATABASE") as? NSDictionary)?.isEqual(defaults.object(forKey: "COLUMNSDATABASE")) ?? false) == false {
                    refreshColumns = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "SERIESORDER"))) != defaults.integer(forKey: "SERIESORDER") {
                    refreshDatabase = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "KeepStudiesOfSamePatientTogether"))) != defaults.integer(forKey: "KeepStudiesOfSamePatientTogether") {
                    refreshDatabase = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "NOINTERPOLATION"))) != defaults.integer(forKey: "NOINTERPOLATION") {
                    refreshViewer = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "SOFTWAREINTERPOLATION"))) != defaults.integer(forKey: "SOFTWAREINTERPOLATION") {
                    refreshViewer = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "publishDICOMBonjour"))) != defaults.integer(forKey: "publishDICOMBonjour") {
                    restartListener = true
                }
                if Int(ObjC.int(previousDefaults?.value(forKey: "STORESCPTLS"))) != defaults.integer(forKey: "STORESCPTLS") {
                    restartListener = true
                }

                if defaults.integer(forKey: "httpWebServer") == 1 && defaults.integer(forKey: "httpWebServer") != Int(ObjC.int(previousDefaults?.value(forKey: "httpWebServer"))) {
                    if AppController.hasMacOSXSnowLeopard() == false {
                        HorosAlertPanel.runCritical(title: NSLocalizedString("Unsupported", comment: ""), message: NSLocalizedString("It is highly recommend to upgrade to MacOS 10.6 or higher to use the Isis DICOM Viewer Web Server.", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
                    }
                }

                previousDefaults = dictionaryRepresentation

                if refreshDatabase {
                    BrowserController.currentBrowser()?.setDBDate()
                    BrowserController.currentBrowser()?.outlineViewRefresh()
                }

            //	if( [(NSString*) [defaults valueForKey:OsirixWebPortalAddressDefaultsKey] length] == 0)
            //		[defaults setValue: [[AppController sharedAppController] privateIP] forKey:OsirixWebPortalAddressDefaultsKey];

                if restartListener {
                    var c = UserDefaults.standard.string(forKey: "AETITLE").map { $0 as NSString }
                    if (c?.length ?? 0) > 16 {
                        c = (c?.substring(to: 16)).map { $0 as NSString }
                        UserDefaults.standard.set(c, forKey: "AETITLE")
                    }

                    if showRestartNeeded == true {
                        showRestartNeeded = false
                        HorosAlertPanel.run(title: NSLocalizedString("DICOM Listener", comment: ""), message: NSLocalizedString("Restart Isis DICOM Viewer to apply these changes.", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
                    }
                }

                if refreshColumns {
                    BrowserController.currentBrowser()?.refreshColumns()
                }

                if recomputePETBlending {
                    DCMView.computePETBlendingCLUT()
                }

                DCMPix.checkUserDefaults(true)

                if refreshViewer || revertViewer {
                    let windows: NSArray = ViewerController.getDisplayed2DViewers() ?? NSMutableArray()

                    for case let v as ViewerController in windows {
                        v.needsDisplayUpdate()
                        if revertViewer {
                            v.displayDICOMOverlays(self)
                        }
                    }

                    for case let v as ViewerController in windows {
                        if v.window?.isMainWindow == true {
                            v.copySettingsToOthers(self)
                        }
                    }
                }

                do {
                    try HorosObjCException.perform {
                        do {
                            let defaultSettings = (defaults.array(forKey: "CompressionSettings").map { $0 as NSArray })?.object(at: 0) as? NSDictionary

                            if ObjC.int(defaultSettings?.value(forKey: "compression")) == 0 ||
                               ((defaultSettings?.value(forKey: "modality") as? NSString)?.isEqual(to: NSLocalizedString("default", comment: "")) ?? false) == false {
                                let d = defaultSettings?.mutableCopy() as? NSMutableDictionary

                                if ObjC.int(defaultSettings?.value(forKey: "compression")) == 0 { // same as default
                                    d?.setObject("1", forKey: "compression" as NSString)
                                }

                                if ((defaultSettings?.value(forKey: "modality") as? NSString)?.isEqual(to: NSLocalizedString("default", comment: "")) ?? false) == false { // item 0 IS default
                                    d?.setObject(NSLocalizedString("default", comment: ""), forKey: "modality" as NSString)
                                }

                                let a = (UserDefaults.standard.array(forKey: "CompressionSettings").map { $0 as NSArray })?.mutableCopy() as? NSMutableArray

                                if let d = d {
                                    a?.replaceObject(at: 0, with: d)
                                }

                                UserDefaults.standard.set(a, forKey: "CompressionSettings")
                            }
                        }

                        do {
                            let defaultSettings = (defaults.array(forKey: "CompressionSettingsLowRes").map { $0 as NSArray })?.object(at: 0) as? NSDictionary

                            if ObjC.int(defaultSettings?.value(forKey: "compression")) == 0 ||
                               ((defaultSettings?.value(forKey: "modality") as? NSString)?.isEqual(to: NSLocalizedString("default", comment: "")) ?? false) == false {
                                let d = defaultSettings?.mutableCopy() as? NSMutableDictionary

                                if ObjC.int(defaultSettings?.value(forKey: "compression")) == 0 { // same as default
                                    d?.setObject("1", forKey: "compression" as NSString)
                                }

                                if ((defaultSettings?.value(forKey: "modality") as? NSString)?.isEqual(to: NSLocalizedString("default", comment: "")) ?? false) == false { // item 0 IS default
                                    d?.setObject(NSLocalizedString("default", comment: ""), forKey: "modality" as NSString)
                                }

                                let a = (UserDefaults.standard.array(forKey: "CompressionSettingsLowRes").map { $0 as NSArray })?.mutableCopy() as? NSMutableArray

                                if let d = d {
                                    a?.replaceObject(at: 0, with: d)
                                }

                                UserDefaults.standard.set(a, forKey: "CompressionSettingsLowRes")
                            }
                        }

                        if UserDefaults.standard.string(forKey: "SupplementaryBurnPath")?.isEmpty ?? true {
                            UserDefaults.standard.set(false, forKey: "BurnSupplementaryFolder")
                            UserDefaults.standard.set(nil, forKey: "SupplementaryBurnPath")
                        }
                    }
                } catch {
                    NSLog("%@", ObjC.arg(ObjC.exception(error)))
                }

                BrowserController.currentBrowser()?.setNetworkLogs()
                DicomFile.resetDefaults()

                DCMView.setDefaults()
                ROI.loadDefaultSettings()

                if restartListener {
                    if defaults.bool(forKey: "UseHostNameForAETitle") {
                        self.setAETitleToHostname()
                    }
                }
            }
        } catch {
            NSLog("Exception updating prefs: %@", ObjC.arg(ObjC.exception(error)?.description))
        }
    }

    // Nonisolated: the defaults post their change on the thread that wrote
    // them. Only a change seen on the main thread schedules the check, as before.
    @objc(preferencesUpdated:) nonisolated func preferencesUpdated(_ note: Notification!) {
        if Thread.isMainThread == false { return }
        assumeMainActor(self) { $0.preferencesUpdatedOnMainActor() }
    }

    private func preferencesUpdatedOnMainActor() {
        if State.checkForPreferencesUpdate == false { return }

        if updateTimer != nil {
            updateTimer?.invalidate()
            updateTimer = nil
        }

        updateTimer = Timer.scheduledTimer(timeInterval: 0.5, target: self, selector: #selector(AppController.runPreferencesUpdateCheck(_:)), userInfo: nil, repeats: false)
    }

    @objc func testMenus() {
        #if DEBUG
        NSLog("Testing localization for menus")

        if self.viewerMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! viewerMenu")
        }

        if self.fileMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! fileMenu")
        }

        if self.wlwwMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! wlwwMenu")
        }

        if self.imageTilingMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! imageTilingMenu")
        }

        if self.orientationMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! orientationMenu")
        }

        if self.opacityMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! opacityMenu")
        }

        if self.convMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! convMenu")
        }

        if self.clutMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! clutMenu")
        }

        if self.workspaceMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! workspaceMenu")
        }

        if self.exportMenu() == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! exportMenu")
        }


        if self.viewerMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! viewerMenu Localized")
        }

        if self.fileMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! fileMenu Localized")
        }

        if self.wlwwMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! wlwwMenu Localized")
        }

        if self.imageTilingMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! imageTilingMenu Localized")
        }

        if self.orientationMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! orientationMenu Localized")
        }

        if self.opacityMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! opacityMenu Localized")
        }

        if self.convMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! convMenu Localized")
        }

        if self.clutMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! clutMenu Localized")
        }

        if self.workspaceMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! workspaceMenu Localized")
        }

        if self.exportMenuTestLocalized(true) == nil {
            NSLog("******* WARNING MENU MOVED / RENAMED ! exportMenu Localized")
        }

        #endif
    }

    @objc(viewerMenuTestLocalized:) func viewerMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: NSApp.mainMenu, identifier: "org.horos.menu.viewer")
    }

    @objc public func viewerMenu() -> NSMenu! {
        return self.viewerMenuTestLocalized(false)
    }

    @objc(fileMenuTestLocalized:) func fileMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: NSApp.mainMenu, identifier: "org.horos.menu.file")
    }

    @objc public func fileMenu() -> NSMenu! {
        return self.fileMenuTestLocalized(false)
    }

    @objc(exportMenuTestLocalized:) func exportMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.fileMenu(), identifier: "org.horos.menu.export")
    }

    @objc public func exportMenu() -> NSMenu! {
        return self.exportMenuTestLocalized(false)
    }

    @objc(imageTilingMenuTestLocalized:) func imageTilingMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.viewerMenu(), identifier: "org.horos.menu.image-tiling")
    }

    @objc public func imageTilingMenu() -> NSMenu! {
        return self.imageTilingMenuTestLocalized(false)
    }

    @objc(orientationMenuTestLocalized:) func orientationMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.viewerMenu(), identifier: "org.horos.menu.orientation")
    }

    @objc public func orientationMenu() -> NSMenu! {
        return self.orientationMenuTestLocalized(false)
    }

    @objc(opacityMenuTestLocalized:) func opacityMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.viewerMenu(), identifier: "org.horos.menu.opacity")
    }

    @objc public func opacityMenu() -> NSMenu! {
        return self.opacityMenuTestLocalized(false)
    }

    @objc(wlwwMenuTestLocalized:) func wlwwMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.viewerMenu(), identifier: "org.horos.menu.wlww")
    }

    @objc public func wlwwMenu() -> NSMenu! {
        return self.wlwwMenuTestLocalized(false)
    }

    @objc(convMenuTestLocalized:) func convMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.viewerMenu(), identifier: "org.horos.menu.convolution")
    }

    @objc public func convMenu() -> NSMenu! {
        return self.convMenuTestLocalized(false)
    }

    @objc(clutMenuTestLocalized:) func clutMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.viewerMenu(), identifier: "org.horos.menu.clut")
    }

    @objc public func clutMenu() -> NSMenu! {
        return self.clutMenuTestLocalized(false)
    }

    @objc(workspaceMenuTestLocalized:) func workspaceMenuTestLocalized(_ testLocalized: Bool) -> NSMenu! {
        // Resource identifiers remain stable when menu titles or positions change.
        _ = testLocalized
        return ApplicationMenuLookup.submenu(in: self.viewerMenu(), identifier: "org.horos.menu.workspace")
    }

    @objc public func workspaceMenu() -> NSMenu! {
        return self.workspaceMenuTestLocalized(false)
    }

    // Build the Load Workspace DICOM SR menu
    public func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()

        let studies = NSMutableArray()

        if BrowserController.currentBrowser()?.window?.isKeyWindow == true && BrowserController.currentBrowser()?.selectedStudy() != nil {
            if let selectedStudy = BrowserController.currentBrowser()?.selectedStudy() {
                studies.add(selectedStudy)
            }
        }

        if studies.count == 0 {
            for case let v as ViewerController in (ViewerController.getDisplayed2DViewers() ?? NSMutableArray()) {
                // [studies addObject: nil] raised in the former code; a nil study is not added here.
                if let currentStudy = v.currentStudy() {
                    if studies.contains(currentStudy) == false {
                        studies.add(currentStudy)
                    }
                }
            }
        }

        if studies.count != 0 {
            var index: Int32 = 1
            if let study = studies.object(at: 0) as? DicomStudy {

                for case let i as DicomImage in (study.allWindowsStateSRSeries() ?? NSArray()) {
                    do {
                        try HorosObjCException.perform {
                            let r: SRAnnotation? = SRAnnotation(contentsOfFile: i.completePathResolved())

                            let dataEncapsulated: Data? = r?.dataEncapsulated()
                            let viewers: NSArray? = dataEncapsulated.flatMap { try? PropertyListSerialization.propertyList(from: $0, options: [], format: nil) } as? NSArray

                            if let viewers = viewers, viewers.count != 0 {
                                var name = (viewers.lastObject as? NSDictionary)?.object(forKey: "name") as? String

                                if ((name as NSString?)?.length ?? 0) == 0 {
                                    if (viewers.lastObject as? NSDictionary)?.object(forKey: "date") != nil {
                                        name = UserDefaults.formatDateTime((viewers.lastObject as? NSDictionary)?.object(forKey: "date") as? Date)
                                    } else {
                                        name = NSLocalizedString("State", comment: "")
                                        name = (name ?? "").appendingFormat(" %d", index)
                                        index += 1
                                    }
                                }

                                let mi = NSMenuItem(title: name ?? "", action: #selector(AppController.loadWindowsStateDICOMSR(_:)), keyEquivalent: "")

                                mi.representedObject = NSDictionary(objects: [study, viewers], forKeys: ["study" as NSString, "windowsState" as NSString])
                                mi.target = self

                                menu.addItem(mi)
                            }
                        }
                    } catch {
                        if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, false, "-[AppController menuNeedsUpdate:]") }
                    }
                }
            }
        }

        if menu.numberOfItems == 0 {
            menu.addItem(withTitle: NSLocalizedString("No saved state", comment: ""), action: nil, keyEquivalent: "")
        }

        return
    }

    @objc(loadWindowsStateDICOMSR:) func loadWindowsStateDICOMSR(_ menuItem: NSMenuItem!) {
        let study = (menuItem?.representedObject as? NSDictionary)?.object(forKey: "study") as? DicomStudy
        let state = (menuItem?.representedObject as? NSDictionary)?.object(forKey: "windowsState") as? NSArray

        let windowsState: Data? = state.flatMap { try? PropertyListSerialization.data(fromPropertyList: $0, format: .xml, options: 0) }

        if let study = study, let windowsState = windowsState {
            // Replace the current windows state of the study, with the content of the DICOM SR
            study.setValue(windowsState, forKey: "windowsState")

            let c = UserDefaults.standard.bool(forKey: "automaticWorkspaceLoad")

            if c == false { UserDefaults.standard.set(true, forKey: "automaticWorkspaceLoad") }

            BrowserController.currentBrowser()?.databaseOpenStudy(study)

            if c == false { UserDefaults.standard.set(c, forKey: "automaticWorkspaceLoad") }
        }
    }

    @objc(UpdateOpacityMenu:) func UpdateOpacityMenu(_ note: Notification!) {
        //*** Build the menu
        var i: Int16
        let keys: NSArray
        let sortedKeys: NSArray

        if State.mainOpacityMenu == nil {
            State.mainOpacityMenu = self.opacityMenu()
        }

        // dictionaryForKey: answers the object objectForKey: answers when it is a dictionary; the test compares the pointers.
        if (UserDefaults.standard.object(forKey: "OPACITY") as? NSDictionary) !== State.previousOpacityKeys {
            State.previousOpacityKeys = UserDefaults.standard.object(forKey: "OPACITY") as? NSDictionary
            keys = (State.previousOpacityKeys?.allKeys ?? []) as NSArray

            sortedKeys = keys.sortedArray(using: #selector(NSString.caseInsensitiveCompare(_:))) as NSArray

            State.mainOpacityMenu?.removeAllItems()

            State.mainOpacityMenu?.addItem(withTitle: NSLocalizedString("Linear Table", comment: ""), action: NSSelectorFromString("ApplyOpacity:"), keyEquivalent: "")
            i = 0
            while Int(i) < sortedKeys.count {
                State.mainOpacityMenu?.addItem(withTitle: (sortedKeys.object(at: Int(i)) as? String) ?? "", action: NSSelectorFromString("ApplyOpacity:"), keyEquivalent: "")
                i += 1
            }
            State.mainOpacityMenu?.addItem(NSMenuItem.separator())
            State.mainOpacityMenu?.addItem(withTitle: NSLocalizedString("Add an Opacity Table", comment: ""), action: NSSelectorFromString("AddOpacity:"), keyEquivalent: "")
        }
    }

    @objc(UpdateWLWWMenu:) func UpdateWLWWMenu(_ note: Notification!) {
        //*** Build the menu
        var i: Int16
        let keys: NSArray
        let sortedKeys: NSArray

        if State.mainMenuWLWWMenu == nil {
            State.mainMenuWLWWMenu = self.wlwwMenu()
        }

        if (UserDefaults.standard.object(forKey: "WLWW3") as? NSDictionary) !== State.previousWLWWKeys {
            State.previousWLWWKeys = UserDefaults.standard.object(forKey: "WLWW3") as? NSDictionary
            keys = (State.previousWLWWKeys?.allKeys ?? []) as NSArray

            sortedKeys = keys.sortedArray(using: #selector(NSString.caseInsensitiveCompare(_:))) as NSArray

            State.mainMenuWLWWMenu?.removeAllItems()

            State.mainMenuWLWWMenu?.addItem(withTitle: NSLocalizedString("Default WL & WW", comment: ""), action: NSSelectorFromString("ApplyWLWW:"), keyEquivalent: "l")
            State.mainMenuWLWWMenu?.addItem(withTitle: NSLocalizedString("Other", comment: ""), action: NSSelectorFromString("ApplyWLWW:"), keyEquivalent: "")
            State.mainMenuWLWWMenu?.addItem(withTitle: NSLocalizedString("Full dynamic", comment: ""), action: NSSelectorFromString("ApplyWLWW:"), keyEquivalent: "y")

            State.mainMenuWLWWMenu?.addItem(NSMenuItem.separator())

            i = 0
            while Int(i) < sortedKeys.count {
                State.mainMenuWLWWMenu?.addItem(withTitle: String(format: "%d - %@", Int32(i) + 1, ObjC.arg(sortedKeys.object(at: Int(i)))), action: NSSelectorFromString("ApplyWLWW:"), keyEquivalent: "")
                i += 1
            }
            State.mainMenuWLWWMenu?.addItem(NSMenuItem.separator())
            State.mainMenuWLWWMenu?.addItem(withTitle: NSLocalizedString("Add Current WL/WW", comment: ""), action: NSSelectorFromString("AddCurrentWLWW:"), keyEquivalent: "")
            // This opened the preset-naming sheet, the same one as the item above it,
            // so setting a window without saving it as a preset was reachable only
            // from the viewer's own pop-up menu, which wires it correctly.
            State.mainMenuWLWWMenu?.addItem(withTitle: NSLocalizedString("Set WL/WW manually", comment: ""), action: NSSelectorFromString("SetWLWW:"), keyEquivalent: "")
        }
    }

    @objc(UpdateConvolutionMenu:) func UpdateConvolutionMenu(_ note: Notification!) {
        //*** Build the menu
        var i: Int16
        let keys: NSArray
        let sortedKeys: NSArray

        if State.mainMenuConvMenu == nil {
            State.mainMenuConvMenu = self.convMenu()
        }

        if (UserDefaults.standard.object(forKey: "Convolution") as? NSDictionary) !== State.previousConvKeys {
            State.previousConvKeys = UserDefaults.standard.object(forKey: "Convolution") as? NSDictionary
            keys = (State.previousConvKeys?.allKeys ?? []) as NSArray

            sortedKeys = keys.sortedArray(using: #selector(NSString.caseInsensitiveCompare(_:))) as NSArray

            State.mainMenuConvMenu?.removeAllItems()

            State.mainMenuConvMenu?.addItem(withTitle: NSLocalizedString("No Filter", comment: ""), action: NSSelectorFromString("ApplyConv:"), keyEquivalent: "")

            State.mainMenuConvMenu?.addItem(NSMenuItem.separator())

            i = 0
            while Int(i) < sortedKeys.count {
                State.mainMenuConvMenu?.addItem(withTitle: (sortedKeys.object(at: Int(i)) as? String) ?? "", action: NSSelectorFromString("ApplyConv:"), keyEquivalent: "")
                i += 1
            }
            State.mainMenuConvMenu?.addItem(NSMenuItem.separator())
            State.mainMenuConvMenu?.addItem(withTitle: NSLocalizedString("Add a Filter", comment: ""), action: NSSelectorFromString("AddConv:"), keyEquivalent: "")
        }
    }

    @objc(UpdateCLUTMenu:) func UpdateCLUTMenu(_ note: Notification!) {
        //*** Build the menu
        var i: Int16
        let keys: NSArray
        let sortedKeys: NSArray

        if State.mainMenuCLUTMenu == nil {
            State.mainMenuCLUTMenu = self.clutMenu()
        }

        if (UserDefaults.standard.object(forKey: "CLUT") as? NSDictionary) !== State.previousCLUTKeys {
            State.previousCLUTKeys = UserDefaults.standard.object(forKey: "CLUT") as? NSDictionary
            keys = (State.previousCLUTKeys?.allKeys ?? []) as NSArray

            sortedKeys = keys.sortedArray(using: #selector(NSString.caseInsensitiveCompare(_:))) as NSArray

            State.mainMenuCLUTMenu?.removeAllItems()

            State.mainMenuCLUTMenu?.addItem(withTitle: NSLocalizedString("No CLUT", comment: ""), action: NSSelectorFromString("ApplyCLUT:"), keyEquivalent: "")

            State.mainMenuCLUTMenu?.addItem(NSMenuItem.separator())

            i = 0
            while Int(i) < sortedKeys.count {
                State.mainMenuCLUTMenu?.addItem(withTitle: (sortedKeys.object(at: Int(i)) as? String) ?? "", action: NSSelectorFromString("ApplyCLUT:"), keyEquivalent: "")
                i += 1
            }
            State.mainMenuCLUTMenu?.addItem(NSMenuItem.separator())
            State.mainMenuCLUTMenu?.addItem(withTitle: NSLocalizedString("Add a CLUT", comment: ""), action: NSSelectorFromString("AddCLUT:"), keyEquivalent: "")
        }
    }

    @objc(startDICOMBonjour:) func startDICOMBonjour(_ t: Timer!) {
        NSLog("startDICOMBonjour")

        BonjourDICOMService = NetService(domain: "", type: "_dicom._tcp.", name: UserDefaults.standard.string(forKey: "AETITLE") ?? "", port: ObjC.int(UserDefaults.standard.string(forKey: "AEPORT")))

        let description: String? = UserDefaults.bonjourSharingName()
        let dict = NSMutableDictionary()

        if let description = description, (description as NSString).length > 0 {
            dict.setValue(description, forKey: "serverDescription")
        }

        dict.setValue(UserDefaults.standard.string(forKey: "AETITLE"), forKey: "AETitle")
        dict.setValue(AppController.uid(), forKey: "UID")

        if UserDefaults.standard.bool(forKey: "activateCGETSCP") {
            dict.setValue("YES", forKey: "CGET") // TXTRECORD doesnt support NSNumber
        } else {
            dict.setValue("NO", forKey: "CGET")  // TXTRECORD doesnt support NSNumber
        }

        if UserDefaults.standard.bool(forKey: "httpWebServer") && UserDefaults.standard.bool(forKey: "wadoServer") {
            let port = Int32(truncatingIfNeeded: UserDefaults.webPortalPortNumber())
            dict.setValue("YES", forKey: "WADO") // TXTRECORD doesnt support NSNumber
            dict.setValue(String(format: "%d", port), forKey: "WADOPort")
            dict.setValue("/wado", forKey: "WADOURL")

            if UserDefaults.standard.bool(forKey: "encryptedWebServer") {
                dict.setValue("https", forKey: "WADOProtocol")
            } else {
                dict.setValue("http", forKey: "WADOProtocol")
            }
        }

        switch UserDefaults.standard.integer(forKey: "preferredSyntaxForIncoming") {
        case 0:
            dict.setValue("LittleEndianImplicit", forKey: "preferredSyntax")
        case 21:
            dict.setValue("JPEGProcess14SV1TransferSyntax", forKey: "preferredSyntax")
        case 26:
            dict.setValue("JPEG2000LosslessOnly", forKey: "preferredSyntax")
        case 27:
            dict.setValue("JPEG2000", forKey: "preferredSyntax")
        case 22:
            dict.setValue("RLELossless", forKey: "preferredSyntax")
        case 23:
            dict.setValue("JPEGLSLossless", forKey: "preferredSyntax")
        case 24:
            dict.setValue("JPEGLSLossy", forKey: "preferredSyntax")
        default:
            dict.setValue("LittleEndianExplicit", forKey: "preferredSyntax")
        }

        // The values are strings: Swift's data(fromTXTRecord:) takes [String: Data], so the same message is sent to the class.
        let txtRecordData = (NetService.self as AnyObject).perform(NSSelectorFromString("dataFromTXTRecordDictionary:"), with: dict)?.takeUnretainedValue() as? Data
        BonjourDICOMService?.setTXTRecord(txtRecordData)

        BonjourDICOMService?.delegate = self
        BonjourDICOMService?.publish()

        (DCMNetServiceDelegate.sharedNetServiceDelegate() as? DCMNetServiceDelegate)?.setPublisher(BonjourDICOMService)
    }


    // MARK: -

    @objc public func restartSTORESCP() {
        NSLog("restartSTORESCP")

        // Is called restart because previous instances of storescp might exist and need to be killed before starting
        // This should be performed only if Horos is to handle storescp, depending on what is defined in the preferences
        // Key:@"STORESCP" is the corresponding switch

        let BUILTIN_DCMTK = true // #define BUILTIN_DCMTK YES of the former file

        do {
            try HorosObjCException.perform {
                quitting = true

                // The Built-In StoreSCP is now the default and only storescp available in Horos.... Antoine 4/9/06
                if UserDefaults.standard.bool(forKey: "USESTORESCP") != true {
                    UserDefaults.standard.set(true, forKey: "USESTORESCP")
                }

                if UserDefaults.standard.bool(forKey: "STORESCP") {
                    // Kill DCMTK listener
                    // built in dcmtk serve testing
                    if BUILTIN_DCMTK == true {
                        AppController.listenerLock.withLock { dcmtkQRSCP = nil }
                    } else {
                        NSLog("********* WARNING - WE SHOULD NOT BE HERE - STORE-SCP")

                        let theArguments = NSMutableArray()
                        var aTask: Process? = Process()
                        aTask?.launchPath = "/usr/bin/killall"
                        theArguments.add("storescp")
                        aTask?.arguments = theArguments as? [String]
                        aTask?.launch()
                        while aTask?.isRunning == true { Thread.sleep(forTimeInterval: 0.01) }
                        aTask?.interrupt()
                        aTask = nil
                    }

                    //make sure that there exist a receiver folder at @"folder" path
                    let path = DicomDatabase.activeLocal()?.incomingDirPath()
                    FileManager.default.confirmNoIndexDirectory(atPath: path)

                    if UserDefaults.standard.bool(forKey: "USESTORESCP") {
                        if STORESCP?.try() == true {
                            Thread.detachNewThreadSelector(#selector(AppController.startSTORESCP(_:)), toTarget: self, with: self)

                            STORESCP?.unlock()
                        } else {
                            HorosAlertPanel.runCritical(title: NSLocalizedString("DICOM Listener Error", comment: ""), message: NSLocalizedString("Cannot start DICOM Listener. Another thread is already running. Restart Isis DICOM Viewer.", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
                        }
                    }
                }

                if UserDefaults.standard.bool(forKey: "STORESCPTLS") {
                    AppController.listenerLock.withLock { dcmtkQRSCPTLS = nil }

                    //make sure that there exist a receiver folder at @"folder" path
                    let path = DicomDatabase.activeLocal()?.incomingDirPath()
                    FileManager.default.confirmNoIndexDirectory(atPath: path)

                    if STORESCPTLS?.try() == true {
                        Thread.detachNewThreadSelector(#selector(AppController.startSTORESCPTLS(_:)), toTarget: self, with: self)

                        STORESCPTLS?.unlock()
                    } else {
                        HorosAlertPanel.runCritical(title: NSLocalizedString("DICOM TLS Listener Error", comment: ""), message: NSLocalizedString("Cannot start DICOM TLS Listener. Another thread is already running. Restart Isis DICOM Viewer.", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
                    }
                }
            }
        } catch {
            let e = ObjC.exception(error)
            if let e = e { _N2LogExceptionImpl(e, true, "-[AppController restartSTORESCP]") }

            if Thread.isMainThread {
                HorosAlertPanel.run(title: NSLocalizedString("Database", comment: ""), message: ObjC.format("%@", e?.reason), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
            }
        }

        BonjourDICOMService?.stop()
        BonjourDICOMService = nil

        if UserDefaults.standard.bool(forKey: "publishDICOMBonjour") {
            //Start DICOM Bonjour
            Timer.scheduledTimer(timeInterval: 5, target: self, selector: #selector(AppController.startDICOMBonjour(_:)), userInfo: nil, repeats: false)
        }
    }

    @objc(displayError:) public func displayError(_ err: String!) {
        HorosAlertPanel.runCritical(title: NSLocalizedString("Error", comment: ""), message: ObjC.format("%@", err), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
    }

    @objc(reportListenBindFailureForService:port:errnoCode:) nonisolated public func reportListenBindFailure(forService service: String!, port: Int, errnoCode code: Int32) {
        // A nil service reached the Swift ListenBindFailure methods as "".
        let line = ListenBindFailure.logLine(service: service ?? "", port: port, errno: code)
        NSLog("%@", line as NSString)
        let hideDICOM = (service?.hasPrefix("DICOM") ?? false)
            && UserDefaults.standard.bool(forKey: "hideListenerError")
        if hideDICOM {
            return
        }
        if !ListenBindFailure.consumeUserNotice(service: service ?? "", port: port) {
            return
        }
        let message = (service == ListenBindFailure.webPortalService)
            ? ListenBindFailure.webPortalUserMessage(port: port)
            : ListenBindFailure.userMessage(service: service ?? "", port: port, errno: code)
        ListenBindFailure.presentUserNotice(message)
    }

    // the DiscPublishing plugin swizzles this method, do not rename it
    // (dynamic: a call from Swift also goes through the Objective-C runtime, as the swizzling expects)
    @objc(displayListenerError:) dynamic func displayListenerError(_ err: String!) {
        NSLog("*** listener error (displayListenerError): %@", ObjC.arg(err))

        // Said in the notices panel: a sheet held the database window until it was
        // dismissed, once per failed association (#691).
        if UserDefaults.standard.bool(forKey: "hideListenerError") == false {
            NetworkNotices.post(title: NSLocalizedString("DICOM Listener Error", comment: ""), message: err ?? "")
        }
    }

    /// Guards dcmtkQRSCP and dcmtkQRSCPTLS: each listener thread sets its own,
    /// and the main thread reads, aborts and clears them (#1005). Held only to
    /// read or write the two variables, never while a listener runs.
    nonisolated static let listenerLock = NSLock()

    /// dcmtkQRSCP and dcmtkQRSCPTLS as they are now.
    nonisolated static func listeners() -> (plain: DCMTKQueryRetrieveSCP?, tls: DCMTKQueryRetrieveSCP?) {
        listenerLock.withLock { (dcmtkQRSCP, dcmtkQRSCPTLS) }
    }

    @objc(startSTORESCP:) nonisolated public func startSTORESCP(_ sender: Any!) {
        // this method is always executed as a new thread detached from the NSthread command of RestartSTORESCP method

        STORESCP?.lock()

        Thread.current.name = "DICOM Store-SCP"

        do {
            try HorosObjCException.perform {


                if UserDefaults.standard.bool(forKey: "UseHostNameForAETitle") {
                    self.setAETitleToHostname()
                }

                // Until it is stored, AETITLE is a registered default computed from the
                // computer's name at every launch - so renaming the Mac renames the
                // listener, and the remote nodes configured with the old title stop
                // being able to send to it. Nothing said so. Store it the first time,
                // so what the listener answers to is a value the user can see and keep.
                if Bundle.main.bundleIdentifier.flatMap({ UserDefaults.standard.persistentDomain(forName: $0) })?["AETITLE"] == nil {
                    let derived = UserDefaults.standard.string(forKey: "AETITLE")
                    if let derived = derived, (derived as NSString).length != 0 {
                        UserDefaults.standard.set(derived, forKey: "AETITLE")
                        NSLog("--- DICOM listener AE title was not stored; it is now \"%@\", taken from this computer's name. It will no longer change if the computer is renamed.", derived as NSString)
                    }
                }

                var c = UserDefaults.standard.string(forKey: "AETITLE").map { $0 as NSString }
                if (c?.length ?? 0) > 16 {
                    c = (c?.substring(to: 16)).map { $0 as NSString }
                    UserDefaults.standard.set(c, forKey: "AETITLE")
                }

                let aeTitle = UserDefaults.standard.string(forKey: "AETITLE")
                let port = ObjC.int(UserDefaults.standard.string(forKey: "AEPORT"))
                let params: [AnyHashable: Any] = ["TLSEnabled": NSNumber(value: false)]

                let listener = DCMTKQueryRetrieveSCP(port: port, aeTitle: aeTitle, extraParamaters: params)
                AppController.listenerLock.withLock { dcmtkQRSCP = listener }

                listener?.run()
            }
        } catch {
            if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, true, "-[AppController startSTORESCP:]") }
        }

        STORESCP?.unlock()

        return
    }

    @objc(startSTORESCPTLS:) nonisolated public func startSTORESCPTLS(_ sender: Any!) {
        // this method is always executed as a new thread detached from the NSthread command of RestartSTORESCP method
        Thread.current.name = "DICOM Store-SCP TLS"

        if UserDefaults.standard.bool(forKey: "STORESCPTLS") {
            STORESCPTLS?.lock()

            do {
                try HorosObjCException.perform {
                    var c = UserDefaults.standard.string(forKey: "TLSStoreSCPAETITLE").map { $0 as NSString }
                    if (c?.length ?? 0) > 16 {
                        c = (c?.substring(to: 16)).map { $0 as NSString }
                        UserDefaults.standard.set(c, forKey: "TLSStoreSCPAETITLE")
                    }

                    let aeTitle = UserDefaults.standard.string(forKey: "TLSStoreSCPAETITLE")
                    let port = ObjC.int(UserDefaults.standard.string(forKey: "TLSStoreSCPAEPORT"))
                    let params: [AnyHashable: Any] = ["TLSEnabled": NSNumber(value: true)]

                    let listener = DCMTKQueryRetrieveSCP(port: port, aeTitle: aeTitle, extraParamaters: params)
                    AppController.listenerLock.withLock { dcmtkQRSCPTLS = listener }
                    listener?.run()
                }
            } catch {
                if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, true, "-[AppController startSTORESCPTLS:]") }
            }

            STORESCPTLS?.unlock()
        }
        return
    }

    // Manage osirix URL : osirix://
    // Parsing lives in HorosSchemeURL so a Chrome 94+ protocol block and a missing
    // StudyInstanceUID are not the same diagnosis. LaunchServices is not rewritten
    // here; the scheme is already in Info.plist.

    @objc(getUrl:withReplyEvent:) func getUrl(_ event: NSAppleEventDescriptor!, withReplyEvent replyEvent: NSAppleEventDescriptor!) {
        let str = event?.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue
        if HorosSchemeURL.consumeDuplicate(str ?? "") {
            NSLog("horos URL ignored duplicate within 1s")
            return
        }

        let parsed = HorosSchemeURL.parse(str ?? "")

        if parsed.layer == "parser" {
            let fallback = str.flatMap { NSURL(string: $0) }
            if parsed.invocation == nil && fallback?.pathExtension == "xml" {
                BrowserController.asyncWADOXMLDownloadURL(fallback as URL?)
                return
            }
            NSLog("horos URL parser (%@): %@", parsed.code as NSString, parsed.message as NSString)
            return
        }

        guard let invocation = parsed.invocation else {
            return
        }

        if UserDefaults.standard.bool(forKey: "httpXMLRPCServer") == false {
            let result = HorosAlertPanel.runInformational(title: NSLocalizedString("URL scheme", comment: ""), message: NSLocalizedString("Isis DICOM Viewer URL scheme [horos:// , osirix://] is currently not activated!\r\rShould I activate it now? Restart is necessary.", comment: ""), defaultButton: NSLocalizedString("No", comment: ""), alternateButton: NSLocalizedString("Activate & Restart", comment: ""), otherButton: nil)

            if result == HorosAlertPanel.alternateResponse {
                UserDefaults.standard.set(true, forKey: "httpXMLRPCServer")
                UserDefaults.standard.synchronize()
                NSApplication.shared.terminate(self)
            }
        }

        if let methodName = invocation.methodName, (methodName as NSString).length > 0 {
            let paramDict = NSMutableDictionary(dictionary: invocation.parameters)
            _ = try? xmlrpcServer?.methodCall(methodName, parameters: paramDict as? [AnyHashable: Any])
            return
        }

        if let imageSpecifier = invocation.imageSpecifier, (imageSpecifier as NSString).length > 0 {
            let components = (imageSpecifier as NSString).components(separatedBy: "+") as NSArray

            if components.count == 2 {
                let sopclassuid = components.object(at: 0) as! String
                let sopinstanceuid = components.object(at: 1) as! String
                var succeeded = false
                BrowserController.currentBrowser()?.lastStudyNotOpenedReason = nil

                //First try to find it in the selected study
                if succeeded == false {
                    let allImages = NSMutableArray()
                    _ = BrowserController.currentBrowser()?.files(forDatabaseOutlineSelection: allImages)

                    let context = BrowserController.currentBrowser()?.database?.managedObjectContext

                    N2ManagedObjectContextPerformAndWait(context) {

                    do {
                        try HorosObjCException.perform {
                            let request = NSComparisonPredicate(leftExpression: NSExpression(forKeyPath: "compressedSopInstanceUID"), rightExpression: NSExpression(forConstantValue: DicomImage.sopInstanceUIDEncode(sopinstanceuid)), customSelector: NSSelectorFromString("isEqualToSopInstanceUID:"))

                            let imagesArray = allImages.filtered(using: request) as NSArray

                            if imagesArray.count > 0 {
                                // A refusal here used to be recorded as a success: the link
                                // was answered, no viewer appeared, and the second search
                                // below was skipped because of it.
                                succeeded = BrowserController.currentBrowser()?.display((imagesArray.lastObject as AnyObject?)?.value(forKeyPath: "series.study") as? DicomStudy, object: imagesArray.lastObject as? NSManagedObject, command: "Open") ?? false
                            }
                        }
                    } catch {
                        if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, true, "-[AppController getUrl:withReplyEvent:]") }
                    }

                    }
                }
                //Second option, try to find the uid in the ENTIRE db....

                if succeeded == false {
                    let dbRequest = NSFetchRequest<NSFetchRequestResult>()
                    dbRequest.entity = BrowserController.currentBrowser()?.database?.seriesEntity()
                    dbRequest.predicate = NSPredicate(format: "seriesSOPClassUID == %@", sopclassuid as NSString)

                    let context = BrowserController.currentBrowser()?.database?.managedObjectContext

                    N2ManagedObjectContextPerformAndWait(context) {

                    let wait = WaitRendering(NSLocalizedString("Locating the image in the database...", comment: ""))
                    wait?.showWindow(self)
                    wait?.setCancel(true)
                    wait?.start()

                    do {
                        try HorosObjCException.perform {
                            // (NSError *error: the Swift fetch throws instead; a failed fetch answers nil as before)
                            let allSeries = ((try? context?.fetch(dbRequest)) as NSArray?)?.value(forKey: "images") as? NSArray

                            let allImages = NSMutableArray()
                            for s in allSeries ?? NSArray() {
                                allImages.addObjects(from: (s as? NSSet)?.allObjects ?? [])
                            }

                            let searchedUID = DicomImage.sopInstanceUIDEncode(sopinstanceuid)
                            var searchUIDImage: DicomImage? = nil

                            for case let i as DicomImage in allImages {
                                if (i.value(forKey: "compressedSopInstanceUID") as? NSData)?.isEqual(toSopInstanceUID: searchedUID) ?? false {
                                    searchUIDImage = i
                                }

                                if searchUIDImage != nil {
                                    break
                                }

                                if wait?.run() == false {
                                    break
                                }
                            }

                            if let searchUIDImage = searchUIDImage {
                                succeeded = BrowserController.currentBrowser()?.display(searchUIDImage.value(forKeyPath: "series.study") as? DicomStudy, object: searchUIDImage, command: "Open") ?? false
                            }
                        }
                    } catch {
                        if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, true, "-[AppController getUrl:withReplyEvent:]") }
                    }
                    wait?.end()
                    wait?.close()

                    }
                }

                // Somebody clicked a link and is waiting on a viewer. Saying
                // nothing at all is what made "the viewer never opened" a
                // report with nothing in it.
                if succeeded == false {
                    var reason = BrowserController.currentBrowser()?.lastStudyNotOpenedReason
                    if ((reason as NSString?)?.length ?? 0) == 0 {
                        reason = StudyNotOpenedReason.reasonForNoStudy()
                    }

                    // One line that is complete on its own: nothing matched here,
                    // so the browser may never have been asked and may have logged
                    // nothing.
                    NSLog("%@%@ - the link asked for image %@", StudyNotOpenedReason.logPrefix() as NSString, ObjC.arg(reason), sopinstanceuid as NSString)
                    _ = HorosAlertPanel.run(title: NSLocalizedString("Open Image", comment: ""), message: reason ?? "", defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
                }
            }
        }
    }

    @objc(application:openFiles:) func application(_ sender: NSApplication!, openFiles filenames: [Any]!) {
        let filenames = (filenames as NSArray?) ?? NSArray()

        if filenames.count == 1 { // for iChat Theatre... (drag & drop a DICOM file on the video chat window)
            for case let v as ViewerController in ViewerController.getDisplayed2DViewers() ?? NSMutableArray() {
                for im in v.fileList() ?? NSMutableArray() {
                    if let imPath = (im as? NSObject)?.perform(NSSelectorFromString("path"))?.takeUnretainedValue() as? NSString,
                       let first = filenames.object(at: 0) as? String,
                       imPath.isEqual(to: first) {
                        v.window?.makeKey()
                        return
                    }
                }
            }
        }

        // exclude --LoadPlugin arguments
        let passedFilenames = NSMutableArray()
        let args = ProcessInfo.processInfo.arguments as NSArray
        for path in filenames {
            var isLoadPlugin = false
            var i = 0
            while !isLoadPlugin && i < args.count - 1 {
                if ((args.object(at: i) as? NSString)?.isEqual(to: "--LoadPlugin") ?? false) {
                    if let path = path as? String, (args.object(at: i + 1) as? NSString)?.isEqual(to: path) ?? false {
                        isLoadPlugin = true
                    }
                }
                i += 1
            }
            if !isLoadPlugin {
                passedFilenames.add(path)
            }
        }

        BrowserController.currentBrowser()?.subSelectFilesAndFolders(toAdd: passedFilenames as? [Any])
    }

    @objc(applicationWillBecomeActive:) func applicationWillBecomeActive(_ aNotification: Notification!) {
        if State.firstCall {
            return
        }

        NSRunningApplication.current.activate(options: .activateAllWindows)
    }

    @objc(applicationDidBecomeActive:) func applicationDidBecomeActive(_ aNotification: Notification!) {
        if State.firstCall {
            State.firstCall = false
            return
        }

        BrowserController.currentBrowser()?.syncReportsIfNecessary()

        if UserDefaults.standard.bool(forKey: "hideListenerError") == false { // Server mode
            if (BrowserController.currentBrowser()?.window?.isMiniaturized ?? false) == true || (BrowserController.currentBrowser()?.window?.isVisible ?? false) == false {
                let winList = NSApp.windows

                for loopItem in winList {
                    if loopItem.windowController is ViewerController { return }
                }

                BrowserController.currentBrowser()?.window?.makeKeyAndOrderFront(self)
            }
        }
    }

    @objc(applicationShouldHandleReopen:hasVisibleWindows:) func applicationShouldHandleReopen(_ theApplication: NSApplication!, hasVisibleWindows flag: Bool) -> Bool {
        if UserDefaults.standard.bool(forKey: "hideListenerError") { // Server mode
            return true
        }

        if flag == false {
            BrowserController.currentBrowser()?.window?.makeKeyAndOrderFront(self)
        }

        return true
    }

    @IBAction @objc(killAllStoreSCU:) public func killAllStoreSCU(_ sender: Any!) {
        let wait = WaitRendering(NSLocalizedString("Abort Incoming DICOM processes...", comment: ""))
        wait?.showWindow(self)

        let persistListenerMode = !UserDefaults.standard.hasArgumentOverride(forKey: "hideListenerError")
        let hideListenerError_copy = UserDefaults.standard.bool(forKey: "hideListenerError")
        if persistListenerMode {
            UserDefaults.standard.set(hideListenerError_copy, forKey: "copyHideListenerError")
            UserDefaults.standard.set(true, forKey: "hideListenerError")
            UserDefaults.standard.synchronize()
        }

        _ = HorosDICOMGlobalAbortBegin()
        RunLoop.current.run(until: Date(timeIntervalSinceNow: 3))

        wait?.close()

        HorosDICOMGlobalAbortEnd()

        if persistListenerMode {
            UserDefaults.standard.set(hideListenerError_copy, forKey: "hideListenerError")
            UserDefaults.standard.removeObject(forKey: "copyHideListenerError")
            UserDefaults.standard.synchronize()
        }
    }

    @objc(applicationWillTerminate:) func applicationWillTerminate(_ aNotification: Notification!) {

        DICOMTLS.eraseKeys()

    //	[webServer release];
    //	webServer = nil;

        xmlrpcServer = nil

        self.closeAllViewers(self)

        for t in ThreadsManager.default()?.threads() ?? NSArray() {
            (t as? Thread)?.cancel()
        }

        BrowserController.currentBrowser()?.browserPrepareForClose()

        WebPortal.finalizeWebPortalClass()

        ROI.saveDefaultSettings()

        BonjourDICOMService?.stop()
        BonjourDICOMService = nil

        quitting = true


        AppControllerCAPIDestroyDCMTK(self)

        AppController.cleanOsiriXSubProcesses()

        // DELETE THE DUMP DIRECTORY...
        let dumpDirectory = DicomDatabase.activeLocal()?.dumpDirPath()
        if FileManager.default.fileExists(atPath: dumpDirectory ?? "") {
            try? FileManager.default.removeItem(atPath: dumpDirectory ?? "")
        }
        if FileManager.default.fileExists(atPath: dumpDirectory ?? "") {
            FileManager.default.moveItemAtPath(toTrash: dumpDirectory)
        }
        if FileManager.default.fileExists(atPath: dumpDirectory ?? "") {
            NSLog("******** FAILED to clean the dumpDirectory directory: %@", ObjC.arg(dumpDirectory))
        }

        let tempDirectory = DicomDatabase.activeLocal()?.tempDirPath()
        let decompressionDirectory = DicomDatabase.activeLocal()?.decompressionDirPath()

        if !UserDefaults.standard.bool(forKey: "DoNotEmptyIncomingDir") { // not DoNot -> delete files
            // DELETE the content of TEMP.noindex directory...
            if FileManager.default.fileExists(atPath: tempDirectory ?? "") {
                try? FileManager.default.removeItem(atPath: tempDirectory ?? "")
            }
            if FileManager.default.fileExists(atPath: tempDirectory ?? "") {
                FileManager.default.moveItemAtPath(toTrash: tempDirectory)
            }
            if FileManager.default.fileExists(atPath: tempDirectory ?? "") {
                NSLog("******** FAILED to clean the tempDirectory directory: %@", ObjC.arg(tempDirectory))
            }

            // DELETE THE DECOMPRESSION.noindex DIRECTORY...
            if FileManager.default.fileExists(atPath: decompressionDirectory ?? "") {
                try? FileManager.default.removeItem(atPath: decompressionDirectory ?? "")
            }
            if FileManager.default.fileExists(atPath: decompressionDirectory ?? "") {
                FileManager.default.moveItemAtPath(toTrash: decompressionDirectory)
            }
            if FileManager.default.fileExists(atPath: decompressionDirectory ?? "") {
                NSLog("******** FAILED to clean the decompressionDirectory directory: %@", ObjC.arg(decompressionDirectory))
            }
        }

        // Delete all process_state files
        let processFolder = String(cString: HorosDICOMProcessFolder())
        for s in (try? FileManager.default.contentsOfDirectory(atPath: processFolder)) ?? [] {
            if (s as NSString).hasPrefix("process_state-") {
                try? FileManager.default.removeItem(atPath: (processFolder as NSString).appendingPathComponent(s))
            }
        }

        try? FileManager.default.removeItem(atPath: (FileManager.default.tmpDirPath() as NSString).appendingPathComponent("zippedCD"))

        let tmpDirPath = FileManager.default.tmpDirPath()
        if FileManager.default.fileExists(atPath: tmpDirPath) {
            try? FileManager.default.removeItem(atPath: tmpDirPath)
        }
        if FileManager.default.fileExists(atPath: tmpDirPath) {
            FileManager.default.moveItemAtPath(toTrash: tmpDirPath)
        }
        if FileManager.default.fileExists(atPath: tmpDirPath) {
            NSLog("******** FAILED to clean the tmpDirPath directory: %@", tmpDirPath as NSString)
        }

        // EMPTY THE INCOMING.noindex DIRECTORY... into the Trash: what is still there
        // was received and never imported, so it stays recoverable (#629).
        let incomingDirectoryPath = DicomDatabase.activeLocal()?.incomingDirPath()
        if FileManager.default.fileExists(atPath: incomingDirectoryPath ?? "") && !UserDefaults.standard.bool(forKey: "DoNotEmptyIncomingDir") {
            do {
                try IncomingFolderOnQuit.sendToTrashIfPending(incomingDirectoryPath ?? "", resultingPath: nil)
            } catch let incomingError {
                NSLog("******** FAILED to clean the INCOMING.noindex directory: %@ (%@)", ObjC.arg(incomingDirectoryPath), incomingError.localizedDescription as NSString)
            }
        }

        _ = FileManager.default.confirmDirectory(atPath: incomingDirectoryPath)
    }

    @IBAction @objc(terminate:) public func terminate(_ sender: Any!) {
        if (BrowserController.currentBrowser()?.shouldTerminate(sender) ?? false) == false { return }
        finishTermination(sender)
    }

    /// The rest of quitting, once the browser has agreed to it.
    func finishTermination(_ sender: Any!) {
        UserDefaults.standard.set(QueryController.current()?.window?.isVisible ?? false, forKey: "isQueryControllerVisible")
        for w in NSApp.windows {
            w.orderOut(sender)
        }

        let listeners = AppController.listeners()
        listeners.plain?.abort()
        listeners.tls?.abort()

        Thread.sleep(forTimeInterval: 0.5)

        let t = Date.timeIntervalSinceReferenceDate
        while (ThreadsManager.default()?.threads()?.count ?? 0) > 0 && Date.timeIntervalSinceReferenceDate - t < 10 { // give declared background threads 10 secs to cancel
            for case let thread as Thread in ThreadsManager.default()?.threads() ?? NSArray() {
                if !thread.isCancelled {
                    thread.cancel()
                }
            }
            Thread.sleep(forTimeInterval: 0.05)
        }

        for w in NSApp.windows {
            w.close()
        }

        UserDefaults.standard.synchronize()

        OSIGeneralPreferencePanePref.applyLanguagesIfNeeded()

        NSApp.terminate(sender)
    }

    public override init() {
        super.init()
        do {
            try HorosObjCException.perform {
                appController = self
                OsiriX = self

                DICOMTLS.eraseKeys()
                try? FileManager.default.removeItem(atPath: FileManager.default.tmpDirPath())

                if let applicationSupport = (FileManager.default.urls(for: .applicationSupportDirectory, in: .localDomainMask) as NSArray).firstObject as? URL,
                   let bundleName = Bundle.main.object(forInfoDictionaryKey: kCFBundleNameKey as String) as? String,
                   FileManager.default.fileExists(atPath: ((applicationSupport.path as NSString).appendingPathComponent(bundleName) as NSString).appendingPathComponent("DLog.enable")) {
                    N2Debug.setActive(true)
                }


                PapyrusLock = NSRecursiveLock()
                STORESCP = NSRecursiveLock()
                STORESCPTLS = NSRecursiveLock()

                NSAppleEventManager.shared().setEventHandler(self, andSelector: #selector(AppController.getUrl(_:withReplyEvent:)), forEventClass: AEEventClass(kInternetEventClass), andEventID: AEEventID(kAEGetURL))

                AppControllerCAPITestGraphicBoard()
            }
        } catch {
            let e = ObjC.exception(error)
            _ = HorosAlertPanel.runCritical(title: NSLocalizedString("Error", comment: ""), message: ObjC.format("%@", e?.reason), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)

            if let e = e { _N2LogExceptionImpl(e, true, "-[AppController init]") }
        }
    }


    @objc class func initializeAppController() {

        do {
            try HorosObjCException.perform {
                if self == AppController.self && State.initialized == false {
                    if (Bundle.main.infoDictionary?["CFBundlePackageType"] as? String) == "APPL" {
                        Thread.detachNewThreadSelector(#selector(AppController.DNSResolve(_:)), toTarget: self, with: nil)

                        State.initialized = true

                        var i: Int

                        srandom(UInt32(truncatingIfNeeded: time(nil)))

        //				Altivec = HasAltiVec();
                        //	if( Altivec == 0)
                        //	{
                        //		NSRunCriticalAlertPanel(@"Hardware Info", @"This application is optimized for Altivec - Velocity Engine unit, available only on G4/G5 processors.", @"OK", nil, nil);
                        //		exit(0);
                        //	}

                        if AppController.hasMacOSXElCapitan() == false {
                            _ = HorosAlertPanel.runCritical(title: NSLocalizedString("macOS", comment: ""), message: NSLocalizedString("This application requires macOS 10.11 or higher. Please upgrade your operating system.", comment: ""), defaultButton: NSLocalizedString("Quit", comment: ""), alternateButton: nil, otherButton: nil)
                            exit(0)
                        }

                        var processors: Int32 = 0
                        var mib: [Int32] = [CTL_HW, HW_NCPU]
                        var dataLen: Int = MemoryLayout<Int32>.size // 'num' is an 'int'
                        let result = sysctl(&mib, 2, &processors, &dataLen, nil, 0)
                        if result == -1 {
                            processors = 1
                        }

                        var bits = "32-bit"
                        if MemoryLayout<Int>.size == 8 {
                            bits = "64-bit"
                        }

                        NSLog("*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*-+-*")
                        NSLog("Number of processors: %d / %d", processors, Int32(truncatingIfNeeded: ProcessInfo.processInfo.processorCount))
                        NSLog("Number of screens: %d", Int32(truncatingIfNeeded: NSScreen.screens.count))
                        NSLog("Main screen backingScaleFactor: %f", Double(Float(NSScreen.main?.backingScaleFactor ?? 0)))
                        NSLog("Horos version: %@ - %@ - %@", ObjC.arg(Bundle.main.infoDictionary?[kCFBundleVersionKey as String]), ObjC.arg(Bundle.main.infoDictionary?["CFBundleShortVersionString"]), bits as NSString)
                        // <OpenJPEG/opj_config.h> is not published with the framework: AppController+CAPI.m reads it.
                        var opjMajor: Int32 = 0, opjMinor: Int32 = 0, opjBuild: Int32 = 0
                        AppControllerCAPIOpenJPEGVersion(&opjMajor, &opjMinor, &opjBuild)
                        NSLog("OpenJPEG %d.%d.%d", opjMajor, opjMinor, opjBuild)
                        let components = (Bundle.main.path(forResource: "Localizable", ofType: "strings") as NSString?)?.pathComponents as NSArray?
                        if let components = components, components.count > 3 {
                            NSLog("Localization: %@", ObjC.arg(components.object(at: components.count - 2)))
                        }
                        // AppKit's constraint visualiser draws a purple window of its own over
                        // ours. Turning it on by writing the preference left it on in the
                        // person's own preference file whenever a run ended any way but its
                        // own quit - for every later run, of any build - and AppKit lists
                        // every domain carrying the key when asked why that window is there.
                        // A window nobody recognises is reported as ours, so the log says
                        // when this is what it is.
                        #if !DEBUG
                        LayoutDebuggingDefaults.adoptForThisProcessOnly(false)
                        #else
                        LayoutDebuggingDefaults.adoptForThisProcessOnly(true)
                        #endif
                        let layoutDebugging = LayoutDebuggingDefaults.reportForCurrentProcess()
                        if let layoutDebugging = layoutDebugging {
                            NSLog("%@", layoutDebugging as NSString)
                        }
                        #if DEBUG
                        NSLog("**** DEBUG MODE ****")
                        #endif

                    //	if( [[NSCalendarDate dateWithYear:2006 month:6 day:2 hour:12 minute:0 second:0 timeZone:[NSTimeZone timeZoneWithAbbreviation:@"EST"]] timeIntervalSinceNow] < 0)
                    //	{
                    //		NSRunCriticalAlertPanel(@"Update needed!", @"This version of Horos is outdated. Please download the latest version from Horos web site!", @"OK", nil, nil);
                    //		[[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:URL_HOROS_VIEWER]];
                    //		exit(0);
                    //	}

                        //	switch( NSRunInformationalAlertPanel(@"Horos", @"Thank you for using Horos!\rWe need your help! Send us comments, bugs and ideas!\r\rI need supporting emails to prove utility of Horos!\r\rThanks!", @"Continue", @"Send an email", @"Web Site"))
                        //	{
                        //		case 0:
                        //			[[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:@"mailto:horos@horosproject.org?subject=Horos"]];
                        //		break;
                        //
                        //		case -1:
                        //			[[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:URL_HOROS_VIEWER]];
                        //		break;
                        //	}

                        // ** REGISTER DEFAULTS DICTIONARY

                        UserDefaults.standard.register(defaults: (DefaultsOsiriX.getDefaults() as? [String: Any]) ?? [:])


                        if (BrowserController._currentModifierFlags() & UInt32(NSEvent.ModifierFlags.command.rawValue)) != 0 &&
                           (BrowserController._currentModifierFlags() & UInt32(NSEvent.ModifierFlags.option.rawValue)) != 0 {
                            let result = HorosAlertPanel.runInformational(title: NSLocalizedString("Reset Preferences", comment: ""), message: NSLocalizedString("Are you sure you want to reset ALL preferences of Isis DICOM Viewer? All the preferences will be reseted to their default values.", comment: ""), defaultButton: NSLocalizedString("Cancel", comment: ""), alternateButton: NSLocalizedString("OK", comment: ""), otherButton: nil)

                            if result == HorosAlertPanel.alternateResponse {
                                for k in UserDefaults.standard.dictionaryRepresentation().keys {
                                    UserDefaults.standard.removeObject(forKey: k)
                                }

                                UserDefaults.standard.synchronize()
                            }
                        }



                        UserDefaults.standard.set(200, forKey: "NSInitialToolTipDelay")
                        UserDefaults.standard.set(false, forKey: "DontUseUndoQueueForROIs")
                        UserDefaults.standard.set(20, forKey: "UndoQueueSize")

                        // AutoClean evolution: old defaults AUTOCLEANINGSPACEPRODUCED and AUTOCLEANINGSPACEOPENED are merged into AutocleanSpaceMode
                        if UserDefaults.standard.object(forKey: "AutocleanSpaceMode") == nil {
                            let cleanOldest = ObjC.bool(UserDefaults.standard.object(forKey: "AUTOCLEANINGSPACEPRODUCED"))
                            let cleanOldestUnopened = ObjC.bool(UserDefaults.standard.object(forKey: "AUTOCLEANINGSPACEOPENED"))
                            if !cleanOldest && !cleanOldestUnopened {
                                UserDefaults.standard.set(false, forKey: "AUTOCLEANINGSPACE")
                                UserDefaults.standard.set(2, forKey: "AutocleanSpaceMode")
                            } else if cleanOldestUnopened {
                                UserDefaults.standard.set(1, forKey: "AutocleanSpaceMode")
                            } else {
                                UserDefaults.standard.set(0, forKey: "AutocleanSpaceMode")
                            }
                        }

                        // DICOMweb nodes of the pilot, stored in SERVERS with retrieveMode 3, move to
                        // DICOMWEB_SERVERS before anything reads SERVERS as a list of DIMSE nodes (#799).
                        DICOMwebNode.migrateLegacyServers()

                        SandboxFileAccess.restore()
                        DistributionChannel.configurePreferences()
                        #if MACAPPSTORE
                        let alternateDatabaseDefault = DatabaseLocation.baseDirectory(forPath: FileManager.default.userApplicationSupportFolderForApp())
                        #else
                        let alternateDatabaseDefault: String? = nil
                        #endif
                        DatabaseFirstUse.prepare(alternateDefault: alternateDatabaseDefault)

                        UserDefaults.standard.set(UserDefaults.standard.integer(forKey: "DEFAULT_DATABASELOCATION"), forKey: "DATABASELOCATION")
                        UserDefaults.standard.set(UserDefaults.standard.string(forKey: "DEFAULT_DATABASELOCATIONURL"), forKey: "DATABASELOCATIONURL")

                        UserDefaults.standard.set(false, forKey: "OSIEnvironmentActivated")
                        UserDefaults.standard.set(false, forKey: "is12bitPluginAvailable")
                        UserDefaults.standard.set(false, forKey: "ROITEXTNAMEONLY")

                        if !UserDefaults.standard.hasArgumentOverride(forKey: "hideListenerError") &&
                            UserDefaults.standard.object(forKey: "copyHideListenerError") != nil {
                            UserDefaults.standard.set(UserDefaults.standard.bool(forKey: "copyHideListenerError"), forKey: "hideListenerError")
                        }

                        #if MACAPPSTORE
                        UserDefaults.standard.set(NSLocalizedString("(Application storage)", comment: ""), forKey: "DefaultDatabasePath")
                        #else
                        UserDefaults.standard.set(NSLocalizedString("(Current User Documents folder)", comment: ""), forKey: "DefaultDatabasePath")
                        #endif

                        // __LP64__: both architectures are 64-bit (the 32-bit branch set LP64bit to NO)
                        UserDefaults.standard.set(true, forKey: "LP64bit")

                        // if we are loading a database that isn't on the root volume, then we must wait for it to load - if it doesn't become available after a few minutes, then we'll just let osirix switch to the db at ~/Documents as it would do anyway

                        var dataBasePath: String? = nil
                        do {
                            try HorosObjCException.perform {
                                dataBasePath = DicomDatabase.baseDirPath(forMode: Int32(truncatingIfNeeded: UserDefaults.standard.integer(forKey: "DATABASELOCATION")), path: UserDefaults.standard.string(forKey: "DATABASELOCATIONURL"))
                            }
                        } catch {
                            if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, false, "+[AppController initialize]") }
                        }

                        if ((dataBasePath as NSString?)?.hasPrefix("/Volumes/") ?? false) || dataBasePath == nil {
                            // +baseDirPathForMode:path: answers nil for a database on a volume
                            // that is not mounted, which is exactly the case this panel is for.
                            // The volume to wait for then has to come from the preference
                            // itself: asking about a path derived from nil could never say the
                            // volume had appeared, so plugging the disk back in while the panel
                            // was up did nothing and the launch waited the full ten minutes.
                            let defaults = UserDefaults.standard
                            let configuredPath: String? = defaults.integer(forKey: "DATABASELOCATION") == 1 ? defaults.string(forKey: "DATABASELOCATIONURL") : nil
                            let pathComponents = ((((dataBasePath as NSString?)?.length ?? 0) > 0 ? dataBasePath : configuredPath) as NSString?)?.components(separatedBy: "/") as NSArray?
                            let volumePath: String? = (pathComponents?.count ?? 0) >= 3 ? (pathComponents!.subarray(with: NSMakeRange(0, 3)) as NSArray).componentsJoined(by: "/") : nil
                            if let volumePath = volumePath, (volumePath as NSString).length > 0, !FileManager.default.fileExists(atPath: volumePath) {
                                let dialog = NSPanel.alert(withTitle: DatabaseLocation.dataDirectoryName,
                                                           message: ObjC.format(NSLocalizedString("Isis DICOM Viewer is configured to use the database located at %@. This volume is currently not available, most likely because it hasn't yet been mounted by the system, or because it is not plugged in or is turned off, or because you don't have write permissions for this location. Isis DICOM Viewer will wait for a few minutes, then give up and switch to a database in the current user's home directory.", comment: ""), UserDefaults.standard.string(forKey: "DATABASELOCATIONURL")),
                                                           defaultButton: "Quit",
                                                           alternateButton: "Continue",
                                                           icon: nil)
                                let session = NSApp.beginModalSession(for: dialog)

                                let endTime = Date.timeIntervalSinceReferenceDate + 10 * 60 // if ignored, the dialog stays up for 10 minutes
                                while true {
                                    let r = NSApp.runModalSession(session).rawValue
                                    if r == HorosAlertPanel.defaultResponse { // default button says Quit
                                        exit(0)
                                    } else if r == HorosAlertPanel.alternateResponse { // alternate button says Continue
                                        break
                                    }
                                    if FileManager.default.fileExists(atPath: volumePath) { // the volume has become available, we can close the dialog
                                        break
                                    }
                                    if Date.timeIntervalSinceReferenceDate > endTime { // time's out, we close the dialog
                                        NSLog("Warning: after waiting for 10 minutes, Horos is switching to the default database location because %@ is still not available", volumePath as NSString)
                                        break
                                    }
                                }

                                NSApp.endModalSession(session)
                                dialog.orderOut(self)

                                do {
                                    try HorosObjCException.perform {
                                        dataBasePath = DicomDatabase.baseDirPath(forMode: Int32(truncatingIfNeeded: UserDefaults.standard.integer(forKey: "DATABASELOCATION")), path: UserDefaults.standard.string(forKey: "DATABASELOCATIONURL"))
                                    }
                                } catch {
                                    UserDefaults.standard.set(0, forKey: "DATABASELOCATION")
                                    UserDefaults.standard.set(0, forKey: "DEFAULT_DATABASELOCATION")
                                }
                            }
                        }

                        // now, sometimes databases point to other volumes for data storage through the DBFOLDER_LOCATION file, so if it's the case verify that that volume is mounted, too
                        dataBasePath = DicomDatabase.baseDirPath(forPath: dataBasePath) // we know this is the data directory's path
                        // TODO: sometimes people use an alias... and if it's an alias, we should check that it points to an available volume..... should.
                        let dataBaseDataPath = ((dataBasePath as NSString?)?.appendingPathComponent("DBFOLDER_LOCATION")).flatMap { try? NSString(contentsOfFile: $0, encoding: String.Encoding.utf8.rawValue) }
                        if dataBaseDataPath?.hasPrefix("/Volumes/") ?? false {
                            let volumePath = ((dataBaseDataPath!.components(separatedBy: "/") as NSArray).subarray(with: NSMakeRange(0, 3)) as NSArray).componentsJoined(by: "/")
                            if !FileManager.default.fileExists(atPath: volumePath) {
                                let dialog = NSPanel.alert(withTitle: DatabaseLocation.dataDirectoryName,
                                                           message: ObjC.format(NSLocalizedString("Isis DICOM Viewer is configured to use the database with data located at %@. This volume is currently not available, most likely because it hasn't yet been mounted by the system, or because it is not plugged in or is turned off, or because you don't have write permissions for this location. Isis DICOM Viewer will wait for a few minutes, then give up and ignore this highly dangerous situation.", comment: ""), dataBaseDataPath),
                                                           defaultButton: "Quit",
                                                           alternateButton: "Continue",
                                                           icon: nil)
                                let session = NSApp.beginModalSession(for: dialog)

                                let endTime = Date.timeIntervalSinceReferenceDate + 10 * 60 // if ignored, the dialog stays up for 10 minutes
                                while true {
                                    let r = NSApp.runModalSession(session).rawValue
                                    if r == HorosAlertPanel.defaultResponse { // default button says Quit
                                        exit(0)
                                    } else if r == HorosAlertPanel.alternateResponse { // alternate button says Continue
                                        break
                                    }
                                    if FileManager.default.fileExists(atPath: volumePath) { // the volume has become available, we can close the dialog
                                        break
                                    }
                                    if Date.timeIntervalSinceReferenceDate > endTime { // time's out, we close the dialog
                                        NSLog("Warning: after waiting for 10 minutes, Horos is switching to the default database location because %@ is still not available", volumePath as NSString)
                                        break
                                    }
                                }

                                NSApp.endModalSession(session)
                                dialog.orderOut(self)
                            }
                        }






                        // Plugins may read DICOM through DCM.framework as they load (#742).
                        AppControllerCAPIRegisterDCMTKCodecs()
                        State.pluginManager = PluginManager()

                        //Add Endoscopy LUT, WL/WW, shading to existing prefs
                        // Shading Preset
                        let shadingArray = (UserDefaults.standard.object(forKey: "shadingsPresets") as? NSArray)?.mutableCopy() as? NSMutableArray
                        var exists = false

                        exists = false
                        for shading in shadingArray ?? NSMutableArray() {
                            if ((shading as? NSDictionary)?.object(forKey: "name") as? NSString)?.isEqual(to: "Endoscopy") ?? false {
                                exists = true
                            }
                        }

                        if exists == false {
                            let shading = NSMutableDictionary()
                            shading.setValue("Endoscopy", forKey: "name")
                            shading.setValue("0.12", forKey: "ambient")
                            shading.setValue("0.64", forKey: "diffuse")
                            shading.setValue("0.73", forKey: "specular")
                            shading.setValue("50", forKey: "specularPower")
                            shadingArray?.add(shading)
                        }

                        exists = false
                        for shading in shadingArray ?? NSMutableArray() {
                            if ((shading as? NSDictionary)?.object(forKey: "name") as? NSString)?.isEqual(to: "Glossy Bone") ?? false {
                                exists = true
                            }
                        }

                        if exists == false {
                            let shading = NSMutableDictionary()
                            shading.setValue("Glossy Bone", forKey: "name")
                            shading.setValue("0.15", forKey: "ambient")
                            shading.setValue("0.24", forKey: "diffuse")
                            shading.setValue("1.17", forKey: "specular")
                            shading.setValue("6.98", forKey: "specularPower")
                            shadingArray?.add(shading)
                        }

                        exists = false
                        for shading in shadingArray ?? NSMutableArray() {
                            if ((shading as? NSDictionary)?.object(forKey: "name") as? NSString)?.isEqual(to: "Glossy Vascular") ?? false {
                                exists = true
                            }
                        }

                        if exists == false {
                            let shading = NSMutableDictionary()
                            shading.setValue("Glossy Vascular", forKey: "name")
                            shading.setValue("0.15", forKey: "ambient")
                            shading.setValue("0.28", forKey: "diffuse")
                            shading.setValue("1.42", forKey: "specular")
                            shading.setValue("50", forKey: "specularPower")
                            shadingArray?.add(shading)
                        }

                        UserDefaults.standard.set(shadingArray, forKey: "shadingsPresets")

                        // Endoscopy LUT
                        let cluts = (UserDefaults.standard.object(forKey: "CLUT") as? NSDictionary)?.mutableCopy() as? NSMutableDictionary
                        // fix bad CLUT in previous versions
                        let clut = cluts?.object(forKey: "Endoscopy") as? NSDictionary
                        if clut == nil || ObjC.int((clut?.object(forKey: "Red") as? NSArray)?.object(at: 0)) != 240 {
                            let aCLUTFilter = NSMutableDictionary()
                            let rArray = NSMutableArray()
                            let gArray = NSMutableArray()
                            let bArray = NSMutableArray()
                            i = 0
                            while i < 256 {
                                bArray.add(NSNumber(value: Int(195 - (Double(i) * 0.26))))
                                gArray.add(NSNumber(value: Int(187 - (Double(i) * 0.26))))
                                rArray.add(NSNumber(value: Int(240 + (Double(i) * 0.02))))
                                i += 1
                            }
                            aCLUTFilter.setObject(rArray, forKey: "Red" as NSString)
                            aCLUTFilter.setObject(gArray, forKey: "Green" as NSString)
                            aCLUTFilter.setObject(bArray, forKey: "Blue" as NSString)

                            // Points & Colors
                            let colors = NSMutableArray(), points = NSMutableArray()
                            points.add(NSNumber(value: 0 as Int))
                            points.add(NSNumber(value: 255 as Int))

                            colors.add(NSArray(objects: NSNumber(value: 1 as Float), NSNumber(value: 1 as Float), NSNumber(value: 1 as Float)))
                            colors.add(NSArray(objects: NSNumber(value: 0 as Float), NSNumber(value: 0 as Float), NSNumber(value: 0 as Float)))


                            aCLUTFilter.setObject(colors, forKey: "Colors" as NSString)
                            aCLUTFilter.setObject(points, forKey: "Points" as NSString)

                            cluts?.setObject(aCLUTFilter, forKey: "Endoscopy" as NSString)
                            UserDefaults.standard.set(cluts, forKey: "CLUT")
                        }

                        //ww/wl
                        let wlwwValues = (UserDefaults.standard.object(forKey: "WLWW3") as? NSDictionary)?.mutableCopy() as? NSMutableDictionary
                        let wwwl = wlwwValues?.object(forKey: "VR - Endoscopy")
                        if wwwl == nil {
                            wlwwValues?.setObject(NSArray(objects: NSNumber(value: -300 as Float), NSNumber(value: 700 as Float)), forKey: "VR - Endoscopy" as NSString)
                            UserDefaults.standard.set(wlwwValues, forKey: "WLWW3")
                        }


                        // CREATE A TEMPORATY FILE DURING STARTUP

                        if !DatabaseFirstUse.hasPendingChoice {
                            let path = (DicomDatabase.defaultBaseDirPath() as NSString?)?.appendingPathComponent("Loading")
                            let pluginMarkerExists = FileManager.default.fileExists(atPath: PluginManager.crashMarkerPath())

                            if UserDefaults.standard.bool(forKey: "hideListenerError") == false {
                                if FileManager.default.fileExists(atPath: path ?? "") &&
                                    PluginUpdateRecovery.shouldOfferDatabaseRebuild(loadingFileExists: true, pluginMarkerExists: pluginMarkerExists) {
                                    let result = HorosAlertPanel.runInformational(title: NSLocalizedString("Isis DICOM Viewer crashed during last startup", comment: ""), message: NSLocalizedString("Previous crash is maybe related to a corrupt database or corrupted images.\r\rShould I run Isis DICOM Viewer in Protected Mode (recommended) (no images displayed)? To allow you to delete the crashing/corrupted images/studies.\r\rOr Should I rebuild the local database? All albums, comments and status will be lost.", comment: ""), defaultButton: NSLocalizedString("Continue normally", comment: ""), alternateButton: NSLocalizedString("Protected Mode", comment: ""), otherButton: NSLocalizedString("Rebuild Database", comment: ""))

                                    if result == HorosAlertPanel.otherResponse {
                                        NEEDTOREBUILD = true
                                        COMPLETEREBUILD = true
                                    }
                                    if result == HorosAlertPanel.alternateResponse { DCMPix.setRunOsiriXInProtectedMode(true) }
                                }
                            }

                            if let path = path {
                                try? (path as NSString).write(toFile: path, atomically: false, encoding: String.Encoding.utf8.rawValue)
                            }

                        }

                        Reports.checkForWordTemplates()
                        Reports.checkForPagesTemplate()

                    }
                }
            }
        } catch {
            NSLog("+initialize exception: %@", ObjC.arg(ObjC.exception(error)?.description))
        }

    }

    // MARK: -
    // MARK: notification

    @objc(notificationTitle:description:name:) nonisolated public func notificationTitle(_ title: String!, description: String!, name: String!) {
        // Any thread posts these (imports, listeners, routing): now on the main
        // thread, or later on the main queue.
        onMainActor { self.notificationTitleOnMainActor(title, description: description, name: name) }
    }

    private func notificationTitleOnMainActor(_ title: String?, description: String?, name: String?) {
        if State.delivered == nil { State.delivered = NSMutableDictionary(); State.pending = NSMutableDictionary() }
        let delivered = State.delivered!, pending = State.pending!
        let kind: String = ((name as NSString?)?.length ?? 0) > 0 ? name! : "horos"
        let now = Date.timeIntervalSinceReferenceDate
        let last = delivered.object(forKey: kind) as? NSNumber
        let wait: TimeInterval = last != nil ? last!.doubleValue + AppController.HorosNotificationInterval - now : 0
        if wait > 0 {
            let scheduled = pending.object(forKey: kind) != nil
            pending.setObject([title ?? "", description ?? ""] as NSArray, forKey: kind as NSString)
            if !scheduled {
                DispatchQueue.main.asyncAfter(deadline: .now() + wait) {
                    let latest = pending.object(forKey: kind) as? NSArray
                    pending.removeObject(forKey: kind)
                    delivered.setObject(NSNumber(value: Date.timeIntervalSinceReferenceDate), forKey: kind as NSString)
                    self.deliverNotificationTitle(latest?.object(at: 0) as? String, description: latest?.object(at: 1) as? String, name: kind, sound: false)
                }
            }
            return
        }
        delivered.setObject(NSNumber(value: now), forKey: kind as NSString)
        self.deliverNotificationTitle(title, description: description, name: kind,
                                      sound: last == nil || now - last!.doubleValue >= AppController.HorosNotificationQuietSound)
    }

    @objc(deliverNotificationTitle:description:name:sound:) func deliverNotificationTitle(_ title: String!, description: String!, name: String!, sound: Bool) {
        if #available(macOS 10.14, *) {
            let notification = UNMutableNotificationContent()
            notification.title = title ?? ""
            notification.body = description ?? ""
            notification.categoryIdentifier = name ?? ""
            notification.threadIdentifier = name ?? ""
            if sound { notification.sound = UNNotificationSound.default }

            let trigger: UNNotificationTrigger? = nil // deliver immediately
            let request = UNNotificationRequest(identifier: "org.horosproject.notification." + name, content: notification, trigger: trigger)
            let center = UNUserNotificationCenter.current()
            center.add(request) { error in
                if let error = error {
                    NSLog("User Notification failed for title=[%@] description=[%@] error=[%@]", ObjC.arg(title), ObjC.arg((description as NSString?)?.replacingOccurrences(of: "\r", with: "\n")), error.localizedDescription as NSString)
                }
            }
        }
    }

    // MARK: -

    @objc(killDICOMListenerWait:) public func killDICOMListenerWait(_ w: Bool) {
        var listeners = AppController.listeners()
        listeners.plain?.abort()
        listeners.tls?.abort()

        self.killAllStoreSCU(self)

        listeners = AppController.listeners()
        if let plain = listeners.plain {
            _ = QueryController.echo(self.privateIP(), port: plain.port(), aet: plain.aeTitle())
        }
        if let tls = listeners.tls {
            _ = QueryController.echo(self.privateIP(), port: tls.port(), aet: tls.aeTitle())
        }

        Thread.sleep(forTimeInterval: 0.1)

        if w {
            while AppController.listeners().plain?.running() ?? false {
                NSLog("waiting for listener to stop...")
                Thread.sleep(forTimeInterval: 0.1)
            }
            while AppController.listeners().tls?.running() ?? false {
                NSLog("waiting for TLS listener to stop...")
                Thread.sleep(forTimeInterval: 0.1)
            }
        }

        AppController.listenerLock.withLock {
            dcmtkQRSCP = nil
            dcmtkQRSCPTLS = nil
        }
    }

    @objc(switchHandler:) func switchHandler(_ notification: Notification!) {
        if notification?.name == NSWorkspace.sessionDidResignActiveNotification {
            _ = BrowserController.currentBrowser()?.database?.save(nil)

            if UserDefaults.standard.bool(forKey: "RunListenerOnlyIfActive") {
                NSLog("----- Horos : session deactivation: STOP DICOM LISTENER FOR THIS SESSION")

                self.killDICOMListenerWait(true)

                isSessionInactive = true
            }
        } else if notification?.name == NSWorkspace.sessionDidBecomeActiveNotification {
            Thread.sleep(forTimeInterval: 4)

            isSessionInactive = false

            if UserDefaults.standard.bool(forKey: "RunListenerOnlyIfActive") {
                NSLog("----- Horos : session activation: START DICOM LISTENER FOR THIS SESSION")

                // [[BrowserController currentBrowser] loadDatabase: [[BrowserController currentBrowser] currentDatabasePath]]; // TODO: hmm

                self.restartSTORESCP()
            }
        }
    }

    @objc nonisolated public func isStoreSCPRunning() -> Bool {
        let listeners = AppController.listeners()
        if listeners.plain?.running() ?? false {
            return true
        }

        if listeners.tls?.running() ?? false {
            return true
        }

        if UserDefaults.standard.bool(forKey: "NinjaSTORESCP") { // some undefined external entity is linked to Horos for DICOM communications...
            return true
        }

        return false
    }

    @objc(applicationDidFinishLaunching:) func applicationDidFinishLaunching(_ aNotification: Notification!) {

        ViewerController.installROIInterchangeMenuItems()
        ViewerController.installRegistrationMenuItems()
        ViewerController.installSeriesListPlacementMenuItems()
        ViewerController.installRegisteredGIFMenuItems()
        ViewerController.installGSPSMenuItems()
        BrowserController.installAutomaticCleanupPreviewMenu()
        BrowserController.installSurgicalProcedureImportMenu()

        NSWorkspace.shared.notificationCenter.addObserver(self,
                                                          selector: #selector(AppController.switchHandler(_:)),
                                                          name: NSWorkspace.sessionDidBecomeActiveNotification,
                                                          object: nil)

        NSWorkspace.shared.notificationCenter.addObserver(self,
                                                          selector: #selector(AppController.switchHandler(_:)),
                                                          name: NSWorkspace.sessionDidResignActiveNotification,
                                                          object: nil)

        // Will request authorization for notifications now even if not enabled in preferences as user may update
        // preferences while running. NOTE: requirements for application to be able to get authorization are more
        // stringent for later releases (e.g., properly signed, notarized).
        //
        if #available(macOS 10.14, *) {
            let center = UNUserNotificationCenter.current()
            // Earlier versions left one notification per imported batch (#696).
            center.removeAllDeliveredNotifications()
            center.requestAuthorization(options: [.sound, .alert]) { (granted, error) in
                if error == nil {
                    NSLog("User Notification authorization request succeeded")
                }
                else {
                    NSLog("User Notification authorization request failed, error=[%@]", ObjC.arg(error?.localizedDescription))
                }
            }
        }


//#ifdef WITH_IMPORTANT_NOTICE
//	[AppController displayImportantNotice: self];
//#endif

        if UserDefaults.standard.bool(forKey: "hideListenerError") {
            UserDefaults.standard.set(false, forKey: "checkForUpdatesPlugins")
        }

        UserDefaults.standard.set(true, forKey: "USEALWAYSTOOLBARPANEL2")
        UserDefaults.standard.set(true, forKey: "syncPreviewList")
        UserDefaults.standard.set(true, forKey: "SeriesListVisible")
//    [[NSUserDefaults standardUserDefaults] setBool: NO  forKey: @"AUTOHIDEMATRIX"];


        #if !MACAPPSTORE
        if UserDefaults.standard.bool(forKey: "checkForUpdatesPlugins") {
            if let pluginManager = State.pluginManager {
                pluginManager.checkForUpdates(nil)
            }
        }


        // If Horos crashed before...
        let HorosCrashed = (FileManager.default.tmpDirPath() as NSString).appendingPathComponent("HorosCrashed")

        if FileManager.default.fileExists(atPath: HorosCrashed) // Activate check for update !
        {
            try? FileManager.default.removeItem(atPath: HorosCrashed)

            if UserDefaults.standard.bool(forKey: "CheckHorosUpdates") == false
            {
                if UserDefaults.standard.bool(forKey: "hideListenerError") == false {
                    Thread.detachNewThreadSelector(#selector(AppController.checkForUpdates(_:)), toTarget: self, with: "crash" as NSString)
                }
            }
        }
        else { Thread.detachNewThreadSelector(#selector(AppController.checkForUpdates(_:)), toTarget: self, with: self) }

        #endif
        DistributionChannel.configureMenu(NSApp.mainMenu)

        if UserDefaults.standard.bool(forKey: "hideListenerError") { // Server mode
            BrowserController.currentBrowser()?.window?.orderOut(self)
        }

        // (OSIRIX_LIGHT: "Horos Lite" alert offering to download the full version, exit(0) on exception, not compiled)


//	NSString *source = [NSString stringWithContentsOfFile: [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"/dicom.dic"]];
//
//	NSArray *lines = [source componentsSeparatedByString: @"\n"];
//
//	NSMutableDictionary *nameDictionary = [NSMutableDictionary dictionary], *tagDictionary = [NSMutableDictionary dictionary];
//
//    NSBundle *bundle = [NSBundle bundleForClass:NSClassFromString(@"DCMTagDictionary")];
//
//    tagDictionary = [NSMutableDictionary dictionaryWithContentsOfFile: [bundle pathForResource:@"tagDictionary" ofType:@"plist"]];
//    nameDictionary = [NSMutableDictionary dictionaryWithContentsOfFile: [bundle pathForResource:@"nameDictionary" ofType:@"plist"]];
//
//	for( NSString *l in lines)
//	{
//		if( [l hasPrefix: @"#"] == NO)
//		{
//			NSArray *f = [l componentsSeparatedByString: @"\t"];
//
//			if( [f count] == 5)
//			{
//				NSString *grel = [[f objectAtIndex: 0] stringByReplacingOccurrencesOfString: @"(" withString:@""];
//				grel = [grel stringByReplacingOccurrencesOfString: @")" withString:@""];
//				grel = [grel uppercaseString];
//
//				if( [grel length] >= 9 && [grel characterAtIndex:4] == ',')
//				{
//					grel = [grel substringToIndex: 9];
//
//					NSDictionary *d = [NSDictionary dictionaryWithObjectsAndKeys: [f objectAtIndex: 2], @"Description", [f objectAtIndex: 3], @"VM", [f objectAtIndex: 1], @"VR", nil];	//[f objectAtIndex: 4], @"Version", nil];
//
//                    if( [tagDictionary objectForKey: grel])
//                    {
////                        NSLog( @"%@", [tagDictionary objectForKey: grel]);
//                    }
//                    else
//                    {
//                        NSLog( @"%@", d);
//
//                        [tagDictionary setObject: d forKey: grel];
//                        [nameDictionary setObject: grel forKey: [f objectAtIndex: 2]];
//                    }
//				}
//			}
//			else
//				NSLog( @"%@", f);
//		}
//	}
//
//	[tagDictionary writeToFile: @"/tmp/tagDictionary.plist" atomically: YES];
//	[nameDictionary writeToFile: @"/tmp/nameDictionary.plist" atomically: YES];

//	warning : patientssex -> patientsex, patientsname -> patientname, ...

//	<?xml version="1.0" encoding="UTF-8"?>
//	<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
//	<plist version="1.0">
//	<dict>
//	<key>Description</key>
//	<string>PhilipsFactor</string>
//	<key>VM</key>
//	<string>1</string>
//	<key>VR</key>
//	<string>DS</string>
//	</dict>
//	</plist>


        self.testMenus()

        ROI.loadDefaultSettings()

        // #ifndef OSIRIX_LIGHT
#if !DEBUG
        PFMoveToApplicationsFolderIfNecessary()

        // (WITH_CODE_SIGNING: SecStaticCodeCheckValidity of the bundle against the "66HE7FMBC4" certificate, with a critical alert, not compiled)
#endif // NDEBUG
        // #endif // OSIRIX_LIGHT

        if AppController.hasMacOSXElCapitan() == false
        {
            _ = HorosAlertPanel.runCritical(title: NSLocalizedString("macOS Version", comment: ""), message: NSLocalizedString("Isis DICOM Viewer requires macOS 10.11 or higher. Please update your OS: Apple Menu - Software Update...", comment: ""), defaultButton: NSLocalizedString("Quit", comment: ""), alternateButton: nil, otherButton: nil)
            exit(0)
        }

        if UserDefaults.standard.bool(forKey: "SyncPreferencesFromURL") {
            Thread.detachNewThreadSelector(NSSelectorFromString("addPreferencesFromURL:"), toTarget: OSIGeneralPreferencePanePref.self, with: UserDefaults.standard.string(forKey: "SyncPreferencesURL").flatMap { NSURL(string: $0) })
        }


        // #ifndef OSIRIX_LIGHT
        if UserDefaults.standard.bool(forKey: "isQueryControllerVisible")
        {
            if QueryController.current() == nil {
                _ = QueryController(autoQuery: false)
            }

            QueryController.current()?.showWindow(self)
        }
        // #endif

        // #if defined(USEFEEDBACKREPORTER): the dispatch_after of 5 s that sends
        // [FRFeedbackReporter sharedReporter] on the main queue, in AppController+CAPI.m.
        //dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0), ^{
        AppControllerCAPIStartFeedbackReporter()
        //});
    }

    @objc func checkForOsirixMimeType() {
        let path = "~/Library/Preferences/com.apple.LaunchServices.plist"

        let dict: NSDictionary? = NSMutableDictionary(contentsOfFile: (path as NSString).expandingTildeInPath)

        for handler in (dict?.object(forKey: "LSHandlers") as? NSArray) ?? NSArray()
        {
            if ((handler as? NSDictionary)?.object(forKey: "LSHandlerURLScheme") as? NSString)?.isEqual(to: "dicom") == true
            {
                return
            }
        }

        let mutableDict = NSMutableDictionary(dictionary: (dict as? [AnyHashable: Any]) ?? [:])

        let handlerForOsiriX = NSDictionary(objects: ["thalesmms.isis.workstation" /* BUNDLE_IDENTIFIER */, "dicom"], forKeys: ["LSHandlerRoleAll" as NSString, "LSHandlerURLScheme" as NSString])

        // Sent through the runtime so that a nil array raises, as -setObject:forKey: did.
        _ = mutableDict.perform(#selector(NSMutableDictionary.setObject(_:forKey:)), with: (dict?.object(forKey: "LSHandlers") as? NSArray)?.adding(handlerForOsiriX), with: "LSHandlers" as NSString)

        try? FileManager.default.removeItem(atPath: (path as NSString).expandingTildeInPath)
        mutableDict.write(toFile: (path as NSString).expandingTildeInPath, atomically: true)
    }

    // #define kIOPCIDevice                "IOPCIDevice"
    private static let kIOPCIDevice = "IOPCIDevice"
    // #define kIONameKey                  "IOName"
    private static let kIONameKey = "IOName"
    // #define kDisplayKey                 "display"
    private static let kDisplayKey = "display"
    // #define kModelKey                   "model"
    private static let kModelKey = "model"
    // #define kIntelGPUPrefix             @"Intel"
    private static let kIntelGPUPrefix = "Intel"

    @objc class func getGPUNames() -> NSArray! {
        let GPUs = NSMutableArray()

        // The IOPCIDevice class includes display adapters/GPUs.
        let devices = IOServiceMatching(AppController.kIOPCIDevice)
        var entryIterator: io_iterator_t = 0

        if IOServiceGetMatchingServices(kIOMainPortDefault, devices, &entryIterator) == kIOReturnSuccess {
            var device: io_registry_entry_t

            while true {
                device = IOIteratorNext(entryIterator)
                if device == 0 { break }

                var serviceDictionaryRef: Unmanaged<CFMutableDictionary>? = nil

                if IORegistryEntryCreateCFProperties(device, &serviceDictionaryRef, kCFAllocatorDefault, IOOptionBits(0)) != kIOReturnSuccess {
                    // Couldn't get the properties for this service, so clean up and
                    // continue.
                    IOObjectRelease(device)
                    continue
                }

                // takeRetainedValue: released at the end of the iteration, where CFRelease was.
                guard let serviceDictionary = serviceDictionaryRef?.takeRetainedValue() as NSDictionary? else { continue }

                let ioName = serviceDictionary.object(forKey: AppController.kIONameKey) as AnyObject?

                if let ioName = ioName {
                    // If we have an IOName, and its value is "display", then we've
                    // got a "model" key, whose value is a CFDataRef that we can
                    // convert into a string.
                    if CFGetTypeID(ioName) == CFStringGetTypeID() && CFStringCompare((ioName as! CFString), AppController.kDisplayKey as CFString, .compareCaseInsensitive) == .compareEqualTo {
                        let model = serviceDictionary.object(forKey: AppController.kModelKey)

                        let gpuName = NSString(data: (model as? Data) ?? Data(),
                                               encoding: String.Encoding.ascii.rawValue)

                        if let gpuName = gpuName {
                            GPUs.add(gpuName)
                        }
                    }
                }
            }
        }

        return GPUs
    }

    @objc func verifyHardwareInterpolation() {
        if AppController.hasMacOSX1083() // Intel 10.8.3 graphic bug
        {
            var onlyIntelGraphicBoard = true
            for gpuName in AppController.getGPUNames() ?? NSArray()
            {
                if (gpuName as? NSString)?.hasPrefix(AppController.kIntelGPUPrefix) != true {
                    onlyIntelGraphicBoard = false
                }
            }

            if onlyIntelGraphicBoard
            {
                NSLog("**** 10.8.3 graphic board bug: only intel board discovered : No 32-bit pipeline available")
                NSLog("%@", ObjC.arg(AppController.getGPUNames()))

                UserDefaults.standard.set(false, forKey: "FULL32BITPIPELINE")
                return
            }
        }

        let size: UInt = 32, size2 = size * size

        let win = NSWindow(contentRect: NSMakeRect(0, 0, CGFloat(size), CGFloat(size)), styleMask: .titled, backing: .buffered, defer: false)

        let annotCopy: Int = UserDefaults.standard.integer(forKey: "ANNOTATIONS")
        let clutBarsCopy: Int = UserDefaults.standard.integer(forKey: "CLUTBARS")
        let noInterpolationCopy = UserDefaults.standard.bool(forKey: "NOINTERPOLATION")
        let highQInterpolationCopy = UserDefaults.standard.bool(forKey: "SOFTWAREINTERPOLATION")

        var pixData: [Float] = [0, 1, 1, 0]
        let dcmPix = DCMPix(data: &pixData, 32, 2, 2, 1, 1, 0, 0, 0)

        var dcmView: DCMView!
        // gray_1 holds the capture without interpolation, gray_2 the one with it.
        var gray_1 = [UInt8](repeating: 0, count: Int(size2))
        var gray_2 = [UInt8](repeating: 0, count: Int(size2))

        UserDefaults.standard.set(annotNone, forKey: "ANNOTATIONS")
        UserDefaults.standard.set(barHide, forKey: "CLUTBARS")

        // pix 1: no interpolation

        UserDefaults.standard.set(true, forKey: "NOINTERPOLATION")
        UserDefaults.standard.set(false, forKey: "SOFTWAREINTERPOLATION")
        UserDefaults.standard.set(true, forKey: "FULL32BITPIPELINE")

        dcmView = DCMView(frame: NSMakeRect(0, 0, CGFloat(size), CGFloat(size)))
        dcmView.setPixels(NSMutableArray(object: dcmPix!), files: nil, rois: nil, firstImage: 0, level: CChar(UInt8(ascii: "i")), reset: true)
        dcmView.setScaleValueCentered(Float(size))
        win.contentView?.addSubview(dcmView)
        dcmView.draw(NSMakeRect(0, 0, CGFloat(size), CGFloat(size)))

        do {
            var imOrigin = [Float](repeating: 0, count: 3), imSpacing = [Float](repeating: 0, count: 2)
            var width = 0, height = 0, spp = 0, bpp = 0

            let data = dcmView.getRawPixelsViewWidth(&width, height: &height, spp: &spp, bpp: &bpp, screenCapture: true, force8bits: true, removeGraphical: true, squarePixels: true, allowSmartCropping: false, origin: &imOrigin, spacing: &imSpacing, offset: nil, isSigned: nil)

            assert(spp == 3)

            if let data = data
            {
                for i in 0..<Int(size2) {
                    gray_1[i] = UInt8(truncatingIfNeeded: (Int32(data[i*3]) + Int32(data[i*3+1]) + Int32(data[i*3+2])) / 3)
                }
                free(data)

//            planes[0] = gray_1;
//            NSBitmapImageRep* representation = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:planes
//                                                                                       pixelsWide:size pixelsHigh:size bitsPerSample:8
//                                                                                  samplesPerPixel:1 hasAlpha:NO isPlanar:NO
//                                                                                   colorSpaceName:NSCalibratedBlackColorSpace bytesPerRow:size
//                                                                                     bitsPerPixel:8];
//            [[representation TIFFRepresentation] writeToFile:@"/tmp/aaaaa1.tif" atomically:YES];
//            [representation release];
            }
        }

        dcmView.removeFromSuperview()

        // pix 2: interpolation

        UserDefaults.standard.set(false, forKey: "NOINTERPOLATION")
        UserDefaults.standard.set(false, forKey: "SOFTWAREINTERPOLATION")
        UserDefaults.standard.set(true, forKey: "FULL32BITPIPELINE")
        dcmView = DCMView(frame: NSMakeRect(0, 0, CGFloat(size), CGFloat(size)))
        dcmView.setPixels(NSMutableArray(object: dcmPix!), files: nil, rois: nil, firstImage: 0, level: CChar(UInt8(ascii: "i")), reset: true)
        dcmView.setScaleValueCentered(Float(size))
        win.contentView?.addSubview(dcmView)
        dcmView.draw(NSMakeRect(0, 0, CGFloat(size), CGFloat(size)))

        do {
            var imOrigin = [Float](repeating: 0, count: 3), imSpacing = [Float](repeating: 0, count: 2)
            var width = 0, height = 0, spp = 0, bpp = 0

            let data = dcmView.getRawPixelsViewWidth(&width, height: &height, spp: &spp, bpp: &bpp, screenCapture: true, force8bits: true, removeGraphical: true, squarePixels: true, allowSmartCropping: false, origin: &imOrigin, spacing: &imSpacing, offset: nil, isSigned: nil)

            assert(spp == 3)

            if let data = data
            {
                for i in 0..<Int(size2) {
                    gray_2[i] = UInt8(truncatingIfNeeded: (Int32(data[i*3]) + Int32(data[i*3+1]) + Int32(data[i*3+2])) / 3)
                }
                free(data)

//            planes[0] = gray_1;
//            NSBitmapImageRep* representation = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:planes
//                                                                                       pixelsWide:size pixelsHigh:size bitsPerSample:8
//                                                                                  samplesPerPixel:1 hasAlpha:NO isPlanar:NO
//                                                                                   colorSpaceName:NSCalibratedBlackColorSpace bytesPerRow:size
//                                                                                     bitsPerPixel:8];
//            [[representation TIFFRepresentation] writeToFile:@"/tmp/aaaaa2.tif" atomically:YES];
//            [representation release];
            }
        }
        dcmView.removeFromSuperview()


        UserDefaults.standard.set(annotCopy, forKey: "ANNOTATIONS")
        UserDefaults.standard.set(clutBarsCopy, forKey: "CLUTBARS")
        UserDefaults.standard.set(noInterpolationCopy, forKey: "NOINTERPOLATION")
        UserDefaults.standard.set(highQInterpolationCopy, forKey: "SOFTWAREINTERPOLATION")

        DCMView.setCLUTBARS(Int32(truncatingIfNeeded: clutBarsCopy), annotations: Int32(truncatingIfNeeded: annotCopy))

        // eval results

        var delta: CGFloat = 0
        for i in 0..<Int(size2) {
            delta += CGFloat(fabsf(Float(gray_1[i]) - Float(gray_2[i])))
        }
        let has32bitPipeline = delta > 1000 // we may want to raise this..

        if has32bitPipeline
        {
            NSLog("-- 32bit pipeline available : delta = %f", Double(delta))
            UserDefaults.standard.set(true, forKey: "hasFULL32BITPIPELINE")
            UserDefaults.standard.set(true, forKey: "FULL32BITPIPELINE")
        }
        else
        {
            NSLog("-- 32bit pipeline inactivated : delta = %f", Double(delta))
            UserDefaults.standard.set(false, forKey: "hasFULL32BITPIPELINE")
            UserDefaults.standard.set(false, forKey: "FULL32BITPIPELINE")
        }
    }


    @objc(applicationWillFinishLaunching:) func applicationWillFinishLaunching(_ aNotification: Notification!) {
        if let dictionary = HorosVendoredDicomDictionaryPath() {
            _ = HorosLoadVendoredDicomDictionary(dictionary)
        }

        if DatabaseFirstUse.hasPendingChoice
        {
            if !DatabaseFirstUse.choosePreparedLocation() {
                exit(0)
            }
            UserDefaults.standard.set(UserDefaults.standard.integer(forKey: "DEFAULT_DATABASELOCATION"), forKey: "DATABASELOCATION")
            UserDefaults.standard.set(UserDefaults.standard.string(forKey: "DEFAULT_DATABASELOCATIONURL"), forKey: "DATABASELOCATIONURL")
            BrowserController.currentBrowser()?.completeFirstUseDatabaseSetup()
        }

        DispatchQueue.main.async {
            _ = self.setupCrashReporter()
        }

        ////////////////////////////

        AppController.cleanOsiriXSubProcesses()

        if Date.timeIntervalSinceReferenceDate - UserDefaults.standard.double(forKey: "lastDate32bitPipelineCheck") > TimeInterval(60 * 60 * 24) // 1 days
        {
            UserDefaults.standard.set(Date.timeIntervalSinceReferenceDate, forKey: "lastDate32bitPipelineCheck")
            self.verifyHardwareInterpolation()
        }

        // Series are independent viewers; tabbing breaks tiling and active-viewer routing.
        if #available(macOS 10.12, *) {
            NSWindow.allowsAutomaticWindowTabbing = false
        }

        let dialog = false



        // This used to list three temporary prefixes by hand and miss the one that
        // matters: macOS puts the per-user temporary directory under
        // /private/var/folders/.../T/, which is where a CD's database is copied and
        // opened from. One rule, in HorosSourceLocation, so this and the browser's
        // own pass cannot disagree.
        let dbArray = UserDefaults.standard.array(forKey: "localDatabasePaths")
        let permanent = SourceLocation.permanentEntries(in: (dbArray as? [[String: Any]]) ?? [], pathKey: "Path")
        if permanent.count != (dbArray?.count ?? 0)
        {
            for dropped in SourceLocation.temporaryEntries(in: (dbArray as? [[String: Any]]) ?? [], pathKey: "Path") {
                NSLog("---- sources: forgetting %@; it is in a temporary location, not a database to come back to", dropped as NSString)
            }
            UserDefaults.standard.set(permanent, forKey: "localDatabasePaths")
        }

        if UserDefaults.standard.value(forKey: "timeZone") != nil
        {
            if UserDefaults.standard.integer(forKey: "timeZone") != NSTimeZone.local.secondsFromGMT()
            {
            }
        }
        else { UserDefaults.standard.set(NSTimeZone.local.secondsFromGMT(), forKey: "timeZone") }

        if ObjC.int(UserDefaults.standard.value(forKey: "COPYDATABASEMODE")) == 1 { // tag 1 "if on CD", disappeared after new CD/DVD import system
            UserDefaults.standard.set(2, forKey: "COPYDATABASEMODE")
        }


        if dialog == false
        {

        }

        /*
        #ifndef OSIRIX_LIGHT
        #ifndef MACAPPSTORE
        if( [[NSUserDefaults standardUserDefaults] boolForKey: @"hideListenerError"] == NO)
        {
            @try
            {
                ILCrashReporter *reporter = [ILCrashReporter defaultReporter];

                NSUserDefaults *d = [NSUserDefaults standardUserDefaults];


                if( [d valueForKey: @"crashReporterSMTPServer"])
                {
                    reporter.SMTPServer = [d valueForKey: @"crashReporterSMTPServer"];
                    int port = [d integerForKey: @"crashReporterSMTPPort"];
                    reporter.SMTPPort = port? port : 25;
                    // if these are empty, set them to empty
                    reporter.SMTPUsername = [d valueForKey: @"crashReporterSMTPUsername"];
                    reporter.SMTPPassword = [d valueForKey: @"crashReporterSMTPPassword"];
                }

                if( [d valueForKey: @"crashReporterFromAddress"])
                {
                    reporter.fromAddress = [d valueForKey: @"crashReporterFromAddress"];
                }

                NSString *reportAddr = @"horoscrashreport@gmail.com";

                if( [d valueForKey: @"crashReporterToAddress"])
                {
                    reportAddr = [d valueForKey: @"crashReporterToAddress"];
                }

                reporter.automaticReport = [d boolForKey: @"crashReporterAutomaticReport"];


                NSLog(@"%@",reporter.SMTPServer);
                NSLog(@"%@",reporter.SMTPUsername);
                NSLog(@"%@",reporter.SMTPPassword);
                NSLog(@"%@",reporter.fromAddress);


                [reporter launchReporterForCompany:@"Horos Developers" reportAddr: reportAddr];
            }
            @catch (NSException *e)
            {
                NSLog( @"**** Exception ILCrashReporter: %@", e);
            }
        }
        #endif
        #endif
        */

        // A plugin that raises here used to take the rest of this method with it,
        // and the rest of this method is the DICOM stack: an exception escaping
        // the notification observer left DCMTK, the store SCP, the database and
        // browser classes, the Web Portal, Bonjour and the XML-RPC interface
        // uninitialised, with the application still on screen and nothing but a
        // log line to say so.
        do {
            try HorosObjCException.perform {
                PluginManager.setMenus(self.filtersMenu, self.roisMenu, self.othersMenu, self.dbMenu)
            }
        } catch {
            if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, true, "-[AppController applicationWillFinishLaunching:]") }
        }

        appController = self
        AppControllerCAPIInitDCMTK(self)
        self.restartSTORESCP()


        DicomDatabase.initializeDicomDatabaseClass()
        BrowserController.initializeBrowserControllerClass()
        // #ifndef OSIRIX_LIGHT
        WebPortal.initializeWebPortalClass()
        let publisher = BonjourPublisher()
        _bonjourPublisher.withLockUnchecked { $0 = publisher }
        // #endif

        // #ifndef OSIRIX_LIGHT
        if UserDefaults.standard.bool(forKey: "httpXMLRPCServer") {
            if xmlrpcServer == nil { xmlrpcServer = XMLRPCInterface() }
        }
        // #endif

        let nc = NotificationCenter.default
        nc.addObserver(self,
                       selector: #selector(AppController.UpdateWLWWMenu(_:)),
                       name: .OsirixUpdateWLWWMenu,
                       object: nil)
        nc.addObserver(self,
                       selector: #selector(AppController.UpdateConvolutionMenu(_:)),
                       name: .OsirixUpdateConvolutionMenu,
                       object: nil)
        nc.addObserver(self,
                       selector: #selector(AppController.UpdateCLUTMenu(_:)),
                       name: .OsirixUpdateCLUTMenu,
                       object: nil)
        nc.addObserver(self,
                       selector: #selector(AppController.UpdateOpacityMenu(_:)),
                       name: .OsirixUpdateOpacityMenu,
                       object: nil)

        NotificationCenter.default.post(name: .OsirixUpdateOpacityMenu, object: NSLocalizedString("Linear Table", comment: "") as NSString, userInfo: nil)
        NotificationCenter.default.post(name: .OsirixUpdateCLUTMenu, object: NSLocalizedString("No CLUT", comment: "") as NSString, userInfo: nil)
        NotificationCenter.default.post(name: .OsirixUpdateWLWWMenu, object: NSLocalizedString("Other", comment: "") as NSString, userInfo: nil)
        NotificationCenter.default.post(name: .OsirixUpdateConvolutionMenu, object: NSLocalizedString("No Filter", comment: "") as NSString, userInfo: nil)

        NotificationCenter.default.addObserver(self, selector: #selector(AppController.applicationDidChangeScreenParameters(_:)), name: NSApplication.didChangeScreenParametersNotification, object: NSApp)

        self.updateScreenParameters()

//	if( USETOOLBARPANEL) [[toolbarPanel window] makeKeyAndOrderFront:self];

// Increment the startup counter.

        let startCount: Int = UserDefaults.standard.integer(forKey: "STARTCOUNT")
        UserDefaults.standard.set(startCount + 1, forKey: "STARTCOUNT")

        if startCount == 0 // Replaces FIRSTTIME.
        {
            switch HorosAlertPanel.runInformational(title: NSLocalizedString("Isis DICOM Viewer Updates", comment: ""), message: NSLocalizedString("Would you like to activate automatic checking for updates?", comment: ""), defaultButton: NSLocalizedString("Yes", comment: ""), alternateButton: NSLocalizedString("No", comment: ""), otherButton: nil)
            {
                case 0:
                    UserDefaults.standard.set("NO", forKey: "CheckHorosUpdates")
                default:
                    break
            }
        }
        else
        {
            if !UserDefaults.standard.bool(forKey: "SURVEYDONE5")
            {
//			if ([[NSUserDefaults standardUserDefaults] integerForKey: @"STARTCOUNT2"] > 20)
//			{
//				switch( NSRunInformationalAlertPanel(@"Horos", @"Thank you for using Horos!\rDo you agree to answer a small survey to improve Horos?", @"Yes, sure!", @"Maybe next time", nil))
//				{
//					case 1:
//					{
//						Survey		*survey = [[Survey alloc] initWithWindowNibName:@"Survey"];
//						[[survey window] center];
//						[survey showWindow:self];
//					}
//						break;
//				}
//			}

//			if( [[NSCalendarDate dateWithYear:2009 month:10 day:14 hour:12 minute:0 second:0 timeZone:[NSTimeZone timeZoneWithAbbreviation:@"EST"]] timeIntervalSinceNow] > 0 &&
//				[[NSCalendarDate dateWithYear:2009 month:9 day:1 hour:12 minute:0 second:0 timeZone:[NSTimeZone timeZoneWithAbbreviation:@"EST"]] timeIntervalSinceNow] < 0)
//			{
//				Survey *survey = [[Survey alloc] initWithWindowNibName:@"Survey"];
//				[[survey window] center];
//				[survey showWindow: self];
//			}
            }
            else
            {
            }
        }


        //Checks for Bonjour enabled dicom servers. Most likely other copies of Horos
        _ = DCMNetServiceDelegate.sharedNetServiceDelegate()

        previousDefaults = UserDefaults.standard.dictionaryRepresentation() as NSDictionary
        showRestartNeeded = true

        NotificationCenter.default.addObserver(self,
                                               selector: #selector(AppController.preferencesUpdated(_:)),
                                               name: UserDefaults.didChangeNotification,
                                               object: nil)

        UserDefaults.standard.set(true, forKey: "SAMESTUDY")

        UserDefaults.standard.set(AppController.hasMacOSXSnowLeopard(), forKey: "hasMacOSXSnowLeopard")

        if ((UserDefaults.standard.object(forKey: "HOTKEYS") as? NSDictionary)?.count ?? 0) < Int(SetKeyImageAction.rawValue) {
            let d = (UserDefaults.standard.object(forKey: "HOTKEYS") as? NSDictionary)?.mutableCopy() as? NSMutableDictionary

            var f = false
            for key in d?.allKeys ?? [] {
                if ObjC.integer(d?.object(forKey: key)) == Int(FullScreenAction.rawValue) {
                    f = true
                }

                if ObjC.integer(d?.object(forKey: key)) == Int(Sync3DAction.rawValue) {
                    f = true
                }

                if ObjC.integer(d?.object(forKey: key)) == Int(SetKeyImageAction.rawValue) {
                    f = true
                }
            }

            if f == false {
                d?.setObject(NSNumber(value: FullScreenAction.rawValue), forKey: "dbl-click" as NSString)
                d?.setObject(NSNumber(value: Sync3DAction.rawValue), forKey: "dbl-click + alt" as NSString)
                d?.setObject(NSNumber(value: SetKeyImageAction.rawValue), forKey: "dbl-click + cmd" as NSString)

                UserDefaults.standard.set(d, forKey: "HOTKEYS")
            }
        }


        self.initTilingWindows()

        do {
            let inc = DicomDatabase.activeLocal()?.incomingDirPath()
            let temporary = DicomDatabase.activeLocal()?.tempDirPath()
            // [NSArray arrayWithObjects: temporary, decompressionDirPath, nil]: stops at the first nil.
            let decompression = DicomDatabase.activeLocal()?.decompressionDirPath()
            let paths = NSMutableArray()
            if let temporary = temporary {
                paths.add(temporary)
                if let decompression = decompression { paths.add(decompression) }
            }
            for case let path as String in paths {
                let enumerator = FileManager.default.enumerator(atPath: path, filesOnly: false, recursive: false)
                for case let f as String in enumerator
                {
                    // JPEGs retained for Mail/Photos are outputs, not interrupted
                    // DICOM reception. Leave their original paths available.
                    if path == temporary &&
                        ImageExportPath.isPrivateExportDirectory(atPath: (path as NSString).appendingPathComponent(f)) {
                        continue
                    }
                    if let destination = (inc as NSString?)?.appendingPathComponent(f) {
                        try? FileManager.default.moveItem(atPath: (path as NSString).appendingPathComponent(f), toPath: destination)
                    }
                }
            }
        }
    }

    @IBAction @objc(updateViews:) public func updateViews(_ sender: Any!) {
        let winList = NSApp.windows

        for loopItem in winList
        {
            if let viewer = loopItem.windowController as? ViewerController
            {
                viewer.needsDisplayUpdate()
            }
        }
    }



    // MARK: -

    @objc nonisolated public class func isFDACleared() -> Bool {
        return false
    }

    @objc(displayUpdateMessage:) func displayUpdateMessage(_ msg: String!) {
        if msg == "LISTENER"
        {
            _ = HorosAlertPanel.run(title: NSLocalizedString("DICOM Listener Error", comment: ""), message: NSLocalizedString("Isis DICOM Viewer listener cannot start. Is the Port valid? Is there another process using this Port?\r\rSee Listener - Preferences.", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
        }

        #if !MACAPPSTORE
        if msg == "UPTODATE"
        {
            _ = HorosAlertPanel.run(title: NSLocalizedString("Isis DICOM Viewer is up-to-date", comment: ""), message: NSLocalizedString("You have the most recent version of Isis DICOM Viewer.", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
        }

        if msg == "ERROR"
        {
            _ = HorosAlertPanel.run(title: NSLocalizedString("No Internet connection", comment: ""), message: NSLocalizedString("Unable to check latest version available.", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
        }

        if msg == "UPDATECRASH"
        {
            _ = HorosAlertPanel.runInformational(title: NSLocalizedString("Isis DICOM Viewer crashed", comment: ""), message: NSLocalizedString("Isis DICOM Viewer crashed... You are running an outdated version of Isis DICOM Viewer ! This bug is probably corrected in the last version !", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)

            NSWorkspace.shared.open(UpdateFeedClient.releasesURL) // URL_HOROS_UPDATE_CRASH
        }

        if msg == "UPDATE"
        {
            let button = HorosAlertPanel.run(title: NSLocalizedString("New Version Available", comment: ""), message: NSLocalizedString("A new version of Isis DICOM Viewer is available. Would you like to download the new version now?", comment: ""), defaultButton: NSLocalizedString("Download", comment: ""), alternateButton: NSLocalizedString("Continue", comment: ""), otherButton: nil)

            if HorosAlertPanel.defaultResponse == button {
                NSWorkspace.shared.open(URL(string: "https://github.com/ThalesMMS/horos/releases")!) // URL_HOROS_UPDATE
            }
        }
        #endif
    }

    @objc public func splashScreen() -> Any! {
        var wait: WaitRendering? = nil

        // (OSIRIX_LIGHT: WaitRendering "Starting Horos Lite...", not compiled)
        if MemoryLayout<Int>.size == 8 {
            wait = WaitRendering(NSLocalizedString("Starting Isis DICOM Viewer 64-bit", comment: ""))
        }
        else {
            wait = WaitRendering(NSLocalizedString("Starting Isis DICOM Viewer 32-bit", comment: ""))
        }

        return wait
    }

    // #ifndef OSIRIX_LIGHT / #ifndef MACAPPSTORE (compiled)

    @IBAction @objc(checkForUpdatesDisabled:) nonisolated func checkForUpdatesDisabled(_ sender: Any!) {
        #if !MACAPPSTORE
        if UserDefaults.standard.bool(forKey: "CheckHorosUpdates") != false
        {
            DispatchQueue.global(qos: .default).async {
                DispatchQueue.main.async {
                    Thread.detachNewThreadSelector(#selector(AppController.checkForUpdates(_:)), toTarget: self, with: self)
                }
            }
        }
        else
        {
            let delayInSeconds: Double = 60
            DispatchQueue.global(qos: .default).asyncAfter(deadline: .now() + delayInSeconds) {
                DispatchQueue.main.async {
                    Thread.detachNewThreadSelector(#selector(AppController.checkForUpdatesDisabled(_:)), toTarget: self, with: self)
                }
            }
        }
        #endif
    }

    @IBAction @objc(checkForUpdates:) nonisolated public func checkForUpdates(_ sender: Any!) {
        #if !MACAPPSTORE
        // Capture per-request intent: automatic checks must not overwrite a manual check.
        let manualCheck = (sender as AnyObject?) !== self
        let afterCrash = (sender as? NSString)?.isEqual(to: "crash") == true
        let bundle = Bundle(for: type(of: self))
        let currentVersion = bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        let displayVersion = (bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? currentVersion

        UpdateFeedClient.fetch(url: UpdateFeedClient.stableFeedURL) { (release, error) in // URL_HOROS_VERSION
            // The Swift client delivers all outcomes on the main queue.
            guard let release = release else {
                if let error = error, manualCheck && !afterCrash {
                    _ = HorosAlertPanel.run(title: NSLocalizedString("Unable to Check for Updates", comment: ""),
                                            message: UpdateFeedClient.message(for: error),
                                            defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
                }
                return
            }
            let summary = UpdateFeedClient.summary(installedVersion: displayVersion ?? "",
                                                   build: currentVersion ?? "",
                                                   availableBuild: release.build)
            if !release.isNewer(than: currentVersion) {
                if manualCheck && !afterCrash {
                    _ = HorosAlertPanel.run(title: NSLocalizedString("Update Check Result", comment: ""), message: summary,
                                            defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
                }
            } else if UpdateInstaller.isBusy {
                // That release is already being downloaded or installed.
            } else if (UserDefaults.standard.bool(forKey: "CheckHorosUpdates") &&
                        !UserDefaults.standard.bool(forKey: "hideListenerError") && UpdateInstaller.isReleaseCopy &&
                        UpdateInstaller.postponedBuild != release.build) || manualCheck {
                // A development copy has no release build number, so it is told about a
                // release only when asked; nobody is asked hourly about the same release.
                UpdateInstaller.postponedBuild = release.build
                if UpdateInstaller.canInstall(release) {
                    let button = HorosAlertPanel.run(title: NSLocalizedString("New Stable Build Available", comment: ""),
                                                     message: summary + "\n\n" + NSLocalizedString("Isis DICOM Viewer will quit and reopen when the download finishes.", comment: "Update installation notice"),
                                                     defaultButton: NSLocalizedString("Download and Install", comment: ""),
                                                     alternateButton: NSLocalizedString("Cancel", comment: ""),
                                                     otherButton: NSLocalizedString("View Fork Releases", comment: ""))
                    if button == HorosAlertPanel.defaultResponse {
                        UpdateInstaller.install(release,
                            confirmQuit: { BrowserController.currentBrowser()?.shouldTerminate(self) ?? true },
                            quit: { self.finishTermination(self) })
                    } else if button == HorosAlertPanel.otherResponse {
                        NSWorkspace.shared.open(UpdateFeedClient.releasesURL) // URL_HOROS_UPDATE
                    }
                } else {
                    let button = HorosAlertPanel.run(title: NSLocalizedString("New Stable Build Available", comment: ""), message: summary,
                                                     defaultButton: NSLocalizedString("View Fork Releases", comment: ""),
                                                     alternateButton: NSLocalizedString("Continue", comment: ""), otherButton: nil)
                    if button == HorosAlertPanel.defaultResponse {
                        NSWorkspace.shared.open(UpdateFeedClient.releasesURL) // URL_HOROS_UPDATE
                    }
                }
            }
        }

        if manualCheck
        {
            return
        }

        if UserDefaults.standard.bool(forKey: "CheckHorosUpdates") != false
        {
            let delayInSeconds: Double = 3600
            DispatchQueue.global(qos: .default).asyncAfter(deadline: .now() + delayInSeconds) {
                DispatchQueue.main.async {
                    Thread.detachNewThreadSelector(#selector(AppController.checkForUpdates(_:)), toTarget: self, with: self)
                }
            }
        }
        else
        {
            let delayInSeconds: Double = 60
            DispatchQueue.global(qos: .default).asyncAfter(deadline: .now() + delayInSeconds) {
                DispatchQueue.main.async {
                    Thread.detachNewThreadSelector(#selector(AppController.checkForUpdatesDisabled(_:)), toTarget: self, with: self)
                }
            }
        }
        #endif
    }
    // #endif / #endif

    // Swift name urlResource...: a method named URL would hide the URL type in this class.
    @objc(URL:resourceDidFailLoadingWithReason:) func urlResource(_ sender: NSURL!, resourceDidFailLoadingWithReason reason: String!) {
        if verboseUpdateCheck {
            _ = HorosAlertPanel.run(title: NSLocalizedString("No connection available", comment: ""), message: ObjC.format("%@", reason), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
        }
    }

    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————
    // MARK: -

    @IBAction @objc(about:) public func about(_ sender: Any!) {
        splashController = SplashScreen()
        splashController?.showWindow(self)
        splashController?.affiche()
    }

    @IBAction @objc(printFromMenu:) public func printFromMenu(_ sender: Any!) {
        let controller = NSApp.keyWindow?.windowController
        if let browser = controller as? BrowserController {
            browser.printDatabaseSelection(sender)
        }
        else {
            _ = NSApp.sendAction(NSSelectorFromString("print:"), to: nil, from: sender)
        }
    }

    @objc(validatePrintFromMenu:) func validatePrintFromMenu(_ item: NSMenuItem!) -> Bool {
        if NSApp.keyWindow?.windowController is BrowserController {
            return true
        }

        // Preserve the existing responder and its validation in other windows.
        let target = NSApp.target(forAction: NSSelectorFromString("print:"), to: nil, from: item)
        if target == nil {
            return false
        }
        let legacyItem = item?.copy() as? NSMenuItem
        legacyItem?.action = NSSelectorFromString("print:")
        // The target may implement these without adopting the protocols: sent through their IMP, as ObjC sent the message.
        typealias ValidateIMP = @convention(c) (AnyObject, Selector, NSMenuItem?) -> Bool
        let validateMenuItemSelector = NSSelectorFromString("validateMenuItem:")
        let validateUserInterfaceItemSelector = NSSelectorFromString("validateUserInterfaceItem:")
        if let target = target as? NSObject, target.responds(to: validateMenuItemSelector) {
            return unsafeBitCast(target.method(for: validateMenuItemSelector), to: ValidateIMP.self)(target, validateMenuItemSelector, legacyItem)
        }
        if let target = target as? NSObject, target.responds(to: validateUserInterfaceItemSelector) {
            return unsafeBitCast(target.method(for: validateUserInterfaceItemSelector), to: ValidateIMP.self)(target, validateUserInterfaceItemSelector, legacyItem)
        }
        return true
    }

    @IBAction @objc(showPreferencePanel:) public func showPreferencePanel(_ sender: Any!) {
        PreferencesWindowController.sharedPreferencesWindowController().showWindow(sender)
    }


    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    deinit {
        NotificationCenter.default.removeObserver(self)

        AppController.listenerLock.withLock {
            dcmtkQRSCP = nil
            dcmtkQRSCPTLS = nil
        }
    }

    // The former file sent these messages to an id, whatever its class (some are
    // implemented by OSIWindowController only in its .m): they are sent the same
    // way here, a nil receiver answers 0/NO/nil, and a receiver that does not
    // answer raises the same exception.
    private func idSendBool(_ target: Any?, _ name: String) -> Bool {
        guard let object = target as? NSObject else { return false }
        typealias Imp = @convention(c) (AnyObject, Selector) -> ObjCBool
        let selector = NSSelectorFromString(name)
        return unsafeBitCast(object.method(for: selector), to: Imp.self)(object, selector).boolValue
    }

    private func idSendInteger(_ target: Any?, _ name: String) -> Int {
        guard let object = target as? NSObject else { return 0 }
        typealias Imp = @convention(c) (AnyObject, Selector) -> Int
        let selector = NSSelectorFromString(name)
        return unsafeBitCast(object.method(for: selector), to: Imp.self)(object, selector)
    }

    private func idSendVoid(_ target: Any?, _ name: String) {
        guard let object = target as? NSObject else { return }
        typealias Imp = @convention(c) (AnyObject, Selector) -> Void
        let selector = NSSelectorFromString(name)
        unsafeBitCast(object.method(for: selector), to: Imp.self)(object, selector)
    }

    private func idSendObject(_ target: Any?, _ name: String) -> AnyObject? {
        guard let object = target as? NSObject else { return nil }
        return object.perform(NSSelectorFromString(name))?.takeUnretainedValue()
    }

    /// [target setWindowFrame: frame showWindow: YES animate: YES]
    private func idSendSetWindowFrame(_ target: Any?, _ frame: NSRect) {
        guard let object = target as? NSObject else { return }
        typealias Imp = @convention(c) (AnyObject, Selector, NSRect, ObjCBool, ObjCBool) -> Void
        let selector = NSSelectorFromString("setWindowFrame:showWindow:animate:")
        unsafeBitCast(object.method(for: selector), to: Imp.self)(object, selector, frame, true, true)
    }

    /// [target compare: other]
    private func idSendCompare(_ target: AnyObject?, _ other: AnyObject?) -> ComparisonResult {
        guard let object = target as? NSObject else { return .orderedSame }
        typealias Imp = @convention(c) (AnyObject, Selector, AnyObject?) -> Int
        let selector = NSSelectorFromString("compare:")
        return ComparisonResult(rawValue: unsafeBitCast(object.method(for: selector), to: Imp.self)(object, selector, other)) ?? .orderedSame
    }

    /// [a isEqualToString: b]: NO when either is nil.
    private func idIsEqualToString(_ a: Any?, _ b: Any?) -> Bool {
        guard let a = a as? NSString, let b = b as? String else { return false }
        return a.isEqual(to: b)
    }

    /// [[[viewer fileList] objectAtIndex: 0] valueForKeyPath:@"series.study.studyInstanceUID"]
    private func idStudyInstanceUID(_ viewer: Any?) -> Any? {
        return ((idSendObject(viewer, "fileList") as? NSArray)?.object(at: 0) as? NSObject)?.value(forKeyPath: "series.study.studyInstanceUID")
    }

    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    // pixList is compared by identity: it is an NSArray here, not a bridged [Any], so
    // the viewer's own array is still the object compared.
    // A viewer whose window is closing is not returned: its -windowWillClose:
    // autoreleased it, and it goes when the pool drains, with the views of a
    // window shown again still on screen. A request made in that same pass of
    // the run loop opens a new viewer instead.
    @objc(FindViewer::) public func FindViewer(_ nib: String!, _ pixList: NSArray!) -> Any! {
        for loopItem in NSApp.windows {
            if let name = loopItem.windowController?.windowNibName, let nib = nib, (name as NSString).isEqual(to: nib) {
                if idSendObject(loopItem.windowController, "pixList") === pixList && !viewerWindowWillClose(loopItem.windowController) {
                    return loopItem.windowController
                }
            }
        }

        return nil
    }

    /// [controller windowWillClose], for the controllers that answer it
    /// (OSIWindowController and its subclasses); NO for the others.
    private func viewerWindowWillClose(_ controller: NSWindowController?) -> Bool {
        guard let controller = controller, controller.responds(to: NSSelectorFromString("windowWillClose")) else { return false }
        return idSendBool(controller, "windowWillClose")
    }

    @objc(FindRelatedViewers:) public func FindRelatedViewers(_ pixList: NSArray!) -> [Any]! {
        let viewersList = NSMutableArray()

        for loopItem in NSApp.windows {
            if loopItem.windowController?.responds(to: NSSelectorFromString("pixList")) ?? false {
                if idSendObject(loopItem.windowController, "pixList") === pixList {
                    if let controller = loopItem.windowController {
                        viewersList.add(controller)
                    }
                }
            }
        }

        return viewersList as? [Any]
    }

    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    @objc public func dbScreen() -> NSScreen! {
        //return screen if there is a reserved DB Screen otherwise return nil;
        if UserDefaults.standard.bool(forKey: "ReserveScreenForDB") == true {
            return dbWindow?.screen
        }
        return nil
    }

    @objc public func viewerScreens() -> [Any]! {
        var screens = (UserDefaults.standard.screensUsedForViewers() as NSArray?)?.mutableCopy() as? NSMutableArray
        if (screens?.count ?? 0) == 0 {
            screens = (NSScreen.screens as NSArray).mutableCopy() as? NSMutableArray
        }

        let dbScreen = dbWindow?.screen
        if UserDefaults.standard.bool(forKey: "ReserveScreenForDB") && (dbScreen.map { screens?.contains($0) ?? false } ?? false) && (screens?.count ?? 0) > 1 {
            if let dbScreen = dbScreen {
                screens?.removeObject(identicalTo: dbScreen)
            }
        }

        if (screens?.count ?? 0) == 0 {
            screens = (NSScreen.screens as NSArray).mutableCopy() as? NSMutableArray
        }

        // arrange them left to right
        screens?.sort(comparator: { o1, o2 in
            let f1 = (o1 as? NSScreen)?.frame ?? .zero, f2 = (o2 as? NSScreen)?.frame ?? .zero
            let c1: CGFloat = f1.origin.x+f1.size.width/2, c2: CGFloat = f2.origin.x+f2.size.width/2
            if c1 < c2 { return .orderedAscending }
            if c1 > c2 { return .orderedDescending }
            return .orderedSame
        })

        return screens as? [Any]
    }

    @objc(checkAllWindowsAreVisible:makeKey:) public func checkAllWindowsAreVisible(_ sender: Any!, makeKey: Bool) {
        if checkAllWindowsAreVisibleIsOff { return }

        let winList = NSApp.windows
        var last: NSWindow? = nil

        for loopItem in winList {
            if let viewer = loopItem.windowController as? ViewerController {
                if viewer.windowWillClose() == false {
                    last = loopItem
                    loopItem.orderFront(self)
                    viewer.checkBuiltMatrixPreview()
//				[[loopItem windowController] redrawToolbar];	// To avoid the drag & remove item bug - multiple windows
                }
            }
        }

        if makeKey {
            last?.makeKeyAndOrderFront(self)

            if UserDefaults.standard.bool(forKey: "syncPreviewList") {
                idSendVoid(last?.windowController, "syncThumbnails")
            }
        }
    }

    @objc(checkAllWindowsAreVisible:) public func checkAllWindowsAreVisible(_ sender: Any!) {
        self.checkAllWindowsAreVisible(sender, makeKey: false)
    }

    @objc(displayViewers:monitorIndex:screens:numberOfMonitors:rowsPerScreen:columnsPerScreen:)
    func displayViewers(_ viewers: NSArray!, monitorIndex: Int32, screens: NSArray!, numberOfMonitors: Int32, rowsPerScreen: Int32, columnsPerScreen: Int32) {
        var rowsPerScreen = rowsPerScreen, columnsPerScreen = columnsPerScreen
        let strechWindows = UserDefaults.standard.bool(forKey: "StrechWindows")
        var lastScreen = false

        if columnsPerScreen <= 0 {
            columnsPerScreen = 1
        }

        if rowsPerScreen <= 0 {
            rowsPerScreen = 1
        }

        let OcolumnsPerScreen = columnsPerScreen
        let OrowsPerScreen = rowsPerScreen

        var i: Int32 = 0
        while Int(i) < (viewers?.count ?? 0) {
            if monitorIndex == numberOfMonitors-1 && strechWindows == true && lastScreen == false {
                var remaining = Int32(truncatingIfNeeded: (viewers?.count ?? 0) - Int(i))

                if remaining < 0 {
                    remaining = 0
                }

                lastScreen = true

                while rowsPerScreen*columnsPerScreen > remaining && rowsPerScreen >= 0 && columnsPerScreen >= 0 {
                    rowsPerScreen -= 1

                    if rowsPerScreen*columnsPerScreen > remaining {
                        columnsPerScreen -= 1
                    }
                }

                if columnsPerScreen > 0 {
                    while rowsPerScreen*columnsPerScreen < remaining {
                        rowsPerScreen += 1
                    }
                }
            }

            if columnsPerScreen == 0 {
                columnsPerScreen = 1
            }

            let posInScreen = i % (OcolumnsPerScreen*OrowsPerScreen)
            let row = posInScreen / columnsPerScreen
            let column = posInScreen % columnsPerScreen

            var frame = AppController.usefullRect(for: screens?.object(at: Int(monitorIndex)) as? NSScreen)

            var temp: Int32

            temp = Int32(frame.size.width / CGFloat(columnsPerScreen))
            frame.size.width = CGFloat(temp * columnsPerScreen)

            temp = Int32(frame.size.height / CGFloat(rowsPerScreen))
            frame.size.height = CGFloat(temp * rowsPerScreen)

            let visibleFrame = frame
            frame.size.width /= CGFloat(columnsPerScreen)
            frame.origin.x += (frame.size.width * CGFloat(column))

            frame.size.height /= CGFloat(rowsPerScreen)
            frame.origin.y += frame.size.height * CGFloat((rowsPerScreen - 1) - row)

            if lastScreen {
                if Int(i + columnsPerScreen) >= (viewers?.count ?? 0) && strechWindows == true {
                    frame.size.height += frame.origin.y - visibleFrame.origin.y
                    frame.origin.y = visibleFrame.origin.y
                }
            }

            idSendSetWindowFrame(viewers?.object(at: Int(i)), frame)
            i += 1
        }
    }

    @objc func orderedScreens() -> NSArray! {
        let srcScreens = NSMutableArray(array: NSScreen.screens)
        let dstScreens = NSMutableArray()

        while srcScreens.count != 0 {
            var minY: Float = 1000000, minX: Float = 1000000

            var screen: NSScreen? = nil
            for case let s as NSScreen in srcScreens {
                if s.visibleFrame.origin.y <= CGFloat(minY) {
                    if s.visibleFrame.origin.x < CGFloat(minX) {
                        minY = Float(s.visibleFrame.origin.y)
                        minX = Float(s.visibleFrame.origin.x)
                        screen = s
                    }
                }
            }

            // A pass that picks no screen (a frame at or beyond a million points, or
            // not a number) would repeat forever: the rest keep the order they came in.
            guard let screen = screen else {
                dstScreens.addObjects(from: Array(srcScreens))
                break
            }
            dstScreens.add(screen)
            srcScreens.remove(screen)
        }

        return dstScreens
    }

    // ViewerController* in the former file, which also received the 3D viewers of
    // -tile3DWindows:: only -window is sent to it.
    @objc(currentRowForViewer:) func currentRowForViewer(_ v: NSWindowController!) -> Int32 {
        let ordered = self.orderedScreens()
        var index = NSNotFound
        if let screen = v?.window?.screen {
            index = ordered?.index(of: screen) ?? NSNotFound
        }
        var i = UInt(bitPattern: index)
        if index == NSNotFound { i = 0 }
        i += 1

        i *= 3000

        return Int32(CGFloat(i) - ((v?.window?.frame.origin.y ?? 0) + (3*(v?.window?.frame.size.height ?? 0))/4 - (v?.window?.screen?.visibleFrame.origin.y ?? 0)))
    }

    @objc(scaleToFit:) public func scaleToFit(_ sender: Any!) {
        let array = ViewerController.getDisplayed2DViewers()

        for case let v as ViewerController in (array as NSArray?) ?? NSArray() {
            v.imageView()?.scaleToFit()
        }
    }

    @objc(windowCenter:) func windowCenter(_ w: NSWindow!) -> NSPoint {
        let ordered = self.orderedScreens()
        var index = NSNotFound
        if let screen = w?.screen {
            index = ordered?.index(of: screen) ?? NSNotFound
        }
        var i = UInt(bitPattern: index)
        if index == NSNotFound { i = 0 }
        i += 1

        i *= 3000

        return NSMakePoint(CGFloat(i) + (w?.frame.origin.x ?? 0) + (w?.frame.size.width ?? 0)/2, CGFloat(i) + (w?.frame.origin.y ?? 0) + (w?.frame.size.height ?? 0)/2)
    }

    // MARK: -

    @objc(addStudyToRecentStudiesMenu:) public func addStudyToRecentStudiesMenu(_ studyID: NSManagedObjectID!) {
        if Thread.isMainThread == false {
            self.performSelector(onMainThread: #selector(AppController.addStudyToRecentStudiesMenu(_:)), with: studyID, waitUntilDone: false)
            return
        }

        if recentStudies == nil {
            recentStudies = NSMutableArray()
            recentStudiesAlbums = NSMutableDictionary()
        }

        // A nil studyID made -insertObject:atIndex: raise, which ended this method.
        guard let studyID = studyID else { return }

        recentStudies.remove(studyID)
        recentStudies.insert(studyID, at: 0)

        if let selectedAlbumName = BrowserController.currentBrowser()?.selectedAlbumName {
            recentStudiesAlbums.setObject(selectedAlbumName, forKey: studyID)
        }

        // NSUInteger > NSInteger: compared unsigned, as in C
        if UInt(recentStudies.count) > UInt(bitPattern: UserDefaults.standard.integer(forKey: "MaxNumberOfRecentStudies")) {
            recentStudies.removeLastObject()
        }

        self.buildRecentStudiesMenu()
    }

    @objc(loadRecentStudy:) public func loadRecentStudy(_ sender: Any!) {
        let item = sender as? NSMenuItem

        ViewerController.closeAllWindows()

        let db = BrowserController.currentBrowser()?.database
        let study = db?.object(withID: item?.representedObject) as? DicomStudy

        if let study = study, study.isDeleted == false {
            if let representedObject = item?.representedObject, let albumName = recentStudiesAlbums?.object(forKey: representedObject) {
                BrowserController.currentBrowser()?.selectAlbum(withName: albumName as? String)
            }

            BrowserController.currentBrowser()?.selectThisStudy(study)
            BrowserController.currentBrowser()?.databaseOpenStudy(study)
        }
    }

    @objc public func buildRecentStudiesMenu() {
        recentStudiesMenu?.removeAllItems()

        var studiesToRemove: [Any] = []
        let db = BrowserController.currentBrowser()?.database
        for studyID in recentStudies ?? NSMutableArray() {
            let study = db?.object(withID: studyID) as? DicomStudy
            if study == nil {
                studiesToRemove.append(studyID)
            } else if let study = study {
                let components = NSMutableArray()

                if let name = study.name, (name as NSString).length != 0 {
                    components.add(name)
                }

                if let date = study.date {
                    components.add(UserDefaults.dateTimeFormatter().string(from: date))
                }

                if let studyName = study.studyName, (studyName as NSString).length != 0 {
                    components.add(studyName)
                }

                if let modality = study.modality, (modality as NSString).length != 0 {
                    components.add(modality)
                }

                let title = NSAttributedString(string: components.componentsJoined(by: " / "), attributes: [NSAttributedString.Key.font: NSFont.boldSystemFont(ofSize: 14)])

                let menuItem = NSMenuItem(title: title.string, action: #selector(AppController.loadRecentStudy(_:)), keyEquivalent: "")

                menuItem.attributedTitle = title
                menuItem.target = self
                menuItem.representedObject = studyID

                recentStudiesMenu?.addItem(menuItem)
            }
        }

        recentStudies?.removeObjects(in: studiesToRemove)
    }

    // MARK: -

    @objc public func initTilingWindows() {
        for item in windowsTilingMenuRows?.items ?? [] {
            item.target = self
            item.action = #selector(AppController.setFixedTilingRows(_:))
        }

        for item in windowsTilingMenuColumns?.items ?? [] {
            item.target = self
            item.action = #selector(AppController.setFixedTilingColumns(_:))
        }

        self.buildTilingAreaMenu()
    }

    // Built here rather than in a nib: there is one nib per language, and this is a
    // list that belongs to HorosTilingArea. It goes next to the Rows and Columns
    // submenus, because it answers the question they raise - how much of the screen.
    @objc public func buildTilingAreaMenu() {
        let supermenu = windowsTilingMenuRows?.supermenu
        let at: Int = supermenu?.indexOfItem(withSubmenu: windowsTilingMenuRows) ?? 0
        guard let parent = supermenu, !(at < 0) else { return }

        let title = NSLocalizedString("Screen Area", comment: "")
        if parent.indexOfItem(withTitle: title) >= 0 { return }      // built already

        let areaItem = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        let areaMenu = NSMenu(title: title)
        areaMenu.autoenablesItems = false

        for name in TilingArea.presetNames {
            let item = NSMenuItem(title: NSLocalizedString(name, comment: ""),
                                  action: #selector(AppController.setTilingArea(_:)),
                                  keyEquivalent: "")
            item.target = self
            item.representedObject = name
            areaMenu.addItem(item)
        }

        areaItem.submenu = areaMenu
        parent.insertItem(areaItem, at: at + 1)
    }

    @IBAction @objc(setTilingArea:) public func setTilingArea(_ sender: Any!) {
        var screen = NSApp.keyWindow?.screen
        if screen == nil { screen = NSScreen.main }

        // A nil name reached +fractionsForPresetNamed: as an empty string.
        TilingArea.set(fractions: TilingArea.fractions(presetNamed: (idSendObject(sender, "representedObject") as? String) ?? ""),
                       for: screen)

        NSLog("Tiling area on \"%@\" is now %@; %@",
              TilingArea.identifier(for: screen) as NSString, ObjC.arg(idSendObject(sender, "representedObject")),
              NSStringFromRect(AppController.usefullRect(for: screen)) as NSString)

        // The floating panels place themselves from the screen parameters, and each
        // viewer has its own: without this only the front one would move, and the
        // others would stay across the part that was just reserved.
        NotificationCenter.default.post(name: NSApplication.didChangeScreenParametersNotification, object: NSApp)

        self.tileWindows(nil)
    }

    @IBAction @objc(setFixedTilingRows:) public func setFixedTilingRows(_ sender: Any!) {
        self.tileWindows(NSDictionary(object: NSNumber(value: Int32(truncatingIfNeeded: idSendInteger(sender, "tag"))), forKey: "rows" as NSString))
    }

    @IBAction @objc(setFixedTilingColumns:) public func setFixedTilingColumns(_ sender: Any!) {
        self.tileWindows(NSDictionary(object: NSNumber(value: Int32(truncatingIfNeeded: idSendInteger(sender, "tag"))), forKey: "columns" as NSString))
    }

    @objc(validateMenuItem:) public func validateMenuItem(_ item: NSMenuItem!) -> Bool {
        if !DistributionChannel.supportsGitHubUpdates && item?.action == NSSelectorFromString("checkForUpdates:") {
            return false
        }
        if item?.action == #selector(AppController.printFromMenu(_:)) {
            return self.validatePrintFromMenu(item)
        }

        if item?.action == #selector(AppController.setTilingArea(_:)) {
            var screen = NSApp.keyWindow?.screen
            if screen == nil { screen = NSScreen.main }

            let chosen = idIsEqualToString(TilingArea.presetName(for: screen), item?.representedObject)
            item?.state = chosen ? .on : .off
            item?.isEnabled = true
            return true
        }

        if item?.action == #selector(AppController.loadRecentStudy(_:)) {
            let db = BrowserController.currentBrowser()?.database

            for item in recentStudiesMenu?.items ?? [] {
                let study = db?.object(withID: item.representedObject) as? DicomStudy

                if study == nil || (study?.isDeleted ?? false) {
                    item.isEnabled = false
                    item.state = .off
                } else {
                    item.isEnabled = true

                    let objectIDs = ((ViewerController.getDisplayed2DViewers() as NSArray?)?.value(forKey: "currentStudy") as? NSArray)?.value(forKey: "objectID") as? NSArray
                    if let representedObject = item.representedObject, objectIDs?.contains(representedObject) ?? false {
                        item.state = .on
                    } else {
                        item.state = .off
                    }
                }
            }
            return true
        } else if item?.action == #selector(AppController.autoQueryRefresh(_:)) {
            // This test sat inside the tiling branch below, which never sees this
            // action, so the item stayed enabled without an auto query window.
            // #ifndef OSIRIX_LIGHT
            if QueryController.currentAuto() != nil {
                return true
            } else {
                return false
            }
        } else if item?.action == #selector(AppController.setFixedTilingRows(_:)) || item?.action == #selector(AppController.setFixedTilingColumns(_:)) {
            // [item tag] (NSInteger) <= [... count] (NSUInteger): compared unsigned, as in C
            if item?.action == #selector(AppController.setFixedTilingColumns(_:)) {
                if (item?.tag ?? 0) == Int(lastColumns) && UInt(bitPattern: item?.tag ?? 0) <= UInt((ViewerController.getDisplayed2DViewers() as NSArray?)?.count ?? 0) {
                    item?.state = .on
                } else {
                    item?.state = .off
                }
            }

            if item?.action == #selector(AppController.setFixedTilingRows(_:)) {
                if (item?.tag ?? 0) == Int(lastRows) && UInt(bitPattern: item?.tag ?? 0) <= UInt((ViewerController.getDisplayed2DViewers() as NSArray?)?.count ?? 0) {
                    item?.state = .on
                } else {
                    item?.state = .off
                }
            }

            if UInt(bitPattern: item?.tag ?? 0) > UInt((ViewerController.getDisplayed2DViewers() as NSArray?)?.count ?? 0) {
                return false
            }
        }
        return true
    }

    @objc(usefullRectForScreen:) public class func usefullRect(for screen: NSScreen!) -> NSRect {
        return AppController.usefullRect(for: screen, showFloatingWindows: true)
    }

    @objc(usefullRectForScreen:showFloatingWindows:) class func usefullRect(for screen: NSScreen!, showFloatingWindows: Bool) -> NSRect {
        // The area this screen is allowed to hold Horos windows, which is the whole
        // visible frame unless somebody reserved part of it for something else.
        // Narrowing first means the floating panels are taken out of the chosen
        // area, not out of the screen.
        var screenFrame = TilingArea.rect(for: screen, visibleFrame: screen?.visibleFrame ?? .zero)

        if showFloatingWindows {
            if AppController.usetoolbarpanel() || UserDefaults.standard.bool(forKey: "USEALWAYSTOOLBARPANEL2") == true {
                // 78 was 100 minus a 22-point menu bar, frozen in place. Both halves
                // move - the toolbar needs more than 100 now, and the menu bar is
                // not 22 - so the room the tiling leaves has to come from the panel
                // itself, or the windows are laid over the bottom of its labels.
                screenFrame.size.height -= CGFloat(ToolbarPanelController.exposedHeight())
            }

            if UserDefaults.standard.bool(forKey: "UseFloatingThumbnailsList") && UserDefaults.standard.bool(forKey: "SeriesListVisible") {
                screenFrame.origin.x += CGFloat(ThumbnailsListPanel.fixedWidth())
                screenFrame.size.width -= CGFloat(ThumbnailsListPanel.fixedWidth())
            }

            screenFrame = NavigatorView.adjustIfScreenAreaIf4DNavigator(screenFrame)
        }

        return screenFrame
    }

    @IBAction @objc(tileWindows:) public func tileWindows(_ sender: Any!) {
        let viewersList = NSMutableArray()

        //get 2D viewer windows
        for win in NSApp.orderedWindows {
            if let controller = win.windowController as? OSIWindowController {
                if controller.magnetic() {
                    if idSendBool(controller, "windowWillClose") == false && win.isMiniaturized == false {
                        viewersList.add(controller)
                    }

                    else if idSendBool(controller, "windowWillClose") {
                    }

                    if idSendBool(viewersList.lastObject, "FullScreenON") {
                        return
                    }
                }
            }

            win.animationBehavior = .none
        }

        self.tileWindows(sender, windows: viewersList, display2DViewerToolbar: useToolbarPanel, displayThumbnailsList: UserDefaults.standard.bool(forKey: "UseFloatingThumbnailsList"))

        BrowserController.currentBrowser()?.closeWaitWindowIfNecessary()
    }

    @IBAction @objc(tile3DWindows:) public func tile3DWindows(_ sender: Any!) {
        let viewersList = NSMutableArray()

        //get 2D viewer windows
        for win in NSApp.orderedWindows {
            if let controller = win.windowController as? Window3DController {
                if controller.windowWillClose() == false && win.isMiniaturized == false && win.isVisible == true {
                    viewersList.add(controller)
                }

                else if controller.windowWillClose() {
                }

                if idSendBool(viewersList.lastObject, "FullScreenON") {
                    return
                }
            }
        }

        self.tileWindows(sender, windows: viewersList, display2DViewerToolbar: false, displayThumbnailsList: false)

        for case let win as NSWindowController in viewersList {
            win.window?.makeKeyAndOrderFront(self)
        }
    }

    @objc(tileWindows:windows:display2DViewerToolbar:displayThumbnailsList:) public func tileWindows(_ sender: Any!, windows viewersList: NSMutableArray!, display2DViewerToolbar: Bool, displayThumbnailsList: Bool) {
        // Each use of a nil list read it as empty.
        var viewersList: NSMutableArray = viewersList ?? NSMutableArray()
        let origCopySettings = UserDefaults.standard.bool(forKey: "COPYSETTINGS")
        var screenRect = screenFrame()
        var keepSameStudyOnSameScreen = UserDefaults.standard.bool(forKey: "KeepStudiesTogetherOnSameScreen")
        let studyList = NSMutableArray()
        // ViewerController* in the former file, which also held the 3D viewers of -tile3DWindows:
        var keyWindow: AnyObject? = nil

        delayedTileWindows = 0 // NO

        AppController.checkForPreferencesUpdate(false)
        UserDefaults.standard.set(false, forKey: "COPYSETTINGS")
        AppController.checkForPreferencesUpdate(true)

        //order windows from left-top to right-bottom, per screen if necessary
        let cWindows = (viewersList.mutableCopy() as? NSMutableArray) ?? NSMutableArray()

        // Only the visible windows
        do {
            var i = Int32(truncatingIfNeeded: cWindows.count - 1)
            while i >= 0 {
                if ((cWindows.object(at: Int(i)) as? NSWindowController)?.window?.isVisible ?? false) == false { cWindows.removeObject(at: Int(i)) }
                i -= 1
            }
        }

        var screens = NSMutableArray(array: self.viewerScreens() ?? [])

        if viewersList.count < screens.count && UserDefaults.standard.bool(forKey: "UseDBScreenAtLast") {
            let dbscreen = dbWindow?.screen
            if let dbscreen = dbscreen {
                screens.removeObject(identicalTo: dbscreen)
            }
        }

        if screens.count <= 0 {
            screens = NSMutableArray(array: self.viewerScreens() ?? [])
        }

        let numberOfMonitors = Int32(truncatingIfNeeded: screens.count)

        let cResult = NSMutableArray()

        do {
            try HorosObjCException.perform {
                var count = Int32(truncatingIfNeeded: cWindows.count)
                while count > 0 {
                    var index: Int32 = 0
                    var row = self.currentRowForViewer(cWindows.object(at: Int(index)) as? NSWindowController)

                    var x: Int32 = 0
                    while Int(x) < cWindows.count {
                        if self.currentRowForViewer(cWindows.object(at: Int(x)) as? NSWindowController) < row {
                            row = self.currentRowForViewer(cWindows.object(at: Int(x)) as? NSWindowController)
                            index = x
                        }
                        x += 1
                    }

                    var minX = Float(self.windowCenter((cWindows.object(at: Int(index)) as? NSWindowController)?.window).x)

                    x = 0
                    while Int(x) < cWindows.count {
                        if self.windowCenter((cWindows.object(at: Int(x)) as? NSWindowController)?.window).x < CGFloat(minX) && self.currentRowForViewer(cWindows.object(at: Int(x)) as? NSWindowController) <= row {
                            minX = Float(self.windowCenter((cWindows.object(at: Int(x)) as? NSWindowController)?.window).x)
                            index = x
                        }
                        x += 1
                    }

                    cResult.add(cWindows.object(at: Int(index)))
                    cWindows.removeObject(at: Int(index))
                    count -= 1
                }
            }
        } catch {
            NSLog("***** 1: %@", ObjC.arg(ObjC.exception(error)))
        }

        let hiddenWindows = NSMutableArray()

        // Add the hidden windows
        for v in viewersList {
            if ((v as? NSWindowController)?.window?.isVisible ?? false) == false {
                hiddenWindows.add(v)
                cResult.add(v)

                keyWindow = v as AnyObject
            }
        }

        viewersList = cResult

        if keyWindow == nil {
            for v in viewersList {
                if (v as? NSWindowController)?.window?.isKeyWindow ?? false {
                    keyWindow = v as AnyObject
                }
            }
        }

        var identical = true

        if UserDefaults.standard.bool(forKey: "tileWindowsOrderByStudyDate") {
            if hiddenWindows.count != 0 {
                hiddenWindows.removeAllObjects()
            }

            viewersList.sort(comparator: { obj1, obj2 in
                let date1 = self.idSendObject(self.idSendObject(obj1, "currentStudy"), "date")
                let date2 = self.idSendObject(self.idSendObject(obj2, "currentStudy"), "date")

                if UserDefaults.standard.bool(forKey: "reversedTileWindowsOrderByStudyDate") {
                    return self.idSendCompare(date1, date2)
                } else {
                    return self.idSendCompare(date2, date1)
                }
            })
        }

        if keepSameStudyOnSameScreen {
            // Are there different studies
            if viewersList.count != 0 {
                let studyUID = idStudyInstanceUID(viewersList.object(at: 0))

                //get 2D viewer study arrays
                var i: Int32 = 0
                while Int(i) < viewersList.count {
                    if idIsEqualToString(idStudyInstanceUID(viewersList.object(at: Int(i))), studyUID) == false {
                        identical = false
                    }
                    i += 1
                }
            }
        }

        do {
            try HorosObjCException.perform {
                if keepSameStudyOnSameScreen == true && identical == false {
                    //get 2D viewer study arrays
                    var i: Int32 = 0
                    while Int(i) < viewersList.count {
                        let studyUID = self.idStudyInstanceUID(viewersList.object(at: Int(i)))

                        var found = false
                        // loop through and add to correct array if present
                        var x: Int32 = 0
                        while Int(x) < studyList.count {
                            if self.idIsEqualToString(self.idStudyInstanceUID((studyList.object(at: Int(x)) as? NSArray)?.object(at: 0)), studyUID) {
                                (studyList.object(at: Int(x)) as? NSMutableArray)?.add(viewersList.object(at: Int(i)))
                                found = true
                            }
                            x += 1
                        }
                        // create new array for current UID
                        if found == false {
                            studyList.add(NSMutableArray())
                            (studyList.lastObject as? NSMutableArray)?.add(viewersList.object(at: Int(i)))
                        }
                        i += 1
                    }
                }
                else { keepSameStudyOnSameScreen = false }
            }
        } catch {
            NSLog("***** 2: %@", ObjC.arg(ObjC.exception(error)))
        }

        let viewerCount = Int32(truncatingIfNeeded: viewersList.count)

        screenRect = (screens.object(at: 0) as? NSScreen)?.visibleFrame ?? .zero

        let landscape = (screenRect.size.width/screenRect.size.height > 1) ? true : false

        var landscapeRatio: Float = 1.5

        if screenRect.size.width/screenRect.size.height > 1.7 { // 16/9 screen or more
            landscapeRatio = 2.0
        }

        var portraitRatio: Float = 0.9

        if screenRect.size.height/screenRect.size.width > 1.7 { // 16/9 screen or more
            portraitRatio = 0.49
        }

        var rows = WindowLayoutManager.shared()?.windowsRows() ?? 0
        var columns = WindowLayoutManager.shared()?.windowsColumns() ?? 0

        if let senderDictionary = sender as? NSDictionary {
            if ObjC.int(senderDictionary.object(forKey: "rows")) != 0 && ObjC.int(senderDictionary.object(forKey: "columns")) != 0 {
                rows = ObjC.int(senderDictionary.object(forKey: "rows"))
                columns = ObjC.int(senderDictionary.object(forKey: "columns"))
            }
            else if ObjC.int(senderDictionary.object(forKey: "rows")) != 0 {
                rows = ObjC.int(senderDictionary.object(forKey: "rows"))
                columns = Int32(floor(Double(Float(viewerCount) / Float(rows))))
            }
            else if ObjC.int(senderDictionary.object(forKey: "columns")) != 0 {
                columns = ObjC.int(senderDictionary.object(forKey: "columns"))
                rows = Int32(floor(Double(Float(viewerCount) / Float(columns))))
            }

            if ObjC.int(senderDictionary.object(forKey: "Rows")) != 0 && ObjC.int(senderDictionary.object(forKey: "Columns")) != 0 {
                rows = ObjC.int(senderDictionary.object(forKey: "Rows"))
                columns = ObjC.int(senderDictionary.object(forKey: "Columns"))
            }
            else if ObjC.int(senderDictionary.object(forKey: "Rows")) != 0 {
                rows = ObjC.int(senderDictionary.object(forKey: "Rows"))
                columns = Int32(floor(Double(Float(viewerCount) / Float(rows))))
            }
            else if ObjC.int(senderDictionary.object(forKey: "Columns")) != 0 {
                columns = ObjC.int(senderDictionary.object(forKey: "Columns"))
                rows = Int32(floor(Double(Float(viewerCount) / Float(columns))))
            }
        }
        else if WindowLayoutManager.shared()?.currentHangingProtocol == nil || viewerCount < rows * columns {
            if landscape {
                columns = 2 * numberOfMonitors
                rows = 1
            }
            else {
                columns = numberOfMonitors
                rows = 2
            }
        }

        if rows <= 0 {
            rows = 1
        }

        if columns <= 0 {
            columns = 1
        }

        //excess viewers. Need to add spaces to accept
        if viewerCount > (rows * columns) {
            let ratioValue: Float

            if landscape { ratioValue = landscapeRatio }
            else { ratioValue = portraitRatio }

            let viewerCountPerScreen = Float(viewerCount) / Float(numberOfMonitors)
            var columnsPerScreen = Int32(ceil(Double(Float(columns) / Float(numberOfMonitors))))

            var fixedRows = false, fixedColumns = false

            if let senderDictionary = sender as? NSDictionary, senderDictionary.object(forKey: "rows") != nil {
                fixedRows = true
            }

            if let senderDictionary = sender as? NSDictionary, senderDictionary.object(forKey: "columns") != nil {
                fixedColumns = true
            }

            while viewerCountPerScreen > Float(rows * columnsPerScreen) {
                if fixedRows {
                    columnsPerScreen += 1
                } else if fixedColumns {
                    rows += 1
                } else {
                    let ratio = Float(columnsPerScreen) / Float(rows)

                    if ratio > ratioValue {
                        rows += 1
                    } else {
                        columnsPerScreen += 1
                    }
                }
            }

            let intViewerCountPerScreen = Int32(ceilf(viewerCountPerScreen))

            if rows * columnsPerScreen > intViewerCountPerScreen && rows*(columnsPerScreen-1) == intViewerCountPerScreen {
                columnsPerScreen -= 1
            }

            if rows * columnsPerScreen > intViewerCountPerScreen && columnsPerScreen*(rows-1) == intViewerCountPerScreen {
                rows -= 1
            }

            columns = columnsPerScreen * numberOfMonitors
        }

        // Smart arrangement if one window was added or removed
        if numberOfMonitors == 1 {
            do {
                try HorosObjCException.perform {
                    if self.lastColumns != columns {
                        if Int(self.lastCount) == viewersList.count - 1 {	// One window was added
                            if Int(columns) < viewersList.count {
                                // Not nil: the list holds more viewers than columns.
                                if let lastObject = viewersList.lastObject {
                                    viewersList.insert(lastObject, at: Int(self.lastColumns))
                                }
                                viewersList.removeObject(at: viewersList.count - 1)
                            }

                        }

//				if( lastCount == [viewersList count] +1)	// One window was removed
//				{
//					if( viewersAddresses)
//					{
//						// Try to find the missing Viewer
//
//						for( int i = 0 ; i < [viewersAddresses count]; i++)
//						{
//							if( [viewersList containsObject: [[viewersAddresses objectAtIndex: i] nonretainedObjectValue]] == NO)
//							{
//								// We found the missing viewer
//								[viewersList insertObject: [viewersList lastObject] atIndex: i];
//								[viewersList removeObjectAtIndex: [viewersList count]-1];
//								break;
//							}
//						}
//					}
//				}
                    }
                }
            } catch {
                if let e = ObjC.exception(error) { _N2LogExceptionImpl(e, true, "-[AppController tileWindows:windows:display2DViewerToolbar:displayThumbnailsList:]") }
            }

        }

        self.lastColumns = columns
        self.lastRows = rows
        self.lastCount = Int32(truncatingIfNeeded: viewersList.count)

//	if( viewersAddresses == nil)
//		viewersAddresses = [[NSMutableArray array] retain];
//
//	[viewersAddresses removeAllObjects];
//	for( id v in viewersList)
//		[viewersAddresses addObject: [NSValue valueWithNonretainedObject: v]];

        accumulateAnimations = true

        if keepSameStudyOnSameScreen && numberOfMonitors > 1 {
            var columnsForThisScreen = columns
            var rowsForThisScreen = rows

            columnsForThisScreen = Int32(ceil(Double(Float(columns) / Float(numberOfMonitors))))

            do {
                try HorosObjCException.perform {
                    NSLog("Tile Windows with keepSameStudyOnSameScreen == YES")

                    var i: Int32 = 0
                    while i < numberOfMonitors && Int(i) < studyList.count {
                        let viewersForThisScreen = (studyList.object(at: Int(i)) as? NSMutableArray) ?? NSMutableArray()

                        if i == numberOfMonitors - 1 || Int(i) == studyList.count - 1 {
                            // Take all remaining studies

                            var x = i + 1
                            while Int(x) < studyList.count {
                                viewersForThisScreen.addObjects(from: (studyList.object(at: Int(x)) as? [Any]) ?? [])
                                x += 1
                            }
                        }

                        if viewersForThisScreen.count > Int(rowsForThisScreen * columnsForThisScreen) {
                            do {
                                let ratioValue: Float

                                if landscape { ratioValue = landscapeRatio }
                                else { ratioValue = portraitRatio }

                                var fixedRows = false, fixedColumns = false

                                if let senderDictionary = sender as? NSDictionary, senderDictionary.object(forKey: "rows") != nil {
                                    fixedRows = true
                                }

                                if let senderDictionary = sender as? NSDictionary, senderDictionary.object(forKey: "columns") != nil {
                                    fixedColumns = true
                                }

                                while viewersForThisScreen.count > Int(rowsForThisScreen * columnsForThisScreen) {
                                    if fixedRows {
                                        columnsForThisScreen += 1
                                    } else if fixedColumns {
                                        rowsForThisScreen += 1
                                    } else {
                                        let ratio = Float(columnsForThisScreen) / Float(rowsForThisScreen)

                                        if ratio > ratioValue {
                                            rowsForThisScreen += 1
                                        } else {
                                            columnsForThisScreen += 1
                                        }
                                    }
                                }

                                let intViewerCountPerScreen = Int32(ceilf(Float(viewersForThisScreen.count)))

                                if rowsForThisScreen * columnsForThisScreen > intViewerCountPerScreen && rowsForThisScreen*(columnsForThisScreen-1) == intViewerCountPerScreen {
                                    columnsForThisScreen -= 1
                                }

                                if rowsForThisScreen * columnsForThisScreen > intViewerCountPerScreen && columnsForThisScreen*(rowsForThisScreen-1) == intViewerCountPerScreen {
                                    rowsForThisScreen -= 1
                                }

                                columns = columnsForThisScreen * numberOfMonitors
                            }
                        }

                        self.displayViewers(viewersForThisScreen, monitorIndex: i, screens: screens, numberOfMonitors: i+1, rowsPerScreen: rowsForThisScreen, columnsPerScreen: columnsForThisScreen)
                        i += 1
                    }

                }
            } catch {
                NSLog("***** 3: %@", ObjC.arg(ObjC.exception(error)))
            }
        }

        // if monitor count is greater than or equal to viewers. One viewer per window

        else if viewerCount <= numberOfMonitors {
            let count = Int32(truncatingIfNeeded: viewersList.count)

            for i in 0..<count {
                let frame = AppController.usefullRect(for: screens.object(at: Int(i)) as? NSScreen, showFloatingWindows: display2DViewerToolbar)

                idSendSetWindowFrame(viewersList.object(at: Int(i)), frame)
            }

            self.lastRows = 1
            self.lastColumns = numberOfMonitors
        }

        /* Will have columns but no rows.
         There are more columns than monitors.
          Need to separate columns among the window evenly  */

        else if (viewerCount <= columns) && (viewerCount % numberOfMonitors == 0) {
            let viewersPerScreen = viewerCount / numberOfMonitors
            for i in 0..<viewerCount {
                let index = i/viewersPerScreen
                let viewerPosition = i % viewersPerScreen
                var frame = AppController.usefullRect(for: screens.object(at: Int(index)) as? NSScreen, showFloatingWindows: display2DViewerToolbar)

                frame.size.width /= CGFloat(viewersPerScreen)
                frame.origin.x += (frame.size.width * CGFloat(viewerPosition))

                idSendSetWindowFrame(viewersList.object(at: Int(i)), frame)
            }

            self.lastRows = 1
            self.lastColumns = viewerCount
        }
        //have different number of columns in each window
        else if viewerCount <= columns {
            let columnsPerScreen = Int32(ceil(Double(Float(columns) / Float(numberOfMonitors))))
            let extraViewers = viewerCount % numberOfMonitors

            for i in 0..<viewerCount {
                let monitorIndex = i / columnsPerScreen
                let viewerPosition = i % columnsPerScreen
                let screen = screens.object(at: Int(monitorIndex)) as? NSScreen
                var frame = AppController.usefullRect(for: screen, showFloatingWindows: display2DViewerToolbar)

                if monitorIndex < extraViewers {
                    frame.size.width /= CGFloat(columnsPerScreen)
                } else {
                    frame.size.width /= CGFloat(columnsPerScreen - 1)
                }

                frame.origin.x += (frame.size.width * CGFloat(viewerPosition))

                if hiddenWindows.count != 0 {	// We have new viewers to insert !
                    if (viewersList.object(at: Int(i)) as? NSWindowController)?.window?.screen !== screen {
                        viewersList.remove(hiddenWindows.object(at: 0))
                        viewersList.insert(hiddenWindows.object(at: 0), at: Int(i))

                        hiddenWindows.remove(hiddenWindows.object(at: 0))
                    }
                }

                idSendSetWindowFrame(viewersList.object(at: Int(i)), frame)

                hiddenWindows.remove(viewersList.object(at: Int(i)))
            }

            self.lastRows = 1
            self.lastColumns = viewerCount
        }
        //adjust for actual number of rows needed
        else if viewerCount <= columns * rows {
            var columnsPerScreen = columns
            let rowsPerScreen = rows

            columnsPerScreen = Int32(ceil(Double(Float(columns) / Float(numberOfMonitors))))


            let viewersForThisScreen = NSMutableArray()

            var previousIndex: Int32 = 0
            var monitorIndex: Int32 = 0

            if viewerCount != 0 {
                for i in 0..<viewerCount {
                    monitorIndex = i / (columnsPerScreen*rowsPerScreen)

                    if monitorIndex == numberOfMonitors { monitorIndex = numberOfMonitors-1 }

                    let screen = screens.object(at: Int(monitorIndex)) as? NSScreen

                    if monitorIndex != previousIndex {
                        self.displayViewers(viewersForThisScreen, monitorIndex: previousIndex, screens: screens, numberOfMonitors: numberOfMonitors, rowsPerScreen: rowsPerScreen, columnsPerScreen: columnsPerScreen)
                        viewersForThisScreen.removeAllObjects()

                        previousIndex = monitorIndex
                    }

                    if hiddenWindows.count != 0 {	// We have new viewers to insert !
                        if (viewersList.object(at: Int(i)) as? NSWindowController)?.window?.screen !== screen {
                            viewersList.remove(hiddenWindows.object(at: 0))
                            viewersList.insert(hiddenWindows.object(at: 0), at: Int(i))

                            hiddenWindows.remove(hiddenWindows.object(at: 0))
                        }
                    }

                    viewersForThisScreen.add(viewersList.object(at: Int(i)))

                    hiddenWindows.remove(viewersList.object(at: Int(i)))
                }

                if viewersForThisScreen.count != 0 {
                    self.displayViewers(viewersForThisScreen, monitorIndex: monitorIndex, screens: screens, numberOfMonitors: numberOfMonitors, rowsPerScreen: rowsPerScreen, columnsPerScreen: columnsPerScreen)
                }
            }
        }
        else {
            NSLog("NO tiling")
        }

        // int / NSUInteger: an unsigned division, as in C; arm64 answered 0 for a division by zero, where Swift traps.
        let viewerScreensCount = UInt(AppController.shared()?.viewerScreens()?.count ?? 0)
        var p = Int32(truncatingIfNeeded: viewerScreensCount == 0 ? 0 : UInt(bitPattern: Int(self.lastColumns)) / viewerScreensCount)
        if p < 1 {
            p = 1
        }

        UserDefaults.standard.set(String(format: "%d%d", self.lastRows, p), forKey: "LastWindowsTilingRowsColumns")

        accumulateAnimations = false
        if (accumulateAnimationsArray?.count ?? 0) != 0 {
            OSIWindowController.setDontEnterMagneticFunctions(true)
            OSIWindowController.setDontEnterWindowDidChangeScreen(true)

            let animation = NSViewAnimation(viewAnimations: (accumulateAnimationsArray as? [[NSViewAnimation.Key: Any]]) ?? [])
            animation.animationBlockingMode = .blocking

            if accumulateAnimationsArray?.count == 1 {
                animation.duration = 0.20
            } else {
                animation.duration = 0.40
            }
            animation.start()

            accumulateAnimationsArray = nil

            OSIWindowController.setDontEnterMagneticFunctions(false)
            OSIWindowController.setDontEnterWindowDidChangeScreen(false)
        }

        AppController.checkForPreferencesUpdate(false)
        UserDefaults.standard.set(origCopySettings, forKey: "COPYSETTINGS")
        AppController.checkForPreferencesUpdate(true)


        var screenIndex = 0
        while screenIndex < NSScreen.screens.count {
            thumbnailsListPanelAt(screenIndex)?.setThumbnailsView(nil, viewer: nil)
            screenIndex += 1
        }

        if keyWindow == nil {
            keyWindow = ViewerController.frontMostDisplayed2DViewer(for: nil)
        }

        if viewersList.count > 0 && keyWindow != nil {
            DCMView.setDontListenToSyncMessage(true)

            (keyWindow as? NSWindowController)?.window?.makeKeyAndOrderFront(self)
            idSendVoid(keyWindow, "propagateSettings")

            for v in viewersList.reverseObjectEnumerator().allObjects {
                if let viewer = v as? ViewerController {
                    if viewer !== keyWindow {
                        // hiddenWindows holds the viewers, not their windows.
                        viewer.buildMatrixPreview(hiddenWindows.contains(viewer))
//                    [v redrawToolbar]; this is very slow if several windows are displayed : cannot reproduce the bug// To avoid the drag & remove item bug - multiple windows
                    }
                }
            }

            ToolbarPanelController.checkForValidToolbar()

            if let keyViewer = keyWindow as? ViewerController {
                keyViewer.imageView()?.becomeMainWindow()
                keyViewer.buildMatrixPreview(true)

                keyViewer.redrawToolbar()
            }

            if UserDefaults.standard.bool(forKey: "syncPreviewList") {
                idSendVoid(keyWindow, "syncThumbnails")
            }

            DCMView.setDontListenToSyncMessage(false)
        }
    }


    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    @IBAction @objc(closeAllViewers:) public func closeAllViewers(_ sender: Any!) {
        // Is there a full screen window displayed?
        for window in NSApp.orderedWindows {
            if window is NSFullScreenWindow {
                NSSound.beep()
                return
            }
        }

        ViewerController.closeAllWindows()
    }

    //———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

    // MARK: -
    // MARK: HTML Templates
    @available(*, deprecated) @objc public class func checkForHTMLTemplates() { // __deprecated
        BrowserController.currentBrowser()?.database?.checkForHtmlTemplates()
    }

    // MARK: -
    // MARK: 12 Bit Display support.

    @objc public class func canDisplay12Bit() -> Bool {
        return State.canDisplay12Bit
    }

    @objc(setCanDisplay12Bit:) public class func setCanDisplay12Bit(_ boo: Bool) {
        State.canDisplay12Bit = boo
        UserDefaults.standard.set(boo, forKey: "is12bitPluginAvailable")
    }

    @objc(setLUT12toRGB:) public class func setLUT12toRGB(_ lut: UnsafeMutablePointer<UInt8>!) {
        State.LUT12toRGB = lut
    }

    @objc public class func LUT12toRGB() -> UnsafeMutablePointer<UInt8>! {
        return State.LUT12toRGB
    }

    // Swift cannot name NSInvocation: the invocation is kept and answered as an
    // object, and the generated interface declares it as id.
    @objc(set12BitInvocation:) public class func set12BitInvocation(_ invocation: AnyObject!) {
        State.fill12BitBufferInvocation = invocation
    }

    @objc public class func fill12BitBufferInvocation() -> AnyObject! {
        return State.fill12BitBufferInvocation
    }

    // MARK: -

    @objc nonisolated func defaultWebPortalManagedObjectContext() -> NSManagedObjectContext! {
        // The former @try returned from the method.
        var returned = false
        var context: NSManagedObjectContext? = nil
        do {
            try HorosObjCException.perform {
                // #ifndef OSIRIX_LIGHT
                context = WebPortal.default()?.database?.managedObjectContext
                returned = true
            }
        } catch {
            NSLog("***** defaultWebPortalManagedObjectContext : %@", ObjC.arg(ObjC.exception(error)))
        }
        if returned { return context }

        // static NSManagedObjectContext *fakeContext
        return State.fakeContextLock.withLock {
            if State.fakeContext == nil {
                // The UI binds to it: a main-queue context, with no store (#967).
                State.fakeContext = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
                let model = NSManagedObjectModel(contentsOf: URL(fileURLWithPath: ((Bundle.main.resourcePath ?? "") as NSString).appendingPathComponent("/WebPortalDB.momd")))
                let psc = model.map { NSPersistentStoreCoordinator(managedObjectModel: $0) }
                State.fakeContext?.persistentStoreCoordinator = psc
            }
            return State.fakeContext
        }
    }

    @objc nonisolated public func defaultWebPortal() -> WebPortal! {
        // (OSIRIX_LIGHT: returned nil, not compiled)
        return WebPortal.default()
    }

    // #ifndef OSIRIX_LIGHT

    @objc nonisolated public func weasisBasePath() -> String! {
        return (Bundle.main.resourcePath as NSString?)?.appendingPathComponent("weasis")
    }

    // #endif

    // static NSMutableDictionary* _receivingDict → State.receivingDict

    @objc func _receivingIconUpdate() {
        // Counted under the same @synchronized (self) as the listener threads
        // that change the dictionary (#1005).
        let receiving = receivingThreadCount()
        if receiving == 0 {
            NSApp.applicationIconImage = NSImage(named: "Isis.icns")
        } else { NSApp.applicationIconImage = NSImage(named: "IsisDownload.icns") }
    }

    nonisolated private func receivingThreadCount() -> Int {
        objc_sync_enter(self); defer { objc_sync_exit(self) }
        return State.receivingDict?.count ?? 0
    }

    @objc(_receivingIconSet:) nonisolated func _receivingIconSet(_ flag: Bool) {
        do {
            objc_sync_enter(self); defer { objc_sync_exit(self) }
            if State.receivingDict == nil {
                State.receivingDict = NSMutableDictionary()
            }

            // The key is the thread's address. The thread is retained once while it
            // has an entry, so that the address cannot be reused by another thread,
            // and released when the entry goes: not once per call.
            let thread = Thread.current
            let threadValue = NSValue(pointer: Unmanaged.passUnretained(thread).toOpaque())
            let setCount = State.receivingDict?.object(forKey: threadValue) as? N2MutableUInteger

            if flag {
                if setCount == nil {
                    State.receivingDict?.setObject(N2MutableUInteger.mutableUInteger(with: 1), forKey: threadValue)
                    _ = Unmanaged.passRetained(thread)
                } else { setCount?.increment() }
            } else {
                if let setCount = setCount {
                    if setCount.unsignedIntegerValue > 0 {
                        setCount.decrement()
                    }
                    if setCount.unsignedIntegerValue == 0 {
                        State.receivingDict?.removeObject(forKey: threadValue)
                        Unmanaged.passUnretained(thread).release()
                    }
                }
            }

            self.performSelector(onMainThread: #selector(AppController._receivingIconUpdate), with: nil, waitUntilDone: false)
        }
    }

    @objc nonisolated public func setReceivingIcon() {
        self._receivingIconSet(true)
    }

    @objc nonisolated public func unsetReceivingIcon() {
        self._receivingIconSet(false)
    }

    @objc(setBadgeLabel:) nonisolated public func setBadgeLabel(_ label: String!) {
        // The database sets it from its import threads: on the main thread now
        // or later.
        let label: String? = label
        onMainActor {
            NSApp.dockTile.badgeLabel = label
            NSApp.dockTile.display()
        }
    }

    @objc public func playGrabSound() {
        let path = "/System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds/system/Grab.aif"
        let sound = NSSound(contentsOfFile: path, byReference: false)
        sound?.delegate = self
        sound?.play()
    }

    public func sound(_ sound: NSSound, didFinishPlaying finishedPlaying: Bool) {
        var sound: NSSound? = sound   // the former code set its parameter to nil
        sound = nil
        _ = sound
    }


    // //////////////////////////////////////////////////////////////////////////////////////////////////


    // MARK: -
    // #pragma FeedbackReporter


    @objc func crash() {
        NSLog("crash")
        // Preserve the intentional segmentation fault used by crash reporting.
        _ = Darwin.raise(SIGSEGV)
    }


    @objc func setupCrashReporter() -> Bool {
        NSLog("Unicode test: مرحبا - 你好 - שלום")

        // #if defined(USEFEEDBACKREPORTER): the delegate and -reportIfCrash, in AppController+CAPI.m
        return AppControllerCAPISetupFeedbackReporter(self)
    }

    // The reporter fills the tabs of its window on a queue of its own and asks
    // its delegate for the preferences from there. These three answers touch no
    // state of the application, and they are not isolated to the main actor: when
    // they were, the question from that queue ended the application the moment
    // the crash report window opened.
    @objc nonisolated func feedbackDisplayName() -> String! {
        return "Isis DICOM Viewer"
    }

    @objc nonisolated func customParametersForFeedbackReport() -> NSDictionary! {
        let dict = NSMutableDictionary()

        return dict
    }

    @objc(anonymizePreferencesForFeedbackReport:) nonisolated func anonymizePreferencesForFeedbackReport(_ preferences: NSMutableDictionary!) -> NSMutableDictionary! {
        return preferences
    }

    // The SMTP server, account and password of the original project's crash
    // report mailbox were returned here in clear text. FeedbackReporter never
    // asked for them (it posts to targetURLForFeedbackReport or the Info.plist
    // URL, and this fork sets neither), so they only put a credential in the
    // source and the binary. They are gone, and nothing is sent by e-mail.

    @objc func mailSenderTitle() -> String! {
        return "Isis DICOM Viewer"
    }

    @objc func mailSubject() -> String! {
        return "Isis DICOM Viewer Crash Report"
    }

    @objc func mailTextBody() -> String! {
        return "See attached XML file"
    }

    /*
     - (NSString *)targetUrlForFeedbackReport
    {
        NSString *targetUrlFormat = @"http://horosproject.org/crashreport.php?project=%@&version=%@";
        NSString *project = [[[NSBundle mainBundle] infoDictionary] valueForKey: @"CFBundleExecutable"];
        NSString *version = [[[NSBundle mainBundle] infoDictionary] valueForKey: @"CFBundleVersion"];

        return [NSString stringWithFormat:targetUrlFormat, project, version];
    }
    */

}
