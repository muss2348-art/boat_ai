# boat_ai_app.py
# BOATRACE AI v7.6
# 艇番 "1 Image" / "１ Image" 対応・イベント名誤取得修正・出走表ブロック抽出強化版

import re
import itertools
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Tuple

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


APP_VERSION = "v7.6 艇番Image対応・出走表抽出強化版"

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


@dataclass
class Racer:
    lane: int
    name: str
    klass: str = "B1"
    avg_st: float = 0.18
    national_2: float = 0.0
    local_2: float = 0.0
    motor_no: int = 0
    motor_2: float = 0.0
    boat_no: int = 0
    boat_2: float = 0.0
    display_time: float = 0.0
    tilt: float = 0.0
    tenji_st: float = 0.0
    tenji_f: bool = False
    score: float = 0.0
    data_status: str = ""


def zen_to_han(s: str) -> str:
    if s is None:
        return ""
    return str(s).translate(str.maketrans(
        "０１２３４５６７８９．－＋　",
        "0123456789.-+ "
    ))


def clean_text(s: str) -> str:
    s = zen_to_han(str(s))
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def safe_float(x, default=0.0) -> float:
    try:
        x = clean_text(x).replace("%", "").replace("F", "")
        if x in ["", "-", "－", "None", "nan"]:
            return default
        return float(x)
    except Exception:
        return default


def safe_int(x, default=0) -> int:
    try:
        x = clean_text(x)
        if x in ["", "-", "－", "None", "nan"]:
            return default
        return int(float(x))
    except Exception:
        return default


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
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


def soup_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [clean_text(x) for x in text.splitlines()]
    return [x for x in lines if x]


