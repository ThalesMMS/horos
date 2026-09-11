#!/usr/bin/env python3
"""Actual Metal -> IOSurface -> legacy GL composition, without launching a UI.

Read back the destination FBO, not the intermediate Metal texture. Tolerance
is zero for this transfer: the independently tested shader has already applied
interpolation/window/CLUT. Also exercise state restoration, cache, resize,
content replacement, session invalidation and a host overlay after the quad.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host-source', type=Path, default=root/'Horos/Sources/PlanarHostRenderer.swift')
args = parser.parse_args()
driver = r'''
import AppKit
import Metal
import OpenGL.GL

@main @MainActor struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { exit(2) }
        let attributes: [NSOpenGLPixelFormatAttribute] = [
            UInt32(NSOpenGLPFAAccelerated), UInt32(NSOpenGLPFAColorSize), 24,
            UInt32(NSOpenGLPFAAllowOfflineRenderers), 0]
        guard let format = NSOpenGLPixelFormat(attributes: attributes),
              let context = NSOpenGLContext(format: format, share: nil) else { exit(2) }
        context.makeCurrentContext()
        let registry = VolumeSessionRegistry.shared
        let id = VolumeIdentity(studyInstanceUID:"synthetic", seriesInstanceUID:"interop")!
        var session = registry.open(identity:id, owner:"host")!
        let host = PlanarHostRenderer()
        let control = try PlanarMetalRenderer(device:device)
        let clut = Data((0..<256).flatMap { i -> [UInt8] in
            i < 128 ? [0,0,255,255] : [255,255,0,255]
        })
        let source = (0..<40).map { Float(($0*31)%256) }
        let pixels = source.withUnsafeBytes { Data($0) }
        var argbBytes = [UInt8]()
        for i: Int in 0..<40 {
            argbBytes.append(255); argbBytes.append(UInt8((i*17)%256))
            argbBytes.append(UInt8((i*29)%256)); argbBytes.append(UInt8((i*41)%256))
        }
        let argb = Data(argbBytes)
        let payload: NSMutableDictionary = [
            "width":8, "height":5, "pixels":pixels, "clut":clut,
            "frameIdentity":"frame/0", "level":128, "widthWindow":256,
            "viewSize":[8,5], "screenToPixel":[0,0,8,0,0,5], "nearest":false]
        var checked = 0
        for size in [(8,5),(512,320),(40,66),(8,5)] {
            let (w,h) = size
            var framebuffer:GLuint=0, attachment:GLuint=0
            glGenFramebuffersEXT(1,&framebuffer)
            glBindFramebufferEXT(GLenum(GL_FRAMEBUFFER_EXT),framebuffer)
            glGenTextures(1,&attachment); glBindTexture(GLenum(GL_TEXTURE_2D),attachment)
            glTexImage2D(GLenum(GL_TEXTURE_2D),0,GL_RGBA8,GLsizei(w),GLsizei(h),0,
                         GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),nil)
            glFramebufferTexture2DEXT(GLenum(GL_FRAMEBUFFER_EXT),GLenum(GL_COLOR_ATTACHMENT0_EXT),
                                      GLenum(GL_TEXTURE_2D),attachment,0)
            assert(glCheckFramebufferStatusEXT(GLenum(GL_FRAMEBUFFER_EXT)) == GLenum(GL_FRAMEBUFFER_COMPLETE_EXT))
            for color in [false,true] { for nearest in [false,true] { for transform in 0..<4 {
                payload["isColor"]=color; payload["nearest"]=nearest
                payload["pixels"] = color ? argb : pixels
                payload["screenToPixel"] = [[0.0,0,8,0,0,5], [8.0,0,0,0,8,5],
                                             [0.0,5,8,5,0,0], [1.0,0.3,5,1.3,0,3.3]][transform]
                // Deliberately non-default host state, including a second unit.
                glActiveTexture(GLenum(GL_TEXTURE1))
                glEnable(GLenum(GL_BLEND)); glEnable(GLenum(GL_SCISSOR_TEST))
                glScissor(2,3,1,1); glViewport(3,4,5,6)
                glMatrixMode(GLenum(GL_MODELVIEW)); glLoadIdentity(); glTranslatef(7,8,0)
                glMatrixMode(GLenum(GL_PROJECTION)); glLoadIdentity(); glScalef(0.3,0.7,1)
                assert(host.draw(snapshot:payload,session:session,context:context,width:w,height:h), host.failureReason ?? "failed")
                var viewport=[GLint](repeating:0,count:4), active:GLint=0, mode:GLint=0
                glGetIntegerv(GLenum(GL_VIEWPORT),&viewport); glGetIntegerv(GLenum(GL_ACTIVE_TEXTURE),&active)
                glGetIntegerv(GLenum(GL_MATRIX_MODE),&mode)
                assert(viewport==[3,4,5,6] && active==GL_TEXTURE1 && mode==GL_PROJECTION)
                var model=[GLfloat](repeating:0,count:16), projection=model
                glGetFloatv(GLenum(GL_MODELVIEW_MATRIX),&model)
                glGetFloatv(GLenum(GL_PROJECTION_MATRIX),&projection)
                assert(model[12]==7 && model[13]==8 && model[0]==1 && model[5]==1)
                assert(abs(projection[0]-0.3)<0.000001 && abs(projection[5]-0.7)<0.000001)
                assert(glIsEnabled(GLenum(GL_BLEND))==GLboolean(GL_TRUE))
                assert(glIsEnabled(GLenum(GL_SCISSOR_TEST))==GLboolean(GL_TRUE))
                let renders=host.renderedFrameCount
                assert(host.draw(snapshot:payload,session:session,context:context,width:w,height:h))
                assert(host.renderedFrameCount==renders, "overlay-only draw rerendered Metal")
                assert(!host.encodedGPUCommand, "cached draw must not report the previous GPU timing as a new command")
                try control.update(PlanarFrame(payload))
                let reference=[UInt8](try control.renderBGRA(width:w,height:h))
                glPixelStorei(GLenum(GL_PACK_ALIGNMENT),1)
                var actual=[UInt8](repeating:0,count:w*h*4)
                glReadPixels(0,0,GLsizei(w),GLsizei(h),GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),&actual)
                // GL readback begins at bottom left; Metal data begins at top.
                for y in 0..<h {
                    assert(Array(actual[y*w*4..<(y+1)*w*4]) == Array(reference[(h-1-y)*w*4..<(h-y)*w*4]),
                           "interop changed pixels size=\(size) color=\(color) nearest=\(nearest) transform=\(transform) row=\(y)")
                }
                assert(glGetError()==GLenum(GL_NO_ERROR))
                checked += w*h
            }}}
            // A host overlay still renders after the Metal quad.
            glDisable(GLenum(GL_SCISSOR_TEST)); glDisable(GLenum(GL_BLEND))
            glActiveTexture(GLenum(GL_TEXTURE0)); glDisable(GLenum(GL_TEXTURE_RECTANGLE_EXT))
            glDisable(GLenum(GL_TEXTURE_2D)); glViewport(0,0,GLsizei(w),GLsizei(h))
            glMatrixMode(GLenum(GL_PROJECTION)); glLoadIdentity()
            glMatrixMode(GLenum(GL_MODELVIEW)); glLoadIdentity()
            glColor4f(1,0,0,1); glRectf(-1,-1,0,0)
            var overlay=[UInt8](repeating:0,count:4)
            glReadPixels(0,0,1,1,GLenum(GL_BGRA),GLenum(GL_UNSIGNED_BYTE),&overlay)
            assert(overlay==[0,0,255,255])
            glDeleteFramebuffersEXT(1,&framebuffer); glDeleteTextures(1,&attachment)
        }
        registry.invalidateVolume(session.identity)
        assert(!host.draw(snapshot:payload,session:session,context:context,width:8,height:5))
        let next = session.identity
        registry.close(session)
        session = registry.open(identity:next,owner:"host")!
        host.invalidate(); registry.close(session)
        assert(!host.draw(snapshot:payload,session:session,context:context,width:8,height:5))
        assert(registry.openSessionCount==0 && source.withUnsafeBytes { Data($0) }==pixels)
        print("PASS: \(checked) final GL pixels exact, Metal interop transforms/state/cache/resize/overlay/teardown")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-planar-host-') as temporary:
    work = Path(temporary)
    (work/'Check.swift').write_text(driver)
    # PlanarMetal4Renderer is the backend the host may be asked for (#609);
    # it compiles here so the selection and its fallback are exercised, not stubbed.
    sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'PlanarMetalRenderer.swift',
               'PlanarMetal4Renderer.swift']
    command = ['xcrun', 'swiftc', '-Onone', '-parse-as-library', '-suppress-warnings',
               *[str(root/'Horos/Sources'/name) for name in sources], str(args.host_source), str(work/'Check.swift'), '-o', str(work/'check')]
    subprocess.run(command, check=True)
    result = subprocess.run([str(work/'check')], timeout=45)
    raise SystemExit(result.returncode)
