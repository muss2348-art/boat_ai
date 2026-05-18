# boat_ai_app.py
# Boat Race AI v3
# 熱🔥 / 本線 / 穴 / 抑え / 厳選 / 厚張りAI
# 買い目点数選択対応版

import math
import itertools
from datetime import date

import pandas as pd
import streamlit as st


# =====================================================
# CONFIG
# =====================================================

st.set_page_config(
    page_title="Boat AI v3",
    page_icon="🚤",
    layout="wide"
)

# =====================================================
# DEMO DATA
# =====================================================

def demo_racecard():

    return pd.DataFrame([
        {
            "艇": 1,
            "選手": "1号艇",
            "級別": "A1",
            "全国2連率": 52.1,
            "当地2連率": 49.5,
            "モーター": 42.0,
            "ボート": 36.0,
            "平均ST": 0.13,
            "展示": 6.71,
        },
        {
            "艇": 2,
            "選手": "2号艇",
            "級別": "A1",
            "全国2連率": 46.8,
            "当地2連率": 40.2,
            "モーター": 39.0,
            "ボート": 31.2,
            "平均ST": 0.14,
            "展示": 6.74,
        },
        {
            "艇": 3,
            "選手": "3号艇",
            "級別": "A2",
            "全国2連率": 38.1,
            "当地2連率": 34.2,
            "モーター": 28.0,
            "ボート": 30.0,
            "平均ST": 0.16,
            "展示": 6.79,
        },
        {
            "艇": 4,
            "選手": "4号艇",
            "級別": "A2",
            "全国2連率": 35.4,
            "当地2連率": 32.0,
            "モーター": 48.0,
            "ボート": 38.0,
            "平均ST": 0.15,
            "展示": 6.73,
        },
        {
            "艇": 5,
            "選手": "5号艇",
            "級別": "B1",
            "全国2連率": 25.1,
            "当地2連率": 21.0,
            "モーター": 44.0,
            "ボート": 35.0,
            "平均ST": 0.17,
            "展示": 6.75,
        },
        {
            "艇": 6,
            "選手": "6号艇",
            "級別": "B1",
            "全国2連率": 18.2,
            "当地2連率": 15.0,
            "モーター": 29.0,
            "ボート": 24.0,
            "平均ST": 0.19,
            "展示": 6.84,
        },
    ])


# =====================================================
# SCORE
# =====================================================

def grade_score(g):

    return {
        "A1": 18,
        "A2": 12,
        "B1": 5,
        "B2": 0,
    }.get(g, 5)


def calc_power(df):

    out = df.copy()

    scores = []

    for _, r in out.iterrows():

        score = 0

        # 枠補正
        score += {
            1: 30,
            2: 18,
            3: 12,
            4: 11,
            5: 5,
            6: 2
        }.get(r["艇"], 0)

        # 級別
        score += grade_score(r["級別"])

        # ST
        score += max(0, (0.20 - r["平均ST"]) * 120)

        # 展示
        score += max(0, (6.90 - r["展示"]) * 100)

        # 全国
        score += r["全国2連率"] * 0.7

        # 当地
        score += r["当地2連率"] * 0.5

        # モーター
        score += r["モーター"] * 0.6

        # ボート
        score += r["ボート"] * 0.3

        # 4カド穴
        if r["艇"] == 4 and r["展示"] <= 6.74:
            score += 8

        scores.append(round(score, 1))

    out["AI指数"] = scores

    out = out.sort_values(
        "AI指数",
        ascending=False
    ).reset_index(drop=True)

    out["順位"] = range(1, len(out)+1)

    return out


# =====================================================
# 疑似オッズ
# =====================================================

def make_odds():

    rows = []

    for c in itertools.permutations([1,2,3,4,5,6], 3):

        a,b,c3 = c

        odd = (
            5
            + abs(a-1)*5
            + abs(b-2)*3
            + abs(c3-3)*2
            + (a*b*c3)/2
        )

        rows.append({
            "買い目": f"{a}-{b}-{c3}",
            "オッズ": round(odd,1)
        })

    return pd.DataFrame(rows)


# =====================================================
# COMBO SCORE
# =====================================================

def combo_score(combo, power):

    score_map = dict(zip(
        power["艇"],
        power["AI指数"]
    ))

    rank_map = dict(zip(
        power["艇"],
        power["順位"]
    ))

    a,b,c = combo

    s = 0

    s += score_map[a] * 0.52
    s += score_map[b] * 0.30
    s += score_map[c] * 0.18

    # イン逃げ
    if a == 1:
        s += 10

    # 4カド
    if a == 4:
        s += 5

    # 穴補正
    if c in [4,5,6]:
        s += 3

    # 上位補正
    s += max(0, 7-rank_map[a]) * 2

    return round(s,1)


# =====================================================
# BUILD TICKETS
# =====================================================

def build_tickets(power, odds):

    odd_map = dict(zip(
        odds["買い目"],
        odds["オッズ"]
    ))

    rows = []

    for combo in itertools.permutations([1,2,3,4,5,6],3):

        key = f"{combo[0]}-{combo[1]}-{combo[2]}"

        odd = odd_map.get(key, 20)

        ai = combo_score(combo, power)

        ev = ai * math.log(odd+1)

        label = "抑え"

        if ai >= 95 and odd <= 20:
            label = "熱🔥"

        elif ai >= 88:
            label = "本線"

        elif odd >= 18 and ai >= 72:
            label = "穴"

        elif ai >= 66:
            label = "抑え"

        rows.append({
            "買い目": key,
            "分類": label,
            "AI信頼度": round(ai,1),
            "オッズ": round(odd,1),
            "期待値": round(ev,1)
        })

    df = pd.DataFrame(rows)

    df = df.sort_values(
        ["期待値","AI信頼度"],
        ascending=False
    )

    return df


