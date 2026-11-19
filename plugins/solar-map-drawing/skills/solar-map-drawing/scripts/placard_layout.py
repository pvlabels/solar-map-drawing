"""Read order dimensions and plan physical cutline/header/map/footer zones.

No model API or project dependency. Source interpretation and label routing stay
with the chat agent; this module refuses unsupported production-size guesses.
"""
from __future__ import annotations
import argparse
import copy
from fractions import Fraction
import hashlib
import html
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
try:
    import pymupdf as fitz
except ImportError:
    import fitz

ASSET=Path(__file__).resolve().parents[1]/'assets/placard-profiles.json'
NUMBER=r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?|\.\d+)'
UNIT=r'(?:"|inches\b|inch\b|in\b|mm\b|cm\b|pt\b)'
DIMENSION=re.compile(r'(?<![\d./-])('+NUMBER+r')\s*('+UNIT+r')?\s*[x×]\s*('+NUMBER+r')\s*('+UNIT+r')?',re.I)

def assets():return json.loads(ASSET.read_text(encoding='utf8'))
def num(v):
    v=float(v)
    if not math.isfinite(v):raise ValueError('Layout values must be finite')
    return f'{v:.5f}'.rstrip('0').rstrip('.') or '0'
def positive(v):
    v=float(v)
    if not math.isfinite(v) or v<=0:raise ValueError('Physical dimensions and type sizes must be positive')
    return v
def fraction(s):return sum(float(Fraction(p)) for p in s.strip().split())
def dimensions(text):
    """Return explicit-unit dimensions; bare 5 x 5 remains unconfirmed."""
    text=text.replace('″','"').replace('“','"').replace('”','"').replace('×','x')
    for c,v in [('½','1/2'),('¼','1/4'),('¾','3/4'),('⅛','1/8'),('⅜','3/8'),('⅝','5/8'),('⅞','7/8')]:
        text=re.sub(r'(\d)'+c,r'\1 '+v,text);text=text.replace(c,v)
    result=[]
    for match in DIMENSION.finditer(text):
        a,b=fraction(match[1]),fraction(match[3]);u1,u2=match[2],match[4]
        if not u1 and not u2:continue
        def unit(s):return 'in' if s and (s=='"' or s.lower().startswith('in')) else s.lower() if s else None
        u1,u2=unit(u1),unit(u2)
        if u1 and u2 and u1!=u2:continue
        u=u1 or u2;factor={'in':1,'mm':1/25.4,'cm':1/2.54,'pt':1/72}[u]
        if a>0 and b>0:result.append({'nominal_size_in':[a*factor,b*factor],'source_size_text':match[0],'units':u})
    return result

def profile_candidates(sku,size):
    found=[]
    for name,p in assets()['profiles'].items():
        if all(abs(a-b)<.001 for a,b in zip(size,p['nominal_in'])):
            if p.get('stock_sku')==sku:found.insert(0,name)
            elif not p.get('stock_sku'):found.append(name)
    return found

