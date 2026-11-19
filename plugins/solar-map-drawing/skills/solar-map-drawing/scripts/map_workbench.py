"""Inspect source maps, retain PDF paths, and render a reviewed map scene.

Requires PyMuPDF and Pillow. No API key, web app, template registry, or Chrome.
Page numbers in the CLI are one-based; all geometry uses displayed page points.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import importlib.util
import json
import math
import os
import re
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from PIL import Image, ImageDraw

# Physical points in the final drawing; never multiplied by map fit scale.
ROLES = {"building": 2.0, "roof": 1.0, "wall": 1.0, "solar": 1.25, "solar_field": 1.25, "equipment": 1.5,
         "context": 1.0, "north": 1.5, "leader": 1.0, "feature": 1.0}
OUTPUT_MODES = ('map-only', 'map-labeled', 'finished')


def apply_output_mode(scene, mode=None):
    """Change the deliverable scope without mutating the reviewed source scene."""
    mode = mode if mode is not None else scene.get('output_mode')
    if mode is None:
        return scene  # Keep existing scenes and callers compatible.
    if mode not in OUTPUT_MODES:
        raise ValueError('output_mode must be map-only, map-labeled or finished')
    result = copy.deepcopy(scene)
    result['output_mode'] = mode
    if mode == 'finished' and not result.get('placard'):
        raise ValueError('Finished output needs source-confirmed placard size and warning metadata')
    if result.get('placard'):
        result['placard']['include_chrome'] = mode == 'finished'
    if result.get('north_arrow'):
        result['north_arrow']['include_label'] = mode != 'map-only'
    if mode == 'map-only':
        result['callouts'] = []
        result['labels'] = []
        result.pop('callout_layout', None)
        result['elements'] = [e for e in result.get('elements', []) if e.get('role') != 'leader']
        for road in result.get('roads', []):
            road.pop('label', None)
    return result


def placard_tools():
    global _PLACARD_TOOLS
    if '_PLACARD_TOOLS' not in globals():
        spec=importlib.util.spec_from_file_location('solar_placard_layout',Path(__file__).with_name('placard_layout.py'))
        _PLACARD_TOOLS=importlib.util.module_from_spec(spec);spec.loader.exec_module(_PLACARD_TOOLS)
    return _PLACARD_TOOLS


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def open_source(path):
    doc = fitz.open(path)
    if doc.is_pdf:
        return doc
    pdf = fitz.open(stream=doc.convert_to_pdf(), filetype="pdf")
    doc.close()
    return pdf


def n(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Coordinates must be finite")
    return f"{value:.5f}".rstrip("0").rstrip(".") or "0"


def point(p, matrix):
    p = fitz.Point(p) * matrix
    return [float(p.x), float(p.y)]


def commands_for(path, matrix):
    """Retain curves, quadrilaterals, disconnected subpaths, and closePath."""
    commands, last = [], None
    for item in path["items"]:
        kind = item[0]
        if kind in ("l", "c"):
            pts = [point(p, matrix) for p in item[1:]]
            if last != pts[0]:
                commands.append(["M", *pts[0]])
            commands.append(["L", *pts[1]] if kind == "l" else ["C", *sum(pts[1:], [])])
            last = pts[-1]
        elif kind in ("re", "qu"):
            if kind == "re":
                r = fitz.Rect(item[1])
                corners = [r.tl, r.tr, r.br, r.bl]
                if len(item) > 2 and item[2] < 0:
                    corners.reverse()
            else:
                q = item[1]
                corners = [q.ul, q.ur, q.lr, q.ll]
            pts = [point(p, matrix) for p in corners]
            commands.append(["M", *pts[0]])
            commands.extend([["L", *p] for p in pts[1:]])
            commands.append(["Z"])
            last = None
        else:
            raise ValueError(f"Unsupported PDF path item: {kind}")
    if path.get("closePath") and last is not None:
        commands.append(["Z"])
    return commands


def path_d(commands):
    sizes = {"M": 2, "L": 2, "C": 6, "Z": 0}
    out = []
    for command in commands:
        if not command or command[0] not in sizes or len(command) != sizes[command[0]] + 1:
            raise ValueError(f"Invalid path command: {command}")
        out.append(command[0] + " ".join(n(v) for v in command[1:]))
    return " ".join(out)


def intersects(a, b):
    # Rect.intersects considers zero-height lines empty; compare inclusively.
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def viewport(values):
    if len(values) != 4 or not all(math.isfinite(v) for v in values):
        raise ValueError("Viewport must contain four finite numbers")
    x0, y0, x1, y1 = values
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Viewport must have positive width and height")
    return fitz.Rect(values)


def svg_wrap(body, box, width=1200, physical=False):
    box = viewport(list(box))
    height = width * box.height / box.width
    dimensions = (f'width="{n(box.width)}pt" height="{n(box.height)}pt"' if physical
                  else f'width="{n(width)}" height="{n(height)}"')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" {dimensions} '
            f'viewBox="{n(box.x0)} {n(box.y0)} {n(box.width)} {n(box.height)}">'
            f'<defs><clipPath id="crop"><rect x="{n(box.x0)}" y="{n(box.y0)}" '
            f'width="{n(box.width)}" height="{n(box.height)}"/></clipPath></defs>'
            f'<g clip-path="url(#crop)">{body}</g></svg>')


def svg_png(svg, output, width=1600, alpha=False):
    # MuPDF does not paint SVG markers. Expand a temporary review copy only;
    # the delivered SVG retains the live marker attached to its stroke.
    svg=placard_tools().expand_equipment_markers(svg)
    with fitz.open(stream=svg.encode(), filetype="svg") as doc:
        page = doc[0]
        page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width, width/page.rect.width), alpha=alpha).save(output)


def inspect_source(source, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    index, thumbs = [], []
    with open_source(source) as doc:
        for i, page in enumerate(doc):
            zoom = min(900/page.rect.width, 900/page.rect.height)
            file = output/f"page-{i+1:03d}.png"
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(file)
            index.append({"page": i+1, "bounds": list(page.rect), "rotation": page.rotation,
                          "paths": len(page.get_drawings()), "images": len(page.get_images()),
                          "text": page.get_text()})
            im = Image.open(file).convert("RGB")
            im.thumbnail((340, 380))
            tile = Image.new("RGB", (370, 420), "white")
            tile.paste(im, ((370-im.width)//2, 30))
            ImageDraw.Draw(tile).text((12, 10), f"PAGE {i+1} / {len(doc)}", fill="black")
            thumbs.append(tile)
    # Paginate the index rather than silently ignoring pages of long plan sets.
    for start in range(0, len(thumbs), 12):
        chunk = thumbs[start:start+12]
        sheet = Image.new("RGB", (370*min(3, len(chunk)), 420*math.ceil(len(chunk)/3)), "#dddddd")
        for j, tile in enumerate(chunk):
            sheet.paste(tile, ((j%3)*370, (j//3)*420))
        sheet.save(output/f"contact-{start//12+1:02d}.png")
    write_json(output/"pages.json", index)
    return {"pages": len(index), "output": str(output)}


def extract(source, page_number, clip, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with open_source(source) as doc:
        if not 1 <= page_number <= len(doc):
            raise ValueError("Page number is outside the document")
        page = doc[page_number-1]
        region = viewport(clip) if clip else page.rect
        if not page.rect.contains(region):
            raise ValueError("Crop is outside displayed page bounds")
        paths = []
        for i, path in enumerate(page.get_drawings()):
            box = fitz.Rect(path["rect"]) * page.rotation_matrix
            if not intersects(list(box), list(region)):
                continue
            paths.append({"id": f"D{i+1:05d}", "bbox": list(box),
                          "commands": commands_for(path, page.rotation_matrix),
                          "stroke": path.get("color"), "fill": path.get("fill"),
                          "width": path.get("width"), "dashes": path.get("dashes"),
                          "even_odd": path.get("even_odd", False),
                          "type": path.get("type"),
                          "crosses_crop": not region.contains(box)})
        texts = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                box = fitz.Rect(line["bbox"]) * page.rotation_matrix
                if intersects(list(box), list(region)):
                    texts.append({"bbox": list(box), "text": "".join(s["text"] for s in line["spans"])})
        zoom = 1800 / max(region.width, region.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=region)
        pix.save(output/"source.png")
        # Keep a job movable between chat sessions and machines. Legacy absolute
        # manifests remain readable; new jobs resolve the PDF beside the manifest.
        try:
            source_reference = Path(os.path.relpath(Path(source).resolve(), output.resolve())).as_posix()
        except ValueError:  # Separate Windows drives cannot have relative paths.
            source_reference = str(Path(source).resolve())
        manifest = {"version": 1, "source": source_reference,
                    "sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                    "page": page_number, "page_bounds": list(page.rect), "page_rotation": page.rotation,
                    "viewport": list(region), "preview_size": [pix.width, pix.height],
                    "paths": paths, "texts": texts,
                    "warnings": ["Path inventory is unclassified; text outlines and annotation paths may be present.",
                                 "PDF clipping, masks, and hidden content require comparison with source.png."]}
        write_json(output/"manifest.json", manifest)
        body = []
        unit = region.width/1000
        for p in paths:
            body.append(f'<path d="{path_d(p["commands"])}" fill="none" stroke="#1476ce" stroke-width="{n(unit)}"/>')
            x, y = p["bbox"][:2]
            body.append(f'<text x="{n(x)}" y="{n(y)}" font-size="{n(5*unit)}" fill="#cf193c">{p["id"]}</text>')
        atlas = svg_wrap("".join(body), region)
        (output/"path-atlas.svg").write_text(atlas, encoding="utf-8")
        svg_png(atlas, output/"path-atlas.png", width=1800)
        return {"paths": len(paths), "texts": len(texts), "output": str(output)}


def element_commands(element):
    kind = element.get("kind", "path")
    if kind == "path":
        return element["commands"]
    if kind in ("polygon", "polyline"):
        pts = element["points"]
        if len(pts) < (3 if kind == "polygon" else 2) or any(len(p) != 2 for p in pts):
            raise ValueError("Too few or malformed points")
        return [["M", *pts[0]], *[["L", *p] for p in pts[1:]], *([["Z"]] if kind == "polygon" else [])]
    raise ValueError(f"Unsupported element kind: {kind}")


def resolve_elements(scene, manifest):
    available = {p["id"]: p for p in manifest["paths"]}
    used, ids, resolved = set(), set(), []
    warnings = list(scene.get("uncertainties", []))
    elements = scene.get("elements", [])
    if not elements:
        raise ValueError("Scene contains no reviewed map elements")
    for el in elements:
        eid, role = el["id"], el["role"]
        if eid in ids:
            raise ValueError(f"Duplicate element id: {eid}")
        ids.add(eid)
        if role not in ROLES:
            raise ValueError(f"Unknown role: {role}")
        commands_list = []
        if "source_ids" in el:
            if not el["source_ids"]:
                raise ValueError(f"Empty source selection: {eid}")
            for sid in el["source_ids"]:
                if sid not in available:
                    raise ValueError(f"Unknown source path: {sid}")
                if sid in used:
                    raise ValueError(f"Source path used twice: {sid}")
                used.add(sid)
                p = available[sid]
                if p["crosses_crop"]:
                    warnings.append(f"{sid} crosses extraction crop; inspect clipping")
                source_dash=re.match(r'\[([^]]*)\]',str(p.get('dashes','')))
                if source_dash and any(float(v)>0 for v in re.findall(r'[-\d.]+',source_dash[1])) and not el.get('dash_pt') and not el.get('dash_conversion_evidence'):
                    warnings.append(f'{eid}: source path {sid} is dashed; preserve its meaning with dash_pt or record dash_conversion_evidence')
                commands_list.append(p["commands"])
        else:
            if not el.get("evidence"):
                raise ValueError(f"Drawn element requires an evidence note: {eid}")
            commands_list.append(element_commands(el))
        for commands in commands_list:
            path_d(commands)  # finite coordinates and command arity
        resolved.append({**el, "paths": commands_list})
    return resolved, used, warnings


def vertices(commands):
    return [(cmd[j], cmd[j+1]) for cmd in commands for j in range(1, len(cmd), 2)]


def bounds(points):
    if not points:
        raise ValueError("No drawable coordinates")
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def line_segments(paths):
    segments = []
    for commands in paths:
        first = previous = None
        for cmd in commands:
            if cmd[0] == "M": first = previous = cmd[1:]
            elif cmd[0] == "L":
                if previous is not None: segments.append((previous, cmd[1:]))
                previous = cmd[1:]
            elif cmd[0] == "Z" and previous is not None and first is not None:
                segments.append((previous, first)); previous = first
            elif cmd[0] == "C": previous = cmd[-2:]
    return [(a,b) for a,b in segments if math.dist(a,b)>1e-6]


def alignment_for(scene, elements):
    """One rigid rotation for the site, selected using only the main outline."""
    align = scene.get("alignment", {})
    if align.get("enabled", True) is False:
        return {"rotation_deg": 0.0, "primary_structure": None}
    groups = {}
    for el in elements:
        if el["role"] == "building":
            groups.setdefault(el.get("structure_id", el["id"]), []).extend(el["paths"])
    if not groups:
        return {"rotation_deg": 0.0, "primary_structure": None}
    def group_area(paths):
        b = bounds([p for commands in paths for p in vertices(commands)])
        return (b[2]-b[0])*(b[3]-b[1])
    primary = align.get("primary_structure") or max(groups, key=lambda key: group_area(groups[key]))
    if primary not in groups:
        raise ValueError(f"Unknown primary structure: {primary}")
    segments = line_segments(groups[primary])
    if not segments:
        raise ValueError("Main structure has no straight edges for alignment")
    # Dominant orthogonal family; select its longest actual edge to make that
    # edge exactly flat. A circular mean alone can leave a small residual tilt.
    angles = [(math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])), math.dist(a,b)) for a,b in segments]
    sx = sum(w*math.cos(math.radians(4*a)) for a,w in angles)
    sy = sum(w*math.sin(math.radians(4*a)) for a,w in angles)
    dominant = math.degrees(math.atan2(sy,sx))/4
    candidates = [(a,w) for a,w in angles if abs((a-dominant+45)%90-45)<10]
    angle = max(candidates or angles, key=lambda pair: pair[1])[0]
    step=float(align.get('orientation_step_deg',45))
    if step not in (45,90):raise ValueError('Main-structure orientation step must be 45 or 90 degrees')
    rotation = -((angle+step/2)%step-step/2)
    if abs(rotation)<1e-8: rotation=0.0
    return {"rotation_deg": rotation, "primary_structure": primary,
            "source_edge_deg": angle, "aligned_edge_deg": angle+rotation,
            "structure_count": len(groups)}


def layout_for(scene, manifest, elements):
    info = alignment_for(scene, elements)
    rad = math.radians(info["rotation_deg"])
    c,s = math.cos(rad),math.sin(rad)
    def rotated(p): return (p[0]*c-p[1]*s, p[0]*s+p[1]*c)
    layout = scene.get("layout")
    if layout:
        box = viewport([0,0,*layout["size_pt"]])
        area = viewport(layout["map_box"])
        if not box.contains(area): raise ValueError("Map box is outside physical canvas")
        pts = [rotated(p) for el in elements if el["role"] not in ("north","leader")
               for commands in el["paths"] for p in vertices(commands)]
        for road in ([] if scene.get('road_layout') else scene.get('roads',[])):
            pts.extend(cardinal_road_points([rotated(p) for p in road.get('points',[])]))
        b = bounds(pts)
        if b[2]==b[0] or b[3]==b[1]: raise ValueError("Map has zero width or height")
        # Reserve half of the largest stroke at every map-box edge.
        pad = max(ROLES.values())/2
        scale = min((area.width-2*pad)/(b[2]-b[0]), (area.height-2*pad)/(b[3]-b[1]))
        if scale <= 0: raise ValueError("Map box is too small")
        tx = (area.x0+area.x1)/2 - scale*(b[0]+b[2])/2
        ty = (area.y0+area.y1)/2 - scale*(b[1]+b[3])/2
    else:
        box = viewport(scene.get("viewport", manifest["viewport"]))
        center = ((box.x0+box.x1)/2,(box.y0+box.y1)/2)
        rc = rotated(center)
        scale,tx,ty = 1.0,center[0]-rc[0],center[1]-rc[1]
    info.update({"scale":scale,"translation":[tx,ty],"canvas_pt":list(box)})
    def transform(p):
        x,y=rotated(p)
        return (x*scale+tx,y*scale+ty)
    return box,transform,info


def transform_commands(commands, transform):
    return [[cmd[0], *[v for j in range(1,len(cmd),2) for v in transform(cmd[j:j+2])]] for cmd in commands]


def closed_polygons(paths, element_id):
    """Split explicit straight closed module outlines; never infer a grid."""
    polygons, points = [], []
    def finish():
        nonlocal points
        if len(points)>1 and math.dist(points[0],points[-1])<1e-6:
            points.pop()
        if len(points)<3:
            raise ValueError(f'{element_id}: solar modules need individual closed outlines for production clearance')
        clean = []
        for p in points:
            if not clean or math.dist(clean[-1],p)>1e-6: clean.append(p)
        polygons.append(clean)
        points=[]
    for path in paths:
        for cmd in path:
            if cmd[0]=='M':
                if points:
                    if len(points)>2 and math.dist(points[0],points[-1])<1e-6: finish()
                    else: raise ValueError(f'{element_id}: split solar grid lines into source-confirmed individual modules')
                points=[tuple(cmd[1:])]
            elif cmd[0]=='L': points.append(tuple(cmd[1:]))
            elif cmd[0]=='Z': finish()
            else: raise ValueError(f'{element_id}: curved solar artwork needs source-confirmed individual module outlines')
        if points:
            if len(points)>2 and math.dist(points[0],points[-1])<1e-6: finish()
            else: raise ValueError(f'{element_id}: split solar grid lines into source-confirmed individual modules')
    return polygons


def cross(a,b):
    return a[0]*b[1]-a[1]*b[0]


def polygon_area(points):
    return sum(cross(a,b) for a,b in zip(points,points[1:]+points[:1]))/2


def inset_polygon(points, inset):
    """Parallel inward offsets of a convex module, in physical output points."""
    orientation=1 if polygon_area(points)>0 else -1
    edges=[]
    for a,b in zip(points,points[1:]+points[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        if length<1e-6: raise ValueError('Degenerate solar outline')
        normal=(-dy/length*orientation,dx/length*orientation)
        if any((p[0]-a[0])*normal[0]+(p[1]-a[1])*normal[1]<-1e-5 for p in points):
            raise ValueError('Solar module outline must be convex; verify individual module boundaries')
        edges.append((a,normal))
    result=list(points)
    offsets=[inset]*len(edges) if isinstance(inset,(int,float)) else inset
    if len(offsets)!=len(edges): raise ValueError('One solar inset is required per edge')
    for (origin,normal),distance in zip(edges,offsets):
        clipped=[]
        for a,b in zip(result,result[1:]+result[:1]):
            da=(a[0]-origin[0])*normal[0]+(a[1]-origin[1])*normal[1]-distance
            db=(b[0]-origin[0])*normal[0]+(b[1]-origin[1])*normal[1]-distance
            if da>=-1e-8: clipped.append(a)
            if (da>0) != (db>0):
                t=da/(da-db)
                clipped.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
        result=clipped
        if len(result)<3: raise ValueError('Solar panel is too small for production clearance; increase the map scale')
    # Reject offset collapse / excessive shrink rather than remove or distort modules.
    if abs(polygon_area(result))<abs(polygon_area(points))*.20:
        raise ValueError('Solar panel would shrink excessively; increase the map scale or review its boundaries')
    for _,normal in edges:
        positions=[p[0]*normal[0]+p[1]*normal[1] for p in result]
        # The 1 pt clearance rule applies to panel/roof edges. Inside a tiny
        # module, require a visible opening without inventing a second 1 pt
        # rule that forces source arrays into an unsolicited enlarged detail.
        if max(positions)-min(positions)<ROLES['solar']+.25:
            raise ValueError('Solar panel is too narrow to keep its own strokes apart; increase the map scale')
    return result


def point_segment_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.dist(p,(a[0]+t*dx,a[1]+t*dy))


def segments_distance(a,b,c,d):
    ab=(b[0]-a[0],b[1]-a[1]); cd=(d[0]-c[0],d[1]-c[1])
    den=cross(ab,cd)
    if abs(den)>1e-10:
        ac=(c[0]-a[0],c[1]-a[1])
        t,u=cross(ac,cd)/den,cross(ac,ab)/den
        if 0<=t<=1 and 0<=u<=1: return 0.0
    return min(point_segment_distance(a,c,d),point_segment_distance(b,c,d),
               point_segment_distance(c,a,b),point_segment_distance(d,a,b))


def inside_polygon(p,polygon):
    orientation=1 if polygon_area(polygon)>0 else -1
    return all(orientation*cross((b[0]-a[0],b[1]-a[1]),(p[0]-a[0],p[1]-a[1]))>=-1e-8
               for a,b in zip(polygon,polygon[1:]+polygon[:1]))


def polygon_segment_distance(polygon,a,b):
    if inside_polygon(a,polygon) or inside_polygon(b,polygon): return 0.0
    return min(segments_distance(c,d,a,b) for c,d in zip(polygon,polygon[1:]+polygon[:1]))


def polygon_distance(a,b):
    if inside_polygon(a[0],b) or inside_polygon(b[0],a): return 0.0
    return min(polygon_segment_distance(a,c,d) for c,d in zip(b,b[1:]+b[:1]))


def clearance_edges(paths):
    """Flatten roof curves for distance checks only, within 0.02 output pt."""
    result=[]
    def curve(a,b,c,d,depth=0):
        if depth>=16 or max(point_segment_distance(b,a,d),point_segment_distance(c,a,d))<.02:
            if math.dist(a,d)>1e-8: result.append((a,d))
            return
        midpoint=lambda p,q:((p[0]+q[0])/2,(p[1]+q[1])/2)
        ab,bc,cd=midpoint(a,b),midpoint(b,c),midpoint(c,d)
        abc,bcd=midpoint(ab,bc),midpoint(bc,cd)
        center=midpoint(abc,bcd)
        curve(a,ab,abc,center,depth+1); curve(center,bcd,cd,d,depth+1)
    for path in paths:
        first=previous=None
        for cmd in path:
            if cmd[0]=='M': first=previous=tuple(cmd[1:])
            elif cmd[0]=='L':
                end=tuple(cmd[1:])
                if previous is not None and math.dist(previous,end)>1e-8: result.append((previous,end))
                previous=end
            elif cmd[0]=='C':
                curve(previous,tuple(cmd[1:3]),tuple(cmd[3:5]),tuple(cmd[5:7]))
                previous=tuple(cmd[5:7])
            elif cmd[0]=='Z':
                if math.dist(previous,first)>1e-8: result.append((previous,first))
                previous=first
    return result


def uniform_rooftop_modules(modules, mapped, roof_edges, gap, equipment_polygons=(), equipment_gap=1):
    """Compact countable arrays around fixed anchors; shrink their joined grids."""
    if not modules:return None
    footprints=[]
    for el in mapped:
        if el['role']=='building':
            try:footprints.extend(closed_polygons(el['paths'],el['id']))
            except ValueError:pass
    for index,m in enumerate(modules):
        el=mapped[m['element']];poly=m['original']
        if len(poly)!=4:raise ValueError('Countable modules need four reviewed corners for rectangular array fitting')
        center=tuple(sum(p[j] for p in poly)/4 for j in (0,1))
        surface=el.get('mount_surface')
        if surface not in (None,'roof','ground'):raise ValueError('Solar mount_surface must be roof or ground')
        edges=[(math.dist(a,b),a,b) for a,b in zip(poly,poly[1:]+poly[:1])]
        longest,a,b=max(edges,key=lambda q:q[0]);axis=tuple((b[j]-a[j])/longest for j in (0,1))
        if axis[0 if abs(axis[0])>=abs(axis[1]) else 1]<0:axis=tuple(-v for v in axis)
        m.update(center=center,axis=axis,short=min(q[0] for q in edges),long=longest,
                 rooftop=surface=='roof' or (surface is None and any(inside_polygon(center,p) for p in footprints)))
        if m['short']<1e-7:raise ValueError('Degenerate module outline; verify the source corners')
        explicit=el.get('array_id')
        if explicit is not None and (not isinstance(explicit,str) or not explicit.strip()):raise ValueError('array_id must be a nonempty source-confirmed identifier')
        m['array_key']=('explicit',explicit) if explicit is not None else ('inferred',index)
    short=statistics.median(m['short'] for m in modules);long=statistics.median(m['long'] for m in modules)
    # Legacy scenes may omit array IDs. Join only clearly adjacent, same-bearing
    # modules, never across a roof/wall, surface, or explicit array identity.
    parents=list(range(len(modules)))
    def find(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for i,m in enumerate(modules):
        if m['array_key'][0]=='explicit':continue
        for j,n in enumerate(modules[:i]):
            if n['array_key'][0]=='explicit' or m['rooftop']!=n['rooftop']:continue
            if mapped[m['element']].get('structure_id')!=mapped[n['element']].get('structure_id'):continue
            if abs(cross(m['axis'],n['axis']))>math.sin(math.radians(3)):continue
            u=m['axis'];v=(-u[1],u[0]);delta=tuple(m['center'][k]-n['center'][k] for k in (0,1))
            dx=abs(sum(delta[k]*u[k] for k in (0,1)));dy=abs(sum(delta[k]*v[k] for k in (0,1)))
            adjacent=(.55*long<=dx<=1.35*long and dy<=.18*short) or (.55*short<=dy<=1.35*short and dx<=.18*long)
            if adjacent and not any(segments_distance(m['center'],n['center'],a,b)<1e-7 for a,b,_ in roof_edges):parents[find(i)]=find(j)
    arrays={}
    for i,m in enumerate(modules):
        if m['array_key'][0]=='inferred':m['array_key']=('inferred',find(i))
        arrays.setdefault(m['array_key'],[]).append(m)
    def inferred_cells(values,dimension):
        levels=[]
        for value in sorted(values):
            if not levels or value-levels[-1][-1]>.18*dimension:levels.append([value])
            else:levels[-1].append(value)
        centers=[statistics.mean(level) for level in levels]
        distances=[b-a for a,b in zip(centers,centers[1:])]
        pitch=min(distances) if distances else dimension
        if distances and not .55*dimension<=pitch<=1.35*dimension:raise ValueError('Ambiguous array spacing; supply reviewed array_id and array_cell metadata')
        indices=[round((value-centers[0])/pitch) for value in values]
        if any(abs(value-(centers[0]+cell*pitch))>.18*dimension for value,cell in zip(values,indices)):
            raise ValueError('Irregular array grid; supply reviewed array_cell metadata rather than guessing missing cells')
        return indices
    groups=[]
    for key,members in arrays.items():
        u=members[0]['axis'];v=(-u[1],u[0])
        if any(abs(cross(u,m['axis']))>math.sin(math.radians(3)) for m in members):raise ValueError('One array mixes panel bearings; split source-confirmed groups before fitting')
        specs=[mapped[m['element']] for m in members]
        spacing=[float(el.get('array_gap_pt',0)) for el in specs]
        if any(not math.isfinite(s) or s<0 for s in spacing) or max(spacing)-min(spacing)>1e-7:raise ValueError('An array needs one nonnegative array_gap_pt value')
        if spacing[0] and not all(el.get('array_spacing_evidence') for el in specs):raise ValueError('Separated panels need explicit array_spacing_evidence')
        if spacing[0] and not all(el.get('array_spacing_authorization')=='user' for el in specs):raise ValueError('Panel rules are locked: separated panels need explicit user authorization, not source artwork or notes')
        cells=[el.get('array_cell') for el in specs]
        if any(cell is not None for cell in cells):
            if not all(isinstance(cell,list) and len(cell)==2 and all(type(n) is int for n in cell) for cell in cells):raise ValueError('Supply an integer array_cell [long_axis_index, short_axis_index] on every individual module in the array')
        else:
            xs=[sum(m['center'][k]*u[k] for k in (0,1)) for m in members];ys=[sum(m['center'][k]*v[k] for k in (0,1)) for m in members]
            cells=list(zip(inferred_cells(xs,long),inferred_cells(ys,short)))
        if len({tuple(cell) for cell in cells})!=len(cells):raise ValueError('Duplicate/ambiguous array cells; verify module count and assign source-confirmed grid cells')
        if not spacing[0]:
            occupied={tuple(cell) for cell in cells};pending=[next(iter(occupied))];connected=set(pending)
            while pending:
                x,y=pending.pop()
                for neighbor in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                    if neighbor in occupied and neighbor not in connected:connected.add(neighbor);pending.append(neighbor)
            if connected!=occupied:raise ValueError('Array cells must connect edge-to-edge; split separate source groups without filling missing cells')
        anchor=tuple(statistics.mean(m['center'][k] for m in members) for k in (0,1))
        mean_cell=tuple(statistics.mean(cell[k] for cell in cells) for k in (0,1))
        for m,cell in zip(members,cells):m['cell']=tuple(cell)
        groups.append({'key':key,'members':members,'axis':u,'normal':v,'anchor':anchor,'mean_cell':mean_cell,'spacing':spacing[0]})
    def polygons(scale):
        result={}
        for group in groups:
            u,v=group['axis'],group['normal'];extra=ROLES['solar']+group['spacing'] if group['spacing'] else 0
            for m in group['members']:
                x=(m['cell'][0]-group['mean_cell'][0])*(long*scale+extra)
                y=(m['cell'][1]-group['mean_cell'][1])*(short*scale+extra)
                c=tuple(group['anchor'][k]+u[k]*x+v[k]*y for k in (0,1))
                result[id(m)]=[(c[0]+u[0]*a+v[0]*b,c[1]+u[1]*a+v[1]*b)
                               for a,b in ((-long*scale/2,-short*scale/2),(long*scale/2,-short*scale/2),(long*scale/2,short*scale/2),(-long*scale/2,short*scale/2))]
        return [result[id(m)] for m in modules]
    def interiors_overlap(a,b):
        for poly in (a,b):
            for c,d in zip(poly,poly[1:]+poly[:1]):
                n=(-(d[1]-c[1]),d[0]-c[0]);pa=[sum(p[k]*n[k] for k in (0,1)) for p in a];pb=[sum(p[k]*n[k] for k in (0,1)) for p in b]
                if min(max(pa),max(pb))-max(min(pa),min(pb))<=1e-7:return False
        return True
    def valid(polys):
        for i,p in enumerate(polys):
            if any(polygon_segment_distance(p,a,b)<gap+ROLES['solar']/2+r-1e-7 for a,b,r in roof_edges):return False
            if any(polygon_distance(p,q)<equipment_gap+(ROLES['solar']+ROLES['equipment'])/2-1e-7 for q in equipment_polygons):return False
            bb=bounds(p)
            for j,q in enumerate(polys[:i]):
                if modules[i]['array_key']==modules[j]['array_key']:continue  # Unique grid cells cannot overlap.
                qb=bounds(q)
                if bb[0]>qb[2]+1.5 or qb[0]>bb[2]+1.5 or bb[1]>qb[3]+1.5 or qb[1]>bb[3]+1.5:continue
                distance=polygon_distance(p,q)
                if distance<1e-6 and not interiors_overlap(p,q):continue
                if distance<ROLES['solar']+.25-1e-7:return False
        return True
    low=max((ROLES['solar']+.25)/short,(ROLES['solar']+.25)/long)
    if low>1:raise ValueError('Panels are too small for a visible 1.25 pt outline; increase map scale')
    scale=1.0;polys=polygons(scale)
    if not valid(polys):
        # Interior obstacles can make validity non-monotonic. Search downward,
        # then refine the first valid interval instead of assuming the smallest fits.
        high=1.0;found=False
        for step in range(1,129):
            trial=1-(1-low)*step/128
            if valid(polygons(trial)):scale=trial;found=True;break
            high=trial
        if not found:raise ValueError('Joined panel arrays cannot retain wall/equipment clearances; review array cells/anchor or increase map scale')
        for _ in range(34):
            mid=(scale+high)/2
            if valid(polygons(mid)):scale=mid
            else:high=mid
        polys=polygons(scale)
    for m,p in zip(modules,polys):m['polygon']=p;m['array_fitted']=True
    return {'module_count':len(modules),'rooftop_module_count':sum(m['rooftop'] for m in modules),
            'short_long_size_pt':[short*scale,long*scale],'common_scale':scale,'centers_preserved':False,
            'array_anchors_preserved':True,'stroke_pt':ROLES['solar'],
            'arrays':[{'id':str(g['key'][1]),'grouping':g['key'][0],'module_count':len(g['members']),
                       'anchor_pt':list(g['anchor']),'cells':[list(m['cell']) for m in g['members']],
                       'panel_gap_pt':g['spacing'],'shared_edges_required':not bool(g['spacing'])} for g in groups]}


def production_elements(elements, transform, settings=None):
    """Keep source evidence untouched; fit joined arrays against final obstacles."""
    settings=settings or {}
    gap=float(settings.get('roof_gap_pt',settings.get('panel_gap_pt',1)))
    if not math.isfinite(gap) or gap<1: raise ValueError('Panel/roof/wall visible clearance must be at least 1 pt')
    equipment_gap=float(settings.get('equipment_gap_pt',1))
    if not math.isfinite(equipment_gap) or equipment_gap<1:raise ValueError('Panel/equipment visible clearance must be at least 1 pt')
    mapped=[{**el,'paths':[transform_commands(p,transform) for p in el['paths']]} for el in elements]
    for el in mapped:
        if el['role']=='solar_field' and not el.get('representation_evidence'):
            raise ValueError(f"{el['id']}: solar_field needs representation_evidence confirming schematic rows or array footprints")
    roof_edges=[]
    for el in mapped:
        if el['role'] in ('building','roof','wall'):
            curved=any(c[0]=='C' for p in el['paths'] for c in p)
            roof_edges.extend((a,b,ROLES[el['role']]/2+(.02 if curved else 0)) for a,b in clearance_edges(el['paths']))
    modules=[]
    for ei,el in enumerate(mapped):
        if el['role']!='solar': continue
        for poly in closed_polygons(el['paths'],el['id']):
            modules.append({'element':ei,'original':poly,'inset':[0.0]*len(poly)})
    # Fit against the actual 1.5 pt production rectangles, not customer glyphs.
    equipment_mapped,_=normalize_equipment(mapped,transform)
    equipment_polygons=[poly for el in equipment_mapped if el['role']=='equipment' for poly in closed_polygons(el['paths'],el['id'])]
    rooftop=uniform_rooftop_modules(modules,mapped,roof_edges,gap,equipment_polygons,equipment_gap)
    # Rebuild countable panels from the fitted grids, never per-edge insets.
    for el in mapped:
        if el['role']=='solar': el['paths']=[]
    for m in modules:
        p=m['polygon']
        mapped[m['element']]['paths'].append([['M',*p[0]],*[['L',*v] for v in p[1:]],['Z']])
    for el in mapped:
        if el.get('dash_pt') is not None:
            if el.get('solid') or el['role'] in ('solar','equipment'):
                raise ValueError('Dashes belong on reviewed context/feature boundaries or schematic field rows, not equipment or individual modules')
            el['paths']=[dash_commands(p,el['dash_pt'],el.get('dash_phase_pt',0)) for p in el['paths']]
        if el['role']=='solar_field':
            for a,b in clearance_edges(el['paths']):
                if any(segments_distance(a,b,c,d)<gap+ROLES['solar_field']/2+radius-1e-5
                       for c,d,radius in roof_edges):
                    raise ValueError(f"{el['id']}: schematic array strokes need reviewed roof clearance; do not substitute invented modules")
                if any(polygon_segment_distance(poly,a,b)<equipment_gap+(ROLES['solar_field']+ROLES['equipment'])/2-1e-5 for poly in equipment_polygons):
                    raise ValueError(f"{el['id']}: schematic array strokes need reviewed equipment clearance")
    return mapped, {'gap_pt':gap,'roof_gap_pt':gap,'panel_to_panel_gap_required':False,
                    'module_count':len(modules),'module_insets_pt':[m['inset'] for m in modules],
                    'uniform_rooftop':rooftop,'uniform_modules':rooftop,'equipment_gap_pt':equipment_gap,
                    'schematic_field_elements':sum(el['role']=='solar_field' for el in mapped)}


def dash_commands(commands, pattern, phase=0):
    """Bake physical dash gaps into loose vectors; no masks or phase-reset exports."""
    if not isinstance(pattern,(list,tuple)) or not pattern:
        raise ValueError('dash_pt must be a nonempty list of positive physical lengths')
    pattern=list(map(float,pattern)); phase=float(phase)
    if not all(math.isfinite(v) and v>0 for v in pattern) or not math.isfinite(phase):
        raise ValueError('Invalid physical dash pattern or phase')
    if len(pattern)%2: pattern*=2
    output=[]; previous=first=None; pen=False
    for command in commands:
        if command[0]=='M':
            first=previous=tuple(command[1:]); pen=False; index=0
            offset=phase%sum(pattern)
            while offset>=pattern[index]: offset-=pattern[index]; index=(index+1)%len(pattern)
            remaining=pattern[index]-offset
            continue
        if command[0] not in ('L','Z'):
            raise ValueError('Curved dashed boundaries need reviewed straight trace segments')
        end=first if command[0]=='Z' else tuple(command[1:])
        length=math.dist(previous,end); progress=0.0
        if length<1e-9: continue
        while progress<length-1e-9:
            step=min(remaining,length-progress)
            a=tuple(previous[j]+(end[j]-previous[j])*progress/length for j in (0,1))
            b=tuple(previous[j]+(end[j]-previous[j])*(progress+step)/length for j in (0,1))
            if index%2==0:
                if not pen: output.append(['M',*a])
                output.append(['L',*b]); pen=True
            else: pen=False
            remaining-=step; progress+=step
            if remaining<1e-9:
                index=(index+1)%len(pattern); remaining=pattern[index]
                if index%2: pen=False
        previous=end
    return output


def equipment_box_size():
    """Fixed 1.5:1 geometry, 25% wider than the canonical Arrow 2 head."""
    arrow=read_json(Path(__file__).resolve().parents[1]/'assets/leader-arrow-2.json')
    ys=[p[1] for p in vertices(arrow['commands'])]
    head_width=(max(ys)-min(ys))*ROLES['leader']/float(arrow['reference_stroke_pt'])
    if not math.isfinite(head_width) or head_width<=0:raise ValueError('Invalid canonical arrowhead width')
    width=head_width*1.25
    return width,width/1.5


def normalize_equipment(elements, transform):
    """Replace source glyphs with equal arrow-sized 1.5 pt equipment rectangles."""
    if not any(el['role']=='equipment' for el in elements): return elements,[]
    width,depth=equipment_box_size()
    reports=[]
    walls=[]
    for el in elements:
        if el['role'] not in ('building','wall'): continue
        try: polygons=closed_polygons(el['paths'],el['id'])
        except ValueError:
            # Cropped site maps may show only part of a house. Preserve its open
            # outline and require a confirmed segment plus explicit face vector.
            for a,b in line_segments(el['paths']):
                length=math.dist(a,b); u=((b[0]-a[0])/length,(b[1]-a[1])/length)
                walls.append({'structure':el.get('structure_id',el['id']),'a':a,'b':b,'u':u,
                              'inward':None,'polygon':None})
            continue
        for poly in polygons:
            orientation=1 if polygon_area(poly)>0 else -1
            for a,b in zip(poly,poly[1:]+poly[:1]):
                length=math.dist(a,b)
                if length<1e-6: continue
                u=((b[0]-a[0])/length,(b[1]-a[1])/length)
                walls.append({'structure':el.get('structure_id',el['id']),'a':a,'b':b,'u':u,
                              'inward':(-u[1]*orientation,u[0]*orientation),'polygon':poly})
    result=[]
    for el in elements:
        if el['role']!='equipment': result.append(el); continue
        bb=bounds([p for path in el['paths'] for p in vertices(path)])
        original=((bb[0]+bb[2])/2,(bb[1]+bb[3])/2)
        if el.get('mount_side')=='freestanding':
            angle=float(el.get('box_rotation_deg',0))
            if not math.isfinite(angle): raise ValueError('Invalid freestanding equipment rotation')
            rad=math.radians(angle); origin=transform((0,0)); axis=transform((math.cos(rad),math.sin(rad)))
            length=math.dist(origin,axis); u=tuple((axis[j]-origin[j])/length for j in (0,1)); normal=(-u[1],u[0])
            poly=[(original[0]+u[0]*v+normal[0]*d,original[1]+u[1]*v+normal[1]*d)
                  for v,d in ((-width/2,-depth/2),(width/2,-depth/2),(width/2,depth/2),(-width/2,depth/2))]
            result.append({**el,'solid':False,'production_equipment':True,
                           'paths':[[['M',*poly[0]],*[['L',*p] for p in poly[1:]],['Z']]]})
            reports.append({'id':el['id'],'source_output_bounds':bb,'source_output_center':original,
                            'output_center':original,'wall_contact':None,'wall_segment':None,
                            'mount_side':'freestanding','structure':None,'size_pt':[width,depth]})
            continue
        if not walls: raise ValueError(f"{el['id']}: equipment needs a confirmed exterior building wall")
        choices=[wall for wall in walls if not el.get('mount_structure') or wall['structure']==el['mount_structure']]
        if el.get('wall_segment'):
            a,b=[transform(p) for p in el['wall_segment']]
            choices=[wall for wall in choices if point_segment_distance(a,wall['a'],wall['b'])<1e-4
                     and point_segment_distance(b,wall['a'],wall['b'])<1e-4]
        if not choices: raise ValueError(f"{el['id']}: confirmed equipment wall is not on the building perimeter")
        wall=min(choices,key=lambda item:point_segment_distance(original,item['a'],item['b']))
        side=el.get('mount_side')
        inward=wall['inward']
        if inward is None:
            if not el.get('wall_segment') or side not in ('inside','outside') or not el.get('wall_inward'):
                raise ValueError(f"{el['id']}: open perimeter requires wall_segment, mount_side and source-confirmed wall_inward")
            raw=el['wall_inward']
            if len(raw)!=2 or not all(math.isfinite(float(v)) for v in raw): raise ValueError('Invalid wall_inward vector')
            origin=transform((0,0)); end=transform(raw); length=math.dist(origin,end)
            if length<1e-8: raise ValueError('wall_inward must be a nonzero source-coordinate vector')
            inward=tuple((end[j]-origin[j])/length for j in (0,1))
            if abs(sum(inward[j]*wall['u'][j] for j in (0,1)))>1e-5:
                raise ValueError('wall_inward must be perpendicular to the confirmed wall')
        if side is None:
            # Ray crossing works for stepped/concave building footprints too.
            x,y=original; inside=False; poly=wall['polygon']
            for a,b in zip(poly,poly[1:]+poly[:1]):
                if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: inside=not inside
            side='inside' if inside else 'outside'
        if side not in ('inside','outside'): raise ValueError('Equipment mount_side must be inside or outside')
        a,b,u=wall['a'],wall['b'],wall['u']
        length=math.dist(a,b)
        if length<width: raise ValueError(f"{el['id']}: equipment box is too wide for the selected wall segment")
        along=max(width/2,min(length-width/2,(original[0]-a[0])*u[0]+(original[1]-a[1])*u[1]))
        contact=(a[0]+along*u[0],a[1]+along*u[1])
        sign=1 if side=='inside' else -1
        normal=tuple(sign*v for v in inward)
        # The mounting edge is directly on the wall centerline. Its intentional
        # 1.5 pt / 2 pt overlap is the user's sole duplicate-edge exception.
        offset=0.0
        near=(contact[0]+normal[0]*offset,contact[1]+normal[1]*offset)
        poly=[(near[0]+u[0]*v+normal[0]*d,near[1]+u[1]*v+normal[1]*d)
              for v,d in ((-width/2,0),(width/2,0),(width/2,depth),(-width/2,depth))]
        center=(near[0]+normal[0]*depth/2,near[1]+normal[1]*depth/2)
        result.append({**el,'solid':False,'production_equipment':True,
                       'paths':[[['M',*poly[0]],*[['L',*p] for p in poly[1:]],['Z']]]})
        reports.append({'id':el['id'],'source_output_bounds':bb,'source_output_center':original,
                        'output_center':center,'wall_contact':contact,'wall_segment':[a,b],
                        'mount_side':side,'structure':wall['structure'],'size_pt':[width,depth]})
    return result,reports


def layout_callouts(labels, groups=None):
    """Explicit nearby equipment groups share a margin and block-to-block gap."""
    labels=[dict(label) for label in labels]
    members={}
    for i,label in enumerate(labels):
        if label.get('group'): members.setdefault(label['group'],[]).append(i)
    for name,indices in members.items():
        spec=(groups or {}).get(name,{})
        anchor=spec.get('anchor','start')
        if anchor not in ('start','end'): raise ValueError('Callout groups need a start or end margin')
        gap=float(spec.get('gap_pt',6))
        if not math.isfinite(gap) or gap<0: raise ValueError('Invalid callout text gap')
        indices.sort(key=lambda i:labels[i]['y'])
        boxes=[text_box(labels[i])[3] for i in indices]
        margin=float(spec.get('margin_x',min(b[0] for b in boxes) if anchor=='start' else max(b[2] for b in boxes)))
        top=float(spec.get('top',boxes[0][1]))
        for i in indices:
            label=labels[i]
            _,size,_,_=text_box(label)
            label.update(x=margin,y=top+size,anchor=anchor)
            top=text_box(label)[3][3]+gap
    return labels


def square_route(start, via, target, side, allow_45=False, final_axis=None):
    """Insert elbows at odd bearings; never move the target or label."""
    route=[start]
    waypoints=[*via,target]
    for index,end in enumerate(waypoints):
        previous=route[-1]
        dx,dy=end[0]-previous[0],end[1]-previous[1]
        if abs(dx)<1e-7 and abs(dy)<1e-7: continue
        diagonal=allow_45 and abs(abs(dx)-abs(dy))<1e-6
        if abs(dx)>1e-7 and abs(dy)>1e-7 and not diagonal:
            horizontal=side in ('left','right') if len(route)==1 else abs(route[-1][1]-route[-2][1])>1e-7
            if index==len(waypoints)-1 and final_axis:
                horizontal=final_axis=='vertical'
            route.append((end[0],previous[1]) if horizontal else (previous[0],end[1]))
        route.append(tuple(end))
    # Remove forward collinear vertices without deleting intentional reversals.
    clean=[]
    for p in route:
        while len(clean)>1:
            a,b=clean[-2:]; u=(b[0]-a[0],b[1]-a[1]); v=(p[0]-b[0],p[1]-b[1])
            if abs(cross(u,v))<1e-7 and u[0]*v[0]+u[1]*v[1]>=0: clean.pop()
            else: break
        clean.append(p)
    return clean


def clear_commands(commands, voids, padding=0, preserve_edges=()):
    """Trim stroked vectors out of equipment interiors, without white fills.

    Keep untouched primitives exact; subdivide only a Bezier near a cut edge.
    This also works in SVG renderers that ignore clipPath.
    """
    if not voids: return commands
    def inside(p,poly):
        sign=1 if polygon_area(poly)>0 else -1
        return all(sign*cross((b[0]-a[0],b[1]-a[1]),(p[0]-a[0],p[1]-a[1]))/math.dist(a,b)>=-padding-1e-8
                   for a,b in zip(poly,poly[1:]+poly[:1]))
    def intervals(a,b):
        result=[(0.0,1.0)]
        for index,poly in enumerate(voids):
            if index<len(preserve_edges) and preserve_edges[index]:
                c,d=preserve_edges[index]
                if abs(cross((d[0]-c[0],d[1]-c[1]),(a[0]-c[0],a[1]-c[1])))<1e-5*math.dist(c,d) and \
                   abs(cross((d[0]-c[0],d[1]-c[1]),(b[0]-c[0],b[1]-c[1])))<1e-5*math.dist(c,d):
                    continue
            lo,hi=0.0,1.0; sign=1 if polygon_area(poly)>0 else -1
            for c,d in zip(poly,poly[1:]+poly[:1]):
                edge=(d[0]-c[0],d[1]-c[1]); length=math.dist(c,d)
                da=sign*cross(edge,(a[0]-c[0],a[1]-c[1]))/length+padding
                db=sign*cross(edge,(b[0]-c[0],b[1]-c[1]))/length+padding
                if da<0 and db<0: lo,hi=1,0; break
                if (da<0)!=(db<0):
                    t=da/(da-db)
                    if da<0: lo=max(lo,t)
                    else: hi=min(hi,t)
            if lo>hi: continue
            remaining=[]
            for p,q in result:
                if hi<=p or lo>=q: remaining.append((p,q)); continue
                if p<lo: remaining.append((p,lo))
                if hi<q: remaining.append((hi,q))
            result=remaining
        return result
    def line(a,b):
        return [(tuple(a[j]+t*(b[j]-a[j]) for j in (0,1)),
                 ['L',*[a[j]+u*(b[j]-a[j]) for j in (0,1)]])
                for t,u in intervals(a,b) if u-t>1e-8]
    def curve(a,b,c,d,depth=0):
        bb=bounds([a,b,c,d])
        if not any(intersects([bb[0]-padding,bb[1]-padding,bb[2]+padding,bb[3]+padding],bounds(poly)) for poly in voids):
            return [(a,['C',*b,*c,*d])]
        if any(all(inside(p,poly) for p in (a,b,c,d)) for poly in voids): return []
        if depth>=14 or max(point_segment_distance(b,a,d),point_segment_distance(c,a,d))<.02:
            return line(a,d)
        mid=lambda p,q:tuple((p[j]+q[j])/2 for j in (0,1))
        ab,bc,cd=mid(a,b),mid(b,c),mid(c,d)
        abc,bcd=mid(ab,bc),mid(bc,cd); center=mid(abc,bcd)
        return curve(a,ab,abc,center,depth+1)+curve(center,bcd,cd,d,depth+1)
    paths=[]; current=[]
    for cmd in commands:
        if cmd[0]=='M' and current: paths.append(current); current=[]
        current.append(cmd)
    if current: paths.append(current)
    output=[]
    for path in paths:
        pieces=[]; changed=False; first=previous=None
        for cmd in path:
            if cmd[0]=='M': first=previous=tuple(cmd[1:]); continue
            end=first if cmd[0]=='Z' else tuple(cmd[-2:])
            part=curve(previous,tuple(cmd[1:3]),tuple(cmd[3:5]),end) if cmd[0]=='C' else line(previous,end)
            expected=['L',*end] if cmd[0]=='Z' else cmd
            if len(part)!=1 or math.dist(part[0][0],previous)>1e-7 or part[0][1]!=expected: changed=True
            pieces.extend(part); previous=end
        if not changed: output.extend(path); continue
        if path[-1][0]=='Z' and pieces:
            for i in range(len(pieces)):
                if math.dist(pieces[i-1][1][-2:],pieces[i][0])>1e-6:
                    pieces=pieces[i:]+pieces[:i]; break
        end=None
        for start,cmd in pieces:
            if end is None or math.dist(end,start)>1e-6: output.append(['M',*start])
            output.append(cmd); end=cmd[-2:]
    return output


def draw_elements(elements, transform, color, warnings, box, voids=(), mount_edges=()):
    body=[]
    for el in elements:
        role=el["role"]
        content=[]
        for commands in el["paths"]:
            mapped=transform_commands(commands,transform)
            mapped=clear_commands(mapped,voids,ROLES[role]/2,mount_edges if role in ('building','wall') else ())
            if not mapped: continue
            if any(not (box.x0<=x<=box.x1 and box.y0<=y<=box.y1) for x,y in vertices(mapped)):
                warnings.append(f'{el["id"]} has coordinates outside output viewport')
            fill='none' if el.get('production_equipment') else color if el.get("solid",False) else "none"
            content.append(f'<path d="{path_d(mapped)}" fill="{fill}" stroke="{color}" stroke-width="{n(ROLES[role])}" stroke-linejoin="miter" stroke-linecap="butt"/>')
        mount=f' data-mount-side="{el.get("mount_side", "wall")}"' if role=='equipment' else ''
        body.append(f'<g id="{html.escape(el["id"],quote=True)}" data-role="{role}"{mount}>{"".join(content)}</g>')
    return "".join(body)


def text_box(label):
    size=float(label.get("size_pt",13))
    if not math.isfinite(size) or size<8: raise ValueError("Map callout text must be at least 8 pt")
    lines=placard_tools().text_lines(label["text"])
    font=fitz.Font("helv")
    stretch=float(label.get('width_scale',1))
    placard_tools().font_scale(stretch)
    width=max(font.text_length(line,fontsize=size) for line in lines)*stretch
    anchor=label.get("anchor","start")
    if anchor not in ("start","middle","end"): raise ValueError("Invalid label anchor")
    x,y=float(label["x"]),float(label["y"])
    left=x-({"start":0,"middle":0.5,"end":1}[anchor])*width
    return lines,size,anchor,[left,y-size,left+width,y+(len(lines)-1)*size*1.2+size*0.22]


def arrow_obstacles(elements, transform):
    """Output-point edges and cubic control hulls that heads must clear."""
    obstacles = []
    for element in elements:
        radius = ROLES[element["role"]] / 2
        for path in element["paths"]:
            if not path:
                continue
            mapped = transform_commands(path, transform)
            closed = path[-1][0] == "Z" or (len(path) > 2 and path[0][1:] == path[-1][-2:])
            if closed and (element["role"] in ("equipment", "solar") or element.get("solid")):
                # Reserve the enclosure as well as its outline, so even a
                # target at the center of a large symbol gets an exterior tip.
                obstacles.append((vertices(mapped), radius))
                continue
            start = previous = None
            for cmd in mapped:
                if cmd[0] == "M":
                    start = previous = tuple(cmd[1:])
                    continue
                points = [start] if cmd[0] == "Z" else vertices([cmd])
                if previous is not None:
                    obstacles.append(([previous, *points], radius))
                previous = points[-1]
    return obstacles


def arrow_setback(target, ux, uy, gap, depth, half_width, obstacles):
    """Clear the actual triangular head envelope, not an oversized rectangle.

    A rectangle spanning every wing along the full head length falsely blocks
    heads beside sloping walls and crowded symbols, forcing needless reroutes.
    Broad intervals cheaply select obstacles; exact distances decide clearance.
    """
    possible=[]
    for points, radius in obstacles:
        pad = radius + 2
        local = [((target[0]-x)*ux + (target[1]-y)*uy,
                  (y-target[1])*ux - (x-target[0])*uy) for x, y in points]
        if max(y for _,y in local)<-half_width-pad or min(y for _,y in local)>half_width+pad:
            continue
        low=min(x for x,y in local)-depth-pad;high=max(x for x,y in local)+pad
        possible.append((low,high,local,pad))
    for _ in range(4096):
        head=[(gap,0),(gap+depth,half_width),(gap+depth,-half_width)]
        collision=False
        for lo,hi,points,pad in possible:
            if not lo<=gap<=hi:continue
            distance=polygon_segment_distance(head,*points) if len(points)==2 else polygon_distance(head,points)
            if distance<pad-1e-7:collision=True;break
        if not collision:return gap
        gap+=.25
    raise ValueError('Arrowhead has no clear approach; choose another route')


def footprint_contains(point, polygon):
    """Ray crossing, including concave/stepped house footprints."""
    x,y=point; inside=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: inside=not inside
    return inside


def segment_inside_length(a,b,polygon):
    cuts=[0.,1.]; direction=(b[0]-a[0],b[1]-a[1])
    for c,d in zip(polygon,polygon[1:]+polygon[:1]):
        edge=(d[0]-c[0],d[1]-c[1]); den=cross(direction,edge)
        if abs(den)<1e-9: continue
        offset=(c[0]-a[0],c[1]-a[1]); t,u=cross(offset,edge)/den,cross(offset,direction)/den
        if 0<t<1 and 0<=u<=1: cuts.append(t)
    cuts=sorted(set(cuts))
    return math.dist(a,b)*sum(hi-lo for lo,hi in zip(cuts,cuts[1:])
        if footprint_contains(tuple(a[j]+(lo+hi)/2*direction[j] for j in (0,1)),polygon))


def equipment_route_clear(route, target, context, voids, text_boxes):
    """Keep routing outside the house; allow only a local final entry."""
    segments=list(zip(route,route[1:]))
    for i,(a,b) in enumerate(segments):
        if i:
            u=(a[0]-segments[i-1][0][0],a[1]-segments[i-1][0][1]);v=(b[0]-a[0],b[1]-a[1])
            if abs(cross(u,v))<1e-7 and sum(u[j]*v[j] for j in (0,1))<0:return False
        if any(segments_distance(a,b,c,d)<1e-6 for c,d in segments[:max(0,i-1)]):return False
    for poly in voids:
        if any(polygon_segment_distance(poly,a,b)<2.5-1e-6 for a,b in segments): return False
    for bbox in text_boxes:
        poly=[(bbox[0],bbox[1]),(bbox[2],bbox[1]),(bbox[2],bbox[3]),(bbox[0],bbox[3])]
        if any(polygon_segment_distance(poly,a,b)<2.5-1e-6 for a,b in segments): return False
    walls,footprints=context or ([],[])
    for index,(a,b) in enumerate(segments):
        crossings=[]
        for c,d in walls:
            u=(b[0]-a[0],b[1]-a[1]);v=(d[0]-c[0],d[1]-c[1]);den=cross(u,v)
            if abs(den)<1e-9:
                if line_overlap(a,b,c,d): return False
                continue
            ac=(c[0]-a[0],c[1]-a[1]);t,s=cross(ac,v)/den,cross(ac,u)/den
            if -1e-7<=t<=1+1e-7 and -1e-7<=s<=1+1e-7: crossings.append(round(t,6))
        if crossings and (index!=len(segments)-1 or len(set(crossings))>1): return False
        for poly in footprints:
            travel=segment_inside_length(a,b,poly)
            if travel<1e-5: continue
            if index!=len(segments)-1 or not footprint_contains(target,poly): return False
            local_depth=min(point_segment_distance(target,c,d) for c,d in zip(poly,poly[1:]+poly[:1]))
            if travel>local_depth+1e-5: return False
    return True


def draw_callouts(labels, transform, color, box, warnings, obstacles=(), equipment_targets=None, voids=(), array_targets=None, backing_color="#ffffff", routing_context=None):
    leaders,texts,boxes,targets=[],[],[],[]
    head_envelopes=[];shaft_routes=[]
    arrow=read_json(Path(__file__).resolve().parents[1]/"assets/leader-arrow-2.json")
    arrow_scale=ROLES["leader"]/arrow["reference_stroke_pt"]
    shaft_inset=arrow["shaft_stop_before_tip"]*arrow_scale
    head_points=vertices(arrow["commands"])
    head_depth=-min(x for x, _ in head_points)*arrow_scale
    head_half_width=max(abs(y) for _, y in head_points)*arrow_scale
    marker_id='equipment-arrow-2-'+re.sub(r'[^a-zA-Z0-9_-]','',color)
    marker_used=False
    label_boxes=[text_box(label)[3] for label in labels]
    for index,label in enumerate(labels):
        label=dict(label)
        lines,size,anchor,bbox=text_box(label)
        if "target" in label:
            target=transform(label["target"])
            side=label.get("side","right" if target[0]>(bbox[0]+bbox[2])/2 else "left")
            desired="end" if side=="right" else "start" if side=="left" else ("end" if anchor=="end" else "start")
            label["anchor"]=desired
            label["x"]=bbox[2] if desired=="end" else bbox[0]
            lines,size,anchor,bbox=text_box(label)
        if not box.contains(fitz.Rect(bbox)): warnings.append(f"Callout {index+1} is outside canvas")
        for other in boxes:
            if intersects(bbox,other): warnings.append(f"Callout {index+1} overlaps another label")
        boxes.append(bbox)
        if "target" in label:
            target=transform(label["target"])
            if label.get('target_element'):
                if label['target_element'] not in (equipment_targets or {}):
                    raise ValueError('Callout target_element must identify a production equipment rectangle')
                target=equipment_targets[label['target_element']]
            if label.get('array_element'):
                choices=(array_targets or {}).get(label['array_element'])
                if not choices:raise ValueError('Array callout needs a confirmed solar/solar_field element')
                # Countable module centers may move while their array compacts.
                # Keep the original source target as evidence; aim at production.
                if label.get('_array_module_target'):
                    centers=[tuple(sum(p[k] for p in poly)/len(poly) for k in (0,1)) for poly,_ in choices]
                    target=min(centers,key=lambda p:math.dist(p,target))
            side=label.get("side","right" if target[0]>(bbox[0]+bbox[2])/2 else "left")
            if side not in ("left","right","top","bottom"): raise ValueError("Invalid leader side")
            start={"left":(bbox[0]-4,(bbox[1]+bbox[3])/2),"right":(bbox[2]+4,(bbox[1]+bbox[3])/2),
                   "top":((bbox[0]+bbox[2])/2,bbox[1]-4),"bottom":((bbox[0]+bbox[2])/2,bbox[3]+4)}[side]
            via=label.get("via")
            if via is None:
                if "elbow_x" in label: via=[(label["elbow_x"],start[1]),(label["elbow_x"],target[1])]
                elif "elbow_y" in label: via=[(start[0],label["elbow_y"]),(target[0],label["elbow_y"])]
                else: via=[(target[0],start[1])]
            requested_gap=float(label.get("target_gap_pt",3))
            if not math.isfinite(requested_gap): raise ValueError("Invalid arrow gap")
            candidates=[square_route(start,via,target,side,label.get('allow_45',False),axis)
                        for axis in (None,'horizontal','vertical')]
            if label.get('via') is None and 'elbow_x' not in label and 'elbow_y' not in label:
                candidates.append(square_route(start,[(start[0],target[1])],target,side))
            # A flush box can make a wall-parallel head approach too crowded.
            # Try a perpendicular approach before asking for a revised label.
            candidates.extend([square_route(start,[(target[0],start[1])],target,side),
                               square_route(start,[(start[0],target[1])],target,side)])
            if side in ('left','right'):
                # A side-attached label needs a visible horizontal tail. Do not
                # let an almost aligned target collapse it to a vertical line
                # beside the last letter, as in the user's rejected example.
                direction=-1 if side=='left' else 1
                candidates=[route for route in candidates if len(route)>1
                            and abs(route[1][1]-start[1])<1e-6
                            and direction*(route[1][0]-start[0])>=6-1e-6]
                tail=(start[0]+direction*6,start[1])
                middle=(start[1]+target[1])/2
                candidates.append([start,tail,(tail[0],middle),(target[0],middle),target])
            if label.get('target_element'):
                # Old via points are hints, not a reason to retain a detour.
                # Try zero/one bends first, then only necessary extra bends.
                if side in ('left','right'):
                    for x in ((start[0]+target[0])/2,start[0]+(-6 if side=='left' else 6)):
                        if (x-start[0])*(-1 if side=='left' else 1)>=6-1e-6:
                            candidates.append(square_route(start,[(x,start[1]),(x,target[1])],target,side))
                else:
                    for y in ((start[1]+target[1])/2,start[1]+(-6 if side=='top' else 6)):
                        if (y-start[1])*(-1 if side=='top' else 1)>=6-1e-6:
                            candidates.append(square_route(start,[(start[0],y),(target[0],y)],target,side))
                unique={tuple(map(tuple,route)):route for route in candidates}
                candidates=sorted(unique.values(),key=lambda route:(len(route),sum(math.dist(a,b) for a,b in zip(route,route[1:]))))
            valid=False
            for route in candidates:
                if len(route)<2: continue
                prev=route[-2]; length=math.dist(prev,target)
                if length<1e-7:continue
                ux,uy=(target[0]-prev[0])/length,(target[1]-prev[1])/length
                if any(math.dist(a,b)<4-1e-6 for a,b in zip(route[1:-2],route[2:-1])):continue
                # Try a bounded stagger along the same target bearing when
                # closely spaced devices would otherwise merge arrowheads.
                for extra in (0,3,6,head_depth+2,12,2*(head_depth+2)):
                    base_gap=max(3,requested_gap)+extra
                    gap=arrow_setback(target,ux,uy,base_gap,head_depth,head_half_width,obstacles)
                    if label.get('target_element'):
                        own=[(poly,ROLES['equipment']/2) for poly in voids if inside_polygon(target,poly)]
                        expected=arrow_setback(target,ux,uy,base_gap,head_depth,head_half_width,own)
                        if gap>expected+.1:continue
                    if label.get('array_element'):
                        if label['array_element'] not in (array_targets or {}):raise ValueError('Array callout needs a confirmed solar/solar_field element')
                        expected=arrow_setback(target,ux,uy,base_gap,head_depth,head_half_width,array_targets[label['array_element']])
                        if gap>expected+.1:continue
                    # Keep a full 6 pt of visible straight shaft behind the
                    # rearmost wing; never put an elbow inside the head.
                    if length-gap<head_depth+6-1e-6:continue
                    tip=(target[0]-gap*ux,target[1]-gap*uy)
                    envelope=[tip,
                              (tip[0]-head_depth*ux-head_half_width*uy,tip[1]-head_depth*uy+head_half_width*ux),
                              (tip[0]-head_depth*ux+head_half_width*uy,tip[1]-head_depth*uy-head_half_width*ux)]
                    proposed=[*route[:-1],(tip[0]-shaft_inset*ux,tip[1]-shaft_inset*uy)]
                    if label.get('target_element') and not equipment_route_clear(proposed,target,routing_context,voids,label_boxes):continue
                    if any(polygon_distance(envelope,other)<2-1e-6 for other in head_envelopes):continue
                    if any(polygon_segment_distance(envelope,a,b)<max(2+ROLES['leader']/2,2.5)-1e-6
                           for prior in shaft_routes for a,b in zip(prior,prior[1:])):continue
                    if any(polygon_segment_distance(other,a,b)<max(2+ROLES['leader']/2,2.5)-1e-6
                           for other in head_envelopes for a,b in zip(proposed,proposed[1:])):continue
                    valid=True;break
                if valid:break
            if not valid:
                if label.get('target_element'):
                    raise ValueError(f'Move the equipment label {" ".join(lines)} closer to its device/on the same side of the house, then reroute: use only necessary bends, a continuous stroke, 6 pt of straight shaft behind the head and 2 pt head clearance')
                raise ValueError(f'Extend the final leader segment or reroute {" ".join(lines)}: leave 6 pt of straight shaft behind the head, 2 pt between heads and other leaders, and no short jogs')
            tip=(target[0]-gap*ux,target[1]-gap*uy)
            route[-1]=tip
            # Stop the shaft inside the filled head: a stroke to the tip makes
            # a blunt nib protrude past the pointed Arrow 2 silhouette.
            route[-1]=(tip[0]-shaft_inset*ux,tip[1]-shaft_inset*uy)
            shaft_commands=[["M",*route[0]],*[["L",*p] for p in route[1:]]]
            d=path_d(shaft_commands if label.get('target_element') else clear_commands(shaft_commands,voids,ROLES['leader']/2))
            # Keep the crossed artwork intact. Each white/colored pair is
            # painted together so later leaders also bridge earlier leaders.
            leaders.append(f'<path data-role="leader-underlay" d="{d}" fill="none" stroke="{backing_color}" stroke-width="5" stroke-linecap="butt" stroke-linejoin="round"/>')
            attached=f' marker-end="url(#{marker_id})" data-equipment-leader="true"' if label.get('target_element') else ''
            leaders.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{n(ROLES["leader"])}" stroke-linecap="butt"{attached}/>')
            def head_transform(p):
                return (tip[0]+arrow_scale*(p[0]*ux-p[1]*uy),
                        tip[1]+arrow_scale*(p[0]*uy+p[1]*ux))
            head=transform_commands(arrow["commands"],head_transform)
            head_envelopes.append(envelope);shaft_routes.append(list(route))
            if label.get('target_element'):marker_used=True
            else:leaders.append(f'<path data-arrowhead="Illustrator Arrow 2" d="{path_d(head)}" fill="{color}"/>')
            targets.append({"text":lines,"source_target":label["target"],"output_target":target,"arrow_tip":tip,"setback_pt":gap,
                            "shaft_route":route,"text_bbox":bbox,"attachment_side":side,
                            "target_element":label.get('target_element'),'clearance':True,'backing_width_pt':5,'backing_color':backing_color,
                            'head_envelope':envelope,'visible_straight_shaft_pt':length-gap-head_depth})
        records=[placard_tools().text_record(line,label["x"],label["y"]+i*size*1.2,size,
                  anchor,float(label.get('width_scale',1)),role='callout-text') for i,line in enumerate(lines)]
        texts.append(placard_tools().text_svg(records,color))
    marker=''
    if marker_used:
        marker=('<defs><marker id="'+marker_id+'" data-arrowhead="Illustrator Arrow 2" '
                'markerUnits="userSpaceOnUse" orient="auto" refX="'+n(-shaft_inset)+'" refY="0" '
                'viewBox="-12 -6 14 12" markerWidth="14" markerHeight="12" overflow="visible">'
                '<path d="'+path_d(transform_commands(arrow['commands'],lambda p:(p[0]*arrow_scale,p[1]*arrow_scale)))+'" fill="'+color+'"/></marker></defs>')
    return marker+'<g id="callout-leaders">'+"".join(leaders)+'</g><g id="callout-text">'+"".join(texts)+'</g>', targets


def north_direction(north, applied_rotation):
    """Compensate bearing, then apply the user's bounded cosmetic snapping."""
    if "source_rotation_deg" not in north:
        raise ValueError("North direction must be supplied from source")
    raw=float(north["source_rotation_deg"])+applied_rotation
    tolerance=float(north.get("snap_tolerance_deg",10))
    if not math.isfinite(raw) or not math.isfinite(tolerance) or not 0<=tolerance<=10:
        raise ValueError("North snap tolerance must be between 0 and 10 degrees")
    nearest=45*math.floor(raw/45+.5)
    shown=nearest if abs(nearest-raw)<=tolerance+1e-8 else raw
    mode="snapped" if shown!=raw else "compensated"
    if "display_rotation_deg" in north:
        if not north.get("display_rotation_evidence"):
            raise ValueError("North display override requires user/source evidence")
        shown=float(north["display_rotation_deg"])
        if not math.isfinite(shown): raise ValueError("Invalid north display rotation")
        mode="explicit_override"
    return {"compensated_deg":raw,"display_deg":shown,"snap_tolerance_deg":tolerance,"mode":mode}


