import AppKit
import simd

@objc(HorosSRSurfacePoint)
public final class SRSurfacePoint: NSObject {
    @objc public let x: Double
    @objc public let y: Double
    @objc public let z: Double

    @objc public init(x: Double, y: Double, z: Double) {
        self.x = x
        self.y = y
        self.z = z
    }

    var vector: SIMD3<Double> { SIMD3(x, y, z) }
}

/// Click, iso-surface hit and exported DICOM voxel for Surface Rendering 3D points.
///
/// `vtkWorldPointPicker` without a z-buffer returns the camera focal plane.
/// Iso actors are `PickableOff` so that picker never sees the surface. The
/// voxel conversion matches `-[SRView convert3Dto2Dpoint::]`: invert the
/// actor user matrix, subtract the actor position, divide by spacing.
@objc(HorosSRSurfacePointGeometry)
public final class SRSurfacePointGeometry: NSObject {
    /// VTK consumes view-local backing pixels; NSEvent locations are window points.
    @objc(displayPoint:inView:)
    public static func displayPoint(_ windowPoint: NSPoint, in view: NSView) -> NSPoint {
        VRInteractionGeometry.backingPoint(windowPoint, in: view)
    }

    @objc(voxelFromWorldX:y:z:rowMajorMatrix:actorPositionX:actorPositionY:actorPositionZ:spacingX:spacingY:spacingZ:)
    public static func voxel(fromWorldX worldX: Double, y worldY: Double, z worldZ: Double,
                             rowMajorMatrix matrix: [NSNumber],
                             actorPositionX: Double, actorPositionY: Double, actorPositionZ: Double,
                             spacingX: Double, spacingY: Double, spacingZ: Double) -> SRSurfacePoint? {
        guard matrix.count == 16 else { return nil }
        let columns = (
            SIMD4(matrix[0].doubleValue, matrix[4].doubleValue, matrix[8].doubleValue, matrix[12].doubleValue),
            SIMD4(matrix[1].doubleValue, matrix[5].doubleValue, matrix[9].doubleValue, matrix[13].doubleValue),
            SIMD4(matrix[2].doubleValue, matrix[6].doubleValue, matrix[10].doubleValue, matrix[14].doubleValue),
            SIMD4(matrix[3].doubleValue, matrix[7].doubleValue, matrix[11].doubleValue, matrix[15].doubleValue)
        )
        let inverted = simd_inverse(simd_double4x4(columns.0, columns.1, columns.2, columns.3))
        let mapped = inverted * SIMD4(worldX, worldY, worldZ, 1)
        var voxel = SIMD3(mapped.x, mapped.y, mapped.z) - SIMD3(actorPositionX, actorPositionY, actorPositionZ)
        if spacingX != 0 { voxel.x /= spacingX }
        if spacingY != 0 { voxel.y /= spacingY }
        if spacingZ != 0 { voxel.z /= spacingZ }
        guard voxel.x.isFinite, voxel.y.isFinite, voxel.z.isFinite else { return nil }
        return SRSurfacePoint(x: voxel.x, y: voxel.y, z: voxel.z)
    }

    public static func displayPoint(forWorld world: SIMD3<Double>,
                                    viewportWidth: Double, viewportHeight: Double,
                                    cameraPositionX: Double, cameraPositionY: Double, cameraPositionZ: Double,
                                    focalX: Double, focalY: Double, focalZ: Double,
                                    viewUpX: Double, viewUpY: Double, viewUpZ: Double,
                                    parallelScale: Double, viewAngle: Double, parallel: Bool) -> NSPoint? {
        guard let camera = basis(position: SIMD3(cameraPositionX, cameraPositionY, cameraPositionZ),
                                  focal: SIMD3(focalX, focalY, focalZ),
                                  viewUp: SIMD3(viewUpX, viewUpY, viewUpZ),
                                  viewport: SIMD2(viewportWidth, viewportHeight),
                                  parallelScale: parallelScale, viewAngle: viewAngle, parallel: parallel)
        else { return nil }
        let offset = world - camera.focal
        let xView = simd_dot(offset, camera.right)
        let yView = simd_dot(offset, camera.up)
        return NSPoint(x: (xView / camera.width + 0.5) * viewportWidth,
                       y: (yView / camera.height + 0.5) * viewportHeight)
    }

