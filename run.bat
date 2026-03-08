@echo off
chcp 65001 >nul
echo ============================================
echo   阿片类药物智能辅助系统 - 启动中...
echo ============================================
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

:: 安装依赖（首次运行）
echo [1/2] 安装/更新依赖包...
pip install streamlit>=1.35.0 openai>=1.30.0 -q

echo [2/2] 启动 Web 应用...
echo.
echo 浏览器将自动打开，也可手动访问：http://localhost:8501
echo 按 Ctrl+C 停止服务
echo.

cd /d D:\medical_ai_web
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false

pause
