#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path
from delphin import ace
from delphin import derivation as drv

def parse_one(ace_bin: str, grammar_dat: str, sent: str, n: int):
    try:
        return ace.parse(
            grammar_dat, sent,
            executable=ace_bin,
            cmdargs=["-n", str(n)],
            stderr=subprocess.DEVNULL,  # silence NOTE
        )
    except TypeError:
        # older PyDelphin: no stderr kwarg
        return ace.parse(
            grammar_dat, sent,
            executable=ace_bin,
            cmdargs=["-n", str(n)],
        )

def leaf_label(node) -> str:
    # Leaves usually carry a 'form' (token string)
    form = getattr(node, "form", None)
    if form is None:
        # some versions store it as .orth or in .tokens
        form = getattr(node, "orth", None)
    return f'"{form}"' if form is not None else "(leaf)"

def node_label(node) -> str:
    # Internal node: rule name is usually .entity (or .label depending on version)
    ent = getattr(node, "entity", None) or getattr(node, "label", None) or "?"
    start = getattr(node, "start", None)
    end = getattr(node, "end", None)
    span = f"{start}-{end}" if start is not None and end is not None else ""
    return f"{ent} [{span}]".strip()

def render_text(node, indent="", last=True) -> str:
    """
    Pretty-print derivation as an ASCII tree.
    """
    branch = "└─ " if last else "├─ "
    lines = []
    if getattr(node, "daughters", None):
        lines.append(indent + branch + node_label(node))
        new_indent = indent + ("   " if last else "│  ")
        ds = list(node.daughters)
        for i, ch in enumerate(ds):
            lines.append(render_text(ch, new_indent, i == len(ds) - 1))
    else:
        # leaf
        lines.append(indent + branch + f"{node_label(node)}  {leaf_label(node)}")
    return "\n".join(lines)

def to_dot(node) -> str:
    """
    Produce Graphviz DOT for the derivation tree.
    """
    lines = ["digraph Deriv {", "  node [shape=box,fontname=Helvetica];"]
    counter = {"i": 0}

    def new_id():
        counter["i"] += 1
        return f"n{counter['i']}"

    def walk(n):
        nid = new_id()
        lbl = node_label(n)
        if not getattr(n, "daughters", None):
            lbl = f"{lbl}\\n{leaf_label(n)}"
        lines.append(f'  {nid} [label="{lbl}"];')
        for ch in getattr(n, "daughters", []) or []:
            cid = walk(ch)
            lines.append(f"  {nid} -> {cid};")
        return nid

    walk(node)
    lines.append("}")
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ace", required=True)
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--sent", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--mrs", action="store_true")
    ap.add_argument("--dot", action="store_true", help="also output Graphviz DOT")
    ap.add_argument("--dot-out", default="", help="write DOT to this file (optional)")
    args = ap.parse_args()

    resp = parse_one(args.ace, args.grammar, args.sent, args.n)
    results = resp.get("results", [])
    print(f"Sentence: {args.sent}")
    print(f"Parses: {len(results)}\n")
    if not results:
        return

    for idx, r in enumerate(results, 1):
        print(f"=== Parse {idx} ===")
        deriv_str = r.get("derivation")
        if deriv_str:
            d = drv.from_string(deriv_str)
            print(render_text(d))
            if args.dot:
                dot = to_dot(d)
                if args.dot_out:
                    Path(args.dot_out).write_text(dot, encoding="utf-8")
                    print(f"\n[DOT written to {args.dot_out}]")
                else:
                    print("\n[DOT]")
                    print(dot)
        else:
            print("(No derivation field in result; cannot render tree.)")

        if args.mrs:
            print("\n[MRS]")
            print(r.get("mrs", "(no mrs)"))
        print()

if __name__ == "__main__":
    main()