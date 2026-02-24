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
        print("❌ ERROR: No se encontró GOOGLE_CREDS_JSON en las variables.")
        return None
    try:
        creds_dict = json.loads(creds_str)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"❌ ERROR: El formato de GOOGLE_CREDS_JSON es inválido: {e}")
        return None

CREDS_JSON = get_creds_path()
partidos_monitoreados = {}

# ============================================================
# FUNCIONES DE EXCEL Y GOOGLE SHEETS
# ============================================================

def preparar_excel():
    try:
        if not os.path.exists(EXCEL_PATH):
            df = pd.DataFrame(columns=['EQUIPO 1', 'EQUIPO 2', '1P 1', '1P 2', '2P 1', '2P 2', 'TOTAL', 'CUOTA AMBOS MARCAN 1 PARTE', 'AMBOS MARCAN'])
            df.to_excel(EXCEL_PATH, index=False)
            print(f"📁 Archivo Excel temporal creado.")
    except Exception as e:
        print(f"❌ Error al preparar Excel: {e}")

def guardar_en_gsheet(datos, ambos_1p, ambos_partido):
    try:
        if not CREDS_JSON or not GSHEET_ID:
            return
            
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GSHEET_ID).sheet1

        total_gol = f"{datos['g1p1'] + datos['g2p1']}-{datos['g1p2'] + datos['g2p2']}"
        nueva_fila = [datos['eq1'], datos['eq2'], datos['g1p1'], datos['g1p2'], datos['g2p1'], datos['g2p2'], total_gol, "", ""]
        sheet.append_row(nueva_fila)

        last_idx = len(sheet.get_all_values())
        color_v = {"red": 0.0, "green": 0.9, "blue": 0.0}
        color_r = {"red": 1.0, "green": 0.0, "blue": 0.0}
        
        sheet.format(f"H{last_idx}", {"backgroundColor": color_v if ambos_1p else color_r})
        sheet.format(f"I{last_idx}", {"backgroundColor": color_v if ambos_partido else color_r})
        print(f"📊 [GSHEETS] ✅ Subido: {datos['eq1']} vs {datos['eq2']}")
    except Exception as e:
        print(f"❌ [GSHEETS] Error al subir: {e}")

def guardar_resultado(p):
    try:
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active
        headers = {cell.value: i + 1 for i, cell in enumerate(ws[1])}
        row = ws.max_row + 1

        def limpiar_nombre(n):
            m = re.search(r'\((.*?)\)', n)
            return m.group(1).strip().upper() if m else n.strip().upper()

        eq1, eq2 = limpiar_nombre(p['eq1']), limpiar_nombre(p['eq2'])
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
        print(f"✅ EXCEL LOCAL: {eq1} vs {eq2} ({t1}-{t2})")
        
        datos_gs = p.copy()
        datos_gs.update({'eq1': eq1, 'eq2': eq2})
        guardar_en_gsheet(datos_gs, a1p, ap)
    except Exception as e:
        print(f"❌ Error guardando Excel: {e}")

# ============================================================
# NÚCLEO DEL BOT
# ============================================================

def ejecutar_bot():
    preparar_excel()
    
    # Ruta estándar de Ubuntu garantizada por aptPkgs
    chrome_path = "/usr/bin/chromium"
    
    if not os.path.exists(chrome_path):
        chrome_path = shutil.which("chromium")
        
    if not chrome_path:
        print("❌ ERROR CRÍTICO: No se encuentra Chromium en el sistema APT.")
        return

    print(f"🚀 Iniciando Bot. Navegador asegurado en: {chrome_path}")

    while True:
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

            # Inyección limpia del string
            driver = uc.Chrome(options=options, browser_executable_path=str(chrome_path))
            driver.get(URL)
            print("🌐 Bet365 cargada. Esperando sección Volta...")
            time.sleep(15)

            while True:
                try:
                    comps = driver.find_elements(By.CLASS_NAME, "ovm-Competition")
                    volta = next((c for c in comps if "Battle Volta" in c.text), None)
                    en_pantalla = set()

                    if volta:
                        fixtures = volta.find_elements(By.CLASS_NAME, "ovm-Fixture")
                        for fix in fixtures:
                            try:
                                names = fix.find_elements(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_TeamName")
                                if len(names) < 2: continue
                                
                                match_id = f"{names[0].text} vs {names[1].text}"
                                en_pantalla.add(match_id)

                                s1 = int(fix.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamOne").text)
                                s2 = int(fix.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamTwo").text)
                                timer = fix.find_element(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_Timer").text
                                
                                m_search = re.search(r'(\d{2}):(\d{2})', timer)
                                current_mins = int(m_search.group(1)) if m_search else 0

                                if match_id not in partidos_monitoreados:
                                    print(f"🆕 Partido detectado: {match_id}")
                                    partidos_monitoreados[match_id] = {
                                        "eq1": names[0].text, "eq2": names[1].text, "estado": "1P",
                                        "g1p1": 0, "g1p2": 0, "g2p1": 0, "g2p2": 0,
                                        "u_s1": s1, "u_s2": s2, "m_pre3": (s1, s2), "u_min": current_mins
                                    }

                                p = partidos_monitoreados[match_id]
                                p.update({"u_s1": s1, "u_s2": s2, "u_min": current_mins})
                                
                                if current_mins < 3: 
                                    p["m_pre3"] = (s1, s2)

                                if p["estado"] == "1P":
                                    if "Descanso" in timer or current_mins >= 3:
                                        g1, g2 = (s1, s2) if "Descanso" in timer else p["m_pre3"]
                                        p.update({"g1p1": g1, "g1p2": g2, "estado": "2P"})
                                        print(f"🌘 Media parte: {match_id} ({g1}-{g2})")

                                elif p["estado"] == "2P":
                                    if current_mins >= 6 or "Finalizado" in timer:
                                        p.update({
                                            "g2p1": s1 - p["g1p1"],
                                            "g2p2": s2 - p["g1p2"],
                                            "estado": "FIN"
                                        })
                                        guardar_resultado(p)
                            except: continue

                    # Eliminar y guardar los partidos que desaparecen de la pantalla
                    borrar = [m for m, p in partidos_monitoreados.items() if m not in en_pantalla and p["estado"] != "FIN"]
                    for m in borrar:
                        p = partidos_monitoreados[m]
                        if p["u_min"] >= 5:
                            p.update({"g2p1": p["u_s1"] - p["g1p1"], "g2p2": p["u_s2"] - p["g1p2"], "estado": "FIN"})
                            guardar_resultado(p)
                        del partidos_monitoreados[m]

                    time.sleep(10)
                except Exception:
                    driver.get(URL)
                    time.sleep(10)

        except Exception as e:
            print(f"❌ Sesión cerrada / Error en Selenium: {e}")
            if driver:
                try: driver.quit()
                except: pass
            time.sleep(20)

if __name__ == "__main__":
    ejecutar_bot()
