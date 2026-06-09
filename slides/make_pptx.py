"""
Build presentation.pptx from the ITMO template without python-pptx.
Uses the template's slide master/layouts/media and builds slides as XML.
"""
import zipfile, shutil, os, io, re

TEMPLATE = '/tmp/example_full'  # extracted template
OUT_PATH = os.path.join(os.path.dirname(__file__), 'presentation.pptx')
IMAGES   = os.path.join(os.path.dirname(__file__), 'images')

W = 9144000   # slide width  (EMU)
H = 5143500   # slide height (EMU)
def ex(pct): return int(pct / 100 * W)
def ey(pct): return int(pct / 100 * H)
def ei(inch): return int(inch * 914400)

# --- XML namespaces ---
NS_A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
NS_P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
NS_R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

# --- Colors ---
C_PURPLE = '7030A0'
C_TITLE  = '272424'
C_BODY   = '2C2D2E'
C_WHITE  = 'FFFFFF'
C_LGRAY  = 'CCCCCC'
C_LPURP  = 'E8E0F0'

# =========================================================
# Shape helpers: return XML strings
# =========================================================
_shape_id = [100]

def _sid():
    _shape_id[0] += 1
    return _shape_id[0]

def _rpr(sz, bold=False, color=C_BODY, italic=False, lang='ru-RU'):
    b = ' b="1"' if bold else ''
    i = ' i="1"' if italic else ''
    return (f'<a:rPr lang="{lang}" sz="{sz}" dirty="0"{b}{i}>'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'</a:rPr>')

def txbox(x, y, w, h, paragraphs, wrap='square'):
    """
    paragraphs: list of (text, sz, bold, color, italic, align)
    align: 'l','c','r'
    """
    sid = _sid()
    paras = ''
    for item in paragraphs:
        if isinstance(item, str):
            item = (item, 1300, False, C_BODY, False, 'l')
        while len(item) < 6:
            item = item + (False,) if len(item) == 5 else item + ('l',)
        txt, sz, bold, color, italic, align = item
        algn = {'l': 'l', 'c': 'ctr', 'r': 'r'}.get(align, 'l')
        algn_attr = f' algn="{algn}"' if align != 'l' else ''
        rpr = _rpr(sz, bold, color, italic)
        paras += f'<a:p><a:pPr{algn_attr}/><a:r>{rpr}<a:t>{_esc(txt)}</a:t></a:r></a:p>'
    return f'''<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="{sid}" name="tb{sid}"/>
    <p:cNvSpPr txBox="1"><a:spLocks noGrp="1"/></p:cNvSpPr>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:noFill/>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="{wrap}" rtlCol="0"><a:normAutofit/></a:bodyPr>
    <a:lstStyle/>
    {paras}
  </p:txBody>
</p:sp>'''

def filled_rect(x, y, w, h, fill, line_color=None):
    sid = _sid()
    line = f'<a:ln><a:noFill/></a:ln>' if line_color is None else \
           f'<a:ln><a:solidFill><a:srgbClr val="{line_color}"/></a:solidFill></a:ln>'
    return f'''<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="{sid}" name="rc{sid}"/>
    <p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>
    {line}
  </p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
</p:sp>'''

def picture_shape(x, y, w, h, rid):
    sid = _sid()
    return f'''<p:pic>
  <p:nvPicPr>
    <p:cNvPr id="{sid}" name="img{sid}"/>
    <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
    <p:nvPr/>
  </p:nvPicPr>
  <p:blipFill>
    <a:blip r:embed="{rid}"/>
    <a:stretch><a:fillRect/></a:stretch>
  </p:blipFill>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
  </p:spPr>
</p:pic>'''

def slide_num_box(num):
    """Purple box in top-right with slide number."""
    bw = ex(5.5); bh = ey(6.8); bx = W - bw
    sid = _sid()
    return f'''<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="{sid}" name="num{sid}"/>
    <p:cNvSpPr txBox="1"><a:spLocks noGrp="1"/></p:cNvSpPr>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{bx}" y="0"/><a:ext cx="{bw}" cy="{bh}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:solidFill><a:srgbClr val="{C_PURPLE}"/></a:solidFill>
    <a:ln><a:noFill/></a:ln>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" anchor="ctr"><a:normAutofit/></a:bodyPr>
    <a:lstStyle/>
    <a:p><a:pPr algn="ctr"/>
      <a:r><a:rPr lang="ru-RU" sz="1600" b="1" dirty="0">
        <a:solidFill><a:srgbClr val="{C_WHITE}"/></a:solidFill>
      </a:rPr><a:t>{num}</a:t></a:r>
    </a:p>
  </p:txBody>
</p:sp>'''

def title_bar(text):
    """Dark title bar left side of slide (74.6% wide)."""
    tw = ex(74.6); th = ey(10.3); ty = ey(1.0)
    sid = _sid()
    return f'''<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="{sid}" name="ttl{sid}"/>
    <p:cNvSpPr txBox="1"><a:spLocks noGrp="1"/></p:cNvSpPr>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{ei(0.45)}" y="{ty}"/><a:ext cx="{tw}" cy="{th}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:noFill/>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" anchor="ctr"><a:normAutofit/></a:bodyPr>
    <a:lstStyle/>
    <a:p><a:r>
      <a:rPr lang="ru-RU" sz="2200" b="1" dirty="0">
        <a:solidFill><a:srgbClr val="{C_TITLE}"/></a:solidFill>
      </a:rPr>
      <a:t>{_esc(text)}</a:t>
    </a:r></a:p>
  </p:txBody>
</p:sp>'''

