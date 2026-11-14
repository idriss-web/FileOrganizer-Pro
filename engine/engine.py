#!/usr/bin/env python3
"""File Organizer engine. stdin: JSON {cmd, ...options}. stdout: JSON lines (progress..., result|error)."""
import sys, os, json, re, shutil, hashlib, fnmatch, time
from pathlib import Path
from datetime import datetime
try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

CATS = {
 "Images": "jpg jpeg png gif bmp webp svg heic tif tiff ico raw cr2 nef psd ai",
 "Videos": "mp4 mkv avi mov wmv flv webm m4v mpg mpeg",
 "Audio": "mp3 wav flac aac ogg m4a wma opus mid",
 "Documents": "pdf doc docx odt rtf txt md tex epub mobi pages",
 "Spreadsheets": "xls xlsx xlsm csv ods tsv",
 "Presentations": "ppt pptx odp key",
 "Archives": "zip rar 7z tar gz bz2 xz iso cab",
 "Code": "py js ts jsx tsx html css json xml yml yaml c cpp h cs java go rs php rb sh bat ps1 sql ipynb",
 "Installers": "exe msi msix appx apk deb",
 "Fonts": "ttf otf woff woff2",
 "Design3D": "fig sketch xd blend obj fbx stl dwg dxf",
 "Shortcuts": "lnk url torrent",
}
EXT = {e: c for c, s in CATS.items() for e in s.split()}
UNDO = ".organizer_undo"

def emit(**k): print(json.dumps(k), flush=True)

def scan(o):
    root, now, out = Path(o["source"]), time.time(), []
    ign = o.get("ignore", [])
    only = {x.lower().lstrip(".") for x in o.get("only_ext", []) if x}
    skip = {x.lower().lstrip(".") for x in o.get("exclude_ext", []) if x}
    for dp, dn, fn in os.walk(root):
        dn[:] = [] if not o.get("recursive") else [d for d in dn if not d.startswith((".", "$", "_Duplicates"))]
        for n in fn:
            p = Path(dp, n)
            try: st = p.stat()
            except OSError: continue
            if not o.get("hidden") and (n.startswith(".") or getattr(st, "st_file_attributes", 0) & 6): continue
            if any(fnmatch.fnmatch(n.lower(), g.lower()) for g in ign): continue
            ext = p.suffix.lower().lstrip(".")
            if (only and ext not in only) or ext in skip: continue
            if now - st.st_mtime < o.get("min_age_min", 0) * 60: continue
            if st.st_size < o.get("min_mb", 0) * 1e6: continue
            if o.get("max_mb") and st.st_size > o["max_mb"] * 1e6: continue
            if o.get("older_days") and now - st.st_mtime < o["older_days"] * 86400: continue
            out.append(dict(path=str(p), name=n, ext=ext, size=st.st_size, mtime=st.st_mtime, ctime=st.st_ctime))
    return out

def safe(s): return re.sub(r'[<>:"|?*]', "_", s).strip(" .") or "_"

def subfolder(f, o):
    for r in o.get("rules", []):
        if r.get("pattern") and fnmatch.fnmatch(f["name"].lower(), r["pattern"].lower()): return r["folder"]
    t = datetime.fromtimestamp(f["ctime"] if o.get("date_source") == "created" else f["mtime"])
    s = f["size"]
    size = "Tiny" if s < 1e5 else "Small" if s < 1e6 else "Medium" if s < 1e8 else "Large" if s < 1e9 else "Huge"
    ch = next((c.upper() for c in f["name"] if c.isalnum()), "#")
    ch = ch if ch.isalpha() else ("0-9" if ch.isdigit() else "#")
    try:
        return o.get("template", "{category}").format(category=EXT.get(f["ext"], "Other"), ext=f["ext"].upper() or "NoExtension",
            year=t.year, month=t.strftime("%m-%B"), day=f"{t.day:02d}", size=size, letter=ch, parent=Path(f["path"]).parent.name)
    except (KeyError, IndexError, ValueError):
        return EXT.get(f["ext"], "Other")

def newname(n, mode, mt):
    stem, ext = os.path.splitext(n)
    if mode == "lower": stem, ext = stem.lower(), ext.lower()
    elif mode == "clean": stem = re.sub(r"[\s_]+", " ", stem).strip()
    elif mode == "date": stem = f"{datetime.fromtimestamp(mt):%Y-%m-%d}_{stem}"
    return stem + ext

def plan(o):
    root = Path(o["source"]); dest = Path(o.get("dest") or root)
    taken, rows, skipped = set(), [], 0
    for f in scan(o):
        sub = Path(*[safe(x) for x in re.split(r"[\\/]+", subfolder(f, o)) if x])
        dst = dest / sub / newname(f["name"], o.get("rename", "none"), f["mtime"])
        if str(dst).lower() == f["path"].lower(): continue
        pol = o.get("conflict", "rename")
        if pol != "overwrite" and (dst.exists() or str(dst).lower() in taken):
            if pol == "skip": skipped += 1; continue
            i = 1
            while (c := dst.with_name(f"{dst.stem} ({i}){dst.suffix}")).exists() or str(c).lower() in taken: i += 1
            dst = c
        taken.add(str(dst).lower())
        rows.append(dict(src=f["path"], dst=str(dst), size=f["size"], folder=str(sub)))
    return rows, skipped

