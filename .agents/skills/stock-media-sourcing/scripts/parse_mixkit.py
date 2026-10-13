# -*- coding: utf-8 -*-
"""临时脚本：解析 Mixkit 列表页，提取候选素材清单（音乐 / 音效）。
用完即弃。"""
import re
import sys
import json
import html as _html
from pathlib import Path

ITEM_SPLIT = re.compile(r'<div class="item-grid__item">')


def parse_page(text, kind):
    """解析一个 Mixkit 列表页，返回 [{id,title,tags,dur,url}]"""
    chunks = ITEM_SPLIT.split(text)[1:]
    out = []
    for c in chunks:
        m = re.search(r'data-audio-player-item-id-value="(\d+)"', c)
        if not m:
            continue
        iid = m.group(1)
        mt = re.search(r'<h2 class="item-grid-card__title">\s*(.*?)\s*</h2>', c, re.S)
        title = _html.unescape(re.sub(r'<[^>]+>', '', mt.group(1))).strip() if mt else ''
        tags = re.findall(r'class="meta-links__link"[^>]*href="([^"]+)"[^>]*>([^<]*)</a>', c)
        tag_names = [t[1].strip() for t in tags if t[1].strip()]
        md = re.search(r'data-test-id="duration">\s*([\d:]+)\s*<', c)
        dur = md.group(1).strip() if md else ''
        if kind == 'music':
            url = f'https://assets.mixkit.co/music/{iid}/{iid}.mp3'
        else:
            url = f'https://assets.mixkit.co/active_storage/sfx/{iid}/{iid}.wav'
        out.append({'id': iid, 'title': title, 'tags': tag_names,
                    'dur': dur, 'url': url, 'page': f'https://mixkit.co/'
                    + ('free-stock-music/' if kind == 'music' else 'free-sound-effects/')})
    return out


def main():
    tmp = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp')
    kind = sys.argv[2] if len(sys.argv) > 2 else 'all'

    music_files = sorted(tmp.glob('p_*.html')) + sorted(tmp.glob('p2_*.html'))
    sfx_files = sorted(tmp.glob('s_*.html')) + sorted(tmp.glob('s2_*.html'))

    result = {}
    if kind in ('all', 'music'):
        seen = {}
        for f in music_files:
            for it in parse_page(f.read_text(encoding='utf-8', errors='replace'), 'music'):
                if it['id'] in seen:
                    seen[it['id']]['src'].append(f.stem)
                else:
                    it['src'] = [f.stem]
                    seen[it['id']] = it
        result['music'] = list(seen.values())
    if kind in ('all', 'sfx'):
        seen = {}
        for f in sfx_files:
            for it in parse_page(f.read_text(encoding='utf-8', errors='replace'), 'sfx'):
                if it['id'] in seen:
                    seen[it['id']]['src'].append(f.stem)
                else:
                    it['src'] = [f.stem]
                    seen[it['id']] = it
        result['sfx'] = list(seen.values())

    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
