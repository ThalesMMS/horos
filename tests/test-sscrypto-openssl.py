#!/usr/bin/env python3
"""Exercise the public SSCrypto implementation against Horos's OpenSSL archive."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from dcmtk_build import ROOT, BUILD

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=ROOT/'cocoahttpserver/SSCrypto.m')
args = parser.parse_args()
openssl = BUILD/'OpenSSL.build/Install'
if not (openssl/'lib/libcrypto.a').is_file():
    print('skipped: needs OpenSSL from script/build_and_run.sh --verify')
    raise SystemExit(2)

code = r'''
#import <Foundation/Foundation.h>
#import "SSCrypto.h"
#include <openssl/crypto.h>
#include <openssl/provider.h>
#include <assert.h>
static NSData *text(NSString *value) { return [value dataUsingEncoding:NSUTF8StringEncoding]; }
int main(void) { @autoreleasepool {
    assert(!strcmp(OPENSSL_VERSION_TEXT, OpenSSL_version(OPENSSL_VERSION)));
    assert(OPENSSL_VERSION_MAJOR >= 3);
    assert(!OSSL_PROVIDER_available(NULL, "legacy"));
    NSData *plain = text(@"Horos synthetic payload");
    assert([[[SSCrypto getMD5ForData:plain] hexval] isEqual:@"2e3e02b09d423f879122046dab918767"]);
    assert([[[SSCrypto getSHA1ForData:plain] hexval] isEqual:@"d64e19d47e6f14d2415c56d7105fedd41c00da97"]);
    for (NSNumber *newlines in @[@NO, @YES]) {
        NSData *encoded = text([plain encodeBase64WithNewlines:newlines.boolValue]);
        assert([[encoded decodeBase64WithNewLines:newlines.boolValue] isEqual:plain]);
    }
    // These fixed vectors were also checked against the previous 1.1.1 archive.
    // In particular, do not change the default Blowfish key derivation silently.
    for (NSString *name in @[@"AES-256-CBC", @"BF-CBC"]) { @autoreleasepool {
        SSCrypto *crypto = [[SSCrypto alloc] initWithSymmetricKey:text(@"synthetic key")];
        NSString *cipher = [name isEqual:@"BF-CBC"] ? nil : name;
        NSString *expected = cipher ? @"c0947d2658202704ea3474ca3238fc1b8e62887a0cc9aaf6658c8a319e05ee28"
                                   : @"f97722f71ff1a5666435925ea0e0b5b38585d7ca4fd13090";
        [crypto setClearTextWithData:plain];
        assert([[[crypto encrypt:cipher] hexval] isEqual:expected]);
        assert([[crypto decrypt:cipher] isEqual:plain]);
        NSUInteger block = cipher ? 16 : 8;
        for (NSUInteger length = 1; length <= 3 * block + 1; ++length) {
            NSMutableData *input = [NSMutableData dataWithLength:length];
            memset(input.mutableBytes, 'x', length);
            [crypto setClearTextWithData:input];
            NSData *encrypted = [crypto encrypt:cipher];
            assert(encrypted.length == (length / block + 1) * block);
            assert([[crypto decrypt:cipher] isEqual:input]);
            // Truncation fails without publishing a partial plaintext.
            [crypto setCipherText:[encrypted subdataWithRange:NSMakeRange(0, encrypted.length - 1)]];
            assert([crypto decrypt:cipher] == nil);
            assert([[crypto clearTextAsData] isEqual:input]);
        }
        [crypto setClearTextWithData:text(@"abc")];
        assert([[[crypto digest:@"SHA256"] hexval] isEqual:@"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"]);
        assert([[[crypto digest:@"MD4"] hexval] isEqual:@"a448017aaf21d8525fc10ae87aa6729d"]);
        assert([crypto digest:@"HOROS-NO-SUCH-DIGEST"] == nil);
        NSData *previous = [crypto cipherTextAsData];
        assert([crypto encrypt:@"HOROS-NO-SUCH-CIPHER"] == nil);
        assert([[crypto cipherTextAsData] isEqual:previous]);
        assert(!OSSL_PROVIDER_available(NULL, "legacy"));
        [crypto release];
    }}
    // Provider teardown must not alter the process-wide DCMTK/TLS context either.
    assert(!OSSL_PROVIDER_available(NULL, "legacy"));
    NSData *privateKey = [SSCrypto generateRSAPrivateKeyWithLength:2048];
    NSData *publicKey = [SSCrypto generateRSAPublicKeyFromPrivateKey:privateKey];
    assert(privateKey && publicKey);
    SSCrypto *rsa = [[SSCrypto alloc] initWithPublicKey:publicKey privateKey:privateKey];
    [rsa setClearTextWithData:plain];
    assert([rsa encrypt] && [[rsa decrypt] isEqual:plain]);
    assert([rsa sign] && [[rsa verify] isEqual:plain]);
    [rsa release];
    puts("PASS: SSCrypto hashes, Base64, legacy vectors/provider isolation, padding boundaries, invalid input and RSA");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-sscrypto-') as directory:
    p = Path(directory)
    (p/'main.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
        '-Wno-deprecated-declarations', '-I'+str(openssl/'include'), '-I'+str(ROOT/'cocoahttpserver'),
        str(p/'main.m'), str(args.source), str(openssl/'lib/libcrypto.a'),
        '-framework', 'Foundation', '-o', str(p/'test')], check=True)
    subprocess.run([str(p/'test')], check=True, env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0',
        'UBSAN_OPTIONS': 'halt_on_error=1'})
