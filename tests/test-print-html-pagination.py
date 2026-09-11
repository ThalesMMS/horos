#!/usr/bin/env python3
"""#384 A exercises the exact WebKit PDF helper without a printer or visible UI."""
import subprocess
import tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
driver = r'''
#import "HorosHTMLPrint.h"
#define check(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
int main(int argc, char **argv) { @autoreleasepool {
    [NSApplication sharedApplication];
    NSString *folder = [NSString stringWithUTF8String:argv[1]];
    NSString *html = [folder stringByAppendingPathComponent:@"fixture.html"];
    NSString *pdf = [folder stringByAppendingPathComponent:@"pages.pdf"];
    // A stale previous print range must not truncate report conversion.
    NSPrintInfo.sharedPrintInfo.dictionary[NSPrintAllPages] = @NO;
    NSPrintInfo.sharedPrintInfo.dictionary[NSPrintFirstPage] = @2;
    NSPrintInfo.sharedPrintInfo.dictionary[NSPrintLastPage] = @2;
    NSData *original = [NSData dataWithContentsOfFile:html];
    check(HorosPrintHTMLToPDF(html, pdf, 20));
    PDFDocument *document = [[[PDFDocument alloc] initWithURL:[NSURL fileURLWithPath:pdf]] autorelease];
    check(document.pageCount == 3);
    check([[document pageAtIndex:0].string containsString:@"PRINT384-FIRST"]);
    check([[document pageAtIndex:1].string containsString:@"PRINT384-SECOND"]);
    PDFPage *last = [document pageAtIndex:2];
    check(last.numberOfCharacters == 0);
    unsigned char *pixels = calloc(612 * 792, 4);
    CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(pixels, 612, 792, 8, 612*4, space, (CGBitmapInfo)kCGImageAlphaPremultipliedLast);
    CGContextDrawPDFPage(context, last.pageRef);
    NSUInteger red = 0;
    for (NSUInteger i=0; i<612*792; i++)
        if (pixels[i*4] > 240 && pixels[i*4+1] < 10 && pixels[i*4+2] < 10) red++;
    check(red > 10000); // A graphics-only final page is real content, not a blank trailer.
    CGContextRelease(context); CGColorSpaceRelease(space); free(pixels);
    check([[NSData dataWithContentsOfFile:html] isEqualToData:original]);
    NSData *printed = [NSData dataWithContentsOfFile:pdf];
    check(!HorosPrintHTMLToPDF(html, pdf, 20)); // Never overwrite an existing original.
    check([[NSData dataWithContentsOfFile:pdf] isEqualToData:printed]);
    check(!HorosPrintHTMLToPDF([folder stringByAppendingPathComponent:@"missing.html"], [folder stringByAppendingPathComponent:@"missing.pdf"], 20));
    check(!HorosPrintHTMLToPDF(html, [folder stringByAppendingPathComponent:@"timeout.pdf"], 0));
    check(![NSFileManager.defaultManager fileExistsAtPath:[folder stringByAppendingPathComponent:@"timeout.pdf"]]);
    NSString *derived = [html stringByAppendingPathExtension:@"pdf"];
    NSData *previous = [@"PREVIOUS-DERIVED-PDF" dataUsingEncoding:NSUTF8StringEncoding];
    [previous writeToFile:derived atomically:YES];
    check(HorosUpdateHTMLReportPDF(html, 20));
    PDFDocument *updated = [[[PDFDocument alloc] initWithURL:[NSURL fileURLWithPath:derived]] autorelease];
    check(updated.pageCount == 3);
    check([[NSData dataWithContentsOfFile:html] isEqualToData:original]);
    NSString *absent = [folder stringByAppendingPathComponent:@"absent.html"];
    NSString *retained = [absent stringByAppendingPathExtension:@"pdf"];
    [previous writeToFile:retained atomically:YES];
    check(!HorosUpdateHTMLReportPDF(absent, 20));
    check([[NSData dataWithContentsOfFile:retained] isEqualToData:previous]);
    for (NSString *name in [NSFileManager.defaultManager contentsOfDirectoryAtPath:folder error:NULL])
        check(![name hasPrefix:@"horos-html-print-"]);
    puts("PASS: atomic refresh of derived report preserves prior PDF on failure; WebKit completion, 3 ordered pages including graphics-only last page, stale-range reset, preserved input, existing/missing/timeout failures");
    return 0;
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-print-384-html-') as temporary:
    folder = Path(temporary)
    (folder / 'fixture.html').write_text('''<!doctype html><html><head><style>
.page { break-after: page; height: 200px; }</style></head><body>
<div class="page">PRINT384-FIRST</div><div class="page">PRINT384-SECOND</div>
<svg width="200" height="150"><rect width="200" height="150" fill="red"/></svg></body></html>''')
    (folder / 'Check.m').write_text(driver)
    subprocess.run(['xcrun', 'clang', '-fblocks', '-I', str(root / 'Horos/Sources'), '-framework', 'AppKit', '-framework', 'WebKit', '-framework', 'Quartz', str(folder / 'Check.m'), '-o', str(folder / 'check')], check=True, timeout=60)
    subprocess.run([str(folder / 'check'), str(folder)], check=True, timeout=45)

# Decompress must use this helper, return failure and never trim graphics by character count.
source = (root / 'Decompress/Decompress.mm').read_bytes().decode('latin1')
body = source.split('if ([what isEqualToString:@"pdfFromURL"])', 1)[1].split('// deregister JPEG codecs', 1)[0]
assert 'HorosUpdateHTMLReportPDF' in body and '? 0 : 1' in body
assert 'numberOfCharacters' not in body and 'removePageAtIndex' not in body
