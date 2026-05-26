
BOATRACE AI v10.7 見送り強化AI 変更点

① race_confidence() を強化

置換前:
if tactic["展開"] == "イン逃げ濃厚":
    confidence += 5
elif tactic["展開"] == "1飛び警戒":
    confidence -= 2
elif tactic["展開"] == "混戦":
    confidence -= 6

置換後:
if tactic["展開"] == "イン逃げ濃厚":
    confidence += 7
elif tactic["展開"] == "1飛び警戒":
    confidence -= 8
elif tactic["展開"] == "混戦":
    confidence -= 14
elif tactic["展開"] == "穴期待":
    confidence -= 5

② head_gap 判定を厳しくする

置換前:
if head_gap < 4:
    confidence -= 5

置換後:
if head_gap < 6:
    confidence -= 10
elif head_gap < 3:
    confidence -= 15

③ spread 判定を厳しくする

置換前:
if spread < 18:
    confidence -= 7

置換後:
if spread < 20:
    confidence -= 12
elif spread < 14:
    confidence -= 18

④ grade 判定を変更

置換前:
if confidence >= 90:
    grade = "熱🔥"
elif confidence >= 80:
    grade = "厚張り候補"
elif confidence >= 70:
    grade = "厳選候補"
elif confidence >= 62:
    grade = "穴期待"
else:
    grade = "見送り寄り"

置換後:
if confidence >= 92 and head_gap >= 8:
    grade = "熱🔥"
elif confidence >= 84 and head_gap >= 6:
    grade = "厚張り候補"
elif confidence >= 74:
    grade = "厳選候補"
elif confidence >= 66:
    grade = "穴期待"
else:
    grade = "見送り寄り"

⑤ 厳選AI最低値

置換前:
min_conf = st.slider("厳選表示の最低勝負度", 0, 100, 65)

置換後:
min_conf = st.slider("厳選表示の最低勝負度", 0, 100, 74)

⑥ 的中率重視の点数

置換前:
if preset == "的中率重視":
    default_count = 5

置換後:
if preset == "的中率重視":
    default_count = 4

⑦ 混戦レースは買い目を減らす

generate_predictions() 内:
df = balance_predictions(raw_df, racers, tactic, pick_count, preset)

の直後に追加:

if tactic["展開"] == "混戦":
    df = df.head(max(3, pick_count // 2))

Commit Summary:
v10.7 add skip race filtering AI
