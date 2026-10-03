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

#if MACAPPSTORE
import AppKit

@MainActor @objc(PluginManagerController)
public final class PluginManagerController: NSWindowController {
    @IBOutlet @objc var filtersMenu: NSMenu?
    @IBOutlet @objc var roisMenu: NSMenu?
    @IBOutlet @objc var othersMenu: NSMenu?
    @IBOutlet @objc var dbMenu: NSMenu?
    @objc public var plugins: NSArray { [] }
    @objc public func refreshPluginList() {}
    public override func showWindow(_ sender: Any?) {}
}
#else
import AppKit
import WebKit
import Synchronization

// The catalogs are shared by every controller and kept ten minutes: the file
// statics of the former PluginManagerController.m. The window's worker fills
// them and the main thread reads them, so they are read and written only under
// `pluginCatalogLock` (#1005); that is what makes nonisolated(unsafe) hold.
private let pluginCatalogLock = NSLock()
nonisolated(unsafe) private var CachedOsiriXPluginsList: NSArray? = nil
nonisolated(unsafe) private var CachedOsiriXPluginsListDate: Date? = nil

nonisolated(unsafe) private var CachedHorosPluginsList: NSArray? = nil
nonisolated(unsafe) private var CachedHorosPluginsListDate: Date? = nil

/// The class methods of PluginManager this window sends, by their Objective-C
/// selectors. PluginManager.h declares them for the application's Objective-C
/// only (OSIRIX_VIEWER), which Swift does not see; the messages go to the
/// PluginManager class object, as [PluginManager ...] did.
@objc private protocol PluginManagerMessages {
    @objc(pluginsList) func pluginsList() -> NSArray?
    @objc(availabilities) func availabilities() -> NSArray?
    @objc(setMenus::::) func setMenus(_ filtersMenu: NSMenu?, _ roisMenu: NSMenu?, _ othersMenu: NSMenu?, _ dbMenu: NSMenu?)
    @objc(activatePluginWithName:) func activatePlugin(withName pluginName: String?)
    @objc(deactivatePluginWithName:) func deactivatePlugin(withName pluginName: String?)
    @objc(changeAvailabilityOfPluginWithName:to:) func changeAvailabilityOfPlugin(withName pluginName: String?, to availability: String?)
    @discardableResult
    @objc(deletePluginWithName:) func deletePlugin(withName pluginName: String?) -> String?
    @discardableResult
    @objc(deletePluginWithName:availability:isActive:) func deletePlugin(withName pluginName: String?, availability: String?, isActive: Bool) -> String?
    @objc(userActivePluginsDirectoryPath) func userActivePluginsDirectoryPath() -> String?
    @objc(movePluginFromPath:toPath:) func movePlugin(fromPath sourcePath: String?, toPath destinationPath: String?)
    @objc(loadPluginAtPath:) func loadPlugin(atPath path: String?)
}

private var pluginManager: PluginManagerMessages {
    unsafeBitCast(PluginManager.self as AnyObject, to: PluginManagerMessages.self)
}

/// The plugin table of PluginManager.xib: Delete and Backspace send -delete:
/// to its delegate, the PluginManagerController.
@objc(PluginsTableView)
public final class PluginsTableView: NSTableView {

    public override func keyDown(with event: NSEvent) {
        guard let characters = event.characters as NSString?, characters.length != 0 else {
            return
        }

        let c = Int(characters.character(at: 0))

        if (c == NSDeleteFunctionKey || c == NSDeleteCharacter || c == NSBackspaceCharacter || c == NSDeleteCharFunctionKey) && self.selectedRow >= 0 && self.numberOfRows > 0 {
            _ = (self.delegate as AnyObject?)?.perform(NSSelectorFromString("delete:"), with: self)
        } else {
            super.keyDown(with: event)
        }
    }
}

/// Window Controller for PluginFilter management: the plugin manager window
/// (installed plugins, the OsiriX and Horos catalogs, downloads and installs).
///
/// Implemented in Swift since #720: the Objective-C name, the selectors and
/// <Horos/PluginManagerController.h> are those of the former class. The C
/// function sortPluginArrayByName of the former PluginManagerController.m is
/// in PluginManagerController+CAPI.m. MainMenu.xib creates one with -init, and
/// PluginManager.xib has it as File's Owner.
@objc(PluginManagerController)
public final class PluginManagerController: NSWindowController {

    // Outlets the xibs set: ivars of the former class.
    @IBOutlet @objc var filtersMenu: NSMenu?
    @IBOutlet @objc var roisMenu: NSMenu?
    @IBOutlet @objc var othersMenu: NSMenu?
    @IBOutlet @objc var dbMenu: NSMenu?

    @IBOutlet @objc var pluginsArrayController: NSArrayController?
    @IBOutlet @objc var pluginTable: PluginsTableView?

    @IBOutlet @objc var tabView: NSTabView?
    @IBOutlet @objc var installedPluginsTabViewItem: NSTabViewItem?
    @IBOutlet @objc var osirixPluginsTabViewItem: NSTabViewItem?
    @IBOutlet @objc var horosPluginsTabViewItem: NSTabViewItem?

    @IBOutlet @objc var osirixPluginWebView: WKWebView?
    @IBOutlet @objc var horosPluginWebView: WKWebView?
    @IBOutlet @objc var osirixPluginListPopUp: NSPopUpButton?
    @IBOutlet @objc var horosPluginListPopUp: NSPopUpButton?
    @IBOutlet @objc var osirixPluginDownloadButton: NSButton?
    @IBOutlet @objc var horosPluginDownloadButton: NSButton?

    @IBOutlet @objc var osirixPluginStatusTextField: NSTextField?
    @IBOutlet @objc var horosPluginStatusTextField: NSTextField?
    @IBOutlet @objc var osirixPluginStatusProgressIndicator: NSProgressIndicator?
    @IBOutlet @objc var horosPluginStatusProgressIndicator: NSProgressIndicator?

    @IBOutlet @objc var validatedInHorosBox: NSBox?
    @IBOutlet @objc var NOTvalidatedInHorosBox: NSBox?
    @IBOutlet @objc var protectedModeLabel: NSTextField?

    /// What -plugins returns: the array PluginManager.xib's controller binds
    /// to, emptied and refilled in place by -refreshPluginList.
    private var pluginsArray = NSMutableArray()