def draw_north(north, applied_rotation, color):
    if north is None: return "",None
    asset=read_json(Path(__file__).resolve().parents[1]/"assets/north-arrow.json")
    legacy_height=float(north.get("height_pt",34))
    if not math.isfinite(legacy_height) or legacy_height<=0: raise ValueError("Invalid north symbol height")
    stroke=float(north.get("stroke_pt",2 if legacy_height<28 else 3))
    if stroke not in (2,3): raise ValueError("North Arrow 15 requires a 2 pt or 3 pt reference stroke")
    scale=stroke/asset["reference_stroke_pt"]
    height=asset["height"]*scale
    angle=north_direction(north,applied_rotation)["display_deg"]
    rad=math.radians(angle); c,s=math.cos(rad),math.sin(rad)
    x,y=north["x"],north["y"]
    def transform(p): return (x+scale*(p[0]*c-p[1]*s),y+scale*(p[0]*s+p[1]*c))
    commands=transform_commands(asset["commands"],transform)
    needle=f'<path data-arrowhead="Illustrator Arrow 15" data-reference-stroke-pt="{n(stroke)}" d="{path_d(commands)}" fill="{color}" fill-rule="evenodd"/>'
    # Orbit the glyph center with the needle, but keep the letter upright.
    # Preserve the existing north-up baseline and spacing at every bearing.
    size=float(north.get("label_size_pt",18 if stroke==2 else 25))
    if size not in (18,25): raise ValueError("North N must be 18 pt or 25 pt")
    cap_height=fitz.Font("helv").glyph_bbox(ord("N")).height*size
    orbit=height+size+4-cap_height/2
    label_x=x-orbit*s
    label_y=y+orbit*c+cap_height/2
    letter=f'<text x="{n(label_x)}" y="{n(label_y)}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="{n(size)}" fill="{color}">N</text>'
    return f'<g id="north-arrow" data-rotation-deg="{n(angle)}">{needle}{letter if north.get("include_label",True) else ""}</g>', angle


