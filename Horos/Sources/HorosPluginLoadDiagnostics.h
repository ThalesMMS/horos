#import <Foundation/Foundation.h>

// Process-local outcomes, keyed by the resolved bundle path, never by display name.
static NSMutableDictionary *HorosPluginLoadOutcomes;

static void HorosRecordPluginLoad(NSString *path, NSString *state, NSString *reason)
{
    if (!path.length) return;
    @synchronized (NSBundle.class) {
        if (!HorosPluginLoadOutcomes) HorosPluginLoadOutcomes = [NSMutableDictionary new];
        HorosPluginLoadOutcomes[path] = @{ @"loadState":state, @"loadReason":reason };
    }
}

static NSDictionary *HorosPluginLoadOutcome(NSString *path, BOOL active)
{
    @synchronized (NSBundle.class) {
        NSDictionary *outcome = HorosPluginLoadOutcomes[path];
        if (!active) return @{
            @"loadState":NSLocalizedString(@"Installed", nil),
            @"loadReason":NSLocalizedString(@"This plugin is disabled. Enable it and restart Horos to load it. Already loaded code remains in this process until restart.", nil)
        };
        if (outcome) return [[outcome retain] autorelease];
        return @{
            @"loadState":NSLocalizedString(@"Not loaded", nil),
            @"loadReason":NSLocalizedString(@"No successful load was recorded in this session. Restart Horos; check protected mode, duplicate plugins and DoNotLoad.txt if it remains unavailable.", nil)
        };
    }
}
