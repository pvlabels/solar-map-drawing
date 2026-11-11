"""Inspect source maps, retain PDF paths, and render a reviewed map scene.

Requires PyMuPDF and Pillow. No API key, web app, template registry, or Chrome.
Page numbers in the CLI are one-based; all geometry uses displayed page points.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

# Physical points in the final drawing; never multiplied by map fit scale.
ROLES = {"building": 2.0, "roof": 1.0, "solar": 1.25, "equipment": 1.5,
         "context": 1.0, "north": 1.5, "leader": 0.75, "feature": 1.0}


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
        manifest = {"version": 1, "source": str(Path(source).resolve()),
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
    rotation = -((angle+22.5)%45-22.5)
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


def draw_elements(elements, transform, color, warnings, box):
    body=[]
    for el in elements:
        role=el["role"]
        content=[]
        for commands in el["paths"]:
            mapped=transform_commands(commands,transform)
            if any(not (box.x0<=x<=box.x1 and box.y0<=y<=box.y1) for x,y in vertices(mapped)):
                warnings.append(f'{el["id"]} has coordinates outside output viewport')
            fill=color if el.get("solid",False) else "none"
            content.append(f'<path d="{path_d(mapped)}" fill="{fill}" stroke="{color}" stroke-width="{n(ROLES[role])}" stroke-linejoin="miter" stroke-linecap="butt"/>')
        body.append(f'<g id="{html.escape(el["id"],quote=True)}" data-role="{role}">{"".join(content)}</g>')
    return "".join(body)


def text_box(label):
    size=float(label.get("size_pt",12))
    if not math.isfinite(size) or size<=0: raise ValueError("Invalid text size")
    lines=label["text"] if isinstance(label["text"],list) else [label["text"]]
    if not lines or not all(isinstance(line,str) and line for line in lines): raise ValueError("Empty label")
    font=fitz.Font("helv")
    width=max(font.text_length(line,fontsize=size) for line in lines)
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
    """Keep the whole head envelope at least 2 pt from nearby stroked edges."""
    blocked = []
    for points, radius in obstacles:
        pad = radius + 2
        lateral = half_width + pad
        local = [((target[0]-x)*ux + (target[1]-y)*uy,
                  (y-target[1])*ux - (x-target[0])*uy) for x, y in points]
        if max(y for _, y in local) < -lateral or min(y for _, y in local) > lateral:
            continue
        if len(local) == 2:
            # Restrict a straight edge to the strip occupied by the head.
            (a, v), (b, w) = local
            if v != w:
                t0, t1 = sorted(((-lateral-v)/(w-v), (lateral-v)/(w-v)))
                local = [(a+(b-a)*max(0, t0), 0), (a+(b-a)*min(1, t1), 0)]
        low, high = sorted((min(x for x, _ in local), max(x for x, _ in local)))
        blocked.append((low-depth-pad, high+pad))
    for low, high in sorted(blocked):
        if low <= gap <= high:
            gap = high + 0.05
    return gap


def draw_callouts(labels, transform, color, box, warnings, obstacles=()):
    leaders,texts,boxes,targets=[],[],[],[]
    arrow=read_json(Path(__file__).resolve().parents[1]/"assets/leader-arrow-2.json")
    arrow_scale=ROLES["leader"]/arrow["reference_stroke_pt"]
    shaft_inset=arrow["shaft_stop_before_tip"]*arrow_scale
    head_points=vertices(arrow["commands"])
    head_depth=-min(x for x, _ in head_points)*arrow_scale
    head_half_width=max(abs(y) for _, y in head_points)*arrow_scale
    for index,label in enumerate(labels):
        lines,size,anchor,bbox=text_box(label)
        if not box.contains(fitz.Rect(bbox)): warnings.append(f"Callout {index+1} is outside canvas")
        for other in boxes:
            if intersects(bbox,other): warnings.append(f"Callout {index+1} overlaps another label")
        boxes.append(bbox)
        if "target" in label:
            target=transform(label["target"])
            side=label.get("side","right" if target[0]>(bbox[0]+bbox[2])/2 else "left")
            if side not in ("left","right","top","bottom"): raise ValueError("Invalid leader side")
            start={"left":(bbox[0]-4,(bbox[1]+bbox[3])/2),"right":(bbox[2]+4,(bbox[1]+bbox[3])/2),
                   "top":((bbox[0]+bbox[2])/2,bbox[1]-4),"bottom":((bbox[0]+bbox[2])/2,bbox[3]+4)}[side]
            via=label.get("via")
            if via is None:
                if "elbow_x" in label: via=[(label["elbow_x"],start[1]),(label["elbow_x"],target[1])]
                elif "elbow_y" in label: via=[(start[0],label["elbow_y"]),(target[0],label["elbow_y"])]
                else: via=[(target[0],start[1])]
            route=[start,*via,target]
            # Drop coincident points before choosing the final approach vector.
            route=[p for i,p in enumerate(route) if i==0 or math.dist(p,route[i-1])>1e-6]
            if len(route)<2: raise ValueError("Leader has no length")
            prev=route[-2]; length=math.dist(prev,target)
            ux,uy=(target[0]-prev[0])/length,(target[1]-prev[1])/length
            gap=float(label.get("target_gap_pt",3))
            if not math.isfinite(gap): raise ValueError("Invalid arrow gap")
            gap=arrow_setback(target,ux,uy,max(3,gap),head_depth,head_half_width,obstacles)
            if length<=gap+shaft_inset:
                raise ValueError(f'Extend the final leader segment for {" ".join(lines)} to leave space at its arrowhead')
            tip=(target[0]-gap*ux,target[1]-gap*uy)
            route[-1]=tip
            # Stop the shaft inside the filled head: a stroke to the tip makes
            # a blunt nib protrude past the pointed Arrow 2 silhouette.
            route[-1]=(tip[0]-shaft_inset*ux,tip[1]-shaft_inset*uy)
            d=path_d([["M",*route[0]],*[["L",*p] for p in route[1:]]])
            if label.get("clearance",True):
                leaders.append(f'<path d="{d}" fill="none" stroke="white" stroke-width="5" stroke-linejoin="round"/>')
            leaders.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{n(ROLES["leader"])}" stroke-linecap="butt"/>')
            def head_transform(p):
                return (tip[0]+arrow_scale*(p[0]*ux-p[1]*uy),
                        tip[1]+arrow_scale*(p[0]*uy+p[1]*ux))
            head=transform_commands(arrow["commands"],head_transform)
            leaders.append(f'<path data-arrowhead="Illustrator Arrow 2" d="{path_d(head)}" fill="{color}"/>')
            targets.append({"text":lines,"source_target":label["target"],"output_target":target,"arrow_tip":tip,"setback_pt":gap})
        for i,line in enumerate(lines):
            texts.append(f'<text x="{n(label["x"])}" y="{n(label["y"]+i*size*1.2)}" font-family="Arial,Helvetica,sans-serif" font-size="{n(size)}" text-anchor="{anchor}" fill="{color}">{html.escape(line)}</text>')
    return '<g id="callout-leaders">'+"".join(leaders)+'</g><g id="callout-text">'+"".join(texts)+'</g>', targets


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
    height=float(north.get("height_pt",34))
    if not math.isfinite(height) or height<=0: raise ValueError("Invalid north symbol height")
    scale=height/asset["height"]
    angle=north_direction(north,applied_rotation)["display_deg"]
    rad=math.radians(angle); c,s=math.cos(rad),math.sin(rad)
    x,y=north["x"],north["y"]
    def transform(p): return (x+scale*(p[0]*c-p[1]*s),y+scale*(p[0]*s+p[1]*c))
    commands=transform_commands(asset["commands"],transform)
    needle=f'<path d="{path_d(commands)}" fill="{color}" fill-rule="evenodd"/>'
    # Upright N stays below the symbol's rotated bounds, with consistent spacing.
    bb=bounds(vertices(commands)); size=height*.52
    letter=f'<text x="{n((bb[0]+bb[2])/2)}" y="{n(bb[3]+size+4)}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="{n(size)}" fill="{color}">N</text>'
    return f'<g id="north-arrow" data-rotation-deg="{n(angle)}">{needle}{letter}</g>', angle


def scene_artwork(scene, manifest):
    elements,used,warnings=resolve_elements(scene,manifest)
    # Source compass artwork is replaced with the fixed house symbol.
    if any(el["role"]=="north" for el in elements):
        raise ValueError("Use north_arrow with source_rotation_deg; do not reuse customer compass artwork")
    box,transform,alignment=layout_for(scene,manifest,elements)
    color=html.escape(scene.get("color","#00a651"),quote=True)
    body=[draw_elements(elements,transform,color,warnings,box)]
    callouts=scene.get("callouts",[])
    obstacles=arrow_obstacles(elements,transform) if callouts else ()
    callout_svg,targets=draw_callouts(callouts,transform,color,box,warnings,obstacles)
    body.append(callout_svg)
    north_svg,north_angle=draw_north(scene.get("north_arrow"),alignment["rotation_deg"],color)
    body.append(north_svg)
    # Plain labels without leaders use final output point coordinates.
    for label in scene.get("labels", []):
        size = float(label.get("size_pt", 12))
        if size <= 0 or not label.get("text"):
            raise ValueError("Label needs positive size and nonempty text")
        lines = label["text"] if isinstance(label["text"], list) else [label["text"]]
        anchor = label.get("anchor", "middle")
        if anchor not in ("start", "middle", "end"):
            raise ValueError("Invalid label anchor")
        for i, line in enumerate(lines):
            body.append(f'<text x="{n(label["x"])}" y="{n(label["y"]+i*size*1.2)}" font-family="Arial,sans-serif" font-size="{n(size)}" text-anchor="{anchor}" fill="{color}">{html.escape(line)}</text>')
    counts={role:sum(el["role"]==role for el in elements) for role in ROLES if any(el["role"]==role for el in elements)}
    report = {"status": "needs_visual_review", "elements_by_role": counts,
              "alignment":alignment, "stroke_widths_pt":ROLES,
              "north_rotation_deg":north_angle,
              "north_direction":north_direction(scene["north_arrow"],alignment["rotation_deg"]) if scene.get("north_arrow") else None,
              "callout_targets":targets,
              "selected_source_paths": len(used), "unselected_source_paths": len(manifest["paths"])-len(used),
              "warnings": sorted(set(warnings)),
              "checks": ["building count, outline topology, relative placement", "roof junctions and open/closed edges",
                         "panel count, layout, rotation, roof clearance", "equipment position and north direction",
                         "labels, omitted details, crop boundaries"]}
    return "".join(body), box, report


def render_scene(scene, manifest):
    body, box, report = scene_artwork(scene, manifest)
    return svg_wrap(body, box, physical=True), report


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
        if not isinstance(letter,str) or not re.fullmatch(r"[A-Za-z]",letter):
            raise ValueError("job.item_letter must be one source-confirmed letter")
        if job.get("item_letter") and not job.get("item_evidence"):
            raise ValueError("Record job.item_evidence linking the letter to the source map")
    return order+(f'-{letter.upper()}' if letter else '')+'.svg'


def verified_source(scene_file, scene, with_image):
    manifest_file = (scene_file.parent/scene["manifest"]).resolve()
    manifest = read_json(manifest_file)
    source = Path(manifest["source"])
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


def render_order(scene_file, order, diagnostics=None):
    """Lay out separately reviewed maps at their original output scale."""
    map_files = order["maps"]
    if not isinstance(map_files, list) or len(map_files) < 2:
        raise ValueError("A shared artboard requires at least two map scene paths")
    if order.get("job", {}).get("map_count", len(map_files)) != len(map_files):
        raise ValueError("job.map_count must match the number of map scenes")
    panels = {}
    order_id = None
    for map_file in map_files:
        path = scene_file.parent / map_file
        scene = read_json(path)
        manifest, original = verified_source(path, scene, diagnostics is not None)
        this_order, _ = work_order_id(scene, manifest)
        if order_id is None:
            order_id, _ = work_order_id(order, manifest)
        if this_order != order_id:
            raise ValueError(f"{map_file} belongs to {this_order}, expected {order_id}")
        letter = scene.get("job", {}).get("item_letter", "")
        if not isinstance(letter, str) or not re.fullmatch(r"[A-Za-z]", letter) or not scene["job"].get("item_evidence"):
            raise ValueError(f"Supply a source-confirmed item letter and evidence for {map_file}")
        letter = letter.upper()
        if letter in panels:
            raise ValueError(f"Duplicate map item {letter}")
        body, box, report = scene_artwork(scene, manifest)
        panels[letter] = (body, box, report, scene, manifest, original)

    margin, gutter, heading = 24, 36, 28
    content, reports = [], []
    y, width = margin, 0
    items = sorted(panels.items())
    for row_start in range(0, len(items), 2):
        x, row_height = margin, 0
        for letter, (body, box, report, scene, manifest, original) in items[row_start:row_start+2]:
            panel_id = f'item-{letter}'
            body = re.sub(r' id="([^"]+)"', rf' id="{panel_id}-\1"', body)
            clip_id = f'{panel_id}-clip'
            label = f'{order_id}-{letter}'
            content.append(
                f'<g id="{panel_id}"><title>{label}</title>'
                f'<text x="{n(x)}" y="{n(y+16)}" font-family="Arial,Helvetica,sans-serif" '
                f'font-size="14" font-weight="bold">{label}</text>'
                f'<defs><clipPath id="{clip_id}"><rect x="{n(box.x0)}" y="{n(box.y0)}" '
                f'width="{n(box.width)}" height="{n(box.height)}"/></clipPath></defs>'
                f'<g transform="translate({n(x-box.x0)} {n(y+heading-box.y0)})" '
                f'clip-path="url(#{clip_id})">{body}</g></g>'
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
    report = {"status":"needs_visual_review", "output_filename":f"{order_id}.svg",
              "maps":reports, "warnings":[f'{item["label"]}: {warning}'
                                           for item in reports for warning in item["report"]["warnings"]]}
    return svg_wrap("".join(content), artboard, physical=True), report


def render(scene_file, output, *, preview=None, diagnostics=None):
    """Write one vector artboard for the order, with optional internal QA."""
    scene_file, output = Path(scene_file), Path(output)
    scene = read_json(scene_file)
    preview = Path(preview) if preview is not None else None
    if "maps" in scene:
        svg, report = render_order(scene_file, scene, diagnostics)
    else:
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
    args=parser.parse_args()
    if args.command=="inspect": result=inspect_source(args.source,args.output)
    elif args.command=="extract": result=extract(args.source,args.page,args.clip,args.output)
    else: result=render(args.scene,args.output,preview=args.preview,diagnostics=args.diagnostics)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
