// Records, from inside a running development app, what a process listing
// cannot see (#627, #626): every thread the process creates - the short-lived
// ones included, through the pthread introspection hook - next to the threads
// alive, the open descriptors and the memory footprint, sampled on an interval;
// and the app's own time in each scan of INCOMING.
//
//   xcrun clang -dynamiclib -O2 -fno-objc-arc -framework Foundation \
//       tools/probe-app-resources.m -o probe-app-resources.dylib
//   DYLD_INSERT_LIBRARIES=probe-app-resources.dylib HOROS_RESOURCE_RECORDER=samples.jsonl <app>
//
// Each line of the file is one sample:
//   {"t": seconds since load, "created": threads created since load,
//    "alive": threads alive, "fds": open descriptors, "footprint": bytes}
// or, for every -[DicomDatabase importFilesFromIncomingDir:listenerCompressionSettings:],
//   {"scan_start": t, "scan_end": t, "imported": files, "created": threads created at its end}
// HOROS_RESOURCE_INTERVAL_MS sets the interval (default 100). The sampler is a
// thread of its own, created once at load and counted like any other.
#import <Foundation/Foundation.h>
#include <objc/runtime.h>
#include <libproc.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <pthread.h>
#include <pthread/introspection.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static atomic_long created = 0;
static pthread_introspection_hook_t previous;
static FILE *recording = NULL;
static mach_timebase_info_data_t timebase;
static uint64_t loaded = 0;

static double secondsSinceLoad(void) {
    return (double)(mach_absolute_time() - loaded) * timebase.numer / timebase.denom / 1e9;
}

static void hook(unsigned int event, pthread_t thread, void *address, size_t size) {
    if (event == PTHREAD_INTROSPECTION_THREAD_CREATE)
        atomic_fetch_add(&created, 1);
    if (previous)
        previous(event, thread, address, size);
}

static int aliveThreads(void) {
    thread_act_array_t threads;
    mach_msg_type_number_t count;
    if (task_threads(mach_task_self(), &threads, &count) != KERN_SUCCESS)
        return -1;
    for (mach_msg_type_number_t i = 0; i < count; i++)
        mach_port_deallocate(mach_task_self(), threads[i]);
    vm_deallocate(mach_task_self(), (vm_address_t)threads, sizeof(thread_t) * count);
    return (int)count;
}

static int openDescriptors(void) {
    static struct proc_fdinfo buffer[16384];
    int bytes = proc_pidinfo(getpid(), PROC_PIDLISTFDS, 0, buffer, sizeof(buffer));
    return bytes < 0 ? -1 : bytes / (int)PROC_PIDLISTFD_SIZE;
}

static unsigned long long footprint(void) {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS)
        return 0;
    return info.phys_footprint;
}

static void *sample(void *argument) {
    const char *interval = getenv("HOROS_RESOURCE_INTERVAL_MS");
    useconds_t pause = (useconds_t)((interval ? atoi(interval) : 100) * 1000);
    for (;;) {
        char line[256];
        snprintf(line, sizeof(line), "{\"t\": %.3f, \"created\": %ld, \"alive\": %d, \"fds\": %d, \"footprint\": %llu}\n",
                 secondsSinceLoad(), atomic_load(&created), aliveThreads(), openDescriptors(), footprint());
        flockfile(recording);
        fputs(line, recording);
        fflush(recording);
        funlockfile(recording);
        usleep(pause);
    }
    return NULL;
}

typedef NSInteger (*ImportIMP)(id, SEL, NSNumber *, int);
static ImportIMP originalImport = NULL;

static NSInteger timedImport(id database, SEL selector, NSNumber *showGUI, int compression) {
    double start = secondsSinceLoad();
    NSInteger imported = originalImport(database, selector, showGUI, compression);
    char line[256];
    snprintf(line, sizeof(line), "{\"scan_start\": %.6f, \"scan_end\": %.6f, \"imported\": %ld, \"created\": %ld}\n",
             start, secondsSinceLoad(), (long)imported, atomic_load(&created));
    flockfile(recording);
    fputs(line, recording);
    fflush(recording);
    funlockfile(recording);
    return imported;
}

__attribute__((constructor)) static void startRecording(void) {
    const char *variable = getenv("HOROS_RESOURCE_RECORDER");
    if (!variable)
        return;
    recording = fopen(variable, "a");
    // The helpers the app launches (Decompress, dciodvfy) must not record into
    // the same file: they do not inherit the recorder.
    unsetenv("HOROS_RESOURCE_RECORDER");
    unsetenv("DYLD_INSERT_LIBRARIES");
    if (!recording)
        return;
    mach_timebase_info(&timebase);
    loaded = mach_absolute_time();
    previous = pthread_introspection_hook_install(hook);
    Method import = class_getInstanceMethod(objc_getClass("DicomDatabase"),
                                            sel_registerName("importFilesFromIncomingDir:listenerCompressionSettings:"));
    if (import)
        originalImport = (ImportIMP)method_setImplementation(import, (IMP)timedImport);
    fprintf(recording, "{\"recorder\": \"loaded\", \"incoming_scans_timed\": %s}\n", import ? "true" : "false");
    fflush(recording);
    pthread_t sampler;
    if (pthread_create(&sampler, NULL, sample, NULL) == 0)
        pthread_detach(sampler);
}
