from delphin.codecs import simplemrs
from delphin import mrs

m1_str = r'''
[ LTOP: h0 INDEX: e2 [ e SF: prop-or-ques E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] RELS: < [ "exist_q_rel"<-1:-1> LBL: h4 ARG0: x3 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h5 BODY: h6 ]  [ "_n1_n_rel"<-1:-1> LBL: h7 ARG0: x3 ]  [ "exist_q_rel"<-1:-1> LBL: h8 ARG0: x9 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h10 BODY: h11 ]  [ "nominalized_rel"<-1:-1> LBL: h12 ARG0: x9 ARG1: h13 ]  [ "exist_q_rel"<-1:-1> LBL: h14 ARG0: x15 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h16 BODY: h17 ]  [ "_n2_n_rel"<-1:-1> LBL: h18 ARG0: x15 ]  [ "exist_q_rel"<-1:-1> LBL: h19 ARG0: x20 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h21 BODY: h22 ]  [ "_n3_n_rel"<-1:-1> LBL: h23 ARG0: x20 ]  [ "_tv1_v_rel"<-1:-1> LBL: h24 ARG0: e25 [ e SF: prop-or-ques E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] ARG1: x15 ARG2: x20 ]  [ "_tv2_v_rel"<-1:-1> LBL: h1 ARG0: e2 ARG1: x3 ARG2: x9 ] > HCONS: < h0 qeq h1 h5 qeq h7 h10 qeq h12 h13 qeq h24 h16 qeq h18 h21 qeq h23 > ICONS: < > ]
'''

m2_str = r'''
[ LTOP: h0 INDEX: e2 [ e SF: prop-or-ques E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] RELS: < [ "exist_q_rel"<-1:-1> LBL: h4 ARG0: x3 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h5 BODY: h6 ]  [ "_n1_n_rel"<-1:-1> LBL: h7 ARG0: x3 ]  [ "_tv2_v_rel"<-1:-1> LBL: h1 ARG0: e2 ARG1: x3 ARG2: x8 [ x SPECI: bool COG-ST: uniq-id PNG: png ] ]  [ "exist_q_rel"<-1:-1> LBL: h9 ARG0: x8 RSTR: h10 BODY: h11 ]  [ "exist_q_rel"<-1:-1> LBL: h12 ARG0: x13 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h14 BODY: h15 ]  [ "_n2_n_rel"<-1:-1> LBL: h16 ARG0: x13 ]  [ "_tv1_v_rel"<-1:-1> LBL: h17 ARG0: e18 [ e SF: iforce E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] ARG1: x13 ARG2: x19 [ x SPECI: bool COG-ST: cog-st PNG: png ] ]  [ "nominalized_rel"<-1:-1> LBL: h20 ARG0: x8 ARG1: h21 ]  [ "exist_q_rel"<-1:-1> LBL: h22 ARG0: x19 RSTR: h23 BODY: h24 ]  [ "_n3_n_rel"<-1:-1> LBL: h25 ARG0: x19 ] > HCONS: < h0 qeq h1 h5 qeq h7 h10 qeq h20 h14 qeq h16 h21 qeq h17 h23 qeq h25 > ICONS: < > ]
'''


# =========================
# 解析
# =========================
m1 = simplemrs.decode(m1_str)
m2 = simplemrs.decode(m2_str)


# =========================
# Pretty Print
# =========================
def pretty(title, m):
    print(f"\n===== {title} =====")
    print(simplemrs.encode(m, indent=True))


# =========================
# EP signature（用于比较）
# =========================
def ep_sig(ep):
    return (
        ep.predicate,
        ep.label,
        tuple(sorted(ep.args.items()))
    )


# =========================
# 差异分析
# =========================
def diff_mrs(m1, m2):
    print("\n========================")
    print("DIFF REPORT")
    print("========================")

    # TOP / INDEX
    print("\n=== TOP / INDEX ===")
    if m1.top != m2.top:
        print("TOP differs:", m1.top, "!=", m2.top)
    else:
        print("TOP same:", m1.top)

    if m1.index != m2.index:
        print("INDEX differs:", m1.index, "!=", m2.index)
    else:
        print("INDEX same:", m1.index)

    # RELS
    print("\n=== RELS only in m1 ===")
    rels1 = {ep_sig(ep) for ep in m1.rels}
    rels2 = {ep_sig(ep) for ep in m2.rels}

    for r in sorted(rels1 - rels2):
        print(r)

    print("\n=== RELS only in m2 ===")
    for r in sorted(rels2 - rels1):
        print(r)

    # HCONS
    print("\n=== HCONS only in m1 ===")
    h1 = {(hc.hi, hc.relation, hc.lo) for hc in m1.hcons}
    h2 = {(hc.hi, hc.relation, hc.lo) for hc in m2.hcons}

    for x in sorted(h1 - h2):
        print(x)

    print("\n=== HCONS only in m2 ===")
    for x in sorted(h2 - h1):
        print(x)

    # ICONS
    print("\n=== ICONS only in m1 ===")
    i1 = {(ic.left, ic.relation, ic.right) for ic in m1.icons}
    i2 = {(ic.left, ic.relation, ic.right) for ic in m2.icons}

    for x in sorted(i1 - i2):
        print(x)

    print("\n=== ICONS only in m2 ===")
    for x in sorted(i2 - i1):
        print(x)

    # predicate 层对比（很实用）
    print("\n=== Predicate diff ===")
    p1 = {ep.predicate for ep in m1.rels}
    p2 = {ep.predicate for ep in m2.rels}

    print("only in m1:", p1 - p2)
    print("only in m2:", p2 - p1)

if __name__ == "__main__":
    pretty("MRS 1", m1)
    pretty("MRS 2", m2)

    print("\n========================")
    print("ISOMORPHIC CHECK")
    print("========================")
    print("isomorphic (strict):", mrs.is_isomorphic(m1, m2, properties=True))
    print("isomorphic (ignore properties):", mrs.is_isomorphic(m1, m2, properties=False))

    diff_mrs(m1, m2)