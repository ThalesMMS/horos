import Foundation

/// Separate the Dental3D/CBCT ray-cast Z-buffer crash from a plugin ABI miss.
///
/// Upstream Horos 2.2 died in `vtkFixedPointRayCastImage::GetZBufferValue`
/// on a worker thread while Dental3DPlugin was still inside
/// `configurePlugin`. That is not `NSExecutableArchitectureMismatchError` (3585)
/// and not a missing dylib. A plugin that actually loads on arm64 still
/// triggers fixed-point ray casting; Intermix then reads a Z buffer that
/// CaptureZBuffer left NULL or zero-sized. VTK is not rebuilt: the Horos
/// mapper drops that buffer before `RenderSubVolume`.
@objc(HorosRayCastZBuffer)
public final class RayCastZBuffer: NSObject {

    @objc(isUsableUseZBuffer:pointerValid:width:height:)
    public static func isUsable(useZBuffer: Bool, pointerValid: Bool, width: Int, height: Int) -> Bool {
        useZBuffer && pointerValid && width > 0 && height > 0
    }

    /// `raycast-zbuffer` is the GetZBufferValue stack. Cocoa executable-load
    /// errors are `abi-plugin-load`. They are not interchangeable.
    @objc(classifyFailureStackSymbol:loadErrorDomain:loadErrorCode:)
    public static func classifyFailure(stackSymbol: String, loadErrorDomain: String, loadErrorCode: Int) -> String {
        if stackSymbol.contains("GetZBufferValue") {
            return "raycast-zbuffer"
        }
        if loadErrorDomain == NSCocoaErrorDomain && (3584...3588).contains(loadErrorCode) {
            return "abi-plugin-load"
        }
        return "unknown"
    }

    /// Cone-beam volumes used with Dental3D: small isotropic voxels, a stack.
    @objc(diagnoseCBCTSpacingMM:sliceIntervalMM:sliceCount:pixelWidth:pixelHeight:)
    public static func diagnoseCBCT(spacingMM: Double, sliceIntervalMM: Double,
                                      sliceCount: Int, pixelWidth: Int, pixelHeight: Int) -> String {
        guard spacingMM.isFinite, sliceIntervalMM.isFinite,
              spacingMM > 0, sliceIntervalMM > 0,
              sliceCount >= 2, pixelWidth > 0, pixelHeight > 0 else {
            return "invalid"
        }
        let ratio = spacingMM / sliceIntervalMM
        guard ratio.isFinite, ratio >= 0.5, ratio <= 2,
              (0.05...0.8).contains(spacingMM),
              (0.05...0.8).contains(sliceIntervalMM) else {
            return "invalid"
        }
        return "cbct-ready"
    }

    /// A compatible, loaded plugin plus a CBCT volume may ray-cast. An ABI
    /// miss never reaches the mapper. A bad Z buffer is dropped, not fatal.
    @objc(classifyTriggerPluginCompatible:pluginLoaded:cbctDiagnosis:zBufferUsable:)
    public static func classifyTrigger(pluginCompatible: Bool, pluginLoaded: Bool,
                                        cbctDiagnosis: String, zBufferUsable: Bool) -> String {
        if !pluginCompatible || !pluginLoaded {
            return "abi-plugin-load"
        }
        if cbctDiagnosis != "cbct-ready" {
            return "invalid"
        }
        return zBufferUsable ? "raycast-ready" : "raycast-sanitized"
    }
}
