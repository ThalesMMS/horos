#import <Foundation/Foundation.h>
#include <arpa/inet.h>
#include <net/if.h>

// Comparison only: never resolve DNS while assembling the UI's server list.
static inline NSString *DCMBonjourAddressKey(id value)
{
    if (![value isKindOfClass:NSString.class]) return nil;
    NSString *address = [value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if ([address hasPrefix:@"["] && [address hasSuffix:@"]"])
        address = [address substringWithRange:NSMakeRange(1,address.length-2)];
    if (!address.length) return nil;
    struct in_addr ipv4;
    char buffer[INET6_ADDRSTRLEN];
    if (inet_pton(AF_INET,address.UTF8String,&ipv4) == 1) {
        inet_ntop(AF_INET,&ipv4,buffer,sizeof(buffer));
        return [@"v4:" stringByAppendingString:[NSString stringWithUTF8String:buffer]];
    }
    NSArray *parts = [address componentsSeparatedByString:@"%"];
    struct in6_addr ipv6;
    if (parts.count <= 2 && inet_pton(AF_INET6,[parts[0] UTF8String],&ipv6) == 1) {
        NSString *zone = parts.count == 2 ? parts[1] : @"";
        if (parts.count == 2 && !zone.length) return nil;
        unsigned int scope = if_nametoindex(zone.UTF8String);
        if (scope) zone = [NSString stringWithFormat:@"%u",scope];
        if ([zone isEqualToString:@"0"]) zone = @"";
        if (IN6_IS_ADDR_V4MAPPED(&ipv6) && !zone.length) {
            inet_ntop(AF_INET, &ipv6.s6_addr[12],buffer,sizeof(buffer));
            return [@"v4:" stringByAppendingString:[NSString stringWithUTF8String:buffer]];
        }
        inet_ntop(AF_INET6,&ipv6,buffer,sizeof(buffer));
        return [NSString stringWithFormat:@"v6:%@%%%@",[NSString stringWithUTF8String:buffer],zone];
    }
    NSCharacterSet *invalid = [[NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._"] invertedSet];
    if ([address rangeOfCharacterFromSet:invalid].location != NSNotFound) return nil;
    address = address.lowercaseString;
    while ([address hasSuffix:@"."]) address = [address substringToIndex:address.length-1];
    return address.length ? [@"dns:" stringByAppendingString:address] : nil;
}

static inline NSString *DCMBonjourSocketAddress(NSData *data, int *port)
{
    if (![data isKindOfClass:NSData.class] || data.length < sizeof(struct sockaddr)) return nil;
    struct sockaddr_storage storage = {};
    memcpy(&storage,data.bytes,MIN(sizeof(storage),data.length));
    char buffer[INET6_ADDRSTRLEN];
    if (storage.ss_family == AF_INET && data.length >= sizeof(struct sockaddr_in)) {
        struct sockaddr_in *value = (struct sockaddr_in *)&storage;
        if (!inet_ntop(AF_INET,&value->sin_addr,buffer,sizeof(buffer))) return nil;
        if (port) *port = ntohs(value->sin_port);
        return [NSString stringWithUTF8String:buffer];
    }
    if (storage.ss_family == AF_INET6 && data.length >= sizeof(struct sockaddr_in6)) {
        struct sockaddr_in6 *value = (struct sockaddr_in6 *)&storage;
        if (!inet_ntop(AF_INET6,&value->sin6_addr,buffer,sizeof(buffer))) return nil;
        if (port) *port = ntohs(value->sin6_port);
        return value->sin6_scope_id ? [NSString stringWithFormat:@"%s%%%u",buffer,value->sin6_scope_id] : [NSString stringWithUTF8String:buffer];
    }
    return nil;
}

static inline BOOL DCMBonjourEndpointAlreadyConfigured(NSArray *servers, NSNetService *service, int port)
{
    if (port < 1 || port > 65535) return NO;
    NSMutableSet *addresses = [NSMutableSet set];
    NSString *hostname = DCMBonjourAddressKey(service.hostName);
    if (hostname) [addresses addObject:hostname];
    for (NSData *data in service.addresses) {
        int candidatePort = 0;
        NSString *address = DCMBonjourSocketAddress(data,&candidatePort);
        NSString *key = DCMBonjourAddressKey(address);
        if (key && candidatePort == port) [addresses addObject:key];
    }
    for (id server in servers) {
        if (![server isKindOfClass:NSDictionary.class]) continue;
        id value = [server objectForKey:@"Port"];
        if (![value isKindOfClass:NSString.class] && ![value isKindOfClass:NSNumber.class]) continue;
        NSScanner *scanner = [NSScanner scannerWithString:[value description]];
        NSInteger configuredPort = 0;
        if (![scanner scanInteger:&configuredPort] || !scanner.isAtEnd || configuredPort != port) continue;
        NSString *key = DCMBonjourAddressKey([server objectForKey:@"Address"]);
        if (key && [addresses containsObject:key]) return YES;
    }
    return NO;
}
