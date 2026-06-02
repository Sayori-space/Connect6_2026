"""
ShaderBackground：使用 OpenGL 3.3 的动态星空/星云背景。

将 shader/stars.gdshader（Godot 4 canvas_item shader）翻译为 GLSL 3.30。
依赖：PyOpenGL（pip install PyOpenGL）。
如果 PyOpenGL 不可用，则回退到普通深色背景。
"""

from __future__ import annotations

import struct
import time
from typing import Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QOpenGLShader, QOpenGLShaderProgram, QSurfaceFormat
from PyQt5.QtWidgets import QOpenGLWidget, QWidget

try:
    from OpenGL import GL as gl  # type: ignore[import-untyped]
    _HAS_GL = True
except ImportError:
    _HAS_GL = False
    import sys
    print(
        f"[ShaderBackground] PyOpenGL not found in {sys.executable}\n"
        f"  Fix: pip install PyOpenGL  (in the same environment VSCode uses)\n"
        f"  Falling back to plain dark background.",
        flush=True,
    )


# ── GLSL 源码 ─────────────────────────────────────────────────────────

_VERT = """\
#version 330 core
layout(location = 0) in vec2 a_pos;
void main() {
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
"""

_FRAG = """\
#version 330 core
uniform float u_time;
uniform vec2  u_resolution;
out vec4 frag_color;

const float density              = 150.0;
const int   layer_parascale      = 2;
const float speedx               = 0.2;
const float speedy               = 0.0;
const float star_horizontal_wave = 0.3;
const float star_size            = 3.0;
const float twinkle_effect       = 0.6;
const float twinkle_speed        = 0.3;

const float fbm_strength = 0.12;
const float fbm_mix      = 0.07;
const float fbm_freq     = 4.0;
const float fbm_amp      = 1.5;
const float fbm_speed    = 5.0;
const float warp_scale   = 2.0;

const float cloud_freq      = 40.0;
const float cloud_amp       = 0.02;
const float cloud_speed     = 5.0;
const float cloud_color_ci1 = 0.75;
const float cloud_color_ci2 = 0.45;
const float cloud_color_ci3 = 0.90;

const vec3  background_color = vec3(0.0, 0.0, 0.0);
const float PI               = 3.14159265358979323846;

float onedx(float x)  { return (x == 0.0) ? 1.0 : 1.0 / x; }
float onedx2(float x) { float v = onedx(x); return v * v; }

float getI(vec2 uv, float f, vec2 SIZE) {
    return onedx2(SIZE.x * uv.x * PI / f) * onedx2(SIZE.y * uv.y * PI / f);
}

float random(vec2 st) {
    return fract(sin(dot(st, vec2(12.9898, 78.233))) * 43759.5453123);
}

float noise(vec2 st) {
    vec2 i = floor(st), f = fract(st);
    float a = random(i), b = random(i + vec2(1,0)),
          c = random(i + vec2(0,1)), d = random(i + vec2(1,1));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(a,b,u.x) + (c-a)*u.y*(1.0-u.x) + (d-b)*u.x*u.y;
}

float fbm(vec2 st) {
    float value = 0.0, freq = fbm_freq;
    for (int i = 0; i < 5; i++) { value += fbm_amp * noise(st * freq); freq *= 2.7; }
    return value;
}

vec2 clouduv(vec2 uv, float t) {
    vec2 flowDir = vec2(0.20, -0.07);
    vec2 p = uv * warp_scale - t * vec2(speedx, speedy) * fbm_speed;
    vec2 warp = vec2(fbm(p + vec2(5.2, 1.3) + t*flowDir*1.2),
                     fbm(p + vec2(-2.8, 3.1) - t*flowDir*0.9));
    uv += (warp - 0.5) * fbm_strength;
    vec2 centers[3];
    centers[0] = vec2(-0.3, 0.4); centers[1] = vec2(0.7,-0.5); centers[2] = vec2(-0.5, 0.7);
    for (int i = 0; i < 3; i++) {
        vec2 toC = uv - centers[i]; float r = length(toC) + 1e-6;
        uv += normalize(toC) * sin(r*cloud_freq - t*cloud_speed) * cloud_amp;
    }
    return uv;
}

vec2 rot2d(vec2 v, float a) { float c=cos(a),s=sin(a); return vec2(v.x*c-v.y*s, v.x*s+v.y*c); }

void main() {
    float aspect = u_resolution.x / u_resolution.y;
    vec2 uv  = vec2(gl_FragCoord.x / u_resolution.x, 1.0 - gl_FragCoord.y / u_resolution.y);
    vec2 st  = vec2(uv.x * aspect, uv.y);
    vec2 cuv = (st - 0.5) * 2.0;
    vec3 color = background_color;

    for (int layer = 0; layer < 4; layer++) {
        float lf = float(layer);
        float layerScale = exp(float(layer * layer_parascale + 1) * density * 0.002);
        vec2  timeOff    = u_time * vec2(speedx, speedy) * (1.0 + lf * 0.3);
        vec2  layerSt    = st * layerScale - timeOff;
        vec2  gridSt = fract(layerSt), gridId = floor(layerSt);
        float rs = random(gridId);
        vec2 snowPos = vec2(0.5 + 0.3*sin(rs*6.28318 + u_time*star_horizontal_wave),
                            0.5 + 0.2*cos(rs*12.56637));
        float dist     = distance(gridSt, snowPos);
        float snowSize = star_size * (1.0 - lf*0.2) * 0.01 * (0.5 + 0.5*rs);
        float M        = exp(-dist*dist / (snowSize*snowSize));
        vec2 wc  = (gridId + snowPos + timeOff) / layerScale;
        vec2 fst = rot2d(cuv - (wc - 0.5)*2.0, 0.01*u_time*cos(rs*120.0 + u_time*0.05));
        float sf = M * 0.5 * (getI(fst, 0.8 - dist*42.0, vec2(1.0/snowSize)) + 1.0);
        sf *= (1.0-twinkle_effect) + twinkle_effect
              * sin(rs*100.0 + u_time*twinkle_speed) * cos(rs*120.0 + u_time*(twinkle_speed+2.0));
        color = max(color + sf*(1.0-lf*0.3)*vec3(random(gridId-3.0),random(gridId+7.0),random(gridId+5.0)), color);
    }

    vec2 fuv = clouduv(cuv, u_time);
    vec3 cloud = vec3(fuv.x*(1.0-cloud_color_ci1)+fuv.y*cloud_color_ci2,
                      fuv.x*(1.0-cloud_color_ci3)+fuv.y*cloud_color_ci2,
                      fuv.x*(1.0-cloud_color_ci3)+fuv.y*cloud_color_ci1);
    frag_color = vec4(mix(color, cloud, fbm_mix), 1.0);
}
"""


