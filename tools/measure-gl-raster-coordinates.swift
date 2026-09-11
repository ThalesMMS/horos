// Controlled GL varying-coordinate experiment. No application/database access.
import AppKit
import OpenGL.GL

let attributes: [NSOpenGLPixelFormatAttribute] = [UInt32(NSOpenGLPFAAccelerated),
    UInt32(NSOpenGLPFAColorSize), 24, 0]
guard let format = NSOpenGLPixelFormat(attributes: attributes),
      let context = NSOpenGLContext(format: format, share: nil) else { exit(2) }
context.makeCurrentContext()
func shader(_ text: String, _ type: GLenum) -> GLuint {
    let name = glCreateShader(type)
    text.withCString { p in
        var pointer: UnsafePointer<GLchar>? = p
        glShaderSource(name, 1, &pointer, nil)
    }
    glCompileShader(name)
    var valid: GLint = 0; glGetShaderiv(name, GLenum(GL_COMPILE_STATUS), &valid)
    precondition(valid != 0)
    return name
}
let vertex = shader("""
#version 120
void main() {
    gl_Position = gl_Vertex;
    gl_TexCoord[0] = gl_MultiTexCoord0;
}
""", GLenum(GL_VERTEX_SHADER))
let fragment = shader("""
#version 120
void main() { gl_FragColor = vec4(gl_TexCoord[0].xy, 0.0, 1.0); }
""", GLenum(GL_FRAGMENT_SHADER))
let program = glCreateProgram()
glAttachShader(program, vertex); glAttachShader(program, fragment); glLinkProgram(program)
var linked: GLint = 0; glGetProgramiv(program, GLenum(GL_LINK_STATUS), &linked)
precondition(linked != 0); glUseProgram(program)
let width = 1569, height = 807
var fbo: GLuint = 0, target: GLuint = 0
glGenFramebuffersEXT(1, &fbo); glBindFramebufferEXT(GLenum(GL_FRAMEBUFFER_EXT), fbo)
glGenTextures(1, &target); glBindTexture(GLenum(GL_TEXTURE_2D), target)
glTexImage2D(GLenum(GL_TEXTURE_2D), 0, GL_RGBA32F_ARB, GLsizei(width), GLsizei(height),
             0, GLenum(GL_RGBA), GLenum(GL_FLOAT), nil)
glFramebufferTexture2DEXT(GLenum(GL_FRAMEBUFFER_EXT), GLenum(GL_COLOR_ATTACHMENT0_EXT),
                         GLenum(GL_TEXTURE_2D), target, 0)
precondition(glCheckFramebufferStatusEXT(GLenum(GL_FRAMEBUFFER_EXT)) == GLenum(GL_FRAMEBUFFER_COMPLETE_EXT))
glViewport(0, 0, GLsizei(width), GLsizei(height))
glDisable(GLenum(GL_BLEND)); glDisable(GLenum(GL_DITHER)); glDisable(GLenum(GL_MULTISAMPLE))
var bits: GLint = 0; glGetIntegerv(GLenum(GL_SUBPIXEL_BITS), &bits)
let quantum = pow(2.0, -Double(bits))
var results = [[String: Any]]()
for scale in [1.0, 1.833984375, 2.791015625, 3.1513671875] {
    for offset in [(0.0, 0.0), (5.7, -5.3), (-33.25, 91.0625)] {
        let left = Double(width)/2 + offset.0 - 128*scale
        let bottom = Double(height)/2 + offset.1 - 128*scale
        // Capture exactly representable vertex inputs; independently invert
        // their projected bounds for the CPU reference.
        let x0 = Float(left*2/Double(width)-1), x1 = Float((left+256*scale)*2/Double(width)-1)
        let y0 = Float(bottom*2/Double(height)-1), y1 = Float((bottom+256*scale)*2/Double(height)-1)
        glClearColor(-1, -1, -1, -1); glClear(GLbitfield(GL_COLOR_BUFFER_BIT))
        glBegin(GLenum(GL_TRIANGLE_STRIP))
        glTexCoord2f(0, 0); glVertex2f(x0, y0)
        glTexCoord2f(256, 0); glVertex2f(x1, y0)
        glTexCoord2f(0, 256); glVertex2f(x0, y1)
        glTexCoord2f(256, 256); glVertex2f(x1, y1)
        glEnd()
        var pixels = [Float](repeating: 0, count: width*height*4)
        glReadPixels(0, 0, GLsizei(width), GLsizei(height), GLenum(GL_RGBA), GLenum(GL_FLOAT), &pixels)
        let l = (Double(x0)+1)*Double(width)/2, r = (Double(x1)+1)*Double(width)/2
        let b = (Double(y0)+1)*Double(height)/2, t = (Double(y1)+1)*Double(height)/2
        var maximum = 0.0, checked = 0, beyondFloat = 0
        for y in 0..<height { for x in 0..<width {
            let px = (Double(x)+0.5-l)/(r-l)*256, py = (Double(y)+0.5-b)/(t-b)*256
            guard px > 2 && px < 254 && py > 2 && py < 254 else { continue }
            let actualX = Double(pixels[(y*width+x)*4]), actualY = Double(pixels[(y*width+x)*4+1])
            let screenError = max(abs(actualX-px)*(r-l)/256, abs(actualY-py)*(t-b)/256)
            maximum = max(maximum, screenError); checked += 1
            if abs(actualX-px) > Double(Float(px).ulp)*8 || abs(actualY-py) > Double(Float(py).ulp)*8 { beyondFloat += 1 }
        }}
        precondition(glGetError() == 0)
        results.append(["scale":scale, "offset":[offset.0,offset.1], "checked":checked,
                        "maximumScreenError":maximum, "beyondEightFloatULPs":beyondFloat,
                        "withinReportedQuantum":maximum <= quantum])
    }
}
let output: [String: Any] = ["subpixelBits":bits, "screenQuantum":quantum, "cases":results]
let data = try JSONSerialization.data(withJSONObject: output, options: [.prettyPrinted, .sortedKeys])
print(String(decoding: data, as: UTF8.self))
precondition(results.allSatisfy { $0["withinReportedQuantum"] as! Bool })