def analyze_order_pdf(path,work_order,*,page_numbers=None):
    """Associate dimensions and SKU by physical packing-slip row, not file size."""
    order=re.sub(r'(?i)^WO-','',str(work_order));marker=re.compile(r'(?<!\d)'+re.escape(order)+r'\s*(?:-+\s*)?\(?\s*([A-Z]{1,3}\d{0,3})(?![A-Za-z0-9])')
    if not order.isdigit():raise ValueError('Analyze a source-confirmed numeric work order')
    digest=hashlib.sha256(Path(path).read_bytes()).hexdigest();items=[]
    with fitz.open(path) as doc:
        for page_index in ([n-1 for n in page_numbers] if page_numbers is not None else range(len(doc))):
            page=doc[page_index]
            if 'packing slip' not in page.get_text().lower():continue
            lines=[]
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    text=''.join(s['text'] for s in line['spans']).strip()
                    if text:lines.append({'text':text,'bbox':line['bbox']})
            sku_lines=[l for l in lines if re.fullmatch(r'\d{1,2}-\d{1,4}',l['text'])]
            marked=[(l,marker.search(l['text'])) for l in lines if marker.search(l['text'])]
            for line,m in marked:
                y0,y1=line['bbox'][1],line['bbox'][3];mid=(y0+y1)/2;x0=line['bbox'][0]
                nearby=sorted(sku_lines,key=lambda l:abs((l['bbox'][1]+l['bbox'][3])/2-mid))
                sku=nearby[0]['text'] if nearby and abs((nearby[0]['bbox'][1]+nearby[0]['bbox'][3])/2-mid)<9 else None
                next_y=min([l['bbox'][1] for l in lines if l['bbox'][0]<x0-12 and (l['bbox'][1]+l['bbox'][3])/2>mid+5]+
                           [l['bbox'][1] for l,_ in marked if l is not line and l['bbox'][1]>y0+1]+[page.rect.height-20])
                description=[l for l in lines if l['bbox'][1]>=y0-1 and l['bbox'][1]<next_y-1 and l['bbox'][0]>=x0-4]
                description.sort(key=lambda l:(round(l['bbox'][1],1),l['bbox'][0]))
                text='\n'.join(l['text'] for l in description)
                sizes=dimensions(text);unique={tuple(round(v,5) for v in d['nominal_size_in']):d for d in sizes}
                size=next(iter(unique.values())) if len(unique)==1 else None
                holes=None
                if re.search(r'(?i)NO\s+HOLES',text):holes=False
                elif re.search(r'(?i)\bHOLES?\b',text):holes=True
                item={'work_order':'WO-'+order,'item_code':m[1],'sku':sku,'source_page':page_index+1,
                      'source_sha256':digest,'order_row_evidence':text,'nominal_size_in':size['nominal_size_in'] if size else None,
                      'size_candidates':list(unique.values()),'holes_requested':holes,
                      'branding_restricted':bool(re.search(r'(?i)NO\s+PV\s*LABELS?\s+(?:INFO|INFORMATION)',text)),
                      'material_hint':'metal' if re.search(r'(?i)\b(?:aluminum|aluminium|metal)\b',text) else None,
                      'profile_candidates':profile_candidates(sku,size['nominal_size_in']) if size else [],
                      'needs_review':not bool(sku and size),'warning_requires_source_review':True}
                # A range of repeated devices is not automatically one map item.
                item['range_item']=bool(re.search(re.escape(m[0])+r'\s*[-–]\s*[A-Z]{1,3}\d{0,3}(?![A-Za-z0-9])',line['text']))
                if not re.search(re.escape(order)+r'\s*-',m[0]):
                    item['item_separator_missing']=True;item['needs_review']=True
                items.append(item)
    grouped={}
    for item in items:grouped.setdefault(item['item_code'],[]).append(item)
    for group in grouped.values():
        keys={(x['sku'],tuple(x['nominal_size_in'] or [])) for x in group}
        if len(keys)>1:
            for x in group:x['needs_review']=True;x['conflicting_order_rows']=True
    return {'source_sha256':digest,'items':items,'note':'Candidate row associations require visual confirmation against the selected map/item. No map geometry or warning behavior is inferred.'}

def production_style(settings=None):
    settings=settings or {};process=settings.get('process','laser')
    defaults={'laser':('#00a651','#ffffff','Laser'),'metal':('#000000','#ffffff','Print'),'label':('#ffffff','#ed1c24','Print')}
    if process not in defaults:raise ValueError('production.process must be laser, metal or label')
    ink,background,layer=defaults[process]
    ink=settings.get('ink_color',ink);background=settings.get('background_color',background)
    if not all(re.fullmatch(r'#[0-9a-fA-F]{6}',str(c)) for c in (ink,background)):raise ValueError('Production preview colors must be six-digit SVG colors')
    if ink.lower()==background.lower():raise ValueError('Production ink and background need visible contrast')
    return {'process':process,'ink':ink,'background':background,'backing':background if process=='label' else '#ffffff','layer':layer}


