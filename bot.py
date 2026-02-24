import os
import json
import tempfile
import time
import re
import traceback
import shutil
from datetime import datetime
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ============================================================
# CONFIGURACIÓN - Railway usa variables de entorno
# ============================================================
EXCEL_PATH = "/tmp/FIFA_VOLTA.xlsx"
URL = "https://www.bet365.es/#/IP/B1"
GSHEET_ID = os.environ.get("GSHEET_ID", "")

def get_creds_path():
    creds_str = os.environ.get("GOOGLE_CREDS_JSON", "")
    if not creds_str:
        print("❌ No se encontró GOOGLE_CREDS_JSON en variables de entorno")
        return None
    try:
        creds_dict = json.loads(creds_str)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"❌ Error procesando credenciales: {e}")
        return None

CREDS_JSON = get_creds_path()
partidos_monitoreados = {}

# ============================================================
# FUNCIONES DE EXCEL LOCAL
# ============================================================

def preparar_excel():
    try:
        expected = [
            'EQUIPO 1', 'EQUIPO 2', '1P 1', '1P 2', '2P 1', '2P 2', 'TOTAL',
            'CUOTA AMBOS MARCAN 1 PARTE', 'AMBOS MARCAN'
        ]
        if not os.path.exists(EXCEL_PATH):
            df = pd.DataFrame(columns=expected)
            df.to_excel(EXCEL_PATH, index=False)
            print(f"📁 Excel temporal creado en {EXCEL_PATH}")
        else:
            wb = openpyxl.load_workbook(EXCEL_PATH)
            ws = wb.active
            headers = [cell.value for cell in ws[1]]
            for col in expected:
                if col not in headers:
                    ws.cell(row=1, column=ws.max_column + 1, value=col)
            wb.save(EXCEL_PATH)
    except Exception as e:
        print(f"❌ Error Excel local: {e}")

# ============================================================
# GOOGLE SHEETS
# ============================================================

def guardar_en_gsheet(datos_fila, ambos_1p, ambos_partido):
    try:
        if not CREDS_JSON or not GSHEET_ID:
            return

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GSHEET_ID).sheet1

        eq1, eq2 = datos_fila['eq1'], datos_fila['eq2']
        g1p1, g1p2 = datos_fila['g1p1'], datos_fila['g1p2']
        g2p1, g2p2 = datos_fila['g2p1'], datos_fila['g2p2']
        total = f"{g1p1 + g2p1}-{g1p2 + g2p2}"

        nueva_fila = [eq1, eq2, g1p1, g1p2, g2p1, g2p2, total, "", ""]
        sheet.append_row(nueva_fila)

        last_row = len(sheet.get_all_values())
        color_v = {"red": 0.0, "green": 0.9, "blue": 0.0}
        color_r = {"red": 1.0, "green": 0.0, "blue": 0.0}

        sheet.format(f"H{last_row}", {"backgroundColor": color_v if ambos_1p else color_r})
        sheet.format(f"I{last_row}", {"backgroundColor": color_v if ambos_partido else color_r})
        print(f"📊 [GSHEETS] ✅ {eq1} vs {eq2} guardado.")

    except Exception as e:
        print(f"❌ [GSHEETS] Error: {e}")

def guardar_resultado(datos):
    try:
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active
        headers = {cell.value: i + 1 for i, cell in enumerate(ws[1])}
        row = ws.max_row + 1

        # Limpiar nombres (quitar paréntesis si existen)
        def limpiar(n):
            m = re.search(r'\((.*?)\)', n)
            return m.group(1).strip().upper() if m else n.strip().upper()

        eq1, eq2 = limpiar(datos['eq1']), limpiar(datos['eq2'])
        
        ws.cell(row=row, column=headers['EQUIPO 1'], value=eq1)
        ws.cell(row=row, column=headers['EQUIPO 2'], value=eq2)
        ws.cell(row=row, column=headers['1P 1'], value=datos['g1p1'])
        ws.cell(row=row, column=headers['1P 2'], value=datos['g1p2'])
        ws.cell(row=row, column=headers['2P 1'], value=datos['g2p1'])
        ws.cell(row=row, column=headers['2P 2'], value=datos['g2p2'])

        t1, t2 = datos['g1p1'] + datos['g2p1'], datos['g1p2'] + datos['g2p2']
        ws.cell(row=row, column=headers['TOTAL'], value=f"{t1}-{t2}")

        ambos_1p = datos['g1p1'] > 0 and datos['g1p2'] > 0
        ambos_p = t1 > 0 and t2 > 0

        for col, ok in [('CUOTA AMBOS MARCAN 1 PARTE', ambos_1p), ('AMBOS MARCAN', ambos_p)]:
            c = ws.cell(row=row, column=headers[col], value="")
            c.fill = PatternFill(start_color="00FF00" if ok else "FF0000", fill_type="solid")

        wb.save(EXCEL_PATH)
        print(f"✅ EXCEL: {eq1} vs {eq2} | {t1}-{t2}")
        
        datos_gs = datos.copy()
        datos_gs.update({'eq1': eq1, 'eq2': eq2})
        guardar_en_gsheet(datos_gs, ambos_1p, ambos_p)

    except Exception as e:
        print(f"❌ Error guardando: {e}")

