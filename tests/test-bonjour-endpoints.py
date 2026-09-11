#!/usr/bin/env python3
"""Bonjour endpoints deduplicate against saved servers without merging distinct ones."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
#import <Foundation/Foundation.h>
#import "DCMBonjourEndpoint.h"
#include <netinet/in.h>
#include <sys/socket.h>
#include <arpa/inet.h>

#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)

// Stands in for the resolved NSNetService: only hostName and addresses are read.
@interface Service:NSObject
@property(retain) NSString *hostName;
@property(retain) NSArray *addresses;
@end
@implementation Service
@end

static NSData *ipv4(const char *address, uint16_t port) {
    struct sockaddr_in value = {};
    value.sin_len = sizeof(value); value.sin_family = AF_INET;
    value.sin_port = htons(port); inet_pton(AF_INET,address,&value.sin_addr);
    return [NSData dataWithBytes:&value length:sizeof(value)];
}
static NSData *ipv6(const char *address, uint16_t port, uint32_t scope) {
    struct sockaddr_in6 value = {};
    value.sin6_len = sizeof(value); value.sin6_family = AF_INET6;
    value.sin6_port = htons(port); value.sin6_scope_id = scope;
    inet_pton(AF_INET6,address,&value.sin6_addr);
    return [NSData dataWithBytes:&value length:sizeof(value)];
}
static NSDictionary *saved(id address, id port) {
    return [NSDictionary dictionaryWithObjectsAndKeys:address,@"Address",port,@"Port",nil];
}
static BOOL configured(NSArray *servers, Service *service, int port) {
    return DCMBonjourEndpointAlreadyConfigured(servers,(NSNetService *)service,port);
}

int main(){@autoreleasepool{
 Service *service = [Service new];

 // A saved entry holding the IP is the same endpoint the service advertises.
 service.hostName = @"scanner.local.";
 service.addresses = @[ipv4("10.0.0.4",11112)];
 check(configured(@[saved(@"10.0.0.4",@"11112")],service,11112));
 // ...and so is one holding the hostname, in any case, with or without the dot.
 check(configured(@[saved(@"Scanner.Local",@11112)],service,11112));
 check(configured(@[saved(@"scanner.local.",@"11112")],service,11112));
 // A different port is a different endpoint, whichever side differs.
 check(!configured(@[saved(@"10.0.0.4",@"104")],service,11112));
 service.addresses = @[ipv4("10.0.0.4",104)];
 service.hostName = nil;
 check(!configured(@[saved(@"10.0.0.4",@"11112")],service,11112));
 // An unrelated host on the same port stays.
 service.addresses = @[ipv4("10.0.0.4",11112)];
 check(!configured(@[saved(@"10.0.0.5",@"11112")],service,11112));

 // Link-local IPv6 in different zones are different interfaces, not duplicates.
 service.hostName = nil;
 service.addresses = @[ipv6("fe80::1",11112,1)];
 check(configured(@[saved(@"fe80::1%lo0",@"11112")],service,11112));
 check(!configured(@[saved(@"fe80::1%en3",@"11112")],service,11112));
 check(!configured(@[saved(@"fe80::1",@"11112")],service,11112));
 // A global IPv6 has no zone and matches in bracketed or bare form.
 service.addresses = @[ipv6("2001:db8::1",11112,0)];
 check(configured(@[saved(@"2001:db8::1",@"11112")],service,11112));
 check(configured(@[saved(@"[2001:DB8:0:0:0:0:0:1]",@"11112")],service,11112));
 check(!configured(@[saved(@"2001:db8::2",@"11112")],service,11112));
 // A v4-mapped address is the same host as its IPv4 form.
 service.addresses = @[ipv6("::ffff:10.0.0.4",11112,0)];
 check(configured(@[saved(@"10.0.0.4",@"11112")],service,11112));

 // Nothing here may crash or match by accident.
 service.hostName = @"";
 service.addresses = @[];
 check(!configured(@[saved(@"",@"11112")],service,11112));
 service.hostName = nil;
 service.addresses = nil;
 check(!configured(@[saved(@"10.0.0.4",@"11112")],service,11112));
 service.hostName = @"   ";
 service.addresses = @[[NSData data], (id)@"not a socket", ipv4("10.0.0.4",11112),
                       [NSData dataWithBytes:"\x10\x02" length:2]];
 check(configured(@[saved(@"10.0.0.4",@"11112")],service,11112));
 check(!configured(@[saved(@"  ",@"11112")],service,11112));
 // Surrounding whitespace in a saved port is tolerated, since it is typed by
 // hand; anything else in the field is not a port.
 check(configured(@[saved(@"10.0.0.4",@" 11112 ")],service,11112));
 // Malformed or hostile saved rows are skipped rather than matched.
 check(!configured(@[(id)@"not a dictionary",
                     saved(@"10.0.0.4",@"11112x"),
                     saved(@"10.0.0.4",@"111 12"),
                     saved(@"10.0.0.4",@""),
                     saved(@"10.0.0.4",[NSNull null]),
                     saved([NSNull null],@"11112"),
                     saved(@"10.0.0.4/../evil",@"11112"),
                     [NSDictionary dictionary]],
                   service,11112));
 // Out-of-range ports are never considered configured.
 check(!configured(@[saved(@"10.0.0.4",@"0")],service,0));
 check(!configured(@[saved(@"10.0.0.4",@"70000")],service,70000));
 // An empty server list is the ordinary first-discovery case.
 check(!configured(@[],service,11112));

 NSLog(@"PASS: hostname and saved IP on one port collapse; ports, zones and hosts stay distinct; v4-mapped equivalence; empty, malformed and hostile input neither crash nor match");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-bonjour-') as folder:
    p = Path(folder)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-framework', 'Foundation',
                    '-I', str(root / 'DCM Framework'), str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