# ── 控件 ─────────────────────────────────────────────────────────────

class ShaderBackground(QOpenGLWidget):
    """
    通过 OpenGL 3.3 + PyOpenGL 实现的动态星空/星云背景。
    可直接替换静态 StarBackground。
    """

    def __init__(self, count: int = 180, parent: Optional[QWidget] = None):
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        super().__init__(parent)
        self.setFormat(fmt)

        self._prog: Optional[QOpenGLShaderProgram] = None
        self._vao:  Optional[int] = None
        self._vbo:  Optional[int] = None
        self._loc_time: int = -1
        self._loc_res:  int = -1
        self._t0:  float = time.monotonic()
        self._ok:  bool  = False

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    # ── OpenGL 生命周期 ───────────────────────────────────────────────

    def initializeGL(self) -> None:
        if not _HAS_GL:
            print("[ShaderBackground] PyOpenGL not available")
            return
        try:
            self._prog = QOpenGLShaderProgram()
            if not self._prog.addShaderFromSourceCode(QOpenGLShader.Vertex, _VERT):
                raise RuntimeError(f"Vertex: {self._prog.log()}")
            if not self._prog.addShaderFromSourceCode(QOpenGLShader.Fragment, _FRAG):
                raise RuntimeError(f"Fragment: {self._prog.log()}")
            if not self._prog.link():
                raise RuntimeError(f"Link: {self._prog.log()}")

            pid = self._prog.programId()
            self._loc_time = gl.glGetUniformLocation(pid, "u_time")
            self._loc_res  = gl.glGetUniformLocation(pid, "u_resolution")

            verts = struct.pack("6f", -1.0, -1.0,  3.0, -1.0,  -1.0, 3.0)
            self._vao = gl.glGenVertexArrays(1)
            self._vbo = gl.glGenBuffers(1)
            gl.glBindVertexArray(self._vao)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vbo)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, verts, gl.GL_STATIC_DRAW)
            gl.glEnableVertexAttribArray(0)
            gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, gl.GL_FALSE, 8, None)
            gl.glBindVertexArray(0)

            self._ok = True
            print("[ShaderBackground] initialised OK")

        except Exception as exc:
            print(f"[ShaderBackground] initializeGL failed: {exc}")
            self._ok = False

    def resizeGL(self, w: int, h: int) -> None:
        if _HAS_GL:
            gl.glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        if not _HAS_GL:
            return
        gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        if not self._ok or self._prog is None:
            return
        self._prog.bind()
        gl.glUniform1f(self._loc_time, time.monotonic() - self._t0)
        gl.glUniform2f(self._loc_res, float(self.width()), float(self.height()))
        gl.glBindVertexArray(self._vao)
        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 3)
        gl.glBindVertexArray(0)
        self._prog.release()
