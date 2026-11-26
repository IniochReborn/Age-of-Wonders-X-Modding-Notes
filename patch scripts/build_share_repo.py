#!/usr/bin/env python3
"""Stage the shareable AoWx sources (patch scripts + Claude memory notes) for the GitHub repo.

Same rules as the Discord drops for BXL (see memory note discord-share-drops), tightened
for a public audience: no binaries, no backups, no debug dumps, no key / signing files,
personal details scrubbed from every text file, and a scan of the staged result.

    py -3.10 build_share_repo.py                 # dry run: counts + scan of what WOULD be staged
    py -3.10 build_share_repo.py --apply         # (re)write the staging folder
    py -3.10 build_share_repo.py --apply --out D:\\somewhere

The staging folder is only ever synced, never the game folder: files that no longer
qualify are removed from it, the .git folder and the hand-written top-level files
(README.md, LICENSE, .gitignore, .gitattributes) are left alone.
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
MEMORY = os.path.join(os.path.expanduser('~'), '.claude', 'projects',
                      'C--Users-<user>-Desktop-Age-of-Wonders-X---Claude', 'memory')
DEFAULT_OUT = os.path.join(GAME, 'share to github', 'notes repo')

KEEP_TOP = {'.git', 'README.md', 'LICENSE', '.gitignore', '.gitattributes'}

# mapunlock = strips passwords from other mapmakers' maps: not published
SKIP_DIRS = {'__pycache__', 'node_modules', '.wrangler', 'dist', 'build', '.git', 'mapunlock'}
SKIP_DIR_PREFIX = ('tmp', 'bak_')
SKIP_EXT = {'.dll', '.exe', '.dpl', '.pyc', '.pkl', '.log', '.node', '.wasm', '.stop',
            '.pem', '.pfx', '.key', '.zip', '.7z', '.asg', '.hsm', '.csm', '.pfs', '.ilb',
            '.wav', '.reg'}
MAX_BYTES = 5 * 1024 * 1024
MAX_PNG = 400 * 1024
MAX_TXT_DUMP = 400 * 1024          # big .txt = probe dumps

# signing / key handling: never shared (public key files included, as in the Discord drops)
KEY_NAME = re.compile(r'aowx_keygen|aowx_sign_release|aowx_change_passphrase|sign_latest_release'
                      r'|aowx_update_public|PublicKey\.cs|__Sign AoWx', re.I)
KEY_MARK = re.compile(rb'BEGIN [A-Z ]*(PRIVATE|PUBLIC) ' + rb'KEY|<RSAKey' + rb'Value>|<Modu' + rb'lus>')

# crash / hang / probe output: lists the modules loaded on the dev machine
DUMP_NAME = re.compile(r'^(hang_|veh_)|probe', re.I)

# memory notes that are about people / accounts rather than the mod
# printed-manual-book = the user's personal project, not part of the mod
# discord-share-drops / feedback-no-ai-attribution-public = notes about the sharing itself
MEMORY_SKIP = {'map-password-unlock.md', 'printed-manual-book.md', 'discord-share-drops.md',
               'feedback-no-ai-attribution-public.md'}

TEXT_EXT = {'.py', '.md', '.txt', '.json', '.js', '.mjs', '.cjs', '.ts', '.cs', '.cmd', '.ps1',
            '.iss', '.toml', '.jsonc', '.yml', '.xml', '.html', '.css', '.h', '.cc', '.bnf',
            '.ini', '.asm', '.inc', '.bat', '.csv', '.vsf', ''}

SCRUBS = [
    (re.compile(r'(?i)(Users[\\/]+)(the user|Inioch)\b'), r'\1<user>'),
    (re.compile(r'C--Users-(the user|Inioch)-'), r'C--Users-<user>-'),
    (re.compile(r'(?i)\b[\w.+-]+@(gmail|hotmail|outlook|yahoo|proton(mail)?)\.[a-z.]+\b'), '<email>'),
    (re.compile(r'\b[\w-]+\.aowx\.workers\.dev\b'), '<worker>.workers.dev'),
    (re.compile(r'<server id>'), '<server id>'),
    (re.compile(r'<a?:(\w+):\d{17,20}>'), r':\1:'),          # Discord custom emoji ids
    (re.compile(r"(?<!Hunter's )\bMark's\b"), "a tester's"),  # tester's name (not the spell)
    (re.compile(r"(?<!Hunter's )\bMark\b(?! of)"), 'a tester'),
    (re.compile(r"\bCody's\b"), "the user's"),
    (re.compile(r'\bCody\b'), 'the user'),
]

# what the scan reports in the staged tree (after scrubbing)
SCAN = [
    ('private key',  re.compile('PRIVATE ' + 'KEY')),
    ('token-like',   re.compile(r'\b(gh[opsu]_[A-Za-z0-9]{20,}|[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,})\b')),
    ('email',        re.compile(r'\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b')),
    ('snowflake id', re.compile(r'(?<![\dxA-Fa-f])\d{17,20}(?!\d)')),
    ('ipv4',         re.compile(r'(?<![\d.])(?!127\.0\.0\.1|0\.0\.0\.0|255\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])')),
    ('user path',    re.compile(r'(?i)Users[\\/]+(?!<user>|Public|%)[A-Za-z]\w+')),
    ('name the user',    re.compile(r'\bCody\b')),
    ('passphrase',   re.compile(r'(?i)passphrase\s*[:=]\s*\S+')),
    ('account id',   re.compile(r'(?i)account_id\s*=')),
]


def want(path, rel_dirs, name):
    ext = os.path.splitext(name)[1].lower()
    if '.bak' in name.lower() or name.endswith('~'):
        return 'backup'
    if ext in SKIP_EXT:
        return 'ext ' + ext
    if KEY_NAME.search(name):
        return 'key/signing'
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        return '>5 MB'
    if ext == '.png' and size > MAX_PNG:
        return 'big png'
    if ext == '.txt' and (size > MAX_TXT_DUMP or DUMP_NAME.search(name)):
        return 'debug dump'
    with open(path, 'rb') as f:
        data = f.read()
    if KEY_MARK.search(data):
        return 'key marker'
    return None


def walk(src, dst_prefix, recurse=True, only_ext=None):
    """yield (src_path, rel_dst, skip_reason)"""
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not d.lower().startswith(SKIP_DIR_PREFIX)) if recurse else []
        for name in sorted(files):
            p = os.path.join(root, name)
            if only_ext and os.path.splitext(name)[1].lower() not in only_ext:
                continue
            rel = os.path.relpath(p, src).replace('\\', '/')
            yield p, dst_prefix + '/' + rel, want(p, root, name)


# --- `reference files\BXL`: BXL's (Ziggurat) drop, in which the laptop sessions of
# July/August also saved OUR scripts and notes.  Ours go out as ours; of his files only
# the ones we used as they are (user rule 2026-11-25: not the ones we never used, and
# not the ones we ported into a script of our own).
BXL_DIR = os.path.join(GAME, 'reference files', 'BXL')
ZIG_DIR = os.path.join(GAME, 'reference files', 'new BXL', 'Ziggurat Scrolls', 'Ziggurat Scrolls')
OURS_IN_BXL = re.compile(r'^(HSM_Map_Format_Objects\.md|Spring_Of_Life_Wasteland_Design\.md'
                         r'|UnitFloater_Expand_Design\.md'
                         r'|build_scripts/(build_desync_.*|build_spring_wasteland|build_unitfloater_expand'
                         r'|patch_version_402)\.py'
                         r'|re_tools/(comm_probe|desync_dump|hook_probe|spring_crumbs|tc_dump|vmtdump)\.py)$')
BXL_USED = [   # (source path, name in the repo)
    (os.path.join(BXL_DIR, 'build_scripts', 'build_dlgdirs.py'), 'build_scripts/build_dlgdirs.py'),
    (os.path.join(BXL_DIR, 'Editor_Modernization_DialogDirs_Toolbar.md'), 'Editor_Modernization_DialogDirs_Toolbar.md'),
    (os.path.join(ZIG_DIR, '2026-08', 'notes', 'ID_Ceilings.md'), 'ID_Ceilings.md'),
    (os.path.join(ZIG_DIR, '2026-08', 'notes', 'Investigation_Site_Defender_Rosters.md'),
     'Investigation_Site_Defender_Rosters.md'),
    (os.path.join(ZIG_DIR, '2026-07', 're_tools', 'hang_stack.py'), 're_tools/hang_stack.py'),
] + [(os.path.join(BXL_DIR, 're_tools', n + '.py'), 're_tools/%s.py' % n)
     for n in ('aowsyms', 'pescan', 'xref', 'grabwin', 'sampler', 'dfm_parse')]


def bxl_folder():
    out = []
    for p, rel, why in walk(BXL_DIR, 'x'):
        rel = rel[2:]
        if OURS_IN_BXL.match(rel):
            out.append((p, 'patch scripts/_laptop era (July-August)/' + rel, why))
    for p, rel in BXL_USED:
        out.append((p, 'patch scripts/_laptop era (July-August)/' + rel, want(p, None, os.path.basename(p))))
    return out


def collect():
    items = []
    items += walk(HERE, 'patch scripts')
    # July-era scripts that still live in the game root
    items += walk(GAME, 'patch scripts/_game_root (July era)', recurse=False, only_ext={'.py'})
    for p, rel, why in walk(MEMORY, 'memory files', recurse=False, only_ext={'.md'}):
        if os.path.basename(p) in MEMORY_SKIP:
            why = 'memory skip list'
        items.append((p, rel, why))
    # sources of the modding tools, early research and the
    # per-feature write-ups from the first Discord drops (BXL's own files are not ours to publish)
    SRC = {'.py', '.md', '.txt', '.json', '.png', '.ico'}
    items += walk(os.path.join(GAME, 'modding tools'), 'modding tools', only_ext=SRC)
    items += walk(os.path.join(GAME, 'old modding tools', 'research'),
                  'modding tools/_early research', only_ext={'.py'})   # the .txt there are other authors' help files
    prev = os.path.join(GAME, 'share to discord', 'previously shared')
    W = {'.py', '.md', '.txt'}
    items += walk(os.path.join(prev, 'share to discord 2'), 'early write-ups', only_ext=W)
    items += walk(os.path.join(prev, 'AoWx Map Generator'), 'early write-ups/AoWx Map Generator', only_ext=W)
    items += walk(prev, 'early write-ups', recurse=False, only_ext=W)
    items += walk(os.path.join(GAME, 'share to discord'), 'early write-ups', recurse=False, only_ext=W)
    # user 2026-11-25: no separate 'early write-ups' folder - scripts join patch scripts,
    # the explanations join the notes
    def merged(it):
        p, rel, why = it
        if rel.startswith('early write-ups/'):
            rest = rel[len('early write-ups/'):]
            top = 'patch scripts/' if rel.lower().endswith('.py') else 'memory files/'
            rel = top + rest
        return p, rel, why
    items = [merged(it) for it in items
             if it[1] != 'early write-ups/README.md']   # cover note of an old Discord zip
    items += bxl_folder()
    # the user's pre-2026 hex-edit spreadsheet (read 2026-11-25: offsets and bytes only, no names)
    xl = os.path.join(GAME, 'reference files', 'Old Hex Editing Notes.xlsx')
    if os.path.exists(xl):
        items.append((xl, 'Old Hex Editing Notes.xlsx', None))
    cl = os.path.join(GAME, 'X', 'Documentation', 'changelogs.txt')
    if os.path.exists(cl):
        items.append((cl, 'changelogs.txt', None))
    return items


def scrub(data, ext):
    if ext not in TEXT_EXT:
        return data, 0
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text = data.decode('cp1252')
            enc = 'cp1252'
        except UnicodeDecodeError:
            return data, 0
    else:
        enc = 'utf-8'
    n = 0
    for rx, rep in SCRUBS:
        text, k = rx.subn(rep, text)
        n += k
    return (text.encode(enc) if n else data), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--show-skips', action='store_true')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    items = collect()
    keep = [(p, rel) for p, rel, why in items if not why]
    skips = [(rel, why) for p, rel, why in items if why]
    by = {}
    for rel, why in skips:
        by.setdefault(why, []).append(rel)
    print('keep %d files, skip %d' % (len(keep), len(skips)))
    for why in sorted(by):
        print('  skipped (%s): %d' % (why, len(by[why])))
        if a.show_skips or why in ('key/signing', 'key marker', 'memory skip list', '>5 MB'):
            for rel in by[why]:
                print('      ' + rel)

    dup = [rel for rel in {r for _, r in keep} if sum(1 for _, r in keep if r.lower() == rel.lower()) > 1]
    if dup:
        sys.exit('name collisions after merging folders: %s' % sorted(dup))
    staged = {}
    total = scrubbed_files = scrubbed_hits = 0
    for p, rel in keep:
        with open(p, 'rb') as f:
            data = f.read()
        data, n = scrub(data, os.path.splitext(p)[1].lower())
        if rel.startswith('memory files/'):
            # drop index lines that point at held-back notes
            lines = data.split(b'\n')
            kept = [ln for ln in lines if not any(('(%s)' % m).encode() in ln for m in MEMORY_SKIP)]
            if len(kept) != len(lines):
                data = b'\n'.join(kept)
        if n:
            scrubbed_files += 1
            scrubbed_hits += n
        staged[rel] = data
        total += len(data)
    print('staged size %.1f MB; scrubbed %d replacements in %d files'
          % (total / 1e6, scrubbed_hits, scrubbed_files))

    print('\nscan of the staged content:')
    for label, rx in SCAN:
        hits = []
        for rel, data in staged.items():
            if os.path.splitext(rel)[1].lower() not in TEXT_EXT:
                continue
            text = data.decode('utf-8', 'replace')
            for m in rx.finditer(text):
                s = max(0, m.start() - 40)
                hits.append((rel, text[s:m.end() + 30].replace('\n', ' ')))
        print('  %-13s %d' % (label, len(hits)))
        seen = set()
        for rel, ctx in hits:
            if (rel, ctx) in seen:
                continue
            seen.add((rel, ctx))
            if len(seen) > 25:
                print('      ...')
                break
            print('      %s: %s' % (rel, ctx))

    if not a.apply:
        print('\ndry run - nothing written (use --apply)')
        return
    out = a.out
    os.makedirs(out, exist_ok=True)
    # remove staged files that no longer qualify (never the kept top-level files)
    for root, dirs, files in os.walk(out):
        if root == out:
            dirs[:] = [d for d in dirs if d not in KEEP_TOP]
        for name in files:
            p = os.path.join(root, name)
            rel = os.path.relpath(p, out).replace('\\', '/')
            if root == out and name in KEEP_TOP:
                continue
            if rel not in staged:
                os.remove(p)
    for rel, data in staged.items():
        p = os.path.join(out, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.exists(p):
            with open(p, 'rb') as f:
                if f.read() == data:
                    continue
        with open(p, 'wb') as f:
            f.write(data)
    for root, dirs, files in os.walk(out, topdown=False):
        if '.git' in root.split(os.sep):
            continue
        if not os.listdir(root):
            os.rmdir(root)
    print('\nwrote %d files to %s' % (len(staged), out))


if __name__ == '__main__':
    main()
