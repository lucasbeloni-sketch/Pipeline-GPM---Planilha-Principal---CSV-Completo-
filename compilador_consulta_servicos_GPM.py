import os
import logging
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from common import load_service_account_credentials, execute_with_retries

# =========================
# CONFIG
# =========================
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

# IDs/nomes podem ser sobrescritos por variáveis de ambiente; os valores
# abaixo são os defaults de produção.
NEW_FOLDER_ID = os.getenv("CONSULTA_NEW_FOLDER_ID", "1QHtqMNCcIzNihwnu3copkNmBZnaL6Z6z")
OUTPUT_CSV_NAME = os.getenv("CONSULTA_OUTPUT_CSV_NAME", "BANCO.csv")
FOLDER_ID = os.getenv("CONSULTA_FOLDER_ID", "17IobcQeVLs83rUCqWKTi18yXiAPbupjf")
SPREADSHEET_ID = os.getenv("CONSULTA_SPREADSHEET_ID", "189JPWONK4hSpziocviwSQOtj59rWl9tbhkVvrxb6Lds")
SHEET_NAME = os.getenv("CONSULTA_SHEET_NAME", "BD_ConsultaServ")

UPLOAD_BANCO_PARA_DRIVE = os.getenv("UPLOAD_BANCO_PARA_DRIVE", "true").strip().lower() in {"1", "true", "yes"}

READ_CSV_KWARGS = dict(
    dtype=str,
    encoding="utf-8-sig",
    sep=None,
    engine="python"
)

# Nomes finais das colunas mantidas, na ordem.
TARGET_COLUMNS = [
    "centro_servico",
    "Nota",
    "cod_pep_obra",
    "equipe",
    "obs_servico",
    "dta_exec_srv",
    "total_servicos",
]

# Seleção por NOME de cabeçalho é o padrão (mais robusta a reordenação de
# colunas). Os cabeçalhos das CSVs de origem coincidem com TARGET_COLUMNS.
# Pode ser sobrescrita por env var; defina KEEP_COLS_BY_NAME="" (vazia) para
# cair no fallback por posição (KEEP_COL_POS_1BASED).
KEEP_COLS_BY_NAME = [
    n.strip()
    for n in os.getenv("KEEP_COLS_BY_NAME", ",".join(TARGET_COLUMNS)).split(",")
    if n.strip()
]

# Fallback por POSIÇÃO (1-based), usado quando KEEP_COLS_BY_NAME está vazia.
# As posições podem ser sobrescritas por env var e DEVEM mapear 1:1 em
# TARGET_COLUMNS.
KEEP_COL_POS_1BASED = [
    int(p.strip())
    for p in os.getenv("KEEP_COL_POS_1BASED", "47,6,27,50,52,68,70").split(",")
    if p.strip()
]

# =========================
# AUTH
# =========================
def get_drive_service():
    return build("drive", "v3", credentials=load_service_account_credentials(SCOPES))

def get_sheets_service():
    return build("sheets", "v4", credentials=load_service_account_credentials(SCOPES))

# =========================
# DRIVE HELPERS
# =========================
def list_files(service, folder_id, drive_id):
    query = f"'{folder_id}' in parents and trashed = false"
    files = []
    token = None

    while True:
        resp = execute_with_retries(
            service.files().list(
                q=query,
                pageToken=token,
                pageSize=1000,
                fields="nextPageToken, files(id,name,mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="drive",
                driveId=drive_id,
            ),
            description="listagem de arquivos no Drive",
        )

        files.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break

    return files

def download_file(service, file_id, filename):
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(filename, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk(num_retries=2)

def find_file_in_folder(service, folder_id, drive_id, filename):
    query = f"'{folder_id}' in parents and trashed = false and name = '{filename}'"

    resp = execute_with_retries(
        service.files().list(
            q=query,
            fields="files(id,name)",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="drive",
            driveId=drive_id,
        ),
        description=f"busca de arquivo existente '{filename}'",
    )

    files = resp.get("files", [])
    return files[0]["id"] if files else None

def upload_or_update_banco(drive_service, folder_id, drive_id, local_path, filename):
    media = MediaFileUpload(local_path, mimetype="text/csv", resumable=True)
    existing_id = find_file_in_folder(drive_service, folder_id, drive_id, filename)

    if existing_id:
        execute_with_retries(
            drive_service.files().update(
                fileId=existing_id,
                media_body=media,
                supportsAllDrives=True
            ),
            description=f"atualização do arquivo '{filename}'",
        )
        return "updated"

    execute_with_retries(
        drive_service.files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            supportsAllDrives=True
        ),
        description=f"criação do arquivo '{filename}'",
    )
    return "created"

