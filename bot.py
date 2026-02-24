import os
import json
import tempfile
import time
import re
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
# CONFIGURACIÓN
# ============================================================
EXCEL_PATH = "/tmp/FIFA_VOLTA.xlsx"
URL = "https://www.bet365.es/#/IP/B1"
GSHEET_ID = os.environ.get("GSHEET_ID", "")

def get_creds_path():
    creds_str = os.environ.get("GOOGLE_CREDS_JSON", "")
    if not creds_str:
        print("⚠️ [CONFIG] GOOGLE_CREDS_JSON no detectada.")
        return None
    try:
        creds_dict = json.loads(creds_str)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"❌ [CONFIG] Error en JSON de credenciales: {e}")
        return None

CREDS_JSON = get_creds_path()
partidos_monitoreados = {}

def preparar_excel():
    if not os.path.exists(EXCEL_PATH):
        pd.DataFrame(columns=['EQUIPO 1', 'EQUIPO 2', '1P 1', '1P 2', '2P 1', '2P 2', 'TOTAL', 'AMBOS 1P', 'AMBOS FINAL']).to_excel(EXCEL_PATH, index=False)

# ============================================================
# LOGICA DE GOOGLE SHEETS
# ============================================================

def guardar_en_gsheet(datos, a1p, afinal):
    try:
        if not CREDS_JSON or not GSHEET_ID: return
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_JSON, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GSHEET_ID).sheet1
        
        total_str = f"{datos['g1p1']+datos['g2p1']}-{datos['g1p2']+datos['g2p2']}"
        fila = [datos['eq1'], datos['eq2'], datos['g1p1'], datos['g1p2'], datos['g2p1'], datos['g2p2'], total_str, "SI" if a1p else "NO", "SI" if afinal else "NO"]
        sheet.append_row(fila)
        
        # Colorear última fila
        idx = len(sheet.get_all_values())
        color_v = {"red": 0.0, "green": 0.8, "blue": 0.0}
        color_r = {"red": 0.8, "green": 0.0, "blue": 0.0}
        sheet.format(f"H{idx}", {"backgroundColor": color_v if a1p else color_r})
        sheet.format(f"I{idx}", {"backgroundColor": color_v if afinal else color_r})
    except Exception as e:
        print(f"⚠️ [GSHEETS] Error: {e}")

# ============================================================
# BOT PRINCIPAL
# ============================================================

def ejecutar_bot():
    preparar_excel()
    
    # BUSQUEDA ROBUSTA DEL BINARIO
    chrome_path = shutil.which("chromium") or shutil.which("google-chrome") or "/usr/bin/chromium"
    
    if not chrome_path or not os.path.exists(chrome_path):
        # Si sigue fallando, forzamos la ruta común en Nixpacks
        chrome_path = "/usr/bin/chromium"
    
    print(f"📍 [SISTEMA] Browser Path: {chrome_path}")

    while True:
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            # Solo intentamos arrancar si chrome_path es un string válido
            driver = uc.Chrome(options=options, browser_executable_path=str(chrome_path))
            driver.get(URL)
            time.sleep(15)

            while True:
                # Lógica de escaneo (Simplificada para estabilidad)
                try:
                    section = driver.find_elements(By.CLASS_NAME, "ovm-Competition")
                    volta = next((c for c in section if "Battle Volta" in c.text), None)
                    
                    if volta:
                        items = volta.find_elements(By.CLASS_NAME, "ovm-Fixture")
                        for item in items:
                            # Tu lógica de captura de goles aquí...
                            pass
                    
                    time.sleep(10)
                except Exception as e:
                    print(f"🔄 Refrescando... {e}")
                    driver.get(URL)
                    time.sleep(10)

        except Exception as e:
            print(f"❌ [CRÍTICO] {e}")
            if driver: driver.quit()
            time.sleep(30)

if __name__ == "__main__":
    ejecutar_bot()