    private nonisolated let osirixPluginListURLs: [String] = [OSIRIX_PLUGIN_LIST_URL, OSIRIX_PLUGIN_LIST_ALT_URL]
    private nonisolated let horosPluginListURLs: [String] = [HOROS_PLUGIN_LIST_URL, HOROS_PLUGIN_LIST_ALT_URL]
    private var osirixPluginDownloadURL: String? = nil
    private var horosPluginDownloadURL: String? = nil
    private var osiriXPluginHorosCompatibility = false

    /// The last catalog failures, written by the catalog load on its worker and
    /// read by the window on the main thread.
    private nonisolated let catalogErrors = Mutex<(osirix: NSError?, horos: NSError?)>((nil, nil))
    private var osirixCatalogError: NSError? { catalogErrors.withLock { $0.osirix } }
    private var horosCatalogError: NSError? { catalogErrors.withLock { $0.horos } }
    /// Path -> transfer. The activity thread takes a snapshot under this mutex;
    /// AppKit and installation remain on the main actor.
    private nonisolated let downloadingPlugins = Mutex<[String: PluginPackageDownload]>([:])

    /// The catalogs' navigation delegate, which the web views hold weakly,
    /// and the observations of their loading that drive the spinners. Set up
    /// once, the first time the window shows.
    private var catalogNavigation: CatalogNavigation?
    private var catalogLoadingObservations: [NSKeyValueObservation] = []

    // NSWindowController's -init is a convenience initializer: this one
    // replaces it without `override`, as the former -init did.
    @objc public convenience init() {
        self.init(windowNibName: "PluginManager")

        pluginsArray = NSMutableArray(array: (pluginManager.pluginsList() as? [Any]) ?? [])
    }

    public override init(window: NSWindow?) {
        super.init(window: window)
    }

