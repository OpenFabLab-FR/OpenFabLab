"""Installation-owned branding; no institution assets or identity heuristics."""
import html
import math
import os
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

LOGO_KINDS = ('wordmark', 'header_institution', 'network', 'institution', 'main', 'signature')
VISIBILITY_KEYS = ('show_wordmark_logo', 'show_header_institution_logo', 'show_network_logo')
BADGE_FILENAME = 'badge-template.svg'
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024


def validate_badge_template(raw):
    """Accept self-contained vector SVG only; never fetch URLs, fonts or images."""
    try:
        text = raw.decode('utf-8')
        if len(raw) > MAX_TEMPLATE_BYTES or re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I):
            raise ValueError
        root = ET.fromstring(text)
        if root.tag != '{http://www.w3.org/2000/svg}svg':
            raise ValueError
        if root.get('viewBox', '').split() != ['0', '0', '54', '86']:
            raise ValueError
        ids = {}
        forbidden = {'script', 'foreignObject', 'image', 'iframe', 'audio', 'video', 'animate', 'set', 'a', 'style'}
        nodes = list(root.iter())
        if len(nodes) > 12000:
            raise ValueError
        for node in nodes:
            tag = node.tag.rsplit('}', 1)[-1]
            if tag in forbidden:
                raise ValueError
            for key, value in node.attrib.items():
                local = key.rsplit('}', 1)[-1].lower()
                if local.startswith('on') or local in {'base', 'src'}:
                    raise ValueError
                if local == 'href' and not value.startswith('#'):
                    raise ValueError
                if re.search(r'(?i)javascript:|@import|url\s*\(\s*[\'\"]?(?!#)', value):
                    raise ValueError
            name = node.get('id')
            if name:
                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.:-]*', name):
                    raise ValueError
                if name in ids:
                    raise ValueError
                ids[name] = node
        for key in ('user-id', 'first-name', 'category'):
            node = ids.get(key)
            if node is None or node.tag.rsplit('}', 1)[-1] != 'text' or list(node):
                raise ValueError
            for attribute in ('x', 'y', 'font-size'):
                if not math.isfinite(float(node.get(attribute, 'nan'))):
                    raise ValueError
            if not 0 < float(node.get('font-size')) <= 100:
                raise ValueError
            for attribute in ('letter-spacing', 'textLength'):
                if node.get(attribute) is not None and not math.isfinite(float(node.get(attribute))):
                    raise ValueError
            if node.get('textLength') is not None and not 0 < float(node.get('textLength')) <= 54:
                raise ValueError
        qr = ids.get('qr-code')
        if qr is None or qr.tag.rsplit('}', 1)[-1] != 'g' or qr.get('transform'):
            raise ValueError
        # The replacement group has fixed coordinates; an inherited transform
        # would silently move the QR out of its reserved area.
        def check_parent(node, transformed=False):
            if node is qr and transformed:
                raise ValueError
            for child in node:
                check_parent(child, transformed or bool(node.get('transform')))
        check_parent(root)
        bank = ids.get('badge-glyphs')
        if bank is not None:
            units = float(bank.get('data-units', 'nan'))
            if not math.isfinite(units) or not 1 <= units <= 100000:
                raise ValueError
            for glyph in bank:
                if not re.fullmatch(r'[0-9a-f]{4,6}', glyph.get('data-char', '')):
                    raise ValueError
                advance = float(glyph.get('data-advance', 'nan'))
                if not math.isfinite(advance) or not 0 <= advance <= 10 * units:
                    raise ValueError
        return text
    except (UnicodeError, ET.ParseError, ValueError, RecursionError, OverflowError):
        raise ValueError('Modèle de badge invalide : SVG vectoriel autonome 54 × 86 mm, avec user-id, first-name, category et qr-code requis ; aucun contenu actif ou lien externe.') from None


def badge_source(structure, default, data_directory):
    configured = (structure or {}).get('badge_template', '')
    if not configured:
        return Path(default).read_text(encoding='utf-8')
    if configured != BADGE_FILENAME:
        raise ValueError('Le modèle privé de badge configuré est invalide.')
    path = Path(data_directory) / 'branding' / configured
    if not path.is_file() or path.is_symlink():
        raise ValueError('Le modèle privé de badge est configuré mais absent. Restaurez-le dans Réglages → Identité de la structure.')
    # Canonical XML avoids depending on quote style, namespace prefixes or a
    # self-closing placeholder. Only the QR placeholder is replaced entirely.
    root = ET.fromstring(validate_badge_template(path.read_bytes()))
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
    for node in root.iter():
        if node.get('id') == 'qr-code':
            node.clear(); node.set('id', 'qr-code')
    return ET.tostring(root, encoding='unicode', short_empty_elements=False)


