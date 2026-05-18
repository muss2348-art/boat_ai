# boat_ai_app.py
# Boat Race AI v4
# 本番寄せ：BOATRACE公式から出走表・直前情報・3連単オッズを取得
# 熱🔥 / 本線 / 穴 / 抑え / 厳選 / 厚張りAI / 買い目点数 1〜20点

import re
import math
import itertools
from datetime import date

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


# =====================================================
# CONFIG
# =====================================================

st.set_page_config(
    page_title="Boat AI v4",
    page_icon="🚤",
    layout="wide"
)

BASE_URL = "https://www.boatrace.jp/owpc/pc/race"

JCD_MAP = {
    "桐生": "01",
    "戸田": "02",
    "江戸川": "03",
    "平和島": "04",
    "多摩川": "05",
    "浜名湖": "06",
    "蒲郡": "07",
    "常滑": "08",
    "津": "09",
    "三国": "10",
    "びわこ": "11",
    "住之江": "12",
    "尼崎": "13",
    "鳴門": "14",
    "丸亀": "15",
    "児島": "16",
    "宮島": "17",
    "徳山": "18",
    "下関": "19",
    "若松": "20",
    "芦屋": "21",
    "福岡": "22",
    "唐津": "23",
    "大村": "24",
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


# =====================================================
# FETCH
# =====================================================

def fetch_pages(jcd, rno, hd):
    urls = {
        "出走表": build_url("racelist", rno, jcd, hd),
        "直前情報": build_url("beforeinfo", rno, jcd, hd),
        "3連単オッズ": build_url("odds3t", rno, jcd, hd),
    }

    htmls = {}

    for name, url in urls.items():
        htmls[name] = safe_get(url)

    return urls, htmls


# =====================================================
# PARSE RACELIST
# =====================================================

def parse_racelist(html):
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")

    rows = []

    # BOATRACE公式の出走表テキストは枠ごとに
    # 登録番号 / 級別 → 選手名 → F/L → 平均ST → 勝率/2連率/3連率...
    # の順で並びやすい
    blocks = re.split(r"\n\s*(?=[1-6]\s*\n)", text)

    for waku in range(1, 7):
        target = None

        for b in blocks:
            b_clean = clean_text(b)
            if re.match(rf"^{waku}\s", b_clean) or b_clean.startswith(str(waku)):
                if re.search(r"\b(A1|A2|B1|B2)\b", b_clean):
                    target = b_clean
                    break

        if not target:
            rows.append({
                "艇": waku,
                "選手": f"{waku}号艇",
                "級別": "B1",
                "全国2連率": 0.0,
                "当地2連率": 0.0,
                "モーター": 0.0,
                "ボート": 0.0,
                "平均ST": 0.18,
                "データ状態": "出走表取得弱い",
            })
            continue

        grade_match = re.search(r"\b(A1|A2|B1|B2)\b", target)
        grade = grade_match.group(1) if grade_match else "B1"

        name = f"{waku}号艇"

        # 級別の直後付近に名前が来ることが多い
        name_match = re.search(
            r"\b(?:A1|A2|B1|B2)\b\s*([一-龥ぁ-んァ-ンー・\s]{2,12})\s+[北海道青森岩手宮城秋田山形福島茨城栃木群馬埼玉千葉東京神奈川新潟富山石川福井山梨長野岐阜静岡愛知三重滋賀京都大阪兵庫奈良和歌山鳥取島根岡山広島山口徳島香川愛媛高知福岡佐賀長崎熊本大分宮崎鹿児島沖縄]",
            target
        )

        if name_match:
            name = clean_text(name_match.group(1))

        nums = [to_float(x) for x in re.findall(r"\d+\.\d+", target)]

        avg_st = 0.18
        rate_nums = []

        for n in nums:
            if 0.05 <= n <= 0.35 and avg_st == 0.18:
                avg_st = n
            elif 0 <= n <= 100:
                rate_nums.append(n)

        # 公式の並びに寄せた暫定抽出
        # 平均STの後に 全国勝率/2連率/3連率、当地勝率/2連率/3連率、モーターNo/2連率/3連率、ボートNo/2連率/3連率
        national2 = 0.0
        local2 = 0.0
        motor2 = 0.0
        boat2 = 0.0

        # 2連率らしい数値だけ拾う
        likely_rates = [n for n in rate_nums if 0 <= n <= 100]

        if len(likely_rates) >= 3:
            national2 = likely_rates[1]
        if len(likely_rates) >= 6:
            local2 = likely_rates[4]
        if len(likely_rates) >= 9:
            motor2 = likely_rates[7]
        if len(likely_rates) >= 12:
            boat2 = likely_rates[10]

        rows.append({
            "艇": waku,
            "選手": name,
            "級別": grade,
            "全国2連率": national2,
            "当地2連率": local2,
            "モーター": motor2,
            "ボート": boat2,
            "平均ST": avg_st,
            "データ状態": "OK",
        })

    return pd.DataFrame(rows)


# =====================================================
# PARSE BEFOREINFO
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

    # 展示タイムは 6.xx を拾う
    times = [to_float(x) for x in re.findall(r"\b6\.\d{2}\b", text)]
    times = [x for x in times if 6.40 <= x <= 7.20]

    # STは .12 形式もあるため拾う
    st_raw = re.findall(r"(?<!\d)\.?\d{2}(?!\d)", text)
    st_vals = []

    for s in st_raw:
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
# PARSE ODDS
# =====================================================

def parse_odds3t(html):
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.get_text(" "))

    rows = []

    # 1-2-3 12.3 のような並びを拾う
    pattern1 = r"([1-6])\s*[-–]\s*([1-6])\s*[-–]\s*([1-6])\s+(\d+\.\d+)"
    for a, b, c, odd in re.findall(pattern1, text):
        if len({a, b, c}) == 3:
            rows.append({
                "買い目": f"{a}-{b}-{c}",
                "オッズ": to_float(odd)
            })

    # HTML内の data やテーブルが読めない場合に備えた保険
    if not rows:
        try:
            tables = pd.read_html(html)
            raw = " ".join(
                " ".join(map(str, t.values.flatten()))
                for t in tables
            )
            for a, b, c, odd in re.findall(pattern1, clean_text(raw)):
                if len({a, b, c}) == 3:
                    rows.append({
                        "買い目": f"{a}-{b}-{c}",
                        "オッズ": to_float(odd)
                    })
        except Exception:
            pass

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df = df.drop_duplicates("買い目")
    df = df[(df["オッズ"] > 0) & (df["オッズ"] < 9999)]

    return df


