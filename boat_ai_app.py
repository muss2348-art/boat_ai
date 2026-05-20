# boat_ai_app.py
# BOATRACE AI v7.5
# 出走表ズレ修正強化版：BOATRACE公式HTML本文から選手名・級別・成績を直接抽出
# GitHub + Streamlit Cloud 用

import re
import itertools
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


APP_VERSION = "v7.5 出走表HTML本文抽出強化版"


JCD_MAP = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川", "06": "浜名湖",
    "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島", "17": "宮島", "18": "徳山",
    "19": "下関", "20": "若松", "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def zen_to_han(s: str) -> str:
    if s is None:
        return ""
    table = str.maketrans(
        "０１２３４５６７８９．－＋　",
        "0123456789.-+ "
    )
    return str(s).translate(table)


def clean_text(s: str) -> str:
    s = zen_to_han(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s+\n", "\n", s)
    return s.strip()


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def parse_query_from_url(url: str) -> Tuple[str, str, str]:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    rno = q.get("rno", [""])[0]
    jcd = q.get("jcd", [""])[0].zfill(2)
    hd = q.get("hd", [""])[0]
    if not rno or not jcd or not hd:
        raise ValueError("URLから rno / jcd / hd を取得できませんでした。")
    return rno, jcd, hd


def make_url(page: str, rno: str, jcd: str, hd: str) -> str:
    return f"https://www.boatrace.jp/owpc/pc/race/{page}?rno={rno}&jcd={jcd}&hd={hd}"


@dataclass
class Racer:
    lane: int
    name: str
    klass: str = "B1"
    avg_st: float = 0.18
    national_win: float = 0.0
    national_2: float = 0.0
    national_3: float = 0.0
    local_win: float = 0.0
    local_2: float = 0.0
    local_3: float = 0.0
    motor_no: int = 0
    motor_2: float = 0.0
    motor_3: float = 0.0
    boat_no: int = 0
    boat_2: float = 0.0
    boat_3: float = 0.0
    display_time: float = 0.0
    tilt: float = 0.0
    tenji_st: float = 0.0
    tenji_f: bool = False
    score: float = 0.0
    data_status: str = ""


def safe_float(x, default=0.0) -> float:
    try:
        x = str(x).replace("%", "").replace("F", "").replace("L", "").strip()
        if x in ["", "-", "－", "None"]:
            return default
        return float(x)
    except Exception:
        return default


def safe_int(x, default=0) -> int:
    try:
        x = str(x).strip()
        if x in ["", "-", "－", "None"]:
            return default
        return int(float(x))
    except Exception:
        return default


def soup_text_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    text = clean_text(text)
    lines = [clean_text(x) for x in text.splitlines()]
    return [x for x in lines if x]


def extract_event_name(lines: List[str]) -> str:
    for line in lines:
        if "杯" in line or "選手権" in line or "シリーズ" in line or "競走" in line:
            if len(line) >= 4 and not line.startswith("*"):
                return line.replace("##", "").strip()
    return ""


def parse_racelist(html: str) -> Tuple[List[Racer], Dict]:
    """
    BOATRACE公式のPC出走表を、表構造ではなく本文行から抽出する。
    例:
      1
      4651 / B1
      佐藤 大騎
      大阪/大阪
      41歳/52.0kg
      F0
      L0
      0.16  3.81
      16.33
      27.55  3.13
      ...
    """
    lines = soup_text_lines(html)
    event_name = extract_event_name(lines)

    racers: List[Racer] = []

    # レーサー開始位置：艇番行 → 登録番号 / 級別
    starts = []
    for i in range(len(lines) - 1):
        lane_line = lines[i].strip()
        next_line = lines[i + 1].strip()
        if re.fullmatch(r"[1-6]", lane_line) and re.fullmatch(r"\d{4}\s*/\s*[AB][12]", next_line):
            starts.append((i, int(lane_line)))

    for idx, (start_i, lane) in enumerate(starts):
        end_i = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = lines[start_i:end_i]

        reg_class = block[1] if len(block) > 1 else ""
        m = re.search(r"(\d{4})\s*/\s*([AB][12])", reg_class)
        klass = m.group(2) if m else "B1"

        name = ""
        if len(block) > 2:
            candidate = block[2].strip()
            if not re.search(r"\d|kg|F\d|L\d|/", candidate):
                name = candidate

        if not name:
            name = f"{lane}号艇"

        # F/L 後の数値群から成績を取る
        floats = []
        ints = []

        for b in block:
            for n in re.findall(r"(?<![A-Za-z])[-+]?\d+\.\d+", b):
                floats.append(safe_float(n))
            # motor / boat No候補。登録番号や年齢なども入るので後で位置で使う
            for n in re.findall(r"\b\d{1,3}\b", b):
                ints.append(safe_int(n))

        # 平均STは0.10〜0.30程度の最初の小数値を優先
        avg_st = 0.18
        for f in floats:
            if 0.08 <= f <= 0.35:
                avg_st = f
                break

        # 公式の並び想定：
        # avg_st, national_win, national_2, national_3, local_win, local_2, local_3, motor_2, motor_3, boat_2, boat_3
        meaningful = floats[:12]
        national_win = meaningful[1] if len(meaningful) > 1 else 0.0
        national_2 = meaningful[2] if len(meaningful) > 2 else 0.0
        national_3 = meaningful[3] if len(meaningful) > 3 else 0.0
        local_win = meaningful[4] if len(meaningful) > 4 else 0.0
        local_2 = meaningful[5] if len(meaningful) > 5 else 0.0
        local_3 = meaningful[6] if len(meaningful) > 6 else 0.0

        # Noは本文上で全国/当地後に出るが、抽出が難しいので候補から最後寄りを使用
        # 外しても指数の主軸にはしない
        motor_no = 0
        boat_no = 0
        no_candidates = [x for x in ints if 1 <= x <= 99]
        if len(no_candidates) >= 2:
            motor_no = no_candidates[-2]
            boat_no = no_candidates[-1]

        motor_2 = meaningful[7] if len(meaningful) > 7 else 0.0
        motor_3 = meaningful[8] if len(meaningful) > 8 else 0.0
        boat_2 = meaningful[9] if len(meaningful) > 9 else 0.0
        boat_3 = meaningful[10] if len(meaningful) > 10 else 0.0

        status_parts = []
        if name == f"{lane}号艇":
            status_parts.append("名前取得弱い")
        else:
            status_parts.append("名前OK")
        if national_2 <= 0:
            status_parts.append("全国2連弱い")
        if motor_2 <= 0:
            status_parts.append("モーター弱い")

        racers.append(Racer(
            lane=lane,
            name=name,
            klass=klass,
            avg_st=avg_st,
            national_win=national_win,
            national_2=national_2,
            national_3=national_3,
            local_win=local_win,
            local_2=local_2,
            local_3=local_3,
            motor_no=motor_no,
            motor_2=motor_2,
            motor_3=motor_3,
            boat_no=boat_no,
            boat_2=boat_2,
            boat_3=boat_3,
            data_status=" / ".join(status_parts),
        ))

    # 6艇取れない場合の最終フォールバック
    found = {r.lane for r in racers}
    for lane in range(1, 7):
        if lane not in found:
            racers.append(Racer(
                lane=lane,
                name=f"{lane}号艇",
                klass="B1",
                data_status="出走表フォールバック"
            ))

    racers = sorted(racers, key=lambda x: x.lane)

    meta = {
        "event_name": event_name,
        "racelist_count": len([r for r in racers if not r.name.endswith("号艇")]),
        "raw_lines_sample": lines[:80],
    }
    return racers, meta


def parse_beforeinfo(html: str, racers: List[Racer]) -> Dict:
    lines = soup_text_lines(html)
    by_lane = {r.lane: r for r in racers}

    # 展示タイム・チルト
    # 例: 1 佐藤 大騎 52.0kg 7.25 0.0
    for line in lines:
        m = re.match(r"^([1-6])\s+(.+?)\s+\d+\.\d+kg\s+(\d+\.\d+)\s+(-?\d+\.\d+)", line)
        if m:
            lane = int(m.group(1))
            if lane in by_lane:
                by_lane[lane].display_time = safe_float(m.group(3))
                by_lane[lane].tilt = safe_float(m.group(4))

    # スタート展示
    # 本文上では「1 .07」「4 F.09」など
    for line in lines:
        m = re.match(r"^([1-6])\s+(F)?\.?(\d{2})$", line)
        if m:
            lane = int(m.group(1))
            is_f = bool(m.group(2))
            st = safe_float("0." + m.group(3))
            if lane in by_lane:
                by_lane[lane].tenji_st = st
                by_lane[lane].tenji_f = is_f

    return {"beforeinfo_ok": True}


def parse_odds3t(html: str) -> Dict[str, float]:
    """
    3連単オッズページは本文上でかなり詰めて表示される。
    完全な表復元が難しいケースもあるため、
    pandas.read_htmlが取れれば優先、無理なら本文から疑似復元。
    """
    odds = {}

    # まずHTMLテーブル抽出を試す
    try:
        tables = pd.read_html(html)
        for df in tables:
            text = " ".join(map(str, df.values.flatten()))
            odds.update(parse_odds_text(text))
    except Exception:
        pass

    if len(odds) < 20:
        lines = soup_text_lines(html)
        joined = " ".join(lines)
        odds.update(parse_odds_text(joined))

    return odds


def parse_odds_text(text: str) -> Dict[str, float]:
    """
    本文の並びをざっくり復元する。
    3連単は 1着ブロックごとに2着・3着・オッズが並ぶため、完全復元できないページもある。
    ただし表示順位づけ用に取れる範囲で使う。
    """
    text = clean_text(text)
    odds = {}

    # 素直な "1-2-3 31.8" 型があれば取得
    for m in re.finditer(r"([1-6])[-ー]([1-6])[-ー]([1-6])\s+(\d+\.\d+)", text):
        a, b, c, v = m.groups()
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)

    # 公式PC本文は券番が省略表示になるため、取れない場合は空で返す
    return odds


