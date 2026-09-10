#!/usr/bin/env python3
"""
LAK27 补充批次抽样 —— 解开「编译失败」与「全盘失败」的混淆。

产出 batch2.json：60 条，两格各 30
  A  compile_result == Success 且全部测试失败   （现有样本里只有 1 条 → 补 30）
  B  compile_result == Error                    （现有 28 条 → 再补 30，合计 58）

编译失败的条目带上 javac 消息（compiler_output）。

依赖：merged.pkl、tiktoc/test-case-query-results/test_cases-1-26-24.csv、existing_204.json
用法：python sample_batch2.py
"""
import csv, json, hashlib, sys
import pandas as pd

MERGED    = "merged.pkl"
TESTCASES = "tiktoc/test-case-query-results/test_cases-1-26-24.csv"
EXISTING  = "existing_204.json"
OUT       = "batch2.json"

N_A = 30          # 编译通过 · 全挂
N_B = 30          # 编译失败
SEED = 20260910

PID_FAM = {1:'math', 3:'logic', 5:'logic', 13:'math', 17:'logic', 20:'math',
           22:'math', 24:'math', 25:'math', 34:'string', 37:'string',
           39:'string', 40:'string', 46:'array', 71:'array'}


def norm(s):
    return "\n".join(l.rstrip() for l in str(s).strip().splitlines())


def read_mysql_csv(path):
    """坑 1：该文件用反斜杠转义，不是 RFC 4180。"""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh, doublequote=False, escapechar="\\"))
    return pd.DataFrame(rows[1:], columns=rows[0])


def as_flags(bc):
    """binary_correctness 可能是 list / ndarray / '0,1,1' / '[0, 1, 1]'。"""
    if isinstance(bc, str):
        cleaned = bc.strip().strip("[]")
        parts = [p for p in cleaned.replace(",", " ").split() if p != ""]
        return [int(float(p)) for p in parts]
    return [int(float(x)) for x in list(bc)]


def make_id(pid, code, taken):
    base = f"{pid}|{norm(code)}"
    for salt in range(1000):
        h = hashlib.md5((base + ("" if salt == 0 else f"#{salt}")).encode()).hexdigest()
        iid = "IT" + h[:8].upper()
        if iid not in taken:
            return iid
    raise RuntimeError("item_id 生成失败")


def main():
    m = pd.read_pickle(MERGED)
    tc = read_mysql_csv(TESTCASES)
    existing = json.load(open(EXISTING, encoding="utf-8"))

    # 参照值自检（坑 2：条数对齐不代表内容对齐）
    def peek(pid, n):
        sub = tc[tc.coding_prompt_id.astype(str) == str(pid)]
        sub = sub.assign(_i=sub["id"].astype(int)).sort_values("_i").reset_index(drop=True)
        r = sub.iloc[n - 1]
        return r["input"], r["expected_output"]
    checks = [((13, 13), ("61, false", "1")),
              ((40, 1),  ('"breadjambread"', '"jam"'))]
    for (pid, n), want in checks:
        got = peek(pid, n)
        if got != want:
            sys.exit(f"❌ 测试用例参照值不符 P{pid}#{n}: 期望 {want}，实得 {got}")
    print("✅ 测试用例参照值通过")

    # 每题的测试用例，按 id 升序 —— 与 binary_correctness 严格对齐
    tests_by_pid = {}
    for pid, g in tc.groupby(tc.coding_prompt_id.astype(int)):
        g = g.assign(_i=g["id"].astype(int)).sort_values("_i")
        tests_by_pid[pid] = list(zip(g["input"], g["expected_output"]))

    taken = {x["id"] for x in existing}
    used_code = {(x["pid"], norm(x["code"])) for x in existing}

    m = m[m.ProblemID.isin(PID_FAM)].copy()
    m["code_key"] = list(zip(m.ProblemID, m.Code.map(norm)))
    m = m[~m.code_key.isin(used_code)]                       # 排除已在 204 里的
    m = m[m.compile_result.notna()]

    def flags_ok(row):
        pid = int(row.ProblemID)
        if pid not in tests_by_pid:
            return None
        f = as_flags(row.binary_correctness)
        return f if len(f) == len(tests_by_pid[pid]) else None

    m["tflags"] = m.apply(flags_ok, axis=1)
    dropped = m["tflags"].isna().sum()
    m = m[m["tflags"].notna()].copy()
    print(f"   对齐失败丢弃 {dropped} 条，剩 {len(m)} 条候选")

    m["nt"] = m["tflags"].map(len)
    m["nf"] = m["tflags"].map(lambda f: sum(1 for x in f if x == 0))

    pool_a = m[(m.compile_result == "Success") & (m.nf == m.nt)]
    pool_b = m[m.compile_result == "Error"]
    print(f"   A 池（编译通过·全挂）: {len(pool_a)}   B 池（编译失败）: {len(pool_b)}")

    def draw(pool, n, label):
        if len(pool) == 0:
            sys.exit(f"❌ {label} 池为空")
        n = min(n, len(pool))
        # 按题目分层，避免全挤在一两道题上
        per = max(1, n // pool.ProblemID.nunique())
        picked = (pool.groupby("ProblemID", group_keys=False)
                      .apply(lambda g: g.sample(min(per, len(g)), random_state=SEED)))
        if len(picked) < n:
            rest = pool.drop(picked.index).sample(n - len(picked), random_state=SEED)
            picked = pd.concat([picked, rest])
        return picked.sample(frac=1, random_state=SEED).head(n)

    sel = pd.concat([draw(pool_a, N_A, "A"), draw(pool_b, N_B, "B")])

    out = []
    for _, r in sel.iterrows():
        pid = int(r.ProblemID)
        flags = r["tflags"]
        cases = tests_by_pid[pid]
        nf, nt = int(r.nf), int(r.nt)
        sev = "total" if nf == nt else ("near-miss" if nf == 1 else "partial")
        compiles = (r.compile_result == "Success")
        iid = make_id(pid, r.Code, taken)
        taken.add(iid)
        out.append({
            "id": iid,
            "pid": pid,
            "sev": sev,
            "fam": PID_FAM[pid],
            "compiles": bool(compiles),
            "nf": nf,
            "nt": nt,
            "compiler_output": None if compiles else str(r.compiler_output or "").strip(),
            "prompt": str(r.prompt).strip(),
            "code": str(r.Code),
            "tests": [{"i": i + 1, "in": c[0], "exp": c[1], "ok": bool(flags[i] == 1)}
                      for i, c in enumerate(cases)],
        })

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n✅ 写出 {OUT}：{len(out)} 条")
    print("   编译失败:", sum(1 for x in out if not x["compiles"]),
          " 编译通过·全挂:", sum(1 for x in out if x["compiles"]))
    miss = [x["id"] for x in out if not x["compiles"] and not x["compiler_output"]]
    print("   编译失败但无 javac 消息:", len(miss), "(应为 0)", miss[:5])
    print("   涉及题目:", sorted({x["pid"] for x in out}))


if __name__ == "__main__":
    main()
