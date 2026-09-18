// The NIfTI-1 I/O library on its own, loaded from a dylib, for #631.
//
//   probe-nifti-library dump <dylib> <file>...
//       what the library reads from each file, as one JSON object per line:
//       nifti_read_header's fields, nifti_image_read's image without and with
//       its data (every voxel, in the file's order, as numbers), the extension
//       codes and texts, the orientation codes of qto_xyz and sto_xyz, and the
//       length of nifti_image_to_ascii. A call that refuses the file is null.
//
//   probe-nifti-library interleave <dylib A> <dylib B> <file list> <iterations>
//       times both builds call by call on the same files: for each "label path"
//       line of the list, <label>_header_us (nifti_read_header and free, what
//       +[DicomFile isNIfTIFile:] costs), <label>_describe_us (nifti_image_read
//       without data, nifti_image_to_ascii, and both freed: the metadata
//       window) and <label>_load_us with <label>_load_cpu_us (nifti_image_read
//       with data and nifti_image_free: what DCMPix pays per frame). Prints
//       {"A": {metric: [...]}, "B": {...}}; HOROS_AB_FIRST names the build that
//       goes first in the first iteration, and the order alternates after.
//
// Both builds are compiled against these headers: the structures they share
// did not change between library 1.43 and 2.1.0 (tests/test-nifti-upstream.py
// compares the layouts).
//
//   xcrun clang -O2 tools/probe-nifti-library.c -o probe-nifti-library
#include <dlfcn.h>
#include <mach/mach_time.h>
#include <math.h>
#include <pthread/qos.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "../NIfTI_Library/nifti1_io.h"

typedef struct {
    nifti_1_header *(*read_header)(const char *, int *, int);
    nifti_image *(*image_read)(const char *, int);
    void (*image_free)(nifti_image *);
    char *(*to_ascii)(const nifti_image *);
    void (*orientation)(mat44, int *, int *, int *);
    void (*set_debug_level)(int);
} Library;

static Library load(const char *path) {
    void *handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        fprintf(stderr, "cannot load %s: %s\n", path, dlerror());
        exit(2);
    }
    Library library = {
        dlsym(handle, "nifti_read_header"), dlsym(handle, "nifti_image_read"), dlsym(handle, "nifti_image_free"),
        dlsym(handle, "nifti_image_to_ascii"), dlsym(handle, "nifti_mat44_to_orientation"),
        dlsym(handle, "nifti_set_debug_level"),
    };
    if (!library.read_header || !library.image_read || !library.image_free || !library.to_ascii ||
        !library.orientation || !library.set_debug_level) {
        fprintf(stderr, "%s lacks a NIfTI function\n", path);
        exit(2);
    }
    library.set_debug_level(0);  // errors are this probe's to report, not stderr's
    return library;
}

static void json_string(const char *text, size_t length) {
    putchar('"');
    for (size_t i = 0; i < length && text[i]; i++) {
        unsigned char c = (unsigned char)text[i];
        if (c == '"' || c == '\\') printf("\\%c", c);
        else if (c < 0x20 || c >= 0x7f) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}

// A header full of noise can hold NaN or infinities, which JSON cannot: null.
static void json_number(double value) {
    if (isfinite(value)) printf("%.9g", value);
    else printf("null");
}

static void json_floats(const float *values, int count) {
    putchar('[');
    for (int i = 0; i < count; i++) {
        if (i) putchar(',');
        json_number(values[i]);
    }
    putchar(']');
}

static void json_matrix(mat44 m) {
    putchar('[');
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++) {
            if (r || c) putchar(',');
            json_number(m.m[r][c]);
        }
    putchar(']');
}

static double voxel(const nifti_image *nim, size_t index) {
    const void *data = nim->data;
    switch (nim->datatype) {
        case DT_UINT8: return ((const unsigned char *)data)[index];
        case DT_INT8: return ((const signed char *)data)[index];
        case DT_INT16: return ((const short *)data)[index];
        case DT_UINT16: return ((const unsigned short *)data)[index];
        case DT_INT32: return ((const int *)data)[index];
        case DT_UINT32: return ((const unsigned int *)data)[index];
        case DT_FLOAT32: return ((const float *)data)[index];
        case DT_FLOAT64: return ((const double *)data)[index];
        /* three bytes a voxel: red x 65536 + green x 256 + blue, as the matrix packs them (#643) */
        case DT_RGB24: { const unsigned char *rgb = (const unsigned char *)data + 3 * index;
                         return rgb[0] * 65536.0 + rgb[1] * 256.0 + rgb[2]; }
        default: return 0;
    }
}