def class_bonus(klass: str) -> float:
    return {"A1": 8.0, "A2": 4.5, "B1": 0.0, "B2": -3.0}.get(klass, 0.0)


def calculate_scores(racers: List[Racer]) -> List[Racer]:
    for r in racers:
        score = 0.0

        # 基礎：級別・全国・当地・モーター・ボート
        score += 50.0
        score += class_bonus(r.klass)
        score += r.national_2 * 0.35
        score += r.national_3 * 0.15
        score += r.local_2 * 0.18
        score += r.motor_2 * 0.20
        score += r.boat_2 * 0.10

        # 平均ST
        if r.avg_st > 0:
            score += max(0, (0.20 - r.avg_st) * 80)

        # 展示
        if r.display_time > 0:
            score += max(0, (7.25 - r.display_time) * 18)

        # 展示ST
        if r.tenji_st > 0:
            score += max(0, (0.15 - r.tenji_st) * 60)
        if r.tenji_f:
            score -= 7.0

        # 枠補正
        lane_bonus = {1: 9.5, 2: 4.5, 3: 2.5, 4: 1.0, 5: -2.0, 6: -4.0}
        score += lane_bonus.get(r.lane, 0.0)

        r.score = round(score, 1)

    return sorted(racers, key=lambda x: x.score, reverse=True)


