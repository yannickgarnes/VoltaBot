import os
import json
import tempfile
import time
import re
import shutil
import subprocess
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
        print("⚠️ [CONFIG] GOOGLE_CREDS_JSON no detectada en variables.")
        return None
    try:
        creds_dict = json.loads(creds_str)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"❌ [CONFIG] Error en JSON: {e}")
        return None

CREDS_JSON = get_creds_path()
partidos_monitoreados = {}

def preparar_excel():
    if not os.path.exists(EXCEL_PATH):
        pd.DataFrame(columns=['EQUIPO 1', 'EQUIPO 2', '1P 1', '1P 2', '2P 1', '2P 2', 'TOTAL', 'AMBOS 1P', 'AMBOS FINAL']).to_excel(EXCEL_PATH, index=False)

# ============================================================
# BOT PRINCIPAL
# ============================================================

def ejecutar_bot():
    preparar_excel()
    
    # 1. Intentar encontrar la ruta con 'which'
    chrome_path = shutil.which("chromium") or shutil.which("google-chrome")
    
    # 2. Si falla, intentar buscarlo en las rutas de Nix
    if not chrome_path:
        try:
            chrome_path = subprocess.check_output(['which', 'chromium']).decode('utf-8').strip()
        except:
            # Ruta forzada común en Nixpacks si está instalado
            for p in ["/usr/bin/chromium", "/usr/bin/google-chrome", "/nix/var/nix/profiles/default/bin/chromium"]:
                if os.path.exists(p):
                    chrome_path = p
                    break

    if not chrome_path:
        print("❌ ERROR FATAL: No se encuentra Chromium. Revisa el nixpacks.toml")
        return # Salimos para evitar el error de 'Must be a string'

    print(f"📍 [SISTEMA] Navegador detectado en: {chrome_path}")

    while True:
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            # Forzamos que sea un string
            driver = uc.Chrome(options=options, browser_executable_path=str(chrome_path))
            driver.get(URL)
            print("🌐 Bet365 cargada correctamente")
            
            # Aquí iría tu bucle de escaneo de fixtures...
            while True:
                time.sleep(60) # Mantener vivo
                
        except Exception as e:
            print(f"❌ [ERROR] {e}")
            if driver: driver.quit()
            time.sleep(20)

if __name__ == "__main__":
    ejecutar_bot()
