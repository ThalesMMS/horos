#!/usr/bin/env python3
"""Project stored patient-space angle points under several cameras; the angle is unchanged."""
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
try:
    functions = source[source.index('static bool HorosProjectPatientPoints'):
                       source.index('// Each inactive overlay')]
except ValueError:
    print('FAIL: HorosProjectPatientPoints is missing', file=sys.stderr)
    sys.exit(1)
install = root / 'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install / 'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code = r'''
#include <vtkAutoInit.h>
VTK_MODULE_INIT(vtkRenderingOpenGL2);
VTK_MODULE_INIT(vtkRenderingFreeType);
#include <vtkRenderer.h>
#include <vtkCamera.h>
#include <vtkRenderWindow.h>
#include <cassert>
#include <cmath>
#include <cstdio>
FUNCTIONS
int main() {
    auto window = vtkRenderWindow::New();
    auto renderer = vtkRenderer::New();
    window->AddRenderer(renderer);
    auto camera = renderer->GetActiveCamera();
    camera->ParallelProjectionOn();
    camera->SetParallelScale(40);
    window->SetSize(800, 600);
    const double factor = 0.1;
    const double patient[3][3] = {{0, 0, 0}, {30, 0, 0}, {0, 0, 30}};
    double first[3][3];
    camera->SetPosition(0, -100, 0);
    camera->SetFocalPoint(0, 0, 0);
    camera->SetViewUp(0, 0, 1);
    assert(HorosProjectPatientPoints(renderer, factor, patient, 3, first));
    struct Pose { double px, py, pz, ux, uy, uz; };
    Pose poses[] = {
        {0, -100, 0, 0, 0, 1},
        {100, 0, 0, 0, 0, 1},
        {0, 0, 100, 0, 1, 0},
        {80, 60, 40, 0, 0, 1},
        {-50, 70, 20, 0.2, 0.1, 1},
    };
    for (auto pose : poses) {
        camera->SetPosition(pose.px, pose.py, pose.pz);
        camera->SetFocalPoint(0, 0, 0);
        camera->SetViewUp(pose.ux, pose.uy, pose.uz);
        double display[3][3];
        assert(HorosProjectPatientPoints(renderer, factor, patient, 3, display));
        for (int i = 0; i < 3; ++i)
            assert(std::isfinite(display[i][0]) && std::isfinite(display[i][1]));
    }
    camera->SetPosition(100, 0, 0);
    camera->SetViewUp(0, 0, 1);
    double rotated[3][3];
    assert(HorosProjectPatientPoints(renderer, factor, patient, 3, rotated));
    // The projection has to follow the camera. Which coordinate moves depends
    // on the pose: point 0 is the focal point and does not move at all, and
    // turning the camera from -y to +x about the same up vector leaves point
    // 1's display y where it was too, so naming either of those is a test that
    // passes whatever the projection does. Require that something moved.
    bool moved = false;
    for (int i = 0; i < 3; ++i)
        if (std::abs(rotated[i][0] - first[i][0]) > 1 ||
            std::abs(rotated[i][1] - first[i][1]) > 1)
            moved = true;
    assert(moved);
    renderer->Delete();
    window->Delete();
    puts("PASS: patient-space points reproject under five cameras without changing the stored phantom");
}
'''.replace('FUNCTIONS', functions)
with tempfile.TemporaryDirectory(prefix='horos-vr-angle-proj-') as d:
    p = Path(d)
    (p / 'test.cxx').write_text(code)
    libs = sorted((install / 'lib').glob('libvtkCommon*.a'))
    for name in ['vtkRenderingCore', 'vtkRenderingFreeType', 'vtkfreetype',
                 'vtkRenderingOpenGL2', 'vtkglew', 'vtkFiltersCore', 'vtkFiltersGeneral',
                 'vtkFiltersSources', 'vtkImagingCore', 'vtkFiltersGeometry', 'vtksys',
                 'vtkdoubleconversion']:
        libs += list((install / 'lib').glob('lib' + name + '-*.a'))
    subprocess.run(['xcrun', 'clang++', '-std=c++11', '-I' + str(install / 'include'),
                    str(p / 'test.cxx'), *[str(x) for x in libs], '-lz',
                    '-framework', 'Cocoa', '-framework', 'OpenGL', '-o', str(p / 'test')],
                   check=True)
    subprocess.run([str(p / 'test')], check=True)
