#import <AppKit/AppKit.h>
#import <WebKit/WebKit.h>
#import <Quartz/Quartz.h>

// Shared by the Decompress report converter and its focused integration probe.
// WebKit discovers printable page bounds asynchronously. A synchronous
// runOperation can finish before that discovery and silently omit pages.
@interface HorosHTMLPrintSession : NSObject <WKNavigationDelegate>
@property BOOL loaded;
@property BOOL failed;
@property BOOL printed;
@property BOOL succeeded;
@end

@implementation HorosHTMLPrintSession
- (void)webView:(WKWebView *)view didFinishNavigation:(WKNavigation *)navigation { self.loaded = YES; }
- (void)webView:(WKWebView *)view didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error { self.failed = YES; }
- (void)webView:(WKWebView *)view didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error { self.failed = YES; }
- (void)webViewWebContentProcessDidTerminate:(WKWebView *)view { self.failed = YES; }
- (void)printOperationDidRun:(NSPrintOperation *)operation success:(BOOL)success contextInfo:(void *)context
{
    // AppKit may complete printing on its worker thread.
    dispatch_async(dispatch_get_main_queue(), ^{ self.succeeded = success; self.printed = YES; });
}
@end

static BOOL HorosPrintHTMLToPDF(NSString *path, NSString *destination, NSTimeInterval timeout)
{
    NSCAssert(NSThread.isMainThread, @"HTML pagination requires the main thread");
    if (![NSFileManager.defaultManager isReadableFileAtPath:path] ||
        [NSFileManager.defaultManager fileExistsAtPath:destination]) return NO;
    HorosHTMLPrintSession *session = [[[HorosHTMLPrintSession alloc] init] autorelease];
    WKWebViewConfiguration *configuration = [[[WKWebViewConfiguration alloc] init] autorelease];
    configuration.websiteDataStore = WKWebsiteDataStore.nonPersistentDataStore;
    configuration.defaultWebpagePreferences.allowsContentJavaScript = NO;
    WKWebView *webView = [[[WKWebView alloc] initWithFrame:NSMakeRect(0, 0, 612, 792) configuration:configuration] autorelease];
    NSWindow *window = [[[NSWindow alloc] initWithContentRect:webView.frame styleMask:NSWindowStyleMaskBorderless
        backing:NSBackingStoreBuffered defer:NO] autorelease];
    window.releasedWhenClosed = NO;
    window.contentView = webView;
    webView.navigationDelegate = session;
    NSURL *url = [NSURL fileURLWithPath:path];
    [webView loadFileURL:url allowingReadAccessToURL:url.URLByDeletingLastPathComponent];
    NSTimeInterval deadline = NSProcessInfo.processInfo.systemUptime + timeout;
    while (!session.loaded && !session.failed && NSProcessInfo.processInfo.systemUptime < deadline)
        [NSRunLoop.currentRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
    BOOL success = NO;
    if (session.loaded && !session.failed)
    {
        NSMutableDictionary *dictionary = [NSMutableDictionary dictionaryWithDictionary:NSPrintInfo.sharedPrintInfo.dictionary];
        dictionary[NSPrintJobDisposition] = NSPrintSaveJob;
        dictionary[NSPrintJobSavingURL] = [NSURL fileURLWithPath:destination];
        dictionary[NSPrintAllPages] = @YES;
        dictionary[NSPrintSelectionOnly] = @NO;
        [dictionary removeObjectForKey:NSPrintFirstPage];
        [dictionary removeObjectForKey:NSPrintLastPage];
        NSPrintInfo *info = [[[NSPrintInfo alloc] initWithDictionary:dictionary] autorelease];
        info.paperSize = NSMakeSize(612, 792);
        info.orientation = NSPaperOrientationPortrait;
        info.topMargin = info.bottomMargin = 30;
        info.leftMargin = info.rightMargin = 24;
        info.horizontalPagination = NSPrintingPaginationModeAutomatic;
        info.verticalPagination = NSPrintingPaginationModeAutomatic;
        info.verticallyCentered = NO;
        NSPrintOperation *operation = [webView printOperationWithPrintInfo:info];
        operation.showsPrintPanel = NO;
        operation.showsProgressPanel = NO;
        operation.canSpawnSeparateThread = YES;
        [operation runOperationModalForWindow:window delegate:session
            didRunSelector:@selector(printOperationDidRun:success:contextInfo:) contextInfo:NULL];
        while (!session.printed && !session.failed && NSProcessInfo.processInfo.systemUptime < deadline)
            [NSRunLoop.currentRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
        PDFDocument *pdf = [[[PDFDocument alloc] initWithURL:[NSURL fileURLWithPath:destination]] autorelease];
        success = session.printed && session.succeeded && pdf.pageCount > 0 && pdf.allowsPrinting;
        // The helper process exits on timeout, so an unfinished WebKit job can
        // never resume writing after its parent removes the private spool.
    }
    [webView stopLoading];
    webView.navigationDelegate = nil;
    if (!success) [NSFileManager.defaultManager removeItemAtPath:destination error:NULL];
    return success;
}

// Existing pdfFromURL callers regenerate a derived <html>.pdf when a report
// changes. Render a fresh sibling first, then replace atomically: failure must
// keep the previous PDF available, and the HTML/DICOM original is never moved.
static BOOL HorosUpdateHTMLReportPDF(NSString *path, NSTimeInterval timeout)
{
    NSString *destination = [path stringByAppendingPathExtension:@"pdf"];
    NSString *staged = [destination.stringByDeletingLastPathComponent stringByAppendingPathComponent:
        [NSString stringWithFormat:@"horos-html-print-%@.pdf", NSUUID.UUID.UUIDString]];
    @try {
        if (!HorosPrintHTMLToPDF(path, staged, timeout)) return NO;
        return rename(staged.fileSystemRepresentation, destination.fileSystemRepresentation) == 0;
    } @finally {
        [NSFileManager.defaultManager removeItemAtPath:staged error:NULL];
    }
}
