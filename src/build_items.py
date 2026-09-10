#!/usr/bin/env python3
"""
合并 204 + 60 → items_264.json，并给所有编译失败的条目补上 javac 消息。

现有 204 条里有 28 条 compiles=false，当初生成时还没有编译器数据，
必须一并补上——否则同一批样本里两部分证据面不一致。

依赖：merged.pkl、existing_204.json、batch2.json
用法：python build_items.py
"""
import json, sys
import pandas as pd

MERGED   = "merged.pkl"
EXISTING = "existing_204.json"
BATCH2   = "batch2.json"
OUT      = "items_264.json"


def norm(s):
    return "\n".join(l.rstrip() for l in str(s).strip().splitlines())


def main():
    m = pd.read_pickle(MERGED)
    old = json.load(open(EXISTING, encoding="utf-8"))
    new = json.load(open(BATCH2, encoding="utf-8"))

    # (pid, 规范化代码) -> (compile_result, compiler_output)
    lut = {}
    for _, r in m.iterrows():
        lut[(int(r.ProblemID), norm(r.Code))] = (
            r.compile_result,
            None if pd.isna(r.compiler_output) else str(r.compiler_output).strip(),
        )
    print(f"查找表 {len(lut)} 条")

    # 现有 204 条只有 id/pid/code，需要从原工作台补回完整字段
    # → 这一步由 patch_map 提供：id -> compiler_output
    patch, missing = {}, []
    for x in old:
        hit = lut.get((x["pid"], norm(x["code"])))
        if hit is None:
            missing.append(x["id"])
            continue
        res, msg = hit
        patch[x["id"]] = {"compile_result": res, "compiler_output": msg}

    print(f"现有 204 条中匹配上 {len(patch)}，未匹配 {len(missing)}")
    if missing:
        print("  未匹配 id:", missing[:10])

    json.dump({"patch": patch, "batch2": new},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

    n_err = sum(1 for v in patch.values() if v["compile_result"] == "Error")
    n_msg = sum(1 for v in patch.values()
                if v["compile_result"] == "Error" and v["compiler_output"])
    print(f"\n✅ 写出 {OUT}")
    print(f"   现有条目中编译失败 {n_err} 条，其中有 javac 消息 {n_msg} 条（应相等）")
    print(f"   新增条目 {len(new)} 条")
    if n_err != n_msg:
        sys.exit("❌ 有编译失败条目缺 javac 消息，先查合并那步")


if __name__ == "__main__":
    main()
