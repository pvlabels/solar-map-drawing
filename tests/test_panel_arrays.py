"""Production checks for joined panel arrays, independent of customer files."""
import copy
import importlib.util
import math
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

CORE=Path(__file__).resolve().parents[1]/'plugins/solar-map-drawing/skills/solar-map-drawing'
SPEC=importlib.util.spec_from_file_location('map_workbench',CORE/'scripts/map_workbench.py')
w=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(w)

def rectangle(name,role,cx,cy,width,height,**metadata):
    points=[(cx-width/2,cy-height/2),(cx+width/2,cy-height/2),(cx+width/2,cy+height/2),(cx-width/2,cy+height/2)]
    return dict(id=name,role=role,paths=[[['M',*points[0]],*[['L',*p] for p in points[1:]],['Z']]],**metadata)

def panel(name,x,y,**metadata):return rectangle(name,'solar',x,y,10,6,mount_surface='roof',**metadata)
def polygons(elements):return [w.closed_polygons(el['paths'],el['id'])[0] for el in elements if el['role']=='solar']
def center(p):return tuple(sum(q[k] for q in p)/len(p) for k in (0,1))

class PanelArrays(unittest.TestCase):
    def fit(self,elements):return w.production_elements(elements,lambda p:p)
    def assertJoined(self,p,q):
        self.assertAlmostEqual(w.polygon_distance(p,q),0,places=6)
        # Touching interiors have additive area, with a shared full edge.
        shared=set(tuple(round(x,6) for x in a) for a in p)&set(tuple(round(x,6) for x in a) for a in q)
        self.assertEqual(len(shared),2)

    def test_source_gaps_close_without_changing_array_anchor_or_count(self):
        source=[panel('a',20,20),panel('b',32,20)];before=copy.deepcopy(source)
        out,report=self.fit(source);p,q=polygons(out)
        self.assertJoined(p,q);self.assertEqual(source,before)
        self.assertEqual(report['module_count'],2)
        self.assertEqual(report['uniform_modules']['short_long_size_pt'],[6,10])
        self.assertAlmostEqual((center(p)[0]+center(q)[0])/2,26)

    def test_shrinking_keeps_shared_edges_and_clears_exterior(self):
        building=rectangle('house','building',15,15,30,30)
        out,report=self.fit([building,panel('a',4,12),panel('b',16,12)])
        p,q=polygons(out);self.assertJoined(p,q)
        self.assertLess(report['uniform_modules']['common_scale'],1)
        self.assertGreaterEqual(min(x for x,y in p)-(.625+1),1-1e-6)

    def test_clearance_uses_normalized_equipment_not_small_customer_glyph(self):
        device=rectangle('inverter','equipment',38,20,.2,.2,mount_side='freestanding',box_size_pt=[6,8])
        out,report=self.fit([panel('a',18,20),panel('b',30,20),device])
        p,q=polygons(out);self.assertJoined(p,q)
        normalized,_=w.normalize_equipment(out,lambda p:p)
        box=next(el for el in normalized if el['role']=='equipment')
        equipment=w.closed_polygons(box['paths'],box['id'])[0]
        self.assertGreaterEqual(min(w.polygon_distance(p,equipment),w.polygon_distance(q,equipment))-(1.25+1.5)/2,1-1e-6)
        self.assertLess(report['uniform_modules']['common_scale'],1)

    def test_distinct_arrays_remain_separate(self):
        out,report=self.fit([panel('a',20,20,array_id='west'),panel('b',32,20,array_id='east')])
        self.assertEqual(len(report['uniform_modules']['arrays']),2)
        self.assertAlmostEqual(w.polygon_distance(*polygons(out)),2)

    def test_explicit_spacing_exception_is_visible_stroke_gap(self):
        metadata=dict(array_id='special',array_gap_pt=2,array_spacing_evidence='Current user requests 2 pt spacing.',array_spacing_authorization='user')
        out,_=self.fit([panel('a',20,20,**metadata),panel('b',32,20,**metadata)])
        self.assertAlmostEqual(w.polygon_distance(*polygons(out))-1.25,2)

    def test_spacing_requires_evidence(self):
        with self.assertRaisesRegex(ValueError,'array_spacing_evidence'):
            self.fit([panel('a',20,20,array_gap_pt=2)])

    def test_customer_art_alone_cannot_override_locked_panel_rules(self):
        with self.assertRaisesRegex(ValueError,'explicit user authorization'):
            self.fit([panel('a',20,20,array_gap_pt=2,array_spacing_evidence='Customer drawing shows separate panels.')])

    def test_stepped_array_keeps_missing_cell(self):
        out,report=self.fit([panel('a',20,20,array_id='roof',array_cell=[0,0]),panel('b',32,20,array_id='roof',array_cell=[1,0]),panel('c',20,28,array_id='roof',array_cell=[0,1])])
        p,q,r=polygons(out);self.assertJoined(p,q);self.assertJoined(p,r)
        self.assertEqual(report['module_count'],3)
        self.assertEqual(report['uniform_modules']['arrays'][0]['cells'],[[0,0],[1,0],[0,1]])

    def test_duplicate_cells_fail_instead_of_overlapping(self):
        with self.assertRaisesRegex(ValueError,'Duplicate/ambiguous'):
            self.fit([panel('a',20,20,array_id='roof',array_cell=[0,0]),panel('b',32,20,array_id='roof',array_cell=[0,0])])

    def test_corner_only_contact_is_not_an_edge_connected_array(self):
        with self.assertRaisesRegex(ValueError,'connect edge-to-edge'):
            self.fit([panel('a',20,20,array_id='roof',array_cell=[0,0]),panel('b',32,28,array_id='roof',array_cell=[1,1])])

    def test_interior_wall_through_array_anchor_fails_without_erasing_wall(self):
        wall={'id':'divider','role':'wall','paths':[[['M',20,0],['L',20,40]]]}
        with self.assertRaisesRegex(ValueError,'wall/equipment clearances'):
            self.fit([wall,panel('a',20,20)])

    def test_ground_countable_array_also_joins(self):
        source=[panel('a',20,20),panel('b',32,20)]
        for el in source:el['mount_surface']='ground'
        out,report=self.fit(source);self.assertJoined(*polygons(out))
        self.assertEqual(report['uniform_modules']['rooftop_module_count'],0)

    def test_rotated_array_keeps_bearing_and_shared_edges(self):
        angle=math.radians(30);c,s=math.cos(angle),math.sin(angle)
        source=[panel('a',20,20),panel('b',32,20)]
        for el in source:el['paths']=[w.transform_commands(p,lambda p:(c*p[0]-s*p[1],s*p[0]+c*p[1])) for p in el['paths']]
        out,_=self.fit(source);p,q=polygons(out);self.assertJoined(p,q)
        a,b=center(p),center(q);self.assertAlmostEqual(math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])),30)

    def test_array_arrow_follows_compacted_module(self):
        elements=[{'id':name,'role':'solar','kind':'polygon','points':[(x-5,17),(x+5,17),(x+5,23),(x-5,23)],'mount_surface':'roof','evidence':'Synthetic two-module source.'} for name,x in [('a',20),('b',32)]]
        scene={'elements':elements,'alignment':{'enabled':False},'viewport':[0,0,100,100],
               'callouts':[{'text':'ARRAY','x':60,'y':23.9,'size_pt':10,'side':'left','via':[],'target':[32,20],'array_element':'b','clearance':False}]}
        _,_,report=w.scene_artwork(scene,{'paths':[],'viewport':[0,0,100,100]})
        self.assertEqual(report['callout_targets'][0]['source_target'],[32,20])
        self.assertAlmostEqual(report['callout_targets'][0]['output_target'][0],31)

    def test_shared_border_exports_once_at_fixed_weight(self):
        out,_=self.fit([panel('a',20,20),panel('b',32,20)])
        body=w.draw_elements(out,lambda p:p,'#00a651',[],w.fitz.Rect(0,0,100,100))
        svg,report=w.clean_export(w.svg_wrap(body,w.fitz.Rect(0,0,100,100),physical=True))
        tree=ET.fromstring(svg);segments=[]
        for path in tree:
            self.assertEqual(float(path.get('stroke-width')),1.25)
            tokens=re.findall(r'[MLZ]|-?\d+(?:\.\d+)?',path.get('d',''));start=previous=None;i=0
            while i<len(tokens):
                command=tokens[i];i+=1
                if command=='Z':point=start
                else:point=tuple(round(float(v),5) for v in tokens[i:i+2]);i+=2
                if command=='M':start=point
                elif previous is not None:segments.append(tuple(sorted((previous,point))))
                previous=point
        self.assertEqual(len(segments),len(set(segments)))
        self.assertGreater(report['overlap_segments_removed'],0)

if __name__=='__main__':unittest.main()
