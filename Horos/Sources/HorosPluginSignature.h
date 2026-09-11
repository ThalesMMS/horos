#import <Foundation/Foundation.h>
#import <Security/Security.h>

// Validate existing seals before NSBundle executes code. This is integrity
// validation, not a notarization or publisher-trust assertion. Legacy unsigned
// plugins retain their existing behavior; dyld still applies process policy.
static BOOL HorosPluginSignatureAllowsLoading(NSString *path, NSError **error)
{
    if (error) *error = nil;
    SecStaticCodeRef code = NULL;
    OSStatus status = SecStaticCodeCreateWithPath((CFURLRef)[NSURL fileURLWithPath:path], kSecCSDefaultFlags, &code);
    CFErrorRef failure = NULL;
    if (status == errSecSuccess) {
        status = SecStaticCodeCheckValidityWithErrors(code, kSecCSCheckAllArchitectures | kSecCSCheckNestedCode, NULL, &failure);
    }
    if (code) CFRelease(code);
    BOOL allowed = status == errSecSuccess || status == errSecCSUnsigned;
    if (!allowed && error) {
        NSString *message = [(NSString *)SecCopyErrorMessageString(status, NULL) autorelease];
        NSMutableDictionary *info = [NSMutableDictionary dictionary];
        if (message) info[NSLocalizedDescriptionKey] = message;
        if (failure) info[NSUnderlyingErrorKey] = (NSError *)failure;
        *error = [NSError errorWithDomain:NSOSStatusErrorDomain code:status userInfo:info];
    }
    if (failure) CFRelease(failure);
    return allowed;
}
