import Foundation

/// How much a TLS peer has to prove, given a stored preference (#371, #317).
///
/// `TLSCertificateVerificationType` in `DICOMTLS.h` has three values — require
/// (0), verify (1), ignore (2) — and three places map it onto DCMTK's
/// `DcmCertificateVerification`: the query node, the store SCU and the listener.
/// All three were written the same way:
///
///     if(certVerification==RequirePeerCertificate)      … DCV_requireCertificate;
///     else if(certVerification==VerifyPeerCertificate)  … DCV_checkCertificate;
///     else                                              … DCV_ignoreCertificate;
///
/// The value comes from `NSUserDefaults` or from a server's parameter dictionary
/// as `[… intValue]`, and neither is bounded. Anything that is not 0 or 1 —
/// a corrupted preference, a stale plist, a value from a future version, a
/// negative — falls into the `else` and turns peer verification **off**. A
/// security control that fails open on unexpected input is the wrong way round.
///
/// This normalises first, so the mapping only ever sees a value it knows, and an
/// unknown one becomes the **strictest** rather than the loosest.
@objc(HorosTLSVerificationPolicy)
public final class TLSVerificationPolicy: NSObject {
    /// `RequirePeerCertificate` in `DICOMTLS.h`.
    @objc public static let require = 0
    /// `VerifyPeerCertificate`.
    @objc public static let verify = 1
    /// `IgnorePeerCertificate`.
    @objc public static let ignore = 2

    /// Always one of the three, and `require` for anything unrecognised.
    @objc(normalise:)
    public static func normalise(_ stored: Int) -> Int {
        switch stored {
        case verify: return verify
        case ignore: return ignore
        default: return require
        }
    }

    /// Whether a stored value said anything the application recognises. A caller
    /// that wants to warn about a broken preference can ask; the normalisation
    /// does not depend on it.
    @objc(isRecognised:)
    public static func isRecognised(_ stored: Int) -> Bool {
        stored == require || stored == verify || stored == ignore
    }

    /// Whether this level actually checks the peer. `ignore` is the only one
    /// that does not, and it has to be chosen deliberately.
    @objc(verifiesPeer:)
    public static func verifiesPeer(_ stored: Int) -> Bool {
        normalise(stored) != ignore
    }
}