static void describe_image(Library *library, nifti_image *nim, int with_data) {
    if (!nim) {
        printf("null");
        return;
    }
    printf("{\"ndim\":%d,\"dim\":[", nim->ndim);
    for (int i = 0; i < 8; i++) printf("%s%d", i ? "," : "", nim->dim[i]);
    printf("],\"pixdim\":");
    json_floats(nim->pixdim, 8);
    printf(",\"nvox\":%zu,\"nbyper\":%d,\"datatype\":%d,\"nifti_type\":%d,\"byteorder\":%d,\"iname_offset\":%d",
           nim->nvox, nim->nbyper, nim->datatype, nim->nifti_type, nim->byteorder, nim->iname_offset);
    printf(",\"scl_slope\":");
    json_number(nim->scl_slope);
    printf(",\"scl_inter\":");
    json_number(nim->scl_inter);
    printf(",\"qform_code\":%d,\"sform_code\":%d,\"qto_xyz\":", nim->qform_code, nim->sform_code);
    json_matrix(nim->qto_xyz);
    printf(",\"sto_xyz\":");
    json_matrix(nim->sto_xyz);
    int i = 0, j = 0, k = 0;
    library->orientation(nim->qto_xyz, &i, &j, &k);
    printf(",\"orientation_q\":[%d,%d,%d]", i, j, k);
    i = j = k = 0;
    library->orientation(nim->sto_xyz, &i, &j, &k);
    printf(",\"orientation_s\":[%d,%d,%d],\"extensions\":[", i, j, k);
    for (int e = 0; e < nim->num_ext; e++) {
        printf("%s{\"ecode\":%d,\"esize\":%d,\"text\":", e ? "," : "", nim->ext_list[e].ecode, nim->ext_list[e].esize);
        json_string(nim->ext_list[e].edata ? nim->ext_list[e].edata : "",
                    nim->ext_list[e].esize > 8 ? (size_t)nim->ext_list[e].esize - 8 : 0);
        putchar('}');
    }
    char *ascii = library->to_ascii(nim);
    printf("],\"ascii_bytes\":%zu", ascii ? strlen(ascii) : 0);
    free(ascii);
    if (with_data) {
        printf(",\"data\":");
        if (!nim->data) printf("null");
        else {
            putchar('[');
            for (size_t v = 0; v < nim->nvox; v++) {
                if (v) putchar(',');
                json_number(voxel(nim, v));
            }
            putchar(']');
        }
    }
    putchar('}');
}

static int dump(int argc, char **argv) {
    Library library = load(argv[2]);
    for (int index = 3; index < argc; index++) {
        const char *path = argv[index];
        printf("{\"file\":");
        json_string(path, strlen(path));
        nifti_1_header *header = library.read_header(path, NULL, 0);
        printf(",\"header\":");
        if (!header) printf("null");
        else {
            printf("{\"sizeof_hdr\":%d,\"dim\":[", header->sizeof_hdr);
            for (int i = 0; i < 8; i++) printf("%s%d", i ? "," : "", header->dim[i]);
            printf("],\"pixdim\":");
            json_floats(header->pixdim, 8);
            printf(",\"datatype\":%d,\"bitpix\":%d,\"vox_offset\":", header->datatype, header->bitpix);
            json_number(header->vox_offset);
            printf(",\"scl_slope\":");
            json_number(header->scl_slope);
            printf(",\"scl_inter\":");
            json_number(header->scl_inter);
            printf(",\"qform_code\":%d,\"sform_code\":%d,\"magic\":", header->qform_code, header->sform_code);
            json_string(header->magic, 4);
            putchar('}');
            free(header);
        }
        nifti_image *image = library.image_read(path, 0);
        printf(",\"image\":");
        describe_image(&library, image, 0);
        library.image_free(image);
        image = library.image_read(path, 1);
        printf(",\"loaded\":");
        describe_image(&library, image, 1);
        library.image_free(image);
        printf("}\n");
    }
    return 0;
}