def extract_event_name(html: str, place: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for tag in soup.find_all(["h1", "h2", "h3", "div", "p", "span"]):
        txt = clean_text(tag.get_text(" "))
        if not txt:
            continue
        if any(k in txt for k in ["BOATRACE杯", "ボートレース杯", "選手権", "グランプリ", "周年", "ダービー", "シリーズ"]):
            if "ヴィーナスシリーズ" == txt:
                continue
            if "出走表" in txt and len(txt) > 25:
                continue
            if len(txt) >= 5:
                candidates.append(txt)

    title = clean_text(soup.title.get_text(" ")) if soup.title else ""
    if title:
        title = re.sub(r"出走表.*", "", title)
        title = re.sub(r"【.*", "", title)
        title = title.replace(place, "").strip()
        if title and "ヴィーナスシリーズ" != title:
            candidates.insert(0, title)

    for c in candidates:
        c = c.replace("##", "").strip()
        if 5 <= len(c) <= 60:
            return c

    return ""


def is_lane_line(line: str) -> int:
    """
    BOATRACE公式は艇番行が
    1
    1 Image
    １ Image
    のようになることがある。
    """
    line = clean_text(line)
    m = re.match(r"^([1-6])(?:\s+Image)?$", line)
    if m:
        return int(m.group(1))
    return 0


def is_reg_class_line(line: str) -> bool:
    return bool(re.search(r"\d{4}\s*/\s*[AB][12]", clean_text(line)))


def parse_racelist(html: str, place: str) -> Tuple[List[Racer], Dict]:
    lines = soup_lines(html)
    event_name = extract_event_name(html, place)

    starts = []
    for i, line in enumerate(lines):
        lane = is_lane_line(line)
        if not lane:
            continue

        # 艇番行の直後数行に「登録番号 / 級別」があれば出走表ブロック開始
        look = lines[i + 1:i + 8]
        if any(is_reg_class_line(x) for x in look):
            starts.append((i, lane))

    # 重複除去
    uniq = []
    seen_lane = set()
    for i, lane in starts:
        if lane not in seen_lane:
            uniq.append((i, lane))
            seen_lane.add(lane)
    starts = uniq

    racers: List[Racer] = []

    for idx, (start_i, lane) in enumerate(starts):
        end_i = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = lines[start_i:end_i]

        block_text = "\n".join(block)

        m_class = re.search(r"\d{4}\s*/\s*([AB][12])", block_text)
        klass = m_class.group(1) if m_class else "B1"

        name = ""
        for j, b in enumerate(block):
            if is_reg_class_line(b):
                for cand in block[j + 1:j + 5]:
                    cand = clean_text(cand)
                    if (
                        cand
                        and not re.search(r"\d|kg|F\d|L\d|/", cand)
                        and "支部" not in cand
                        and "出身地" not in cand
                        and "年齢" not in cand
                    ):
                        name = cand
                        break
                break

        if not name:
            name = f"{lane}号艇"

        nums = [safe_float(x) for x in re.findall(r"[-+]?\d+\.\d+", block_text)]

        avg_st = 0.18
        for n in nums:
            if 0.08 <= n <= 0.35:
                avg_st = n
                break

        # 公式出走表の小数値から、率系を推定
        rate_nums = [n for n in nums if n > 0.35]
        national_2 = rate_nums[1] if len(rate_nums) > 1 else 0.0
        local_2 = rate_nums[4] if len(rate_nums) > 4 else 0.0
        motor_2 = rate_nums[6] if len(rate_nums) > 6 else 0.0
        boat_2 = rate_nums[8] if len(rate_nums) > 8 else 0.0

        int_nums = [safe_int(x) for x in re.findall(r"\b\d{1,3}\b", block_text)]
        no_candidates = [x for x in int_nums if 1 <= x <= 99]
        motor_no = no_candidates[-2] if len(no_candidates) >= 2 else 0
        boat_no = no_candidates[-1] if len(no_candidates) >= 1 else 0

        status = []
        status.append("名前OK" if name != f"{lane}号艇" else "名前取得弱い")
        status.append("全国OK" if national_2 > 0 else "全国2連弱い")
        status.append("機力OK" if motor_2 > 0 else "モーター弱い")

        racers.append(Racer(
            lane=lane,
            name=name,
            klass=klass,
            avg_st=avg_st,
            national_2=national_2,
            local_2=local_2,
            motor_no=motor_no,
            motor_2=motor_2,
            boat_no=boat_no,
            boat_2=boat_2,
            data_status=" / ".join(status),
        ))

    found = {r.lane for r in racers}
    for lane in range(1, 7):
        if lane not in found:
            racers.append(Racer(lane=lane, name=f"{lane}号艇", data_status="出走表フォールバック"))

    racers = sorted(racers, key=lambda r: r.lane)

    meta = {
        "event_name": event_name,
        "raw_lines_sample": lines[:160],
        "starts": starts,
    }
    return racers, meta


def parse_beforeinfo(html: str, racers: List[Racer]) -> Dict:
    lines = soup_lines(html)
    by_lane = {r.lane: r for r in racers}

    # 展示タイム候補：艇番近くに 6.xx〜7.xx が出る
    for i, line in enumerate(lines):
        lane = is_lane_line(line)
        if not lane or lane not in by_lane:
            continue

        block = " ".join(lines[i:i + 20])
        floats = [safe_float(x) for x in re.findall(r"[-+]?\d+\.\d+", block)]

        display_candidates = [x for x in floats if 6.20 <= x <= 7.80]
        tilt_candidates = [x for x in floats if -0.5 <= x <= 3.0]

        if display_candidates:
            by_lane[lane].display_time = display_candidates[0]

        # チルトは展示タイムと違う小さい値
        for t in tilt_candidates:
            if t != by_lane[lane].display_time:
                by_lane[lane].tilt = t
                break

    # スタート展示
    joined = "\n".join(lines)
    for m in re.finditer(r"([1-6])\s+(F)?\.?(\d{2})", joined):
        lane = int(m.group(1))
        if lane in by_lane:
            st = safe_float("0." + m.group(3))
            if 0.00 <= st <= 0.40:
                by_lane[lane].tenji_st = st
                by_lane[lane].tenji_f = bool(m.group(2))

    return {"beforeinfo_ok": True}


def parse_odds_text(text: str) -> Dict[str, float]:
    text = clean_text(text)
    odds = {}

    for m in re.finditer(r"([1-6])[-ー]([1-6])[-ー]([1-6])\s+(\d+\.\d+)", text):
        a, b, c, v = m.groups()
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)

    return odds


def parse_odds3t(html: str) -> Dict[str, float]:
    odds = {}

    try:
        tables = pd.read_html(html)
        for df in tables:
            text = " ".join(map(str, df.values.flatten()))
            odds.update(parse_odds_text(text))
    except Exception:
        pass

    if len(odds) < 10:
        odds.update(parse_odds_text(" ".join(soup_lines(html))))

    return odds


def class_bonus(klass: str) -> float:
    return {"A1": 8.0, "A2": 4.5, "B1": 0.0, "B2": -3.0}.get(klass, 0.0)


