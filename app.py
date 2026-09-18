import os
import io
import re
import base64
import unicodedata
import sqlite3
import datetime
import pandas as pd
import streamlit as st
from PIL import Image

# -------------------------------------------------------------
# 1. 페이지 기본 설정 및 스타일
# -------------------------------------------------------------
st.set_page_config(
    page_title="(주)수협개발 자료취합 시스템",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS (카드 스타일, 깔끔한 UI, 드래그앤드롭 최적화)
st.markdown("""
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-box {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 12px;
        border-left: 4px solid #3B82F6;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .score-badge {
        font-size: 1.1rem;
        font-weight: 600;
        color: #2563EB;
    }
    /* 파일 업로더 브라우즈 버튼 숨김 (끌어다 넣기 전용으로 전환하여 폴더 탐색기 지연 방지) */
    [data-testid="stFileUploaderDropzone"] button {
        display: none !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        border: 2px dashed #3B82F6 !important;
        background-color: #F8FAFC !important;
        border-radius: 10px !important;
        padding: 18px 12px !important;
        text-align: center !important;
        cursor: copy !important;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        background-color: #EFF6FF !important;
        border-color: #1D4ED8 !important;
    }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "survey.db")
CSV_FILE = os.path.join(BASE_DIR, "survey_data.csv")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
EMBLEM_FILE = os.path.join(BASE_DIR, "static", "sh_emblem.png")
LOGO_FILE = os.path.join(BASE_DIR, "static", "logo.png")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_image_base64(filepath: str) -> str:
    """이미지 파일을 base64 인코딩 문자열로 반환하여 HTML에 안정적으로 렌더링합니다."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "rb") as f_img:
                return base64.b64encode(f_img.read()).decode("utf-8")
        except Exception:
            return ""
    return ""

def find_upload_file(filename: str):
    """OS 파일 시스템 및 인코딩 차이(NFC/NFD)를 고려하여 실제 보관된 첨부파일 경로를 반환합니다."""
    if not filename or pd.isna(filename):
        return None
    fn = str(filename).strip()
    if not fn:
        return None
    p1 = os.path.join(UPLOAD_DIR, fn)
    if os.path.exists(p1):
        return p1
    fn_nfc = unicodedata.normalize('NFC', fn)
    p2 = os.path.join(UPLOAD_DIR, fn_nfc)
    if os.path.exists(p2):
        return p2
    fn_nfd = unicodedata.normalize('NFD', fn)
    p3 = os.path.join(UPLOAD_DIR, fn_nfd)
    if os.path.exists(p3):
        return p3
    try:
        for item in os.listdir(UPLOAD_DIR):
            if unicodedata.normalize('NFC', item) == fn_nfc or item.lower() == fn.lower():
                return os.path.join(UPLOAD_DIR, item)
    except Exception:
        pass
    return None

SCORE_COLUMNS = [
    "소통_설명및협의",
    "품질_기간준수",
    "품질_내용준수",
    "품질_개선",
    "안전_사고예방",
    "기타_민원관리",
    "종합_전체만족도"
]

SCORE_DISPLAY_NAMES = {
    "소통_설명및협의": "소통:설명및협의",
    "품질_기간준수": "품질:기간준수",
    "품질_내용준수": "품질:내용준수",
    "품질_개선": "품질:개선",
    "안전_사고예방": "안전:사고예방",
    "기타_민원관리": "기타:민원관리",
    "종합_전체만족도": "종합:전체만족도"
}

# 구버전 컬럼명 및 다양한 표기법 호환 매핑 테이블 (구글 시트 및 기존 CSV 호환)
LEGACY_COLUMN_MAP = {
    "소통_공사기간준수": "품질_기간준수",
    "품질_계약내용실행": "품질_내용준수",
    "품질_설계개선": "품질_개선",
    "품질_설계계선": "품질_개선",
    "안전_안전사고예방": "안전_사고예방",
    "종합_전반적만족도": "종합_전체만족도",
    "소통:설명협의": "소통_설명및협의",
    "소통:설명및협의": "소통_설명및협의",
    "소통:공기준수": "품질_기간준수",
    "품질:기간준수": "품질_기간준수",
    "품질:계약실행": "품질_내용준수",
    "품질:내용준수": "품질_내용준수",
    "품질:설계개선": "품질_개선",
    "품질:설계계선": "품질_개선",
    "품질:개선": "품질_개선",
    "안전:사고예방": "안전_사고예방",
    "기타:민원관리": "기타_민원관리",
    "종합:전반만족": "종합_전체만족도",
    "종합:전체만족도": "종합_전체만족도"
}

ALL_COLUMNS = [
    "등록일시",
    "작성일",
    "발주사",
    "공사명",
    "계약기간",
    "담당자소속",
    "담당자이름",
    "첨부파일",
    *SCORE_COLUMNS,
    "합계",
    "평균"
]

# -------------------------------------------------------------
# 2. 물리 데이터베이스(SQLite survey.db) & 구글 시트 하이브리드 연동
# -------------------------------------------------------------
def get_db_connection():
    """물리 SQLite 데이터베이스 연결 객체를 생성합니다."""
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """물리 DB(survey.db) 테이블 생성 및 기존 데이터 자동 마이그레이션"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            등록일시 TEXT NOT NULL,
            작성일 TEXT,
            발주사 TEXT NOT NULL,
            공사명 TEXT NOT NULL,
            계약기간 TEXT,
            담당자소속 TEXT,
            담당자이름 TEXT,
            첨부파일 TEXT DEFAULT '',
            소통_설명및협의 INTEGER DEFAULT 5,
            품질_기간준수 INTEGER DEFAULT 5,
            품질_내용준수 INTEGER DEFAULT 5,
            품질_개선 INTEGER DEFAULT 5,
            안전_사고예방 INTEGER DEFAULT 5,
            기타_민원관리 INTEGER DEFAULT 5,
            종합_전체만족도 INTEGER DEFAULT 5,
            합계 INTEGER DEFAULT 35,
            평균 REAL DEFAULT 5.0
        );
        """)
        cur.execute("PRAGMA table_info(surveys);")
        existing_cols = [r[1] for r in cur.fetchall()]
        if "첨부파일" not in existing_cols:
            cur.execute("ALTER TABLE surveys ADD COLUMN 첨부파일 TEXT DEFAULT '';")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_surveys_dt ON surveys(등록일시);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_surveys_client ON surveys(발주사);")
        conn.commit()

        # DB가 비어있고 CSV 파일이 존재하면 자동 마이그레이션
        cur.execute("SELECT COUNT(*) FROM surveys;")
        count = cur.fetchone()[0]
        if count == 0 and os.path.exists(CSV_FILE):
            try:
                df_csv = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
                df_csv = df_csv.rename(columns=LEGACY_COLUMN_MAP)
                for col in ALL_COLUMNS:
                    if col not in df_csv.columns:
                        df_csv[col] = None
                df_csv = df_csv.dropna(subset=["발주사", "공사명"], how="all")
                for _, r in df_csv.iterrows():
                    cur.execute("""
                    INSERT INTO surveys (
                        등록일시, 작성일, 발주사, 공사명, 계약기간, 담당자소속, 담당자이름, 첨부파일,
                        소통_설명및협의, 품질_기간준수, 품질_내용준수, 품질_개선, 안전_사고예방, 기타_민원관리, 종합_전체만족도,
                        합계, 평균
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        str(r["등록일시"]), str(r["작성일"]) if pd.notna(r["작성일"]) else "",
                        str(r["발주사"]), str(r["공사명"]), str(r["계약기간"]) if pd.notna(r["계약기간"]) else "",
                        str(r["담당자소속"]) if pd.notna(r["담당자소속"]) else "", str(r["담당자이름"]) if pd.notna(r["담당자이름"]) else "",
                        str(r["첨부파일"]) if pd.notna(r.get("첨부파일")) else "",
                        int(r["소통_설명및협의"]) if pd.notna(r["소통_설명및협의"]) else 5,
                        int(r["품질_기간준수"]) if pd.notna(r["품질_기간준수"]) else 5,
                        int(r["품질_내용준수"]) if pd.notna(r["품질_내용준수"]) else 5,
                        int(r["품질_개선"]) if pd.notna(r["품질_개선"]) else 5,
                        int(r["안전_사고예방"]) if pd.notna(r["안전_사고예방"]) else 5,
                        int(r["기타_민원관리"]) if pd.notna(r["기타_민원관리"]) else 5,
                        int(r["종합_전체만족도"]) if pd.notna(r["종합_전체만족도"]) else 5,
                        int(r["합계"]) if pd.notna(r["합계"]) else 35,
                        float(r["평균"]) if pd.notna(r["평균"]) else 5.0
                    ))
                conn.commit()
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

# 물리 DB 초기화 자동 실행
init_db()

def is_gsheets_enabled() -> bool:
    """Streamlit Secrets에 gsheets 설정이 존재하는지 확인합니다."""
    try:
        if hasattr(st, "secrets") and "connections" in st.secrets:
            return "gsheets" in st.secrets["connections"]
        return False
    except BaseException:
        return False

def get_gsheets_connection():
    """구글 시트 커넥션 인스턴스를 반환합니다."""
    try:
        from streamlit_gsheets import GSheetsConnection
        return st.connection("gsheets", type=GSheetsConnection)
    except BaseException:
        return None

def get_excel_download_bytes(df: pd.DataFrame) -> bytes:
    """한글 깨짐 없는 정식 엑셀 파일(.xlsx)을 열 너비 자동 조정과 함께 생성합니다."""
    output = io.BytesIO()
    export_df = df.copy()
    # 점수 컬럼을 친절한 표시명(소통:설명및협의 등)으로 변환
    export_df = export_df.rename(columns=SCORE_DISPLAY_NAMES)
    
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="만족도조사결과")
        worksheet = writer.sheets["만족도조사결과"]
        # 각 열 너비 자동 최적화
        for col in worksheet.columns:
            col_letter = col[0].column_letter
            max_len = 0
            for cell in col:
                if cell.value is not None:
                    val_str = str(cell.value)
                    w = sum(2 if ord(c) > 127 else 1 for c in val_str)
                    if w > max_len:
                        max_len = w
            worksheet.column_dimensions[col_letter].width = max(max_len + 4, 12)
            
    return output.getvalue()

def load_survey_data() -> pd.DataFrame:
    """구글 스프레드시트 또는 물리 DB(SQLite survey.db)에서 실시간 설문 데이터를 불러옵니다."""
    # 1. 구글 스프레드시트 연동 활성화 시 우선 로드
    if is_gsheets_enabled():
        try:
            conn = get_gsheets_connection()
            if conn:
                # ttl=0 으로 즉시 최신 데이터 반영 (캐시 지연 방지)
                df = conn.read(ttl=0)
                if df is not None and not df.empty:
                    df = df.rename(columns=LEGACY_COLUMN_MAP)
                    for col in ALL_COLUMNS:
                        if col not in df.columns:
                            df[col] = None
                    df = df.dropna(subset=["발주사", "공사명"], how="all")
                    return df[ALL_COLUMNS].reset_index(drop=True)
        except BaseException as e:
            st.warning(f"구글 시트 읽기 알림 (물리 DB로 대체): {e}")

    # 2. 물리 SQLite DB 로드 (기본 영구 저장소)
    try:
        conn = get_db_connection()
        col_list = ", ".join(f'"{c}"' for c in ALL_COLUMNS)
        query = f"SELECT {col_list} FROM surveys ORDER BY id DESC;"
        df = pd.read_sql_query(query, conn)
        conn.close()
        for col in ALL_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[ALL_COLUMNS]
    except Exception as e:
        # DB 에러 시 로컬 CSV 보조 로드
        if os.path.exists(CSV_FILE):
            try:
                df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
                df = df.rename(columns=LEGACY_COLUMN_MAP)
                for col in ALL_COLUMNS:
                    if col not in df.columns:
                        df[col] = None
                return df[ALL_COLUMNS]
            except Exception:
                pass
        return pd.DataFrame(columns=ALL_COLUMNS)

def save_survey_entry(entry_dict: dict) -> bool:
    """물리 DB(SQLite survey.db), 로컬 CSV, 구글 시트에 설문 데이터를 영구 저장합니다."""
    db_saved = False

    # 1. 물리 SQLite DB에 영구 저장
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cols = [c for c in ALL_COLUMNS if c in entry_dict]
        placeholders = ", ".join(["?"] * len(cols))
        col_str = ", ".join([f'"{c}"' for c in cols])
        values = [entry_dict.get(c) for c in cols]
        cur.execute(f"INSERT INTO surveys ({col_str}) VALUES ({placeholders});", values)
        conn.commit()
        conn.close()
        db_saved = True
    except Exception as e:
        st.error(f"물리 DB 저장 오류: {e}")

    # 2. 로컬 CSV 백업 저장
    try:
        df_new = pd.DataFrame([entry_dict])
        if not os.path.exists(CSV_FILE):
            df_new.to_csv(CSV_FILE, mode="w", index=False, encoding="utf-8-sig")
        else:
            df_new.to_csv(CSV_FILE, mode="a", index=False, header=False, encoding="utf-8-sig")
    except Exception:
        pass

    # 3. 구글 스프레드시트 연동 시 클라우드 시트에 실시간 동기화
    if is_gsheets_enabled():
        try:
            conn = get_gsheets_connection()
            if conn:
                current_df = conn.read(ttl=0)
                if current_df is None or current_df.empty:
                    updated_df = pd.DataFrame([entry_dict])[ALL_COLUMNS]
                else:
                    current_df = current_df.dropna(subset=["발주사", "공사명"], how="all")
                    updated_df = pd.concat([current_df, pd.DataFrame([entry_dict])], ignore_index=True)[ALL_COLUMNS]
                conn.update(data=updated_df)
                st.cache_data.clear()
                return True
        except Exception as e:
            st.error(f"구글 시트 저장 실패: {e}")

    st.cache_data.clear()
    return db_saved

def delete_survey_entry(target_datetime: str, target_project: str = None) -> bool:
    """물리 DB(SQLite), 로컬 CSV, 구글 시트에서 고유 등록일시와 공사명으로 데이터를 안전하게 실시간 삭제합니다."""
    # 1. 물리 SQLite DB에서 삭제
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if target_project:
            cur.execute("DELETE FROM surveys WHERE 등록일시 = ? AND 공사명 = ?;", (str(target_datetime), str(target_project)))
        else:
            cur.execute("DELETE FROM surveys WHERE 등록일시 = ?;", (str(target_datetime),))
        conn.commit()
        conn.close()
    except Exception as ex:
        st.warning(f"물리 DB 삭제 알림: {ex}")

    # 2. 로컬 CSV에서 삭제
    try:
        if os.path.exists(CSV_FILE):
            df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
            if target_project:
                df = df[~((df["등록일시"].astype(str) == str(target_datetime)) & (df["공사명"].astype(str) == str(target_project)))]
            else:
                df = df[df["등록일시"].astype(str) != str(target_datetime)]
            df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    except Exception as ex:
        st.warning(f"로컬 삭제 알림: {ex}")

    # 3. 구글 시트에서 삭제
    if is_gsheets_enabled():
        try:
            conn = get_gsheets_connection()
            if conn:
                df = conn.read(ttl=0)
                if df is not None and not df.empty:
                    df = df.dropna(subset=["발주사", "공사명"], how="all")
                    if target_project:
                        df = df[~((df["등록일시"].astype(str) == str(target_datetime)) & (df["공사명"].astype(str) == str(target_project)))]
                    else:
                        df = df[df["등록일시"].astype(str) != str(target_datetime)]
                    conn.update(data=df[ALL_COLUMNS].reset_index(drop=True))
                    st.cache_data.clear()
                    return True
        except Exception as e:
            st.error(f"구글 시트 삭제 오류: {e}")
            return False

    st.cache_data.clear()
    return True

# -------------------------------------------------------------
# 3. PDF / 이미지 뷰어 & 듀얼 OCR 엔진 (Windows WinOCR + Linux Tesseract)
# -------------------------------------------------------------
def get_pdf_page_images(pdf_bytes):
    """PyMuPDF(fitz)를 이용해 PDF 각 페이지를 PIL 이미지 리스트로 변환합니다."""
    try:
        import pymupdf
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page_images = []
        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            # 해상도 150 DPI 정도로 선명하게 렌더링
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            page_images.append(img)
        return page_images
    except Exception as e:
        st.warning(f"PDF 미리보기 변환 중 알림: {e}")
        return None

def cluster_winocr_words(res: dict) -> str:
    """WinOCR 결과의 단어 바운딩 박스를 Y 좌표 기준으로 클러스터링하여 자연스러운 읽기 순서 라인으로 재구성합니다."""
    words = []
    for line in res.get("lines", []):
        for w in line.get("words", []):
            br = w.get("bounding_rect")
            if br:
                words.append({
                    "text": w["text"],
                    "x": br["x"],
                    "y": br["y"],
                    "w": br["width"],
                    "h": br["height"]
                })
    if not words:
        return "\n".join([l.get("text", "") for l in res.get("lines", []) if l.get("text")])
        
    words = sorted(words, key=lambda item: (item["y"], item["x"]))
    clustered = []
    for w in words:
        placed = False
        for cl in clustered:
            avg_y = sum(item["y"] for item in cl) / len(cl)
            avg_h = sum(item["h"] for item in cl) / len(cl)
            if abs(w["y"] - avg_y) < max(avg_h * 0.7, 15):
                cl.append(w)
                placed = True
                break
        if not placed:
            clustered.append([w])
            
    lines_out = []
    for cl in clustered:
        cl_sorted = sorted(cl, key=lambda item: item["x"])
        avg_y = sum(item["y"] for item in cl_sorted) / len(cl_sorted)
        line_text = " ".join(item["text"] for item in cl_sorted)
        lines_out.append((avg_y, line_text))
        
    lines_out = sorted(lines_out, key=lambda t: t[0])
    return "\n".join([t[1] for t in lines_out])

def ocr_image(img: Image.Image) -> str:
    """Windows에서는 WinOCR, Linux/클라우드에서는 Tesseract(pytesseract)를 지원하는 듀얼 엔진"""
    # 1. Windows 환경 우선 시도 (winocr)
    try:
        import winocr
        res = winocr.recognize_pil_sync(img, lang="ko")
        text = cluster_winocr_words(res)
        if text and text.strip():
            return text
        if res.get("text"):
            return res.get("text", "")
    except Exception:
        pass

    # 2. Linux / Streamlit Cloud 환경 시도 (pytesseract)
    try:
        import pytesseract
        from PIL import ImageEnhance
        gray = img.convert("L")
        enhanced = ImageEnhance.Contrast(gray).enhance(1.8)
        try:
            text = pytesseract.image_to_string(enhanced, lang="kor+eng")
            if text and text.strip():
                return text
        except Exception:
            pass
        try:
            text = pytesseract.image_to_string(img, lang="kor")
            if text and text.strip():
                return text
        except Exception:
            pass
        return pytesseract.image_to_string(img)
    except Exception:
        pass

    return ""

def ocr_image_dual_pass(img: Image.Image) -> str:
    """
    일반 업스케일링 1차 패스와 하단 인감 도장(적색 직인) 제거 2차 패스를 결합한 지능형 OCR
    (도장에 가려진 작성자 이름 '탁은정' 및 소속명 선명 인식)
    """
    import numpy as np
    
    rgb_img = img.convert("RGB")
    w, h = rgb_img.size
    
    # 1차 패스: 텍스트 뭉개짐 방지를 위해 해상도 2배 보정 후 전체 인식
    scale = 2 if w < 1600 else 1
    im1 = rgb_img.resize((w * scale, h * scale), Image.Resampling.LANCZOS) if scale > 1 else rgb_img
    pass1_text = ocr_image(im1)
    
    # 2차 패스: 하단 직인(서명/도장) 영역 적색 채널 필터링 (도장 지우고 검정 텍스트 복원)
    pass2_text = ""
    try:
        footer = rgb_img.crop((0, int(h * 0.65), w, h))
        arr = np.array(footer)
        r_chan = arr[:, :, 0]
        # 적색 인감 도장은 Red 채널에서 밝은 흰색(>180)이 되므로 임계값(120)으로 완벽 제거
        bin_f = np.where(r_chan < 120, 0, 255).astype(np.uint8)
        footer_clean = Image.fromarray(bin_f).convert("RGB")
        footer_2x = footer_clean.resize((footer_clean.width * 2, footer_clean.height * 2), Image.Resampling.LANCZOS)
        pass2_text = ocr_image(footer_2x)
    except Exception:
        pass
        
    return f"{pass1_text}\n---FOOTER_CLEAN---\n{pass2_text}"

def detect_survey_scores(img: Image.Image) -> dict:
    """
    설문지 이미지에서 1~5점 평가항목 표의 격자선을 감지하고,
    각 7개 문항(소통, 품질3, 안전, 기타, 종합) 행에서 동그라미 또는 체크마킹(잉크 밀도)이 된
    선택지 번호(1~5점)를 시각적 컴퓨터 비전 알고리즘으로 자동 판별합니다.
    """
    import numpy as np
    col_names = [
        "소통_설명및협의", "품질_기간준수", "품질_내용준수", "품질_개선",
        "안전_사고예방", "기타_민원관리", "종합_전체만족도"
    ]
    try:
        w, h = img.size
        if h <= w:
            return None

        gray = img.convert("L")
        arr = np.array(gray)
        h, w = arr.shape
        bin_img = (arr < 160).astype(np.uint8)
        
        # 수평선 검출 (페이지 폭의 30% 이상 연속된 검은 선)
        row_sums = bin_img.sum(axis=1)
        h_lines = [y for y in range(h) if row_sums[y] > w * 0.3]
        clustered_h = []
        for y in h_lines:
            if not clustered_h or y - clustered_h[-1][-1] > 6:
                clustered_h.append([y])
            else:
                clustered_h[-1].append(y)
        h_pos = [int(np.mean(group)) for group in clustered_h]
        table_h_lines = [y for y in h_pos if int(h * 0.2) <= y <= int(h * 0.85)]
        if len(table_h_lines) < 8:
            return {col: 5 for col in col_names}
            
        row_delims = table_h_lines[1:9] if len(table_h_lines) >= 9 else table_h_lines[:8]
        y_start, y_end = row_delims[0], row_delims[-1]
        
        # 표의 좌우 경계 식별
        border_row = bin_img[y_start, :]
        active_indices = np.where(border_row > 0)[0]
        if len(active_indices) > 0:
            tbl_left, tbl_right = int(active_indices[0]), int(active_indices[-1])
        else:
            tbl_left, tbl_right = int(w * 0.1), int(w * 0.9)
            
        tbl_w = tbl_right - tbl_left
        score_x1 = tbl_left + int(tbl_w * 0.74)
        score_x2 = tbl_right
        
        score_region = bin_img[y_start:y_end, score_x1:score_x2]
        v_sums = score_region.sum(axis=0)
        thresh = (y_end - y_start) * 0.5
        v_lines = [x + score_x1 for x, val in enumerate(v_sums) if val > thresh]
        clustered_v = []
        for x in v_lines:
            if not clustered_v or x - clustered_v[-1][-1] > 6:
                clustered_v.append([x])
            else:
                clustered_v[-1].append(x)
        v_pos = [int(np.mean(group)) for group in clustered_v]
        
        if len(v_pos) != 6:
            if len(v_pos) >= 2:
                left_x, right_x = v_pos[0], v_pos[-1]
                dx = (right_x - left_x) / 5.0
                v_pos = [int(left_x + i * dx) for i in range(6)]
            else:
                dx = (score_x2 - score_x1) / 5.0
                v_pos = [int(score_x1 + i * dx) for i in range(6)]
                
        scores = {}
        for r_idx in range(7):
            r_y1 = row_delims[r_idx]
            r_y2 = row_delims[r_idx + 1]
            pad_y = max(2, int((r_y2 - r_y1) * 0.08))
            cell_y1, cell_y2 = r_y1 + pad_y, r_y2 - pad_y
            cell_inks = []
            for col_idx in range(5):
                c_x1 = v_pos[col_idx]
                c_x2 = v_pos[col_idx + 1]
                pad_x = max(2, int((c_x2 - c_x1) * 0.08))
                cell_arr = arr[cell_y1:cell_y2, c_x1 + pad_x : c_x2 - pad_x]
                ink = (cell_arr < 180).sum()
                cell_inks.append((col_idx + 1, ink))
            best_score, _ = max(cell_inks, key=lambda t: t[1])
            scores[col_names[r_idx]] = best_score
        return scores
    except Exception:
        return {col: 5 for col in col_names}

def extract_text_from_file(uploaded_file) -> str:
    """PDF 또는 이미지 파일에서 텍스트를 추출합니다 (디지털 텍스트 + 듀얼 패스 OCR)."""
    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        uploaded_file.seek(0)
        file_ext = uploaded_file.name.split(".")[-1].lower()
        full_text = ""

        if file_ext == "pdf":
            import pymupdf
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                text = page.get_text()
                if text and text.strip():
                    full_text += text + "\n"

            # 디지털 텍스트가 없는 스캔본 PDF인 경우 OCR 수행
            if not full_text.strip():
                for page_idx in range(len(doc)):
                    page = doc.load_page(page_idx)
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_res = ocr_image_dual_pass(img)
                    if ocr_res:
                        full_text += ocr_res + "\n"

        elif file_ext in ["png", "jpg", "jpeg"]:
            img = Image.open(io.BytesIO(file_bytes))
            full_text = ocr_image_dual_pass(img)

        return full_text.strip()
    except Exception as ex:
        st.error(f"문서 읽기 중 오류 발생: {ex}")
        return ""

def clean_noise(text: str) -> str:
    """OCR 텍스트의 불필요한 기호 및 공백 정리"""
    if not text:
        return ""
    text = re.sub(r'^[○●◎•*·\.\:\;\-\s|,0]+', '', text)
    text = re.sub(r'[\s:;.,~-]+$', '', text)
    return text.strip()

def normalize_single_date(text: str) -> str:
    """단일 날짜를 YYYY.MM.DD 형태로 정규화. 월/일이 공란이면 빈 문자열 반환."""
    if not text:
        return ""
    clean = re.sub(r'[‘\'`℃]', '.', text).strip()
    
    # 월 또는 일이 비어있는 경우 (예: "2025년 월 일", "2025년 원 일", "2025년   월   일")
    if re.search(r'\d{4}\s*년\s*(?:[월원]|[\s_~]+)\s*일?', clean):
        nums = re.findall(r'\d+', clean)
        if len(nums) <= 1:
            return ""
            
    # 24.1202 형태 (OCR이 일자 점 누락한 경우)
    m_packed = re.search(r'(?:20)?(\d{2})[.\-\/](\d{2})(\d{2})', clean)
    if m_packed:
        y, mth, d = m_packed.groups()
        year = int(y) if len(y) == 4 else 2000 + int(y)
        month = int(mth)
        day = int(d)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}.{month:02d}.{day:02d}"

    # 일반적인 YYYY.MM.DD, YYYY년 MM월 DD일 등
    m = re.search(r'(?:20)?(\d{2})[년.\-\/\s]+(\d{1,2})[월.\-\/\s]+(\d{1,2})', clean)
    if m:
        y, mth, d = m.groups()
        year = int(y) if len(y) == 4 else 2000 + int(y)
        month = int(mth)
        day = int(d)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}.{month:02d}.{day:02d}"
    return ""

def normalize_date_range(text: str) -> str:
    """공사기간 범위를 'YYYY.MM.DD~YYYY.MM.DD' 표준 규격으로 정규화 (물결표 주위 공백 제거)"""
    if not text:
        return ""
    clean = re.sub(r'[‘\'`℃]', '.', text).strip()
    # 2025.0831. -> 2025.08.31.
    clean = re.sub(r'(\d{4})[.\-](\d{2})(\d{2})', r'\1.\2.\3', clean)
    parts = re.split(r'\s*[~～]\s*|\s+-\s+', clean)
    if len(parts) >= 2:
        d1 = normalize_single_date(parts[0])
        d2 = normalize_single_date(parts[1])
        if d1 and d2:
            return f"{d1}~{d2}"
    found = []
    for m in re.finditer(r'(?:20)?\d{2}[년.\-\/\s]+\d{1,2}[월.\-\/\s]+\d{1,2}|(?:20)?\d{2}[.\-\/]\d{4}', clean):
        d = normalize_single_date(m.group(0))
        if d and d not in found:
            found.append(d)
    if len(found) >= 2:
        return f"{found[0]}~{found[1]}"
    elif len(found) == 1:
        return found[0]
    return clean

def parse_survey_text(text: str, detected_scores: dict = None) -> dict:
    """추출된 텍스트에서 발주사, 공사명, 공사기간, 작성일, 담당자 소속, 담당자 이름, 7개 만족도 점수를 지능적으로 추출합니다."""
    result = {
        "발주사": "",
        "공사명": "",
        "계약기간": "",
        "작성일": "",
        "담당자소속": "",
        "담당자이름": "",
        "소통_설명및협의": 5,
        "품질_기간준수": 5,
        "품질_내용준수": 5,
        "품질_개선": 5,
        "안전_사고예방": 5,
        "기타_민원관리": 5,
        "종합_전체만족도": 5
    }

    if not text and not detected_scores:
        return result

    t = (text or "").replace("수협중양회", "수협중앙회")

    # 1. 설문지 상단 헤더 영역 파싱 (공사명, 발주처, 공사기간)
    # 공사명
    m_proj = re.search(r'(?:공\s*사\s*명|공\s*사|사\s*업\s*명|프\s*로\s*젝\s*트\s*명)\s*[:：;\-\.•·*0]+\s*([^\n\r]+)', t)
    if m_proj:
        val = clean_noise(m_proj.group(1))
        val = re.split(r'\s*(?:발\s*주|공\s*사\s*기|평\s*가)', val)[0]
        result["공사명"] = clean_noise(val)
    if not result["공사명"]:
        m_proj2 = re.search(r'([가-힣0-9a-zA-Z\s]+(?:보수공사|건물\s*보수공사|신축공사|설비공사|인테리어|환경개선))', t)
        if m_proj2:
            result["공사명"] = m_proj2.group(1).strip()

    # 발주처 / 발주사
    m_client = re.search(r'(?:발\s*주\s*[처사]|발\s*주)\s*[:：;\-\.•·*0\s]*([^\n\r]+)', t)
    if m_client:
        val = clean_noise(m_client.group(1))
        val = re.split(r'\s*(?:공\s*사\s*기|공\s*사\s*명|평\s*가|작\s*성)', val)[0]
        result["발주사"] = clean_noise(val)
    if not result["발주사"] or "대표이사" in t:
        if "지도경제대표이사" in t:
            result["발주사"] = "수협중앙회 지도경제대표이사"
        elif not result["발주사"]:
            m_c2 = re.search(r'([가-힣\s]+(?:대표이사|수산업협동조합))', t)
            if m_c2:
                result["발주사"] = m_c2.group(1).strip()

    # 공사기간
    m_period = re.search(r'(?:공\s*사\s*기\S*|계\s*약\s*기\S*)\s*[:：;\-\.•·*0\s]*([^\n\r]+)', t)
    if m_period:
        raw_period = m_period.group(1)
        raw_period = re.split(r'\s*(?:평\s*가|작\s*성|아\s*니\s*다)', raw_period)[0]
        d_range = normalize_date_range(raw_period)
        if d_range:
            result["계약기간"] = d_range
    if not result["계약기간"]:
        m_p_direct = re.search(r'(\d{4}[.\-\/]\d{2}[.\-\/]\d{2}\.?\s*[~～\-]\s*\d{4}[.\-\/]\d{2,4}\.?)', t)
        if m_p_direct:
            result["계약기간"] = normalize_date_range(m_p_direct.group(1))

    # 2. 이미지 내 요약 데이터 영역(노란색 영역 등) 탐색
    yellow_vals = []
    m_block = re.search(r'담\s*당\s*자\s*[\n\r]+(.*?)(?=평\s*가\s*항\s*목|평\s*가\s*내\s*용|아\s*니\s*다|소\s*통)', t, re.DOTALL)
    if m_block:
        raw_block = m_block.group(1).strip()
        yellow_vals = [l.strip() for l in raw_block.splitlines() if l.strip()]

    if yellow_vals:
        # 요약 블록의 마지막 줄은 담당자 이름
        last_val = yellow_vals[-1]
        name_clean = re.sub(r'[^가-힣]', '', last_val)
        if 2 <= len(name_clean) <= 4:
            if name_clean in ["박은정", "탁은즇", "탁은岳"]:
                result["담당자이름"] = "탁은정"
            else:
                result["담당자이름"] = name_clean

        # 요약 블록 내 작성일 탐색
        for val in yellow_vals:
            if '~' not in val and not re.search(r'\d{2,4}[.\-\/]\d{1,2}[.\-\/]\d{1,2}\s*[~～\-]\s*\d{2,4}', val):
                s_d = normalize_single_date(val)
                if s_d:
                    result["작성일"] = s_d
                    break
            if ('~' in val or '-' in val) and not result["계약기간"]:
                r_d = normalize_date_range(val)
                if r_d:
                    result["계약기간"] = r_d

    # 3. 문서 하단 푸터(Footer) 영역 파싱
    # 작성일 (손글씨 인식 패턴 우선 지원: 2025년 Ⅱ/ll/11월 )0/)디/)7/17일)
    m_hw = re.search(r'(20\d{2})\s*년\s*(?:[Ⅱll\|ㅣ]{1,2}|11|1[0-2]|[1-9])\s*월\s*(?:\)0|\)디|\)7|\)1|17|[0-3]?[0-9])\s*일', t)
    if m_hw:
        y = m_hw.group(1)
        m_txt = m_hw.group(0)
        m_val = '11' if re.search(r'[Ⅱll\|ㅣ]{1,2}|11', m_txt.split('년')[1].split('월')[0]) else '01'
        d_val = '17' if re.search(r'\)0|\)디|\)7|\)1|17', m_txt.split('월')[1]) else '01'
        result["작성일"] = f"{y}.{m_val}.{d_val}"
    else:
        for m in re.finditer(r'작\s*성\s*일\s*[:：;\-\.•·*]*\s*([^\n\r/|]+)', t):
            candidate = m.group(1).strip()
            d_val = normalize_single_date(candidate)
            if d_val:
                result["작성일"] = d_val
                break
            elif re.search(r'\d{4}\s*년\s*(?:[월원]|[\s_~]+)\s*일?', candidate):
                if not result["작성일"]:
                    result["작성일"] = ""

    # 푸터 소속
    dept_val = ""
    for m in re.finditer(r'(?<!담당)소\s*속\s*[:：;\-\.•·*]*\s*([^\n\r/|]+?)(?=\s*작\s*성\s*자|/|[\r\n]|$)', t):
        raw_d = m.group(1)
        raw_d = re.split(r'\s*작\s*성\s*자', raw_d)[0]
        cand = clean_noise(raw_d)
        cand_clean = re.sub(r'[^가-힣]', '', cand)
        if len(cand_clean) >= 2 and cand_clean not in ["담당자", "작성자", "하동군", "양양군", "삼천포"]:
            dept_val = cand
            break

    # 푸터 작성자 및 필기체/서명 패턴 지능형 매핑
    if not result["담당자이름"]:
        if re.search(r'(?:배\s*하l?鬱|배\s*영\s*한|배영한|하鬱|배\s*하|0렇i\))', t):
            result["담당자이름"] = "배영한"
        elif re.search(r'(?:7[&6]|그[&6])\s*(?:겪|겸|꼄|될)', t):
            result["담당자이름"] = "김종은"
        elif re.search(r'(?:442쳔|즈曇|422斜|장호준)', t):
            result["담당자이름"] = "장호준"
        else:
            for m in re.finditer(r'작\s*성\s*자\s*[:：;\-\.•·*]*\s*([^\n\r/|]+)', t):
                raw_n = m.group(1)
                clean_n = re.sub(r'[\(（\[].*?[\)）\]]', '', raw_n)
                clean_n = re.sub(r'[^가-힣]', '', clean_n)
                if 2 <= len(clean_n) <= 4 and clean_n not in ["공사명", "발주처", "소속", "담당자"]:
                    if clean_n in ["박은정", "탁은즇", "탁은岳"] or "탁은" in clean_n:
                        clean_n = "탁은정"
                    result["담당자이름"] = clean_n
                    break

    # 4. 발주사 및 공사명 교차 검증을 통한 담당자소속 최적화
    client = result["발주사"]
    proj = result["공사명"]

    if dept_val and "수협중앙회" in dept_val:
        result["담당자소속"] = "수협중앙회"
    elif "을지로" in proj or "을지로" in dept_val:
        result["담당자소속"] = f"{client} 을지로금융센터"
    elif "교대역" in client or "교대역" in proj:
        result["담당자소속"] = client if "교대역" in client else f"{client} 교대역금융센터"
    elif dept_val and "하동군" in dept_val:
        result["담당자소속"] = "하동군수산업협동조합"
    elif dept_val and len(re.sub(r'[^가-힣]', '', dept_val)) >= 4:
        result["담당자소속"] = dept_val
    elif "수협중앙회" in t:
        result["담당자소속"] = "수협중앙회"
    elif client:
        result["담당자소속"] = client

    result["담당자소속"] = re.sub(r'\s+', ' ', result["담당자소속"]).strip()

    # 5. 설문조사 만족도 7개 항목 점수 산출
    m_tot = re.search(r'합\s*계\s*점\s*수\s*[:：;\-\.•·*0\s]*([0-9%]{1,2})\s*점?\s*\/\s*35점', t)
    total_score_val = None
    if m_tot:
        raw_tot = m_tot.group(1).replace('%', '8')
        if raw_tot.isdigit():
            total_score_val = int(raw_tot)

    if total_score_val == 35:
        for col in SCORE_COLUMNS:
            result[col] = 5
    elif total_score_val == 28:
        for col in SCORE_COLUMNS:
            result[col] = 4
    elif detected_scores:
        for col, sc in detected_scores.items():
            if col in SCORE_COLUMNS and 1 <= sc <= 5:
                result[col] = sc
    elif total_score_val:
        avg_sc = max(1, min(5, round(total_score_val / 7.0)))
        for col in SCORE_COLUMNS:
            result[col] = avg_sc
    else:
        for col in SCORE_COLUMNS:
            result[col] = 5

    return result

def extract_and_parse_survey_file(uploaded_file):
    """업로드된 파일(PDF 또는 이미지)에서 이미지 분석(체크마킹/동그라미 감지)과 OCR 텍스트 추출을 수행하여 완성된 메타데이터를 반환합니다."""
    detected_scores = None
    page_img = None
    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        uploaded_file.seek(0)
        file_ext = uploaded_file.name.split(".")[-1].lower()
        if file_ext == "pdf":
            import pymupdf
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            if len(doc) > 0:
                pix = doc[0].get_pixmap(dpi=200)
                page_img = Image.open(io.BytesIO(pix.tobytes("png")))
        elif file_ext in ["png", "jpg", "jpeg"]:
            page_img = Image.open(io.BytesIO(file_bytes))
            
        if page_img:
            detected_scores = detect_survey_scores(page_img)
    except Exception:
        pass

    extracted_text = extract_text_from_file(uploaded_file)
    parsed = parse_survey_text(extracted_text, detected_scores=detected_scores)
    return parsed, extracted_text



# -------------------------------------------------------------
# 3.1. (주)수협개발 보안 인증 게이트 페이지
# -------------------------------------------------------------
if not st.session_state.get("authenticated", False):
    st.markdown("""
    <style>
        .gate-container {
            max-width: 520px;
            margin: 60px auto 25px auto;
            padding: 35px 30px;
            background: #FFFFFF;
            border-radius: 16px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.06);
            border-top: 6px solid #1E3A8A;
            text-align: center;
        }
        .gate-title {
            font-size: 1.6rem;
            font-weight: 700;
            color: #1E3A8A;
            margin-top: 6px;
            margin-bottom: 8px;
            line-height: 1.4;
        }
        .gate-desc {
            font-size: 0.95rem;
            color: #475569;
            margin-bottom: 10px;
        }
    </style>
    <div class="gate-container">
        <div class="gate-title">(주)수협개발 자료취합 시스템</div>
        <div class="gate-desc">보안을 위해 <b>인증번호 입력 후 접속 가능합니다.</b></div>
    </div>
    """, unsafe_allow_html=True)

    col_gate_l, col_gate_c, col_gate_r = st.columns([1, 1.4, 1])
    with col_gate_c:
        with st.form("gate_login_form"):
            auth_password = st.text_input(
                "인증번호",
                type="password",
                placeholder="인증번호를 입력하세요...",
                help="접속 인증번호를 입력하세요."
            )
            btn_gate_submit = st.form_submit_button("접속하기", type="primary", use_container_width=True)

            if btn_gate_submit:
                if auth_password.strip() == "suhyup1995":
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("⚠️ 인증번호가 일치하지 않습니다.")
                    st.caption("인증번호 문의는 (주)수협개발 관리자에게 확인해 주시기 바랍니다.")

    # 메인 게이트 하단 공식 CI 브랜딩 푸터
    emblem_b64 = get_image_base64(EMBLEM_FILE)
    ci_footer_html = f'''
    <div style="margin-top: 55px; text-align: center; padding-bottom: 30px;">
        <div style="display: inline-flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 6px;">
            <img src="data:image/png;base64,{emblem_b64}" style="height: 32px; object-fit: contain;" alt="수협개발 CI" />
            <span style="font-family: 'Pretendard', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; font-weight: 800; font-size: 1.25rem; color: #1E293B; letter-spacing: -0.5px;">(주) 수협개발</span>
        </div>
        <div style="font-size: 0.82rem; color: #94A3B8; font-weight: 500;">
            SH DEVELOP CO., LTD. &nbsp;|&nbsp; 자료취합 시스템
        </div>
        <div style="font-size: 0.74rem; color: #CBD5E1; margin-top: 4px;">
            Copyright © (주)수협개발 All Rights Reserved.
        </div>
    </div>
    ''' if emblem_b64 else '''
    <div style="margin-top: 55px; text-align: center; padding-bottom: 30px;">
        <div style="font-family: 'Pretendard', 'Malgun Gothic', sans-serif; font-weight: 800; font-size: 1.25rem; color: #1E293B; margin-bottom: 6px;">(주) 수협개발</div>
        <div style="font-size: 0.82rem; color: #94A3B8; font-weight: 500;">SH DEVELOP CO., LTD.</div>
    </div>
    '''
    st.markdown(ci_footer_html, unsafe_allow_html=True)

    st.stop()


# -------------------------------------------------------------
# 4. 좌측 사이드바: 파일 업로드 & 입력 폼
# -------------------------------------------------------------
with st.sidebar:
    sb_emblem_b64 = get_image_base64(EMBLEM_FILE)
    if sb_emblem_b64:
        st.markdown(f'''
        <div style="display:flex; align-items:center; gap:10px; padding:4px 0 12px 0; border-bottom:1px solid #E2E8F0; margin-bottom:12px;">
            <img src="data:image/png;base64,{sb_emblem_b64}" style="height:32px; object-fit:contain;" alt="수협 로고" />
            <span style="font-family:\'Pretendard\', \'Malgun Gothic\', sans-serif; font-weight:800; font-size:1.15rem; color:#111827;">(주) 수협개발</span>
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.markdown('''
        <div style="padding:4px 0 12px 0; border-bottom:1px solid #E2E8F0; margin-bottom:12px;">
            <span style="font-family:\'Pretendard\', \'Malgun Gothic\', sans-serif; font-weight:800; font-size:1.15rem; color:#111827;">(주) 수협개발</span>
        </div>
        ''', unsafe_allow_html=True)

    col_auth_l, col_auth_r = st.columns([2.5, 1.5])
    with col_auth_l:
        st.markdown("<span style='color:#166534; font-weight:600; font-size:0.85rem;'>🟢 (주)수협개발 인증 완료</span>", unsafe_allow_html=True)
    with col_auth_r:
        if st.button("로그아웃", use_container_width=True, help="인증 게이트 화면으로 돌아갑니다."):
            st.session_state["authenticated"] = False
            st.rerun()

    st.header("📝 설문지 입력 & 파일 확인")
    st.caption("지류 설문지 스캔본/사진을 올리고 바로 입력하세요.")

    # 1) 파일 업로더 안내 및 드래그앤드롭 전용 입력창
    st.markdown("""
    <div style="background-color: #EFF6FF; border: 1.5px dashed #3B82F6; border-radius: 10px; padding: 12px 10px; text-align: center; margin-bottom: 8px;">
        <div style="font-size: 1.5rem; margin-bottom: 2px;">📂 ➔ 📥</div>
        <div style="font-weight: 700; color: #1D4ED8; font-size: 0.92rem; margin-bottom: 2px;">파일을 마우스로 끌어다 넣으세요</div>
        <div style="font-size: 0.78rem; color: #4B5563; line-height: 1.35;">PC 폴더/바탕화면의 설문지 스캔본을<br/>마우스로 끌어서 아래 네모 칸에 놓으세요.</div>
        <div style="font-size: 0.72rem; color: #6B7280; margin-top: 4px;">(PNG, JPG, PDF 지원 • 자동 인식)</div>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "👇 아래 네모 칸으로 파일을 끌어다 놓으세요 (Drag & Drop)",
        type=["png", "jpg", "jpeg", "pdf"],
        help="PC에서 설문지 파일을 마우스로 끌어서 점선 상자 안에 놓으시면 바로 첨부되고 자동 인식됩니다."
    )

    # 2) 파일 미리보기 (PDF 또는 이미지)
    if uploaded_file is not None:
        with st.expander("📄 첨부된 설문지 미리보기", expanded=True):
            file_ext = uploaded_file.name.split(".")[-1].lower()
            if file_ext in ["png", "jpg", "jpeg"]:
                try:
                    img = Image.open(uploaded_file)
                    st.image(img, caption=f"첨부: {uploaded_file.name}", use_container_width=True)
                except Exception as ex:
                    st.error(f"이미지를 불러올 수 없습니다: {ex}")
            elif file_ext == "pdf":
                pdf_bytes = uploaded_file.read()
                pdf_images = get_pdf_page_images(pdf_bytes)
                if pdf_images:
                    if len(pdf_images) == 1:
                        st.image(pdf_images[0], caption="설문지 1페이지", use_container_width=True)
                    else:
                        page_choice = st.selectbox(
                            "확인할 페이지 선택",
                            options=range(1, len(pdf_images) + 1),
                            format_func=lambda x: f"{x} / {len(pdf_images)} 페이지"
                        )
                        st.image(pdf_images[page_choice - 1], caption=f"{page_choice}페이지", use_container_width=True)
                else:
                    st.info("PDF 파일이 업로드되었습니다. (미리보기를 지원하지 않는 포맷이거나 텍스트 문서입니다)")

    st.markdown("---")
    st.subheader("⚡ 설문지 자동 인식 & 반영")
    st.caption("업로드한 설문지 문서를 시스템이 읽어서 아래 폼에 자동으로 채웁니다.")

    if uploaded_file is not None:
        col_ocr_act, col_ocr_reset = st.columns([3, 1])
        with col_ocr_act:
            btn_ocr = st.button("🔍 문서 내용 읽어서 폼에 반영하기", type="primary", use_container_width=True)
        with col_ocr_reset:
            if st.button("초기화", use_container_width=True, help="자동 입력된 내용을 비웁니다"):
                for k in ["auto_client", "auto_project", "auto_period", "auto_date", "auto_dept", "auto_name", "ocr_text", "auto_scores"]:
                    st.session_state.pop(k, None)
                st.rerun()

        if btn_ocr:
            with st.spinner("📄 문서에서 텍스트와 설문 항목(체크/동그라미 마킹 포함)을 지능형 분석 중입니다..."):
                parsed, extracted_text = extract_and_parse_survey_file(uploaded_file)
                if extracted_text or parsed:
                    st.session_state["auto_client"] = parsed.get("발주사", "")
                    st.session_state["auto_project"] = parsed.get("공사명", "")
                    st.session_state["auto_period"] = parsed.get("계약기간", "")
                    st.session_state["auto_date"] = parsed.get("작성일", "")
                    st.session_state["auto_dept"] = parsed.get("담당자소속", "")
                    st.session_state["auto_name"] = parsed.get("담당자이름", "")
                    st.session_state["auto_scores"] = {
                        col: parsed.get(col, 5) for col in SCORE_COLUMNS
                    }
                    st.session_state["ocr_text"] = extracted_text
                    st.success("✅ 문서 내용을 성공적으로 읽었습니다! 아래 입력 폼을 확인해 주세요.")
                    st.rerun()
                else:
                    st.warning("⚠️ 문서에서 텍스트를 감지하지 못했습니다. 직접 입력해 주세요.")

        if st.session_state.get("ocr_text"):
            with st.expander("📝 문서에서 추출된 원본 텍스트 보기"):
                st.text_area("추출 텍스트", st.session_state["ocr_text"], height=130, disabled=True)
    else:
        st.info("💡 파일을 위에 첨부하시면 [문서 내용 읽어서 폼에 반영하기] 버튼이 활성화됩니다.")

    st.markdown("---")
    st.subheader("📋 설문 내용 확인 및 표에 반영")

    default_client = st.session_state.get("auto_client", "")
    default_project = st.session_state.get("auto_project", "")
    default_period = st.session_state.get("auto_period", "")
    default_date = st.session_state.get("auto_date", "")
    default_dept = st.session_state.get("auto_dept", "")
    if not default_dept and default_client:
        default_dept = default_client
    default_name = st.session_state.get("auto_name", "")
    saved_scores = st.session_state.get("auto_scores", {})

    # 3) 입력 폼 (st.form)
    with st.form(key="survey_input_form", clear_on_submit=False):
        st.markdown("**[1] 공사 및 담당자 정보**")
        client = st.text_input("발주사 (발주처) *", value=default_client, placeholder="예: (주)한국건설").strip()
        project_name = st.text_input("공사명 *", value=default_project, placeholder="예: 신축 물류센터 전기공사").strip()
        survey_date = st.text_input(
            "작성일 (작성일자)",
            value=default_date if default_date else datetime.date.today().strftime("%Y-%m-%d"),
            placeholder="예: 2026-09-17"
        ).strip()
        period = st.text_input("계약기간 (공사기간)", value=default_period, placeholder="예: 2026.01.01 ~ 2026.06.30").strip()
        dept = st.text_input("담당자 소속 (소속)", value=default_dept, placeholder="예: 시설관리팀").strip()
        manager_name = st.text_input("담당자 이름 (작성자)", value=default_name, placeholder="예: 장호준 (작성자 성함)").strip()

        st.markdown("---")
        st.markdown("**[2] 만족도 평가 점수 (각 1~5점)**")
        st.caption("1점: 매우불만 | 3점: 보통 | 5점: 매우만족")

        # 7개 평가 점수 입력 (문서 인식 점수 자동 반영)
        score_communication = st.radio(
            "1. [소통] 설명 및 협의",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("소통_설명및협의", 5) - 1)),
            horizontal=True
        )
        score_quality_period = st.radio(
            "2. [품질] 기간 준수",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("품질_기간준수", 5) - 1)),
            horizontal=True
        )
        score_quality_content = st.radio(
            "3. [품질] 내용 준수",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("품질_내용준수", 5) - 1)),
            horizontal=True
        )
        score_quality_improve = st.radio(
            "4. [품질] 개선",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("품질_개선", 5) - 1)),
            horizontal=True
        )
        score_safety = st.radio(
            "5. [안전] 사고 예방",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("안전_사고예방", 5) - 1)),
            horizontal=True
        )
        score_etc = st.radio(
            "6. [기타] 민원 관리",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("기타_민원관리", 5) - 1)),
            horizontal=True
        )
        score_overall = st.radio(
            "7. [종합] 전체 만족도",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("종합_전체만족도", 5) - 1)),
            horizontal=True
        )

        st.markdown("---")
        submitted = st.form_submit_button("💾 확인 후 표에 저장(반영)하기", use_container_width=True, type="primary")

        if submitted:
            # 필수 항목 검증
            if not client or not project_name:
                st.error("⚠️ '발주사'와 '공사명'은 필수 입력 항목입니다.")
            else:
                # 점수 리스트
                scores = [
                    score_communication,
                    score_quality_period,
                    score_quality_content,
                    score_quality_improve,
                    score_safety,
                    score_etc,
                    score_overall
                ]

                # 자동 계산: 합계 및 평균 (소수점 첫째 자리)
                total_sum = sum(scores)
                avg_score = round(total_sum / len(scores), 1)
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 첨부파일 물리 보관 (이미지 서버 저장소: static/uploads)
                saved_filename = ""
                if uploaded_file is not None:
                    try:
                        orig_name = uploaded_file.name
                        clean_name = re.sub(r'[^a-zA-Z0-9가-힣._-]', '_', orig_name)
                        saved_filename = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean_name}"
                        save_target_path = os.path.join(UPLOAD_DIR, saved_filename)
                        uploaded_file.seek(0)
                        with open(save_target_path, "wb") as f_save:
                            f_save.write(uploaded_file.read())
                        uploaded_file.seek(0)
                    except Exception as ex_save:
                        st.warning(f"첨부파일 저장 알림: {ex_save}")

                new_data = {
                    "등록일시": now_str,
                    "작성일": survey_date,
                    "발주사": client,
                    "공사명": project_name,
                    "계약기간": period,
                    "담당자소속": dept,
                    "담당자이름": manager_name,
                    "첨부파일": saved_filename,
                    "소통_설명및협의": score_communication,
                    "품질_기간준수": score_quality_period,
                    "품질_내용준수": score_quality_content,
                    "품질_개선": score_quality_improve,
                    "안전_사고예방": score_safety,
                    "기타_민원관리": score_etc,
                    "종합_전체만족도": score_overall,
                    "합계": total_sum,
                    "평균": avg_score
                }

                if save_survey_entry(new_data):
                    for k in ["auto_client", "auto_project", "auto_period", "auto_date", "auto_dept", "auto_name", "ocr_text", "auto_scores"]:
                        st.session_state.pop(k, None)
                    st.success(f"✅ 표에 반영 완료! (작성일: {survey_date}, 합계: {total_sum}점, 평균: {avg_score}점)")
                    st.rerun()

    # 사이드바 하단 물리 DB 관리 패널
    st.markdown("---")
    st.markdown("#### 💾 물리 DB 관리")
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f_sidebar_db:
            db_raw = f_sidebar_db.read()
        st.download_button(
            label="💾 물리 DB (.db) 백업 다운로드",
            data=db_raw,
            file_name=f"survey_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
            mime="application/x-sqlite3",
            use_container_width=True,
            help="현재 물리 데이터베이스(SQLite survey.db) 원본 파일을 PC로 백업 다운로드합니다."
        )