    public required init?(coder: NSCoder) {
        super.init(coder: coder)
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    /// Shows a catalog's spinner while its page loads, and hides it when the
    /// page has loaded or failed: what the WebViewProgressStarted and
    /// WebViewProgressFinished notifications did.
    private func catalogLoadingChanged(_ webView: WKWebView) {
        let statusProgressIndicator = webView === osirixPluginWebView ? osirixPluginStatusProgressIndicator : horosPluginStatusProgressIndicator

        if webView.isLoading {
            statusProgressIndicator?.isHidden = false
            statusProgressIndicator?.startAnimation(self)
        } else {
            statusProgressIndicator?.isHidden = true
            statusProgressIndicator?.stopAnimation(self)
        }

        self.window?.display()
    }

    /// Makes the controller the catalogs' navigation delegate and observes
    /// their loading. The delegate and the observations reach the controller
    /// weakly, so a page that finishes after it is gone calls nothing.
    private func configureCatalogWebViews() {
        guard catalogNavigation == nil else { return }

        let navigation = CatalogNavigation(controller: self)
        catalogNavigation = navigation

        for case let webView? in [osirixPluginWebView, horosPluginWebView] {
            webView.navigationDelegate = navigation
            catalogLoadingObservations.append(webView.observe(\.isLoading) { [weak self] webView, _ in
                // A web view changes its loading state on the main thread.
                MainActor.assumeIsolated { self?.catalogLoadingChanged(webView) }
            })
        }
    }

    @objc(windowDidBecomeMain:)
    public func windowDidBecomeMain(_ notification: Notification) {
        if AppController.isFDACleared() {
            HorosAlertPanel.runCritical(title: NSLocalizedString("Important Notice", comment: ""), message: NSLocalizedString("Plugins are not certified for primary diagnosis in medical imaging, unless specifically written by the plugin author(s).", comment: ""), defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
        }
    }

    // MARK: -
    // MARK: installed

    @objc(plugins)
    public func plugins() -> NSMutableArray! {
        return pluginsArray
    }

    @objc(availabilities)
    public func availabilities() -> NSArray! {
        return pluginManager.availabilities()
    }

    /// The row of the table's arranged objects: -objectAtIndex: raises for a
    /// row outside the list (-1 when nothing was clicked), as it did.
    private func arrangedPlugin(atRow row: Int) -> NSDictionary? {
        let pluginsList = pluginsArrayController?.arrangedObjects as? NSArray
        return pluginsList?.object(at: row) as? NSDictionary
    }

    private static func boolValue(_ value: Any?) -> Bool {
        if let number = value as? NSNumber { return number.boolValue }
        if let string = value as? NSString { return string.boolValue }
        return false
    }

    /// [value isEqualToString:other], NO when either is nil.
    private static func isEqualToString(_ value: Any?, _ other: Any?) -> Bool {
        guard let string = value as? NSString, let other = other as? String else { return false }
        return string.isEqual(to: other)
    }

    /// What %@ printed for an object: its description, or (null).
    private static func formatted(_ value: Any?) -> String {
        guard let value = value else { return "(null)" }
        return String(describing: value as AnyObject)
    }

    /// [NSURLRequest requestWithURL:[NSURL URLWithString:string]], which took
    /// the nil URL of a missing or invalid string.
    private static func request(forURLString string: String?) -> URLRequest {
        if let string = string, let url = NSURL(string: string) as URL? {
            return URLRequest(url: url)
        }
        return NSURLRequest() as URLRequest
    }

    /// Loads a catalog page. An entry without a valid URL empties the page, as
    /// the empty request did in the former WebView, instead of handing
    /// WKWebView a request without a URL.
    private static func loadCatalogPage(_ url: String?, in webView: WKWebView?) {
        let request = Self.request(forURLString: url)
        webView?.load(request.url != nil ? request : URLRequest(url: URL(string: "about:blank")!))
    }

    @IBAction @objc(modifiyActivation:)
    public func modifiyActivation(_ sender: Any!) {
        let clickedRow = pluginTable?.clickedRow ?? 0
        let pluginName = arrangedPlugin(atRow: clickedRow)?.object(forKey: "name") as? String
        let pluginIsActive = Self.boolValue(arrangedPlugin(atRow: clickedRow)?.object(forKey: "active"))

        if !pluginIsActive {
            pluginManager.deactivatePlugin(withName: pluginName)
        } else {
            pluginManager.activatePlugin(withName: pluginName)
        }

        refreshPluginList()
        pluginTable?.selectRowIndexes(IndexSet(integer: pluginTable?.clickedRow ?? 0), byExtendingSelection: false)
    }

    @IBAction @objc(delete:)
    public func delete(_ sender: Any!) {
        if ((pluginsArrayController?.arrangedObjects as? NSArray)?.count ?? 0) == 0 {
            return
        }

        if HorosAlertPanel.runInformational(title: NSLocalizedString("Delete a plugin", comment: ""),
                                            message: NSLocalizedString("Are you sure you want to delete the selected plugin?", comment: ""),
                                            defaultButton: NSLocalizedString("OK", comment: ""),
                                            alternateButton: NSLocalizedString("Cancel", comment: ""),
                                            otherButton: nil) == HorosAlertPanel.defaultResponse {
            let selectedRow = pluginTable?.selectedRow ?? 0
            let pluginName = arrangedPlugin(atRow: selectedRow)?.object(forKey: "name") as? String
            let availability = arrangedPlugin(atRow: selectedRow)?.object(forKey: "availability") as? String
            let pluginIsActive = Self.boolValue(arrangedPlugin(atRow: selectedRow)?.object(forKey: "active"))

            pluginManager.deletePlugin(withName: pluginName,
                                       availability: availability,
                                       isActive: pluginIsActive)

            refreshPluginList()
        }
    }

    @IBAction @objc(modifiyAvailability:)
    public func modifiyAvailability(_ sender: Any!) {
        let pluginName = arrangedPlugin(atRow: pluginTable?.clickedRow ?? 0)?.object(forKey: "name") as? String

        pluginManager.changeAvailabilityOfPlugin(withName: pluginName, to: (sender as? NSControl)?.selectedCell()?.title)

        refreshPluginList() // needed to restore the availability menu in case the user did provided a good admin password
    }

    @IBAction @objc(loadPlugins:)
    public func loadPlugins(_ sender: Any!) {
        pluginManager.setMenus(filtersMenu, roisMenu, othersMenu, dbMenu)
    }

    @objc(windowWillClose:)
    public func windowWillClose(_ aNotification: Notification) {
        self.window?.acceptsMouseMovedEvents = false
        let downloads = downloadingPlugins.withLock { downloads in
            let pending = Array(downloads.values)
            downloads.removeAll()
            return pending
        }
        for download in downloads { download.cancel() }
        osirixPluginStatusProgressIndicator?.stopAnimation(self)
        osirixPluginStatusProgressIndicator?.isHidden = true
        horosPluginStatusProgressIndicator?.stopAnimation(self)
        horosPluginStatusProgressIndicator?.isHidden = true

        do {
            try HorosObjCException.perform {
                self.refreshPluginList()
            }
        } catch {
            NSLog("windowwillClose exception pluginmanagercontroller: %@", Self.formatted((error as NSError).userInfo[HorosObjCExceptionKey]))
        }
    }

    @IBAction public override func showWindow(_ sender: Any?) {
        if self.window?.isVisible == true {
            self.window?.makeKeyAndOrderFront(nil)
            return
        }

        let splash = WaitRendering(NSLocalizedString("Initializing Plugin Manager...", comment: ""))
        splash?.showWindow(self)

        // nonisolated(unsafe): the sender only rides through the catalog load
        // and goes back to AppKit on the main thread, where it came from;
        // nothing touches it in between.
        nonisolated(unsafe) let sender = sender
        DispatchQueue.global(qos: .default).async {

            _ = self.availableOsiriXPlugins()
            _ = self.availableHorosPlugins()

            DispatchQueue.main.async {

                let viewers = ViewerController.getDisplayed2DViewers() as NSArray?
                for case let viewer as ViewerController in viewers ?? NSArray() {
                    viewer.window?.close()
                }

                super.showWindow(sender)


                self.refreshPluginList()



                ////////////////////////////////////////////////////////////////////////////////////////
                ////////////////////////////////////////////////////////////////////////////////////////
                ////////////////////////////////////////////////////////////////////////////////////////

                if DCMPix.isRunOsiriXInProtectedModeActivated() {
                    self.protectedModeLabel?.isHidden = false
                } else {
                    self.protectedModeLabel?.isHidden = true
                }


                self.configureCatalogStatusFields()
                self.configurePluginLoadDetails()
                self.configureCatalogWebViews()

                self.osirixPluginStatusTextField?.isHidden = true
                self.osirixPluginStatusProgressIndicator?.isHidden = true

                self.horosPluginStatusTextField?.isHidden = true
                self.horosPluginStatusProgressIndicator?.isHidden = true

                ////////////////////////////////////////////////////////////////////////////////////////

                let availableOsiriXCatalog = self.availableOsiriXPlugins()
                if (availableOsiriXCatalog?.count ?? 0) < 1 {
                    self.osirixPluginListPopUp?.removeAllItems()
                    self.osirixPluginListPopUp?.isEnabled = false
                    self.osirixPluginDownloadButton?.isEnabled = false

                    self.osirixPluginStatusTextField?.isHidden = false
                    self.osirixPluginStatusTextField?.stringValue = availableOsiriXCatalog != nil ? NSLocalizedString("The plugin catalog is empty.", comment: "") : (self.osirixCatalogError?.localizedDescription ?? NSLocalizedString("No OsiriX plugin server available.", comment: ""))
                } else {
                    self.generateAvailableOsiriXPluginsMenu()
                    let first = self.availableOsiriXPlugins()?.object(at: 0) as? NSObject
                    self.setURLforOsiriXPlugin(withName: first?.value(forKey: "name") as? String)
                    self.setOsiriXPluginDownloadURL(first?.value(forKey: "download_url") as? String)

                    self.setOsiriXPluginHorosCompatibility(
                        Self.boolValue(first?.value(forKey: "HorosCompatiblePlugin"))
                    )
                }

                ////////////////////////////////////////////////////////////////////////////////////////

                let availableHorosCatalog = self.availableHorosPlugins()
                if (availableHorosCatalog?.count ?? 0) < 1 {
                    self.horosPluginListPopUp?.removeAllItems()
                    self.horosPluginListPopUp?.isEnabled = false
                    self.horosPluginDownloadButton?.isEnabled = false

                    self.horosPluginStatusTextField?.isHidden = false
                    self.horosPluginStatusTextField?.stringValue = availableHorosCatalog != nil ? NSLocalizedString("The plugin catalog is empty.", comment: "") : (self.horosCatalogError?.localizedDescription ?? NSLocalizedString("No Horos plugin server available.", comment: ""))
                } else {
                    self.generateAvailableHorosPluginsMenu()

                    let plugin = self.availableHorosPlugins()?.object(at: 0) as? NSObject
                    self.setURLforHorosPlugin(withName: plugin?.value(forKey: "name") as? String)
                    self.setHorosPluginDownloadURL(plugin?.value(forKey: "download_url") as? String)
                }

                ////////////////////////////////////////////////////////////////////////////////////////
                ////////////////////////////////////////////////////////////////////////////////////////
                ////////////////////////////////////////////////////////////////////////////////////////



                // If we need to remove a plugin with a custom pref pane
                for window in NSApp.windows {
                    if window.windowController is PreferencesWindowController {
                        window.close()
                    }
                }

                self.window?.makeKeyAndOrderFront(nil)


                splash?.close()

            }
        }
    }

    @objc(configurePluginLoadDetails)
    public func configurePluginLoadDetails() {
        guard let view = installedPluginsTabViewItem?.view, view.viewWithTag(16601) == nil else { return }
        let button = NSButton(title: NSLocalizedString("Loading Details...", comment: ""), target: self, action: #selector(showPluginLoadDetails(_:)))
        button.frame = NSMakeRect(430, 10, 180, 32)
        button.autoresizingMask = [.minXMargin, .maxYMargin]
        button.tag = 16601
        view.addSubview(button)
    }

    @objc(showPluginLoadDetails:)
    public func showPluginLoadDetails(_ sender: Any!) {
        let rows = pluginsArrayController?.arrangedObjects as? NSArray
        let row = pluginTable?.selectedRow ?? 0
        let alert = NSAlert()
        if row < 0 || row >= (rows?.count ?? 0) {
            alert.messageText = NSLocalizedString("Select a plugin first", comment: "")
        } else {
            let plugin = rows?.object(at: row) as? NSDictionary
            alert.messageText = "\(Self.formatted(plugin?["name"])): \(Self.formatted(plugin?["loadState"]))"
            alert.informativeText = plugin?["loadReason"] as? String ?? ""
        }
        alert.addButton(withTitle: NSLocalizedString("OK", comment: ""))
        if let window = self.window {
            alert.beginSheetModal(for: window, completionHandler: nil)
        }
    }

    @objc(configureCatalogStatusFields)
    public func configureCatalogStatusFields() {
        let fields: [NSTextField?] = [osirixPluginStatusTextField, horosPluginStatusTextField]
        let buttons: [NSButton?] = [osirixPluginDownloadButton, horosPluginDownloadButton]
        for index in 0..<2 {
            guard let field = fields[index], let button = buttons[index] else { continue }
            var frame = field.frame
            frame.origin.y = 8
            frame.size.height = 42
            frame.size.width = max(282, NSMinX(button.frame) - NSMinX(frame) - 16)
            field.frame = frame
            field.autoresizingMask = [.width, .maxYMargin]
            field.textColor = NSColor.labelColor
            field.maximumNumberOfLines = 3
            field.lineBreakMode = .byWordWrapping
            field.cell?.wraps = true
            field.cell?.isScrollable = false
        }

    }

    public override func awakeFromNib() {
        super.awakeFromNib()

    }

    @objc(refreshPluginList)
    public func refreshPluginList() {
        let selectedIndexes = pluginTable?.selectedRowIndexes

        pluginManager.setMenus(filtersMenu, roisMenu, othersMenu, dbMenu)

        self.willChangeValue(forKey: "plugins")
        pluginsArray.removeAllObjects()
        pluginsArray.addObjects(from: (pluginManager.pluginsList() as? [Any]) ?? [])
        self.didChangeValue(forKey: "plugins")

        if let selectedIndexes = selectedIndexes {
            pluginTable?.selectRowIndexes(selectedIndexes, byExtendingSelection: false)
        }
    }

    // MARK: NSTabView Delegate methods

    @objc(tabView:willSelectTabViewItem:)
    public func tabView(_ tabView: NSTabView, willSelect tabViewItem: NSTabViewItem?) {
        if tabViewItem?.isEqual(to: installedPluginsTabViewItem) == true {
            refreshPluginList()
        }
    }

    // MARK: -
    // MARK: web view

    // MARK: pop up menu

    /// Nonisolated: -showWindow: loads the catalog on a worker; on the main
    /// thread it answers the cached list only.
    @objc(availableOsiriXPlugins)
    nonisolated public func availableOsiriXPlugins() -> NSArray! {
        // showWindow preloads on its worker; UI callbacks must never repeat network I/O.
        if Thread.isMainThread { return pluginCatalogLock.withLock { CachedOsiriXPluginsList } }

        var pluginsList: NSArray? = nil

        let fresh = pluginCatalogLock.withLock { () -> NSArray? in
            if CachedOsiriXPluginsListDate == nil || CachedOsiriXPluginsListDate!.timeIntervalSinceNow < -10 * 60 { return nil }
            return CachedOsiriXPluginsList
        }
        if let cached = fresh {
            return cached
        }

        ////////////////////////////////////////////

        catalogErrors.withLock { $0.osirix = nil }
        let attempted = NSMutableSet()
        for endpoint in osirixPluginListURLs {
            if attempted.contains(endpoint) { continue }
            attempted.add(endpoint)
            var failure: NSError? = nil
            pluginsList = HorosLoadPluginCatalog(NSURL(string: endpoint) as URL?, 10, &failure) as NSArray?
            catalogErrors.withLock { $0.osirix = failure }
            if pluginsList != nil { break }
        }

        ////////////////////////////////////////////

        guard let loadedList = pluginsList else {
            pluginCatalogLock.withLock { CachedOsiriXPluginsList = nil }
            return nil
        }

        let sortedPlugins = loadedList.sortedArray({ sortPluginArrayByName($0, $1, $2) }, context: nil) as NSArray

        pluginCatalogLock.withLock {
            CachedOsiriXPluginsListDate = Date()

            CachedOsiriXPluginsList = sortedPlugins
        }

        return sortedPlugins
    }

    /// Nonisolated, as -availableOsiriXPlugins.
    @objc(availableHorosPlugins)
    nonisolated public func availableHorosPlugins() -> NSArray! {
        // showWindow preloads on its worker; UI callbacks must never repeat network I/O.
        if Thread.isMainThread { return pluginCatalogLock.withLock { CachedHorosPluginsList } }

        var pluginsList: NSArray? = nil

        let fresh = pluginCatalogLock.withLock { () -> NSArray? in
            if CachedHorosPluginsListDate == nil || CachedHorosPluginsListDate!.timeIntervalSinceNow < -10 * 60 { return nil }
            return CachedHorosPluginsList
        }
        if let cached = fresh {
            return cached
        }

        ////////////////////////////////////////////

        catalogErrors.withLock { $0.horos = nil }
        let attempted = NSMutableSet()
        for endpoint in horosPluginListURLs {
            if attempted.contains(endpoint) { continue }
            attempted.add(endpoint)
            var failure: NSError? = nil
            pluginsList = HorosLoadPluginCatalog(NSURL(string: endpoint) as URL?, 10, &failure) as NSArray?
            catalogErrors.withLock { $0.horos = failure }
            if pluginsList != nil { break }
        }

        ////////////////////////////////////////////

        guard let loadedList = pluginsList else {
            pluginCatalogLock.withLock { CachedHorosPluginsList = nil }
            return nil
        }

        let sortedPlugins = loadedList.sortedArray({ sortPluginArrayByName($0, $1, $2) }, context: nil) as NSArray

        pluginCatalogLock.withLock {
            CachedHorosPluginsListDate = Date()

            CachedHorosPluginsList = sortedPlugins
        }

        return sortedPlugins
    }

    @objc(generateAvailableOsiriXPluginsMenu)
    public func generateAvailableOsiriXPluginsMenu() {
        osirixPluginListPopUp?.removeAllItems()

        let availablePlugins = availableOsiriXPlugins()

        for loopItem in availablePlugins ?? NSArray() {
            if let name = (loopItem as? NSDictionary)?.object(forKey: "name") as? String {
                osirixPluginListPopUp?.addItem(withTitle: name)
            }
        }
    }

    @objc(generateAvailableHorosPluginsMenu)
    public func generateAvailableHorosPluginsMenu() {
        horosPluginListPopUp?.removeAllItems()

        let availablePlugins = availableHorosPlugins()

        for loopItem in availablePlugins ?? NSArray() {
            if let name = (loopItem as? NSDictionary)?.object(forKey: "name") as? String {
                horosPluginListPopUp?.addItem(withTitle: name)
            }
        }

        //[[horosPluginListPopUp menu] addItem:[NSMenuItem separatorItem]];

        //[horosPluginListPopUp addItemWithTitle:NSLocalizedString(@"Your Horos Plugin here!", nil)];
    }

    // MARK: OsiriX web page

    @objc(setOsiriXPluginURL:)
    public func setOsiriXPluginURL(_ url: String!) {
        Self.loadCatalogPage(url, in: osirixPluginWebView)
    }

    /// Whether a catalog entry is installed, and in the same or a later version.
    ///
    /// The catalog names a plugin by its download's file name, which is the
    /// name of the bundle it installs: an installed plugin of that name is
    /// this entry, whatever its version, and the version only decides between
    /// "already installed" and "download the new version". The former
    /// `alreadyInstalled || sameName || (sameName && sameVersion)` said the
    /// same thing with a term that could never count (#777).
    private func installedState(of plugin: NSDictionary) -> (alreadyInstalled: Bool, sameName: Bool, sameVersion: Bool) {
        let name = HorosPluginDownloadName(plugin as? [AnyHashable: Any])
        for case let installedPlugin as NSDictionary in pluginsArray
            where Self.isEqualToString(name, installedPlugin.value(forKey: "name")) {
            let current = HorosComparePluginVersions(installedPlugin.object(forKey: "version"), plugin.object(forKey: "version")) != .orderedAscending
            return (true, true, current)
        }
        return (false, false, false)
    }

    @objc(setURLforOsiriXPluginWithName:)
    public func setURLforOsiriXPlugin(withName name: String!) {
        let availablePlugins = availableOsiriXPlugins()

        ////////////////////////////

        for case let plugin as NSDictionary in availablePlugins ?? NSArray() {
            if Self.isEqualToString(plugin.value(forKey: "name"), name) {
                if Self.boolValue(plugin.value(forKey: "HorosCompatiblePlugin")) {
                    self.validatedInHorosBox?.isHidden = false
                    self.NOTvalidatedInHorosBox?.isHidden = true
                } else {
                    self.NOTvalidatedInHorosBox?.isHidden = false
                    self.validatedInHorosBox?.isHidden = true
                }

                setOsiriXPluginURL(plugin.value(forKey: "url") as? String)
                setOsiriXPluginDownloadURL(plugin.value(forKey: "download_url") as? String)
                setOsiriXPluginHorosCompatibility(Self.boolValue(plugin.value(forKey: "HorosCompatiblePlugin")))

                let (alreadyInstalled, sameName, sameVersion) = installedState(of: plugin)

                if alreadyInstalled {
                    osirixPluginStatusTextField?.isHidden = false

                    if sameName && sameVersion {
                        osirixPluginStatusTextField?.stringValue = NSLocalizedString("Plugin already installed", comment: "")
                    } else {
                        osirixPluginStatusTextField?.stringValue = NSLocalizedString("Download the new version!", comment: "")
                    }
                } else {
                    osirixPluginStatusTextField?.isHidden = true
                }

                return
            }
        }
    }

    /// The popup's selected title: [sender title].
    private static func title(of sender: Any?) -> String? {
        if let button = sender as? NSButton { return button.title }
        if let item = sender as? NSMenuItem { return item.title }
        return nil
    }

    @IBAction @objc(changeOsiriXPluginWebView:)
    public func changeOsiriXPluginWebView(_ sender: Any!) {
        setURLforOsiriXPlugin(withName: Self.title(of: sender))
    }

    // MARK: Horos web page

    @objc(setHorosPluginURL:)
    public func setHorosPluginURL(_ url: String!) {
        Self.loadCatalogPage(url, in: horosPluginWebView)
    }

    @objc(setURLforHorosPluginWithName:)
    public func setURLforHorosPlugin(withName name: String!) {
        let availablePlugins = availableHorosPlugins()

        ////////////////////////////

        for case let plugin as NSDictionary in availablePlugins ?? NSArray() {
            if Self.isEqualToString(plugin.value(forKey: "name"), name) {
                setHorosPluginURL(plugin.value(forKey: "url") as? String)
                setHorosPluginDownloadURL(plugin.value(forKey: "download_url") as? String)

                let (alreadyInstalled, sameName, sameVersion) = installedState(of: plugin)

                if alreadyInstalled {
                    horosPluginStatusTextField?.isHidden = false

                    if sameName && sameVersion {
                        horosPluginStatusTextField?.stringValue = NSLocalizedString("Plugin already installed", comment: "")
                    } else {
                        horosPluginStatusTextField?.stringValue = NSLocalizedString("Download the new version!", comment: "")
                    }
                } else {
                    horosPluginStatusTextField?.isHidden = true
                }

                return
            } else if Self.isEqualToString(name, NSLocalizedString("Your Horos Plugin here!", comment: "")) {
                loadSubmitPluginPage()

                return
            }
        }
    }

    @IBAction @objc(changeHorosPluginWebView:)
    public func changeHorosPluginWebView(_ sender: Any!) {
        setURLforHorosPlugin(withName: Self.title(of: sender))
    }

    // MARK: download

    @objc(setOsiriXPluginHorosCompatibility:)
    public func setOsiriXPluginHorosCompatibility(_ compatible: Bool) {
        osiriXPluginHorosCompatibility = compatible
    }

    @objc(setOsiriXPluginDownloadURL:)
    public func setOsiriXPluginDownloadURL(_ url: String!) {
        osirixPluginDownloadURL = url

        if Self.isEqualToString(osirixPluginDownloadURL, "") {
            osirixPluginDownloadButton?.isHidden = true
        } else {
            osirixPluginDownloadButton?.isHidden = false
        }
    }

    @objc(setHorosPluginDownloadURL:)
    public func setHorosPluginDownloadURL(_ url: String!) {
        horosPluginDownloadURL = url

        if Self.isEqualToString(horosPluginDownloadURL, "") {
            horosPluginDownloadButton?.isHidden = true
        } else {
            horosPluginDownloadButton?.isHidden = false
        }
    }

    @objc(fakeThread:)
    nonisolated public func fakeThread(_ downloadedFilePath: String!) {
        guard let downloadedFilePath,
              let download = downloadingPlugins.withLock({ $0[downloadedFilePath] }) else { return }
        autoreleasepool {
            while true {
                if Thread.current.isCancelled { download.cancel() }
                let state = download.waitForProgress()
                if state.expected > 0 {
                    Thread.current.progress = CGFloat(Double(state.received) / Double(state.expected))
                }
                if state.finished { break }
            }
        }
    }

    /// Starts the download of a plugin to the temporary folder, unless the same file is
    /// already downloading: the common part of -downloadOsiriXPlugin: and
    /// -downloadHorosPlugin:.
    private func downloadPlugin(from downloadURL: String?) {
        guard let downloadURL, let components = URLComponents(string: downloadURL),
              let encodedName = components.percentEncodedPath.split(separator: "/", omittingEmptySubsequences: false).last,
              let fileName = String(encodedName).removingPercentEncoding,
              !fileName.isEmpty, !fileName.contains("/"), fileName != ".", fileName != ".." else {
            NSLog("Invalid plugin download filename")
            return
        }
        // Query/fragment belong to the request URL, never to the local filename.
        let downloadedFilePath = (FileManager.default.tmpDirPath() as NSString).appendingPathComponent(fileName)

        guard let url = components.url, ["http", "https"].contains(url.scheme?.lowercased() ?? "") else { return }
        guard downloadingPlugins.withLock({ $0[downloadedFilePath] == nil }) else {
            NSLog("---- Already downloading...")
            return
        }
        let download = PluginPackageDownload(url: url, destination: URL(fileURLWithPath: downloadedFilePath),
            progress: { [weak self] download, received, expected in
                DispatchQueue.main.async {
                    guard let self, self.downloadingPlugins.withLock({ $0[downloadedFilePath] === download }) else { return }
                    let (_, indicator) = self.statusControls(forPath: downloadedFilePath)
                    indicator?.isIndeterminate = expected <= 0
                    if expected > 0 { indicator?.doubleValue = 100 * Double(received) / Double(expected) }
                }
            }, completion: { [weak self] download, error in
                DispatchQueue.main.async {
                    guard let self else { download.cancel(); return }
                    self.finishDownload(download, atPath: downloadedFilePath, error: error)
                }
            })
        downloadingPlugins.withLock { $0[downloadedFilePath] = download }
        let (field, indicator) = statusControls(forPath: downloadedFilePath)
        field?.isHidden = false
        field?.stringValue = NSLocalizedString("Downloading...", comment: "")
        indicator?.isHidden = false
        indicator?.isIndeterminate = true
        indicator?.startAnimation(self)
        let thread = Thread(target: self, selector: #selector(fakeThread(_:)), object: downloadedFilePath)
        thread.name = NSLocalizedString("Plugin download...", comment: "")
        thread.status = downloadURL
        thread.supportsCancel = true
        ThreadsManager.default().addThreadAndStart(thread)
        download.start()
    }

    @IBAction @objc(downloadOsiriXPlugin:)
    public func downloadOsiriXPlugin(_ sender: Any!) {
        if self.osiriXPluginHorosCompatibility == false {
            let alert = NSAlert()
            alert.addButton(withTitle: NSLocalizedString("Yes", comment: ""))
            alert.addButton(withTitle: NSLocalizedString("No", comment: ""))
            alert.messageText = NSLocalizedString("Not validated OsiriX plugin.", comment: "")
            alert.informativeText = NSLocalizedString("Not validated OsiriX plugins may cause Isis DICOM Viewer run-time errors. In case of problems, you can disable/uninstall them in [Plugins => Plugin Manager]. Continue installing?", comment: "")
            alert.alertStyle = .warning

            if alert.runModal() != .alertFirstButtonReturn {
                return
            }
        }

        downloadPlugin(from: osirixPluginDownloadURL)
    }

    @IBAction @objc(downloadHorosPlugin:)
    public func downloadHorosPlugin(_ sender: Any!) {
        downloadPlugin(from: horosPluginDownloadURL)
    }

    private func statusControls(forPath path: String) -> (NSTextField?, NSProgressIndicator?) {
        if path.contains("osirixplugin") {
            return (osirixPluginStatusTextField, osirixPluginStatusProgressIndicator)
        }
        return (horosPluginStatusTextField, horosPluginStatusProgressIndicator)
    }

    private func finishDownload(_ download: PluginPackageDownload, atPath path: String, error: Error?) {
        // A closed window removes its transfers before cancellation. A queued
        // success from that generation must never reach installation.
        guard downloadingPlugins.withLock({ $0[path] === download }) else { return }
        _ = downloadingPlugins.withLock { $0.removeValue(forKey: path) }
        let (field, indicator) = statusControls(forPath: path)
        indicator?.isHidden = true
        indicator?.stopAnimation(self)
        if let error = error ?? download.terminalError {
            field?.isHidden = false
            field?.stringValue = NSLocalizedString("Download failed", comment: "")
            if (error as NSError).code != NSURLErrorCancelled {
                HorosAlertPanel.runCritical(title: NSLocalizedString("Download failed", comment: ""), message: error.localizedDescription,
                    defaultButton: NSLocalizedString("OK", comment: ""), alternateButton: nil, otherButton: nil)
            }
            return
        }
        field?.stringValue = NSLocalizedString("Plugin downloaded", comment: "")
        installDownloadedPlugin(atPath: path)
        NotificationCenter.default.post(name: .AppPluginDownloadInstallDidFinish, object: self, userInfo: nil)
    }

    // MARK: install / uinstall

    @objc(installDownloadedPluginAtPath:)
    public func installDownloadedPlugin(atPath path: String!) {
        var statusTextField: NSTextField? = nil
        var statusProgressIndicator: NSProgressIndicator? = nil

        if (path as NSString?)?.contains("osirixplugin") == true {
            statusTextField = osirixPluginStatusTextField
            statusProgressIndicator = osirixPluginStatusProgressIndicator
        } else {
            statusTextField = horosPluginStatusTextField
            statusProgressIndicator = horosPluginStatusProgressIndicator
        }


        statusProgressIndicator?.isHidden = false
        statusProgressIndicator?.startAnimation(self)

        statusTextField?.stringValue = NSLocalizedString("Installing...", comment: "")

        var pluginPath: String? = path

        if isZippedFile(atPath: path) && unZipFile(atPath: path) {
            pluginPath = (path as NSString).deletingPathExtension
            try? FileManager.default.removeItem(atPath: path)
        } else {
            statusTextField?.stringValue = NSLocalizedString("Error: bad zip file", comment: "")
            statusProgressIndicator?.isHidden = true
            statusProgressIndicator?.stopAnimation(self)
            return
        }

        let pluginFileName = (pluginPath as NSString?)?.lastPathComponent

        let oldPath = pluginManager.deletePlugin(withName: pluginFileName)

        // determine in which directory to install the plugin (default = user dir, or if the plugin was already installed: in the same dir)
        let installDirectoryPath: String?

        if let oldPath = oldPath {
            installDirectoryPath = oldPath
        } else {
            installDirectoryPath = pluginManager.userActivePluginsDirectoryPath()
        }

        if let installDirectoryPath = installDirectoryPath, !FileManager.default.fileExists(atPath: installDirectoryPath) {
            try? FileManager.default.createDirectory(atPath: installDirectoryPath, withIntermediateDirectories: true, attributes: nil)
        }

        // movePlugin takes the complete bundle destination, not its parent folder.
        let installedPath = pluginFileName.flatMap { (installDirectoryPath as NSString?)?.appendingPathComponent($0) }
        pluginManager.movePlugin(fromPath: pluginPath, toPath: installedPath)

        guard let installedPath,
              FileManager.default.fileExists(atPath: installedPath),
              !FileManager.default.fileExists(atPath: pluginPath ?? "") else {
            statusTextField?.stringValue = NSLocalizedString("The plugin could not be moved. Its activation or location change was not completed. Check folder permissions and try again.", comment: "")
            statusProgressIndicator?.isHidden = true
            statusProgressIndicator?.stopAnimation(self)
            return
        }

        // Load only the bundle actually installed, and never report a failed move as success.
        pluginManager.loadPlugin(atPath: installedPath)

        statusTextField?.stringValue = NSLocalizedString("Plugin Installed", comment: "")
        statusProgressIndicator?.isHidden = true
        statusProgressIndicator?.stopAnimation(self)

        refreshPluginList()
    }

    @objc(isZippedFileAtPath:)
    public func isZippedFile(atPath path: String!) -> Bool {
        return ((path as NSString?)?.pathExtension as NSString?)?.isEqual(to: "zip") ?? false
    }

    @objc(unZipFileAtPath:)
    public func unZipFile(atPath path: String!) -> Bool {
        if ((path as NSString?)?.length ?? 0) == 0 {
            return false
        }

        do {
            try HorosObjCException.perform {
                let aTask = Process()
                var args = [String]()

                args.append("-o")
                args.append(path)
                args.append("-d")
                args.append((path as NSString).deletingLastPathComponent)
                aTask.launchPath = "/usr/bin/unzip"
                aTask.arguments = args
                aTask.launch()
                while aTask.isRunning {
                    Thread.sleep(forTimeInterval: 0.1)
                }

                //[aTask waitUntilExit];		// <- This is VERY DANGEROUS : the main runloop is continuing...
            }
        } catch {
            NSLog("***** exception in %@: %@", "-[PluginManagerController unZipFileAtPath:]", Self.formatted((error as NSError).userInfo[HorosObjCExceptionKey]))
        }

        if FileManager.default.fileExists(atPath: (path as NSString).deletingPathExtension) {
            return true
        } else {
            return false
        }
    }

    // MARK: submit plugin

    @objc(loadSubmitPluginPage)
    public func loadSubmitPluginPage() {
        // HOROS_PLUGIN_SUBMISSION_URL of url.h, which Swift cannot import.
        setHorosPluginURL(URL_HOROS_PROJECT + "/horos-content/plugins/submit.html")
    }

    @objc(sendPluginSubmission:)
    public func sendPluginSubmission(_ request: String!) {
        // Parse the URL boundary before decoding each form field once.
        let parameters = request.flatMap { URLComponents(string: $0)?.percentEncodedQuery }
        let parametersArray = parameters?.components(separatedBy: "&") ?? []

        let emailMessage = NSMutableString(string: "")

        for loopItem in parametersArray {
            let param = loopItem.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            let name = String(param[0]).replacingOccurrences(of: "+", with: " ").removingPercentEncoding
            let value = param.count > 1 ? String(param[1]).replacingOccurrences(of: "+", with: " ").removingPercentEncoding : nil
            emailMessage.append("\(Self.formatted(name)): \(Self.formatted(value)) \n")
        }

        NSWorkspace.shared.open(URL(string: "mailto:" + URL_EMAIL)!)
    }

    // MARK: catalog navigation

    /// The one decision a catalog navigation gets (#777). A web view that is
    /// not one of this window's catalogs loads what it asks for. A catalog's
    /// links open in the browser and its form goes by mail: neither navigates
    /// the catalog. Back and forward do not either: the page follows the
    /// plugin chosen in the popup, as the empty back/forward list of the
    /// former WebView kept it.
    fileprivate func catalogPolicy(for navigationAction: WKNavigationAction, in webView: WKWebView) -> WKNavigationActionPolicy {
        if webView !== osirixPluginWebView && webView !== horosPluginWebView {
            return .allow
        }

        switch navigationAction.navigationType {
        case .linkActivated:
            if let url = navigationAction.request.url {
                NSWorkspace.shared.open(url)
            }
            return .cancel
        case .formSubmitted:
            sendPluginSubmission(navigationAction.request.url?.absoluteString)
            return .cancel
        case .backForward:
            return .cancel
        default:
            return .allow
        }
    }
}

/// The catalogs' navigation delegate: it asks the controller, which it holds
/// weakly, and cancels what arrives once the controller is gone.
///
/// A private class, so that the generated Objective-C interface of
/// PluginManagerController does not name WebKit's protocol: through it WebKit
/// would reach every Objective-C file importing Horos-Swift.h (#970).
@MainActor
private final class CatalogNavigation: NSObject, WKNavigationDelegate {
    private weak var controller: PluginManagerController?

    init(controller: PluginManagerController) {
        self.controller = controller
    }

    // The Objective-C name is spelled out: a closure type that only nearly
    // matches WebKit's (without @MainActor) exported the method under
    // another selector, which WebKit never called.
    @objc(webView:decidePolicyForNavigationAction:decisionHandler:)
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        decisionHandler(controller?.catalogPolicy(for: navigationAction, in: webView) ?? .cancel)
    }
}

/// One package transfer, shared by URLSession's serial delegate queue and the
/// activity thread. Every mutable transfer field is protected by `condition`;
/// session/task are configured before publication and never replaced. This
/// synchronous delegate/activity bridge needs @unchecked Sendable until the
/// legacy ThreadsManager activity becomes an async consumer.
private final class PluginPackageDownload: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    private let condition = NSCondition()
    private let destination: URL
    private let progress: @Sendable (PluginPackageDownload, Int64, Int64) -> Void
    private let completion: @Sendable (PluginPackageDownload, Error?) -> Void
    private var session: URLSession!
    private var task: URLSessionDownloadTask!
    private var received: Int64 = 0
    private var expected: Int64 = -1
    private var finished = false
    private var staged = false
    private var failure: Error?

    init(url: URL, destination: URL,
         progress: @escaping @Sendable (PluginPackageDownload, Int64, Int64) -> Void,
         completion: @escaping @Sendable (PluginPackageDownload, Error?) -> Void) {
        self.destination = destination
        self.progress = progress
        self.completion = completion
        super.init()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 600
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 1
        session = URLSession(configuration: configuration, delegate: self, delegateQueue: queue)
        task = session.downloadTask(with: url)
    }

    func start() { task.resume() }

    var terminalError: Error? {
        condition.lock()
        defer { condition.unlock() }
        return failure
    }

    func waitForProgress() -> (finished: Bool, received: Int64, expected: Int64) {
        condition.lock()
        defer { condition.unlock() }
        if !finished { _ = condition.wait(until: Date(timeIntervalSinceNow: 0.1)) }
        return (finished, received, expected)
    }

    func cancel() {
        let error = NSError(domain: NSURLErrorDomain, code: NSURLErrorCancelled)
        condition.lock()
        failure = error
        let notify = !finished
        finished = true
        if staged { try? FileManager.default.removeItem(at: destination); staged = false }
        condition.broadcast()
        condition.unlock()
        session.invalidateAndCancel()
        if notify { completion(self, error) }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        condition.lock()
        guard !finished else { condition.unlock(); return }
        received = totalBytesWritten
        expected = totalBytesExpectedToWrite
        condition.signal()
        condition.unlock()
        progress(self, totalBytesWritten, totalBytesExpectedToWrite)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        do {
            guard let response = downloadTask.response as? HTTPURLResponse,
                  (200..<300).contains(response.statusCode), response.statusCode != 206 else {
                throw NSError(domain: NSURLErrorDomain, code: NSURLErrorBadServerResponse,
                    userInfo: [NSLocalizedDescriptionKey: "HTTP \((downloadTask.response as? HTTPURLResponse)?.statusCode ?? 0)"])
            }
            let size = (try FileManager.default.attributesOfItem(atPath: location.path)[.size] as? NSNumber)?.int64Value ?? 0
            // Content-Length describes the encoded representation. Foundation
            // may decompress it, so compare only when no encoding is applied.
            if size == 0 || (response.value(forHTTPHeaderField: "Content-Encoding") == nil &&
                            response.expectedContentLength >= 0 && size != response.expectedContentLength) {
                throw NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotDecodeContentData)
            }
            // Test the central directory AND every member CRC before allowing
            // extraction. A complete HTTP body may still be a truncated ZIP.
            let validation = Process()
            validation.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
            validation.arguments = ["-tq", location.path]
            validation.standardOutput = FileHandle.nullDevice
            validation.standardError = FileHandle.nullDevice
            try validation.run()
            validation.waitUntilExit()
            guard validation.terminationStatus == 0 else {
                throw NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotDecodeContentData)
            }
            condition.lock()
            defer { condition.unlock() }
            guard !finished else { return }
            // URLSession deletes its temporary file after this callback. Move
            // only the fully validated package to the existing destination.
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.moveItem(at: location, to: destination)
            staged = true
        } catch {
            condition.lock()
            if !finished { failure = error }
            condition.unlock()
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        condition.lock()
        guard !finished else { condition.unlock(); return }
        failure = error ?? failure
        if failure == nil && !staged { failure = NSError(domain: NSURLErrorDomain, code: NSURLErrorCannotCreateFile) }
        if failure != nil && staged { try? FileManager.default.removeItem(at: destination); staged = false }
        finished = true
        let result = failure
        condition.broadcast()
        condition.unlock()
        session.finishTasksAndInvalidate()
        completion(self, result)
    }
}

#endif
