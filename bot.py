import os
import sys

# LOG INICIAL PARA RAILWAY
print("--- [SISTEMA] EL BOT ESTÁ ARRANCANDO ---")

try:
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
    print("✅ [SISTEMA] Importaciones completadas")
except Exception as e:
    print(f"❌ [ERROR] Fallo en importación: {e}")
    traceback.print_exc()
    sys.exit(1)

# ============================================================
# CONFIGURACIÓN
# ============================================================
print("--- [SISTEMA] Cargando configuración ---")
EXCEL_PATH = "/tmp/FIFA_VOLTA.xlsx"
URL = "https://www.bet365.es/#/IP/B1"
GSHEET_ID = os.environ.get("GSHEET_ID", "")

def get_creds_path():
    creds_str = os.environ.get("GOOGLE_CREDS_JSON", "")
    if not creds_str:
        print("⚠️ [SISTEMA] GOOGLE_CREDS_JSON no definido")
        return None
    try:
        creds_dict = json.loads(creds_str)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"❌ [ERROR] Credenciales inválidas: {e}")
        return None

CREDS_JSON = get_creds_path()
partidos_monitoreados = {}

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def preparar_excel():
    try:
        cols = ['EQUIPO 1', 'EQUIPO 2', '1P 1', '1P 2', '2P 1', '2P 2', 'TOTAL', 'CUOTA AMBOS MARCAN 1 PARTE', 'AMBOS MARCAN']
        if not os.path.exists(EXCEL_PATH):
            pd.DataFrame(columns=cols).to_excel(EXCEL_PATH, index=False)
        print("📁 [SISTEMA] Excel preparado")
    except Exception as e:
        print(f"⚠️ [ERROR] Excel local: {e}")

def guardar_en_gsheet(datos, a1p, ap):
    try:
        if not CREDS_JSON or not GSHEET_ID: return
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GSHEET_ID).sheet1
        
        fila = [datos['eq1'], datos['eq2'], datos['g1p1'], datos['g1p2'], datos['g2p1'], datos['g2p2'], 
                f"{datos['g1p1']+datos['g2p1']}-{datos['g1p2']+datos['g2p2']}", "", ""]
        sheet.append_row(fila)
        
        last = len(sheet.get_all_values())
        verde = {"red": 0.0, "green": 1.0, "blue": 0.0}
        rojo = {"red": 1.0, "green": 0.0, "blue": 0.0}
        sheet.format(f"H{last}", {"backgroundColor": verde if a1p else rojo})
        sheet.format(f"I{last}", {"backgroundColor": verde if ap else rojo})
        print(f"📊 [GS] Fila añadida: {datos['eq1']} vs {datos['eq2']}")
    except Exception as e:
        print(f"❌ [GS ERROR] {e}")

def guardar_resultado(p):
    try:
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active
        hd = {cell.value: i+1 for i, cell in enumerate(ws[1])}
        row = ws.max_row + 1
        
        def cl(n):
            m = re.search(r'\((.*?)\)', n)
            return m.group(1).strip().upper() if m else n.strip().upper()

        eq1, eq2 = cl(p['eq1']), cl(p['eq2'])
        ws.cell(row=row, column=hd['EQUIPO 1'], value=eq1)
        ws.cell(row=row, column=hd['EQUIPO 2'], value=eq2)
        ws.cell(row=row, column=hd['1P 1'], value=p['g1p1'])
        ws.cell(row=row, column=hd['1P 2'], value=p['g1p2'])
        ws.cell(row=row, column=hd['2P 1'], value=p['g2p1'])
        ws.cell(row=row, column=hd['2P 2'], value=p['g2p2'])
        
        t1, t2 = p['g1p1']+p['g2p1'], p['g1p2']+p['g2p2']
        ws.cell(row=row, column=hd['TOTAL'], value=f"{t1}-{t2}")
        
        a1p, ap = (p['g1p1']>0 and p['g1p2']>0), (t1>0 and t2>0)
        
        for col, ok in [('CUOTA AMBOS MARCAN 1 PARTE', a1p), ('AMBOS MARCAN', ap)]:
            cell = ws.cell(row=row, column=hd[col], value="")
            cell.fill = PatternFill(start_color="00FF00" if ok else "FF0000", fill_type="solid")
        
        wb.save(EXCEL_PATH)
        print(f"✅ [LOCAL] {eq1} vs {eq2} ({t1}-{t2})")
        
        datos_gs = p.copy()
        datos_gs.update({'eq1': eq1, 'eq2': eq2})
        guardar_en_gsheet(datos_gs, a1p, ap)
    except Exception as e:
        print(f"❌ [EXCEL ERROR] {e}")

# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def ejecutar_bot():
    preparar_excel()
    
    chrome_path = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("google-chrome")
    if not chrome_path:
        for p in glob.glob("/usr/bin/chrom*") + glob.glob("/nix/store/*/bin/chrom*"):
            chrome_path = p
            break
            
    if not chrome_path:
        print("❌ [SISTEMA] No se encontró Chromium. Terminando.")
        return

    print(f"🚀 [SISTEMA] Navegador: {chrome_path}")

    while True:
        driver = None
        try:
            print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Iniciando driver...")
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            # use_subprocess es opcional pero a veces ayuda en Linux
            driver = uc.Chrome(options=options, browser_executable_path=chrome_path)
            driver.get(URL)
            time.sleep(10)
            
            print(f"🌐 [WEB] {driver.title}")

            while True:
                try:
                    if URL not in driver.current_url:
                        driver.get(URL)
                        time.sleep(5)

                    comps = driver.find_elements(By.CLASS_NAME, "ovm-Competition")
                    volta = next((c for c in comps if "Battle Volta" in c.text), None)
                    en_pantalla = set()

                    if volta:
                        fixtures = volta.find_elements(By.CLASS_NAME, "ovm-Fixture")
                        for fix in fixtures:
                            try:
                                names = fix.find_elements(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_TeamName")
                                if len(names) < 2: continue
                                mid = f"{names[0].text} vs {names[1].text}"
                                en_pantalla.add(mid)

                                s1 = int(fix.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamOne").text)
                                s2 = int(fix.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamTwo").text)
                                timer = fix.find_element(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_Timer").text
                                
                                mt = re.search(r'(\d+):(\d+)', timer)
                                m = int(mt.group(1)) if mt else 0

                                if mid not in partidos_monitoreados:
                                    print(f"🆕 [{timer}] {mid}")
                                    partidos_monitoreados[mid] = {
                                        "eq1": names[0].text, "eq2": names[1].text, "estado": "1P",
                                        "g1p1": 0, "g1p2": 0, "g2p1": 0, "g2p2": 0,
                                        "u_s1": s1, "u_s2": s2, "m_pre3": (s1, s2), "u_min": m
                                    }

                                p = partidos_monitoreados[mid]
                                p.update({"u_s1": s1, "u_s2": s2, "u_min": m})
                                if m < 3: p["m_pre3"] = (s1, s2)

                                if p["estado"] == "1P" and ("Descanso" in timer or m >= 3):
                                    g1, g2 = (s1, s2) if "Descanso" in timer else p["m_pre3"]
                                    p.update({"g1p1": g1, "g1p2": g2, "estado": "2P"})
                                    print(f"🌘 HT: {mid} ({g1}-{g2})")
                                elif p["estado"] == "2P" and (m >= 6 or "Finalizado" in timer):
                                    p.update({"g2p1": s1 - p["g1p1"], "g2p2": s2 - p["g1p2"], "estado": "FIN"})
                                    guardar_resultado(p)
                            except: continue
                    else:
                        print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] Sin Volta visible")
                    
                    # Limpieza
                    borrar = [m for m, p in partidos_monitoreados.items() if m not in en_pantalla and p["estado"] != "FIN"]
                    for m in borrar:
                        p = partidos_monitoreados[m]
                        if p["u_min"] >= 5:
                            p.update({"g2p1": p["u_s1"] - p["g1p1"], "g2p2": p["u_s2"] - p["g1p2"], "estado": "FIN"})
                            guardar_resultado(p)
                        del partidos_monitoreados[m]

                    time.sleep(5)
                except Exception as e:
                    print(f"⚠️ [ERROR BUCLE] {e}")
                    time.sleep(5)
                    break

        except Exception as e:
            print(f"❌ [CRITICAL] {e}")
            traceback.print_exc()
            if driver:
                try: driver.quit()
                except: pass
            time.sleep(20)

if __name__ == "__main__":
    ejecutar_bot()
