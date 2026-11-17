import copy
import importlib.util
import math
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('corner_roads',ROOT/'plugins/solar-map-drawing/skills/solar-map-drawing/scripts/map_workbench.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


def roads(sides):
    return [{'id':side,'layout_side':side,'source_side':side+' of the property',
             'evidence':'Synthetic source road on this side',
             'label':{'text':side.upper()+' STREET','size_pt':8}} for side in sides]


def rendered(sides=('left','bottom'),area=(10,60,310,260)):
    body=w.draw_roads(roads(sides),lambda p:p,'#00a651',{'drawing_area':area},w.fitz.Rect(0,0,400,600))
    svg,_=w.clean_export(w.svg_wrap(body,w.fitz.Rect(0,0,400,600),physical=True))
    return list(ET.fromstring(svg))


def segments(nodes,role,side):
    return [edge for n in nodes if n.get('data-role')==role and n.get('data-road-side')==side
            for edge in w.line_segments([w.parse_export_path(n.get('d'))])]


def scene(size=356.4,sides=('left','bottom'),mode='map-labeled'):
    return {'output_mode':mode,'alignment':{'enabled':False},
            'layout':{'size_pt':[size,size],'map_box':[95,130,size-65,size-85]},
            'road_layout':{'drawing_area':[12,85,size-12,size-25]},'roads':roads(sides),
            'elements':[{'id':'house','role':'building','kind':'polygon',
                         'points':[[0,0],[100,0],[100,80],[0,80]],'evidence':'Synthetic source footprint'},
                        {'id':'ridge','role':'roof','kind':'polyline',
                         'points':[[50,0],[50,80]],'evidence':'Synthetic source ridge'}]}


class RoadLayoutTests(unittest.TestCase):
    def test_corner_inner_edges_meet_and_outer_lanes_span_the_area(self):
        for sides in (('left','bottom'),('right','top'),('left','right','bottom')):
            with self.subTest(sides=sides):
                nodes=rendered(sides)
                self.assertEqual(sum(n.get('data-role')=='road-edge' for n in nodes),len(sides))
                for side in sides:
                    solid=segments(nodes,'road-edge',side)[0]
                    dashed=segments(nodes,'road-dashed',side)
                    self.assertTrue(dashed)
                    self.assertTrue(all(abs(a[0]-b[0])<1e-6 or abs(a[1]-b[1])<1e-6 for a,b in [solid,*dashed]))
                    fixed=10.375 if side=='left' else 309.625 if side=='right' else 60.375 if side=='top' else 259.625
                    axis=0 if side in ('left','right') else 1
                    self.assertTrue(all(abs(p[axis]-fixed)<1e-6 for edge in dashed for p in edge))
                    length=sum(math.dist(a,b) for a,b in [solid])
                    self.assertGreater(length,170)
                adjacent=[s for s in sides if s in ('left','right')]
                horizontal=next(s for s in sides if s in ('top','bottom'))
                corners=segments(nodes,'road-edge',horizontal)[0]
                for side in adjacent:
                    line=segments(nodes,'road-edge',side)[0]
                    self.assertTrue(any(math.dist(a,b)<1e-6 for a in line for b in corners))
                self.assertTrue(all(n.get('stroke-width')=='0.75' for n in nodes if n.tag.endswith('path')))

    def test_lane_width_and_dashes_scale_with_drawing_area(self):
        first=rendered(('left',),(10,60,210,260))
        second=rendered(('left',),(0,0,400,400))
        def dimensions(nodes):
            inner=segments(nodes,'road-edge','left')[0][0][0]
            outer=segments(nodes,'road-dashed','left')[0]
            return inner-outer[0][0],math.dist(*outer)
        small=dimensions(first);large=dimensions(second)
        self.assertAlmostEqual(large[0],2*small[0])
        self.assertAlmostEqual(large[1],2*small[1])

    def test_road_extension_does_not_change_building_fit_or_source_scene(self):
        original=scene();saved=copy.deepcopy(original)
        svg,report=w.render_scene(original,{'paths':[],'viewport':[0,0,150,150]})
        no_roads=copy.deepcopy(original);no_roads['roads']=[]
        plain,plain_report=w.render_scene(no_roads,{'paths':[],'viewport':[0,0,150,150]})
        def geometry(s):
            return [n.attrib for n in ET.fromstring(s) if n.get('data-role') in ('building','roof')]
        self.assertEqual(geometry(svg),geometry(plain))
        self.assertEqual(report['alignment'],plain_report['alignment'])
        self.assertEqual(original,saved)

    def test_map_only_retains_all_roads_but_omits_names(self):
        for mode in ('map-labeled','map-only'):
            svg,_=w.render_scene(scene(sides=('left','right','bottom'),mode=mode),{'paths':[],'viewport':[0,0,150,150]})
            nodes=list(ET.fromstring(svg))
            self.assertEqual(sum(n.get('data-role')=='road-edge' for n in nodes),3)
            self.assertEqual(sum(n.tag.endswith('text') for n in nodes),3 if mode=='map-labeled' else 0)
            self.assertTrue(all(n.get('fill')=='#ed1c24' for n in nodes if n.tag.endswith('text')))

    def test_reserved_work_zone_rejects_a_road_crossing_the_header(self):
        z=w.placard_tools()
        layout={'work_zone':[10,60,310,260],'reserved_header_corner':None,'holes':[]}
        body=w.draw_roads(roads(('left','bottom')),lambda p:p,'#00a651',{'drawing_area':[10,60,310,260]})
        self.assertEqual(z.validate_map_svg(body,w.fitz.Rect(0,0,320,280),layout)['reserved_zone_collisions'],0)
        bad=w.draw_roads(roads(('left','bottom')),lambda p:p,'#00a651',{'drawing_area':[10,30,310,260]})
        with self.assertRaisesRegex(ValueError,'outside map/callout'):
            z.validate_map_svg(bad,w.fitz.Rect(0,0,320,280),layout)

    def test_legacy_helper_is_unchanged_and_invalid_new_layout_is_rejected(self):
        old={'points':[[100,20],[100,200]],'outer_offset_pt':-14,'source_side':'right','evidence':'Legacy source',
             'label':{'text':'OLD STREET','size_pt':8}}
        self.assertEqual(w.draw_roads([old],lambda p:p,'green'),w.draw_road(old,lambda p:p,'green'))
        for invalid in ({'drawing_area':[0,0,10,10]}, {'drawing_area':[0,0,200,200],'lane_width_ratio':-1}):
            with self.assertRaises(ValueError):w.draw_roads(roads(('left',)),lambda p:p,'green',invalid)
        with self.assertRaisesRegex(ValueError,'Multiple streets'):
            w.draw_roads(roads(('left','left')),lambda p:p,'green',{'drawing_area':[0,0,200,200]})

if __name__=='__main__':unittest.main()