def journal(root, op, entries):
    d = Path(root, UNDO); d.mkdir(exist_ok=True)
    name = f"{datetime.now():%Y%m%d-%H%M%S}.json"
    (d / name).write_text(json.dumps(dict(op=op, time=time.time(), entries=entries)), encoding="utf-8")
    return name

def cleanup(root):
    n = 0
    for dp, dn, fn in os.walk(root, topdown=False):
        if Path(dp) != Path(root) and not dn and not fn and UNDO not in dp:
            try: os.rmdir(dp); n += 1
            except OSError: pass
    return n

def move_all(o, pairs, op):
    done, errs = [], []
    for i, (s, d) in enumerate(pairs, 1):
        try:
            Path(d).parent.mkdir(parents=True, exist_ok=True)
            (shutil.copy2 if op == "copy" else shutil.move)(s, d)
            done.append(dict(src=s, dst=d, op=op))
        except Exception as e:
            errs.append(f"{Path(s).name}: {e}")
        if i % 10 == 0 or i == len(pairs): emit(type="progress", done=i, total=len(pairs))
    return done, errs

def c_plan(o):
    rows, sk = plan(o)
    folders = {}
    for r in rows: folders[r["folder"]] = folders.get(r["folder"], 0) + 1
    return dict(rows=rows[:2000], count=len(rows), size=sum(r["size"] for r in rows), skipped=sk, folders=folders)

def c_apply(o):
    rows, sk = plan(o)
    done, errs = move_all(o, [(r["src"], r["dst"]) for r in rows], o.get("action", "move"))
    removed = cleanup(o["source"]) if o.get("cleanup") and o.get("action", "move") == "move" else 0
    j = journal(o["source"], "organize", done) if done else None
    return dict(moved=len(done), errors=errs, skipped=sk, removed_dirs=removed, journal=j)

def c_history(o):
    d, out = Path(o["source"], UNDO), []
    if d.is_dir():
        for p in sorted(d.glob("*.json"), reverse=True):
            try: j = json.loads(p.read_text(encoding="utf-8"))
            except Exception: continue
            out.append(dict(file=p.name, time=j["time"], op=j["op"], count=len(j["entries"])))
    return dict(items=out)

def c_undo(o):
    p = Path(o["source"], UNDO, o["file"]); j = json.loads(p.read_text(encoding="utf-8")); ok, errs = 0, []
    for e in reversed(j["entries"]):
        try:
            if e["op"] == "copy": os.remove(e["dst"])
            else:
                Path(e["src"]).parent.mkdir(parents=True, exist_ok=True); shutil.move(e["dst"], e["src"])
            ok += 1
        except Exception as x: errs.append(f"{Path(e['dst']).name}: {x}")
    p.rename(p.with_suffix(".undone")); cleanup(o["source"])
    return dict(restored=ok, errors=errs)

def sha(p, part=False):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        if part: h.update(f.read(65536))
        else:
            for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def c_dupes(o):
    o = {**o, "min_mb": o.get("min_mb", 0)}
    by = {}
    for f in scan(o):
        if f["size"] > 0: by.setdefault(f["size"], []).append(f)
    groups, cand = [], [g for g in by.values() if len(g) > 1]
    for i, g in enumerate(cand, 1):
        parts = {}
        for f in g:
            try: parts.setdefault(sha(f["path"], True), []).append(f)
            except OSError: pass
        for pg in parts.values():
            if len(pg) < 2: continue
            full = {}
            for f in pg:
                try: full.setdefault(sha(f["path"]), []).append(f)
                except OSError: pass
            groups += [sorted(x, key=lambda f: f["mtime"]) for x in full.values() if len(x) > 1]
        if i % 5 == 0: emit(type="progress", done=i, total=len(cand))
    groups.sort(key=lambda g: -g[0]["size"] * (len(g) - 1))
    return dict(groups=[[dict(path=f["path"], mtime=f["mtime"], size=f["size"]) for f in g] for g in groups[:500]],
                wasted=sum(g[0]["size"] * (len(g) - 1) for g in groups), total_groups=len(groups))

def c_dedupe(o):
    paths, mode = o["paths"], o.get("mode", "quarantine")
    if mode == "trash" and send2trash:
        n = 0
        for p in paths:
            try: send2trash(p); n += 1
            except Exception: pass
        return dict(removed=n, journal=None)
    q = Path(o["source"], "_Duplicates")
    pairs = [(p, str(q / f"{i}_{Path(p).name}")) for i, p in enumerate(paths)]
    done, errs = move_all(o, pairs, "move")
    return dict(removed=len(done), errors=errs, journal=journal(o["source"], "dedupe", done) if done else None)

def c_stats(o):
    fs = scan({**o, "min_mb": 0}); cats, years = {}, {}
    for f in fs:
        c = EXT.get(f["ext"], "Other"); a = cats.setdefault(c, [0, 0]); a[0] += 1; a[1] += f["size"]
        y = str(datetime.fromtimestamp(f["mtime"]).year); years[y] = years.get(y, 0) + 1
    top = sorted(fs, key=lambda f: -f["size"])[:12]
    return dict(files=len(fs), size=sum(f["size"] for f in fs), cats={k: dict(n=v[0], size=v[1]) for k, v in cats.items()},
                years=dict(sorted(years.items())), largest=[dict(path=f["path"], size=f["size"]) for f in top])

if __name__ == "__main__":
    o = json.load(sys.stdin)
    try:
        emit(type="result", data=globals()["c_" + o["cmd"]](o))
    except Exception as e:
        emit(type="error", message=f"{type(e).__name__}: {e}")
