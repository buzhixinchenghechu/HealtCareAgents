@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   阿片类药物辅助决策系统 - 启动中...
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

echo [1/2] 安装/更新依赖...
pip install -r requirements.txt -q

echo [2/2] 启动 Streamlit...
echo.
echo 浏览器地址：http://localhost:8501
echo 按 Ctrl+C 停止服务
echo.

cd /d "%~dp0"
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false

pause