def make_ai_table(racers: List[Racer]) -> pd.DataFrame:
    ranked = calculate_scores(racers)
    rows = []
    for i, r in enumerate(ranked, start=1):
        rows.append({
            "順位": i,
            "艇": r.lane,
            "選手": r.name,
            "級別": r.klass,
            "AI指数": r.score,
            "展示": r.display_time,
            "展示ST": f"{'F' if r.tenji_f else ''}{r.tenji_st:.2f}" if r.tenji_st else 0,
            "平均ST": r.avg_st,
            "全国2連率": r.national_2,
            "当地2連率": r.local_2,
            "モーター": r.motor_2,
            "ボート": r.boat_2,
            "データ状態": r.data_status,
        })
    return pd.DataFrame(rows)


def combo_score(combo: Tuple[int, int, int], racer_map: Dict[int, Racer]) -> float:
    a, b, c = combo
    r1, r2, r3 = racer_map[a], racer_map[b], racer_map[c]

    s = r1.score * 1.00 + r2.score * 0.67 + r3.score * 0.45

    # 1号艇頭を少し評価
    if a == 1:
        s += 7.0

    # A1/A2頭評価
    if r1.klass == "A1":
        s += 5.0
    elif r1.klass == "A2":
        s += 2.0

    # 展示が良い艇を2-3着に拾う
    for x in [r2, r3]:
        if x.display_time and x.display_time <= 7.12:
            s += 2.0
        if x.tenji_st and x.tenji_st <= 0.08:
            s += 1.5

    # 6号艇頭は強くなければ減点
    if a == 6 and r1.score < 95:
        s -= 8.0

    return round(s, 2)