def scene_artwork(scene, manifest):
    scene=apply_output_mode(scene)
    scene,zone_plan=placard_tools().prepare_scene(scene,manifest) if scene.get('placard') else (scene,None)
    elements,used,warnings=resolve_elements(scene,manifest)
    # Source compass artwork is replaced with the fixed house symbol.
    if any(el["role"]=="north" for el in elements):
        raise ValueError("Use north_arrow with source_rotation_deg; do not reuse customer compass artwork")
    box,transform,alignment=layout_for(scene,manifest,elements)
    style=placard_tools().production_style(scene.get("production"))
    color=style["ink"]
    production,clearances=production_elements(elements,transform,scene.get('production'))
    production,equipment=normalize_equipment(production,transform)
    voids=[vertices(path)[:-1] if path[-1][0]!='Z' and path[-1][-2:]==path[0][1:] else vertices(path)
           for e in production if e['role']=='equipment' for path in e['paths']]
    callouts=layout_callouts(scene.get("callouts",[]),scene.get('callout_layout'))
    for label in callouts:
        if label.get('array_element'):
            label['_array_module_target']=any(e['id']==label['array_element'] and e['role']=='solar' for e in production)
        if 'target' in label and not label.get('target_element'):
            target=transform(label['target'])
            matches=[item['id'] for item in equipment
                     if item['source_output_bounds'][0]-1e-5<=target[0]<=item['source_output_bounds'][2]+1e-5
                     and item['source_output_bounds'][1]-1e-5<=target[1]<=item['source_output_bounds'][3]+1e-5]
            if len(matches)==1: label['target_element']=matches[0]
            elif len(matches)>1: raise ValueError('Ambiguous equipment callout; supply target_element explicitly')
    obstacles=arrow_obstacles(production,lambda p:p) if callouts else ()
    routing_walls=[];routing_footprints=[]
    for element in production:
        if element['role'] not in ('building','wall'):continue
        routing_walls.extend(clearance_edges(element['paths']))
        if element['role']=='building':
            for path in element['paths']:
                try:routing_footprints.extend(closed_polygons([path],element['id']))
                except ValueError:pass  # Open/cropped outlines still provide wall crossings.
    callout_svg,targets=draw_callouts(callouts,transform,color,box,warnings,obstacles,
                                    {item['id']:item['output_center'] for item in equipment},voids,
                                    {e['id']:[(poly,ROLES[e['role']]/2) for poly in closed_polygons(e['paths'],e['id'])]
                                     for e in production if e['role'] in ('solar','solar_field') and any(c.get('array_element')==e['id'] for c in callouts)},style['backing'],(routing_walls,routing_footprints))
    # Only equipment interiors trim source strokes. Leader crossing gaps use
    # editable white backing, preserving the source roof/perimeter geometry.
    body=[draw_elements([e for e in production if e['role']!='equipment'],lambda p:p,color,warnings,box,
                        voids,[item['wall_segment'] for item in equipment if item['wall_segment']])]
    # Draw only the 1.5 pt unfilled rectangle outlines over the cleared artwork.
    body.append(draw_elements([e for e in production if e['role']=='equipment'],lambda p:p,color,warnings,box))
    north_svg,north_angle=draw_north(scene.get("north_arrow"),alignment["rotation_deg"],color)
    body.append(north_svg)
    body.append(draw_roads(scene.get('roads',[]),transform,color,scene.get('road_layout'),box))
    # Paint leaders above every map line, including road edges.
    body.append(callout_svg)
    # Plain labels without leaders use final output point coordinates.
    for label in scene.get("labels", []):
        size = float(label.get("size_pt", 13))
        if not math.isfinite(size) or size < 8 or not label.get("text"):
            raise ValueError("Map labels need nonempty text and at least 8 pt size")
        lines = placard_tools().text_lines(label["text"])
        anchor = label.get("anchor", "middle")
        if anchor not in ("start", "middle", "end"):
            raise ValueError("Invalid label anchor")
        records=[placard_tools().text_record(line,label["x"],label["y"]+i*size*1.2,size,
                  anchor,float(label.get('width_scale',1)),role='map-label') for i,line in enumerate(lines)]
        body.append(placard_tools().text_svg(records,color))
    zone_check=None
    if zone_plan:
        zone_check=placard_tools().validate_map_svg(''.join(body),box,zone_plan)
        body.append(placard_tools().chrome_svg(zone_plan,color))
    counts={role:sum(el["role"]==role for el in elements) for role in ROLES if any(el["role"]==role for el in elements)}
    report = {"status": "needs_visual_review", "output_mode":scene.get('output_mode'), "elements_by_role": counts,
              "alignment":alignment, "stroke_widths_pt":ROLES,
              "panel_clearance":clearances,
              "equipment_rectangles":equipment,
              "placard_layout":zone_plan,"zone_check":zone_check,
              "north_rotation_deg":north_angle,
              "north_direction":north_direction(scene["north_arrow"],alignment["rotation_deg"]) if scene.get("north_arrow") else None,
              "callout_targets":targets,
              "selected_source_paths": len(used), "unselected_source_paths": len(manifest["paths"])-len(used),
              "warnings": sorted(set(warnings)),
              "checks": ["building count, outline topology, relative placement", "roof junctions and open/closed edges",
                         "panel count, layout, rotation, roof clearance", "equipment position and north direction",
                         "labels, omitted details, crop boundaries"]}
    if style["process"]=="label":
        body.insert(0,f'<path data-role="background" d="M{n(box.x0)} {n(box.y0)} L{n(box.x1)} {n(box.y0)} L{n(box.x1)} {n(box.y1)} L{n(box.x0)} {n(box.y1)} Z" fill="{style["background"]}"/>')
    report["production_style"]=style
    report["production_handoff"]="Verify native Illustrator layers/swatches and any print-template bleed before production"
    return f'<g data-production-process="{style["process"]}" data-production-layer="{style["layer"]}" data-production-ink="{color}">'+"".join(body)+"</g>", box, report


