#!/usr/bin/env python3
"""A submitted frame belongs to its input ID, including coalesced round trips."""
import importlib.util
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scroll_trace', root/'tools/verify-native-planar-scroll.py')
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


def write_xml(path, rows):
    document = ET.Element('trace-query-result')
    schema = ET.SubElement(document, 'schema')
    for name in ['time','identifier','name','event-type','category','message']:
        column = ET.SubElement(schema, 'col')
        ET.SubElement(column, 'mnemonic').text = name
    for time, identifier, name, kind, fields in rows:
        row = ET.SubElement(document, 'row')
        for tag, value in [('event-time',time),('identifier',identifier),('name',name),
                           ('event-type',kind),('category','PlanarPerformance'),
                           ('metadata',' '.join(f'{k}={v}' for k,v in fields.items()))]:
            ET.SubElement(row,tag).text = str(value)
    ET.ElementTree(document).write(path)


def event(identifier, start, before, after):
    return [(start,identifier,'PlanarScroll','Begin',dict(view=1,**{'from':before},precise=1,inverted=0,age_ms=0.5)),
            (start+100_000,identifier,'PlanarScroll','End',dict(view=1,to=after))]


def draw(identifier, start, input_id, index, metal=0):
    return [(start,identifier,'PlanarDraw','Begin',dict(view=1,input=input_id,index=index)),
            (start+200_000,identifier,'PlanarPrepared','Event',dict(view=1,metal=metal,legacy_upload=1,gpu_ms=-1)),
            (start+400_000,identifier,'PlanarImageDrawn','Event',dict(view=1)),
            (start+800_000,identifier,'PlanarDraw','End',dict(view=1,index=index,cpu_s=0.2,footprint_bytes=1000000))]


with tempfile.TemporaryDirectory(prefix='horos-scroll-trace-') as folder:
    path = Path(folder)/'signposts.xml'
    # Deliberately larger than exact float64 integer precision. The log's
    # raw numeric identity must survive parsing without a rounding collision.
    first, second = 2**54+1, 2**54+2
    rows = event(first,0,0,1)+draw(31,200_000,first,1)+event(second,2_000_000,1,2)+draw(32,2_200_000,second,2)
    write_xml(path,rows)
    result = trace.verify(path,2,'gl')
    assert result['changed_with_own_draw'] == 2 and not result['coalesced']
    assert result['samples'][0]['input'] == first
    assert result['samples'][0]['event_to_flush_ms'] == 1.5
    assert result['summary']['gpu_ms'] is None
    paired = rows + event(20,4_000_000,2,3) + draw(33,4_200_000,20,3,metal=1)
    write_xml(path, paired)
    selected = trace.verify(path,3,'metal',(2,1))
    assert selected['scroll_events'] == 1 and selected['capture_scroll_events'] == 3
    assert selected['samples'][0]['input'] == 20
    for expected, selection in [(4,(2,1)), (3,(1,2)), (3,(3,1)), (3,(-1,1))]:
        try:
            trace.verify(path,expected,'metal',selection)
        except AssertionError:
            pass
        else:
            raise AssertionError('accepted missing capture inputs, mixed renderer or invalid selection')
    # An unpresented excursion returns to index 1. Matching by index/time
    # alone would attribute the one final frame to both inputs 10 and 12.
    rows = event(10,0,0,1)+event(11,200_000,1,2)+event(12,400_000,2,1)+draw(40,600_000,12,1)
    write_xml(path,rows)
    result = trace.verify(path,3,'gl')
    assert result['changed_with_own_draw'] == 1 and len(result['coalesced']) == 2
    assert result['samples'][0]['input'] == 12
    controls = [('wrong renderer',rows,3,'metal'),('missing event',rows,4,'gl'),
                ('unfinished input',rows[:-4]+event(13,2_000_000,1,2)[:1],4,'gl'),
                ('missing final frame',event(10,0,0,1)+draw(31,200_000,10,1)+event(11,2_000_000,1,2),2,'gl'),
                ('missing stage',event(10,0,0,1)+draw(31,200_000,10,1)[:2]+draw(31,200_000,10,1)[3:]
                 +event(11,2_000_000,1,2)+draw(32,2_200_000,11,2),2,'gl')]
    for name, rows, count, backend in controls:
        write_xml(path,rows)
        try:
            trace.verify(path,count,backend)
        except AssertionError:
            pass
        else:
            raise AssertionError(f'accepted {name}')
print('PASS: exact input identities, coalesced round trips, event-to-flush clock, paired renderer selection and nine rejected incomplete/mismatched controls')