def generate_predictions(racers: List[Racer], odds: Dict[str, float]) -> pd.DataFrame:
    ranked = calculate_scores(racers)
    racer_map = {r.lane: r for r in racers}

    combos = []
    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        s = combo_score(combo, racer_map)
        key = f"{combo[0]}-{combo[1]}-{combo[2]}"
        odd = odds.get(key, 0.0)

        # オッズ補正：取れている時だけ
        value = s
        if odd > 0:
            if 7.0 <= odd <= 35.0:
                value += 8.0
            elif 35.0 < odd <= 90.0:
                value += 4.0
            elif odd < 5.0:
                value -= 5.0
            elif odd > 150:
                value -= 3.0

        combos.append({
            "買い目": key,
            "1着": combo[0],
            "2着": combo[1],
            "3着": combo[2],
            "評価": round(value, 2),
            "オッズ": odd,
        })

    df = pd.DataFrame(combos).sort_values("評価", ascending=False).reset_index(drop=True)

    labels = []
    for i, row in df.iterrows():
        odd = row["オッズ"]
        if i < 2:
            labels.append("熱🔥")
        elif i < 6:
            labels.append("本線")
        elif odd >= 35 if odd else i < 10:
            labels.append("穴")
        else:
            labels.append("抑え")

    df["区分"] = labels

    # 厳選・厚張りAI
    top_gap = ranked[0].score - ranked[1].score if len(ranked) >= 2 else 0
    confidence = min(100, max(0, 45 + top_gap * 2.2 + (ranked[0].score - 85) * 0.7))
    confidence = round(confidence, 1)

    df["勝負度"] = confidence
    df["厚張りAI"] = ""
    if confidence >= 72:
        df.loc[df.index[:2], "厚張りAI"] = "候補"
    if confidence >= 82:
        df.loc[df.index[:1], "厚張りAI"] = "強"

    return df.head(14)


def build_notes_text(event_name: str, place: str, rno: str, ai_df: pd.DataFrame, pred_df: pd.DataFrame) -> str:
    title = f"{place}{rno}R"
    if event_name:
        title += f"｜{event_name}"

    lines = []
    lines.append(title)
    lines.append("")
    lines.append("【指数表・印】")
    mark_map = ["◎", "○", "▲", "△", "☆", "消"]
    for i, row in ai_df.iterrows():
        mark = mark_map[i] if i < len(mark_map) else ""
        lines.append(f"{mark} {int(row['艇'])}号艇 {row['選手']}｜指数 {row['AI指数']}")

    lines.append("")
    lines.append("【買い目】")
    for _, row in pred_df.head(8).iterrows():
        odds_txt = f"（{row['オッズ']}倍）" if row["オッズ"] else ""
        lines.append(f"{row['区分']} {row['買い目']} {odds_txt}")

    lines.append("")
    lines.append("※指数表・印とは連動していない場合もございます。")
    return "\n".join(lines)