def cardinal_road_points(points):
    """Nearest cardinal street direction, retaining its center and length."""
    if len(points)!=2:raise ValueError('Straight road needs two source points')
    a,b=points;dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    if length<1e-6:raise ValueError('Road has zero length')
    u=(1 if dx>=0 else -1,0) if abs(dx)>=abs(dy) else (0,1 if dy>=0 else -1)
    center=tuple((a[j]+b[j])/2 for j in (0,1))
    return [tuple(center[j]+sign*length*u[j]/2 for j in (0,1)) for sign in (-1,1)]


def draw_road(road,transform,color):
    """Cardinal solid/dashed street on the source-confirmed side of the site."""
    if not road.get('evidence') or not road.get('source_side'):
        raise ValueError('Road needs source side/location evidence')
    points=road.get('points',[])
    if len(points)!=2:raise ValueError('Straight road helper requires two points; trace source bends/curves explicitly')
    a,b=cardinal_road_points(list(map(transform,points)));length=math.dist(a,b)
    if length<1e-6:raise ValueError('Road has zero length')
    offset=float(road['outer_offset_pt'])
    if not math.isfinite(offset) or abs(offset)<10:raise ValueError('Road lane needs a reviewed offset of at least 10 pt')
    normal=(-(b[1]-a[1])/length,(b[0]-a[0])/length)
    c=tuple(a[j]+normal[j]*offset for j in (0,1));d=tuple(b[j]+normal[j]*offset for j in (0,1))
    return road_edge_artwork(road,a,b,c,d,color,road.get('dash_pt',[20,24]))


