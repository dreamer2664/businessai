"""Build a .kdw knowledge pack from trimmed passages using the local embedding cache.
   python3 packs/build_pack.py <ext_dir> <out.kdw> [--dims 128]
   Passages without a cached embedding are embedded with the engine first (cache: ~/.cache/bai/known_*.npy)."""
import numpy as np, os, sys, subprocess, shutil
H = os.path.expanduser; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ext, out = sys.argv[1], sys.argv[2]; dims = sys.argv[sys.argv.index("--dims") + 1] if "--dims" in sys.argv else "128"
KK, KE = H("~/.cache/bai/known_keys.npy"), H("~/.cache/bai/known_emb.npy")
keys = list(np.load(KK, allow_pickle=True)) if os.path.exists(KK) else []; emb = np.load(KE) if os.path.exists(KE) else np.zeros((0, 384), np.float32)
known = {k: i for i, k in enumerate(keys)}
ps = [l.rstrip("\n").split("\t", 1)[1] for l in open(os.path.join(ext, "passages.tsv"), encoding="utf-8")]
todo = [t for t in dict.fromkeys(ps) if t not in known]
if todo:
    print(f"embedding {len(todo)} new passages …", flush=True)
    tmp = os.path.join(ext, "_todo.txt"); open(tmp, "w", encoding="utf-8").write("".join(t + "\n" for t in todo))
    with open(tmp, encoding="utf-8") as fi, open(tmp + ".f32", "wb") as fo:
        subprocess.run([os.path.join(ROOT, "release/kdr-brain-lite"), os.path.join(ROOT, "release/brain.kdr"), "embed", "160"], stdin=fi, stdout=fo, stderr=subprocess.DEVNULL, check=True)
    NE = np.fromfile(tmp + ".f32", dtype=np.float32).reshape(-1, 384); assert len(NE) == len(todo)
    for t in todo: known[t] = len(keys); keys.append(t)
    emb = np.concatenate([emb, NE]); np.save(KK, np.array(keys, dtype=object)); np.save(KE, emb)
E = np.stack([emb[known[t]] for t in ps]); os.makedirs(os.path.join(ext, "emb"), exist_ok=True); E.tofile(os.path.join(ext, "emb/part_00.f32"))
shutil.copy(os.path.join(ext, "articles.tsv"), os.path.join(ext, "shuffled_articles.tsv")); shutil.copy(os.path.join(ext, "passages.tsv"), os.path.join(ext, "shuffled_passages.tsv"))
open(os.path.join(ext, "embed_part_00"), "w", encoding="utf-8").write("".join(t + "\n" for t in ps))
subprocess.run([sys.executable, os.path.join(ROOT, "engine/scripts/wiki_pack.py"), ext, out, "--dims", dims], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"{out}: {len(ps)} passages, {os.path.getsize(out)/1e6:.1f} MB")
