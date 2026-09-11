#!/usr/bin/env python3
"""A111: actual legacy GL fragments and Metal versus a scalar CPU oracle.

Tolerance: one byte per channel and no colours outside the discrete CLUT.
At a quantization boundary, admit the adjacent entry only within eight float32
ULPs of the double-precision interpolated intensity (0.001953125 at 2048).
This bounds rounding through the two bilinear mixes; it does not admit colour
mixing. Count these boundary cases separately. vImage is the host's resampler;
the C control uses its flags independently of the Swift texture preparation.
"""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--legacy-source', type=Path, default=root/'Horos/Sources/LegacyScalarCLUT.swift')
args = parser.parse_args()
host = (root/'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
quality = re.search(r'^#define QUALITY (\w+)$', host, re.M).group(1)
control = r'''
#include <Accelerate/Accelerate.h>
long hostScale(float *source, float *output, int width, int height, int scale) {
    vImage_Buffer src={source,height,width,width*4};
    vImage_Buffer dst={output,height*scale,width*scale,width*scale*4};
    return vImageScale_PlanarF(&src,&dst,NULL,QUALITY);
}
'''.replace('QUALITY', quality)
driver = r'''
import AppKit
import Metal
import OpenGL.GL

@main @MainActor struct Check {
    static func main() throws {
        guard let device=MTLCreateSystemDefaultDevice() else { exit(2) }
        let attrs:[NSOpenGLPixelFormatAttribute]=[UInt32(NSOpenGLPFAAccelerated),
            UInt32(NSOpenGLPFAColorSize),24,UInt32(NSOpenGLPFAAllowOfflineRenderers),0]
        guard let format=NSOpenGLPixelFormat(attributes:attrs),
              let context=NSOpenGLContext(format:format,share:nil) else { exit(2) }
        context.makeCurrentContext()
        let state=LegacyScalarCLUTState(), metal=try PlanarMetalRenderer(device:device)
        let w=16,h=8,outW=128,outH=64
        var source=(0..<w*h).map { Float(2032+($0*19)%33) }
        let original=source.withUnsafeBytes { Data($0) }
        let palette:[[UInt8]]=[[0,0,0],[0,0,255],[0,255,0],[0,255,255],
                              [255,0,0],[255,0,255],[255,255,0],[255,255,255]]
        let table=Data((0..<256).flatMap { palette[$0/32]+[255] })
        var fbo:GLuint=0,target:GLuint=0,input:GLuint=0
        glGenFramebuffersEXT(1,&fbo);glBindFramebufferEXT(GLenum(GL_FRAMEBUFFER_EXT),fbo)
        glGenTextures(1,&target);glBindTexture(GLenum(GL_TEXTURE_2D),target)
        glTexImage2D(GLenum(GL_TEXTURE_2D),0,GL_RGBA8,GLsizei(outW),GLsizei(outH),0,
                     GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),nil)
        glFramebufferTexture2DEXT(GLenum(GL_FRAMEBUFFER_EXT),GLenum(GL_COLOR_ATTACHMENT0_EXT),
                                  GLenum(GL_TEXTURE_2D),target,0)
        assert(glCheckFramebufferStatusEXT(GLenum(GL_FRAMEBUFFER_EXT))==GLenum(GL_FRAMEBUFFER_COMPLETE_EXT))
        glGenTextures(1,&input);glViewport(0,0,GLsizei(outW),GLsizei(outH))
        glMatrixMode(GLenum(GL_PROJECTION));glLoadIdentity()
        glMatrixMode(GLenum(GL_MODELVIEW));glLoadIdentity()
        glDisable(GLenum(GL_BLEND));glDisable(GLenum(GL_DEPTH_TEST))
        var checked=0,boundaryPixels=0
        for factor in [1,2,3] {
            let tw=w*factor,th=h*factor
            var enlarged=[Float](repeating:0,count:tw*th)
            if factor==1 { enlarged=source }
            else { assert(hostScale(&source,&enlarged,Int32(w),Int32(h),Int32(factor))==0) }
            glActiveTexture(GLenum(GL_TEXTURE0))
            glBindTexture(GLenum(GL_TEXTURE_RECTANGLE_EXT),input)
            glPixelStorei(GLenum(GL_UNPACK_ALIGNMENT),1);glPixelStorei(GLenum(GL_UNPACK_ROW_LENGTH),0)
            glTexImage2D(GLenum(GL_TEXTURE_RECTANGLE_EXT),0,GL_LUMINANCE32F_ARB,GLsizei(tw),GLsizei(th),0,
                         GLenum(GL_LUMINANCE),GLenum(GL_FLOAT),enlarged)
            for nearest in (factor==1 ? [false,true] : [false]) {
                glActiveTexture(GLenum(GL_TEXTURE0))
                let filter=nearest ? GL_NEAREST : GL_LINEAR
                glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT),GLenum(GL_TEXTURE_MIN_FILTER),filter)
                glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT),GLenum(GL_TEXTURE_MAG_FILTER),filter)
                glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT),GLenum(GL_TEXTURE_WRAP_S),GL_CLAMP_TO_EDGE)
                glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT),GLenum(GL_TEXTURE_WRAP_T),GL_CLAMP_TO_EDGE)
                for points:[Float] in [[0,0,16,0,0,8],[16,0,0,0,16,8],[0,8,16,8,0,0],[1,0.3,13,1.3,0,6.3]] {
                    let frame=try PlanarFrame(["width":w,"height":h,"pixels":original,"clut":table,
                        "frameIdentity":"synthetic","level":2047.77,"widthWindow":64,
                        "viewSize":[w,h],"screenToPixel":points,"softwareScale":factor,"nearest":nearest])
                    let draw=state.prepare(table:table,level:frame.window.x,width:64,nearest:nearest,context:context)!
                    state.setDraw(draw,forArray:1)
                    assert(state.draw(forArray:1)===draw)
                    // Non-default unpack/pixel-transfer state must not tint the
                    // CLUT upload, or leak into the next host upload.
                    glPixelStorei(GLenum(GL_UNPACK_ROW_LENGTH),9)
                    glPixelTransferf(GLenum(GL_RED_SCALE),0.3)
                    glPixelTransferf(GLenum(GL_RED_BIAS),0.7)
                    glActiveTexture(GLenum(GL_TEXTURE1))
                    assert(draw.begin())
                    func vertex(_ x:Float,_ y:Float,_ px:Float,_ py:Float) {
                        glTexCoord2f(px*Float(factor),py*Float(factor));glVertex2f(x,y)
                    }
                    glBegin(GLenum(GL_QUADS))
                    vertex(-1,1,points[0],points[1]);vertex(1,1,points[2],points[3])
                    vertex(1,-1,points[2]+points[4]-points[0],points[3]+points[5]-points[1])
                    vertex(-1,-1,points[4],points[5]);glEnd()
                    draw.end()
                    var active:GLint=0,rowLength:GLint=0,redScale:GLfloat=0
                    glGetIntegerv(GLenum(GL_ACTIVE_TEXTURE),&active)
                    glGetIntegerv(GLenum(GL_UNPACK_ROW_LENGTH),&rowLength)
                    glGetFloatv(GLenum(GL_RED_SCALE),&redScale)
                    assert(active==GL_TEXTURE1 && rowLength==9 && abs(redScale-0.3)<0.000001)
                    glPixelTransferf(GLenum(GL_RED_SCALE),1);glPixelTransferf(GLenum(GL_RED_BIAS),0)
                    glPixelStorei(GLenum(GL_PACK_ALIGNMENT),1)
                    var gl=[UInt8](repeating:0,count:outW*outH*4)
                    glReadPixels(0,0,GLsizei(outW),GLsizei(outH),GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),&gl)
                    try metal.update(frame)
                    let gpu=[UInt8](try metal.renderBGRA(width:outW,height:outH))
                    func sample(_ x:Int,_ y:Int)->Double { Double(enlarged[min(th-1,max(0,y))*tw+min(tw-1,max(0,x))]) }
                    for y in 0..<outH { for x in 0..<outW {
                        let u=(Double(x)+0.5)/Double(outW),v=(Double(y)+0.5)/Double(outH)
                        let px=(Double(points[0])+u*Double(points[2]-points[0])+v*Double(points[4]-points[0]))*Double(factor)
                        let py=(Double(points[1])+u*Double(points[3]-points[1])+v*Double(points[5]-points[1]))*Double(factor)
                        let value:Double
                        if nearest { value=sample(Int(floor(px)),Int(floor(py))) }
                        else {
                            let xx=px-0.5,yy=py-0.5,ix=Int(floor(xx)),iy=Int(floor(yy))
                            let dx=xx-Double(ix),dy=yy-Double(iy)
                            value=sample(ix,iy)*(1-dx)*(1-dy)+sample(ix+1,iy)*dx*(1-dy)
                                + sample(ix,iy+1)*(1-dx)*dy+sample(ix+1,iy+1)*dx*dy
                        }
                        let index=Int(floor(min(1,max(0,(value-Double(frame.window.x)+32)/64))*255+0.5))
                        let rgb=palette[index/32], expected=[rgb[2],rgb[1],rgb[0],255]
                        let slack=Double(Float(value).ulp)*8
                        func entry(_ scalar:Double)->Int {
                            Int(floor(min(1,max(0,(scalar-Double(frame.window.x)+32)/64))*255+0.5))
                        }
                        let allowed=(entry(value-slack)...entry(value+slack)).map { i -> [UInt8] in
                            let color=palette[i/32];return [color[2],color[1],color[0],255]
                        }
                        let legacyPixel=Array(gl[((outH-1-y)*outW+x)*4..<((outH-1-y)*outW+x)*4+4])
                        let metalPixel=Array(gpu[(y*outW+x)*4..<(y*outW+x)*4+4])
                        assert(allowed.contains(legacyPixel),
                            "legacy scalar mismatch factor=\(factor) nearest=\(nearest) pixel=\(x),\(y) value=\(value) points=\(points)")
                        assert(allowed.contains(metalPixel),
                            "Metal software mismatch factor=\(factor) pixel=\(x),\(y) value=\(value)")
                        if legacyPixel != expected || metalPixel != expected { boundaryPixels += 1 }
                        checked += 1
                    }}
                    assert(glGetError()==GLenum(GL_NO_ERROR))
                    state.setDraw(nil,forArray:1);assert(state.draw(forArray:1)==nil)
                }
            }
        }
        // Nonlinear/shutter modes provide host-windowed scalar bytes. They
        // still interpolate scalar values before the final CLUT, with no
        // second application of the original physical WL/WW.
        glActiveTexture(GLenum(GL_TEXTURE0));glBindTexture(GLenum(GL_TEXTURE_RECTANGLE_EXT),input)
        glPixelStorei(GLenum(GL_UNPACK_ROW_LENGTH),0)
        glTexImage2D(GLenum(GL_TEXTURE_RECTANGLE_EXT),0,GL_INTENSITY8,2,1,0,
                     GLenum(GL_LUMINANCE),GLenum(GL_UNSIGNED_BYTE),[UInt8(64),192])
        let steps=Data((0..<256).flatMap { $0<128 ? [UInt8(0),0,255,255] : [255,0,0,255] })
        func quad() {
            glBegin(GLenum(GL_QUADS))
            glTexCoord2f(0,0);glVertex2f(-1,1);glTexCoord2f(2,0);glVertex2f(1,1)
            glTexCoord2f(2,1);glVertex2f(1,-1);glTexCoord2f(0,1);glVertex2f(-1,-1);glEnd()
        }
        for nearest in [false,true] {
            let draw=state.prepare(table:steps,level:0.5,width:1,nearest:nearest,context:context)!
            assert(draw.begin());quad();draw.end()
            var pixels=[UInt8](repeating:0,count:outW*outH*4)
            glReadPixels(0,0,GLsizei(outW),GLsizei(outH),GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),&pixels)
            for y in 0..<outH { for x in 0..<outW {
                let expected:[UInt8]=x<64 ? [255,0,0,255] : [0,0,255,255]
                assert(Array(pixels[(y*outW+x)*4..<(y*outW+x)*4+4])==expected)
            }}
        }
        // A separate blending consumer has its own alpha table even when it
        // shares this context/program with the opaque viewer.
        let translucent=Data((0..<256).flatMap { _ in [UInt8(0),0,255,128] })
        let blend=state.prepare(table:translucent,level:0.5,width:1,nearest:false,context:context)!
        glEnable(GLenum(GL_BLEND));glBlendFunc(GLenum(GL_SRC_ALPHA),GLenum(GL_ONE_MINUS_SRC_ALPHA))
        glClearColor(0,0,0,0);glClear(GLbitfield(GL_COLOR_BUFFER_BIT))
        assert(blend.begin());quad();blend.end()
        var blended=[UInt8](repeating:0,count:4)
        glReadPixels(64,32,1,1,GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),&blended)
        assert(blended==[128,0,0,64], "lost host blending alpha table: \(blended)")
        assert(glIsEnabled(GLenum(GL_BLEND))==GLboolean(GL_TRUE))

        // The native loupe supplies scalar coordinates on unit 1 and its
        // existing alpha mask on unit 0. Its palette occupies a third unit.
        glDisable(GLenum(GL_BLEND))
        glActiveTexture(GLenum(GL_TEXTURE1));glBindTexture(GLenum(GL_TEXTURE_RECTANGLE_EXT),input)
        glPixelStorei(GLenum(GL_UNPACK_ROW_LENGTH),0)
        glTexImage2D(GLenum(GL_TEXTURE_RECTANGLE_EXT),0,GL_LUMINANCE32F_ARB,2,1,0,
                     GLenum(GL_LUMINANCE),GLenum(GL_FLOAT),[Float(64)/255,Float(192)/255])
        var mask:GLuint=0
        glActiveTexture(GLenum(GL_TEXTURE0));glGenTextures(1,&mask)
        glBindTexture(GLenum(GL_TEXTURE_RECTANGLE_EXT),mask)
        glTexImage2D(GLenum(GL_TEXTURE_RECTANGLE_EXT),0,GL_RGBA8,1,1,0,
                     GLenum(GL_RGBA),GLenum(GL_UNSIGNED_BYTE),[UInt8(0),0,0,128])
        glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT),GLenum(GL_TEXTURE_MIN_FILTER),GL_NEAREST)
        glTexParameteri(GLenum(GL_TEXTURE_RECTANGLE_EXT),GLenum(GL_TEXTURE_MAG_FILTER),GL_NEAREST)
        let loupe=state.prepare(table:steps,level:0.5,width:1,nearest:false,context:context)!
        assert(loupe.beginForLens())
        glBegin(GLenum(GL_QUADS))
        glMultiTexCoord2f(GLenum(GL_TEXTURE0),0,0);glMultiTexCoord2f(GLenum(GL_TEXTURE1),2,0);glVertex2f(-1,1)
        glMultiTexCoord2f(GLenum(GL_TEXTURE0),1,0);glMultiTexCoord2f(GLenum(GL_TEXTURE1),0,0);glVertex2f(1,1)
        glMultiTexCoord2f(GLenum(GL_TEXTURE0),1,1);glMultiTexCoord2f(GLenum(GL_TEXTURE1),0,1);glVertex2f(1,-1)
        glMultiTexCoord2f(GLenum(GL_TEXTURE0),0,1);glMultiTexCoord2f(GLenum(GL_TEXTURE1),2,1);glVertex2f(-1,-1)
        glEnd();loupe.end()
        var lens=[UInt8](repeating:0,count:outW*outH*4)
        glReadPixels(0,0,GLsizei(outW),GLsizei(outH),GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),&lens)
        for y in 0..<outH { for x in 0..<outW {
            let expected:[UInt8]=x<64 ? [0,0,255,128] : [255,0,0,128]
            assert(Array(lens[(y*outW+x)*4..<(y*outW+x)*4+4])==expected, "loupe order/mask/coordinates")
        }}
        glDeleteTextures(1,&mask)
        assert(glGetError()==GLenum(GL_NO_ERROR))
        assert(source.withUnsafeBytes { Data($0) }==original)
        assert(state.prepare(table:Data(),level:0,width:1,nearest:false,context:context)==nil)
        glDeleteTextures(1,&input);glDeleteTextures(1,&target);glDeleteFramebuffersEXT(1,&fbo)
        print("PASS: \(checked) pixels in each backend (\(boundaryPixels) float32 boundary cases); scalar-first GL/Metal, software 1x/2x/3x, transforms, state, immutable source; windowed bytes, blending alpha and 8192 masked loupe pixels")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-scalar-clut-') as directory:
    work = Path(directory)
    (work/'Host.c').write_text(control)
    (work/'Host.h').write_text('long hostScale(float *,float *,int,int,int);\n')
    (work/'Check.swift').write_text(driver)
    subprocess.run(['xcrun','clang','-O0','-c',str(work/'Host.c'),'-o',str(work/'Host.o')],check=True)
    subprocess.run(['xcrun','swiftc','-Onone','-parse-as-library','-suppress-warnings',
                    str(root/'Horos/Sources/VolumeAllocation.swift'),str(root/'Horos/Sources/PlanarMetalRenderer.swift'),
                    str(args.legacy_source),str(work/'Host.o'),'-import-objc-header',str(work/'Host.h'),
                    str(work/'Check.swift'),'-o',str(work/'check')],check=True)
    raise SystemExit(subprocess.run([str(work/'check')],timeout=40).returncode)
