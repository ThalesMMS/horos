import AppKit
import OpenGL
import OpenGL.GL

/// Keeps the retained OpenGL viewer's scalar samples in float until its final
/// fragment. Geometry, texture tiling, blending and overlays remain in DCMView.
@MainActor private final class ScalarCLUTProgram: NSObject {
    private let context: CGLContextObj
    private var program: GLuint = 0
    private var tableTexture: GLuint = 0
    private var table: Data?
    private var previousProgram: GLint = 0
    private var active = false

    init?(context: NSOpenGLContext) {
        guard let cgl = context.cglContextObj else { return nil }
        self.context = cgl
        CGLRetainContext(cgl)
        super.init()
        let previous = CGLGetCurrentContext()
        CGLSetCurrentContext(cgl)
        defer { CGLSetCurrentContext(previous) }
        let vertex = """
        #version 120
        void main() {
            gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
            gl_TexCoord[0] = gl_MultiTexCoord0;
            gl_TexCoord[1] = gl_MultiTexCoord1;
        }
        """
        let fragment = """
        #version 120
        #extension GL_ARB_texture_rectangle : enable
        uniform sampler2DRect image;
        uniform sampler2D colors;
        uniform sampler2DRect lensMask;
        uniform bool masked;
        uniform float minimum;
        uniform float span;
        uniform bool nearest;
        void main() {
            vec2 point = masked ? gl_TexCoord[1].xy : gl_TexCoord[0].xy;
            float value;
            if (nearest) value = texture2DRect(image, floor(point)+0.5).r;
            else {
                // Sample exact texel centres and interpolate float values.
                // Fixed-function GL filtering may quantize subpixel weights,
                // moving an oblique sample across a discrete CLUT boundary.
                vec2 base = floor(point-0.5)+0.5;
                vec2 weight = fract(point-0.5);
                value = mix(mix(texture2DRect(image, base).r,
                                texture2DRect(image, base+vec2(1,0)).r, weight.x),
                            mix(texture2DRect(image, base+vec2(0,1)).r,
                                texture2DRect(image, base+vec2(1,1)).r, weight.x), weight.y);
            }
            float index = floor(clamp((value-minimum)/span, 0.0, 1.0)*255.0+0.5);
            gl_FragColor = texture2D(colors, vec2((index+0.5)/256.0, 0.5));
            if (masked) gl_FragColor.a *= texture2DRect(lensMask, gl_TexCoord[0].xy).a;
        }
        """
        func compile(_ source: String, type: GLenum) -> GLuint {
            let shader = glCreateShader(type)
            source.withCString { bytes in
                var pointer: UnsafePointer<GLchar>? = bytes
                glShaderSource(shader, 1, &pointer, nil)
            }
            glCompileShader(shader)
            var status: GLint = 0
            glGetShaderiv(shader, GLenum(GL_COMPILE_STATUS), &status)
            if status == 0 { glDeleteShader(shader); return 0 }
            return shader
        }
        let vs = compile(vertex, type: GLenum(GL_VERTEX_SHADER))
        let fs = compile(fragment, type: GLenum(GL_FRAGMENT_SHADER))
        defer { if vs != 0 { glDeleteShader(vs) }; if fs != 0 { glDeleteShader(fs) } }
        guard vs != 0, fs != 0 else { return nil }
        program = glCreateProgram()
        glAttachShader(program, vs); glAttachShader(program, fs); glLinkProgram(program)
        var linked: GLint = 0
        glGetProgramiv(program, GLenum(GL_LINK_STATUS), &linked)
        guard linked != 0 else { return nil }
    }