def road_edge_artwork(road,a,b,c,d,color,dash,label_center=None):
    """Editable solid/dashed edges and parallel lettering for one street."""
    paths=[f'<path data-role="road-edge" d="M{n(a[0])} {n(a[1])} L{n(b[0])} {n(b[1])}" fill="none" stroke="{color}" stroke-width="1"/>']
    dashed=dash_commands([['M',*c],['L',*d]],dash,0)
    paths.append(f'<path data-role="road-dashed" d="{path_d(dashed)}" fill="none" stroke="{color}" stroke-width="1"/>')
    label=road.get('label')
    if label:
        side=road.get("layout_side")
        if side not in ("left","right","top","bottom"):
            # The dashed outer edge identifies the outward side for legacy roads.
            side=("left" if c[0]<a[0] else "right") if abs(a[0]-b[0])<1e-6 else ("top" if c[1]<a[1] else "bottom")
        angle={"left":-math.pi/2,"right":math.pi/2,"top":0,"bottom":0}[side]
        size=float(label.get('size_pt',8))
        if not math.isfinite(size) or size<8:raise ValueError('Street names must be at least 8 pt')
        co,si=math.cos(angle),math.sin(angle)
        # Keep lettering centered in the normalized street lane, parallel to its
        # cardinal direction. Old source-angle label coordinates are not reused.
        mid=label_center or tuple((a[j]+b[j]+c[j]+d[j])/4 for j in (0,1))
        x,y=mid[0]-si*size*.39,mid[1]+co*size*.39
        paths.append(f'<text x="0" y="0" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="{n(size)}" fill="{color}" transform="matrix({n(co)} {n(si)} {n(-si)} {n(co)} {n(x)} {n(y)})">{html.escape(label["text"])}</text>')
    return ''.join(paths)


