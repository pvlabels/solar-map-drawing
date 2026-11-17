"""Check upright lettering, orbital placement and unchanged north bearings."""
import importlib.util
import math
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('north_orbit',ROOT/'plugins/solar-map-drawing/skills/solar-map-drawing/scripts/map_workbench.py')
w=importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def symbol(angle, height=34, applied=0, **kwargs):
    north={'x':100,'y':100,'height_pt':height,'source_rotation_deg':angle,**kwargs}
    body,bearing=w.draw_north(north,applied,'#00a651')
    svg,_=w.clean_export(w.svg_wrap(body,w.fitz.Rect(0,0,200,200),physical=True))
    nodes=list(ET.fromstring(svg))
    text=next((n for n in nodes if n.tag.endswith('text')),None)
    return svg,nodes,text,bearing


def glyph_box(text):
    size=float(text.get('font-size')); box=w.fitz.Font('helv').glyph_bbox(ord('N'))
    origin=float(text.get('x'))-w.fitz.get_text_length('N',fontsize=size)/2
    baseline=float(text.get('y'))
    return (origin+box.x0*size,baseline-box.y1*size,origin+box.x1*size,baseline-box.y0*size)


class NorthOrbitTests(unittest.TestCase):
    def test_eight_directions_keep_n_upright_on_the_opposite_side(self):
        expected=[(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1),(1,0),(1,1)]
        radii=[]
        for angle,signs in zip(range(0,360,45),expected):
            with self.subTest(angle=angle):
                _,nodes,text,bearing=symbol(angle)
                self.assertEqual(bearing,angle)
                self.assertNotIn('transform',text.attrib)
                self.assertEqual(text.text,'N')
                x0,y0,x1,y1=glyph_box(text)
                dx,dy=(x0+x1)/2-100,(y0+y1)/2-100
                for offset,sign in zip((dx,dy),signs):
                    if sign==0:self.assertAlmostEqual(offset,0,places=3)
                    else:self.assertGreater(offset*sign,0)
                radii.append(math.hypot(dx,dy))
                self.assertTrue(all(n.tag.split('}')[-1] in ('path','text') for n in nodes))
        self.assertLess(max(radii)-min(radii),.002)

    def test_north_up_retains_existing_baseline(self):
        _,_,text,_=symbol(0)
        self.assertAlmostEqual(float(text.get('y')),100+34+34*.52+4,places=3)

    def test_glyph_clears_the_needle_at_every_bearing_and_multiple_sizes(self):
        for height in (20,34,60):
            for angle in range(0,360,5):
                _,nodes,text,_=symbol(angle,height,snap_tolerance_deg=0)
                path=next(n for n in nodes if n.tag.endswith('path'))
                outer=[]
                for command in w.parse_export_path(path.get('d')):
                    if command[0]=='Z':break
                    outer.append(tuple(command[-2:]))
                x0,y0,x1,y1=glyph_box(text)
                rectangle=[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
                self.assertGreater(w.polygon_distance(outer,rectangle),3,(height,angle))

    def test_orbit_uses_compensated_snapped_or_overridden_bearing(self):
        cases=[(38,7,{},45),(24,7,{},31),
               (20,7,{'display_rotation_deg':270,'display_rotation_evidence':'User correction'},270)]
        for source,applied,options,expected in cases:
            _,_,actual,bearing=symbol(source,applied=applied,**options)
            _,_,reference,_=symbol(expected,snap_tolerance_deg=0)
            self.assertEqual(bearing,expected)
            self.assertEqual((actual.get('x'),actual.get('y')),(reference.get('x'),reference.get('y')))

    def test_map_only_omits_n_without_changing_the_needle(self):
        _,labeled,_,_=symbol(315)
        _,plain,text,_=symbol(315,include_label=False)
        self.assertIsNone(text)
        self.assertEqual(labeled[0].get('d'),plain[0].get('d'))
        scene=w.apply_output_mode({'north_arrow':{'x':100,'y':100,'source_rotation_deg':315}},'map-only')
        self.assertFalse(scene['north_arrow']['include_label'])

if __name__=='__main__':unittest.main()