# =========================
# DATA HELPERS
# =========================
def select_target_columns(df):
    """
    Seleciona e renomeia as colunas de interesse para TARGET_COLUMNS.

    Usa nomes de cabeçalho (KEEP_COLS_BY_NAME) quando configurado; caso
    contrário, seleciona por posição (KEEP_COL_POS_1BASED). Em ambos os modos
    valida a configuração e registra o mapeamento, para que mudanças na ordem
    das colunas de origem fiquem detectáveis no log.
    """
    if KEEP_COLS_BY_NAME:
        if len(KEEP_COLS_BY_NAME) != len(TARGET_COLUMNS):
            raise ValueError(
                f"KEEP_COLS_BY_NAME tem {len(KEEP_COLS_BY_NAME)} nome(s), "
                f"esperado {len(TARGET_COLUMNS)} (um por coluna de TARGET_COLUMNS)."
            )
        ausentes = [c for c in KEEP_COLS_BY_NAME if c not in df.columns]
        if ausentes:
            raise KeyError(
                f"Colunas não encontradas no CSV: {ausentes}. "
                f"Cabeçalhos disponíveis: {list(df.columns)}"
            )
        logging.info(f"Selecionando colunas por nome: {KEEP_COLS_BY_NAME} -> {TARGET_COLUMNS}")
        selecionado = df.loc[:, KEEP_COLS_BY_NAME].copy()
        selecionado.columns = TARGET_COLUMNS
        return selecionado

    if len(KEEP_COL_POS_1BASED) != len(TARGET_COLUMNS):
        raise ValueError(
            f"KEEP_COL_POS_1BASED tem {len(KEEP_COL_POS_1BASED)} posição(ões), "
            f"esperado {len(TARGET_COLUMNS)} (uma por coluna de TARGET_COLUMNS)."
        )
    fora = [p for p in KEEP_COL_POS_1BASED if p < 1 or p > df.shape[1]]
    if fora:
        raise IndexError(
            f"Posições fora do intervalo 1..{df.shape[1]}: {fora}. "
            f"O CSV consolidado tem {df.shape[1]} coluna(s)."
        )
    idx = [p - 1 for p in KEEP_COL_POS_1BASED]
    nomes_origem = [df.columns[i] for i in idx]
    # Loga o cabeçalho real em cada posição para detectar mudança de ordem.
    mapeamento = ", ".join(
        f"pos {p} ('{nome}') -> {alvo}"
        for p, nome, alvo in zip(KEEP_COL_POS_1BASED, nomes_origem, TARGET_COLUMNS)
    )
    logging.info(f"Selecionando colunas por posição: {mapeamento}")
    selecionado = df.iloc[:, idx].copy()
    selecionado.columns = TARGET_COLUMNS
    return selecionado

def to_number_ptbr(value):
    if value is None:
        return 0.0
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return 0.0
    s = s.replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0

# =========================
# DATA PARSER (POR ARQUIVO)
# =========================
DATE_REGEX = r"(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}|\d{4}[\/\-.]\d{1,2}[\/\-.]\d{1,2})"

def extrair_data_string(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()

    s = (
        s.str.replace("\u200b", "", regex=False)
         .str.replace("\xa0", " ", regex=False)
         .str.replace(r"\s+", " ", regex=True)
         .str.replace("None", "", regex=False)
         .str.replace("nan", "", regex=False)
    )

    extracted = s.str.extract(DATE_REGEX, expand=False)
    extracted = extracted.str.replace("-", "/", regex=False).str.replace(".", "/", regex=False)
    return extracted

def inferir_formato_por_arquivo(extracted_dates: pd.Series) -> str:
    """
    Retorna "DMY" ou "MDY" com base em datas não-ambíguas:
    - Se primeiro número > 12 => DMY
    - Se segundo número > 12 => MDY
    """
    parts = extracted_dates.dropna().str.split("/", expand=True)
    if parts.empty or parts.shape[1] < 3:
        return "DMY"  # padrão BR

    a = pd.to_numeric(parts[0], errors="coerce")
    b = pd.to_numeric(parts[1], errors="coerce")

    dmy_votes = ((a > 12) & (b <= 12)).sum()
    mdy_votes = ((b > 12) & (a <= 12)).sum()

    # Se não houver voto (só datas ambíguas), padrão BR
    if dmy_votes == 0 and mdy_votes == 0:
        return "DMY"

    return "DMY" if dmy_votes >= mdy_votes else "MDY"

def parse_date_por_arquivo(df: pd.DataFrame, col_data: str, col_arquivo: str) -> pd.Series:
    extracted = extrair_data_string(df[col_data])

    # normaliza ano com 2 dígitos (ex.: 01/02/24 -> 01/02/2024) se aparecer
    def normalizar_ano(x: str) -> str:
        if not isinstance(x, str) or x.strip() == "":
            return x
        p = x.split("/")
        if len(p) != 3:
            return x
        # yyyy/mm/dd já está ok
        if len(p[0]) == 4:
            return x
        # dd/mm/yy ou mm/dd/yy
        if len(p[2]) == 2:
            return f"{p[0]}/{p[1]}/20{p[2]}"
        return x

    extracted = extracted.apply(normalizar_ano)

    parsed_final = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

    for arquivo, idxs in df.groupby(col_arquivo).groups.items():
        ext_grp = extracted.loc[idxs]

        formato = inferir_formato_por_arquivo(ext_grp)

        # ISO (yyyy/mm/dd) sempre tenta primeiro
        iso_mask = ext_grp.str.match(r"^\d{4}/\d{1,2}/\d{1,2}$", na=False)
        if iso_mask.any():
            parsed_final.loc[iso_mask.index[iso_mask]] = pd.to_datetime(
                ext_grp.loc[iso_mask.index[iso_mask]],
                errors="coerce",
                format="%Y/%m/%d"
            )

        rest_idx = ext_grp.index[~iso_mask]
        if len(rest_idx) > 0:
            dayfirst = True if formato == "DMY" else False
            parsed_final.loc[rest_idx] = pd.to_datetime(
                ext_grp.loc[rest_idx],
                errors="coerce",
                dayfirst=dayfirst
            )

        amostras_validas = parsed_final.loc[idxs].notna().sum()
        logging.info(f"[DATA] arquivo_origem={arquivo} | formato_inferido={formato} | amostras_validas={amostras_validas}")

    return parsed_final

# =========================
# SHEETS HELPERS
# =========================
def clear_range(service, spreadsheet_id, range_):
    execute_with_retries(
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_
        ),
        description=f"limpeza do range {range_}",
    )

