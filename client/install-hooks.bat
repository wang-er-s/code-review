@echo off
REM Git Hook安装脚本 (Windows)
REM 将hooks目录中的hook脚本安装到.git/hooks目录

echo ========================================
echo Git Hook 安装脚本
echo ========================================
echo.

REM 检测.git目录（支持从hooks目录或项目根目录运行）
if exist "..\.git" (
    REM 在hooks目录下运行，项目根目录在上一级
    set REPO_ROOT=..
    set HOOKS_SOURCE_DIR=.
) else (
    echo [错误] 找不到.git目录
    echo 请确保在项目根目录或hooks目录下运行此脚本
    pause
    exit /b 1
)

echo [信息] 检测到Git仓库: %CD%
echo [信息] 项目根目录: %REPO_ROOT%
echo [信息] Hook源目录: %HOOKS_SOURCE_DIR%
echo.

REM 检查hook源文件
if not exist "%HOOKS_SOURCE_DIR%\hooks\pre-push" (
    if not exist "%HOOKS_SOURCE_DIR%\pre-push" (
        echo [错误] 找不到 hook 文件
        echo 请确保在hooks目录或项目根目录下运行此脚本
        pause
        exit /b 1
    )
)

REM 确定hook源路径
if exist "%HOOKS_SOURCE_DIR%\hooks\pre-push" (
    set HOOKS_SRC_DIR=%HOOKS_SOURCE_DIR%\hooks
) else (
    set HOOKS_SRC_DIR=%HOOKS_SOURCE_DIR%
)

REM 创建.git/hooks目录（如果不存在）
if not exist "%REPO_ROOT%\.git\hooks" mkdir "%REPO_ROOT%\.git\hooks"

REM 复制hook文件
echo [信息] 正在安装hook文件...
echo [信息] 从: %HOOKS_SRC_DIR%\pre-push
echo [信息] 到: %REPO_ROOT%\.git\hooks\pre-push
copy /Y "%HOOKS_SRC_DIR%\pre-push" "%REPO_ROOT%\.git\hooks\pre-push" >nul
if errorlevel 1 (
    echo [错误] 复制 pre-push 失败
    pause
    exit /b 1
)

copy /Y "%HOOKS_SRC_DIR%\post-push" "%REPO_ROOT%\.git\hooks\post-push" >nul
if errorlevel 1 (
    echo [错误] 复制 post-push 失败
    pause
    exit /b 1
)

echo [成功] Hook文件已安装到 %REPO_ROOT%\.git\hooks\
echo.

REM 检查配置文件（优先查找hooks/config，兼容其他位置）
if exist "%HOOKS_SOURCE_DIR%\config\config.yaml" (
    set CONFIG_DIR=%HOOKS_SOURCE_DIR%\config
) else if exist "%REPO_ROOT%\hooks\config\config.yaml" (
    set CONFIG_DIR=%REPO_ROOT%\hooks\config
) else if exist "%REPO_ROOT%\client\config\config.yaml" (
    set CONFIG_DIR=%REPO_ROOT%\client\config
) else if exist "%REPO_ROOT%\config\config.yaml" (
    set CONFIG_DIR=%REPO_ROOT%\config
) else (
    echo [警告] 配置文件不存在
    echo 请创建 hooks\config\config.yaml 并设置审查机器地址
    echo.
    goto :config_done
)

echo [信息] 配置文件已存在: %CONFIG_DIR%\config.yaml
echo 请确保配置了以下内容:
echo   client:
echo     review_machine_url: "http://审查机器IP:端口"
echo     review_branches: ["MergeBattle"]
echo.

:config_done

echo ========================================
echo 安装完成！
echo ========================================
echo.
echo 下一步:
echo 1. 检查 %CONFIG_DIR%\config.yaml 中的审查机器地址配置
echo 2. 确保已安装Python依赖: pip install -r hooks\requirements.txt
echo 3. 执行一次git push测试hook是否正常工作
echo.
pause

