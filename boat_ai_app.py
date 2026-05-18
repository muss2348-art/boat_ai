# boat_ai_app.py
# Boat Race AI v6
# 出走表取得さらに強化版
# 2号艇/4号艇などの取りこぼし対策
# 熱🔥 / 本線 / 穴 / 抑え / 厳選 / 厚張りAI / 買い目点数 1〜20点

import re
import math
import itertools
from datetime import date

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(
    page_title="Boat AI v6",
    page_icon="🚤",
    layout="wide"
)

BASE_URL = "https://www.boatrace.jp/owpc/pc/race"

JCD_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}


# =====================================================
# UTILS
# =====================================================

def clean_text(x):
    if x is None:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def to_float(x, default=0.0):
    try:
        s = str(x).replace("%", "").replace(",", "").strip()
        if s in ["", "-", "—", "None", "nan"]:
            return default
        return float(s)
    except Exception:
        return default


def safe_get(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and r.text:
            return r.text
        return None
    except Exception:
        return None


def build_url(page, rno, jcd, hd):
    return f"{BASE_URL}/{page}?rno={rno}&jcd={jcd}&hd={hd}"


def fetch_pages(jcd, rno, hd):
    urls = {
        "出走表": build_url("racelist", rno, jcd, hd),
        "直前情報": build_url("beforeinfo", rno, jcd, hd),
        "3連単オッズ": build_url("odds3t", rno, jcd, hd),
    }
    htmls = {name: safe_get(url) for name, url in urls.items()}
    return urls, htmls


# =====================================================
# 出走表取得 v6
# =====================================================

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


def extract_grade(text):
    m = re.search(r"\b(A1|A2|B1|B2)\b", text)
    return m.group(1) if m else ""


def extract_name(text, waku):
    text = clean_text(text)

    bad = [
        "全国", "当地", "モーター", "ボート", "勝率", "展示",
        "平均", "進入", "能力", "事故", "早見", "F", "L"
    ]

    patterns = [
        r"\b(A1|A2|B1|B2)\b\s*([一-龥ぁ-んァ-ンー・]{2,}\s*[一-龥ぁ-んァ-ンー・]{1,})",
        r"\d{4}\s*\b(A1|A2|B1|B2)\b\s*([一-龥ぁ-んァ-ンー・]{2,}\s*[一-龥ぁ-んァ-ンー・]{1,})",
        r"([一-龥]{1,4}\s+[一-龥ぁ-んァ-ンー・]{1,6})",
    ]

    for p in patterns:
        m = re.search(p, text)
        if not m:
            continue

        name = m.group(len(m.groups()))
        name = clean_text(name)
        name = re.sub(r"(全国|当地|モーター|ボート|勝率|平均).*", "", name).strip()

        if name and len(name) <= 12 and not any(b in name for b in bad):
            return name

    return f"{waku}号艇"


def extract_avg_st(nums):
    st_like = [n for n in nums if 0.05 <= n <= 0.35]
    return st_like[0] if st_like else 0.18


def extract_rates_from_text(text):
    nums = [to_float(x) for x in re.findall(r"\d+\.\d+", text)]

    avg_st = extract_avg_st(nums)

    vals = [n for n in nums if 0 <= n <= 100 and not (0.05 <= n <= 0.35)]

    national2 = 0.0
    local2 = 0.0
    motor2 = 0.0
    boat2 = 0.0

    # 公式は「勝率/2連率/3連率」のセットが多い
    if len(vals) >= 3:
        national2 = vals[1]
    if len(vals) >= 6:
        local2 = vals[4]
    if len(vals) >= 9:
        motor2 = vals[7]
    if len(vals) >= 12:
        boat2 = vals[10]

    # 2連率がなぜか小さい場合は隣の数値で補正
    if 0 < national2 < 10 and len(vals) >= 4:
        national2 = vals[2]
    if 0 < local2 < 10 and len(vals) >= 7:
        local2 = vals[5]

    return round(national2, 2), round(local2, 2), round(motor2, 2), round(boat2, 2), avg_st


def find_candidate_blocks(soup):
    blocks = []

    # 1. tr単位
    for tr in soup.find_all("tr"):
        txt = clean_text(tr.get_text(" "))
        if re.search(r"\b(A1|A2|B1|B2)\b", txt):
            blocks.append(txt)

    # 2. div単位
    for div in soup.find_all("div"):
        txt = clean_text(div.get_text(" "))
        if len(txt) > 30 and re.search(r"\b(A1|A2|B1|B2)\b", txt):
            blocks.append(txt)

    # 3. ページ全体を艇番で分割
    full = soup.get_text("\n")
    split_blocks = re.split(r"\n\s*(?=[1-6]\s*\n)", full)
    for b in split_blocks:
        txt = clean_text(b)
        if re.search(r"\b(A1|A2|B1|B2)\b", txt):
            blocks.append(txt)

    # 重複削除
    unique = []
    seen = set()
    for b in blocks:
        if b not in seen:
            seen.add(b)
            unique.append(b)

    return unique


def block_score_for_waku(block, waku):
    score = 0

    if block.startswith(str(waku)):
        score += 8

    if re.search(rf"(^|\s){waku}(\s|号|$)", block):
        score += 5

    if f"table1_boatImage{waku}" in block:
        score += 10

    if re.search(r"\b(A1|A2|B1|B2)\b", block):
        score += 3

    nums = re.findall(r"\d+\.\d+", block)
    score += min(len(nums), 12)

    # 他艇番っぽい始まりなら少し減点
    for other in range(1, 7):
        if other != waku and block.startswith(str(other)):
            score -= 5

    return score


def parse_racelist_by_tables(html):
    try:
        tables = pd.read_html(html)
    except Exception:
        return pd.DataFrame()

    rows = []

    for waku in range(1, 7):
        best_text = ""

        for t in tables:
            raw = " ".join(map(str, t.values.flatten()))
            raw = clean_text(raw)

            pieces = re.split(rf"(?=(?:^|\s){waku}\s)", raw)

            for p in pieces:
                if not p:
                    continue
                if re.search(r"\b(A1|A2|B1|B2)\b", p):
                    if block_score_for_waku(p, waku) > block_score_for_waku(best_text, waku):
                        best_text = p

        if best_text:
            name = extract_name(best_text, waku)
            grade = extract_grade(best_text)
            national2, local2, motor2, boat2, avg_st = extract_rates_from_text(best_text)

            rows.append({
                "艇": waku,
                "選手": name,
                "級別": grade if grade else "B1",
                "全国2連率": national2,
                "当地2連率": local2,
                "モーター": motor2,
                "ボート": boat2,
                "平均ST": avg_st,
                "データ状態": "OKテーブル" if name != f"{waku}号艇" else "テーブル弱い",
            })

    return pd.DataFrame(rows)


def parse_racelist(html):
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")

    table_df = parse_racelist_by_tables(html)

    block_rows = []

    blocks = find_candidate_blocks(soup)

    for waku in range(1, 7):
        best = ""
        best_score = -999

        # classから近い親要素も狙う
        boat_img = soup.find(class_=re.compile(f"table1_boatImage{waku}"))
        if boat_img:
            parent = boat_img.find_parent(["tr", "div", "tbody"])
            if parent:
                txt = clean_text(parent.get_text(" "))
                s = block_score_for_waku(txt, waku) + 10
                if s > best_score:
                    best = txt
                    best_score = s

        for b in blocks:
            s = block_score_for_waku(b, waku)
            if s > best_score:
                best = b
                best_score = s

        if not best:
            block_rows.append(default_boat_row(waku))
            continue

        name = extract_name(best, waku)
        grade = extract_grade(best)
        national2, local2, motor2, boat2, avg_st = extract_rates_from_text(best)

        status = "OK補完"
        if name == f"{waku}号艇":
            status = "出走表取得弱い"

        block_rows.append({
            "艇": waku,
            "選手": name,
            "級別": grade if grade else "B1",
            "全国2連率": national2,
            "当地2連率": local2,
            "モーター": motor2,
            "ボート": boat2,
            "平均ST": avg_st,
            "データ状態": status,
        })

    block_df = pd.DataFrame(block_rows)

    # table_df と block_df を合成。名前が取れている方を優先。
    final_rows = []

    for waku in range(1, 7):
        b = block_df[block_df["艇"] == waku]
        t = table_df[table_df["艇"] == waku]

        if b.empty and t.empty:
            final_rows.append(default_boat_row(waku))
            continue

        row = b.iloc[0].to_dict() if not b.empty else default_boat_row(waku)

        if not t.empty:
            tr = t.iloc[0].to_dict()

            # 選手名
            if row["選手"] == f"{waku}号艇" and tr.get("選手") != f"{waku}号艇":
                row["選手"] = tr.get("選手")

            # 級別
            if not row.get("級別") or row.get("級別") == "B1":
                if tr.get("級別"):
                    row["級別"] = tr.get("級別")

            # 数値は大きい方ではなく、0なら補完
            for col in ["全国2連率", "当地2連率", "モーター", "ボート"]:
                if to_float(row.get(col)) <= 0 and to_float(tr.get(col)) > 0:
                    row[col] = tr.get(col)

            if to_float(row.get("平均ST"), 0.18) == 0.18 and to_float(tr.get("平均ST"), 0.18) != 0.18:
                row["平均ST"] = tr.get("平均ST")

        # 0データが多すぎる場合、完全減点しないため中立補正
        zero_count = sum(1 for c in ["全国2連率", "当地2連率", "モーター", "ボート"] if to_float(row[c]) <= 0)

        if row["選手"] != f"{waku}号艇" and zero_count >= 3:
            row["データ状態"] = "名前OK/数値不足"
        elif row["選手"] != f"{waku}号艇":
            row["データ状態"] = "OK補完"

        final_rows.append(row)

    return pd.DataFrame(final_rows)


# =====================================================
# 直前情報
# =====================================================

def parse_beforeinfo(html):
    base = pd.DataFrame([
        {"艇": i, "展示": 0.0, "展示ST": 0.18, "進入": i, "直前状態": "未取得"}
        for i in range(1, 7)
    ])

    if not html:
        return base

    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.get_text(" "))

    times = [to_float(x) for x in re.findall(r"\b6\.\d{2}\b", text)]
    times = [x for x in times if 6.40 <= x <= 7.20]

    st_vals = []
    for s in re.findall(r"(?<!\d)(?:F|L)?\.?\d{2}(?!\d)", text):
        s = s.replace("F", "").replace("L", "")
        if s.startswith("."):
            v = to_float("0" + s)
        else:
            v = to_float("0." + s)
        if 0.00 <= v <= 0.40:
            st_vals.append(v)

    for i in range(6):
        if i < len(times):
            base.loc[base["艇"] == i + 1, "展示"] = times[i]
            base.loc[base["艇"] == i + 1, "直前状態"] = "展示取得"
        if i < len(st_vals):
            base.loc[base["艇"] == i + 1, "展示ST"] = st_vals[i]

    return base