def font_scale(value):
    scale=float(value)
    if not math.isfinite(scale) or scale<.7-1e-6 or scale>1+1e-6 or abs(scale*20-round(scale*20))>1e-5:
        raise ValueError('Font horizontal scale must be 70%-100% in 5% increments')
    return scale


def text_lines(text):
    """Hard wraps belong to the same logical block, including explicit blank lines."""
    values=[text] if isinstance(text,str) else text
    if not isinstance(values,(list,tuple)) or not values or not all(isinstance(v,str) for v in values):
        raise ValueError('Text block needs a string or list of lines')
    lines=[line for value in values for line in value.replace('\r\n','\n').replace('\r','\n').split('\n')]
    if not any(lines):raise ValueError('Empty text block')
    return lines


def wrap(lines,size,width,scale=1):
    font=fitz.Font('helv');result=[]
    lines=text_lines(lines)
    for line in lines:
        if not isinstance(line,str) or not line.strip():raise ValueError('Warning lines must be nonempty source-confirmed text')
        current=''
        for word in line.split():
            candidate=(current+' '+word).strip()
            if font.text_length(candidate,fontsize=size)*scale<=width+.01:current=candidate
            elif current:result.append(current);current=word
            else:raise ValueError('A warning word does not fit at its required type size')
            if font.text_length(current,fontsize=size)*scale>width+.01:raise ValueError('Warning word exceeds the physical zone')
        result.append(current)
    return result

def text_record(text,x,y,size,anchor='middle',scale=1,role='warning',block_id=None):
    scale=font_scale(scale)
    width=fitz.Font('helv').text_length(text,fontsize=size)*scale
    left=x-width*{'start':0,'middle':.5,'end':1}[anchor]
    return {'text':text,'x':x,'y':y,'size_pt':size,'anchor':anchor,'width_scale':scale,'role':role,'block_id':block_id,
            'bbox':[left,y-size*1.075,left+width,y+size*.299]}

