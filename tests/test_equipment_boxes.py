"""Equipment-symbol proportions, mounting and physical sizing."""
import copy
import json
import math
import unittest
import xml.etree.ElementTree as ET
from test_panel_arrays import CORE,rectangle,w


class EquipmentBoxes(unittest.TestCase):
    def size(self,element):
        poly=w.closed_polygons(element['paths'],element['id'])[0]
        return math.dist(poly[0],poly[1]),math.dist(poly[1],poly[2])

    def test_all_boxes_have_same_ratio_and_arrow_relative_width(self):
        glyphs=[rectangle('one','equipment',20,20,2,8,mount_side='freestanding',box_size_pt=[12,10]),
                rectangle('two','equipment',50,20,14,4,mount_side='freestanding',box_size_pt=[100,1])]
        before=copy.deepcopy(glyphs);out,report=w.normalize_equipment(glyphs,lambda p:p)
        asset=json.loads((CORE/'assets/leader-arrow-2.json').read_text())
        ys=[p[1] for p in w.vertices(asset['commands'])]
        expected_head_width=(max(ys)-min(ys))*1.0/asset['reference_stroke_pt']
        for el in out:
            width,depth=self.size(el)
            self.assertAlmostEqual(width/depth,1.5)
            self.assertAlmostEqual(width/expected_head_width,1.25)
        self.assertEqual(report[0]['size_pt'],report[1]['size_pt'])
        self.assertEqual(glyphs,before)

    def test_dimensions_do_not_scale_with_map(self):
        glyph=rectangle('device','equipment',20,30,2,2,mount_side='freestanding')
        sizes=[]
        for scale in (1,3):
            transform=lambda p:(p[0]*scale,p[1]*scale)
            mapped,_=w.production_elements([glyph],transform)
            normalized,report=w.normalize_equipment(mapped,transform)
            sizes.append(self.size(normalized[0]))
            self.assertEqual(report[0]['output_center'],(20*scale,30*scale))
        self.assertAlmostEqual(sizes[0][0],sizes[1][0]);self.assertAlmostEqual(sizes[0][1],sizes[1][1])

    def test_boxes_remain_flush_on_correct_wall_faces(self):
        house=rectangle('house','building',50,50,100,100,structure_id='house')
        glyphs=[rectangle('outside','equipment',25,-2,2,2,mount_structure='house',wall_segment=[[0,0],[100,0]],mount_side='outside'),
                rectangle('inside','equipment',45,2,2,2,mount_structure='house',wall_segment=[[0,0],[100,0]],mount_side='inside'),
                rectangle('right','equipment',102,50,2,2,mount_structure='house',wall_segment=[[100,0],[100,100]],mount_side='outside')]
        out,report=w.normalize_equipment([house,*glyphs],lambda p:p)
        by_id={el['id']:w.closed_polygons(el['paths'],el['id'])[0] for el in out if el['role']=='equipment'}
        for name in ('outside','inside'):
            self.assertAlmostEqual(by_id[name][0][1],0);self.assertAlmostEqual(by_id[name][1][1],0)
        self.assertLess(by_id['outside'][2][1],0);self.assertGreater(by_id['inside'][2][1],0)
        self.assertAlmostEqual(by_id['right'][0][0],100);self.assertGreater(by_id['right'][2][0],100)
        self.assertEqual([r['wall_contact'] for r in report],[(25,0),(45,0),(100,50)])

    def test_rotated_wall_keeps_ratio_and_mounting_edge(self):
        source=[rectangle('house','building',50,50,100,100,structure_id='house'),
                rectangle('box','equipment',25,-2,2,2,mount_structure='house',wall_segment=[[0,0],[100,0]],mount_side='outside')]
        angle=math.radians(30);c,s=math.cos(angle),math.sin(angle)
        transform=lambda p:(c*p[0]-s*p[1],s*p[0]+c*p[1])
        mapped,_=w.production_elements(source,transform);out,report=w.normalize_equipment(mapped,transform)
        box=out[1];a,b=w.closed_polygons(box['paths'],box['id'])[0][:2]
        self.assertAlmostEqual(math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])),30)
        self.assertAlmostEqual(self.size(box)[0]/self.size(box)[1],1.5)
        self.assertAlmostEqual(report[0]['wall_contact'][0],25*c)
        self.assertAlmostEqual(report[0]['wall_contact'][1],25*s)

    def test_freestanding_source_center_and_bearing_are_retained(self):
        glyph=rectangle('pad','equipment',20,30,3,3,mount_side='freestanding',box_rotation_deg=35)
        out,report=w.normalize_equipment([glyph],lambda p:p)
        self.assertEqual(report[0]['output_center'],(20,30))
        a,b=w.closed_polygons(out[0]['paths'],'pad')[0][:2]
        self.assertAlmostEqual(math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])),35)

    def test_export_is_one_unfilled_1_5_point_rectangle(self):
        source=rectangle('device','equipment',20,30,4,4,mount_side='freestanding',solid=True)
        source['paths'][0].extend([['M',18,28],['L',22,32]])  # Customer strike.
        normalized,_=w.normalize_equipment([source],lambda p:p)
        body=w.draw_elements(normalized,lambda p:p,'#00a651',[],w.fitz.Rect(0,0,100,100))
        svg,_=w.clean_export(w.svg_wrap(body,w.fitz.Rect(0,0,100,100),physical=True))
        tree=ET.fromstring(svg);paths=list(tree.iter('{http://www.w3.org/2000/svg}path'))
        self.assertEqual(len(paths),1)
        self.assertEqual(paths[0].get('fill'),'none');self.assertEqual(float(paths[0].get('stroke-width')),1.5)
        self.assertEqual(len(w.line_segments(normalized[0]['paths'])),4)


if __name__=='__main__':unittest.main()