# =====================================================
# オッズ
# =====================================================

def parse_odds3t(html):
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.get_text(" "))

    rows = []
    pattern = r"([1-6])\s*[-–]\s*([1-6])\s*[-–]\s*([1-6])\s+(\d+\.\d+)"

    for a, b, c, odd in re.findall(pattern, text):
        if len({a, b, c}) == 3:
            rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": to_float(odd)})

    if not rows:
        try:
            tables = pd.read_html(html)
            raw = " ".join(" ".join(map(str, t.values.flatten())) for t in tables)
            for a, b, c, odd in re.findall(pattern, clean_text(raw)):
                if len({a, b, c}) == 3:
                    rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": to_float(odd)})
        except Exception:
            pass

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return df.drop_duplicates("買い目")


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

        rows.append({"買い目": f"{a}-{b}-{c}", "オッズ": round(odd, 1)})

    return pd.DataFrame(rows)


# =====================================================
# AI LOGIC
# =====================================================

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
    s = 0.0

    s += score_map.get(a, 0) * 0.52
    s += score_map.get(b, 0) * 0.30
    s += score_map.get(c, 0) * 0.18

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

    rows = []

    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        key = f"{combo[0]}-{combo[1]}-{combo[2]}"
        odd = odd_map.get(key)

        if odd is None or odd <= 0:
            continue

        ai = combo_score(combo, power)
        ev = ai * math.log(odd + 1)

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

    hot = df[df["分類"] == "熱🔥"].head(hot_count)
    main = df[df["分類"] == "本線"].head(main_count)
    hole = df[df["分類"] == "穴"].head(hole_count)
    saver = df[df["分類"] == "抑え"].head(saver_count)

    out = pd.concat([hot, main, hole, saver])
    out = out.drop_duplicates("買い目")

    if len(out) < ticket_count:
        add = df[~df["買い目"].isin(out["買い目"])].head(ticket_count - len(out))
        out = pd.concat([out, add])

    return out.head(ticket_count).reset_index(drop=True)


