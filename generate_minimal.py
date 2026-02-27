from delphin import ace
import os

ACE_BIN = "/home/dengh/workspace/ANC-learning/bin/ace-0.9.34/ace"
GRAMMAR = "/home/dengh/workspace/ANC-learning/grammars/test-korean_20260226_165854/test-korean.dat"

env = dict(os.environ)
env["LANG"] = "en_US.UTF-8"

m = '''
[ LTOP: h0 INDEX: e2 [ e SF: prop-or-ques E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] RELS: < [ "exist_q_rel"<-1:-1> LBL: h4 ARG0: x3 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h5 BODY: h6 ]  [ "_n1_n_rel"<-1:-1> LBL: h7 ARG0: x3 ]  [ "exist_q_rel"<-1:-1> LBL: h8 ARG0: x9 [ x SPECI: bool COG-ST: uniq-id PNG: png ] RSTR: h10 BODY: h11 ]  [ "poss_rel"<-1:-1> LBL: h12 ARG0: e13 [ e SF: iforce E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] ARG1: x9 ARG2: x14 [ x SPECI: bool COG-ST: cog-st PNG: png ] ]  [ "exist_q_rel"<-1:-1> LBL: h15 ARG0: x14 RSTR: h16 BODY: h17 ]  [ "_n2_n_rel"<-1:-1> LBL: h18 ARG0: x14 ]  [ "_n3_n_rel"<-1:-1> LBL: h12 ARG0: x9 ]  [ "_tv1_v_rel"<-1:-1> LBL: h1 ARG0: e2 ARG1: x3 ARG2: x9 ] > HCONS: < h0 qeq h1 h5 qeq h7 h10 qeq h12 h16 qeq h18 > ICONS: < > ]
'''

response = ace.generate(
    GRAMMAR,
    m,
    executable=ACE_BIN,
    env=env,
    cmdargs=["-1"]
)

print("Number of generations:", len(response.results()))

if response.results():
    print("Surface:", response.result(0)["surface"])