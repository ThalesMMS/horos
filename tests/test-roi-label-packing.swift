import AppKit

@main struct Test {
    static func main() {
        let viewport = NSRect(x: 0, y: 0, width: 240, height: 160)
        var seed: UInt64 = 12345
        func random(_ bound: Int) -> Int {
            seed = seed &* 6364136223846793005 &+ 1
            return Int((seed >> 32) % UInt64(bound))
        }
        var feasible = 0
        for _ in 0..<200 {
            let obstacles = (0..<24).map { _ in
                NSRect(x: random(22)*10, y: random(14)*10, width: (random(5)+1)*10, height: (random(4)+1)*10)
            }
            let input = NSRect(x: random(20)*10, y: random(14)*10, width: 40, height: 20)
            let placed = ROILabelPresentation.placeLabelRect(input, inViewport: viewport, avoiding: obstacles.map(NSValue.init(rect:)))
            precondition(viewport.contains(placed) && placed.size == input.size)
            // Independent coarse feasibility oracle; a found position proves
            // free space, while a miss makes no claim about continuous space.
            var hasFree = false
            for y in stride(from: 0, through: 140, by: 5) {
                for x in stride(from: 0, through: 200, by: 5) {
                    let candidate = NSRect(x: x, y: y, width: 40, height: 20)
                    if obstacles.allSatisfy({ !candidate.intersects($0.insetBy(dx: -2, dy: -2)) }) { hasFree = true; break }
                }
                if hasFree { break }
            }
            if hasFree {
                feasible += 1
                precondition(obstacles.allSatisfy { !placed.intersects($0) })
            }
        }
        precondition(feasible > 100)
        print("PASS: 200 deterministic obstacle scenes, containment/size and \(feasible) independently proven free-space cases")
    }
}