def heavy_ai(df):
    if df.empty:
        return df

    out = df.copy()

    out["厚張り指数"] = (
        out["AI信頼度"] * 0.70
        + out["期待値"] * 0.22
        - out["オッズ"] * 0.08
    )

    out = out[
        (out["AI信頼度"] >= 82)
        & (out["オッズ"] >= 4.0)
        & (out["オッズ"] <= 35.0)
    ]

    return out.sort_values("厚張り指数", ascending=False).head(3).reset_index(drop=True)


# =====================================================
# UI
# =====================================================

st.title("🚤 Boat Race AI v6")
st.caption("出走表取得さらに強化版 / 熱🔥 / 本線 / 穴 / 抑え / 厳選 / 厚張りAI")

with st.sidebar:
    st.header("設定")

    place = st.selectbox("場", list(JCD_MAP.keys()))
    jcd = JCD_MAP[place]

    race_date = st.date_input("日付", value=date.today())
    hd = race_date.strftime("%Y%m%d")

    race_no = st.number_input("レース", min_value=1, max_value=12, value=1)

    ticket_count = st.slider("買い目点数", 1, 20, 10, 1)

    allow_fallback_odds = st.checkbox(
        "オッズ取得失敗時はAI仮オッズで表示",
        value=True
    )

    run = st.button("AI予想開始", width="stretch")