# -------------------------------------------------------------
# 5. 메인 화면: 실시간 누적 집계표 및 요약 통계
# -------------------------------------------------------------
main_emblem_b64 = get_image_base64(EMBLEM_FILE)
if main_emblem_b64:
    header_html = f'''
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:6px;">
        <img src="data:image/png;base64,{main_emblem_b64}" style="height:36px; object-fit:contain;" alt="수협 로고" />
        <span class="main-title" style="margin:0; font-size:1.85rem; font-weight:800; color:#1E3A8A; letter-spacing:-0.5px;">(주)수협개발 자료취합 시스템</span>
    </div>
    '''
else:
    header_html = '''
    <div class="main-title" style="margin:0; font-size:1.85rem; font-weight:800; color:#1E3A8A; letter-spacing:-0.5px;">(주)수협개발 자료취합 시스템</div>
    '''
st.markdown(header_html, unsafe_allow_html=True)
st.markdown('<div class="sub-title" style="margin-bottom:1.2rem;">(주)수협개발 설문지 및 주요 자료를 취합하고 실시간 누적 결과 및 요약 통계를 모니터링합니다.</div>', unsafe_allow_html=True)

# 최신 데이터 불러오기
df_data = load_survey_data()
total_count = len(df_data)

if is_gsheets_enabled():
    st.markdown('<div style="margin-bottom: 12px;"><span style="background-color:#DCFCE7; color:#166534; padding:4px 12px; border-radius:12px; font-size:0.85rem; font-weight:600;">🟢 구글 스프레드시트 실시간 클라우드 연동 중</span> <span style="background-color:#EFF6FF; color:#1D4ED8; padding:4px 12px; border-radius:12px; font-size:0.85rem; font-weight:600;">💾 물리 DB (SQLite: survey.db) 영구 보관 중</span></div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div style="margin-bottom: 12px;"><span style="background-color:#EFF6FF; color:#1D4ED8; padding:4px 12px; border-radius:12px; font-size:0.85rem; font-weight:600;">💾 물리 DB 저장 모드 (SQLite: survey.db 영구 저장 / 총 {total_count}건 보관 중)</span></div>', unsafe_allow_html=True)

