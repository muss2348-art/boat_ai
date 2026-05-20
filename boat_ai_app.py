# boat_ai_app.py
# Boat Race AI v7.4
# 全角艇番対応・出走表ズレ修正版

import re
import math
import itertools
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(page_title="Boat AI v7.4", page_icon="🚤", layout="wide")

BASE_URL = "https://www.boatrace.jp/owpc/pc/race"
JST = timezone(timedelta(hours=9))


def today_jst():
    return datetime.now(JST).date()


JCD_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}

ZEN_TO_HAN = str.maketrans("１２３４５６７８９０", "1234567890")


def clean_text(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()


def normalize_num_text(x):
    return clean_text(x).translate(ZEN_TO_HAN)


def to_float(x, default=0.0):
    try:
        s = normalize_num_text(x).replace("%", "").replace(",", "")
        if s in ["", "-", "—", "None", "nan", "欠場"]:
            return default
        return float(s)
    except Exception:
        return default


def safe_get(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None


def build_url(page, rno, jcd, hd):
    return f"{BASE_URL}/{page}?rno={rno}&jcd={jcd}&hd={hd}"


def fetch_pages(jcd, rno, hd):
    urls = {
        "出走表": build_url("racelist", rno, jcd, hd),
        "直前情報": build_url("beforeinfo", rno, jcd, hd),
        "3連単オッズ": build_url("odds3t", rno, jcd, hd),
    }
    return urls, {k: safe_get(v) for k, v in urls.items()}


def default_boat_row(waku, status="出走表取得弱い"):
    return {
        "艇": waku,
        "選手": f"{waku}号艇",
        "級別": "B1",
        "全国2連率": 0.0,
        "当地2連率": 0.0,
        "モーター": 0.0,
        "ボート": 0.0,
        "平均ST": 0.18,
        "データ状態": status,
    }


def parse_racelist(html):
    if not html:
        return pd.DataFrame([default_boat_row(i) for i in range(1, 7)])

    soup = BeautifulSoup(html, "html.parser")
    lines = [clean_text(x) for x in soup.get_text("\n").split("\n") if clean_text(x)]

    blocks = {i: [] for i in range(1, 7)}
    current = None

    for line in lines:
        nline = normalize_num_text(line)

        if re.fullmatch(r"[1-6]", nline):
            current = int(nline)
            blocks[current].append(line)
            continue

        if current in blocks:
            blocks[current].append(line)

    rows = []

    for waku in range(1, 7):
        block = blocks.get(waku, [])
        if not block:
            rows.append(default_boat_row(waku))
            continue

        joined = clean_text(" ".join(block))
        joined_norm = normalize_num_text(joined)

        grade = "B1"
        reg_index = None

        for i, line in enumerate(block):
            nline = normalize_num_text(line)
            m = re.search(r"\b\d{4}\s*/\s*(A1|A2|B1|B2)\b", nline)
            if m:
                grade = m.group(1)
                reg_index = i
                break

        name = f"{waku}号艇"
        if reg_index is not None:
            for j in range(reg_index + 1, min(reg_index + 5, len(block))):
                candidate = clean_text(block[j])
                if re.search(r"[一-龥ぁ-んァ-ンー]", candidate):
                    if not any(x in candidate for x in ["F", "L", "歳", "kg", "全国", "当地"]):
                        name = candidate
                        break

        avg_st = 0.18
        national2 = 0.0
        local2 = 0.0
        motor2 = 0.0
        boat2 = 0.0

        avg_idx = None
        for i, line in enumerate(block):
            nline = normalize_num_text(line)
            if re.search(r"\b0\.\d{2}\b\s+\d+\.\d+", nline):
                avg_idx = i
                nums = re.findall(r"\d+\.\d+", nline)
                if nums:
                    avg_st = to_float(nums[0], 0.18)
                break

        if avg_idx is not None:
            def line_float(offset):
                idx = avg_idx + offset
                if 0 <= idx < len(block):
                    vals = re.findall(r"\d+\.\d+", normalize_num_text(block[idx]))
                    if vals:
                        return to_float(vals[0])
                return 0.0

            national2 = line_float(1)
            local2 = line_float(3)
            motor2 = line_float(5)
            boat2 = line_float(7)

        rows.append({
            "艇": waku,
            "選手": name,
            "級別": grade,
            "全国2連率": round(national2, 2),
            "当地2連率": round(local2, 2),
            "モーター": round(motor2, 2),
            "ボート": round(boat2, 2),
            "平均ST": round(avg_st, 2),
            "データ状態": "OK全角対応" if name != f"{waku}号艇" else "名前取得弱い",
        })

    return pd.DataFrame(rows)


def parse_beforeinfo(html):
    base = pd.DataFrame([
        {"艇": i, "展示": 0.0, "展示ST": 0.18, "進入": i, "直前状態": "未取得"}
        for i in range(1, 7)
    ])

    if not html:
        return base

    soup = BeautifulSoup(html, "html.parser")
    text = normalize_num_text(soup.get_text(" "))

    times = [to_float(x) for x in re.findall(r"\b6\.\d{2}\b", text)]
    times = [x for x in times if 6.40 <= x <= 7.20]

    st_vals = []
    for s in re.findall(r"(?<!\d)(?:F|L)?\.?\d{2}(?!\d)", text):
        s = s.replace("F", "").replace("L", "")
        v = to_float("0" + s if s.startswith(".") else "0." + s)
        if 0.00 <= v <= 0.40:
            st_vals.append(v)

    for i in range(6):
        if i < len(times):
            base.loc[base["艇"] == i + 1, "展示"] = times[i]
            base.loc[base["艇"] == i + 1, "直前状態"] = "展示取得"
        if i < len(st_vals):
            base.loc[base["艇"] == i + 1, "展示ST"] = st_vals[i]

    return base


def all_3t_combos():
    return [f"{a}-{b}-{c}" for a, b, c in itertools.permutations([1, 2, 3, 4, 5, 6], 3)]


def parse_odds3t(html):
    if not html:
        return pd.DataFrame()

    rows = []
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_num_text(soup.get_text(" "))

    patterns = [
        r"([1-6])\s*[-–]\s*([1-6])\s*[-–]\s*([1-6])\s+(\d+\.\d+)",
        r"\b([1-6]{3})\b\s+(\d+\.\d+)",
    ]

    for p in patterns:
        for m in re.findall(p, text):
            if len(m) == 4:
                a, b, c, odd = m
                if len({a, b, c}) == 3:
                    rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": to_float(odd), "取得方式": "text"})
            elif len(m) == 2:
                combo, odd = m
                if len(set(combo)) == 3:
                    rows.append({"買い目": f"{combo[0]}-{combo[1]}-{combo[2]}", "オッズ": to_float(odd), "取得方式": "text123"})

    try:
        tables = pd.read_html(html)
        for ti, t in enumerate(tables):
            flat = [normalize_num_text(x) for x in t.values.flatten()]
            odds_values = []
            for s in flat:
                for x in re.findall(r"\d+\.\d+", s):
                    v = to_float(x)
                    if 1.0 <= v <= 9999:
                        odds_values.append(v)

            if len(odds_values) >= 80:
                combos = all_3t_combos()
                for i in range(min(len(odds_values), len(combos))):
                    rows.append({"買い目": combos[i], "オッズ": odds_values[i], "取得方式": f"table_restore_{ti}"})
    except Exception:
        pass

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["オッズ"] = pd.to_numeric(df["オッズ"], errors="coerce")
    df = df.dropna(subset=["オッズ"])
    df = df[(df["オッズ"] > 0) & (df["オッズ"] < 9999)]
    df = df.drop_duplicates("買い目")
    df = df.sort_values("オッズ", ascending=True).reset_index(drop=True)
    df["人気順"] = range(1, len(df) + 1)
    return df


def make_fallback_odds(power):
    rank_map = dict(zip(power["艇"], power["順位"]))
    rows = []

    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        a, b, c = combo
        odd = (
            4.5
            + rank_map.get(a, 6) * 2.5
            + rank_map.get(b, 6) * 2.0
            + rank_map.get(c, 6) * 1.5
            + max(0, a - 1) * 2.0
            + max(0, c - 3) * 2.5
        )
        rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": round(odd, 1), "人気順": 0, "取得方式": "AI仮オッズ"})

    return pd.DataFrame(rows)


def grade_score(g):
    return {"A1": 18, "A2": 12, "B1": 5, "B2": 1}.get(str(g), 5)


def neutral_if_zero(value, neutral):
    v = to_float(value)
    return neutral if v <= 0 else v


def calc_power(race, before):
    df = race.merge(before, on="艇", how="left")
    scores = []

    for _, r in df.iterrows():
        waku = int(r["艇"])
        score = 0.0

        score += {1: 30, 2: 18, 3: 12, 4: 11, 5: 5, 6: 2}.get(waku, 0)
        score += grade_score(r["級別"])

        national = neutral_if_zero(r["全国2連率"], 25)
        local = neutral_if_zero(r["当地2連率"], 25)
        motor = neutral_if_zero(r["モーター"], 30)
        boat = neutral_if_zero(r["ボート"], 30)

        score += national * 0.65
        score += local * 0.40
        score += motor * 0.70
        score += boat * 0.25

        avg_st = to_float(r["平均ST"], 0.18)
        score += max(0, (0.22 - avg_st) * 120)

        tenji = to_float(r["展示"], 0.0)
        if tenji > 0:
            score += max(0, (6.95 - tenji) * 80)

        tenji_st = to_float(r["展示ST"], 0.18)
        score += max(0, (0.22 - tenji_st) * 80)

        if waku == 4 and tenji > 0 and tenji <= 6.78:
            score += 8

        if waku == 5 and motor >= 40:
            score += 5

        scores.append(round(score, 1))

    df["AI指数"] = scores
    df = df.sort_values("AI指数", ascending=False).reset_index(drop=True)
    df["順位"] = range(1, len(df) + 1)
    return df


def combo_score(combo, power):
    score_map = dict(zip(power["艇"], power["AI指数"]))
    rank_map = dict(zip(power["艇"], power["順位"]))

    a, b, c = combo
    s = score_map.get(a, 0) * 0.52 + score_map.get(b, 0) * 0.30 + score_map.get(c, 0) * 0.18

    if a == 1:
        s += 10
    if a in [2, 3]:
        s += 3
    if a == 4:
        s += 5
    if a in [5, 6]:
        s -= 6
    if c in [4, 5, 6]:
        s += 3

    s += max(0, 7 - rank_map.get(a, 6)) * 2
    return round(max(s, 1), 1)


def build_tickets(power, odds):
    odd_map = dict(zip(odds["買い目"], odds["オッズ"]))
    pop_map = dict(zip(odds["買い目"], odds["人気順"])) if "人気順" in odds.columns else {}

    rows = []

    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        key = f"{combo[0]}-{combo[1]}-{combo[2]}"
        odd = odd_map.get(key)
        if odd is None or odd <= 0:
            continue

        ai = combo_score(combo, power)
        popularity = pop_map.get(key, 0)
        ev = ai * math.log(odd + 1)

        if popularity and popularity <= 5 and odd < 8 and ai < 92:
            ev *= 0.88

        if ai >= 95 and 5 <= odd <= 25:
            label = "熱🔥"
        elif ai >= 86 and odd <= 35:
            label = "本線"
        elif odd >= 18 and ai >= 70:
            label = "穴"
        elif ai >= 62:
            label = "抑え"
        else:
            continue

        rows.append({
            "買い目": key,
            "分類": label,
            "AI信頼度": round(ai, 1),
            "オッズ": round(odd, 1),
            "人気順": popularity,
            "期待値": round(ev, 1),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    return df.sort_values(["期待値", "AI信頼度"], ascending=False).reset_index(drop=True)


def selected_tickets(df, ticket_count=10):
    if df.empty:
        return df

    hot_count = max(1, round(ticket_count * 0.20))
    main_count = max(1, round(ticket_count * 0.35))
    hole_count = max(0, round(ticket_count * 0.30))
    saver_count = max(0, ticket_count - hot_count - main_count - hole_count)

    out = pd.concat([
        df[df["分類"] == "熱🔥"].head(hot_count),
        df[df["分類"] == "本線"].head(main_count),
        df[df["分類"] == "穴"].head(hole_count),
        df[df["分類"] == "抑え"].head(saver_count),
    ]).drop_duplicates("買い目")

    if len(out) < ticket_count:
        add = df[~df["買い目"].isin(out["買い目"])].head(ticket_count - len(out))
        out = pd.concat([out, add])

    return out.head(ticket_count).reset_index(drop=True)


def heavy_ai(df):
    if df.empty:
        return df

    out = df.copy()
    out["厚張り指数"] = out["AI信頼度"] * 0.70 + out["期待値"] * 0.22 - out["オッズ"] * 0.08

    out = out[
        (out["AI信頼度"] >= 82)
        & (out["オッズ"] >= 4.0)
        & (out["オッズ"] <= 35.0)
    ]

    return out.sort_values("厚張り指数", ascending=False).head(3).reset_index(drop=True)


st.title("🚤 Boat Race AI v7.4")
st.caption("全角艇番対応・出走表ズレ修正版 / 熱🔥 / 本線 / 穴 / 抑え / 厳選 / 厚張りAI")

with st.sidebar:
    st.header("設定")
    st.caption(f"日本時間の今日：{today_jst().strftime('%Y/%m/%d')}")

    place = st.selectbox("場", list(JCD_MAP.keys()))
    jcd = JCD_MAP[place]

    race_date = st.date_input("日付", value=today_jst())
    hd = race_date.strftime("%Y%m%d")

    race_no = st.number_input("レース", min_value=1, max_value=12, value=1)
    ticket_count = st.slider("買い目点数", 1, 20, 10, 1)

    allow_fallback_odds = st.checkbox("オッズ取得失敗時はAI仮オッズで表示", value=True)
    show_debug = st.checkbox("取得デバッグ表示", value=False)

    run = st.button("AI予想開始", width="stretch")


if run:
    urls, htmls = fetch_pages(jcd, int(race_no), hd)

    race = parse_racelist(htmls.get("出走表"))
    before = parse_beforeinfo(htmls.get("直前情報"))

    st.subheader(f"{place} {int(race_no)}R")
    st.caption(f"取得対象日：{hd}")

    with st.expander("取得URL"):
        for k, v in urls.items():
            st.write(f"{k}: {v}")

    if race.empty:
        st.error("出走表を取得できませんでした。開催日・場・レース番号を確認してください。")
        st.stop()

    power = calc_power(race, before)

    odds = parse_odds3t(htmls.get("3連単オッズ"))
    odds_count = len(odds)
    odds_status = f"実オッズ取得OK：{odds_count}件"

    if odds.empty or odds_count < 80:
        if allow_fallback_odds:
            odds = make_fallback_odds(power)
            odds_status = f"実オッズ取得不足：{odds_count}件 → AI仮オッズで表示"
        else:
            st.error(f"3連単オッズ取得不足です。取得件数：{odds_count}件")
            st.stop()

    tickets = build_tickets(power, odds)
    selected = selected_tickets(tickets, ticket_count)
    heavy = heavy_ai(tickets)

    st.info(f"データ状態：{odds_status}")

    if show_debug:
        st.markdown("### 出走表取得デバッグ")
        st.dataframe(race, width="stretch", hide_index=True)

        st.markdown("### オッズ取得デバッグ")
        st.write(f"取得できたオッズ件数：{odds_count}")
        if not odds.empty:
            st.dataframe(odds.head(40), width="stretch", hide_index=True)

    st.markdown("### 指数表")

    show_cols = [
        "順位", "艇", "選手", "級別", "AI指数",
        "展示", "展示ST", "平均ST",
        "全国2連率", "当地2連率", "モーター", "ボート", "データ状態"
    ]

    st.dataframe(power[show_cols], width="stretch", hide_index=True)

    if tickets.empty:
        st.warning("買い目を生成できませんでした。データ不足または基準未満です。")
        st.stop()

    for title, label, n in [
        ("## 熱🔥", "熱🔥", 3),
        ("## 本線", "本線", 5),
        ("## 穴", "穴", 5),
        ("## 抑え", "抑え", 5),
    ]:
        part = tickets[tickets["分類"] == label].head(n)
        if not part.empty:
            st.markdown(title)
            st.dataframe(part, width="stretch", hide_index=True)

    st.markdown("## 厳選買い目")
    st.success(f"{ticket_count}点に厳選")
    st.dataframe(selected, width="stretch", hide_index=True)

    st.markdown("## 厚張り厳選AI")
    if heavy.empty:
        st.warning("厚張り候補なし。無理に厚張りしない判定です。")
    else:
        st.dataframe(heavy, width="stretch", hide_index=True)

    top = power.iloc[0]
    st.info(
        f"""
中心評価：{int(top["艇"])}号艇  
展示・ST・モーター・全国/当地成績を総合評価。  
本線中心に、穴目と抑えを混ぜて期待値も見る構成です。
"""
    )

else:
    st.info("左の設定から、場・日付・レースを選んでAI予想開始を押してください。")