if run:
    urls, htmls = fetch_pages(jcd, int(race_no), hd)

    race = parse_racelist(htmls.get("出走表"))
    before = parse_beforeinfo(htmls.get("直前情報"))

    st.subheader(f"{place} {int(race_no)}R")

    with st.expander("取得URL"):
        for k, v in urls.items():
            st.write(f"{k}: {v}")

    if race.empty:
        st.error("出走表を取得できませんでした。開催日・場・レース番号を確認してください。")
        st.stop()

    power = calc_power(race, before)

    odds = parse_odds3t(htmls.get("3連単オッズ"))
    odds_status = "実オッズ取得OK"

    if odds.empty:
        if allow_fallback_odds:
            odds = make_fallback_odds(power)
            odds_status = "実オッズ取得失敗 → AI仮オッズで表示"
        else:
            st.error("3連単オッズを取得できませんでした。AI仮オッズ表示をONにしてください。")
            st.stop()

    tickets = build_tickets(power, odds)
    selected = selected_tickets(tickets, ticket_count)
    heavy = heavy_ai(tickets)

    st.info(f"データ状態：{odds_status}")

    st.markdown("### 指数表")

    show_cols = [
        "順位", "艇", "選手", "級別", "AI指数",
        "展示", "展示ST", "平均ST",
        "全国2連率", "当地2連率",
        "モーター", "ボート", "データ状態"
    ]

    st.dataframe(power[show_cols], width="stretch", hide_index=True)

    if tickets.empty:
        st.warning("買い目を生成できませんでした。データ不足または基準未満です。")
        st.stop()

    hot = tickets[tickets["分類"] == "熱🔥"].head(3)
    main = tickets[tickets["分類"] == "本線"].head(5)
    hole = tickets[tickets["分類"] == "穴"].head(5)
    saver = tickets[tickets["分類"] == "抑え"].head(5)

    if not hot.empty:
        st.markdown("## 熱🔥")
        st.dataframe(hot, width="stretch", hide_index=True)

    st.markdown("## 本線")
    st.dataframe(main, width="stretch", hide_index=True)

    st.markdown("## 穴")
    st.dataframe(hole, width="stretch", hide_index=True)

    st.markdown("## 抑え")
    st.dataframe(saver, width="stretch", hide_index=True)

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