"""Cross-process drawing and finishing regressions from MAP GUIDLINES.pdf."""
import copy
import math
import unittest
import xml.etree.ElementTree as ET
from test_arrow_backing import scene, MANIFEST, raster, w


def render(process):
    data=scene();data['production']={'process':process}
    data['labels']=[{'text':'TEN POINT','x':10,'y':205,'size_pt':10,'anchor':'start'},
                    {'text':'ELEVEN POINT','x':10,'y':222,'size_pt':11,'anchor':'start'}]
    svg,report=w.render_scene(data,MANIFEST)
    return svg,list(ET.fromstring(svg)),report


def placard():
    return {'order':{'work_order':'123456','sku':'07-650','item_code':'A','nominal_size_in':[5,5],
                     'source_page':1,'order_row_evidence':'Synthetic confirmed 5-inch sign'},
            'production_size_pt':[360,360],'production_size_evidence':'Synthetic measured trim',
            'warning':{'style':'classic','heading':'CAUTION:',
                       'lines':['SOURCE-CONFIRMED WORDING:'],'evidence':'Synthetic exact warning'}}


class PdfGuidelinesTests(unittest.TestCase):
    def test_ten_point_threshold_applies_only_to_laser(self):
        for process in ('laser','metal','label'):
            _,nodes,_=render(process)
            texts={n.text:n for n in nodes if n.tag.endswith('text')}
            normal={'laser':'#00a651','metal':'#000000','label':'#ffffff'}[process]
            self.assertEqual(texts['TEN POINT'].get('fill'),'#ed1c24' if process=='laser' else normal)
            self.assertEqual(texts['ELEVEN POINT'].get('fill'),normal)
            self.assertTrue(all(n.get('data-production-process')==process for n in nodes if not n.tag.endswith('defs')))

    def test_print_label_crossing_uses_red_and_retains_white_foreground(self):
        svg,nodes,report=render('label');img=raster(svg)
        self.assertTrue(all(n.get('stroke')=='#ed1c24' for n in nodes if n.get('data-role')=='leader-underlay'))
        self.assertEqual(report['callout_targets'][0]['backing_color'],'#ed1c24')
        gap=img.getpixel((480,406));line=img.getpixel((480,420))
        self.assertGreater(gap[0],200);self.assertLess(gap[1],60)
        self.assertGreater(min(line),240)

    def test_callout_justification_preserves_target_and_source(self):
        data=scene();before=copy.deepcopy(data)
        svg,report=w.render_scene(data,MANIFEST)
        meter=next(n for n in ET.fromstring(svg) if n.text=='METER')
        self.assertEqual(meter.get('text-anchor'),'end')
        self.assertEqual(report['callout_targets'][0]['source_target'],[270,100])
        self.assertEqual(data,before)

    def test_typography_rejects_too_small_callouts_and_arbitrary_compression(self):
        for extra in ({'size_pt':7.5},{'size_pt':10,'width_scale':.81},{'size_pt':10,'width_scale':1.05}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                w.text_box({'text':'DEVICE','x':10,'y':20,**extra})
        for scale in (.70,.75,.80,.85,.90,.95,1):
            w.text_box({'text':'DEVICE','x':10,'y':20,'size_pt':8,'width_scale':scale})

    def test_north_uses_arrow15_presets_and_upright_letter(self):
        for stroke,size in ((2,18),(3,25)):
            body,_=w.draw_north({'x':100,'y':100,'source_rotation_deg':315,'stroke_pt':stroke},0,'#00a651')
            nodes=list(ET.fromstring('<svg>'+body+'</svg>')[0])
            self.assertEqual(nodes[0].get('data-arrowhead'),'Illustrator Arrow 15')
            self.assertEqual(float(nodes[0].get('data-reference-stroke-pt')),stroke)
            self.assertEqual(float(nodes[1].get('font-size')),size)
            self.assertNotIn('transform',nodes[1].attrib)
        with self.assertRaises(ValueError):w.draw_north({'x':0,'y':0,'source_rotation_deg':0,'stroke_pt':1},0,'green')

    def test_street_names_face_outward_except_top(self):
        roads=[{'layout_side':side,'source_side':side,'evidence':'Synthetic road',
                'label':{'text':side.upper(),'size_pt':8}} for side in ('left','right','top','bottom')]
        body=w.draw_roads(roads,lambda p:p,'black',{'drawing_area':[0,0,300,300]})
        svg,_=w.clean_export(w.svg_wrap(body,w.fitz.Rect(0,0,300,300),physical=True))
        texts={n.text:n for n in ET.fromstring(svg) if n.tag.endswith('text')}
        for side,expected in (('LEFT',-1),('RIGHT',1)):
            matrix=list(map(float,texts[side].get('transform')[7:-1].split()))
            self.assertAlmostEqual(matrix[1],expected)
        self.assertNotIn('transform',texts['TOP'].attrib)
        self.assertNotIn('transform',texts['BOTTOM'].attrib)

    def test_cutline_footer_and_layer_metadata_follow_process(self):
        z=w.placard_tools()
        for process in ('laser','metal','label'):
            plan=z.plan(placard(),production={'process':process})
            body=z.chrome_svg(plan);nodes=list(ET.fromstring('<svg>'+body+'</svg>'))
            cut=next(n for n in nodes if n.get('id')=='cutline')
            self.assertEqual(float(cut.get('stroke-width')),.001 if process=='laser' else 1)
            self.assertEqual(cut.get('data-production-layer'),'Laser' if process=='laser' else 'Flex Cut')
            foot=next(n for n in nodes if n.get('data-role')=='footer-part')
            self.assertEqual(foot.get('font-size'),'5');self.assertNotIn('transform',foot.attrib)
            self.assertEqual(foot.get('fill'),{'laser':'#ed1c24','metal':'#000000','label':'#ffffff'}[process])
            self.assertEqual(plan['header_records'][0]['text'],'CAUTION:')

    def test_mixed_map_export_keeps_each_process_colors(self):
        bodies=[]
        for i,process in enumerate(('laser','metal','label')):
            data=scene();data['production']={'process':process}
            data['labels']=[{'text':process,'x':10,'y':205,'size_pt':10,'anchor':'start'}]
            body,_,_=w.scene_artwork(data,MANIFEST)
            bodies.append(f'<g transform="translate({i*320} 0)">{body}</g>')
        svg,_=w.clean_export(w.svg_wrap(''.join(bodies),w.fitz.Rect(0,0,960,230),physical=True))
        found={n.text:n.get('fill') for n in ET.fromstring(svg) if n.tag.endswith('text')}
        self.assertEqual([found[p] for p in ('laser','metal','label')],['#ed1c24','#000000','#ffffff'])

    def test_print_process_cannot_reuse_laser_plastic_trim_profile(self):
        for process in ('metal','label'):
            data=placard();data['profile']='stock-04-650'
            with self.assertRaisesRegex(ValueError,'metal/label cut size'):
                w.placard_tools().plan(data,production={'process':process})

if __name__=='__main__':unittest.main()
