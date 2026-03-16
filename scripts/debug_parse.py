#!/usr/bin/env python3

import argparse
import re
import subprocess
from pathlib import Path

from delphin import ace
from delphin import derivation as drv

from utils import ACE_BIN


def parse_one(grammar_dat: str, sent: str, n: int):
    try:
        return ace.parse(
            grammar_dat,
            sent,
            executable=ACE_BIN,
            cmdargs=["-n", str(n)],
            stderr=subprocess.DEVNULL,
        )
    except TypeError:
        return ace.parse(
            grammar_dat,
            sent,
            executable=ACE_BIN,
            cmdargs=["-n", str(n)],
        )


def leaf_label(node) -> str:
    form = getattr(node, "form", None)
    if form is None:
        form = getattr(node, "orth", None)
    return form if form is not None else "?"


def node_label(node) -> str:
    return getattr(node, "entity", None) or getattr(node, "label", None) or "?"


def render_derivation(node, indent="", last=True) -> str:
    branch = "└─ " if last else "├─ "
    lines = []

    if getattr(node, "daughters", None):
        lines.append(indent + branch + node_label(node))
        new_indent = indent + ("   " if last else "│  ")
        ds = list(node.daughters)
        for i, ch in enumerate(ds):
            lines.append(render_derivation(ch, new_indent, i == len(ds) - 1))
    else:
        lines.append(indent + branch + leaf_label(node))

    return "\n".join(lines)


def render_simple_tree(node) -> str:
    if not getattr(node, "daughters", None):
        return leaf_label(node)
    children = [render_simple_tree(ch) for ch in node.daughters]
    return f"({node_label(node)} {' '.join(children)})"


def to_dot(node) -> str:
    lines = [
        "digraph Deriv {",
        '  rankdir=TB;',
        '  node [shape=box, fontname="Helvetica", fontsize=11];',
        '  edge [arrowsize=0.7];'
    ]
    counter = {"i": 0}

    def new_id():
        counter["i"] += 1
        return f"n{counter['i']}"

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def walk(n):
        nid = new_id()

        if getattr(n, "daughters", None):
            lbl = node_label(n)
            shape = "box"
        else:
            lbl = leaf_label(n)
            shape = "ellipse"

        lines.append(f'  {nid} [label="{esc(lbl)}", shape={shape}];')

        for ch in getattr(n, "daughters", []) or []:
            cid = walk(ch)
            lines.append(f"  {nid} -> {cid};")

        return nid

    walk(node)
    lines.append("}")
    return "\n".join(lines)


def render_graph(dot_text: str, out_path: Path, fmt: str):
    try:
        proc = subprocess.run(
            ["dot", f"-T{fmt}", "-o", str(out_path)],
            input=dot_text,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        raise SystemExit(
            "ERROR: Graphviz 'dot' not found.\n"
            "Install with:\n"
            "  sudo apt install graphviz"
        )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "dot failed")


def safe_dir_name(text: str) -> str:
    s = text.strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", s)
    s = re.sub(r"_+", "_", s)
    return s[:120] if len(s) > 120 else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--sent", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--mrs", action="store_true")
    ap.add_argument("--tree", action="store_true", help="print ACE tree if available")
    ap.add_argument("--simple", action="store_true", help="print simplified bracket tree")
    ap.add_argument("--dot", action="store_true", help="print DOT text")
    ap.add_argument("--dot-out", default="", help="directory to save DOT files")
    ap.add_argument("--svg-out", default="", help="directory to save SVG files")
    ap.add_argument("--png-out", default="", help="directory to save PNG files")
    args = ap.parse_args()

    resp = parse_one(args.grammar, args.sent, args.n)
    results = resp.get("results", [])

    print(f"Sentence: {args.sent}")
    print(f"Parses: {len(results)}\n")

    if not results:
        return

    sent_dirname = safe_dir_name(args.sent)

    for idx, r in enumerate(results, 1):
        print(f"=== Parse {idx} ===")

        if args.tree and r.get("tree"):
            print("[ACE tree]")
            print(r["tree"])
            print()

        deriv_str = r.get("derivation")
        if deriv_str:
            d = drv.from_string(deriv_str)

            if args.simple:
                print("[Simple tree]")
                print(render_simple_tree(d))
                print()
            else:
                print("[Derivation]")
                print(render_derivation(d))
                print()

            need_dot = args.dot or args.dot_out or args.svg_out or args.png_out
            dot = to_dot(d) if need_dot else None

            if args.dot:
                print("[DOT]")
                print(dot)
                print()

            if args.dot_out:
                outdir = Path(args.dot_out) / sent_dirname
                outdir.mkdir(parents=True, exist_ok=True)
                out = outdir / f"parse_{idx}.dot"
                out.write_text(dot, encoding="utf-8")
                print(f"[DOT written to {out}]")

            if args.svg_out:
                outdir = Path(args.svg_out) / sent_dirname
                outdir.mkdir(parents=True, exist_ok=True)
                out = outdir / f"parse_{idx}.svg"
                render_graph(dot, out, "svg")
                print(f"[SVG written to {out}]")

            if args.png_out:
                outdir = Path(args.png_out) / sent_dirname
                outdir.mkdir(parents=True, exist_ok=True)
                out = outdir / f"parse_{idx}.png"
                render_graph(dot, out, "png")
                print(f"[PNG written to {out}]")
        else:
            print("(No derivation field in result)\n")

        if args.mrs:
            print("[MRS]")
            print(r.get("mrs", "(no mrs)"))
            print()


if __name__ == "__main__":
    main()