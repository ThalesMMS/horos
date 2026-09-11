// Upload 8-bit luminance frames the way DCMView presents them
// (GL_TEXTURE_RECTANGLE_EXT, GL_INTENSITY8, GL_LUMINANCE, GL_UNSIGNED_BYTE).
// This is a buffer/frame-time probe, not the Horos viewer.
#import <AppKit/AppKit.h>
#import <OpenGL/OpenGL.h>
#import <OpenGL/gl.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static double ns_to_ms(uint64_t delta) {
    mach_timebase_info_data_t info;
    mach_timebase_info(&info);
    return (double)delta * info.numer / info.denom / 1.0e6;
}

static int cmp_double(const void *a, const void *b) {
    const double da = *(const double *)a;
    const double db = *(const double *)b;
    return (da > db) - (da < db);
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: scroll-baseline-gl-probe WIDTH HEIGHT FRAMES\n");
        return 2;
    }
    const int width = atoi(argv[1]);
    const int height = atoi(argv[2]);
    const int frames = atoi(argv[3]);
    if (width <= 0 || height <= 0 || frames <= 0) return 2;

    CGLPixelFormatAttribute attrs[] = {
        kCGLPFAAccelerated,
        kCGLPFAColorSize, (CGLPixelFormatAttribute)24,
        kCGLPFAAllowOfflineRenderers,
        (CGLPixelFormatAttribute)0
    };
    CGLPixelFormatObj format = NULL;
    GLint virtualScreens = 0;
    if (CGLChoosePixelFormat(attrs, &format, &virtualScreens) != kCGLNoError || !format) {
        fprintf(stderr, "no accelerated pixel format\n");
        return 1;
    }
    CGLContextObj context = NULL;
    if (CGLCreateContext(format, NULL, &context) != kCGLNoError || !context) {
        CGLReleasePixelFormat(format);
        fprintf(stderr, "could not create CGL context\n");
        return 1;
    }
    CGLReleasePixelFormat(format);
    CGLSetCurrentContext(context);

    GLuint texture = 0;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_RECTANGLE_EXT, texture);
    glTexParameteri(GL_TEXTURE_RECTANGLE_EXT, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_RECTANGLE_EXT, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

    const size_t bytes = (size_t)width * (size_t)height;
    unsigned char *buffer = calloc(1, bytes);
    if (!buffer) return 1;
    double *samples = calloc((size_t)frames, sizeof(double));
    GLenum error = GL_NO_ERROR;
    for (int index = 0; index < frames; index++) {
        memset(buffer, (unsigned char)(index * 7), bytes);
        const uint64_t start = mach_absolute_time();
        glTexImage2D(GL_TEXTURE_RECTANGLE_EXT, 0, GL_INTENSITY8,
                     width, height, 0, GL_LUMINANCE, GL_UNSIGNED_BYTE, buffer);
        glFinish();
        samples[index] = ns_to_ms(mach_absolute_time() - start);
        error = glGetError();
        if (error != GL_NO_ERROR) break;
    }

    double p50 = 0, p95 = 0;
    if (error == GL_NO_ERROR) {
        qsort(samples, (size_t)frames, sizeof(double), cmp_double);
        p50 = samples[(frames - 1) / 2];
        p95 = samples[(int)((frames - 1) * 0.95)];
    }

    printf("{\"name\":\"CGL texture upload\",\"sampled\":%s,\"frames\":%d,"
           "\"width\":%d,\"height\":%d,\"p50_ms\":%.6f,\"p95_ms\":%.6f,"
           "\"gl_error\":%u,\"target\":\"GL_TEXTURE_RECTANGLE_EXT\","
           "\"internal_format\":\"GL_INTENSITY8\"}\n",
           error == GL_NO_ERROR ? "true" : "false", frames, width, height,
           p50, p95, (unsigned)error);

    free(samples);
    free(buffer);
    glDeleteTextures(1, &texture);
    CGLSetCurrentContext(NULL);
    CGLDestroyContext(context);
    return error == GL_NO_ERROR ? 0 : 1;
}