def plan(placard,job=None,manifest=None,output_mode=None,production=None):
    if output_mode not in (None,'map-only','map-labeled','finished'):
        raise ValueError('Unknown solar output mode')
    job=job or {};data=assets();order=placard.get('order',{})
    process=production_style(production)
    for key in ('sku','item_code','nominal_size_in','order_row_evidence','source_page'):
        if not order.get(key):raise ValueError('Size-first layout needs source-confirmed placard.order.'+key)
    if len(order['nominal_size_in'])!=2:raise ValueError('Order size needs width and height')
    if not isinstance(order['source_page'],int) or isinstance(order['source_page'],bool) or order['source_page']<1:raise ValueError('Order evidence page must be one-based')
    if not re.fullmatch(r'\d{1,2}-\d{1,4}',str(order['sku'])):raise ValueError('Footer SKU must be copied from the source order row')
    nominal=list(map(positive,order['nominal_size_in']))
    wo=job.get('work_order') or order.get('work_order')
    if not wo or not re.fullmatch(r'(?:WO-)?\d+',str(wo),re.I):raise ValueError('Placard footer needs a confirmed work order')
    digits=re.sub(r'(?i)^WO-','',str(wo));item=order['item_code']
    if not re.fullmatch(r'[A-Z]{1,3}\d{0,3}',item):raise ValueError('Invalid confirmed item code')
    if job.get('item_letter') and job['item_letter'].upper()!=item:raise ValueError('Placard order item differs from map item')
    if order.get('work_order') and re.sub(r'(?i)^WO-','',order['work_order'])!=digits:raise ValueError('Placard order belongs to a different work order')
    if manifest and manifest.get('sha256') and order.get('source_sha256')!=manifest['sha256']:
        raise ValueError('Placard order evidence must be tied to this source PDF hash')
    name=placard.get('profile');profile=data['profiles'].get(name)
    if profile:
        if process['process']!='laser' or re.search(r'(?i)metal|alumin',str(order.get('material_hint') or order.get('material') or '')):
            raise ValueError('Measured laser-plastic profiles do not establish a metal/label cut size; supply approved dimensions')
        if any(abs(a-b)>.001 for a,b in zip(nominal,profile['nominal_in'])):
            raise ValueError('Ordered size conflicts with the selected production profile; do not force a stock size')
        width,height=profile['cut_size_pt'];inset=profile['safe_inset_pt']
        size_evidence=profile['evidence']
    else:
        explicit=placard.get('production_size_pt')
        if not explicit or len(explicit)!=2 or not placard.get('production_size_evidence'):
            raise ValueError('Unverified custom size: supply measured production_size_pt and production_size_evidence; no universal cut reduction is assumed')
        width,height=map(positive,explicit);inset=positive(placard.get('safe_inset_pt',8));size_evidence=placard['production_size_evidence'];profile={}
    footer={**data['footer'],**placard.get('footer',{})}
    if float(footer['size_pt'])!=5:raise ValueError('Footer must remain 5 pt at 100% horizontal scale')
    footer['color']='#ed1c24' if process['process']=='laser' else process['ink']
    footer_top=height-positive(footer['reserve_height_pt']);safe=[inset,inset,width-inset,footer_top]
    warning=placard.get('warning',{});style_id=warning.get('style',profile.get('warning_style'))
    if style_id not in data['warning_styles']:raise ValueError('Choose a reviewed warning style')
    style={**data['warning_styles'][style_id],**{k:v for k,v in warning.items() if k.endswith('_pt') or k.endswith('_scale')}}
    heading=warning.get('heading');lines=warning.get('lines')
    if (heading is not None or lines is not None) and not warning.get('evidence'):raise ValueError('Record warning.evidence for the supplied wording')
    if heading is None or lines is None:
        if profile.get('stock_sku')!=order['sku'] or not style.get('default_heading'):
            raise ValueError('Custom/customer warning needs exact heading, lines and source evidence; SKU alone does not determine electrical wording')
        heading=heading if heading is not None else style['default_heading'];lines=lines if lines is not None else style['default_lines']
    elif not warning.get('evidence'):raise ValueError('Record warning.evidence for the supplied wording')
    corner=warning.get('position','full_width')
    if corner not in ('full_width','top_left','top_right'):raise ValueError('Invalid warning-zone position')
    if style_id!='directory' and corner!='full_width':raise ValueError('A corner header requires a reviewed directory layout')
    header_width=positive(warning.get('width_pt',width-2*inset if corner=='full_width' else min(350,width*.47)))
    title_margin=positive(warning.get('margin_x_pt',32.8 if corner=='top_left' else 18 if corner=='top_right' else inset))
    left=title_margin if corner!='top_right' else width-title_margin-header_width
    if left<inset-1e-5 or left+header_width>width-inset+1e-5:raise ValueError('Warning/title zone exceeds the physical safe width')
    anchor='middle' if corner=='full_width' else ('end' if corner=='top_right' else 'start')
    x=width/2 if corner=='full_width' else (left+header_width if anchor=='end' else left)
    records=[];hs=positive(style['heading_size_pt']);hscale=positive(style.get('heading_width_scale',1))
    headings=wrap(heading,hs,header_width,hscale)
    y=positive(style['heading_baseline_pt']);leading=positive(style.get('heading_leading_pt',hs*1.2))
    for text in headings:records.append(text_record(text,x,y,hs,anchor,hscale,block_id='warning-heading'));y+=leading
    gap=style.get('body_gap_pt',float(style.get('body_baseline_pt',style['heading_baseline_pt']+21))-style['heading_baseline_pt'])
    body_y=records[-1]['y']+positive(gap)
    bs=positive(style['body_size_pt']);bscale=positive(style.get('width_scale',1));body=wrap(lines,bs,header_width,bscale) if lines else []
    for i,text in enumerate(body):records.append(text_record(text,x,body_y+i*positive(style['leading_pt']),bs,anchor,bscale,block_id='warning-body'))
    bottom=max(t['bbox'][3] for t in records)
    divider_y=bottom+4 if style.get('divider') else None
    note=placard.get('operational_note')
    bottom_notes=list(placard.get('bottom_notes',[]))
    if note and note.get('placement')=='bottom':bottom_notes.insert(0,note);note=None
    if note:
        if not note.get('evidence'):raise ValueError('Operational note needs source evidence')
        size=positive(note.get('size_pt',11));scale=positive(note.get('width_scale',.80 if style_id.startswith('tfs') else 1))
        ny=max(bottom+size+7,(divider_y or 0)+size+4)
        for i,text in enumerate(wrap(note['text'],size,width-2*inset,scale)):
            records.append(text_record(text,width/2,ny+i*size*1.2,size,scale=scale,role='operational-note',block_id='operational-note'))
        bottom=max(t['bbox'][3] for t in records)
    footer_edge=footer_top
    bottom_records=[]
    for block_index,block in reversed(list(enumerate(bottom_notes))):
        if not block.get('evidence'):raise ValueError('Bottom warning/legend needs source evidence')
        size=positive(block.get('size_pt',11));scale=positive(block.get('width_scale',1))
        text=wrap(block['text'],size,width-2*inset,scale)
        baseline=footer_edge-6-size*.299-(len(text)-1)*size*1.2
        local=[text_record(value,width/2,baseline+i*size*1.2,size,scale=scale,role='bottom-note',block_id=f'bottom-note-{block_index}') for i,value in enumerate(text)]
        footer_edge=min(t['bbox'][1] for t in local)
        bottom_records[0:0]=local
    map_bottom=footer_edge-6 if bottom_records else footer_top
    body_top=max(inset,bottom+6,(divider_y or 0)+5)
    reserved=[left,max(0,min(t['bbox'][1] for t in records)),left+header_width,body_top]
    if body_top>=map_bottom-20:raise ValueError('Warning and footer leave no usable map zone at the ordered size')
    safe[3]=map_bottom
    work=[inset,body_top,width-inset,map_bottom] if corner=='full_width' else safe
    regions=[work] if corner=='full_width' else [[inset,body_top,width-inset,map_bottom],
              [reserved[2]+6,inset,width-inset,body_top] if corner=='top_left' else [inset,inset,reserved[0]-6,body_top]]
    holes=placard.get('holes',{})
    unresolved_holes=order.get('holes_requested') is True and (not holes.get('pattern_evidence') or not holes.get('circles'))
    if unresolved_holes and output_mode not in ('map-only','map-labeled'):
        raise ValueError('Holes are requested but their diameter/positions are unconfirmed; supply a source-confirmed hole pattern')
    if unresolved_holes:holes={}
    if order.get('holes_requested') is False and holes.get('circles'):raise ValueError('Order says no holes; supplied hole geometry conflicts with it')
    if holes.get('circles') and not holes.get('pattern_evidence'):raise ValueError('Hole geometry requires pattern_evidence')
    circles=[]
    for circle in holes.get('circles',[]):
        cx,cy=float(circle['cx_pt']),float(circle['cy_pt']);r=positive(circle['diameter_pt'])/2
        if not all(math.isfinite(v) for v in (cx,cy)) or cx-r<0 or cy-r<0 or cx+r>width or cy+r>height:
            raise ValueError('A requested hole is outside the cutline')
        circles.append([cx,cy,r])
    footer_records=[]
    website=footer.get('website','')
    if output_mode in ('map-only','map-labeled') and order.get('branding_restricted'):website=''
    if order.get('branding_restricted') and website:raise ValueError('This order row restricts branding; resolve the website/footer before rendering')
    if website:footer_records.append(text_record(website,footer['margin_x_pt'],height-footer['baseline_from_bottom_pt'],positive(footer['size_pt']),'start',role='footer'))
    part=order['sku']+'-'+digits+'-'+item
    footer_records.append(text_record(part,width-footer['margin_x_pt'],height-footer['baseline_from_bottom_pt'],positive(footer['size_pt']),'end',role='footer-part'))
    if len(footer_records)==2 and footer_records[0]['bbox'][2]+6>footer_records[1]['bbox'][0]:raise ValueError('Footer identifiers do not fit at the required physical size')
    for text in records+bottom_records+footer_records:
        for cx,cy,r in circles:
            if fitz.Rect(text['bbox']).intersects(fitz.Rect(cx-r-2,cy-r-2,cx+r+2,cy+r+2)):
                raise ValueError('Mounting-hole clearance intersects warning/footer text; review the confirmed layout')
    cutline={**data['cutline'],**placard.get('cutline',{})}
    cutline['stroke_pt']=.001 if process['process']=='laser' else 1
    for color in (footer['color'],cutline['color']):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Finishing colors must be explicit six-digit SVG colors')
    return {'profile':name,'nominal_size_in':nominal,'cut_size_pt':[width,height],'size_evidence':size_evidence,
            'warning_style':style_id,'header_zone':reserved,'header_records':records,'divider_y':divider_y,'work_zone':work,
            'bottom_note_records':bottom_records,'bottom_note_zone':[inset,map_bottom,width-inset,footer_top] if bottom_records else None,
            'work_regions':regions,'reserved_header_corner':reserved if corner!='full_width' else None,
            'footer_zone':[0,footer_top,width,height],'footer_records':footer_records,'footer_part_number':part,
            'cutline':cutline,'footer_color':footer['color'],'production_style':process,
            'holes':circles,'include_chrome':output_mode=='finished' if output_mode else placard.get('include_chrome',True),
            'deferred_finishing':['Unconfirmed requested hole pattern; omitted from map output'] if unresolved_holes else []}