def calculate_scores(racers: List[Racer]) -> List[Racer]:
    for r in racers:
        score = 50.0
        score += class_bonus(r.klass)
        score += r.national_2 * 0.42
        score += r.local_2 * 0.20
        score += r.motor_2 * 0.22
        score += r.boat_2 * 0.10

        if r.avg_st:
            score += max(0, (0.20 - r.avg_st) * 80)

        if r.display_time:
            score += max(0, (7.25 - r.display_time) * 20)

        if r.tenji_st:
            score += max(0, (0.15 - r.tenji_st) * 55)

        if r.tenji_f:
            score -= 7.0

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

    s = r1.score * 1.00 + r2.score * 0.68 + r3.score * 0.46

    if a == 1:
        s += 7.0
    if r1.klass == "A1":
        s += 5.0
    elif r1.klass == "A2":
        s += 2.0

    for x in [r2, r3]:
        if x.display_time and x.display_time <= 7.12:
            s += 2.0
        if x.tenji_st and x.tenji_st <= 0.08:
            s += 1.5

    if a == 6 and r1.score < 95:
        s -= 8.0

    return round(s, 2)


def generate_predictions(racers: List[Racer], odds: Dict[str, float]) -> pd.DataFrame:
    ranked = calculate_scores(racers)
    racer_map = {r.lane: r for r in racers}

    rows = []
    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        key = f"{combo[0]}-{combo[1]}-{combo[2]}"
        odd = odds.get(key, 0.0)
        value = combo_score(combo, racer_map)

        if odd > 0:
            if 7.0 <= odd <= 35.0:
                value += 8.0
            elif 35.0 < odd <= 90.0:
                value += 4.0
            elif odd < 5.0:
                value -= 5.0
            elif odd > 150:
                value -= 3.0

        rows.append({
            "買い目": key,
            "評価": round(value, 2),
            "オッズ": odd,
        })

    df = pd.DataFrame(rows).sort_values("評価", ascending=False).reset_index(drop=True)

    labels = []
    for i, row in df.iterrows():
        odd = row["オッズ"]
        if i < 2:
            labels.append("熱🔥")
        elif i < 6:
            labels.append("本線")
        elif (odd and odd >= 35) or (not odd and i < 10):
            labels.append("穴")
        else:
            labels.append("抑え")

    df["区分"] = labels

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


def build_note_text(event_name: str, place: str, rno: str, ai_df: pd.DataFrame, pred_df: pd.DataFrame) -> str:
    lines = []
    title = f"{place}{rno}R"
    if event_name:
        title += f"｜{event_name}"

    lines.append(title)
    lines.append("")
    lines.append("【指数表・印】")

    marks = ["◎", "○", "▲", "△", "☆", "消"]
    for i, row in ai_df.iterrows():
        mark = marks[i] if i < len(marks) else ""
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
    st.set_page_config(page_title="BOATRACE AI", page_icon="🚤", layout="wide")

    st.title("🚤 BOATRACE AI")
    st.caption(APP_VERSION)

    default_url = "https://www.boatrace.jp/owpc/pc/race/racelist?rno=2&jcd=20&hd=20260520"
    url = st.text_input("BOATRACE公式 出走表URL", value=default_url)

    col1, col2, col3 = st.columns(3)
    with col1:
        use_before = st.checkbox("直前情報を取得", value=True)
    with col2:
        use_odds = st.checkbox("3連単オッズを取得", value=True)
    with col3:
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
                racers, meta = parse_racelist(racelist_html, place)

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

            name_ok = int((~ai_df["選手"].astype(str).str.contains("号艇")).sum())
            if name_ok == 6:
                st.success("選手名取得：6/6艇 OK")
            else:
                st.warning(f"選手名取得：{name_ok}/6艇。フォールバックが残っています。")

            before_ok = int((ai_df["展示"].astype(float) > 0).sum())
            if use_before:
                if before_ok == 6:
                    st.success("直前情報：展示タイム 6/6艇 OK")
                else:
                    st.warning(f"直前情報：展示タイム {before_ok}/6艇")

            if use_odds:
                if len(odds) > 0:
                    st.success(f"3連単オッズ：{len(odds)}件取得")
                else:
                    st.info("3連単オッズ：今回は買い目別オッズを復元できませんでした。指数予想は実行しています。")

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
            st.text_area(
                "コピー用",
                value=build_note_text(meta.get("event_name", ""), place, rno, ai_df, pred_df),
                height=260,
            )

            if debug:
                st.markdown("### デバッグURL")
                st.code(f"出走表: {racelist_url}\n直前情報: {before_url}\n3連単オッズ: {odds_url}")

                st.markdown("### 出走表検出位置")
                st.write(meta.get("starts"))

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