# =====================================================
# 厳選AI
# =====================================================

def selected_tickets(df, ticket_count=10):

    hot_count = max(1, round(ticket_count * 0.20))
    main_count = max(1, round(ticket_count * 0.40))
    hole_count = max(1, round(ticket_count * 0.25))
    saver_count = max(1, ticket_count - hot_count - main_count - hole_count)

    hot = df[df["分類"]=="熱🔥"].head(hot_count)
    main = df[df["分類"]=="本線"].head(main_count)
    hole = df[df["分類"]=="穴"].head(hole_count)
    saver = df[df["分類"]=="抑え"].head(saver_count)

    out = pd.concat([
        hot,
        main,
        hole,
        saver
    ])

    out = out.drop_duplicates("買い目")

    if len(out) < ticket_count:

        add = df[
            ~df["買い目"].isin(out["買い目"])
        ].head(ticket_count - len(out))

        out = pd.concat([
            out,
            add
        ])

    return out.head(ticket_count)


# =====================================================
# 厚張りAI
# =====================================================

def heavy_ai(df):

    out = df.copy()

    out["厚張り指数"] = (
        out["AI信頼度"] * 0.75
        + out["期待値"] * 0.25
        - out["オッズ"] * 0.08
    )

    out = out[
        out["AI信頼度"] >= 85
    ]

    out = out.sort_values(
        "厚張り指数",
        ascending=False
    )

    return out.head(3)


# =====================================================
# UI
# =====================================================

st.title("🚤 Boat Race AI v3")

st.caption(
    "熱🔥 / 本線 / 穴 / 抑え / 厳選 / 厚張りAI"
)

with st.sidebar:

    st.header("設定")

    place = st.selectbox(
        "場",
        [
            "桐生","戸田","江戸川","平和島",
            "多摩川","浜名湖","蒲郡","常滑",
            "津","住之江","丸亀","大村"
        ]
    )

    race_date = st.date_input(
        "日付",
        value=date.today()
    )

    race_no = st.number_input(
        "レース",
        min_value=1,
        max_value=12,
        value=1
    )

    ticket_count = st.slider(
        "買い目点数",
        min_value=1,
        max_value=20,
        value=10,
        step=1
    )

    run = st.button(
        "AI予想開始",
        width="stretch"
    )


# =====================================================
# MAIN
# =====================================================

if run:

    race = demo_racecard()

    power = calc_power(race)

    odds = make_odds()

    tickets = build_tickets(
        power,
        odds
    )

    selected = selected_tickets(
        tickets,
        ticket_count
    )

    heavy = heavy_ai(
        tickets
    )

    # ==========================================
    # 指数表
    # ==========================================

    st.subheader(
        f"{place} {race_no}R"
    )

    st.markdown("### 指数表")

    show_cols = [
        "順位",
        "艇",
        "選手",
        "級別",
        "AI指数",
        "展示",
        "平均ST",
        "モーター"
    ]

    st.dataframe(
        power[show_cols],
        width="stretch",
        hide_index=True
    )

    # ==========================================
    # 熱🔥
    # ==========================================

    hot = tickets[
        tickets["分類"]=="熱🔥"
    ].head(3)

    if not hot.empty:

        st.markdown("## 熱🔥")

        st.dataframe(
            hot,
            width="stretch",
            hide_index=True
        )

    # ==========================================
    # 本線
    # ==========================================

    main = tickets[
        tickets["分類"]=="本線"
    ].head(5)

    st.markdown("## 本線")

    st.dataframe(
        main,
        width="stretch",
        hide_index=True
    )

    # ==========================================
    # 穴
    # ==========================================

    hole = tickets[
        tickets["分類"]=="穴"
    ].head(5)

    st.markdown("## 穴")

    st.dataframe(
        hole,
        width="stretch",
        hide_index=True
    )

    # ==========================================
    # 抑え
    # ==========================================

    saver = tickets[
        tickets["分類"]=="抑え"
    ].head(5)

    st.markdown("## 抑え")

    st.dataframe(
        saver,
        width="stretch",
        hide_index=True
    )

    # ==========================================
    # 厳選
    # ==========================================

    st.markdown("## 厳選買い目")

    st.success(
        f"{ticket_count}点に厳選"
    )

    st.dataframe(
        selected,
        width="stretch",
        hide_index=True
    )

    # ==========================================
    # 厚張り
    # ==========================================

    st.markdown("## 厚張り厳選AI")

    st.warning(
        "厚張り候補"
    )

    st.dataframe(
        heavy,
        width="stretch",
        hide_index=True
    )

    # ==========================================
    # AI COMMENT
    # ==========================================

    top = power.iloc[0]["艇"]

    st.info(
        f"""
中心は{top}号艇。
展示・ST・モーター気配を高評価。
本線中心だが穴目も混ぜて期待値重視。
"""
    )

else:

    st.info(
        "左の設定からAI予想開始を押してください。"
    )