def outline_private_text(template):
    """Optional embedded glyph outlines ensure identical SVG/PNG typography.

    This is vector geometry owned by the installation, NOT a bundled font.
    Generic templates keep their ordinary text. Private templates may include
    a glyph bank to avoid platform-dependent font substitution.
    """
    root = ET.fromstring(template)
    bank = next((n for n in root.iter() if n.get('id') == 'badge-glyphs'), None)
    if bank is None:
        return template
    units = float(bank.get('data-units', '0'))
    if not math.isfinite(units) or units <= 0:
        raise ValueError('Géométrie typographique du badge invalide.')
    glyphs = {n.get('data-char'): n for n in bank if n.get('data-char')}
    def replace(match):
        raw = match.group(0)
        node = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">' + raw + '</svg>')[0]
        if node.get('id') not in {'user-id', 'first-name', 'category'}:
            return raw
        value = ''.join(node.itertext())
        size = float(node.get('font-size'))
        spacing = float(node.get('letter-spacing', '0'))
        scale = size / units
        records = []
        width = 0.0
        for char in value:
            glyph = glyphs.get(f'{ord(char):04x}')
            if glyph is None:
                raise ValueError('Le modèle privé ne contient pas la géométrie d’un caractère du prénom ou de la catégorie.')
            records.append((glyph, width))
            width += float(glyph.get('data-advance', '0')) * scale + spacing
        width = max(0, width - spacing)
        limit = float(node.get('textLength', '45'))
        stretch = min(1.0, limit / width) if width else 1.0
        x, y = float(node.get('x')), float(node.get('y'))
        x -= width * stretch / 2 if node.get('text-anchor') == 'middle' else 0
        transforms = html.escape(node.get('transform', ''), quote=True)
        fill = html.escape(node.get('fill', 'inherit'), quote=True)
        paths = ''.join(f'<use href="#{g.get("id")}" transform="translate({offset:.6f},0) scale({scale:.8f},-{scale:.8f})"/>' for g, offset in records)
        # Retain searchable, escaped text in the description, not painted twice.
        return (f'<g id="{node.get("id")}" transform="{transforms}" fill="{fill}">'
                f'<desc>{html.escape(value)}</desc><g transform="translate({x:.6f},{y:.6f}) scale({stretch:.8f},1)">{paths}</g></g>')
    return re.sub(r'<text\b[^>]*>.*?</text>', replace, template, flags=re.S)


def migrate_branding_settings(database, data_directory):
    """One-time additive separation of the legacy header/document logo.

    No business table, PIN or secret is touched. Never infer an institution
    from its name. A customized new key (including empty/off) always wins.
    """
    old = dict(database.execute('SELECT key,value FROM app_settings'))
    def add(key, value):
        database.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES (?,?)', (key, value))
    branding = Path(data_directory) / 'branding'
    if 'structure_header_institution_logo' not in old:
        value = ''
        if old.get('structure_institution_logo') == 'institution.png':
            source, target = branding / 'institution.png', branding / 'header_institution.png'
            if source.is_file() and not source.is_symlink():
                if target.is_symlink() or (target.exists() and target.read_bytes() != source.read_bytes()):
                    raise ValueError('Séparation du logo institutionnel impossible : le fichier d’en-tête existe déjà avec un contenu différent. Aucune ressource n’a été écrasée.')
                if not target.exists():
                    shutil.copy2(source, target)
                    os.chmod(target, 0o600)
                value = 'header_institution.png'
        add('structure_header_institution_logo', value)
    for key, value in (('data_controller', old.get('structure_legal_entity', '')),
                       ('data_controller_address', old.get('structure_address', '')),
                       ('data_controller_representative', ''), ('data_controller_representative_role', '')):
        add('structure_' + key, value)


def logo_status(data_directory, structure):
    branding = Path(data_directory) / 'branding'
    result = {}
    for kind in LOGO_KINDS:
        value = structure.get('signature' if kind == 'signature' else kind + '_logo', '')
        result[kind] = bool(value == kind + '.png' and (branding / value).is_file() and not (branding / value).is_symlink())
    return result
