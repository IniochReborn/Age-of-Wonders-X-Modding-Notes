---
name: adblocker-hides-adv-classes
description: "Ad blockers cosmetically hide elements with adv*-classes on hosted pages — broke the manual's adviser panels at aowx.org"
metadata: 
  node_type: memory
  type: project
  originSessionId: 163b870a-0be3-4c48-b23d-8bb716073fbe
  modified: 2026-08-06T03:42:58.347Z
---

2026-08-05: the AoWx Manual (hosted at **aowx.org**, source = `.AoWx Manual.html` built from `patch scripts\manual_build\template.html`) had its Tanaris/Rolar "adviser" hover panes render as an empty box + portrait ONLY on the laptop viewing the hosted site — fine locally and on the phone. Cause: **EasyList carries generic cosmetic rules `##.advtext` and `##.advtitle`**; the panes used classes `advtext`/`advtitle` and the laptop's Chrome ad blocker hid them. Extensions don't run on `file://` (local worked) and phone Chrome has no extensions (phone worked). Fixed by renaming the whole `adv*` class family → `sage*` (sagetip/sagesw/sagepane/sagetitle/sagerow/sageface/sagetext/hassage) in BOTH the built manual and template.html (JS identifiers like `advTip()` left as-is — filters only see the DOM). Also fixed same-day: nav search box crowding the Community tab at laptop widths (150% scaling → 1280 CSS px) — the `.srch` collapse media query breakpoint raised 980→1400px + `nav a` padding/font tightened in that range. Hosted copy only differs from local by a Cloudflare-injected analytics beacon (verified by download+diff). User must RE-UPLOAD `.AoWx Manual.html` after such fixes.

**Why:** hosted-vs-local rendering differences on this project are usually environment (ad blocker, per-site zoom, extensions), not the file — the file diff takes minutes and settles it.

**How to apply:** never name UI classes with ad-like prefixes (`ad`, `adv`, `sponsor`, `banner`, `promo`); when a hosted page breaks for one device only, audit classes against EasyList exact rules (script pattern in scratchpad `class_audit.py`: extract `class="..."` tokens, match against `##.<name>` lines from easylist.txt). Related: [[project-state-2026-07]].
