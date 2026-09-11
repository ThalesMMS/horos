/* Local validation only: inject into the isolated development bundle.
 * Matches the preflight probe for 16 synthetic 32x32 float images.
 * Do not link this into Horos or use it with a clinical session. */
#include <stdlib.h>
#include <unistd.h>
static void *fail_probe(size_t size) {
    if (size == 6389760) {
        static const char note[] = "HOROS_TEST: refused 6389760-byte memory probe\n";
        write(2, note, sizeof(note)-1);
        return NULL;
    }
    return malloc(size);
}
__attribute__((used)) static struct { const void *replacement; const void *original; }
interpose __attribute__((section("__DATA,__interpose"))) = { (const void*)fail_probe, (const void*)malloc };