def draw_roads(roads,transform,color,layout=None,canvas=None):
    """Frame the reviewed drawing area on its source-confirmed road sides."""
    if not layout:
        return ''.join(draw_road(road,transform,color) for road in roads)
    if not roads:return ''
    raw=layout.get('drawing_area',[])
    if len(raw)!=4 or not all(math.isfinite(float(v)) for v in raw):
        raise ValueError('road_layout needs a finite drawing_area in output points')
    area=fitz.Rect(*map(float,raw))
    if area.width<=0 or area.height<=0 or (canvas is not None and not canvas.contains(area)):
        raise ValueError('Road drawing_area must fit inside the output canvas')
    ratio=float(layout.get('lane_width_ratio',.065))
    if not math.isfinite(ratio) or ratio<=0:
        raise ValueError('Road lane_width_ratio must be positive')
    # Keep the full stroke envelope within the declared drawing area.
    half=1/2
    left,top,right,bottom=area.x0+half,area.y0+half,area.x1-half,area.y1-half
    span=min(area.width,area.height)
    lane=max(10,span*ratio)
    if 2*lane>=min(right-left,bottom-top):
        raise ValueError('Road lanes leave no usable drawing area')
    sides={}
    for road in roads:
        if not road.get('evidence') or not road.get('source_side'):
            raise ValueError('Road needs source side/location evidence')
        side=road.get('layout_side')
        if side not in ('left','right','top','bottom'):
            raise ValueError('Full-span road needs a confirmed final layout_side')
        if side in sides:
            raise ValueError('Multiple streets on one side need an explicitly reviewed layout')
        sides[side]=road
    inner_left=left+lane if 'left' in sides else left
    inner_right=right-lane if 'right' in sides else right
    inner_top=top+lane if 'top' in sides else top
    inner_bottom=bottom-lane if 'bottom' in sides else bottom
    paths={
        'left':((inner_left,inner_top),(inner_left,inner_bottom),(left,top),(left,bottom)),
        'right':((inner_right,inner_top),(inner_right,inner_bottom),(right,top),(right,bottom)),
        'top':((inner_left,inner_top),(inner_right,inner_top),(left,top),(right,top)),
        'bottom':((inner_left,inner_bottom),(inner_right,inner_bottom),(left,bottom),(right,bottom))}
    dash=[20,24]
    result=[]
    for side,road in sides.items():
        a,b,c,d=paths[side]
        if road.get('label'):
            label=road['label'];size=float(label.get('size_pt',8))
            if not math.isfinite(size) or size<8 or size+2>lane:
                raise ValueError('Street name needs readable type and enough lane width')
            if fitz.get_text_length(label['text'],fontsize=size)>math.dist(a,b)-4:
                raise ValueError('Street name exceeds its lane length; review the road layout')
        # Keep the street name within its own lane and out of a corner junction.
        if side in ('left','right'):mid=((a[0]+c[0])/2,(a[1]+b[1])/2)
        else:mid=((a[0]+b[0])/2,(a[1]+c[1])/2)
        content=road_edge_artwork(road,a,b,c,d,color,road.get('dash_pt',dash),mid)
        result.append(f'<g data-road-side="{side}">{content}</g>')
    return ''.join(result)