static double microseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1000.0;
}

// A busy moment before each timed call, so both builds start from a running
// core rather than one the scheduler has just parked (#627).
static void settle(void) {
    uint64_t start = mach_absolute_time();
    volatile unsigned long spin = 0;
    while (microseconds(start, mach_absolute_time()) < 2000.0) spin++;
}

typedef struct {
    char label[64];
    char path[4096];
} Entry;

typedef struct {
    double *values;
    size_t count, capacity;
} Series;

static void append(Series *series, double value) {
    if (series->count == series->capacity) {
        series->capacity = series->capacity ? series->capacity * 2 : 64;
        series->values = realloc(series->values, series->capacity * sizeof(double));
    }
    series->values[series->count++] = value;
}

enum { HEADER, DESCRIBE, LOAD, LOAD_CPU, METRICS };
static const char *metric_names[METRICS] = {"header_us", "describe_us", "load_us", "load_cpu_us"};

static void timed(Library *library, const char *path, Series *series) {
    settle();
    uint64_t t0 = mach_absolute_time();
    nifti_1_header *header = library->read_header(path, NULL, 0);
    free(header);
    append(&series[HEADER], microseconds(t0, mach_absolute_time()));

    settle();
    t0 = mach_absolute_time();
    nifti_image *image = library->image_read(path, 0);
    char *ascii = image ? library->to_ascii(image) : NULL;
    free(ascii);
    library->image_free(image);
    append(&series[DESCRIBE], microseconds(t0, mach_absolute_time()));

    settle();
    struct timespec c0, c1;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &c0);
    t0 = mach_absolute_time();
    image = library->image_read(path, 1);
    library->image_free(image);
    uint64_t t1 = mach_absolute_time();
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &c1);
    append(&series[LOAD], microseconds(t0, t1));
    append(&series[LOAD_CPU], (c1.tv_sec - c0.tv_sec) * 1e6 + (c1.tv_nsec - c0.tv_nsec) / 1e3);
    if (!image) {
        fprintf(stderr, "%s did not load\n", path);
        exit(3);
    }
}

static int interleave(int argc, char **argv) {
    if (argc < 6) return 2;
    Library libraries[2] = {load(argv[2]), load(argv[3])};
    FILE *list = fopen(argv[4], "r");
    if (!list) return 2;
    Entry entries[32];
    int count = 0;
    while (count < 32 && fscanf(list, "%63s %4095[^\n]\n", entries[count].label, entries[count].path) == 2) count++;
    fclose(list);
    int iterations = atoi(argv[5]);
    const char *first = getenv("HOROS_AB_FIRST");
    int start = first && strcmp(first, "B") == 0 ? 1 : 0;
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);

    Series *series = calloc((size_t)count * 2 * METRICS, sizeof(Series));
    for (int iteration = 0; iteration < iterations; iteration++) {
        for (int e = 0; e < count; e++) {
            int order = (start + iteration + e) % 2;
            for (int slot = 0; slot < 2; slot++) {
                int which = (order + slot) % 2;
                timed(&libraries[which], entries[e].path, &series[(e * 2 + which) * METRICS]);
            }
        }
    }
    printf("{");
    for (int which = 0; which < 2; which++) {
        printf("%s\"%s\":{", which ? "," : "", which ? "B" : "A");
        int firstMetric = 1;
        for (int e = 0; e < count; e++) {
            for (int m = 0; m < METRICS; m++) {
                Series *s = &series[(e * 2 + which) * METRICS + m];
                printf("%s\"%s_%s\":[", firstMetric ? "" : ",", entries[e].label, metric_names[m]);
                firstMetric = 0;
                for (size_t v = 0; v < s->count; v++) printf("%s%.4f", v ? "," : "", s->values[v]);
                printf("]");
            }
        }
        printf("}");
    }
    printf("}\n");
    return 0;
}

int main(int argc, char **argv) {
    if (argc >= 4 && strcmp(argv[1], "dump") == 0) return dump(argc, argv);
    if (argc >= 6 && strcmp(argv[1], "interleave") == 0) return interleave(argc, argv);
    fprintf(stderr, "usage: %s dump <dylib> <file>... | interleave <dylib A> <dylib B> <file list> <iterations>\n", argv[0]);
    return 2;
}