def bg_fill(rid):
    """Slide background fill from image."""
    return f'''<p:bg>
  <p:bgPr>
    <a:blipFill dpi="0" rotWithShape="1">
      <a:blip r:embed="{rid}"><a:lum/></a:blip>
      <a:srcRect/>
      <a:stretch><a:fillRect/></a:stretch>
    </a:blipFill>
    <a:effectLst/>
  </p:bgPr>
</p:bg>'''

def build_slide(shapes_xml, bg_xml=''):
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld {NS_A} {NS_P} {NS_R}>
  <p:cSld>
    {bg_xml}
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="{W}" cy="{H}"/>
        <a:chOff x="0" y="0"/><a:chExt cx="{W}" cy="{H}"/></a:xfrm>
      </p:grpSpPr>
      {''.join(shapes_xml)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''

def _esc(s):
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def slide_rels(layout_id, extra_rels=''):
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
    Target="../slideLayouts/slideLayout{layout_id}.xml"/>
  {extra_rels}
</Relationships>'''

def image_rel(rid, target):
    return f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{target}"/>'

# =========================================================
# Content area shortcuts
# =========================================================
CA_X = ei(0.45)      # content left
CA_Y = ey(14.5)      # content top (below title bar)
CA_W = ex(91)        # content width
CA_H = ey(80)        # content height
C1_W = int(CA_W * 0.50)   # left column width
C2_X = CA_X + int(CA_W * 0.53)  # right column start
C2_W = int(CA_W * 0.45)  # right column width

def block(x, y, w, h, title, body, title_color=C_PURPLE, fill=C_LPURP):
    shapes = []
    shapes.append(filled_rect(x, y, w, h, fill))
    shapes.append(txbox(x+ei(0.1), y+ey(0.5), w-ei(0.2), ey(4),
                        [(title, 1200, True, title_color, False, 'l')]))
    shapes.append(txbox(x+ei(0.1), y+ey(5), w-ei(0.2), h-ey(6),
                        [(body, 1050, False, C_BODY, False, 'l')]))
    return shapes

def table_header(cols, col_xs, col_ws, y, row_h=ey(5.5)):
    shapes = []
    for (hd, x, w) in zip(cols, col_xs, col_ws):
        shapes.append(filled_rect(x, y, w-ei(0.04), row_h, 'D8C8EC'))
        shapes.append(txbox(x+ei(0.06), y+ei(0.04), w-ei(0.12), row_h-ei(0.04),
                            [(hd, 1050, True, C_TITLE, False, 'c')]))
    return shapes

def table_row(cells, col_xs, col_ws, y, row_h=ey(5.5), bg='FFFFFF', colors=None):
    shapes = []
    for i, (cell, x, w) in enumerate(zip(cells, col_xs, col_ws)):
        shapes.append(filled_rect(x, y, w-ei(0.04), row_h, bg))
        c = colors[i] if colors and i < len(colors) else C_BODY
        shapes.append(txbox(x+ei(0.06), y+ei(0.04), w-ei(0.12), row_h-ei(0.04),
                            [(cell, 1050, False, c, False, 'c')]))
    return shapes

# =========================================================
# BUILD SLIDES
# =========================================================
slides_data = []   # list of (slide_xml, slide_rels_xml, extra_media)

# --- extra_media: list of (rid, src_path) ---

# =========================================================
# SLIDE 1 — TITLE (dark bg)
# =========================================================
_shape_id[0] = 100
shapes = []
shapes.append(txbox(ei(1.5), ey(2.5), ex(73), ey(6),
    [('Защита выпускной квалификационной работы', 1400, False, C_WHITE, False, 'c')]))
shapes.append(txbox(ei(0.8), ey(10), ex(85), ey(5),
    [('Факультет систем управления и робототехники   ·   Университет ИТМО',
      1100, False, C_LGRAY, False, 'c')]))
shapes.append(txbox(ei(1.2), ey(28), ex(76), ey(22),
    [('Исследование применения обучения с подкреплением для повышения эффективности управления роботами '
      'с использованием визуально-языковых моделей', 1800, True, C_WHITE, False, 'c')]))
shapes.append(txbox(ei(1.2), ey(52), ex(76), ey(6),
    [('Направление подготовки: 09.03.04  Программная инженерия',
      1200, False, C_LGRAY, False, 'c')]))
shapes.append(txbox(ei(5.2), ey(62), ex(45), ey(14),
    [('Студент: Новичков Дмитрий Евгеньевич, гр. 3435', 1200, False, C_WHITE, False, 'l'),
     ('Научный руководитель: Ведяков А.А., к.т.н., доцент ФСУиР', 1200, False, C_WHITE, False, 'l')]))
shapes.append(txbox(ei(3.5), ey(90), ex(32), ey(6),
    [('Санкт-Петербург, 2026', 1100, False, C_LGRAY, False, 'c')]))

sxml = build_slide(shapes, bg_fill('rId2'))
srels = slide_rels(1, image_rel('rId2', '../media/image19.jpg'))
slides_data.append((sxml, srels, []))

# =========================================================
# SLIDE 2 — Актуальность
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(2), title_bar('Актуальность')]

shapes.append(txbox(CA_X, CA_Y, C1_W, ey(6.5),
    [('Визуально-языковые модели действий (VLA) — класс моделей, объединяющих восприятие, '
      'понимание языка и управление роботом.', 1200, False, C_BODY, False, 'l')]))
items = ['•  Текущая эффективность: 70–80% на стандартных задачах',
         '•  RL — перспективный метод для преодоления этого разрыва',
         '•  Экспоненциальный рост публикаций: ×18 за 2 года']
for i, t in enumerate(items):
    shapes.append(txbox(CA_X, CA_Y+ey(7.5)+ei(0.5)*i, C1_W, ey(5),
        [(t, 1150, False, C_BODY, False, 'l')]))

# table block
shapes.append(filled_rect(C2_X, CA_Y, C2_W, ey(34), C_LPURP))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(0.5), C2_W-ei(0.2), ey(4.5),
    [('Динамика публикаций VLA', 1250, True, C_TITLE, False, 'l')]))
rows_data = [('Конференция','Количество работ'), ('ICLR 2024','1'), ('ICLR 2025','47'), ('ICLR 2026','164')]
row_bg = ['D8C8EC','FFFFFF','F8F4FC','FFFFFF']
for ri, (a, b) in enumerate(rows_data):
    ry = CA_Y+ey(6)+ey(6.5)*ri
    shapes.append(filled_rect(C2_X+ei(0.05), ry, C2_W-ei(0.1), ey(6), row_bg[ri]))
    shapes.append(txbox(C2_X+ei(0.15), ry+ey(0.5), int(C2_W*0.55), ey(5),
        [(a, 1100, ri==0, C_TITLE, False, 'l')]))
    clr = C_PURPLE if ri==3 else C_TITLE
    shapes.append(txbox(C2_X+int(C2_W*0.6), ry+ey(0.5), int(C2_W*0.35), ey(5),
        [(b, 1100, ri==3, clr, False, 'c')]))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(32), C2_W-ei(0.2), ey(4),
    [('×18 за 2 года', 1400, True, C_PURPLE, False, 'c')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 3 — Цель и задачи
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(3), title_bar('Цель и задачи исследования')]

bh = ey(14)
shapes.append(filled_rect(CA_X, CA_Y, C1_W, bh, C_LPURP))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(0.8), C1_W-ei(0.2), ey(4),
    [('Цель', 1250, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(5.5), C1_W-ei(0.2), ey(8),
    [('Разработка методических рекомендаций по применению RL для обучения '
      'и дообучения VLA-моделей в задачах манипулирования.',
      1100, False, C_BODY, False, 'l')]))

bh2 = ey(13)
shapes.append(filled_rect(CA_X, CA_Y+ey(15.5), C1_W, bh2, 'F5F0FB'))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(16.3), C1_W-ei(0.2), ey(4),
    [('Объект: методы интеграции RL и VLM/VLA', 1100, False, C_BODY, False, 'l')]))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(21), C1_W-ei(0.2), ey(4),
    [('Предмет: эффективность управления манипулятором в симуляции',
      1100, False, C_BODY, False, 'l')]))

shapes.append(txbox(C2_X, CA_Y, C2_W, ey(5),
    [('Задачи:', 1250, True, C_TITLE, False, 'l')]))
tasks = ['1. Аналитический обзор VLA-моделей (2022–2026 гг.)',
         '2. Классификация методов интеграции RL и VLM по трём направлениям',
         '3. Разработка методики вычислительного эксперимента',
         '4. Реализация прототипа: генерация функций вознаграждения с помощью VLM',
         '5. Четыре серии экспериментов на MetaWorld и LIBERO',
         '6. Анализ результатов и формулировка рекомендаций']
for i, t in enumerate(tasks):
    shapes.append(txbox(C2_X, CA_Y+ey(6.5)+ey(8.5)*i, C2_W, ey(7.5),
        [(t, 1100, False, C_BODY, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 4 — VLA-модели
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(4), title_bar('Обзор визуально-языковых моделей действий')]

shapes.append(txbox(CA_X, CA_Y, CA_W, ey(4.5),
    [('Три архитектурных класса VLA-моделей', 1250, True, C_TITLE, False, 'l')]))

col_xs = [CA_X, CA_X+ex(23), CA_X+ex(56)]
col_ws = [ex(22), ex(32), ex(33)]
hs = table_header(['Класс', 'Модели', 'Результат'], col_xs, col_ws, CA_Y+ey(5.5))
shapes.extend(hs)
rows4 = [('Авторегрессионные', 'RT-2 (55B), OpenVLA (7B)', 'OpenVLA: +16,5 п.п. над RT-2-X'),
         ('Диффузионные', 'π₀, FLOWER (950M)', 'FLOWER: лучший на CALVIN'),
         ('Дискр.-диффузионные', 'dVLA, DiVA', '95–98% на LIBERO')]
for ri, row in enumerate(rows4):
    bg = 'FFFFFF' if ri % 2 == 0 else 'F8F4FC'
    shapes.extend(table_row(row, col_xs, col_ws, CA_Y+ey(12)+ey(8.5)*ri, bg=bg))

shapes.append(txbox(CA_X, CA_Y+ey(42), C1_W, ey(5),
    [('Тенденции:', 1200, True, C_TITLE, False, 'l')]))
for i, t in enumerate(['• Масштаб: 7B – 55B+ параметров',
                        '• Открытые модели конкурентоспособны на бенчмарках',
                        '• Закрытые (π₀.₅, Gemini Robotics) лидируют в обобщении']):
    shapes.append(txbox(CA_X, CA_Y+ey(47)+ey(6)*i, C1_W, ey(5.5),
        [(t, 1100, False, C_BODY, False, 'l')]))

shapes.append(filled_rect(C2_X, CA_Y+ey(42), C2_W, ey(22), C_LPURP))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(43), C2_W-ei(0.2), ey(4.5),
    [('Проблема и решение', 1200, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(49), C2_W-ei(0.2), ey(14),
    [('VLA-модели, обученные на демонстрациях, достигают потолка без '
      'механизма улучшения из взаимодействия со средой.\n'
      'Решение: интеграция с обучением с подкреплением.',
      1100, False, C_BODY, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 5 — Три направления
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(5), title_bar('Три направления интеграции RL и VLM')]

col_xs5 = [CA_X, CA_X+ex(24), CA_X+ex(54), CA_X+ex(83)]
col_ws5 = [ex(23), ex(29), ex(28), ex(12)]
shapes.extend(table_header(['Направление', 'Идея', 'Лучший результат', 'Работа'],
                             col_xs5, col_ws5, CA_Y))
rows5 = [('RL-дообучение VLA', 'RL уточняет готовую VLA-политику',
          '98–99% доля успехов', 'PLD, STARE'),
         ('VLM → награда', 'VLM генерирует функцию вознаграждения',
          'Лучше эксперта на 83% задач', 'EUREKA'),
         ('VLM-планировщик', 'VLM ставит подзадачи; RL исполняет',
          '87,5% на реальном роботе', 'Embodied-R1')]
for ri, row in enumerate(rows5):
    bg = 'FFFFFF' if ri % 2 == 0 else 'F8F4FC'
    shapes.extend(table_row(row, col_xs5, col_ws5,
                            CA_Y+ey(6.5)+ey(9)*ri, bg=bg, row_h=ey(8.5)))

shapes.append(filled_rect(CA_X, CA_Y+ey(37), CA_W, ey(14), C_LPURP))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(38), CA_W-ei(0.2), ey(4.5),
    [('Вывод систематического обзора', 1200, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(44), CA_W-ei(0.2), ey(6),
    [('Каждое направление подходит для своих условий. Выбор определяется '
      'наличием предобученной модели, доступными ресурсами и типом задачи.',
      1100, False, C_BODY, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 6 — Постановка эксперимента
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(6), title_bar('Постановка эксперимента')]

shapes.append(filled_rect(CA_X, CA_Y, C1_W, ey(12), C_LPURP))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(0.8), C1_W-ei(0.2), ey(4.5),
    [('Исследуемое направление', 1200, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(6), C1_W-ei(0.2), ey(5.5),
    [('VLM-генерация функций вознаграждения для RL', 1200, False, C_BODY, False, 'l')]))

shapes.append(txbox(CA_X, CA_Y+ey(14), C1_W, ey(5),
    [('Обоснование:', 1200, True, C_TITLE, False, 'l')]))
reasons = ['• Не требует VLA-модели в 7–55B параметров',
           '• Решает фундаментальную проблему задания наград',
           '• Совместим с любыми RL-алгоритмами (PPO, SAC)',
           '• Дополнительно: воспроизведение OpenVLA-OFT на LIBERO']
for i, r in enumerate(reasons):
    shapes.append(txbox(CA_X, CA_Y+ey(20)+ey(7.5)*i, C1_W, ey(7),
        [(r, 1100, False, C_BODY, False, 'l')]))

shapes.append(filled_rect(C2_X, CA_Y, C2_W, ey(35), 'F5F0FB'))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(0.8), C2_W-ei(0.2), ey(4.5),
    [('Три задачи MetaWorld', 1200, True, C_TITLE, False, 'l')]))
for i, (nm, desc) in enumerate([('1. reach-v3', 'достичь точку  (простая)'),
                                  ('2. push-v3', 'толкнуть кубик  (средняя)'),
                                  ('3. pick-place-v3', 'взять и перенести  (сложная)')]):
    shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(7)+ey(8.5)*i, C2_W-ei(0.2), ey(4.5),
        [(nm, 1200, True, C_PURPLE, False, 'l')]))
    shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(12)+ey(8.5)*i, C2_W-ei(0.2), ey(4),
        [(desc, 1100, False, C_BODY, False, 'l')]))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(33), C2_W-ei(0.2), ey(4),
    [('Алгоритмы: PPO и SAC   |   Бюджет: 500 000 шагов, ≥3 запуска',
      1100, False, C_BODY, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 7 — Архитектура
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(7), title_bar('Архитектура программного прототипа')]

comps = [
    ('1. Модуль генерации вознаграждения',
     'Языковая модель принимает инструкцию и описание API среды, возвращает Python-функцию'),
    ('2. RL-агент (PPO или SAC)',
     'Обучается в среде с автоматически сгенерированной функцией вознаграждения'),
    ('3. Среда симуляции',
     'MetaWorld (MT10) или LIBERO'),
]
for i, (nm, desc) in enumerate(comps):
    shapes.append(txbox(CA_X, CA_Y+ey(1)+ey(19)*i, C1_W, ey(5.5),
        [(nm, 1200, True, C_PURPLE, False, 'l')]))
    shapes.append(txbox(CA_X, CA_Y+ey(7)+ey(19)*i, C1_W, ey(9),
        [(desc, 1100, False, C_BODY, False, 'l')]))

shapes.append(filled_rect(C2_X, CA_Y, C2_W, ey(38), 'F5F0FB'))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(0.8), C2_W-ei(0.2), ey(4.5),
    [('Протокол', 1300, True, C_TITLE, False, 'l')]))
proto = ['• 4 серии, ≈18 запусков на серию',
         '• 500 000 шагов взаимодействия',
         '• Оценка каждые 10 000 шагов (10 эпизодов)',
         '• 5 метрик: SR, шагов до 80%, КВ, ρ(R,S), практичность']
for i, p in enumerate(proto):
    shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(7)+ey(6.5)*i, C2_W-ei(0.2), ey(6),
        [(p, 1100, False, C_BODY, False, 'l')]))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(35.5), C2_W-ei(0.2), ey(4.5),
    [('Суммарно проведено более 70 обучающих запусков', 1200, True, C_PURPLE, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 8 — Серии 1–2 (with image)
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(8), title_bar('Серии 1–2: Базовые линии')]

col8_xs = [CA_X, CA_X+ex(22), CA_X+ex(40), CA_X+ex(57)]
col8_ws = [ex(21), ex(17), ex(16), ex(16)]
shapes.extend(table_header(['Задача','Экспертная','Разреженная','Δ'],
                             col8_xs, col8_ws, CA_Y))
rows8 = [('reach-v3','100%','100%','0 п.п.'),
         ('push-v3','83%','7%','+76 п.п.'),
         ('pick-place-v3','47%','0%','+47 п.п.')]
colors8 = [[C_BODY,C_BODY,C_BODY,C_BODY],
           [C_BODY,C_PURPLE,C_BODY,C_PURPLE],
           [C_BODY,C_PURPLE,C_BODY,C_PURPLE]]
for ri, (row, cols) in enumerate(zip(rows8, colors8)):
    bg = 'FFFFFF' if ri%2==0 else 'F8F4FC'
    shapes.extend(table_row(row, col8_xs, col8_ws,
                            CA_Y+ey(6.5)+ey(7.5)*ri, bg=bg, colors=cols))

shapes.append(txbox(CA_X, CA_Y+ey(29), C1_W, ey(4.5),
    [('SAC, среднее по 3 независимым запускам', 1050, False, C_BODY, True, 'l')]))

shapes.append(filled_rect(CA_X, CA_Y+ey(35), C1_W, ey(18), C_LPURP))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(36), C1_W-ei(0.2), ey(4.5),
    [('Вывод', 1200, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(41.5), C1_W-ei(0.2), ey(11),
    [('Разреженная награда достаточна только для задач без контактной динамики. '
      'Разрыв с экспертной: push +76 п.п., pick-place +47 п.п.',
      1050, False, C_BODY, False, 'l')]))

shapes.append(picture_shape(C2_X, CA_Y, C2_W, ey(55), 'rId2'))

sxml = build_slide(shapes)
srels = slide_rels(1, image_rel('rId2', '../media/img_sr_bar.png'))
slides_data.append((sxml, srels,
    [('img_sr_bar.png', os.path.join(IMAGES, 'success_rate_bar.png'))]))

# =========================================================
# SLIDE 9 — Кривые обучения
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(9), title_bar('Кривые обучения: базовые линии')]

shapes.append(picture_shape(CA_X, CA_Y, CA_W, ey(55), 'rId2'))
shapes.append(txbox(CA_X, CA_Y+ey(57), CA_W, ey(10),
    [('Слева направо: reach-v3, push-v3, pick-place-v3. Каждая линия — один '
      'независимый запуск. Высокая нестабильность на push-v3; '
      'отсутствие обучающего сигнала на pick-place-v3 при разреженной награде.',
      1050, False, C_BODY, True, 'l')]))

sxml = build_slide(shapes)
srels = slide_rels(1, image_rel('rId2', '../media/img_lc.png'))
slides_data.append((sxml, srels,
    [('img_lc.png', os.path.join(IMAGES, 'learning_curves_by_task.png'))]))

# =========================================================
# SLIDE 10 — VLM функции
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(10), title_bar('Серия 3: Сгенерированные функции вознаграждения')]

shapes.append(txbox(CA_X, CA_Y, CA_W, ey(5),
    [('Языковая модель получает описание задачи и API среды, возвращает исполняемый Python-код:',
      1200, False, C_BODY, False, 'l')]))

funcs = [('reach-v3', 'R = −‖ee − goal‖ − 0.01‖a‖'),
         ('push-v3', 'R = −‖ee − obj‖ − ‖obj − goal‖ − 0.01‖a‖'),
         ('pick-place-v3', 'R = −‖ee − obj‖ − ‖obj − goal‖ + 0.1·grip − 0.01‖a‖')]
for i, (nm, formula) in enumerate(funcs):
    bx = CA_X + int(i * CA_W / 3) + ei(0.05)
    bw = int(CA_W / 3) - ei(0.1)
    bh = ey(22)
    shapes.append(filled_rect(bx, CA_Y+ey(7), bw, bh, C_LPURP))
    shapes.append(txbox(bx+ei(0.1), CA_Y+ey(8), bw-ei(0.2), ey(5.5),
        [(nm, 1200, True, C_PURPLE, False, 'l')]))
    shapes.append(txbox(bx+ei(0.1), CA_Y+ey(14), bw-ei(0.2), ey(13),
        [(formula, 1100, False, C_BODY, False, 'l')]))

shapes.append(filled_rect(CA_X, CA_Y+ey(32), CA_W, ey(22), C_LPURP))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(33), CA_W-ei(0.2), ey(5),
    [('Ограничение первой итерации', 1200, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(39), CA_W-ei(0.2), ey(13),
    [('Функции построены только на евклидовых расстояниях. Стадийные термы (контакт, захват, '
      'перемещение) отсутствуют — их наличие необходимо для контактных задач.',
      1100, False, C_BODY, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 11 — Результаты серии 3
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(11), title_bar('Серия 3: Результаты и анализ')]

col11_xs = [CA_X, CA_X+ex(28), CA_X+ex(43)]
col11_ws = [ex(27), ex(14), ex(14)]
shapes.extend(table_header(['Задача','PPO','SAC'], col11_xs, col11_ws, CA_Y))
rows11 = [('reach-v3','71,7%','100%'),('push-v3','0%','0%'),('pick-place-v3','0%','0%')]
colors11 = [[C_BODY,C_BODY,C_PURPLE],[C_BODY,C_BODY,C_BODY],[C_BODY,C_BODY,C_BODY]]
for ri, (row, cols) in enumerate(zip(rows11, colors11)):
    bg = 'FFFFFF' if ri%2==0 else 'F8F4FC'
    shapes.extend(table_row(row, col11_xs, col11_ws,
                            CA_Y+ey(6.5)+ey(7.5)*ri, bg=bg, colors=cols))

shapes.append(txbox(CA_X, CA_Y+ey(31), C1_W, ey(5),
    [('Корреляция ρ(R,S):', 1200, True, C_TITLE, False, 'l')]))
shapes.append(txbox(CA_X, CA_Y+ey(37), C1_W, ey(6),
    [('• reach-v3 (SAC):  0,97 — высокая', 1100, False, C_BODY, False, 'l')]))
shapes.append(txbox(CA_X, CA_Y+ey(43), C1_W, ey(6),
    [('• push-v3:         0,12 — нет связи', 1100, False, C_BODY, False, 'l')]))
shapes.append(txbox(CA_X, CA_Y+ey(51), C1_W, ey(9),
    [('SAC (+28 п.п. над PPO): буфер опыта сглаживает нестабильность '
      'автоматически сгенерированной награды.', 1050, False, C_BODY, True, 'l')]))

shapes.append(picture_shape(C2_X, CA_Y, C2_W, ey(57), 'rId2'))

sxml = build_slide(shapes)
srels = slide_rels(1, image_rel('rId2', '../media/img_t2r.png'))
slides_data.append((sxml, srels,
    [('img_t2r.png', os.path.join(IMAGES, 't2r_comparison_vs_baseline.png'))]))

# =========================================================
# SLIDE 12 — VLA на LIBERO
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(12), title_bar('Серия 4: OpenVLA-OFT на LIBERO')]

shapes.append(txbox(CA_X, CA_Y, C1_W, ey(6),
    [('OpenVLA-OFT (7B параметров), дообученная на демонстрациях LIBERO:',
      1200, False, C_BODY, False, 'l')]))

col12_xs = [CA_X, CA_X+ex(28), CA_X+ex(42)]
col12_ws = [ex(27), ex(13), ex(13)]
shapes.extend(table_header(['Набор задач','Получено','Статья'], col12_xs, col12_ws, CA_Y+ey(7)))
rows12 = [('LIBERO-Object','100,0%','98,8%'),
          ('LIBERO-Spatial','93,0%','98,8%'),
          ('Среднее','96,5%','98,8%')]
row_bgs12 = ['FFFFFF','F8F4FC','ECE8F5']
row_clrs12 = [[C_BODY,C_PURPLE,C_BODY],[C_BODY,C_BODY,C_BODY],[C_BODY,C_PURPLE,C_BODY]]
for ri, (row, bg, cols) in enumerate(zip(rows12, row_bgs12, row_clrs12)):
    shapes.extend(table_row(row, col12_xs, col12_ws,
                            CA_Y+ey(14)+ey(7.5)*ri, bg=bg, colors=cols))

shapes.append(txbox(CA_X, CA_Y+ey(39), C1_W, ey(8),
    [('Расхождение −2,3 п.п. в пределах погрешности (10 эпизодов вместо 50 в оригинале)',
      1050, False, C_BODY, True, 'l')]))

shapes.append(picture_shape(C2_X, CA_Y, C2_W, ey(46), 'rId2'))

shapes.append(filled_rect(C2_X, CA_Y+ey(48), C2_W, ey(18), C_LPURP))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(49), C2_W-ei(0.2), ey(5),
    [('Значение', 1200, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(55), C2_W-ei(0.2), ey(10),
    [('96,5% — отправная точка для RL-дообучения. RL устраняет оставшиеся 3,5–7% ошибок.',
      1050, False, C_BODY, False, 'l')]))

sxml = build_slide(shapes)
srels = slide_rels(1, image_rel('rId2', '../media/img_vla.png'))
slides_data.append((sxml, srels,
    [('img_vla.png', os.path.join(IMAGES, 'vla_libero_success_rates.png'))]))

# =========================================================
# SLIDE 13 — Симуляции
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(13), title_bar('OpenVLA-OFT: симуляции выполнения задач')]

# Big comparison image
img_h = ey(73)
img_w = int(img_h * 1042 / 1002)   # preserve aspect ratio
img_x = CA_X + (CA_W - img_w) // 2
shapes.append(picture_shape(img_x, CA_Y, img_w, img_h, 'rId2'))

shapes.append(txbox(CA_X, CA_Y + img_h + ey(1), CA_W, ey(6), [
    ('Зелёный фон — успешное выполнение.   Красный фон — неудача (рука не захватывает объект).'
     '   Каждый ряд: 4 кадра, равномерно по времени эпизода.',
     950, False, C_BODY, True, 'l')]))

sxml = build_slide(shapes)
srels = slide_rels(1, image_rel('rId2', '../media/img_sim_cmp.png'))
slides_data.append((sxml, srels,
    [('img_sim_cmp.png', os.path.join(IMAGES, 'sim_comparison.png'))]))

# =========================================================
# SLIDE 14 — Сводное сравнение
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(14), title_bar('Сводное сравнение четырёх серий')]

col13_xs = [CA_X, CA_X+ex(8), CA_X+ex(38), CA_X+ex(52), CA_X+ex(65), CA_X+ex(78)]
col13_ws = [ex(7), ex(29), ex(13), ex(12), ex(12), ex(11)]
shapes.extend(table_header(['№','Метод (алгоритм)','reach','push','pick-pl.','Ср.'],
                             col13_xs, col13_ws, CA_Y))
rows13 = [('1','Экспертная награда (SAC)','100%','83%','47%','77%'),
          ('2','Разреженная награда (SAC)','100%','7%','0%','36%'),
          ('3','VLM-код, 1 итерация (SAC)','100%','0%','0%','33%'),
          ('4','OpenVLA-OFT, LIBERO-Object','—','—','—','100%'),
          ('4','OpenVLA-OFT, LIBERO-Spatial','—','—','—','93%')]
row_bgs13 = ['ECE8F5','FFFFFF','F8F4FC','FFFFFF','F8F4FC']
row_clrs13 = [[C_BODY,C_BODY,C_BODY,C_PURPLE,C_PURPLE,C_PURPLE],
              [C_BODY]*6,
              [C_BODY]*6,
              [C_BODY,C_BODY,C_BODY,C_BODY,C_BODY,C_PURPLE],
              [C_BODY]*6]
for ri, (row, bg, cols) in enumerate(zip(rows13, row_bgs13, row_clrs13)):
    shapes.extend(table_row(row, col13_xs, col13_ws,
                            CA_Y+ey(6.5)+ey(8)*ri, bg=bg, colors=cols))

shapes.append(filled_rect(CA_X, CA_Y+ey(48), C1_W, ey(18), 'F5F0FB'))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(49), C1_W-ei(0.2), ey(5),
    [('SAC устойчивее PPO', 1200, True, C_TITLE, False, 'l')]))
shapes.append(txbox(CA_X+ei(0.1), CA_Y+ey(55), C1_W-ei(0.2), ey(10),
    [('Reach-v3 с VLM-наградой: SAC 100%, PPO 71,7% (Δ = 28 п.п.)',
      1050, False, C_BODY, False, 'l')]))

shapes.append(filled_rect(C2_X, CA_Y+ey(48), C2_W, ey(18), C_LPURP))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(49), C2_W-ei(0.2), ey(5),
    [('Главный барьер', 1200, True, C_PURPLE, False, 'l')]))
shapes.append(txbox(C2_X+ei(0.1), CA_Y+ey(55), C2_W-ei(0.2), ey(10),
    [('Push/pick-place требуют стадийной награды с контактными и захватными термами',
      1050, False, C_BODY, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 14 — Выводы
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(15), title_bar('Выводы')]

concls = [
    ('1.', 'Разреженное вознаграждение',
     'применимо только для задач без контактной динамики. Разрыв с экспертной наградой на push-v3: 76 п.п.'),
    ('2.', 'VLM-кодогенерация',
     'работает при ρ = 0,97; на контактных задачах ρ < 0,15 — агент находит ложный оптимум.'),
    ('3.', 'SAC устойчивее PPO:',
     'разница 28 п.п., буфер опыта компенсирует некалиброванность сигнала.'),
    ('4.', 'OpenVLA-OFT',
     'воспроизводит результаты с расхождением −2,3 п.п., достигает 96,5% на LIBERO без RL-дообучения.'),
    ('5.', 'Ключевая рекомендация:',
     'для контактных задач — минимум 3–5 итераций уточнения с явными стадийными и контактными термами.'),
]
for i, (num, bold_txt, rest) in enumerate(concls):
    y = CA_Y + ey(1) + ey(17)*i
    shapes.append(txbox(CA_X, y, ex(5), ey(9),
        [(num, 1300, True, C_PURPLE, False, 'l')]))
    shapes.append(txbox(CA_X+ex(5.5), y, CA_W-ex(5.5), ey(5.5),
        [(bold_txt, 1200, True, C_TITLE, False, 'l')]))
    shapes.append(txbox(CA_X+ex(5.5), y+ey(6), CA_W-ex(5.5), ey(8),
        [(rest, 1100, False, C_BODY, False, 'l')]))

slides_data.append((build_slide(shapes), slide_rels(1), []))

# =========================================================
# SLIDE 15 — Дальнейшие исследования (dark bg)
# =========================================================
_shape_id[0] = 100
shapes = [slide_num_box(16)]

shapes.append(txbox(CA_X, ey(3), ex(65), ey(8),
    [('Направления дальнейших исследований', 1800, True, C_WHITE, False, 'l')]))

future = [
    ('1. Итеративное уточнение функций вознаграждения',
     'для push-v3 и pick-place-v3 (3–5 итераций). Ожидаемый результат: ≥50% на push-v3.'),
    ('2. RL-дообучение OpenVLA-OFT',
     'на LIBERO-Spatial и LIBERO-Long. Цель: ≥97%.'),
    ('3. Сравнение кодогенерации и оценки предпочтений',
     '(RL-VLM-F) как двух подходов к автоматическому получению вознаграждения.'),
    ('4. Перенос на реальный робот:',
     'оценка sim-to-real разрыва с помощью бенчмарка SIMPLER.'),
]
for i, (bold_txt, rest) in enumerate(future):
    y = ey(14) + ey(15)*i
    shapes.append(txbox(CA_X, y, ex(56), ey(6.5),
        [(bold_txt, 1200, True, C_WHITE, False, 'l')]))
    shapes.append(txbox(CA_X, y+ey(7), ex(56), ey(7),
        [(rest, 1100, False, C_LGRAY, False, 'l')]))

shapes.append(txbox(ex(63), ey(32), ex(32), ey(12),
    [('Спасибо за внимание!', 2000, True, C_WHITE, False, 'c')]))
shapes.append(txbox(ex(63), ey(46), ex(32), ey(22),
    [('Новичков Дмитрий Евгеньевич', 1200, False, C_WHITE, False, 'c'),
     ('Группа 3435', 1200, False, C_WHITE, False, 'c'),
     ('', 1000, False, C_WHITE, False, 'c'),
     ('Научный руководитель:', 1100, False, C_LGRAY, False, 'c'),
     ('Ведяков А.А., к.т.н.', 1100, False, C_LGRAY, False, 'c')]))

sxml = build_slide(shapes, bg_fill('rId2'))
srels = slide_rels(14, image_rel('rId2', '../media/image48.jpg'))
slides_data.append((sxml, srels, []))

# =========================================================
# PACKAGE INTO PPTX
# =========================================================
with zipfile.ZipFile(OUT_PATH, 'w', zipfile.ZIP_DEFLATED) as zout:

    # 1. Copy everything from template EXCEPT the old slides
    skip = set()
    for i in range(1, 12):
        skip.add(f'ppt/slides/slide{i}.xml')
        skip.add(f'ppt/slides/_rels/slide{i}.xml.rels')
    skip.add('ppt/presentation.xml')
    skip.add('ppt/_rels/presentation.xml.rels')
    skip.add('[Content_Types].xml')

    for root, dirs, files in os.walk(TEMPLATE):
        for fname in files:
            full = os.path.join(root, fname)
            arcname = os.path.relpath(full, TEMPLATE)
            if arcname not in skip:
                zout.write(full, arcname)

    # 2. Add extra images from our experiments
    added_media = set()
    for i, (sxml, srels, media) in enumerate(slides_data):
        for (media_name, src_path) in media:
            if media_name not in added_media and os.path.exists(src_path):
                zout.write(src_path, f'ppt/media/{media_name}')
                added_media.add(media_name)

    # 3. Write slide XMLs and rels
    for i, (sxml, srels, _) in enumerate(slides_data):
        zout.writestr(f'ppt/slides/slide{i+1}.xml', sxml.encode('utf-8'))
        zout.writestr(f'ppt/slides/_rels/slide{i+1}.xml.rels', srels.encode('utf-8'))

    # 4. presentation.xml — update sldIdLst and slide count
    with open(os.path.join(TEMPLATE, 'ppt/presentation.xml')) as f:
        prs_xml = f.read()
    # Replace sldIdLst
    new_ids = '\n'.join(
        f'<p:sldId id="{256+i}" r:id="rId{100+i}"/>'
        for i in range(len(slides_data)))
    prs_xml = re.sub(r'<p:sldIdLst>.*?</p:sldIdLst>',
                     f'<p:sldIdLst>{new_ids}</p:sldIdLst>', prs_xml, flags=re.DOTALL)
    zout.writestr('ppt/presentation.xml', prs_xml.encode('utf-8'))

    # 5. ppt/_rels/presentation.xml.rels  — rebuild from scratch keeping non-slide rels
    with open(os.path.join(TEMPLATE, 'ppt/_rels/presentation.xml.rels')) as f:
        prs_rels_orig = f.read()
    # Extract all non-slide relationships
    non_slide = re.findall(
        r'<Relationship\s[^>]*/>', prs_rels_orig)
    non_slide = [r for r in non_slide if 'slides/slide' not in r]
    # Build new rels file
    new_slide_rels = [
        f'<Relationship Id="rId{100+i}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        f'Target="slides/slide{i+1}.xml"/>'
        for i in range(len(slides_data))]
    prs_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                + '\n'.join(non_slide + new_slide_rels)
                + '\n</Relationships>')
    zout.writestr('ppt/_rels/presentation.xml.rels', prs_rels.encode('utf-8'))

    # 6. [Content_Types].xml
    with open(os.path.join(TEMPLATE, '[Content_Types].xml')) as f:
        ct = f.read()
    # Remove old slide overrides
    ct = re.sub(r'<Override PartName="/ppt/slides/slide\d+\.xml"[^>]*/>\n?', '', ct)
    new_overrides = '\n'.join(
        f'<Override PartName="/ppt/slides/slide{i+1}.xml" '
        f'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(len(slides_data)))
    ct = ct.replace('</Types>', new_overrides + '\n</Types>')
    zout.writestr('[Content_Types].xml', ct.encode('utf-8'))

print(f'Saved {len(slides_data)} slides → {OUT_PATH}')