# =====================================================
# FALLBACK ODDS
# =====================================================

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

        rows.append({
            "買い目": f"{a}-{b}-{c}",
            "オッズ": round(odd, 1)
        })

    return pd.DataFrame(rows)


# =====================================================
# SCORE
# =====================================================

def grade_score(g):
    return {
        "A1": 18,
        "A2": 12,
        "B1": 5,
        "B2": 1,
    }.get(str(g), 5)


def calc_power(race, before):
    df = race.merge(before, on="艇", how="left")

    for col in ["展示", "展示ST", "進入"]:
        if col not in df.columns:
            df[col] = 0

    scores = []

    for _, r in df.iterrows():
        waku = int(r["艇"])

        score = 0.0

        # 枠
        score += {
            1: 30,
            2: 18,
            3: 12,
            4: 11,
            5: 5,
            6: 2
        }.get(waku, 0)

        # 級別
        score += grade_score(r["級別"])

        # 全国・当地・機力
        score += to_float(r["全国2連率"]) * 0.65
        score += to_float(r["当地2連率"]) * 0.40
        score += to_float(r["モーター"]) * 0.70
        score += to_float(r["ボート"]) * 0.25

        # 平均ST
        avg_st = to_float(r["平均ST"], 0.18)
        score += max(0, (0.22 - avg_st) * 120)

        # 展示
        tenji = to_float(r["展示"], 0.0)
        if tenji > 0:
            score += max(0, (6.95 - tenji) * 80)

        # 展示ST
        tenji_st = to_float(r["展示ST"], 0.18)
        score += max(0, (0.22 - tenji_st) * 80)

        # 4カド穴補正
        if waku == 4 and tenji > 0 and tenji <= 6.78:
            score += 8

        # 5号艇モーター穴
        if waku == 5 and to_float(r["モーター"]) >= 40:
            score += 5

        scores.append(round(score, 1))

    df["AI指数"] = scores
    df = df.sort_values("AI指数", ascending=False).reset_index(drop=True)
    df["順位"] = range(1, len(df) + 1)

    return df