    public static func focalPlaneWorld(fromDisplayX displayX: Double, y displayY: Double,
                                       viewportWidth: Double, viewportHeight: Double,
                                       cameraPositionX: Double, cameraPositionY: Double, cameraPositionZ: Double,
                                       focalX: Double, focalY: Double, focalZ: Double,
                                       viewUpX: Double, viewUpY: Double, viewUpZ: Double,
                                       parallelScale: Double, viewAngle: Double, parallel: Bool) -> SIMD3<Double>? {
        guard let camera = basis(position: SIMD3(cameraPositionX, cameraPositionY, cameraPositionZ),
                                  focal: SIMD3(focalX, focalY, focalZ),
                                  viewUp: SIMD3(viewUpX, viewUpY, viewUpZ),
                                  viewport: SIMD2(viewportWidth, viewportHeight),
                                  parallelScale: parallelScale, viewAngle: viewAngle, parallel: parallel)
        else { return nil }
        let offset = viewOffset(displayX: displayX, displayY: displayY,
                                viewportWidth: viewportWidth, viewportHeight: viewportHeight, camera: camera)
        return camera.focal + offset.x * camera.right + offset.y * camera.up
    }

    public static func surfaceWorld(fromDisplayX displayX: Double, y displayY: Double,
                                     viewportWidth: Double, viewportHeight: Double,
                                     cameraPositionX: Double, cameraPositionY: Double, cameraPositionZ: Double,
                                     focalX: Double, focalY: Double, focalZ: Double,
                                     viewUpX: Double, viewUpY: Double, viewUpZ: Double,
                                     parallelScale: Double, viewAngle: Double, parallel: Bool,
                                     planePointX: Double, planePointY: Double, planePointZ: Double,
                                     planeNormalX: Double, planeNormalY: Double, planeNormalZ: Double) -> SIMD3<Double>? {
        guard let camera = basis(position: SIMD3(cameraPositionX, cameraPositionY, cameraPositionZ),
                                  focal: SIMD3(focalX, focalY, focalZ),
                                  viewUp: SIMD3(viewUpX, viewUpY, viewUpZ),
                                  viewport: SIMD2(viewportWidth, viewportHeight),
                                  parallelScale: parallelScale, viewAngle: viewAngle, parallel: parallel)
        else { return nil }
        let offset = viewOffset(displayX: displayX, displayY: displayY,
                                viewportWidth: viewportWidth, viewportHeight: viewportHeight, camera: camera)
        let origin: SIMD3<Double>
        let direction: SIMD3<Double>
        if parallel {
            origin = camera.position + offset.x * camera.right + offset.y * camera.up
            direction = camera.forward
        } else {
            origin = camera.position
            direction = simd_normalize((camera.focal + offset.x * camera.right + offset.y * camera.up) - camera.position)
        }
        return intersect(origin: origin, direction: direction,
                          point: SIMD3(planePointX, planePointY, planePointZ),
                          normal: SIMD3(planeNormalX, planeNormalY, planeNormalZ))
    }

    private struct Camera {
        let position: SIMD3<Double>
        let focal: SIMD3<Double>
        let forward: SIMD3<Double>
        let right: SIMD3<Double>
        let up: SIMD3<Double>
        let width: Double
        let height: Double
    }

    private static func basis(position: SIMD3<Double>, focal: SIMD3<Double>, viewUp: SIMD3<Double>,
                              viewport: SIMD2<Double>, parallelScale: Double, viewAngle: Double,
                              parallel: Bool) -> Camera? {
        guard viewport.x > 0, viewport.y > 0 else { return nil }
        let forward = focal - position
        let length = simd_length(forward)
        guard length > 0, simd_length(viewUp) > 0 else { return nil }
        let f = forward / length
        var right = simd_cross(f, simd_normalize(viewUp))
        let rightLength = simd_length(right)
        guard rightLength > 0 else { return nil }
        right /= rightLength
        let up = simd_cross(right, f)
        let height: Double
        if parallel {
            guard parallelScale > 0 else { return nil }
            height = 2 * parallelScale
        } else {
            height = 2 * length * tan(viewAngle * .pi / 360)
        }
        let width = height * (viewport.x / viewport.y)
        guard width > 0, height > 0, width.isFinite, height.isFinite else { return nil }
        return Camera(position: position, focal: focal, forward: f, right: right, up: up,
                      width: width, height: height)
    }

    private static func viewOffset(displayX: Double, displayY: Double,
                                    viewportWidth: Double, viewportHeight: Double,
                                    camera: Camera) -> SIMD2<Double> {
        SIMD2((displayX / viewportWidth - 0.5) * camera.width,
              (displayY / viewportHeight - 0.5) * camera.height)
    }

    private static func intersect(origin: SIMD3<Double>, direction: SIMD3<Double>,
                                  point: SIMD3<Double>, normal: SIMD3<Double>) -> SIMD3<Double>? {
        let denom = simd_dot(normal, direction)
        guard abs(denom) > 1e-12 else { return nil }
        let t = simd_dot(normal, point - origin) / denom
        guard t.isFinite, t > 0 else { return nil }
        let hit = origin + t * direction
        guard hit.x.isFinite, hit.y.isFinite, hit.z.isFinite else { return nil }
        return hit
    }
}