def main():
    st.set_page_config(
        page_title="BOATRACE AI",
        page_icon="🚤",
        layout="wide",
    )

    st.title("🚤 BOATRACE AI")
    st.caption(APP_VERSION)

    default_url = "https://www.boatrace.jp/owpc/pc/race/racelist?rno=2&jcd=20&hd=20260520"
    url = st.text_input("BOATRACE公式 出走表URL", value=default_url)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        use_before = st.checkbox("直前情報を取得", value=True)
    with col_b:
        use_odds = st.checkbox("3連単オッズを取得", value=True)
    with col_c:
        debug = st.checkbox("デバッグ表示", value=False)

    if st.button("AI予想を実行", type="primary"):
        try:
            rno, jcd, hd = parse_query_from_url(url)
            place = JCD_MAP.get(jcd, f"jcd={jcd}")

            racelist_url = make_url("racelist", rno, jcd, hd)
            before_url = make_url("beforeinfo", rno, jcd, hd)
            odds_url = make_url("odds3t", rno, jcd, hd)

            with st.spinner("出走表を取得中..."):
                racelist_html = fetch_html(racelist_url)
                racers, meta = parse_racelist(racelist_html)

            if use_before:
                with st.spinner("直前情報を取得中..."):
                    try:
                        before_html = fetch_html(before_url)
                        parse_beforeinfo(before_html, racers)
                    except Exception as e:
                        st.warning(f"直前情報の取得に失敗しました: {e}")

            odds = {}
            if use_odds:
                with st.spinner("3連単オッズを取得中..."):
                    try:
                        odds_html = fetch_html(odds_url)
                        odds = parse_odds3t(odds_html)
                    except Exception as e:
                        st.warning(f"オッズ取得に失敗しました: {e}")

            ai_df = make_ai_table(racers)
            pred_df = generate_predictions(racers, odds)

            st.subheader(f"{place} {rno}R")
            if meta.get("event_name"):
                st.write(meta["event_name"])

            name_ok = int((ai_df["選手"].astype(str).str.contains("号艇") == False).sum())
            if name_ok == 6:
                st.success("選手名：6艇すべて取得OK")
            else:
                st.warning(f"選手名取得：{name_ok}/6艇。フォールバックが残っています。")

            if use_before:
                before_ok = int((ai_df["展示"].astype(float) > 0).sum())
                if before_ok == 6:
                    st.success("直前情報：展示タイム6艇取得OK")
                else:
                    st.warning(f"直前情報：展示タイム {before_ok}/6艇")

            if use_odds:
                if len(odds) > 0:
                    st.success(f"3連単オッズ：{len(odds)}件取得")
                else:
                    st.info("3連単オッズ：公式PC表示形式の都合で今回は買い目別オッズを復元できませんでした。指数予想は実行しています。")

            st.markdown("### 指数表")
            st.dataframe(ai_df, width="stretch", hide_index=True)

            st.markdown("### 買い目AI")
            st.dataframe(pred_df, width="stretch", hide_index=True)

            confidence = pred_df["勝負度"].iloc[0] if len(pred_df) else 0
            if confidence >= 82:
                st.error(f"勝負度：{confidence}%　厚張り候補あり")
            elif confidence >= 72:
                st.warning(f"勝負度：{confidence}%　厳選候補")
            else:
                st.info(f"勝負度：{confidence}%　通常評価")

            st.markdown("### Note貼り付け用")
            note_text = build_notes_text(meta.get("event_name", ""), place, rno, ai_df, pred_df)
            st.text_area("コピー用", value=note_text, height=260)

            if debug:
                st.markdown("### デバッグURL")
                st.code(f"出走表: {racelist_url}\n直前情報: {before_url}\n3連単オッズ: {odds_url}")

                st.markdown("### 出走表本文サンプル")
                st.write(meta.get("raw_lines_sample", []))

                st.markdown("### オッズ取得件数")
                st.write(len(odds))
                if odds:
                    st.write(dict(list(odds.items())[:20]))

        except Exception as e:
            st.error("処理中にエラーが発生しました。")
            st.exception(e)


if __name__ == "__main__":
    main()