# ============================================================
# EJECUCIÓN DEL BOT
# ============================================================

def ejecutar_bot():
    preparar_excel()
    
    # Lista de posibles rutas de Chromium en Railway/Nixpacks
    posibles_rutas = [
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
        "/nix/store/" # Rutas internas de Nix
    ]
    
    # Filtrar None y buscar la primera que exista
    chrome_path = next((ruta for ruta in posibles_rutas if ruta and os.path.exists(ruta)), None)
    
    if not chrome_path:
        print("❌ No se encontró el ejecutable de Chromium en ninguna ruta estándar.")
        # Intentar una búsqueda desesperada en el sistema
        print("🔍 Buscando Chromium manualmente...")
        for root, dirs, files in os.walk('/usr/bin'):
            if 'chromium' in files:
                chrome_path = os.path.join(root, 'chromium')
                break

    print(f"📍 Navegador encontrado en: {chrome_path}")

    while True:
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            # Pasamos la ruta encontrada
            driver = uc.Chrome(options=options, browser_executable_path=chrome_path)
            # ... resto del código
            driver.get(URL)
            time.sleep(15)

            while True:
                try:
                    comps = driver.find_elements(By.CLASS_NAME, "ovm-Competition")
                    volta = next((c for c in comps if "Battle Volta" in c.text), None)
                    
                    en_pantalla = set()
                    if volta:
                        fixtures = volta.find_elements(By.CLASS_NAME, "ovm-Fixture")
                        for f in fixtures:
                            try:
                                names = f.find_elements(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_TeamName")
                                if len(names) < 2: continue
                                
                                mid = f"{names[0].text} vs {names[1].text}"
                                en_pantalla.add(mid)

                                s1 = int(f.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamOne").text)
                                s2 = int(f.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamTwo").text)
                                timer = f.find_element(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_Timer").text
                                
                                m_match = re.search(r'(\d{2}):(\d{2})', timer)
                                mins = int(m_match.group(1)) if m_match else 0

                                if mid not in partidos_monitoreados:
                                    print(f"🆕 Partido: {mid}")
                                    partidos_monitoreados[mid] = {
                                        "eq1": names[0].text, "eq2": names[1].text,
                                        "estado": "1p", "g1p1": 0, "g1p2": 0, "g2p1": 0, "g2p2": 0,
                                        "u_s1": s1, "u_s2": s2, "m_pre3": (s1, s2), "u_min": mins
                                    }

                                p = partidos_monitoreados[mid]
                                p.update({"u_s1": s1, "u_s2": s2, "u_min": mins})
                                if mins < 3: p["m_pre3"] = (s1, s2)

                                if p["estado"] == "1p":
                                    if "Descanso" in timer or mins >= 3:
                                        g1, g2 = (s1, s2) if "Descanso" in timer else p["m_pre3"]
                                        p.update({"g1p1": g1, "g1p2": g2, "estado": "2p"})

                                elif p["estado"] == "2p":
                                    if mins >= 6 or "Finalizado" in timer:
                                        p.update({"g2p1": s1 - p["g1p1"], "g2p2": s2 - p["g1p2"], "estado": "fin"})
                                        guardar_resultado(p)
                            except: continue

                    # Limpieza de partidos que ya no están
                    desaparecidos = [m for m, p in partidos_monitoreados.items() if m not in en_pantalla and p["estado"] != "fin"]
                    for m in desaparecidos:
                        p = partidos_monitoreados[m]
                        if p["u_min"] >= 5:
                            p.update({"g2p1": p["u_s1"] - p["g1p1"], "g2p2": p["u_s2"] - p["g1p2"], "estado": "fin"})
                            guardar_resultado(p)
                        del partidos_monitoreados[m]

                    time.sleep(10)
                except:
                    driver.get(URL)
                    time.sleep(10)

        except Exception as e:
            print(f"❌ Error crítico: {e}")
            if driver: driver.quit()
            time.sleep(20)

if __name__ == "__main__":
    ejecutar_bot()