def prepare_scene(scene,manifest):
    if not scene.get('placard'):return scene,None
    result=copy.deepcopy(scene);p=plan(result['placard'],result.get('job'),manifest,result.get('output_mode'),result.get('production'))
    layout=result.setdefault('layout',{})
    if layout.get('size_pt') and any(abs(a-b)>.001 for a,b in zip(layout['size_pt'],p['cut_size_pt'])):
        raise ValueError('Scene canvas differs from the ordered cutline size; map scale must be planned in the working zone')
    layout['size_pt']=p['cut_size_pt']
    if 'map_box' not in layout:
        l,t,r,b=p['work_regions'][0];gutter=min(30,(r-l)*.14)
        layout['map_box']=[l+gutter,t+gutter,r-gutter,b-gutter]
    return result,p

def text_svg(record,color):
    """One editable text object per block; tspans hold only its line positions."""
    records=record if isinstance(record,list) else [record]
    first=records[0];scale=first.get('width_scale',1);x=first['x']/scale
    for item in records:
        if any(item.get(k)!=first.get(k) for k in ('size_pt','width_scale','anchor','role')):
            raise ValueError('A text block must retain one consistent text style')
    transform=f' transform="matrix({num(scale)} 0 0 1 0 0)"' if scale!=1 else ''
    if len(records)==1:content=html.escape(first['text'])
    else:
        content=''.join(f'<tspan x="{num(item["x"]/scale)}" y="{num(item["y"])}">{html.escape(item["text"])}</tspan>' for item in records)
    return f'<text data-role="{first["role"]}" x="{num(x)}" y="{num(first["y"])}" font-size="{num(first["size_pt"])}" font-family="Arial,Helvetica,sans-serif" text-anchor="{first["anchor"]}" fill="{color}"{transform}>{content}</text>'