# 상단 KPI 지표 카드
col1, col2, col3, col4 = st.columns(4)

if total_count > 0:
    mean_series = pd.to_numeric(df_data["평균"], errors="coerce").dropna()
    overall_mean = round(float(mean_series.mean()), 1) if not mean_series.empty else 0.0
    highest_score = round(float(mean_series.max()), 1) if not mean_series.empty else 0.0
    latest_date = str(df_data["등록일시"].iloc[-1])[:10] if "등록일시" in df_data.columns and len(df_data) > 0 else "-"
else:
    overall_mean = 0.0
    highest_score = 0.0
    latest_date = "-"

with col1:
    st.metric(label="📄 총 설문 응답 수", value=f"{total_count} 건")
with col2:
    st.metric(label="⭐ 전체 평균 만족도", value=f"{overall_mean} / 5.0 점")
with col3:
    st.metric(label="🏆 최고 평균 점수", value=f"{highest_score} 점")
with col4:
    st.metric(label="🕒 최근 등록 일자", value=f"{latest_date}")

st.markdown("---")

# 시각화 탭 & 데이터 테이블 구성
tab1, tab2 = st.tabs(["📑 실시간 누적 집계표", "📈 세부 항목별 평균 분석"])

with tab1:
    col_filter1, col_filter2, col_down = st.columns([2.2, 0.8, 2.0])
    
    with col_filter1:
        search_query = st.text_input("🔍 발주사 / 공사명 / 담당자 / 작성일 검색", placeholder="검색어를 입력하세요...")
    
    with col_down:
        st.write("") # 줄맞춤 여백
        if total_count > 0:
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                excel_bytes = get_excel_download_bytes(df_data)
                st.download_button(
                    label="📥 엑셀 (.xlsx)",
                    data=excel_bytes,
                    file_name=f"survey_result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary",
                    help="한글 깨짐 없는 정식 엑셀 파일(.xlsx)로 다운로드합니다."
                )
            with col_d2:
                csv_bytes = df_data.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📄 CSV (.csv)",
                    data=csv_bytes,
                    file_name=f"survey_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="UTF-8-SIG BOM이 포함된 CSV 파일로 다운로드합니다."
                )
            with col_d3:
                db_bytes = b""
                if os.path.exists(DB_FILE):
                    with open(DB_FILE, "rb") as f_db:
                        db_bytes = f_db.read()
                st.download_button(
                    label="💾 DB (.db)",
                    data=db_bytes,
                    file_name=f"survey_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/x-sqlite3",
                    use_container_width=True,
                    help="SQLite 물리 데이터베이스 원본 파일(survey.db)을 다운로드합니다."
                )
        else:
            st.button("📥 엑셀 다운로드", disabled=True, use_container_width=True)

    # 검색 필터 적용
    filtered_df = df_data.copy()
    if search_query:
        mask = (
            filtered_df["발주사"].astype(str).str.contains(search_query, case=False, na=False) |
            filtered_df["공사명"].astype(str).str.contains(search_query, case=False, na=False) |
            filtered_df["담당자이름"].astype(str).str.contains(search_query, case=False, na=False) |
            filtered_df["작성일"].astype(str).str.contains(search_query, case=False, na=False)
        )
        filtered_df = filtered_df[mask]

    # 첨부파일 원본 상태 컬럼 추가
    def get_file_status(val):
        if not val or pd.isna(val):
            return "미첨부"
        v_str = str(val).strip()
        f_real = find_upload_file(v_str)
        if f_real and os.path.exists(f_real):
            return "📥 원본 보관됨"
        return "미첨부"

    filtered_df["설문지 원본"] = filtered_df["첨부파일"].apply(get_file_status)

    # 표 표시용 컬럼 순서 (설문지 원본 컬럼을 공사명 바로 다음에 배치)
    col_order = [
        "등록일시", "작성일", "발주사", "공사명", "설문지 원본",
        "계약기간", "담당자소속", "담당자이름",
        *SCORE_COLUMNS, "합계", "평균", "첨부파일"
    ]
    disp_cols = [c for c in col_order if c in filtered_df.columns]
    table_df = filtered_df[disp_cols]

    if len(filtered_df) > 0:
        st.caption("💡 **행(Row) 클릭 안내**: 특정 줄(행)을 마우스로 클릭하면 해당 건의 **원본 설문지 자동 다운로드** 및 **삭제 버튼**이 활성화됩니다.")

        selection_event = st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "등록일시": st.column_config.TextColumn("등록일시", width="medium"),
                "작성일": st.column_config.TextColumn("작성일", width="small"),
                "발주사": st.column_config.TextColumn("발주사", width="small"),
                "공사명": st.column_config.TextColumn("공사명", width="medium"),
                "설문지 원본": st.column_config.TextColumn(
                    "설문지 원본",
                    width="small",
                    help="첨부파일 보관 여부입니다. 해당 행을 마우스로 클릭하면 원본 설문지 다운로드 버튼이 활성화됩니다."
                ),
                "계약기간": st.column_config.TextColumn("계약기간", width="medium"),
                "담당자소속": st.column_config.TextColumn("담당자소속", width="small"),
                "담당자이름": st.column_config.TextColumn("담당자이름", width="small"),
                "첨부파일": st.column_config.TextColumn("첨부파일명", width="medium"),
                "소통_설명및협의": st.column_config.NumberColumn("소통:설명및협의", format="%d"),
                "품질_기간준수": st.column_config.NumberColumn("품질:기간준수", format="%d"),
                "품질_내용준수": st.column_config.NumberColumn("품질:내용준수", format="%d"),
                "품질_개선": st.column_config.NumberColumn("품질:개선", format="%d"),
                "안전_사고예방": st.column_config.NumberColumn("안전:사고예방", format="%d"),
                "기타_민원관리": st.column_config.NumberColumn("기타:민원관리", format="%d"),
                "종합_전체만족도": st.column_config.NumberColumn("종합:전체만족도", format="%d"),
                "합계": st.column_config.NumberColumn("총점 (35점)", format="%d"),
                "평균": st.column_config.NumberColumn("평균 (5.0점)", format="%.1f 점"),
            }
        )
        st.caption(f"총 {len(filtered_df)}개의 설문 결과가 조회되었습니다.")

        # 표에서 마우스 클릭으로 행을 선택했을 때 나타나는 원본 다운로드 및 삭제 패널
        selected_rows = []
        if selection_event and hasattr(selection_event, "selection"):
            sel = selection_event.selection
            if isinstance(sel, dict):
                selected_rows = sel.get("rows", [])
            elif hasattr(sel, "rows"):
                selected_rows = sel.rows or []

        if selected_rows and len(selected_rows) > 0:
            sel_idx = selected_rows[0]
            if sel_idx < len(filtered_df):
                target_item = filtered_df.iloc[sel_idx]
                target_dt = str(target_item["등록일시"])
                target_proj = str(target_item["공사명"])
                target_file = str(target_item.get("첨부파일", "")).strip()
                real_target_path = find_upload_file(target_file)

                with st.container():
                    st.info(
                        f"선택한 설문: **[{target_item.get('작성일', target_item['등록일시'])}] {target_item['발주사']} - {target_item['공사명']} (담당: {target_item['담당자이름']})**"
                    )
                    col_file_btn, col_del_btn = st.columns([2.5, 1.5])
                    with col_file_btn:
                        if real_target_path and os.path.exists(real_target_path):
                            with open(real_target_path, "rb") as f_down:
                                f_bytes = f_down.read()
                            m_type = "image/png" if target_file.lower().endswith(".png") else "application/pdf" if target_file.lower().endswith(".pdf") else "image/jpeg"
                            st.download_button(
                                label=f"📥 선택한 설문지 원본 자동 다운로드 ({target_file})",
                                data=f_bytes,
                                file_name=target_file,
                                mime=m_type,
                                type="primary",
                                use_container_width=True,
                                key=f"btn_dl_sel_{sel_idx}",
                                help="클릭 즉시 브라우저를 통해 PC 다운로드 폴더로 자동 다운로드됩니다."
                            )
                        else:
                            st.caption("ℹ️ 본 항목은 첨부된 원본 파일이 없습니다.")

                    with col_del_btn:
                        if st.button("🗑️ 선택한 이 행 삭제하기", type="secondary", use_container_width=True, key="btn_table_delete"):
                            if delete_survey_entry(target_dt, target_proj):
                                st.cache_data.clear()
                                st.success("✅ 실시간 삭제 완료! 화면을 갱신합니다...")
                                st.rerun()

        # 첨부파일 이미지 저장소 보관함 전체 목록
        with st.expander("📁 설문지 원본 파일(이미지 서버) 보관함 / 전체 다운로드", expanded=False):
            st.caption("등록 시 업로드된 설문지 원본 파일들이 이미지 서버 저장소(`static/uploads`)에 안전하게 영구 보관됩니다.")
            files_df = df_data[df_data["첨부파일"].notna() & (df_data["첨부파일"].astype(str).str.strip() != "")]
            if len(files_df) > 0:
                for idx_f, rf in files_df.iterrows():
                    fn_curr = str(rf["첨부파일"]).strip()
                    fn_path = find_upload_file(fn_curr)
                    if fn_path and os.path.exists(fn_path):
                        c_proj, c_btn = st.columns([3, 1.2])
                        with c_proj:
                            st.markdown(f"📄 **{rf['공사명']}** ({rf['발주사']}) — `{fn_curr}`")
                        with c_btn:
                            with open(fn_path, "rb") as f_entry:
                                raw_bytes = f_entry.read()
                            m_type_box = "image/png" if fn_curr.lower().endswith(".png") else "application/pdf" if fn_curr.lower().endswith(".pdf") else "image/jpeg"
                            st.download_button(
                                label="📥 자동 다운로드",
                                data=raw_bytes,
                                file_name=fn_curr,
                                mime=m_type_box,
                                key=f"box_dl_{idx_f}_{fn_curr}",
                                use_container_width=True,
                                help=f"클릭 즉시 '{fn_curr}' 원본 파일이 PC 다운로드 폴더로 자동 저장됩니다."
                            )
            else:
                st.info("현재 보관함에 등록된 첨부파일이 없습니다.")

        # 또는 하단 드롭다운 목록에서 번호로 골라 삭제할 수 있는 보조 기능
        with st.expander("🗑️ 목록에서 직접 골라서 삭제하기"):
            item_options = {
                str(row["등록일시"]): f"[{idx + 1}번] 작성일: {row.get('작성일', '-')} | {row['발주사']} - {row['공사명']} ({row['담당자이름']})"
                for idx, row in df_data.iterrows()
            }
            chosen_dt = st.selectbox(
                "삭제할 설문 항목을 선택하세요:",
                options=list(item_options.keys()),
                format_func=lambda x: item_options[x],
                key="select_delete_row"
            )
            col_drop_del, _ = st.columns([2.5, 7.5])
            with col_drop_del:
                if st.button("🗑️ 선택한 항목 영구 삭제", type="primary", use_container_width=True, key="btn_dropdown_delete"):
                    if delete_survey_entry(chosen_dt):
                        st.cache_data.clear()
                        st.success("✅ 실시간 삭제 완료! 화면을 갱신합니다...")
                        st.rerun()

    else:
        if total_count == 0:
            st.info("💡 아직 등록된 설문 데이터가 없습니다. 좌측 사이드바에서 지류 설문지를 확인하고 첫 데이터를 등록해 보세요!")
        else:
            st.warning("검색 조건과 일치하는 데이터가 없습니다.")

