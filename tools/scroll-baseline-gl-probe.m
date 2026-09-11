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

// Stage B uses the same input catalog as measure-planar-low-contrast.swift.
// Decode/windowing are timed by the Python phase harness. Here the retained
// GL_INTENSITY8 upload, fixed-function draw and completion are timed together.
static int measure_dataset(NSString *directory) {
    @autoreleasepool {
        NSDictionary *input=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:
            [directory stringByAppendingPathComponent:@"input.json"]] options:0 error:nil];
        int width=[input[@"width"] intValue],height=[input[@"height"] intValue];
        NSArray *entries=input[@"frames"];
        if(width<1 || height<1 || width>1024 || height>1024 || entries.count<1 || entries.count>1300)return 2;
        CGLPixelFormatAttribute attrs[]={kCGLPFAAccelerated,kCGLPFAColorSize,(CGLPixelFormatAttribute)24,
            kCGLPFAAllowOfflineRenderers,(CGLPixelFormatAttribute)0};
        CGLPixelFormatObj format=NULL;CGLContextObj context=NULL;GLint count=0;
        uint64_t initStart=mach_absolute_time();
        if(CGLChoosePixelFormat(attrs,&format,&count)!=kCGLNoError || !format)return 1;
        if(CGLCreateContext(format,NULL,&context)!=kCGLNoError || !context){CGLReleasePixelFormat(format);return 1;}
        CGLReleasePixelFormat(format);CGLSetCurrentContext(context);
        double initialization=ns_to_ms(mach_absolute_time()-initStart);
        NSString *extensions=[NSString stringWithUTF8String:(const char*)glGetString(GL_EXTENSIONS)];
        BOOL timer=[extensions containsString:@"GL_EXT_timer_query"];
        GLuint framebuffer=0,target=0,image=0,query=0;
        glGenTextures(1,&target);glBindTexture(GL_TEXTURE_2D,target);
        // The retained window is opaque RGB. GL_INTENSITY also carries alpha;
        // an artificial RGBA FBO would expose that unused channel as opacity.
        glTexImage2D(GL_TEXTURE_2D,0,GL_RGB8,width,height,0,GL_BGRA,GL_UNSIGNED_BYTE,NULL);
        glGenFramebuffersEXT(1,&framebuffer);glBindFramebufferEXT(GL_FRAMEBUFFER_EXT,framebuffer);
        glFramebufferTexture2DEXT(GL_FRAMEBUFFER_EXT,GL_COLOR_ATTACHMENT0_EXT,GL_TEXTURE_2D,target,0);
        if(glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT)!=GL_FRAMEBUFFER_COMPLETE_EXT)return 1;
        glDrawBuffer(GL_COLOR_ATTACHMENT0_EXT);glReadBuffer(GL_COLOR_ATTACHMENT0_EXT);
        glViewport(0,0,width,height);glDisable(GL_BLEND);glDisable(GL_DITHER);
        glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,width,0,height,-1,1);
        glMatrixMode(GL_MODELVIEW);glLoadIdentity();
        glGenTextures(1,&image);glBindTexture(GL_TEXTURE_RECTANGLE_EXT,image);
        glTexParameteri(GL_TEXTURE_RECTANGLE_EXT,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_RECTANGLE_EXT,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_REPLACE);
        glEnable(GL_TEXTURE_RECTANGLE_EXT);glPixelStorei(GL_UNPACK_ALIGNMENT,1);glPixelStorei(GL_PACK_ALIGNMENT,1);
        if(timer)glGenQueries(1,&query);
        NSMutableArray *pixels=[NSMutableArray array],*references=[NSMutableArray array],*samples=[NSMutableArray array];
        for(NSDictionary *entry in entries){
            NSData *data=[NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:entry[@"legacy"]]];
            NSData *reference=[NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:entry[@"expected"]]];
            if(data.length!=(NSUInteger)width*height || reference.length!=(NSUInteger)width*height*4)return 2;
            [pixels addObject:data];[references addObject:reference];
        }
        NSUInteger checked=0;int maximum=0;
        for(int pass=0;pass<4;pass++)for(NSUInteger index=0;index<entries.count;index++){@autoreleasepool{
            uint64_t start=mach_absolute_time();
            NSData *copy=[NSData dataWithBytes:[pixels[index] bytes] length:[pixels[index] length]];
            uint64_t snapshot=mach_absolute_time();
            if(timer)glBeginQuery(GL_TIME_ELAPSED_EXT,query);
            glTexImage2D(GL_TEXTURE_RECTANGLE_EXT,0,GL_INTENSITY8,width,height,0,GL_LUMINANCE,GL_UNSIGNED_BYTE,copy.bytes);
            uint64_t upload=mach_absolute_time();
            glBegin(GL_QUADS);
            glTexCoord2f(0,0);glVertex2f(0,0);
            glTexCoord2f(width,0);glVertex2f(width,0);
            glTexCoord2f(width,height);glVertex2f(width,height);
            glTexCoord2f(0,height);glVertex2f(0,height);
            glEnd();if(timer)glEndQuery(GL_TIME_ELAPSED_EXT);
            uint64_t submit=mach_absolute_time();glFinish();uint64_t completed=mach_absolute_time();
            GLuint64EXT gpu=0;if(timer)glGetQueryObjectui64vEXT(query,GL_QUERY_RESULT,&gpu);
            GLenum error=glGetError();if(error!=GL_NO_ERROR){fprintf(stderr,"GL error %u\n",error);return 1;}
            [samples addObject:@{@"pass":@(pass),@"frame":@(index),@"id":entries[index][@"id"],
                @"snapshot_ms":@(ns_to_ms(snapshot-start)),@"upload_ms":@(ns_to_ms(upload-snapshot)),
                @"allocate_encode_ms":@(ns_to_ms(submit-upload)),@"submit_wait_ms":@(ns_to_ms(completed-submit)),
                @"frame_wall_ms":@(ns_to_ms(completed-start)),@"gpu_ms":timer?@(gpu/1e6):[NSNull null]}];
            // Readback and the independent reference stay outside every timing.
            NSMutableData *actual=[NSMutableData dataWithLength:(NSUInteger)width*height*4];
            glReadPixels(0,0,width,height,GL_BGRA,GL_UNSIGNED_BYTE,actual.mutableBytes);
            const unsigned char *a=actual.bytes,*e=[references[index] bytes];
            for(NSUInteger byte=0;byte<actual.length;byte++){int difference=abs((int)a[byte]-(int)e[byte]);maximum=MAX(maximum,difference);}
            if(maximum>1 || glGetError()!=GL_NO_ERROR){fprintf(stderr,"pixel mismatch %d\n",maximum);return 1;}
            checked+=(NSUInteger)width*height;
        }}
        NSDictionary *report=@{@"backend":@"CGL fixed function",@"samples":samples,@"pixels_checked":@(checked),
            @"maximum_channel_error":@(maximum),@"pipeline_initialization_ms":@(initialization),
            @"gpu_timer_available":@(timer),@"framebuffer_readback_bytes":@(width*height*4),@"image_bytes":@(width*height),
            @"gl_error":@0,@"scope":@"offscreen GL_INTENSITY8 upload/draw/completion, not DCMView or compositor"};
        NSData *json=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted|NSJSONWritingSortedKeys error:nil];
        BOOL saved=[json writeToFile:[directory stringByAppendingPathComponent:@"gl-results.json"] atomically:YES];
        if(query)glDeleteQueries(1,&query);glDeleteTextures(1,&image);glDeleteTextures(1,&target);
        glDeleteFramebuffersEXT(1,&framebuffer);CGLSetCurrentContext(NULL);CGLDestroyContext(context);
        printf("PASS: %lu GL pixels; max channel error %d; GPU timer %s\n",(unsigned long)checked,maximum,timer?"available":"unavailable");
        return saved?0:1;
    }
}

int main(int argc, char **argv) {
    if(argc==3 && strcmp(argv[1],"--dataset")==0)return measure_dataset([NSString stringWithUTF8String:argv[2]]);
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
