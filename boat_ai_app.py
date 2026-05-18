# boat_ai_app.py
# -*- coding: utf-8 -*-

import re
import math
import itertools
from datetime import date, datetime
from typing import Dict, List, Tuple, Optional

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


# =========================================================
# Boat Race AI MVP
# - 出走表取得
# - 直前情報取得
# - オッズ取得
# - 買い目生成
# =========================================================

st.set_page_config(
    page_title="ボートレースAI MVP",
    page_icon="🚤",
    layout="wide",
)

JCD_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04", "多摩川": "05",
    "浜名湖": "06", "蒲郡": "07", "常滑": "08", "津": "09", "三国": "10",
    "びわこ": "11", "住之江": "12", "尼崎": "13", "鳴門": "14", "丸亀": "15",
    "児島": "16", "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}

JCD_NAME = {v: k for k, v in JCD_MAP.items()}

BASE = "https://www.boatrace.jp/owpc/pc/race"


# =========================================================
# Utility
# =========================================================

def normalize_text(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def to_float(x, default=0.0):
    try:
        s = str(x).replace("%", "").replace(",", "").strip()
        if s in ["", "-", "—", "nan", "None"]:
            return default
        return float(s)
    except Exception:
        return default


def safe_get(url: str) -> Optional[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; BoatRaceAI-MVP/1.0)",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200 and r.text:
            return r.text
        return None
    except Exception:
        return None


def build_url(page: str, rno: int, jcd: str, hd: str) -> str:
    return f"{BASE}/{page}?rno={rno}&jcd={jcd}&hd={hd}"


def extract_tables(html: str) -> List[pd.DataFrame]:
    try:
        return pd.read_html(html)
    except Exception:
        return []


# =========================================================
# Demo fallback
# =========================================================

def demo_racecard() -> pd.DataFrame:
    return pd.DataFrame([
        {"枠": 1, "選手名": "1号艇", "級別": "A1", "全国2連率": 48.2, "当地2連率": 45.0, "モーター2連率": 36.4, "ボート2連率": 33.1, "平均ST": 0.13},
        {"枠": 2, "選手名": "2号艇", "級別": "A2", "全国2連率": 39.5, "当地2連率": 41.2, "モーター2連率": 31.2, "ボート2連率": 29.8, "平均ST": 0.16},
        {"枠": 3, "選手名": "3号艇", "級別": "B1", "全国2連率": 28.8, "当地2連率": 25.6, "モーター2連率": 42.0, "ボート2連率": 34.5, "平均ST": 0.18},
        {"枠": 4, "選手名": "4号艇", "級別": "A2", "全国2連率": 37.1, "当地2連率": 33.2, "モーター2連率": 28.9, "ボート2連率": 31.0, "平均ST": 0.15},
        {"枠": 5, "選手名": "5号艇", "級別": "B1", "全国2連率": 24.5, "当地2連率": 21.1, "モーター2連率": 39.8, "ボート2連率": 37.2, "平均ST": 0.17},
        {"枠": 6, "選手名": "6号艇", "級別": "B1", "全国2連率": 22.0, "当地2連率": 20.0, "モーター2連率": 26.5, "ボート2連率": 30.1, "平均ST": 0.19},
    ])


def demo_beforeinfo() -> pd.DataFrame:
    return pd.DataFrame([
        {"枠": 1, "展示タイム": 6.72, "展示ST": 0.08, "進入": 1},
        {"枠": 2, "展示タイム": 6.78, "展示ST": 0.11, "進入": 2},
        {"枠": 3, "展示タイム": 6.70, "展示ST": 0.16, "進入": 3},
        {"枠": 4, "展示タイム": 6.80, "展示ST": 0.09, "進入": 4},
        {"枠": 5, "展示タイム": 6.74, "展示ST": 0.13, "進入": 5},
        {"枠": 6, "展示タイム": 6.85, "展示ST": 0.20, "進入": 6},
    ])


def demo_odds() -> pd.DataFrame:
    rows = []
    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        a, b, c = combo
        base = 8 + abs(a - 1) * 7 + abs(b - 2) * 4 + abs(c - 3) * 3
        odds = round(base + (a * b * c) / 3, 1)
        rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": odds})
    return pd.DataFrame(rows)


# =========================================================
# Parsers
# =========================================================

def parse_racecard(html: str) -> pd.DataFrame:
    text = normalize_text(BeautifulSoup(html, "html.parser").get_text(" "))
    tables = extract_tables(html)

    candidates = []
    for df in tables:
        flat_cols = [normalize_text(c) for c in df.columns]
        joined = " ".join(flat_cols) + " " + " ".join(map(str, df.head(3).values.flatten()))
        if any(k in joined for k in ["選手名", "級別", "登録番号", "モーター", "ボート", "全国"]):
            candidates.append(df)

    if not candidates:
        return pd.DataFrame()

    raw = candidates[0].copy()
    raw.columns = [normalize_text(c) for c in raw.columns]

    rows = []
    soup = BeautifulSoup(html, "html.parser")
    all_text = soup.get_text("\n")
    blocks = re.split(r"\n\s*(?=[1-6]\s*\n)", all_text)

    for waku in range(1, 7):
        name = f"{waku}号艇"
        grade = ""
        motor2 = 0.0
        boat2 = 0.0
        national2 = 0.0
        local2 = 0.0
        avg_st = 0.18

        for block in blocks:
            b = normalize_text(block)
            if not b.startswith(str(waku)):
                continue

            m_name = re.search(r"([一-龥ぁ-んァ-ンー]{2,}\s*[一-龥ぁ-んァ-ンー]{1,})", b)
            if m_name:
                name = normalize_text(m_name.group(1))

            m_grade = re.search(r"\b(A1|A2|B1|B2)\b", b)
            if m_grade:
                grade = m_grade.group(1)

            nums = [to_float(x) for x in re.findall(r"\d+\.\d+", b)]
            if nums:
                st_like = [n for n in nums if 0.05 <= n <= 0.35]
                if st_like:
                    avg_st = st_like[0]
                rate_like = [n for n in nums if 10 <= n <= 80]
                if len(rate_like) >= 1:
                    national2 = rate_like[0]
                if len(rate_like) >= 2:
                    local2 = rate_like[1]
                if len(rate_like) >= 3:
                    motor2 = rate_like[2]
                if len(rate_like) >= 4:
                    boat2 = rate_like[3]
            break

        rows.append({
            "枠": waku,
            "選手名": name,
            "級別": grade,
            "全国2連率": national2,
            "当地2連率": local2,
            "モーター2連率": motor2,
            "ボート2連率": boat2,
            "平均ST": avg_st,
        })

    df = pd.DataFrame(rows)
    return df


def parse_beforeinfo(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    rows = []

    for waku in range(1, 7):
        rows.append({
            "枠": waku,
            "展示タイム": 0.0,
            "展示ST": 0.18,
            "進入": waku,
        })

    df = pd.DataFrame(rows)

    # 大まかな正規表現抽出。公式HTML変更に備えて、失敗しても空にしない。
    lines = [normalize_text(x) for x in text.split("\n") if normalize_text(x)]
    joined = " ".join(lines)

    for waku in range(1, 7):
        pattern = rf"{waku}.*?(\d\.\d{{2}}).*?(?:F|L)?(0\.\d{{2}})"
        m = re.search(pattern, joined)
        if m:
            df.loc[df["枠"] == waku, "展示タイム"] = to_float(m.group(1))
            df.loc[df["枠"] == waku, "展示ST"] = to_float(m.group(2))

    # 進入は展示情報ページから完全抽出しづらい場合があるので、MVPでは枠なり基準
    return df


def parse_odds3t(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_text(soup.get_text(" "))

    rows = []
    # 例: 1-2-3 12.3 のような形を拾う
    for m in re.finditer(r"([1-6])\s*[-–]\s*([1-6])\s*[-–]\s*([1-6])\s+(\d+\.\d+)", text):
        a, b, c, odds = m.groups()
        if len({a, b, c}) == 3:
            rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": to_float(odds)})

    if rows:
        return pd.DataFrame(rows).drop_duplicates("買い目")

    # pandas tableから数字の並びを拾う簡易fallback
    tables = extract_tables(html)
    raw_text = ""
    for t in tables:
        raw_text += " ".join(map(str, t.values.flatten())) + " "

    for m in re.finditer(r"([1-6])\s*([1-6])\s*([1-6])\s*(\d+\.\d+)", raw_text):
        a, b, c, odds = m.groups()
        if len({a, b, c}) == 3:
            rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": to_float(odds)})

    return pd.DataFrame(rows).drop_duplicates("買い目") if rows else pd.DataFrame()


# =========================================================
# Data fetch
# =========================================================

def fetch_all(jcd: str, rno: int, hd: str, use_demo: bool = False):
    if use_demo:
        return demo_racecard(), demo_beforeinfo(), demo_odds(), {}

    urls = {
        "出走表": build_url("racelist", rno, jcd, hd),
        "直前情報": build_url("beforeinfo", rno, jcd, hd),
        "3連単オッズ": build_url("odds3t", rno, jcd, hd),
    }

    html_race = safe_get(urls["出走表"])
    html_before = safe_get(urls["直前情報"])
    html_odds = safe_get(urls["3連単オッズ"])

    racecard = parse_racecard(html_race) if html_race else pd.DataFrame()
    before = parse_beforeinfo(html_before) if html_before else pd.DataFrame()
    odds = parse_odds3t(html_odds) if html_odds else pd.DataFrame()

    if racecard.empty:
        racecard = demo_racecard()
    if before.empty:
        before = demo_beforeinfo()
    if odds.empty:
        odds = demo_odds()

    return racecard, before, odds, urls


# =========================================================
# AI logic
# =========================================================

def grade_score(g: str) -> float:
    return {"A1": 12, "A2": 8, "B1": 3, "B2": 0}.get(str(g).strip(), 4)


def minmax_score(series: pd.Series, reverse=False) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    mn, mx = s.min(), s.max()
    if mx == mn:
        return pd.Series([50] * len(s), index=s.index)
    out = (s - mn) / (mx - mn) * 100
    if reverse:
        out = 100 - out
    return out


def build_power_table(racecard: pd.DataFrame, before: pd.DataFrame) -> pd.DataFrame:
    df = racecard.merge(before, on="枠", how="left")

    for col in ["全国2連率", "当地2連率", "モーター2連率", "ボート2連率", "平均ST", "展示タイム", "展示ST", "進入"]:
        if col not in df.columns:
            df[col] = 0

    df["級別点"] = df["級別"].apply(grade_score)
    df["枠点"] = df["枠"].map({1: 18, 2: 11, 3: 8, 4: 7, 5: 4, 6: 2}).fillna(4)

    df["展示タイム点"] = minmax_score(df["展示タイム"].replace(0, df["展示タイム"].replace(0, pd.NA).mean()), reverse=True)
    df["展示ST点"] = minmax_score(df["展示ST"], reverse=True)
    df["平均ST点"] = minmax_score(df["平均ST"], reverse=True)
    df["全国点"] = minmax_score(df["全国2連率"])
    df["当地点"] = minmax_score(df["当地2連率"])
    df["モーター点"] = minmax_score(df["モーター2連率"])
    df["ボート点"] = minmax_score(df["ボート2連率"])

    df["総合指数"] = (
        df["枠点"] * 1.15 +
        df["級別点"] * 1.00 +
        df["展示タイム点"] * 0.20 +
        df["展示ST点"] * 0.18 +
        df["平均ST点"] * 0.12 +
        df["全国点"] * 0.16 +
        df["当地点"] * 0.08 +
        df["モーター点"] * 0.18 +
        df["ボート点"] * 0.08
    )

    df["順位"] = df["総合指数"].rank(ascending=False, method="first").astype(int)
    df = df.sort_values("総合指数", ascending=False).reset_index(drop=True)
    return df


def combo_probability(combo: Tuple[int, int, int], power: pd.DataFrame) -> float:
    score_map = dict(zip(power["枠"], power["総合指数"]))
    rank_map = dict(zip(power["枠"], power["順位"]))

    a, b, c = combo
    s1 = score_map.get(a, 0)
    s2 = score_map.get(b, 0)
    s3 = score_map.get(c, 0)

    # 1着重視、2-3着は相手力
    raw = s1 * 0.52 + s2 * 0.29 + s3 * 0.19

    # イン逃げ補正
    if a == 1:
        raw += 8

    # 上位艇が絡むほど加点
    raw += max(0, 7 - rank_map.get(a, 6)) * 1.8
    raw += max(0, 7 - rank_map.get(b, 6)) * 1.0
    raw += max(0, 7 - rank_map.get(c, 6)) * 0.7

    # 5・6頭はやや減点。ただし指数が高いなら残す
    if a in [5, 6] and rank_map.get(a, 6) > 2:
        raw -= 8

    return max(raw, 1)


def generate_tickets(power: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    odds_map = dict(zip(odds["買い目"], odds["オッズ"]))

    rows = []
    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        key = f"{combo[0]}-{combo[1]}-{combo[2]}"
        odd = odds_map.get(key, None)
        if odd is None or odd <= 0:
            continue

        p = combo_probability(combo, power)

        # オッズ込み期待値。MVPなので相対評価
        ev = p * math.log(max(odd, 1.01), 2)

        # 分類
        if p >= 78 and odd <= 25:
            label = "本線"
        elif odd >= 18 and p >= 62:
            label = "穴"
        elif p >= 56:
            label = "抑え"
        else:
            label = "見送り"

        rows.append({
            "買い目": key,
            "分類": label,
            "AI信頼度": round(p, 1),
            "オッズ": round(odd, 1),
            "期待値指数": round(ev, 1),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df[df["分類"] != "見送り"].copy()
    df = df.sort_values(["期待値指数", "AI信頼度"], ascending=False).reset_index(drop=True)

    main = df[df["分類"] == "本線"].head(5)
    hole = df[df["分類"] == "穴"].head(5)
    saver = df[df["分類"] == "抑え"].head(5)

    out = pd.concat([main, hole, saver], ignore_index=True)
    return out.drop_duplicates("買い目").reset_index(drop=True)


def heavy_stake_ai(tickets: pd.DataFrame) -> pd.DataFrame:
    if tickets.empty:
        return tickets

    df = tickets.copy()
    df["厚張りスコア"] = (
        df["AI信頼度"] * 0.65 +
        df["期待値指数"] * 0.25 -
        df["オッズ"].clip(lower=0, upper=80) * 0.04
    )

    df = df[
        (df["AI信頼度"] >= 68) &
        (df["期待値指数"] >= df["期待値指数"].quantile(0.55))
    ].copy()

    return df.sort_values("厚張りスコア", ascending=False).head(3)


def make_reason(power: pd.DataFrame) -> str:
    top = power.iloc[0]
    second = power.iloc[1]
    return (
        f"中心は{int(top['枠'])}号艇。展示タイム・ST・モーター気配を総合して上位評価。"
        f"相手筆頭は{int(second['枠'])}号艇。MVP版では枠・展示・ST・モーターを重視して判定。"
    )


# =========================================================
# UI
# =========================================================

st.title("🚤 ボートレースAI MVP")
st.caption("出走表・直前情報・オッズを取得し、本線 / 穴 / 抑え / 厚張り候補を自動生成します。")

with st.sidebar:
    st.header("設定")

    place_name = st.selectbox("場", list(JCD_MAP.keys()), index=list(JCD_MAP.keys()).index("桐生"))
    jcd = JCD_MAP[place_name]

    today = date.today()
    hd_date = st.date_input("開催日", value=today)
    hd = hd_date.strftime("%Y%m%d")

    rno = st.number_input("レース番号", min_value=1, max_value=12, value=1, step=1)

    use_demo = st.checkbox("デモデータで動かす", value=False)

    st.divider()
    st.write("重視項目")
    st.write("✅ 展示タイム")
    st.write("✅ ST")
    st.write("✅ モーター")
    st.write("✅ 進入")
    st.write("✅ 的中率＋期待値")

    run = st.button("AI予想を作成", type="primary", width="stretch")


if run:
    racecard, before, odds, urls = fetch_all(jcd, int(rno), hd, use_demo=use_demo)

    st.subheader(f"{place_name} {int(rno)}R")

    if urls:
        with st.expander("取得URL"):
            for k, v in urls.items():
                st.write(f"{k}: {v}")

    power = build_power_table(racecard, before)
    tickets = generate_tickets(power, odds)
    heavy = heavy_stake_ai(tickets)

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown("### 指数表")
        show_cols = [
            "順位", "枠", "選手名", "級別", "総合指数",
            "展示タイム", "展示ST", "平均ST", "モーター2連率", "全国2連率"
        ]
        st.dataframe(
            power[show_cols].round(2),
            width="stretch",
            hide_index=True,
        )

    with col2:
        st.markdown("### レース診断")
        st.info(make_reason(power))

        top1 = int(power.iloc[0]["枠"])
        top2 = int(power.iloc[1]["枠"])
        top3 = int(power.iloc[2]["枠"])
        st.metric("中心候補", f"{top1}号艇")
        st.metric("相手候補", f"{top2}号艇・{top3}号艇")

    st.divider()

    st.markdown("### 買い目")

    if tickets.empty:
        st.warning("買い目を生成できませんでした。オッズ取得が失敗している可能性があります。")
    else:
        for label in ["本線", "穴", "抑え"]:
            part = tickets[tickets["分類"] == label]
            if not part.empty:
                st.markdown(f"#### {label}")
                st.dataframe(part, width="stretch", hide_index=True)

    st.divider()

    st.markdown("### 厚張り厳選AI")
    if heavy.empty:
        st.warning("厚張り候補はありません。無理に厚張りしない判定です。")
    else:
        st.success("厚張り候補あり")
        st.dataframe(heavy, width="stretch", hide_index=True)

    st.divider()

    st.markdown("### Note / X 投稿用メモ")
    top_tickets = tickets.head(6)["買い目"].tolist() if not tickets.empty else []
    post_text = f"""【{place_name}{int(rno)}R ボートレース予想】

中心評価：{int(power.iloc[0]["枠"])}号艇
相手評価：{int(power.iloc[1]["枠"])}号艇・{int(power.iloc[2]["枠"])}号艇

狙い：
{make_reason(power)}

買い目：
{", ".join(top_tickets)}

※展示・ST・モーター・進入・オッズを総合評価しています。
※指数表・印とは連動していない場合もございます。
"""
    st.text_area("投稿文たたき台", value=post_text, height=260)

else:
    st.info("左の設定から場・日付・レース番号を選んで「AI予想を作成」を押してください。")