def upload_to_sheets(service, df):
    df_sheets = df.iloc[:, :7].copy()
    df_sheets = df_sheets.fillna("")
    values = df_sheets.values.tolist()

    clear_range(service, SPREADSHEET_ID, f"{SHEET_NAME}!A3:G")

    execute_with_retries(
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A3",
            valueInputOption="USER_ENTERED",
            body={"values": values}
        ),
        description=f"escrita dos dados em {SHEET_NAME}!A3",
    )

    timestamp = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")

    execute_with_retries(
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!B1",
            valueInputOption="USER_ENTERED",
            body={"values": [[timestamp]]}
        ),
        description=f"escrita do timestamp em {SHEET_NAME}!B1",
    )

# =========================
# MAIN
# =========================
def main():
    drive_service = get_drive_service()
    sheets_service = get_sheets_service()

    folder = execute_with_retries(
        drive_service.files().get(
            fileId=NEW_FOLDER_ID,
            fields="id,name,driveId",
            supportsAllDrives=True
        ),
        description="leitura de metadados da pasta de destino",
    )

    drive_id = folder["driveId"]
    logging.info(f"Pasta: {folder['name']}")

    files = list_files(drive_service, NEW_FOLDER_ID, drive_id)

    csv_files = [
        f for f in files
        if f["name"].lower().endswith(".csv")
        and f["name"] != OUTPUT_CSV_NAME
    ]

    logging.info(f"CSVs encontrados: {len(csv_files)}")

    dfs = []
    temp_files = []

    for f in csv_files:
        name = f["name"].replace("/", "_")
        download_file(drive_service, f["id"], name)
        temp_files.append(name)

        try:
            df = pd.read_csv(name, **READ_CSV_KWARGS)
            df["arquivo_origem"] = name
            dfs.append(df)
        except Exception as e:
            logging.error(f"Falha ao ler CSV {name}: {e}")

    for f in temp_files:
        try:
            os.remove(f)
        except OSError:
            pass

    if not dfs:
        logging.error("Nenhum CSV válido.")
        return

    banco_df = pd.concat(dfs, ignore_index=True).drop_duplicates()

    origem_col = banco_df["arquivo_origem"].copy()

    banco_df = select_target_columns(banco_df)

    banco_df["arquivo_origem"] = origem_col.values

    banco_df["cod_pep_obra"] = banco_df["cod_pep_obra"].fillna("").astype(str).str.upper()
    banco_df["total_servicos"] = banco_df["total_servicos"].apply(to_number_ptbr)

    # =========================
    # DATA ROBUSTA (POR ARQUIVO)
    # =========================
    banco_df["dta_exec_srv"] = parse_date_por_arquivo(banco_df, "dta_exec_srv", "arquivo_origem")

    total = len(banco_df)
    validas = banco_df["dta_exec_srv"].notna().sum()
    invalidas = total - validas
    logging.info(f"[DATA] Total: {total} | Válidas: {validas} | Inválidas: {invalidas}")

    banco_df = banco_df.sort_values(
        by="dta_exec_srv",
        ascending=True,
        kind="mergesort"
    ).reset_index(drop=True)

    # Formato BR garantido no CSV
    banco_df["dta_exec_srv"] = banco_df["dta_exec_srv"].dt.strftime("%d/%m/%Y")

    banco_df.to_csv(
        OUTPUT_CSV_NAME,
        index=False,
        encoding="utf-8-sig",
        sep=";",
        decimal=",",
        float_format="%.2f"
    )

    upload_to_sheets(sheets_service, banco_df)

    if UPLOAD_BANCO_PARA_DRIVE:
        action = upload_or_update_banco(
            drive_service,
            folder_id=FOLDER_ID,
            drive_id=drive_id,
            local_path=OUTPUT_CSV_NAME,
            filename=OUTPUT_CSV_NAME
        )
        logging.info(f"BANCO.csv enviado ao Drive ({action}).")

    logging.info("Processo finalizado com sucesso.")

if __name__ == "__main__":
    main()
