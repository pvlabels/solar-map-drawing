"""Short equipment routes and live attached heads survive delivery/export."""
import copy
import math
import unittest
import xml.etree.ElementTree as ET
from test_arrow_backing import scene, MANIFEST, raster, w


def simple():
    data=scene();data['roads']=[];data['callouts']=data['callouts'][:1]
    return data


class EquipmentRoutingTests(unittest.TestCase):
    def test_straight_route_replaces_stale_multibend_via(self):
        data=simple();data['callouts'][0]['via']=[[90,100],[90,50],[220,50],[220,100]]
        before=copy.deepcopy(data);svg,report=w.render_scene(data,MANIFEST)
        self.assertEqual(len(report['callout_targets'][0]['shaft_route']),2)
        self.assertEqual(data,before)
        root=ET.fromstring(svg)
        shaft=next(n for n in root if n.get('data-equipment-leader')=='true')
        self.assertEqual(shaft.get('fill'),'none');self.assertEqual(shaft.get('stroke-width'),'1')
        self.assertEqual(shaft.get('d').count('M'),1)
        self.assertTrue(shaft.get('marker-end').startswith('url(#'))
        self.assertFalse(any(n.get('data-arrowhead') for n in root))

    def test_one_bend_replaces_longer_detour(self):
        data=simple();data['callouts'][0].update(y=45.07,via=[[90,40],[90,20],[270,20]])
        _,report=w.render_scene(data,MANIFEST)
        self.assertEqual(len(report['callout_targets'][0]['shaft_route']),3)

    def test_house_traversal_requires_moving_label_to_same_side(self):
        data=simple()
        data['elements'].append({'id':'house','role':'building','kind':'polygon',
            'points':[[100,50],[220,50],[220,190],[100,190]],'evidence':'Synthetic house'})
        with self.assertRaisesRegex(ValueError,'Move the equipment label'):
            w.render_scene(data,MANIFEST)
        data['callouts'][0].update(x=390,side='left')
        _,report=w.render_scene(data,{'paths':[],'viewport':[0,0,450,230]})
        self.assertEqual(len(report['callout_targets'][0]['shaft_route']),2)

    def test_interior_equipment_allows_only_nearby_final_approach(self):
        poly=[(100,50),(220,50),(220,190),(100,190)]
        context=(list(zip(poly,poly[1:]+poly[:1])),[poly])
        self.assertTrue(w.equipment_route_clear([(80,120),(106,120)],(110,120),context,[],[]))
        self.assertFalse(w.equipment_route_clear([(240,120),(114,120)],(110,120),context,[],[]))
        self.assertFalse(w.equipment_route_clear([(80,100),(130,100),(130,116)],(130,120),context,[],[]))

    def test_equipment_obstruction_never_splits_shaft(self):
        data=simple();data['elements'].append({'id':'other','role':'equipment','kind':'polygon',
            'points':[[147,97],[153,97],[153,103],[147,103]],'mount_side':'freestanding','evidence':'Synthetic obstacle'})
        with self.assertRaisesRegex(ValueError,'Move the equipment label'):w.render_scene(data,MANIFEST)
        data['callouts'][0]['via']=[[100,100],[100,60],[220,60],[220,100]]
        svg,report=w.render_scene(data,MANIFEST)
        shaft=next(n for n in ET.fromstring(svg) if n.get('data-equipment-leader')=='true')
        self.assertEqual(shaft.get('d').count('M'),1)
        self.assertGreater(len(report['callout_targets'][0]['shaft_route']),2)

    def test_marker_orientation_matches_report_tip_at_cardinal_bearings(self):
        cases=[('right',10,105.07,(270,100)),('left',270,105.07,(40,100)),
               ('bottom',150,20,(150,200)),('top',150,220,(150,40))]
        for side,x,y,target in cases:
            with self.subTest(side=side):
                label={'text':'DEVICE','x':x,'y':y,'size_pt':13,'side':side,'target':target,'target_element':'d','anchor':'middle'}
                body,report=w.draw_callouts([label],lambda p:p,'#00a651',w.fitz.Rect(0,0,340,260),[],equipment_targets={'d':target})
                svg,_=w.clean_export(w.svg_wrap(body,w.fitz.Rect(0,0,340,260),physical=True))
                expanded=ET.fromstring(w.placard_tools().expand_equipment_markers(svg))
                head=next(n for n in expanded if n.tag.endswith('path') and n.get('stroke') is None)
                tip=w.parse_export_path(head.get('d'))[0][1:]
                self.assertLess(math.dist(tip,report[0]['arrow_tip']),.003)
                img=raster(svg)
                envelope=report[0]['head_envelope'];cx=sum(p[0] for p in envelope)/3;cy=sum(p[1] for p in envelope)/3
                self.assertLess(min(img.getpixel((round(cx*4),round(cy*4)))),200)

    def test_multimap_markers_keep_colors_and_translate_with_shafts(self):
        bodies=[]
        for i,color in enumerate(('#00a651','#000000','#ffffff','#00a651')):
            data=simple();body,_,_=w.scene_artwork(data,MANIFEST)
            body=body.replace('#00a651',color).replace('equipment-arrow-2-00a651','equipment-arrow-2-'+color[1:])
            bodies.append(f'<g transform="translate({320*i} 30)">{body}</g>')
        svg,report=w.clean_export(w.svg_wrap(''.join(bodies),w.fitz.Rect(0,0,1280,300),physical=True))
        root=ET.fromstring(svg);markers={n.get('id'):n for n in root.iter() if n.tag.endswith('marker')}
        self.assertEqual(len(markers),3);self.assertEqual(report['attached_equipment_arrows'],4)
        for shaft in root:
            if shaft.get('marker-end'):
                self.assertEqual(markers[shaft.get('marker-end')[5:-1]][0].get('fill'),shaft.get('stroke'))
                self.assertNotIn('transform',shaft.attrib)
        self.assertFalse(any(n.tag.split('}')[-1]=='g' for n in root.iter()))

    def test_zone_validation_checks_attached_head_extent(self):
        data=simple();body,_,_=w.scene_artwork(data,MANIFEST)
        # A broad work zone accepts the whole map; a boundary through its head rejects it.
        plan={'work_zone':[0,0,310,230],'reserved_header_corner':None,'holes':[]}
        w.placard_tools().validate_map_svg(body,w.fitz.Rect(0,0,310,230),plan)
        # Directly validate an equipment leader with no target geometry: only its head overflows.
        arrow,_=w.draw_callouts([{'text':'X','x':10,'y':105.07,'side':'right','target':[270,100],'target_element':'d'}],lambda p:p,'green',w.fitz.Rect(0,0,310,230),[],equipment_targets={'d':(270,100)})
        plan['work_zone']=[0,0,263,230]
        with self.assertRaisesRegex(ValueError,'outside map/callout working zone'):
            w.placard_tools().validate_map_svg(arrow,w.fitz.Rect(0,0,310,230),plan)


if __name__=='__main__':unittest.main()
