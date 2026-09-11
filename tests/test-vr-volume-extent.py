#!/usr/bin/env python3
"""Check production VR import extents against real VTK and boundary-marked buffers."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/VRView.mm'
source = (subprocess.check_output(['git', 'show', sys.argv[1]+':'+path])
          if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
expressions = re.findall(r'(?:reader|blendingReader)->SetWholeExtent\(([^;]+)\);', source)
assert len(expressions) == 3
for old, new in [('[firstObject pwidth]', 'width'), ('[firstObject pheight]', 'height'),
                 ('[blendingFirstObject pwidth]', 'width'), ('[blendingFirstObject pheight]', 'height'),
                 ('[pixList count]', 'depth'), ('[blendingPixList count]', 'depth')]:
    expressions = [s.replace(old, new) for s in expressions]
install = root/'build/Build/Intermediates.noindex/Horos.build/Release/VTK.build/Install'
if not (install/'lib').is_dir():
    print('needs built VTK libraries in', install, file=sys.stderr)
    sys.exit(2)
code = r'''
#include <vtkImageImport.h>
#include <vtkImageData.h>
#include <vector>
#include <cmath>
#include <cstdio>
int main() {
 int count=0;
 for(int variant=0;variant<3;variant++)for(int depth: {16,3,2,1})for(double spacing: {1.,2.5}) {
  const int width=4,height=3;
  for(int components: {1,4}) {
   std::vector<unsigned short> scalar(width*height*depth);
   std::vector<unsigned char> rgb(width*height*depth*4);
   for(int z=0;z<depth;z++)for(int y=0;y<height;y++)for(int x=0;x<width;x++) {
    int offset=(z*height+y)*width+x;scalar[offset]=1000*z+10*y+x;
    for(int c=0;c<4;c++)rgb[4*offset+c]=10*z+c;
   }
   auto reader=vtkImageImport::New();
   if(components==1){reader->SetDataScalarTypeToUnsignedShort();reader->SetImportVoidPointer(scalar.data());}
   else {reader->SetDataScalarTypeToUnsignedChar();reader->SetImportVoidPointer(rgb.data());}
   reader->SetNumberOfScalarComponents(components);
   switch(variant) { CASES }
   reader->SetDataExtentToWholeExtent();reader->SetDataSpacing(.7,1.2,spacing);reader->Update();
   auto image=reader->GetOutput();int extent[6];image->GetExtent(extent);
   if(extent[4]!=0 || extent[5]!=depth-1) {
    std::fprintf(stderr,"FAIL: path %d depth %d imports Z [%d,%d], expected [0,%d]\n",variant,depth,extent[4],extent[5],depth-1);return 1;
   }
   double bounds[6];image->GetBounds(bounds);
   if(std::abs(bounds[4])>1e-12 || std::abs(bounds[5]-(depth-1)*spacing)>1e-12)return 2;
   for(int z=0;z<depth;z++)for(int y=0;y<height;y++)for(int x=0;x<width;x++)for(int c=0;c<components;c++) {
    double expected=components==1?1000*z+10*y+x:10*z+c;
    if(image->GetScalarComponentAsDouble(x,y,z,c)!=expected)return 3;
   }
   reader->Delete();count++;
  }
 }
 std::printf("PASS: %d VTK imports preserve all samples, boundary slices and physical Z bounds\n",count);
}
'''.replace('CASES', '\n'.join(f'case {i}: reader->SetWholeExtent({e}); break;' for i,e in enumerate(expressions)))
with tempfile.TemporaryDirectory(prefix='horos-vr-extent-') as d:
    p=Path(d); (p/'test.cxx').write_text(code)
    libs=sorted((install/'lib').glob('libvtkCommon*.a'))
    for name in ['vtkIOImage','vtkDICOMParser','vtkmetaio','vtkpng','vtkjpeg','vtktiff','vtkzlib','vtksys','vtkdoubleconversion']:
        libs += list((install/'lib').glob('lib'+name+'-*.a'))
    subprocess.run(['xcrun','clang++','-std=c++11','-fsanitize=address','-I'+str(install/'include'),str(p/'test.cxx'),*[str(x) for x in libs],'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
