"""Wrapped lines retain logical text ownership, placement and zone checks."""
import copy
import unittest
import xml.etree.ElementTree as ET
from test_arrow_backing import w
from test_pdf_guidelines import placard

MANIFEST={'paths':[],'viewport':[0,0,400,300]}


def scene():
    return {'output_mode':'map-labeled','elements':[{'id':'context','role':'context','kind':'polyline',
             'points':[[300,20],[320,20]],'evidence':'Synthetic context line'}],
            'labels':[{'text':['MAIN SERVICE','PANEL'],'x':30,'y':50,'size_pt':13,'anchor':'start'}]}


def texts(svg):
    return [node for node in ET.fromstring(svg) if node.tag.endswith('text')]


class TextBlockTests(unittest.TestCase):
    def test_lines_and_newlines_export_one_editable_object_with_same_layout(self):
        a=scene();b=copy.deepcopy(a);b['labels'][0]['text']='MAIN SERVICE\nPANEL'
        sa,_=w.render_scene(a,MANIFEST);sb,_=w.render_scene(b,MANIFEST)
        self.assertEqual(sa,sb)
        blocks=texts(sa);self.assertEqual(len(blocks),1)
        self.assertEqual([n.text for n in blocks[0]],['MAIN SERVICE','PANEL'])
        self.assertEqual([float(n.get('y')) for n in blocks[0]],[50,65.6])
        self.assertEqual(a,scene())

    def test_nearby_independent_labels_remain_separate_blocks(self):
        s=scene();s['labels'].append({'text':['AC','DISCONNECT'],'x':30,'y':86,'size_pt':13,'anchor':'start'})
        svg,_=w.render_scene(s,MANIFEST)
        blocks=texts(svg);self.assertEqual(len(blocks),2)
        self.assertEqual([[n.text for n in b] for b in blocks],[['MAIN SERVICE','PANEL'],['AC','DISCONNECT']])

    def test_multiline_callout_has_one_block_and_one_leader(self):
        s=scene();s['labels']=[]
        s['callouts']=[{'text':['MAIN SERVICE','PANEL'],'x':30,'y':80,'size_pt':13,
                        'side':'right','target':[330,140]}]
        svg,report=w.render_scene(s,MANIFEST)
        self.assertEqual(len(texts(svg)),1)
        self.assertEqual(len(list(texts(svg)[0])),2)
        self.assertEqual(len(report['callout_targets']),1)
        self.assertEqual(report['export_cleanup']['leader_backing_strokes'],1)

    def test_translated_condensed_block_moves_every_line_once(self):
        s=scene();s['labels'][0]['width_scale']=.8
        body,_,_=w.scene_artwork(s,MANIFEST)
        svg,_=w.clean_export(w.svg_wrap('<g transform="translate(40 20)">'+body+'</g>',w.fitz.Rect(0,0,450,350),physical=True))
        block=texts(svg)[0]
        self.assertEqual(block.get('transform'),'matrix(0.8 0 0 1 0 0)')
        self.assertEqual([float(n.get('x'))*.8 for n in block],[70,70])
        self.assertEqual([float(n.get('y')) for n in block],[70,85.6])

    def test_rotated_block_preserves_line_coordinates_and_translation(self):
        body='<g transform="translate(40 20)"><text x="0" y="0" font-size="13" transform="matrix(0 1 -1 0 100 100)"><tspan x="0" y="0">LINE ONE</tspan><tspan x="0" y="15.6">LINE TWO</tspan></text></g>'
        svg,_=w.clean_export(w.svg_wrap(body,w.fitz.Rect(0,0,400,300),physical=True))
        block=texts(svg)[0];self.assertEqual(block.get('transform'),'matrix(0 1 -1 0 140 120)')
        self.assertEqual([n.get('y') for n in block],['0','15.6'])

    def test_finished_paragraphs_stay_together_without_merging_notes(self):
        z=w.placard_tools();p=placard()
        p['warning']['lines']=['POWER TO THIS BUILDING IS SUPPLIED','FROM THE FOLLOWING SOURCES:']
        p['bottom_notes']=[{'text':['FIRST NOTE','CONTINUED'],'size_pt':10,'evidence':'Synthetic note one'},
                           {'text':['SECOND NOTE','CONTINUED'],'size_pt':10,'evidence':'Synthetic note two'}]
        plan=z.plan(p)
        svg,_=w.clean_export(w.svg_wrap(z.chrome_svg(plan),w.fitz.Rect(0,0,360,360),physical=True))
        blocks=texts(svg)
        warning=[b for b in blocks if b.get('data-role')=='warning']
        self.assertEqual(len(warning),2)  # heading and one body paragraph
        self.assertGreaterEqual(len(list(warning[1])),2)
        notes=[b for b in blocks if b.get('data-role')=='bottom-note']
        self.assertEqual(len(notes),2);self.assertTrue(all(len(list(b))==2 for b in notes))
        self.assertEqual(len([b for b in blocks if b.get('data-role') in ('footer','footer-part')]),2)

    def test_lower_wrapped_line_is_checked_against_zone_and_holes(self):
        z=w.placard_tools();s=scene();s['labels'][0]['y']=90
        body,box,_=w.scene_artwork(s,MANIFEST)
        p={'work_zone':[0,0,400,100],'reserved_header_corner':None,'holes':[]}
        with self.assertRaisesRegex(ValueError,'outside map/callout'):z.validate_map_svg(body,box,p)
        p['work_zone']=[0,0,400,200];p['holes']=[[45,105,3]]
        with self.assertRaisesRegex(ValueError,'hole'):z.validate_map_svg(body,box,p)

    def test_map_only_omits_whole_text_block(self):
        s=scene();s['output_mode']='map-only';svg,_=w.render_scene(s,MANIFEST)
        self.assertEqual(texts(svg),[])

if __name__=='__main__':unittest.main()
