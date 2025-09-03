import os
from config.settings import PROJECT_ROOT, ASSETS_DIR, APP_LOGO_PATH, COMPANY_LOGO_PATH, ICON_PATH
print("PROJECT_ROOT:", PROJECT_ROOT)
print("ASSETS_DIR:", ASSETS_DIR, "    exists?", os.path.exists(ASSETS_DIR))
print("APP_LOGO_PATH:", APP_LOGO_PATH, "    exists?", os.path.exists(APP_LOGO_PATH))
print("COMPANY_LOGO_PATH:", COMPANY_LOGO_PATH, "    exists?", os.path.exists(COMPANY_LOGO_PATH))
print("ICON_PATH:", ICON_PATH, "    exists?", os.path.exists(ICON_PATH))
