import AppKit

@main struct Test {
    static func main() {
        let font = NSFont(name: "Geneva", size: 12)!
        let text = "Mean: 123.456 HU SDev: 78.900 HU Sum: 123456789 Median: 123.456 HU"
        for width: CGFloat in [48, 100, 200, 400] {
            let lines = ROILabelPresentation.wrapLines([text], font: font, maximumWidth: width)
            precondition(lines.joined() == text)
            precondition(lines.allSatisfy { ($0 as NSString).size(withAttributes: [.font: font]).width <= width })
            precondition(lines == ROILabelPresentation.wrapLines([text], font: font, maximumWidth: width))
        }
        let unicode = String(repeating: "é👩🏽‍⚕️測", count: 200)
        let chunks = ROILabelPresentation.wrapLines([unicode], font: font, maximumWidth: 100)
        precondition(chunks.joined() == unicode)
        precondition(chunks.allSatisfy { $0.utf16.count <= 300 })
        precondition(ROILabelPresentation.wrapLines(["Length: 2.000 cm"], font: font, maximumWidth: 400) == ["Length: 2.000 cm"])
        precondition(ROILabelPresentation.wrapLines([text], font: font, maximumWidth: 0) == [text])
        let large = NSFont(name: "Geneva", size: 30)!
        let smallLines = ROILabelPresentation.wrapLines([text], font: font, maximumWidth: 100)
        let largeLines = ROILabelPresentation.wrapLines([text], font: large, maximumWidth: 100)
        precondition(largeLines.count > smallLines.count)
        print("PASS: wrapping width, full text, Unicode clusters, font changes, cache reuse and unwrapped short labels")
    }
}
