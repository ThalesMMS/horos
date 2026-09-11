#!/usr/bin/env python3
"""Write a Word mail-merge template for the report validation of #157.

`-[Reports createNewWordReportForStudy:toDestinationPath:]` hands Word a
template and a tab separated data source whose column names are the Study
entity's attributes, then runs the merge and saves the result. To exercise that
path the template has to be a real .docx with MERGEFIELD codes, and to cover
the case it has to carry the things the report is expected to preserve:
Portuguese and Russian characters, the same field used more than once, and an
image.

    python3 tools/generate-word-merge-template.py 'out/R157 Merge Template.docx'

No patient data is involved: the image is generated here and the text is fixed.
"""
import argparse
import struct
import zlib
from pathlib import Path

# Fields are Study entity attributes; `name` appears twice on purpose.
FIELDS = ['name', 'patientID', 'studyName', 'accessionNumber', 'modality', 'name']
TITLE = 'Relatório de validação — R157'
# Portuguese and Russian, plus a character outside Latin-1 either way.
PARAGRAPHS = [
    'Paciente: acentuação, ção, à, ê, õ, ü — coração.',
    'Пациент: проверка кириллицы — исследование.',
]


def png(width, height):
    """A small deterministic PNG, so the template carries a real image part."""
    rows = b''
    for y in range(height):
        rows += b'\x00' + bytes(
            v for x in range(width)
            for v in (x * 255 // max(1, width - 1), y * 255 // max(1, height - 1), 128))

    def chunk(tag, payload):
        return (struct.pack('>I', len(payload)) + tag + payload
                + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))

    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def mergeField(name):
    """A complete field: begin, instruction, separator, placeholder, end."""
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> MERGEFIELD %s </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>«%s»</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>' % (name, name))


def paragraph(runs):
    return '<w:p>' + runs + '</w:p>'


def text(value):
    return '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % value


def document(width, height):
    body = [paragraph(text(TITLE))]
    for line in PARAGRAPHS:
        body.append(paragraph(text(line)))
    for name in FIELDS:
        body.append(paragraph(text('%s: ' % name) + mergeField(name)))
    # 96 dpi to EMU: one pixel is 9525 EMU.
    drawing = (
        '<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
        '<wp:extent cx="%d" cy="%d"/><wp:docPr id="1" name="R157 image"/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:nvPicPr><pic:cNvPr id="1" name="R157 image"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
        % (width * 9525, height * 9525, width * 9525, height * 9525))
    body.append(paragraph(drawing))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<w:body>' + ''.join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
            '</w:body></w:document>')


CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="png" ContentType="image/png"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>')
ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '</Relationships>')
DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>'
    '</Relationships>')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('destination', help='.docx to write')
    parser.add_argument('--image-width', type=int, default=120)
    parser.add_argument('--image-height', type=int, default=80)
    arguments = parser.parse_args()

    import zipfile
    destination = Path(arguments.destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as package:
        package.writestr('[Content_Types].xml', CONTENT_TYPES)
        package.writestr('_rels/.rels', ROOT_RELS)
        package.writestr('word/_rels/document.xml.rels', DOCUMENT_RELS)
        package.writestr('word/document.xml',
                         document(arguments.image_width, arguments.image_height))
        package.writestr('word/media/image1.png', png(arguments.image_width, arguments.image_height))
    print('%s  %d bytes, %d merge fields (%d distinct), image %dx%d'
          % (destination, destination.stat().st_size, len(FIELDS), len(set(FIELDS)),
             arguments.image_width, arguments.image_height))


if __name__ == '__main__':
    main()
