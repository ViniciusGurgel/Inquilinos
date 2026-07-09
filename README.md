# Inquilinos
Mateus

para executar em desenv:

uvicorn backend.main:app --reload

para atualizar ou criar um app:

python -m PyInstaller run_app.py --name InquilinosApp --onedir --add-data "templates;templates" --add-data "static;static" --add-data "backend;backend"
