import Foundation
import Security
import LocalAuthentication

@objc(HorosDICOMwebCredentials)
public final class DICOMwebCredentials: NSObject {
    private static let readLock = NSLock()
    private static let service = "org.horosproject.DICOMweb.credentials"
    private static func key(_ identifier: String) throws -> [String: Any] {
        guard UUID(uuidString: identifier) != nil else { throw failure(errSecParam) }
        return [kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service, kSecAttrAccount as String: identifier]
    }
    private static func failure(_ status: OSStatus) -> NSError {
        NSError(domain: "HorosDICOMwebCredentials", code: Int(status), userInfo: [NSLocalizedDescriptionKey:
            "DICOMweb credentials could not be accessed. Update the credentials in Locations or unlock the keychain."])
    }
    @objc(saveForIdentifier:username:password:bearerToken:error:)
    public static func save(identifier: String, username: String, password: String, bearerToken: String) throws {
        let header: String
        if !bearerToken.isEmpty {
            guard !bearerToken.contains("\r"), !bearerToken.contains("\n") else { throw failure(errSecParam) }
            header = "Bearer " + bearerToken
        } else {
            guard !username.isEmpty, !username.contains(":"), !password.isEmpty else { throw failure(errSecParam) }
            header = "Basic " + Data((username + ":" + password).utf8).base64EncodedString()
        }
        var query = try key(identifier)
        let value = [kSecValueData as String: Data(header.utf8)]
        let status = SecItemUpdate(query as CFDictionary, value as CFDictionary)
        if status == errSecItemNotFound {
            query.merge(value) { _, new in new }
            query[kSecAttrSynchronizable as String] = false
            let added = SecItemAdd(query as CFDictionary, nil)
            guard added == errSecSuccess else { throw failure(added) }
        } else if status != errSecSuccess { throw failure(status) }
    }
    @objc(headerForIdentifier:error:)
    public static func header(identifier: String) throws -> String {
        var query = try key(identifier)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        let context = LAContext(); context.interactionNotAllowed = true
        query[kSecUseAuthenticationContext as String] = context
        // File-based macOS keychains ignore the SecItem/LAContext UI flags.
        // Serialize our reads and restore the process setting immediately afterward.
        readLock.lock()
        defer { readLock.unlock() }
        var interactionAllowed: DarwinBoolean = false
        let previous = SecKeychainGetUserInteractionAllowed(&interactionAllowed)
        guard previous == errSecSuccess else { throw failure(previous) }
        let disabled = SecKeychainSetUserInteractionAllowed(false)
        guard disabled == errSecSuccess else { throw failure(disabled) }
        defer { SecKeychainSetUserInteractionAllowed(interactionAllowed.boolValue) }
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data,
              let header = String(data: data, encoding: .utf8), !header.contains("\r"), !header.contains("\n")
        else { throw failure(status) }
        return header
    }
    @objc(removeForIdentifier:error:)
    public static func remove(identifier: String) throws {
        let status = SecItemDelete(try key(identifier) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw failure(status) }
    }
}