def parse_export_path(data):
    tokens=re.findall(r'[MLCZ]|[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?',data)
    result=[]; i=0; sizes={'M':2,'L':2,'C':6,'Z':0}
    while i<len(tokens):
        command=tokens[i]; i+=1
        if command not in sizes: raise ValueError('Unexpected production SVG path syntax')
        count=sizes[command]
        result.append([command,*map(float,tokens[i:i+count])]); i+=count
    return result


def line_overlap(a,b,c,d):
    length=math.dist(a,b)
    if length<1e-7: return None
    u=((b[0]-a[0])/length,(b[1]-a[1])/length)
    if abs(cross(u,(c[0]-a[0],c[1]-a[1])))>1e-4 or abs(cross(u,(d[0]-a[0],d[1]-a[1])))>1e-4:
        return None
    lo,hi=sorted(((p[0]-a[0])*u[0]+(p[1]-a[1])*u[1] for p in (c,d)))
    lo,hi=max(0,lo),min(length,hi)
    return (lo,hi) if hi-lo>1e-5 else None


def clean_export(svg):
    """Bake translations, flatten objects and remove coincident stroked edges."""
    ns='{http://www.w3.org/2000/svg}'
    ET.register_namespace('',ns[1:-1])
    root=ET.fromstring(svg); leaves=[]; names={}; hidden=0;markers={}
    def walk(node,dx=0,dy=0,metadata=None):
        nonlocal hidden
        tag=node.tag.split('}')[-1]; metadata=dict(metadata or {})
        for key,value in node.attrib.items():
            if key.startswith('data-'): metadata[key]=value
        if tag=='defs':
            for child in node:
                if child.tag.split('}')[-1]!='marker':continue
                if child.get('data-arrowhead')!='Illustrator Arrow 2' or len(child)!=1 or child[0].tag.split('}')[-1]!='path':
                    raise ValueError('Only the canonical attached equipment Arrow 2 marker may be exported')
                identity=child.get('id')
                if not identity:raise ValueError('Equipment arrow marker requires an ID')
                if identity in markers and ET.tostring(markers[identity])!=ET.tostring(child):
                    raise ValueError('Conflicting equipment arrow marker IDs')
                markers[identity]=child
            return
        if tag in ('clipPath','mask','title','desc','metadata'): return
        if tag=='g':
            identity=node.get('id','')
            if identity: metadata['data-element']=identity
            if identity.startswith('item-') and identity.count('-')==1: metadata['data-map']=identity
            if identity.endswith('callout-leaders'): metadata['data-role']='leader'
        text_scale=1.0;text_tx=text_ty=0.0;text_matrix=None
        if node.get('transform'):
            match=re.fullmatch(r'translate\(([-\d.eE]+)[ ,]+([-\d.eE]+)\)',node.get('transform'))
            if match:dx+=float(match[1]);dy+=float(match[2])
            else:
                matrix=re.fullmatch(r'matrix\(([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)\)',node.get('transform'))
                if tag!='text' or not matrix:raise ValueError('Only text may retain rotation or type condensation; map geometry must be baked')
                a,b,c,d,e,f=map(float,matrix.groups())
                if not all(math.isfinite(v) for v in (a,b,c,d,e,f)) or a*d-b*c<=0 or abs(math.hypot(c,d)-1)>1e-5 or abs(a*c+b*d)>1e-5:
                    raise ValueError('Text matrix must preserve type height and contain no skew')
                if abs(b)<1e-8 and abs(c)<1e-8 and abs(d-1)<1e-8:
                    text_scale=a;text_tx=e;text_ty=f
                else:text_matrix=[a,b,c,d,e+dx,f+dy]
        if tag in ('svg','g'):
            for child in node: walk(child,dx,dy,metadata)
            return
        if tag not in ('path','text'): raise ValueError(f'Unexpected production SVG object: {tag}')
        attrs={**metadata,**node.attrib}
        for key in ('transform','clip-path','mask'): attrs.pop(key,None)
        if tag=='path':
            stroke=attrs.get('stroke','none')!='none' and float(attrs.get('stroke-width',1))>0
            fill=attrs.get('fill','black')!='none'
            if not stroke and not fill: hidden+=1; return
            commands=transform_commands(parse_export_path(attrs['d']),lambda p:(p[0]+dx,p[1]+dy))
            attrs['d']=path_d(commands)
        else:
            if text_matrix:
                attrs['transform']='matrix('+ ' '.join(n(v) for v in text_matrix)+')'
            else:
                attrs['x']=n(float(attrs.get('x',0))+(dx+text_tx)/text_scale); attrs['y']=n(float(attrs.get('y',0))+dy+text_ty)
                if text_scale!=1:attrs['transform']=f'matrix({n(text_scale)} 0 0 1 0 0)'
            scale=math.hypot(text_matrix[0],text_matrix[1]) if text_matrix else text_scale
            placard_tools().font_scale(scale)
            size=float(attrs.get('font-size',13))
            if attrs.get('data-role') in ('footer','footer-part'):
                if abs(size-5)>1e-6 or abs(scale-1)>1e-6:raise ValueError('Footer must be 5 pt at 100% horizontal scale')
            elif size<8:raise ValueError('Map and warning text must be at least 8 pt')
            process=attrs.get('data-production-process','laser')
            if process=='laser' and size<=10:
                attrs['fill']='#ed1c24';attrs['data-engraving']='small'
            elif attrs.get('data-production-ink'):
                attrs['fill']=attrs['data-production-ink']
        name=attrs.get('id') or attrs.get('data-element') or tag
        names[name]=names.get(name,0)+1
        attrs['id']=name if names[name]==1 else f'{name}-{names[name]}'
        leaf=ET.Element(ns+tag,attrs); leaf.text=node.text
        if tag=='text':
            for span in node:
                if span.tag.split('}')[-1]!='tspan' or len(span) or set(span.attrib)-{'x','y'}:
                    raise ValueError('Text blocks require flat tspans with line positions only')
                child_attrs=dict(span.attrib)
                if not text_matrix:
                    child_attrs['x']=n(float(span.get('x',node.get('x',0)))+(dx+text_tx)/text_scale)
                    child_attrs['y']=n(float(span.get('y',node.get('y',0)))+dy+text_ty)
                child=ET.SubElement(leaf,ns+'tspan',child_attrs);child.text=span.text;child.tail=span.tail
        leaves.append(leaf)
    walk(root)
    records=[]; by_owner={}; original_paths={}
    for owner,leaf in enumerate(leaves):
        if leaf.tag!=ns+'path' or leaf.get('stroke','none')=='none': continue
        # White backing is intentionally coincident with its own shaft.
        # It must not erase that shaft or source strokes during deduplication.
        if leaf.get('data-role')=='leader-underlay': continue
        commands=parse_export_path(leaf.get('d')); paths=[]; current=[]
        for command in commands:
            if command[0]=='M' and current: paths.append(current); current=[]
            current.append(command)
        if current: paths.append(current)
        original_paths[owner]=paths; by_owner[owner]=[]
        for sub,path in enumerate(paths):
            start=previous=None; primitive=0
            for command in path:
                if command[0]=='M': start=previous=tuple(command[1:]); continue
                end=start if command[0]=='Z' else tuple(command[-2:])
                cmd=['L',*end] if command[0]=='Z' else command
                kind=cmd[0]
                if kind=='C' and math.dist(previous,end)>1e-6:
                    controls=[cmd[1:3],cmd[3:5]]
                    if all(point_segment_distance(p,previous,end)<1e-5 for p in controls): kind='L'
                record={'owner':owner,'sub':sub,'a':previous,'b':end,'cmd':cmd,'kind':kind,
                        'width':float(leaf.get('stroke-width',1)),'role':leaf.get('data-role'),
                        'mount':leaf.get('data-role')=='equipment' and leaf.get('data-mount-side')!='freestanding' and primitive==0,
                        'parts':[(previous,cmd)],'changed':False}
                records.append(record); by_owner[owner].append(record)
                previous=end; primitive+=1
    covered=[]; curves=set(); removed=0; length_removed=0.0
    for record in sorted(records,key=lambda r:(-r['width'],r['owner'])):
        if record['role'] in ('equipment','leader'): continue
        if record['kind']=='C':
            pts=[record['a'],*vertices([record['cmd']])]
            key=min(tuple(round(v,4) for p in pts for v in p),tuple(round(v,4) for p in reversed(pts) for v in p))
            if key in curves: record.update(parts=[],changed=True); removed+=1
            curves.add(key); continue
        a,b=record['a'],record['b']; length=math.dist(a,b)
        if length<1e-7: record.update(parts=[],changed=True); continue
        intervals=[(0.0,length)]
        for c,d in covered:
            overlap=line_overlap(a,b,c,d)
            if overlap is None: continue
            lo,hi=overlap; remaining=[]
            for p,q in intervals:
                if hi<=p or lo>=q: remaining.append((p,q)); continue
                if p<lo: remaining.append((p,lo))
                if hi<q: remaining.append((hi,q))
            intervals=remaining
            if not intervals: break
        covered.append((a,b))
        kept=sum(q-p for p,q in intervals)
        if length-kept>1e-5:
            u=((b[0]-a[0])/length,(b[1]-a[1])/length)
            record['parts']=[(tuple(a[j]+p*u[j] for j in (0,1)),['L',*[a[j]+q*u[j] for j in (0,1)]])
                             for p,q in intervals if q-p>1e-5]
            record['changed']=True; removed+=1; length_removed+=length-kept
    # Preserve only the intentional equipment mounting-edge / wall overlap.
    allowed=0
    eq=[r for r in records if r['role']=='equipment']
    for i,record in enumerate(eq):
        for other in eq[:i]:
            if record['owner']!=other['owner'] and line_overlap(record['a'],record['b'],other['a'],other['b']):
                on_wall=record['mount'] and other['mount'] and any(
                    wall['role'] in ('building','wall') and wall['kind']=='L' and
                    line_overlap(record['a'],record['b'],wall['a'],wall['b']) for wall in records)
                if not on_wall:
                    raise ValueError('Equipment rectangles overlap; reduce symbol width or resolve the source wall positions')
        for other in records:
            if other['role']=='equipment' or other['kind']!='L': continue
            for start,cmd in other['parts']:
                if line_overlap(record['a'],record['b'],start,cmd[-2:]):
                    if record['mount'] and other['role'] in ('building','wall'): allowed+=1
                    else: raise ValueError('Unresolved equipment edge overlap outside its mounting wall')
    for owner,items in by_owner.items():
        if not any(r['changed'] for r in items): continue
        commands=[]
        for sub,path in enumerate(original_paths[owner]):
            members=[r for r in items if r['sub']==sub]
            if not any(r['changed'] for r in members): commands.extend(path); continue
            pieces=[piece for r in members for piece in r['parts']]
            if path[-1][0]=='Z' and pieces:
                for i in range(len(pieces)):
                    if math.dist(pieces[i-1][1][-2:],pieces[i][0])>1e-5:
                        pieces=pieces[i:]+pieces[:i]; break
            end=None
            for start,cmd in pieces:
                if end is None or math.dist(end,start)>1e-5: commands.append(['M',*start])
                commands.append(cmd); end=cmd[-2:]
        if leaves[owner].get('fill','none')!='none':
            raise ValueError('Coincident stroke on a filled source shape needs explicit scene separation')
        leaves[owner].set('d',path_d(commands))
    output=ET.Element(root.tag,root.attrib); filled=set()
    used_markers=set()
    for leaf in leaves:
        if leaf.get('marker-end'):
            match=re.fullmatch(r'url\(#([^\)]+)\)',leaf.get('marker-end'))
            if not match or match[1] not in markers:raise ValueError('Equipment arrow has no attached marker definition')
            if sum(c[0]=='M' for c in parse_export_path(leaf.get('d')))!=1:
                raise ValueError('Equipment arrow must remain one continuous stroked path')
            used_markers.add(match[1])
    if used_markers:
        definitions=ET.SubElement(output,ns+'defs')
        for identity in sorted(used_markers):definitions.append(markers[identity])
    for leaf in leaves:
        if leaf.tag==ns+'path':
            if not leaf.get('d'): continue
            if leaf.get('stroke','none')=='none':
                key=(leaf.get('d'),leaf.get('fill'),leaf.get('fill-rule'))
                if key in filled: hidden+=1; continue
                filled.add(key)
            elif leaf.get('fill','none')=='none':
                chunks=[]; chunk=[]
                for command in parse_export_path(leaf.get('d')):
                    if command[0]=='M' and chunk: chunks.append(chunk); chunk=[]
                    chunk.append(command)
                if chunk: chunks.append(chunk)
                if len(chunks)>1:
                    for index,chunk in enumerate(chunks,1):
                        attributes={**leaf.attrib,'d':path_d(chunk),'id':leaf.get('id')+f'-part-{index}'}
                        output.append(ET.Element(ns+'path',attributes))
                    continue
        output.append(leaf)
    return ET.tostring(output,encoding='unicode'),{'groups':0,'clipping_paths':0,'hidden_paths_removed':hidden,
             'overlap_segments_removed':removed,'overlap_length_removed_pt':length_removed,
             'permitted_equipment_wall_edges':allowed,
             'attached_equipment_arrows':sum(leaf.get('data-equipment-leader')=='true' for leaf in output),
             'leader_backing_strokes':sum(leaf.get('data-role')=='leader-underlay' for leaf in output)}


