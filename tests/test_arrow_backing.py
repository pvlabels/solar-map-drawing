"""Verify visible crossing gaps and preserved editable geometry."""
import copy
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/solar-map-drawing/skills/solar-map-drawing/scripts/map_workbench.py'
spec = importlib.util.spec_from_file_location('arrow_backing_workbench', SCRIPT)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
MANIFEST = {'paths': [], 'viewport': [0, 0, 310, 230]}


def scene():
    return {
        'output_mode': 'map-labeled',
        'elements': [
            {'id': 'ridge', 'role': 'roof', 'kind': 'polyline',
             'points': [[120, 40], [120, 180]], 'evidence': 'Synthetic crossing'},
            {'id': 'meter', 'role': 'equipment', 'kind': 'polygon',
             'points': [[267, 97], [273, 97], [273, 103], [267, 103]],
             'mount_side': 'freestanding', 'evidence': 'Synthetic equipment target'}],
        'roads': [{'points': [[180, 40], [180, 180]], 'outer_offset_pt': -16,
                   'source_side': 'right', 'evidence': 'Synthetic road crossing'}],
        'callouts': [
            {'text': 'METER', 'x': 10, 'y': 105.07, 'size_pt': 13, 'side': 'right', 'via': [],
             'target': [270, 100], 'target_element': 'meter', 'clearance': False},
            {'text': 'DEVICE', 'x': 150, 'y': 20, 'anchor': 'middle',
             'side': 'bottom', 'via': [], 'target': [150, 210]}]}


def render(source=None):
    svg, report = w.render_scene(source or scene(), MANIFEST)
    return svg, report, list(ET.fromstring(svg))


def raster(svg):
    svg=w.placard_tools().expand_equipment_markers(svg)
    with w.fitz.open(stream=svg.encode(), filetype='svg') as doc:
        pix = doc[0].get_pixmap(matrix=w.fitz.Matrix(4, 4), alpha=False)
    return w.Image.frombytes('RGB', [pix.width, pix.height], pix.samples)


class ArrowBackingTests(unittest.TestCase):
    def test_white_backing_and_colored_shaft_survive_cleanup_in_order(self):
        _, report, nodes = render()
        backings = [i for i, n in enumerate(nodes) if n.get('data-role') == 'leader-underlay']
        self.assertEqual(len(backings), 2)
        for i in backings:
            backing, shaft = nodes[i:i+2]
            self.assertEqual(backing.get('stroke'), '#ffffff')
            self.assertEqual(backing.get('stroke-width'), '5')
            self.assertEqual(shaft.get('stroke-width'), '1')
            self.assertEqual(shaft.get('data-role'), 'leader')
            self.assertEqual(backing.get('d'), shaft.get('d'))
        self.assertEqual(report['export_cleanup']['leader_backing_strokes'], 2)
        self.assertEqual(sum(n.get('data-arrowhead') is not None for n in ET.fromstring(render()[0]).iter()), 2)
        self.assertTrue(all(n.tag.split('}')[-1] in ('path', 'text', 'defs') for n in nodes))

    def test_legacy_clearance_false_cannot_disable_required_backing(self):
        _, report, _ = render()
        self.assertTrue(report['callout_targets'][0]['clearance'])
        self.assertEqual(report['callout_targets'][0]['backing_width_pt'], 5)

    def test_crossed_geometry_matches_map_only_and_source_stays_unchanged(self):
        source = scene()
        before = copy.deepcopy(source)
        _, _, labeled = render(source)
        self.assertEqual(source, before)
        _, _, plain = render(w.apply_output_mode(source, 'map-only'))
        def geometry(nodes):
            return [(n.get('data-element'), n.get('d'), n.get('stroke-width')) for n in nodes
                    if n.get('data-role') in ('roof', 'equipment', 'road-edge', 'road-dashed')]
        self.assertEqual(geometry(labeled), geometry(plain))
        self.assertFalse(any(n.get('data-role') in ('leader', 'leader-underlay') for n in plain))
        ridge = next(n for n in labeled if n.get('data-element') == 'ridge')
        self.assertEqual(ridge.get('d'), 'M120 40 L120 180')

    def test_gap_is_visible_over_roof_road_and_another_leader(self):
        svg, _, _ = render()
        img = raster(svg)
        def white(x, y):
            return min(img.getpixel((round(x*4), round(y*4)))) > 245
        for x in (120, 180):
            self.assertTrue(white(x, 101.5), (x, 'crossing gap'))
            self.assertFalse(white(x, 105), (x, 'preserved crossed line'))
        self.assertTrue(white(151.5, 100), 'later leader has a white bridge')
        self.assertFalse(white(155, 100), 'earlier leader continues beyond bridge')
        self.assertFalse(white(150, 100), 'foreground leader remains continuous')

    def test_backing_and_shafts_remain_paired_after_map_translation(self):
        body, box, _ = w.scene_artwork(scene(), MANIFEST)
        svg, _ = w.clean_export(w.svg_wrap('<g transform="translate(20 30)">'+body+'</g>',
                                          w.fitz.Rect(0, 0, 350, 280), physical=True))
        nodes = list(ET.fromstring(svg))
        for i, node in enumerate(nodes):
            if node.get('data-role') == 'leader-underlay':
                self.assertNotIn('transform', node.attrib)
                self.assertEqual(node.get('d'), nodes[i+1].get('d'))

    def test_short_terminal_run_still_rejected(self):
        label = {'text': 'METER', 'x': 48, 'y': 54.68, 'anchor': 'end',
                 'side': 'right', 'target': [73, 50], 'via': []}
        obstacles = [([(65, 40), (81, 40), (81, 60), (65, 60)], .75)]
        with self.assertRaisesRegex(ValueError, '6 pt of straight shaft'):
            w.draw_callouts([label], lambda p:p, 'green', w.fitz.Rect(0, 0, 100, 100), [], obstacles)

if __name__=='__main__':unittest.main()
