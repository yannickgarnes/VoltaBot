import os
import json
import tempfile
import time
import re
import shutil
import glob
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
# CONFIGURACIÓN
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
# FUNCIONES DE EXCEL
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
            print(f"📁 Excel local creado en {EXCEL_PATH}")
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

def guardar_en_gsheet(datos_fila, ambos_1p, ambos_partido):
    try:
        if not CREDS_JSON or not GSHEET_ID:
            return
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GSHEET_ID).sheet1
        
        nueva_fila = [
            datos_fila['eq1'], datos_fila['eq2'],
            datos_fila['g1p1'], datos_fila['g1p2'],
            datos_fila['g2p1'], datos_fila['g2p2'],
            f"{datos_fila['g1p1']+datos_fila['g2p1']}-{datos_fila['g1p2']+datos_fila['g2p2']}",
            "", ""
        ]
        sheet.append_row(nueva_fila)
        last_row_idx = len(sheet.get_all_values())
        c_v = {"red": 0.0, "green": 1.0, "blue": 0.0}
        c_r = {"red": 1.0, "green": 0.0, "blue": 0.0}
        sheet.format(f"H{last_row_idx}", {"backgroundColor": c_v if ambos_1p else c_r})
        sheet.format(f"I{last_row_idx}", {"backgroundColor": c_v if ambos_partido else c_r})
        print(f"📊 [GSHEETS] Actualizado: {datos_fila['eq1']} vs {datos_fila['eq2']}")
    except Exception as e:
        print(f"❌ [GSHEETS] Error: {e}")

def guardar_resultado(datos):
    try:
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active
        headers = {cell.value: i+1 for i, cell in enumerate(ws[1])}
        row = ws.max_row + 1
        
        def clean(n):
            m = re.search(r'\((.*?)\)', n)
            return m.group(1).strip().upper() if m else n.strip().upper()

        eq1, eq2 = clean(datos['eq1']), clean(datos['eq2'])
        datos_l = datos.copy()
        datos_l.update({'eq1': eq1, 'eq2': eq2})

        ws.cell(row=row, column=headers['EQUIPO 1'], value=eq1)
        ws.cell(row=row, column=headers['EQUIPO 2'], value=eq2)
        ws.cell(row=row, column=headers['1P 1'], value=datos['g1p1'])
        ws.cell(row=row, column=headers['1P 2'], value=datos['g1p2'])
        ws.cell(row=row, column=headers['2P 1'], value=datos['g2p1'])
        ws.cell(row=row, column=headers['2P 2'], value=datos['g2p2'])
        
        t1, t2 = datos['g1p1'] + datos['g2p1'], datos['g1p2'] + datos['g2p2']
        ws.cell(row=row, column=headers['TOTAL'], value=f"{t1}-{t2}")
        
        a1p = datos['g1p1'] > 0 and datos['g1p2'] > 0
        ap = t1 > 0 and t2 > 0

        for col, ok in [('CUOTA AMBOS MARCAN 1 PARTE', a1p), ('AMBOS MARCAN', ap)]:
            cell = ws.cell(row=row, column=headers[col], value="")
            cell.fill = PatternFill(start_color="00FF00" if ok else "FF0000", fill_type="solid")
        
        wb.save(EXCEL_PATH)
        print(f"✅ EXCEL LOCAL OK: {eq1} vs {eq2} ({t1}-{t2})")
        guardar_en_gsheet(datos_l, a1p, ap)
    except Exception as e:
        print(f"❌ Error Guardando: {e}")

# ============================================================
# EJECUCIÓN
# ============================================================