def render_scene(scene, manifest):
    body, box, report = scene_artwork(scene, manifest)
    svg,cleanup=clean_export(svg_wrap(body, box, physical=True))
    report['export_cleanup']=cleanup
    return svg, report


def source_trace(scene,manifest):
    """Unrotated source-coordinate geometry for honest registration overlays."""
    elements,_,_=resolve_elements(scene,manifest)
    box=viewport(scene.get("viewport",manifest["viewport"]))
    # Keep the original source frame for registration checks.
    body=draw_elements(elements,lambda p:p,"#00a651",[],box)
    return svg_wrap(body,box,physical=True)


def work_order_id(scene, manifest):
    job=scene.get("job",{})
    source_match=re.search(r"\bWO[-_ ]?(\d+)(?:[-_ ]([A-Z])(?=[^A-Z0-9]|$))?",
                           Path(manifest["source"]).stem,re.IGNORECASE)
    raw=str(job.get("work_order") or (source_match.group(1) if source_match else ""))
    match=re.fullmatch(r"(?:WO-)?(\d+)",raw,re.IGNORECASE)
    if not match: raise ValueError("Supply job.work_order; source filename has no reliable WO number")
    return f'WO-{match.group(1)}', source_match.group(2) if source_match else None


def output_filename(scene, manifest):
    """Keep the source-confirmed suffix when a single item is exported."""
    order, source_letter = work_order_id(scene, manifest)
    job=scene.get("job",{})
    count=job.get("map_count",1)
    if isinstance(count,bool) or not isinstance(count,int) or count<1:
        raise ValueError("job.map_count must be a positive integer")
    letter=job.get("item_letter") or source_letter
    if count>1:
        raise ValueError("Render an order scene with all maps on one artboard")
    if letter is not None:
        if not isinstance(letter,str) or not re.fullmatch(r"[A-Za-z]{1,3}\d{0,3}",letter):
            raise ValueError("job.item_letter must be a source-confirmed item code, such as A, AC or A1")
        if job.get("item_letter") and not job.get("item_evidence"):
            raise ValueError("Record job.item_evidence linking the letter to the source map")
    return order+(f'-{letter.upper()}' if letter else '')+'.svg'


def verified_source(scene_file, scene, with_image):
    manifest_file = (scene_file.parent/scene["manifest"]).resolve()
    manifest = read_json(manifest_file)
    source = Path(manifest["source"])
    if not source.is_absolute():
        source = (manifest_file.parent/source).resolve()
    if not source.exists():
        raise FileNotFoundError("Source unavailable; restore it before rendering a verified map")
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Source file has changed since extraction; extract again")
    box = viewport(scene.get("viewport", manifest["viewport"]))
    with open_source(source) as doc:
        page = doc[manifest["page"]-1]
        if not page.rect.contains(box):
            raise ValueError("Output viewport must remain within the source page for aligned review")
        original = None
        if with_image:
            pix = page.get_pixmap(matrix=fitz.Matrix(1600/box.width,1600/box.width), clip=box)
            original = Image.frombytes("RGB", [pix.width,pix.height], pix.samples)
    return manifest, original


def write_diagnostics(diagnostics, scene, manifest, svg, report, original):
    diagnostics = Path(diagnostics)
    diagnostics.mkdir(parents=True, exist_ok=True)
    svg_png(svg, diagnostics/"map.png")
    # Register raw trace to the original; compare the deliberately rotated map separately.
    trace_svg=source_trace(scene,manifest)
    (diagnostics/"source-trace.svg").write_text(trace_svg,encoding="utf-8")
    svg_png(trace_svg, diagnostics/"trace-transparent.png", alpha=True)
    trace = Image.open(diagnostics/"trace-transparent.png").convert("RGBA")
    # Integer raster bounds can differ by a pixel after clipping.
    original = original.resize(trace.size)
    overlay = original.convert("RGBA")
    overlay.alpha_composite(trace)
    overlay.convert("RGB").save(diagnostics/"overlay.png")
    clean = Image.open(diagnostics/"map.png").convert("RGB")
    pane_h=max(clean.height,original.height)
    sheet = Image.new("RGB", (clean.width*2,pane_h+42),"white")
    sheet.paste(original,(0,42+(pane_h-original.height)//2)); sheet.paste(clean,(clean.width,42+(pane_h-clean.height)//2))
    draw=ImageDraw.Draw(sheet)
    draw.text((16,14),"SOURCE",fill="black")
    draw.text((clean.width+16,14),"MAP DRAWING - TEMPLATE DEFERRED",fill="black")
    sheet.save(diagnostics/"comparison.png")
    write_json(diagnostics/"review.json",report)


def render_order(scene_file, order, diagnostics=None, mode=None):
    """Lay out separately reviewed maps at their original output scale."""
    map_files = order["maps"]
    if not isinstance(map_files, list) or len(map_files) < 2:
        raise ValueError("A shared artboard requires at least two map scene paths")
    if order.get("job", {}).get("map_count", len(map_files)) != len(map_files):
        raise ValueError("job.map_count must match the number of map scenes")
    mode = mode if mode is not None else order.get('output_mode')
    if mode is not None and mode not in OUTPUT_MODES:
        raise ValueError('output_mode must be map-only, map-labeled or finished')
    panels = {}
    order_id = None
    for map_file in map_files:
        path = scene_file.parent / map_file
        scene = read_json(path)
        if mode is not None:
            scene=apply_output_mode(scene,mode)
        manifest, original = verified_source(path, scene, diagnostics is not None)
        this_order, _ = work_order_id(scene, manifest)
        if order_id is None:
            order_id, _ = work_order_id(order, manifest)
        if this_order != order_id:
            raise ValueError(f"{map_file} belongs to {this_order}, expected {order_id}")
        letter = scene.get("job", {}).get("item_letter", "")
        if not isinstance(letter, str) or not re.fullmatch(r"[A-Za-z]{1,3}\d{0,3}", letter) or not scene["job"].get("item_evidence"):
            raise ValueError(f"Supply a source-confirmed item letter and evidence for {map_file}")
        letter = letter.upper()
        if letter in panels:
            raise ValueError(f"Duplicate map item {letter}")
        body, box, report = scene_artwork(scene, manifest)
        panels[letter] = (body, box, report, scene, manifest, original)

    modes={panel[2].get('output_mode') for panel in panels.values()}
    if len(modes)>1:
        raise ValueError('Use one output mode for every map on the sales order')
    effective_mode=next(iter(modes))
    margin, gutter, heading = 24, 36, 0 if effective_mode=='map-only' else 28
    content, reports = [], []
    y, width = margin, 0
    def item_order(item):
        letters,number=re.fullmatch(r'([A-Z]+)(\d*)',item[0]).groups()
        alphabetic=0
        for char in letters: alphabetic=alphabetic*26+ord(char)-ord('A')+1
        return alphabetic,int(number or 0)
    items = sorted(panels.items(),key=item_order)
    for row_start in range(0, len(items), 2):
        x, row_height = margin, 0
        for letter, (body, box, report, scene, manifest, original) in items[row_start:row_start+2]:
            panel_id = f'item-{letter}'
            ids=re.findall(r' id="([^"]+)"',body)
            body = re.sub(r' id="([^"]+)"', rf' id="{panel_id}-\1"', body)
            for old_id in ids:
                body=body.replace(f'url(#{old_id})',f'url(#{panel_id}-{old_id})')
            label = f'{order_id}-{letter}'
            item_heading = '' if effective_mode=='map-only' else (
                f'<text x="{n(x)}" y="{n(y+16)}" font-family="Arial,Helvetica,sans-serif" '
                f'font-size="14" font-weight="bold">{label}</text>')
            content.append(
                f'<g id="{panel_id}"><title>{label}</title>'
                f'{item_heading}'
                f'<g transform="translate({n(x-box.x0)} {n(y+heading-box.y0)})">{body}</g></g>'
            )
            if diagnostics is not None:
                write_diagnostics(Path(diagnostics)/letter, scene, manifest,
                                  svg_wrap(body, box, physical=True), report, original)
            reports.append({"item_letter":letter, "label":label, "report":report})
            width = max(width, x+box.width+margin)
            row_height = max(row_height, box.height+heading)
            x += box.width+gutter
        y += row_height+gutter
    artboard = viewport([0, 0, width, y-gutter+margin])
    report = {"status":"needs_visual_review", "output_mode":effective_mode, "output_filename":f"{order_id}.svg",
              "maps":reports, "warnings":[f'{item["label"]}: {warning}'
                                           for item in reports for warning in item["report"]["warnings"]]}
    svg,cleanup=clean_export(svg_wrap("".join(content), artboard, physical=True))
    report['export_cleanup']=cleanup
    return svg, report


def render(scene_file, output, *, preview=None, diagnostics=None, mode=None):
    """Write one vector artboard for the order, with optional internal QA."""
    scene_file, output = Path(scene_file), Path(output)
    scene = read_json(scene_file)
    preview = Path(preview) if preview is not None else None
    if "maps" in scene:
        svg, report = render_order(scene_file, scene, diagnostics, mode=mode)
    else:
        scene=apply_output_mode(scene,mode)
        manifest, original = verified_source(scene_file, scene, diagnostics is not None)
        filename = output_filename(scene, manifest)
        svg, report = render_scene(scene, manifest)
        report["output_filename"] = filename
        if diagnostics is not None:
            write_diagnostics(diagnostics, scene, manifest, svg, report, original)
    if diagnostics is not None and "maps" in scene:
        svg_png(svg, Path(diagnostics)/"map.png")
        write_json(Path(diagnostics)/"review.json", report)
    if preview is not None and (diagnostics is None or preview.resolve() != (Path(diagnostics)/"map.png").resolve()):
        preview.parent.mkdir(parents=True, exist_ok=True)
        svg_png(svg, preview)
    output.mkdir(parents=True, exist_ok=True)
    (output/report["output_filename"]).write_text(svg, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "extract"):
        p = sub.add_parser(name)
        p.add_argument("source")
        p.add_argument("--output", required=True)
        if name == "extract":
            p.add_argument("--page", type=int, required=True)
            p.add_argument("--clip", nargs=4, type=float)
    p=sub.add_parser("render")
    p.add_argument("scene")
    p.add_argument("--output",required=True)
    p.add_argument("--preview", help="Optional PNG path for a quick visual check")
    p.add_argument("--diagnostics", help="Optional directory for the full source comparison and review assets")
    p.add_argument("--mode", choices=OUTPUT_MODES, help="Choose map geometry, labeled map or finished placard")
    args=parser.parse_args()
    if args.command=="inspect": result=inspect_source(args.source,args.output)
    elif args.command=="extract": result=extract(args.source,args.page,args.clip,args.output)
    else: result=render(args.scene,args.output,preview=args.preview,diagnostics=args.diagnostics,mode=args.mode)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