def text_blocks_svg(records,color):
    blocks=[]
    for record in records:
        if blocks and record.get('block_id') and blocks[-1][0].get('block_id')==record['block_id']:
            blocks[-1].append(record)
        else:blocks.append([record])
    return ''.join(text_svg(block,color) for block in blocks)


def circle_path(cx,cy,r):
    k=r*.5522847498307936
    return f'M{num(cx+r)} {num(cy)} C{num(cx+r)} {num(cy+k)} {num(cx+k)} {num(cy+r)} {num(cx)} {num(cy+r)} C{num(cx-k)} {num(cy+r)} {num(cx-r)} {num(cy+k)} {num(cx-r)} {num(cy)} C{num(cx-r)} {num(cy-k)} {num(cx-k)} {num(cy-r)} {num(cx)} {num(cy-r)} C{num(cx+k)} {num(cy-r)} {num(cx+r)} {num(cy-k)} {num(cx+r)} {num(cy)} Z'

def chrome_svg(p,color='#00a651'):
    if not p['include_chrome']:return ''
    color=p.get("production_style",{}).get("ink",color)
    cut_layer="Laser" if p.get("production_style",{}).get("process","laser")=="laser" else "Flex Cut"
    w,h=p['cut_size_pt'];cut=p['cutline'];radius=float(cut.get('corner_radius_pt',0))
    if radius<0 or radius>min(w,h)/2:raise ValueError('Invalid cutline corner radius')
    if radius and not cut.get('shape_evidence'):raise ValueError('Rounded cutline needs shape_evidence')
    if radius:
        r=radius;k=r*.5522847498307936
        d=f'M{num(r)} 0 L{num(w-r)} 0 C{num(w-r+k)} 0 {num(w)} {num(r-k)} {num(w)} {num(r)} L{num(w)} {num(h-r)} C{num(w)} {num(h-r+k)} {num(w-r+k)} {num(h)} {num(w-r)} {num(h)} L{num(r)} {num(h)} C{num(r-k)} {num(h)} 0 {num(h-r+k)} 0 {num(h-r)} L0 {num(r)} C0 {num(r-k)} {num(r-k)} 0 {num(r)} 0 Z'
    else:d=f'M0 0 L{num(w)} 0 L{num(w)} {num(h)} L0 {num(h)} Z'
    out=[f'<path id="cutline" data-role="cutline" data-production-layer="{cut_layer}" d="{d}" fill="none" stroke="{cut["color"]}" stroke-width="{num(positive(cut["stroke_pt"]))}"/>']
    for i,(cx,cy,r) in enumerate(p['holes']):out.append(f'<path id="hole-{i+1}" data-role="cutline" data-production-layer="{cut_layer}" d="{circle_path(cx,cy,r)}" fill="none" stroke="{cut["color"]}" stroke-width="{num(positive(cut["stroke_pt"]))}"/>')
    out.append(text_blocks_svg(p['header_records'],color))
    out.append(text_blocks_svg(p.get('bottom_note_records',[]),color))
    if p['divider_y'] is not None:
        y=p['divider_y'];out.append(f'<path data-role="warning-divider" d="M0 {num(y)} L{num(w)} {num(y)}" fill="none" stroke="{color}" stroke-width="0.5"/>')
    out.append(text_blocks_svg(p['footer_records'],p['footer_color']))
    return ''.join(out)

