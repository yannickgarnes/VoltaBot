import os
import json
import tempfile
import time
import re
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
# FUNCIONES DE EXCEL LOCAL (temporal en /tmp)
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
# GOOGLE SHEETS - Actualización en tiempo real
# ============================================================

def guardar_en_gsheet(datos_fila, ambos_1p, ambos_partido):
    try:
        if not CREDS_JSON or not GSHEET_ID:
            print("⚠️ Sin credenciales o GSHEET_ID, saltando Google Sheets")
            return

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GSHEET_ID).sheet1

        eq1 = datos_fila['eq1']
        eq2 = datos_fila['eq2']
        g1p1 = datos_fila['g1p1']
        g1p2 = datos_fila['g1p2']
        g2p1 = datos_fila['g2p1']
        g2p2 = datos_fila['g2p2']
        total = f"{g1p1 + g2p1}-{g1p2 + g2p2}"

        nueva_fila = [eq1, eq2, g1p1, g1p2, g2p1, g2p2, total, "", ""]
        sheet.append_row(nueva_fila)

        rows = sheet.get_all_values()
        last_row_idx = len(rows)

        color_verde = {"red": 0.0, "green": 0.9, "blue": 0.0}
        color_rojo  = {"red": 1.0, "green": 0.0, "blue": 0.0}

        sheet.format(f"H{last_row_idx}", {"backgroundColor": color_verde if ambos_1p else color_rojo})
        sheet.format(f"I{last_row_idx}", {"backgroundColor": color_verde if ambos_partido else color_rojo})

        print(f"📊 [GSHEETS] ✅ Actualizado: {eq1} vs {eq2} | 1ªP: {g1p1}-{g1p2} | Total: {total}")

    except Exception as e:
        print(f"❌ [GSHEETS] Error: {e}")

def guardar_resultado(datos):
    try:
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active
        headers = {cell.value: i + 1 for i, cell in enumerate(ws[1])}
        row = ws.max_row + 1

        m1 = re.search(r'\((.*?)\)', datos['eq1'])
        eq1 = m1.group(1).strip().upper() if m1 else datos['eq1'].strip().upper()
        m2 = re.search(r'\((.*?)\)', datos['eq2'])
        eq2 = m2.group(1).strip().upper() if m2 else datos['eq2'].strip().upper()

        datos_limpios = datos.copy()
        datos_limpios['eq1'] = eq1
        datos_limpios['eq2'] = eq2

        ws.cell(row=row, column=headers['EQUIPO 1'], value=eq1)
        ws.cell(row=row, column=headers['EQUIPO 2'], value=eq2)
        ws.cell(row=row, column=headers['1P 1'], value=datos['g1p1'])
        ws.cell(row=row, column=headers['1P 2'], value=datos['g1p2'])
        ws.cell(row=row, column=headers['2P 1'], value=datos['g2p1'])
        ws.cell(row=row, column=headers['2P 2'], value=datos['g2p2'])

        total_1 = datos['g1p1'] + datos['g2p1']
        total_2 = datos['g1p2'] + datos['g2p2']
        ws.cell(row=row, column=headers['TOTAL'], value=f"{total_1}-{total_2}")

        ambos_1p = datos['g1p1'] > 0 and datos['g1p2'] > 0
        ambos_partido = total_1 > 0 and total_2 > 0

        cell_h = ws.cell(row=row, column=headers['CUOTA AMBOS MARCAN 1 PARTE'], value="")
        cell_h.fill = PatternFill(start_color="00FF00" if ambos_1p else "FF0000", fill_type="solid")

        cell_i = ws.cell(row=row, column=headers['AMBOS MARCAN'], value="")
        cell_i.fill = PatternFill(start_color="00FF00" if ambos_partido else "FF0000", fill_type="solid")

        wb.save(EXCEL_PATH)
        print(f"✅ EXCEL OK: {eq1} vs {eq2} | Final: {total_1}-{total_2}")

        guardar_en_gsheet(datos_limpios, ambos_1p, ambos_partido)

    except Exception as e:
        print(f"❌ Error guardando resultado: {e}")

# ============================================================
# BUCLE PRINCIPAL
# ============================================================

def ejecutar_bot():
    preparar_excel()
    print("🚀 BOT VOLTA INICIADO EN RAILWAY")

    while True:
        driver = None
        try:
            options = uc.ChromeOptions()
            options.binary_location = "/usr/bin/chromium" # Indispensable para Railway
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")

            driver = uc.Chrome(options=options)
            wait = WebDriverWait(driver, 20)

            driver.get(URL)
            time.sleep(12)

            # Bucle de escaneo
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
                                
                                id_match = f"{names[0].text} vs {names[1].text}"
                                en_pantalla.add(id_match)

                                s1 = int(fixture.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamOne").text)
                                s2 = int(fixture.find_element(By.CLASS_NAME, "ovm-StandardScoresSoccer_TeamTwo").text)
                                timer_str = fixture.find_element(By.CLASS_NAME, "ovm-FixtureDetailsTwoWay_Timer").text
                                
                                t_match = re.search(r'(\d{2}):(\d{2})', timer_str)
                                minutos = int(t_match.group(1)) if t_match else 0
                                segundos = int(t_match.group(2)) if t_match else 0

                                if id_match not in partidos_monitoreados:
                                    print(f"🆕 Detectado: {id_match}")
                                    partidos_monitoreados[id_match] = {
                                        "eq1": names[0].text, "eq2": names[1].text,
                                        "estado": "jugando_1p", "g1p1": 0, "g1p2": 0,
                                        "g2p1": 0, "g2p2": 0, "ultimo_s1_visto": s1, 
                                        "ultimo_s2_visto": s2, "marcador_pre_3min": (s1, s2),
                                        "ultimo_min": minutos
                                    }

                                p = partidos_monitoreados[id_match]
                                p.update({"ultimo_s1_visto": s1, "ultimo_s2_visto": s2, "ultimo_min": minutos})

                                if minutos < 3: p["marcador_pre_3min"] = (s1, s2)

                                if p["estado"] == "jugando_1p":
                                    if "Descanso" in timer_str or (minutos == 3 and segundos <= 5):
                                        p.update({"g1p1": s1, "g1p2": s2, "estado": "jugando_2p"})
                                    elif minutos >= 3:
                                        g1, g2 = p["marcador_pre_3min"]
                                        p.update({"g1p1": g1, "g1p2": g2, "estado": "jugando_2p"})

                                elif p["estado"] == "jugando_2p":
                                    if minutos >= 6 or "Finalizado" in timer_str:
                                        p.update({"g2p1": s1 - p["g1p1"], "g2p2": s2 - p["g1p2"], "estado": "finalizado"})
                                        guardar_resultado(p)

                            except: continue

                    # Limpieza
                    borrar = [m for m, p in partidos_monitoreados.items() if m not in en_pantalla and p["estado"] != "finalizado"]
                    for m in borrar:
                        p = partidos_monitoreados[m]
                        if p["ultimo_min"] >= 5:
                            p.update({"g2p1": p["ultimo_s1_visto"] - p["g1p1"], "g2p2": p["ultimo_s2_visto"] - p["g1p2"], "estado": "finalizado"})
                            guardar_resultado(p)
                        del partidos_monitoreados[m]

                    time.sleep(5)

                except Exception as e_inner:
                    print(f"⚠️ Reintentando navegación...")
                    driver.get(URL)
                    time.sleep(5)

        except Exception as e_outer:
            print(f"❌ Error crítico: {e_outer}")
            if driver: driver.quit()
            time.sleep(20)

if __name__ == "__main__":
    ejecutar_bot()
