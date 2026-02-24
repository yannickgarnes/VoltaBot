import os
import json
import tempfile
import time
import re
import shutil
import traceback
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
# CONFIGURACIÓN - Railway Variables de Entorno
# ============================================================
EXCEL_PATH = "/tmp/FIFA_VOLTA.xlsx"
URL = "https://www.bet365.es/#/IP/B1"
GSHEET_ID = os.environ.get("GSHEET_ID", "")

def get_creds_path():
    creds_str = os.environ.get("GOOGLE_CREDS_JSON", "")
    if not creds_str:
        print("❌ No se encontró GOOGLE_CREDS_JSON en las variables del servicio")
        return None
    try:
        creds_dict = json.loads(creds_str)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"❌ Error procesando JSON de credenciales: {e}")
        return None

CREDS_JSON = get_creds_path()
partidos_monitoreados = {}

# ============================================================
# EXCEL Y GOOGLE SHEETS
# ============================================================

def preparar_excel():
    try:
        if not os.path.exists(EXCEL_PATH):
            df = pd.DataFrame(columns=['EQUIPO 1', 'EQUIPO 2', '1P 1', '1P 2', '2P 1', '2P 2', 'TOTAL', 'CUOTA AMBOS MARCAN 1 PARTE', 'AMBOS MARCAN'])
            df.to_excel(EXCEL_PATH, index=False)
    except Exception as e:
        print(f"❌ Error Excel: {e}")

def guardar_en_gsheet(datos, ambos_1p, ambos_partido):
    try:
        if not CREDS_JSON or not GSHEET_ID: return
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GSHEET_ID).sheet1

        total = f"{datos['g1p1'] + datos['g2p1']}-{datos['g1p2'] + datos['g2p2']}"
        nueva_fila = [datos['eq1'], datos['eq2'], datos['g1p1'], datos['g1p2'], datos['g2p1'], datos['g2p2'], total, "", ""]
        sheet.append_row(nueva_fila)

        last_idx = len(sheet.get_all_values())
        color_v = {"red": 0.0, "green": 0.9, "blue": 0.0}
        color_r = {"red": 1.0, "green": 0.0, "blue": 0.0}
        sheet.format(f"H{last_idx}", {"backgroundColor": color_v if ambos_1p else color_r})
        sheet.format(f"I{last_idx}", {"backgroundColor": color_v if ambos_partido else color_r})
        print(f"📊 [GSHEETS] ✅ Sincronizado: {datos['eq1']} vs {datos['eq2']}")
    except Exception as e:
        print(f"❌ [GSHEETS] Error: {e}")

def guardar_resultado(p):
    try:
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active
        headers = {cell.value: i + 1 for i, cell in enumerate(ws[1])}
        row = ws.max_row + 1

        def limpiar(n):
            m = re.search(r'\((.*?)\)', n)
            return m.group(1).strip().upper() if m else n.strip().upper()

        eq1, eq2 = limpiar(p['eq1']), limpiar(p['eq2'])
        t1, t2 = p['g1p1'] + p['g2p1'], p['g1p2'] + p['g2p2']
        
        ws.cell(row=row, column=headers['EQUIPO 1'], value=eq1)
        ws.cell(row=row, column=headers['EQUIPO 2'], value=eq2)
        ws.cell(row=row, column=headers['1P 1'], value=p['g1p1'])
        ws.cell(row=row, column=headers['1P 2'], value=p['g1p2'])
        ws.cell(row=row, column=headers['2P 1'], value=p['g2p1'])
        ws.cell(row=row, column=headers['2P 2'], value=p['g2p2'])
        ws.cell(row=row, column=headers['TOTAL'], value=f"{t1}-{t2}")

        a1p = p['g1p1'] > 0 and p['g1p2'] > 0
        ap = t1 > 0 and t2 > 0

        for col, ok in [('CUOTA AMBOS MARCAN 1 PARTE', a1p), ('AMBOS MARCAN', ap)]:
            cell = ws.cell(row=row, column=headers[col], value="")
            cell.fill = PatternFill(start_color="00FF00" if ok else "FF0000", fill_type="solid")

        wb.save(EXCEL_PATH)
        print(f"✅ EXCEL: {eq1} vs {eq2} | Final: {t1}-{t2}")
        
        datos_gs = p.copy()
        datos_gs.update({'eq1': eq1, 'eq2': eq2})
        guardar_en_gsheet(datos_gs, a1p, ap)
    except Exception as e:
        print(f"❌ Error guardando: {e}")

# ============================================================
# BUCLE DEL BOT
# ============================================================

def ejecutar_bot():
    preparar_excel()
    # Recuperamos la ruta inyectada por el nixpacks.toml
    chrome_path = os.environ.get("CHROME_BIN") or shutil.which("chromium")
    print(f"🚀 BOT INICIADO. Navegador en: {chrome_path}")

    while True:
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")

            driver = uc.Chrome(options=options, browser_executable_path=chrome_path)
            driver.get(URL)
            time.sleep(15)

            while True:
                try:
                    comp_elements = driver.find_elements(By.CLASS_NAME, "ovm-Competition")
                    volta_section = next((c for c in comp_elements if "Battle Volta" in c.text), None)
                    en_pantalla = set()

                    if volta_section:
                        fixtures = volta_section.find_elements(By.CLASS_NAME, "ovm-Fixture")
                        for fixture in fixtures:
                            try:
                                names = fixture.find_elements(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_TeamName")
                                if len(names) < 2: continue
                                mid = f"{names[0].text} vs {names[1].text}"
                                en_pantalla.add(mid)

                                s1 = int(fixture.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamOne").text)
                                s2 = int(fixture.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamTwo").text)
                                timer_str = fixture.find_element(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_Timer").text
                                t_match = re.search(r'(\d{2}):(\d{2})', timer_str)
                                mins = int(t_match.group(1)) if t_match else 0

                                if mid not in partidos_monitoreados:
                                    print(f"🆕 Detectado: {mid}")
                                    partidos_monitoreados[mid] = {
                                        "eq1": names[0].text, "eq2": names[1].text, "estado": "1p",
                                        "g1p1": 0, "g1p2": 0, "g2p1": 0, "g2p2": 0,
                                        "u_s1": s1, "u_s2": s2, "m_pre3": (s1, s2), "u_min": mins
                                    }

                                p = partidos_monitoreados[mid]
                                p.update({"u_s1": s1, "u_s2": s2, "u_min": mins})
                                if mins < 3: p["m_pre3"] = (s1, s2)

                                if p["estado"] == "1p":
                                    if "Descanso" in timer_str or mins >= 3:
                                        g1, g2 = (s1, s2) if "Descanso" in timer_str else p["m_pre3"]
                                        p.update({"g1p1": g1, "g1p2": g2, "estado": "2p"})

                                elif p["estado"] == "2p":
                                    if mins >= 6 or "Finalizado" in timer_str:
                                        p.update({"g2p1": s1 - p["g1p1"], "g2p2": s2 - p["g1p2"], "estado": "finalizado"})
                                        guardar_resultado(p)
                            except: continue

                    # Rescate de partidos desaparecidos
                    borrar = [m for m, p in partidos_monitoreados.items() if m not in en_pantalla and p["estado"] != "finalizado"]
                    for m in borrar:
                        p = partidos_monitoreados[m]
                        if p["u_min"] >= 5:
                            p.update({"g2p1": p["u_s1"] - p["g1p1"], "g2p2": p["u_s2"] - p["g1p2"], "estado": "finalizado"})
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