    func begin(table: Data, level: Float, width: Float, nearest: Bool, masked: Bool = false) -> Bool {
        guard !active, CGLGetCurrentContext() == context, table.count == 1024,
              level.isFinite, width.isFinite, width != 0 else { return false }
        glGetIntegerv(GLenum(GL_CURRENT_PROGRAM), &previousProgram)
        glPushAttrib(GLbitfield(GL_TEXTURE_BIT | GL_PIXEL_MODE_BIT))
        glPushClientAttrib(GLbitfield(GL_CLIENT_PIXEL_STORE_BIT))
        glActiveTexture(GLenum(masked ? GL_TEXTURE2 : GL_TEXTURE1))
        if tableTexture == 0 { glGenTextures(1, &tableTexture) }
        glBindTexture(GLenum(GL_TEXTURE_2D), tableTexture)
        if self.table != table {
            glPixelStorei(GLenum(GL_UNPACK_ROW_LENGTH), 0)
            glPixelStorei(GLenum(GL_UNPACK_SKIP_ROWS), 0)
            glPixelStorei(GLenum(GL_UNPACK_SKIP_PIXELS), 0)
            glPixelStorei(GLenum(GL_UNPACK_ALIGNMENT), 1)
            glPixelStorei(GLenum(GL_UNPACK_CLIENT_STORAGE_APPLE), 0)
            for channel in [GL_RED_SCALE, GL_GREEN_SCALE, GL_BLUE_SCALE, GL_ALPHA_SCALE] {
                glPixelTransferf(GLenum(channel), 1)
            }
            for channel in [GL_RED_BIAS, GL_GREEN_BIAS, GL_BLUE_BIAS, GL_ALPHA_BIAS] {
                glPixelTransferf(GLenum(channel), 0)
            }
            table.withUnsafeBytes { bytes in
                glTexImage2D(GLenum(GL_TEXTURE_2D), 0, GL_RGBA8, 256, 1, 0,
                             GLenum(GL_RGBA), GLenum(GL_UNSIGNED_BYTE), bytes.baseAddress)
            }
            glTexParameteri(GLenum(GL_TEXTURE_2D), GLenum(GL_TEXTURE_MIN_FILTER), GL_NEAREST)
            glTexParameteri(GLenum(GL_TEXTURE_2D), GLenum(GL_TEXTURE_MAG_FILTER), GL_NEAREST)
            glTexParameteri(GLenum(GL_TEXTURE_2D), GLenum(GL_TEXTURE_WRAP_S), GL_CLAMP_TO_EDGE)
            glTexParameteri(GLenum(GL_TEXTURE_2D), GLenum(GL_TEXTURE_WRAP_T), GL_CLAMP_TO_EDGE)
            self.table = table
        }
        glUseProgram(program)
        glUniform1i(glGetUniformLocation(program, "image"), masked ? 1 : 0)
        glUniform1i(glGetUniformLocation(program, "colors"), masked ? 2 : 1)
        // Keep different sampler types on separate units even when the mask
        // branch is inactive; GL validates all active sampler uniforms.
        glUniform1i(glGetUniformLocation(program, "lensMask"), 0)
        glUniform1i(glGetUniformLocation(program, "masked"), masked ? 1 : 0)
        glUniform1f(glGetUniformLocation(program, "minimum"), level-width/2)
        glUniform1f(glGetUniformLocation(program, "span"), width)
        glUniform1i(glGetUniformLocation(program, "nearest"), nearest ? 1 : 0)
        glActiveTexture(GLenum(GL_TEXTURE0))
        active = true
        return true
    }

    func end() {
        guard active else { return }
        glUseProgram(GLuint(previousProgram)); glPopClientAttrib(); glPopAttrib()
        active = false
    }

    deinit {
        let previous = CGLGetCurrentContext()
        CGLSetCurrentContext(context)
        if tableTexture != 0 { glDeleteTextures(1, &tableTexture) }
        if program != 0 { glDeleteProgram(program) }
        CGLSetCurrentContext(previous)
        CGLReleaseContext(context)
    }
}

@MainActor @objc(HorosScalarCLUTDraw)
public final class ScalarCLUTDraw: NSObject {
    private let program: ScalarCLUTProgram
    private let table: Data
    private let level: Float, width: Float
    private let nearest: Bool
    fileprivate init(program: ScalarCLUTProgram, table: Data, level: Float, width: Float, nearest: Bool) {
        self.program = program; self.table = table; self.level = level; self.width = width
        self.nearest = nearest
    }
    @objc public func begin() -> Bool { program.begin(table: table, level: level, width: width, nearest: nearest) }
    @objc public func beginForLens() -> Bool {
        program.begin(table: table, level: level, width: width, nearest: nearest, masked: true)
    }
    @objc public func end() { program.end() }
}

/// One state per host view. Array identities follow the existing malloc/free
/// texture lifetime; weak context keys avoid accumulating export contexts.
@MainActor @objc(HorosLegacyScalarCLUTState)
public final class LegacyScalarCLUTState: NSObject {
    private let programs = NSMapTable<NSOpenGLContext, ScalarCLUTProgram>.weakToStrongObjects()
    private var draws: [UInt: ScalarCLUTDraw] = [:]
    @objc public var lensIsScalar = false
    @objc public var lensIsWindowed = false
    @objc public private(set) var failureReason: String?
    @objc public func resetFailure() { failureReason = nil }
    @objc public func markUnavailable() {
        failureReason = NSLocalizedString("Color mapping unavailable. Try Metal in Viewer.", comment: "")
    }

    @objc(prepareTable:level:width:nearest:context:)
    public func prepare(table: Data, level: Float, width: Float, nearest: Bool, context: NSOpenGLContext) -> ScalarCLUTDraw? {
        resetFailure()
        guard table.count == 1024, level.isFinite, width.isFinite, width != 0,
              (level-width/2).isFinite else { markUnavailable(); return nil }
        var program = programs.object(forKey: context)
        if program == nil {
            program = ScalarCLUTProgram(context: context)
            if let program { programs.setObject(program, forKey: context) }
        }
        guard let program else { markUnavailable(); return nil }
        return ScalarCLUTDraw(program: program, table: table, level: level, width: width, nearest: nearest)
    }

    @objc(setDraw:forArray:)
    public func setDraw(_ draw: ScalarCLUTDraw?, forArray array: UInt) { draws[array] = draw }
    @objc(drawForArray:)
    public func draw(forArray array: UInt) -> ScalarCLUTDraw? { draws[array] }
}
