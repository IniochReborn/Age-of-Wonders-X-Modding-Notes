"""Emit upload/'AoWx changelog (1.37.<N>).txt' from X/Documentation/changelogs.txt.

Mirrors the manual builder's parse (emoji stripped); bullets re-emitted as '.' + spaces ladder
(AoWHeaven strips leading spaces, the dot anchors the indent);
validates the transform by reproducing the shipped 407 txt first.
"""
import re, sys, os

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
clt = open(os.path.join(GAME, 'X/Documentation/changelogs.txt'), 'rb').read().decode('cp1252', 'replace')
cll = [l.rstrip() for l in clt.split('\n')]
DATE_RE = re.compile(r'^(?:[A-Z][a-z]+ \d+(?:st|nd|rd|th),? \d{4}:?|~[0-9\-]+)$')
EMOJI_RE = re.compile(r'<:[A-Za-z0-9_~]+:\d+>|:[A-Za-z0-9_~]+:')
didx = [i for i, l in enumerate(cll) if DATE_RE.match(l.strip())]


def render(bi):
    di = didx[bi]
    bend = didx[bi + 1] if bi + 1 < len(didx) else len(cll)
    date = cll[di].strip().rstrip(':')
    j = di + 1
    while j < bend and not cll[j].strip():
        j += 1
    title = cll[j].strip() if j < bend else ''
    out = [date, title, '']
    stack = []  # ascending indent widths -> relative nesting depth
    for l in cll[j + 1:bend]:
        st = l.strip()
        if not st:
            if out and out[-1] != '':
                out.append('')
            continue
        lvl = 0
        if st.startswith('.'):
            rest = st[1:]
            if not rest.strip():          # lone '.' = deliberate gap line
                if out and out[-1] != '':
                    out.append('')
                continue
            nsp = len(rest) - len(rest.lstrip())
            while stack and nsp < stack[-1]:
                stack.pop()
            if not stack or nsp > stack[-1]:
                stack.append(nsp)
            lvl = len(stack) - 1
            st = rest.strip()
        st = EMOJI_RE.sub('', st).replace('\\', '').strip()
        if not st:
            if out and out[-1] != '':
                out.append('')
            continue
        if not st.startswith('-') and st.endswith(':'):
            if out and out[-1] != '':
                out.append('')
            out.append(st)
            continue
        if st.startswith('-'):
            st = st[1:].strip()
        if st:
            # AoWHeaven strips leading spaces: anchor the indent behind a leading '.' (Discord-style ladder,
            # 10 spaces at level 0 + 5 per level) - user 2026-09-23
            out.append('.' + ' ' * (10 + 5 * lvl) + '- ' + st)
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out) + '\n'


# newest entry (block 0) -> per-release txt named from its "Version 1.37.<N> released" title
title = render(0).split('\n')[1]
mv = re.search(r'Version (1\.\d+\.\d+)', title)
ver = sys.argv[1] if len(sys.argv) > 1 else mv.group(1)
out = render(0)
dst = os.path.join(GAME, 'upload/AoWx changelog (%s).txt' % ver)
open(dst, 'w', encoding='utf-8', newline='').write(out)
print('wrote', dst)
print(out)