# =====================================================
# COMBO AI
# =====================================================

def combo_score(combo, power):
    score_map = dict(zip(power["艇"], power["AI指数"]))
    rank_map = dict(zip(power["艇"], power["順位"]))

    a, b, c = combo

    s = 0.0

    s += score_map.get(a, 0) * 0.52
    s += score_map.get(b, 0) * 0.30
    s += score_map.get(c, 0) * 0.18

    # 1号艇逃げ
    if a == 1:
        s += 10

    # 2・3の差し
    if a in [2, 3]:
        s += 3

    # 4カド穴
    if a == 4:
        s += 5

    # 5・6頭は少し減点
    if a in [5, 6]:
        s -= 6

    # 3着に外枠が入る穴補正
    if c in [4, 5, 6]:
        s += 3

    # 上位艇が頭なら加点
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

        label = "抑え"

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

    df = df.sort_values(["期待値", "AI信頼度"], ascending=False).reset_index(drop=True)

    return df


# =====================================================
# SELECTED / HEAVY
# =====================================================

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
        (out["AI信頼度"] >= 82) &
        (out["オッズ"] >= 4.0) &
        (out["オッズ"] <= 35.0)
    ]

    out = out.sort_values("厚張り指数", ascending=False)

    return out.head(3).reset_index(drop=True)


# =====================================================
# UI
# =====================================================

st.title("🚤 Boat Race AI v4")
st.caption("本番寄せ：公式データ取得 / 熱🔥 / 本線 / 穴 / 抑え / 厳選 / 厚張りAI")

with st.sidebar:
    st.header("設定")

    place = st.selectbox("場", list(JCD_MAP.keys()))
    jcd = JCD_MAP[place]

    race_date = st.date_input("日付", value=date.today())
    hd = race_date.strftime("%Y%m%d")

    race_no = st.number_input("レース", min_value=1, max_value=12, value=1)

    ticket_count = st.slider(
        "買い目点数",
        min_value=1,
        max_value=20,
        value=10,
        step=1
    )

    allow_fallback_odds = st.checkbox(
        "オッズ取得失敗時はAI仮オッズで表示",
        value=True
    )

    run = st.button("AI予想開始", width="stretch")


# =====================================================
# MAIN
# =====================================================

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
            st.error("3連単オッズを取得できませんでした。オッズ取得失敗時のAI仮オッズ表示をONにしてください。")
            st.stop()

    tickets = build_tickets(power, odds)
    selected = selected_tickets(tickets, ticket_count)
    heavy = heavy_ai(tickets)

    st.info(f"データ状態：{odds_status}")

    # ===============================
    # 指数表
    # ===============================

    st.markdown("### 指数表")

    show_cols = [
        "順位",
        "艇",
        "選手",
        "級別",
        "AI指数",
        "展示",
        "展示ST",
        "平均ST",
        "全国2連率",
        "当地2連率",
        "モーター",
        "ボート",
        "データ状態",
    ]

    st.dataframe(
        power[show_cols],
        width="stretch",
        hide_index=True
    )

    # ===============================
    # 買い目
    # ===============================

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