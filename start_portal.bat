@echo off
cd /d "%~dp0"
if not exist web\dist\index.html (
  pushd web
  call npm run build
  popd
)
start "" http://localhost:8765
.venv\Scripts\python server.py
