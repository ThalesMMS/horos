import AppKit

@main
struct LabelHeightTests {
    static func main() {
        let source = ["ROI", "", "Area: 25 mm²", "Mean: 22.5", "Median: 22.5", ""]
        for scale: CGFloat in [1, 2] {
            for capacity in 1...6 {
                let height = CGFloat(capacity) * 20 * scale + 2
                let count = Int(floor((height - 2) / (20 * scale)))
                let actual = ROILabelPresentation.fitLines(source, maximumLineCount: count)
                let nonempty = actual.filter { !$0.isEmpty }
                precondition(CGFloat(nonempty.count) * 20 * scale + 2 <= height)
                if capacity < 4 {
                    precondition(nonempty.last == "…")
                    precondition(Array(nonempty.dropLast()) == Array(source.filter { !$0.isEmpty }.prefix(capacity - 1)))
                } else {
                    precondition(actual == source)
                }
            }
        }
        precondition(ROILabelPresentation.fitLines(source, maximumLineCount: 0) == ["…"])
        precondition(ROILabelPresentation.fitLines(source, maximumLineCount: -1) == ["…"])
        precondition(ROILabelPresentation.fitLines(["", ""], maximumLineCount: 0) == ["", ""])
        let font = NSFont.systemFont(ofSize: 12)
        let long = [String(repeating: "測定 👩🏽‍⚕️ ", count: 100), "Median: 22.5"]
        let wrapped = ROILabelPresentation.wrapLines(long, font: font, maximumWidth: 120)
        let small = ROILabelPresentation.fitLines(wrapped, maximumLineCount: 3)
        precondition(small.count == 3 && small.last == "…")
        let restored = ROILabelPresentation.fitLines(wrapped, maximumLineCount: wrapped.count)
        precondition(restored == wrapped && restored.joined() == long.joined())
        print("PASS: label height at 1x/2x, explicit overflow, empty lines, tiny panes and complete text restoration")
    }
}