def ejecutar_bot():
    preparar_excel()
    print("🚀 BOT VOLTA INICIADO EN RAILWAY - 24/7")
    
    chrome_path = os.environ.get("CHROMIUM_PATH")
    if not chrome_path:
        for b in ["chromium", "chromium-browser", "google-chrome"]:
            chrome_path = shutil.which(b)
            if chrome_path: break
    if not chrome_path:
        posibles = glob.glob("/usr/bin/chrom*") + glob.glob("/nix/store/*/bin/chrom*")
        if posibles: chrome_path = posibles[0]
    
    if not chrome_path:
        print("❌ ERROR: No se encuentra Chromium")
        return

    print(f"✅ Navegador: {chrome_path}")

    while True:
        driver = None
        try:
            print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Iniciando...")
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, browser_executable_path=chrome_path, use_subprocess=True)
            driver.get(URL)
            time.sleep(10)
            
            # Cookies
            try:
                driver.find_element(By.XPATH, "//div[contains(text(), 'Aceptar')]").click()
                time.sleep(2)
            except: pass

            fail_count = 0
            while True:
                try:
                    if URL not in driver.current_url:
                        driver.get(URL)
                        time.sleep(5)

                    comps = driver.find_elements(By.CLASS_NAME, "ovm-Competition")
                    volta = next((c for c in comps if "Battle Volta" in c.text), None)
                    en_pantalla = set()

                    if volta:
                        fail_count = 0
                        fixtures = volta.find_elements(By.CLASS_NAME, "ovm-Fixture")
                        for fix in fixtures:
                            try:
                                names = fix.find_elements(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_TeamName")
                                if len(names) < 2: continue
                                eq1, eq2 = names[0].text.strip(), names[1].text.strip()
                                mid = f"{eq1} vs {eq2}"
                                en_pantalla.add(mid)

                                s1 = int(fix.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamOne").text.strip())
                                s2 = int(fix.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamTwo").text.strip())
                                timer = fix.find_element(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_Timer").text.strip()
                                
                                m = re.search(r'(\d{2}):(\d{2})', timer)
                                mins = int(m.group(1)) if m else 0
                                secs = int(m.group(2)) if m else 0

                                if mid not in partidos_monitoreados:
                                    print(f"🆕 Detectado: {mid} ({timer})")
                                    partidos_monitoreados[mid] = {
                                        "eq1": eq1, "eq2": eq2, "estado": "1P",
                                        "g1p1": 0, "g1p2": 0, "g2p1": 0, "g2p2": 0,
                                        "u_s1": s1, "u_s2": s2, "m_pre3": (s1, s2), "u_min": mins
                                    }

                                p = partidos_monitoreados[mid]
                                p.update({"u_s1": s1, "u_s2": s2, "u_min": mins})
                                if mins < 3: p["m_pre3"] = (s1, s2)

                                if p["estado"] == "1P":
                                    if "Descanso" in timer or mins >= 3:
                                        g1, g2 = (s1, s2) if "Descanso" in timer else p["m_pre3"]
                                        p.update({"g1p1": g1, "g1p2": g2, "estado": "2P"})
                                        print(f"🌘 Media Parte: {mid} ({g1}-{g2})")

                                elif p["estado"] == "2P":
                                    if mins >= 6 or "Finalizado" in timer:
                                        p.update({
                                            "g2p1": s1 - p["g1p1"], "g2p2": s2 - p["g1p2"], "estado": "FIN"
                                        })
                                        guardar_resultado(p)
                            except: continue
                    else:
                        fail_count += 1
                        print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] Sin Volta ({fail_count}/10)")
                        if fail_count % 5 == 0:
                            print(f"   Dbg: {driver.title} | {len(comps)} secciones")
                            if comps:
                                top_names = [c.text.split('\n')[0] for c in comps[:3]]
                                print(f"   Top: {', '.join(top_names)}")
                        if fail_count > 10:
                            driver.execute_script("window.scrollBy(0, 500);")
                            if fail_count > 20: 
                                driver.get(URL)
                                time.sleep(10)
                            fail_count = 0
                    
                    borrar = []
                    for mid, p in partidos_monitoreados.items():
                        if mid not in en_pantalla and p["estado"] != "FIN":
                            if p["u_min"] >= 5:
                                p.update({"g2p1": p["u_s1"] - p["g1p1"], "g2p2": p["u_s2"] - p["g1p2"], "estado": "FIN"})
                                guardar_resultado(p)
                            borrar.append(mid)
                    for m in borrar:
                        if len(partidos_monitoreados) > 30: del partidos_monitoreados[m]

                    time.sleep(4)
                except Exception as e:
                    print(f"⚠️ Error: {e}")
                    time.sleep(5)

        except Exception as e:
            print(f"❌ CRASH: {e}")
            traceback.print_exc()
            if driver:
                try: driver.quit()
                except: pass
            time.sleep(15)

if __name__ == "__main__":
    ejecutar_bot()
