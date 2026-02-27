from delphin import ace
import os

ACE_BIN = "/home/dengh/workspace/ANC-learning/bin/ace-0.9.34/ace"
GRAMMAR = "/home/dengh/workspace/ANC-learning/minimal.dat"

env = dict(os.environ)
env["LANG"] = "en_US.UTF-8"

# TODO: 把这里替换成 minimal-grammar lexicon.tdl 里的词
SENT = "n1 iv"

resp = ace.parse(
    GRAMMAR,
    SENT,
    executable=ACE_BIN,
    env=env,
    cmdargs=["-1"]   # 只要一个结果，输出更干净
)

print("Sentence:", SENT)
print("Parses:", len(resp.results()))

if resp.results():
    r0 = resp.result(0)
    print("\nMRS (string):")
    print(r0["mrs"])
else:
    # 打印 ACE 的错误信息（如果有）
    try:
        print("\nNo parses. ACE stdout/stderr may contain hints:")
        print(resp.get("stderr", ""))
    except Exception:
        pass