def validate_map_svg(body,box,p):
    """Reject artwork crossing reserved zones; never mask it or enlarge the plate."""
    bounds=[]
    def path_parts(d):
        tokens=re.findall(r'[MLCZ]|[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?',d);i=0;prev=first=None
        while i<len(tokens):
            cmd=tokens[i];i+=1;count={'M':2,'L':2,'C':6,'Z':0}[cmd];v=list(map(float,tokens[i:i+count]));i+=count
            if cmd=='M':prev=first=(v[0],v[1]);continue
            pts=[prev,*list(zip(v[::2],v[1::2]))] if cmd!='Z' else [prev,first]
            yield pts
            prev=pts[-1]
    def walk(node,dx=0,dy=0):
        tag=node.tag.split('}')[-1];matrix=[1,0,0,1,0,0]
        transform=node.get('transform','')
        if transform:
            tr=re.fullmatch(r'translate\(([-\d.eE]+)[ ,]+([-\d.eE]+)\)',transform)
            mt=re.fullmatch(r'matrix\(([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)[ ,]+([-\d.eE]+)\)',transform)
            if tr:dx+=float(tr[1]);dy+=float(tr[2])
            elif mt and tag=='text':matrix=list(map(float,mt.groups()))
            else:raise ValueError('Unsupported transform in map-zone validation')
        if tag in ('svg','g'):
            for child in node:walk(child,dx,dy)
        elif tag=='path':
            pad=float(node.get('stroke-width',1))/2 if node.get('stroke','none')!='none' else 0
            for part in path_parts(node.get('d','')):
                points=[(x+dx,y+dy) for x,y in part];xs,ys=zip(*points)
                bounds.append((fitz.Rect(min(xs)-pad,min(ys)-pad,max(xs)+pad,max(ys)+pad),'path',points,pad))
        elif tag=='text':
            lines=list(node) if len(node) else [node]
            for line in lines:
                if line is not node and (line.tag.split('}')[-1]!='tspan' or len(line)):
                    raise ValueError('Text blocks require flat positioned tspans')
                text=line.text or '';size=positive(node.get('font-size',13))
                x=float(line.get('x',node.get('x',0)));y=float(line.get('y',node.get('y',0)))
                r=text_record(text,x,y,size,node.get('text-anchor','start'))
                l,t,rr,b=r['bbox'];a,bb,c,d,e,f=matrix
                pts=[(a*xx+c*yy+e+dx,bb*xx+d*yy+f+dy) for xx,yy in ((l,t),(rr,t),(rr,b),(l,b))]
                bounds.append((fitz.Rect(min(xx for xx,yy in pts),min(yy for xx,yy in pts),max(xx for xx,yy in pts),max(yy for xx,yy in pts)),'text',None,0))
    walk(ET.fromstring('<svg>'+body+'</svg>'))
    work=fitz.Rect(p['work_zone']);corner=fitz.Rect(p['reserved_header_corner']) if p['reserved_header_corner'] else None
    issues=[]
    def segment_hits(points,rect,pad=0):
        rect=rect+(-pad,-pad,pad,pad)
        if len(points)!=2:return fitz.Rect(min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)).intersects(rect)
        (x,y),(xx,yy)=points;t0,t1=0.0,1.0
        for a,b,c,d in ((x,xx,rect.x0,rect.x1),(y,yy,rect.y0,rect.y1)):
            if abs(b-a)<1e-10:
                if not c<=a<=d:return False
            else:
                lo,hi=sorted(((c-a)/(b-a),(d-a)/(b-a)));t0=max(t0,lo);t1=min(t1,hi)
                if t0>t1:return False
        return True
    for r,kind,points,pad in bounds:
        if not (work+(-.05,-.05,.05,.05)).contains(r):issues.append(f'{kind} outside map/callout working zone')
        if corner and (segment_hits(points,corner,pad) if points else r.intersects(corner)):
            issues.append(f'{kind} overlaps the reserved directory-title corner')
        for cx,cy,radius in p['holes']:
            hole=fitz.Rect(cx-radius-2,cy-radius-2,cx+radius+2,cy+radius+2)
            if segment_hits(points,hole,pad) if points else r.intersects(hole):issues.append(f'{kind} enters mounting-hole clearance')
    if issues:raise ValueError('Zone layout needs review: '+', '.join(sorted(set(issues)))+'. Reposition content within the ordered size; do not scale physical strokes or enlarge the cutline.')
    return {'map_objects_checked':len(bounds),'reserved_zone_collisions':0,'physical_size_verified':True}

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    scan=sub.add_parser('analyze-order');scan.add_argument('source');scan.add_argument('--work-order',required=True);scan.add_argument('--output')
    planning=sub.add_parser('plan');planning.add_argument('scene');planning.add_argument('--output')
    args=parser.parse_args()
    if args.command=='analyze-order':result=analyze_order_pdf(args.source,args.work_order)
    else:
        scene=json.loads(Path(args.scene).read_text(encoding='utf8'));result=plan(scene['placard'],scene.get('job'),output_mode=scene.get('output_mode'),production=scene.get('production'))
    if args.output:Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
