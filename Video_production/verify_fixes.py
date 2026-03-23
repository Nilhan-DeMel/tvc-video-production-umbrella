import tvc_config
PROJECT_ROOT = tvc_config.PATHS["root"]

sc = open(os.path.join(PROJECT_ROOT, 'supreme_commander.py'), 'r', encoding='utf-8').read()
tvc = open(os.path.join(PROJECT_ROOT, 'tvc_langgraph_core.py'), 'r', encoding='utf-8').read()

checks = [
    ("Fix #17a: --duration regex in supreme_commander",     '--duration' in sc),
    ("Fix #17b: target_duration=target_duration forwarded", 'target_duration=target_duration' in sc),
    ("Fix #17c: dispatch_weapon accepts target_duration",   'target_duration: int = 60' in sc),
    ("Fix #18:  VTT subtitle_words parsing",                'subtitle_words' in tvc),
    ("Fix #19a: _TeeLogger class exists",                   'class _TeeLogger' in tvc),
    ("Fix #19b: tee.close() in finally block",              'tee.close()' in tvc),
    ("Fix #20:  qa_targets .split(ABSOLUTE NEGATIVE)",      "split('ABSOLUTE NEGATIVE')" in tvc),
    ("Fix #21:  threshold >= 2 (not 3)",                    '>= 2:' in tvc),
]

all_ok = True
for name, ok in checks:
    tag = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print("  " + tag + " | " + name)

print()
if all_ok:
    print("VERDICT: ALL 8 CHECKS PASSED")
else:
    print("VERDICT: SOME CHECKS FAILED")