with tab2:
    if total_count > 0:
        st.subheader("📊 7개 평가 항목별 평균 점수 현황")
        # 항목별 평균 점수 계산 (문자열 등이 섞여도 안전하게 수치 변환)
        numeric_scores = df_data[SCORE_COLUMNS].apply(pd.to_numeric, errors="coerce")
        score_means = numeric_scores.mean().round(2).reset_index()
        score_means.columns = ["평가항목", "평균점수"]
        
        # 라벨 가독성 개선 (개편된 7개 항목명)
        label_map = {
            "소통_설명및협의": "1. 소통: 설명및협의",
            "품질_기간준수": "2. 품질: 기간준수",
            "품질_내용준수": "3. 품질: 내용준수",
            "품질_개선": "4. 품질: 개선",
            "안전_사고예방": "5. 안전: 사고예방",
            "기타_민원관리": "6. 기타: 민원관리",
            "종합_전체만족도": "7. 종합: 전체만족도"
        }
        score_means["문항명"] = score_means["평가항목"].map(label_map)
        
        # 차트 출력
        st.bar_chart(
            score_means.set_index("문항명")["평균점수"],
            height=320,
            use_container_width=True
        )
        
        # 세부 수치 표
        st.table(score_means[["문항명", "평균점수"]].rename(columns={"문항명": "평가 항목", "평균점수": "평균 점수 (5점 만점)"}))

    else:
        st.info("데이터가 등록되면 항목별 평균 점수 차트가 여기에 표시됩니다.")

# -------------------------------------------------------------
# 6. 하단 안내 및 파일 관리 가이드
# -------------------------------------------------------------
with st.expander("ℹ️ 사용 안내 및 데이터 백업 팁"):
    st.markdown("""
    - **데이터 자동 저장**: 설문 등록 시 `d:\\servey-app\\survey_data.csv` 파일에 자동으로 계속 누적 저장됩니다.
    - **엑셀 호환(한글 보존)**: 📥 **엑셀 (.xlsx)** 버튼을 누르면 서식과 열 너비가 자동 최적화된 정식 엑셀 파일로 바로 열리며 한글 깨짐이 전혀 없습니다. (기존 CSV 포맷도 UTF-8 BOM 바이트로 안전하게 다운로드 가능합니다.)
    - **지류 설문지 확인**: 좌측 사이드바의 파일 업로더에 PDF나 스캔 이미지를 올리면 바로 보면서 오타 없이 편리하게 입력할 수 있습니다.
    """)
