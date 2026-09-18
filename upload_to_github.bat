@echo off
REM ============================================================
REM  Sector Rotation Screener -- GitHub upload helper
REM
REM  Yeh script poore project ko GitHub par push karta hai.
REM  Pehli baar chalane par repo URL maangega, uske baad yaad
REM  rakhega (git remote mein save ho jata hai).
REM
REM  Bas is file par DOUBLE-CLICK karo.
REM ============================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ========================================================
echo   Sector Rotation Screener - GitHub Upload
echo ========================================================
echo   Folder: %cd%
echo.

REM ---------- Step 0: Git installed hai ya nahi ----------
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git install nahi hai ya PATH mein nahi mila.
    echo         https://git-scm.com/download/win se install karo,
    echo         phir yeh file dobara chalao.
    echo.
    pause
    exit /b 1
)

REM ---------- Step 1: Git repo initialise ----------
if not exist ".git" (
    echo [1/6] Git repository initialise kar raha hoon...
    git init >nul
    if errorlevel 1 goto :fail
) else (
    echo [1/6] Git repository already maujood hai - skip.
)

REM ---------- Step 2: Branch ko main banao ----------
echo [2/6] Branch ko 'main' set kar raha hoon...
git branch -M main >nul 2>&1

REM ---------- Step 3: Remote (GitHub repo ka URL) ----------
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo.
    echo [3/6] GitHub repo ka URL chahiye.
    echo       Example: https://github.com/USERNAME/REPO-NAME.git
    echo       ^(angle brackets ^< ^> mat lagana^)
    echo.
    set /p REPO_URL="      Repo URL paste karo: "
    if "!REPO_URL!"=="" (
        echo [ERROR] Koi URL nahi diya gaya. Band kar raha hoon.
        echo.
        pause
        exit /b 1
    )
    git remote add origin "!REPO_URL!"
    if errorlevel 1 goto :fail
    echo       Remote set ho gaya.
) else (
    for /f "delims=" %%u in ('git remote get-url origin') do set EXISTING_URL=%%u
    echo [3/6] Remote already set hai: !EXISTING_URL!
)

REM ---------- Step 4: Files stage karo ----------
echo [4/6] Files add kar raha hoon...
git add -A
if errorlevel 1 goto :fail

REM ---------- Step 5: Commit ----------
echo.
set /p COMMIT_MSG="[5/6] Commit message (khaali chhodo to default lag jayega): "
if "!COMMIT_MSG!"=="" set COMMIT_MSG=Update sector rotation screener

git diff --cached --quiet
if not errorlevel 1 (
    echo       Koi naya change nahi mila - commit skip kar raha hoon.
) else (
    git commit -m "!COMMIT_MSG!"
    if errorlevel 1 goto :fail
)

REM ---------- Step 6: Push ----------
echo.
echo [6/6] GitHub par push kar raha hoon...
echo       ^(Pehli baar login maang sakta hai - browser khulega
echo        ya username + Personal Access Token maangega^)
echo.
git push -u origin main
if errorlevel 1 (
    echo.
    echo [ERROR] Push fail ho gaya. Common wajahein:
    echo   - Galat repo URL ya repo exist nahi karti
    echo   - GitHub login/token issue
    echo   - Remote par aisa commit hai jo local mein nahi
    echo     ^(us case mein chalao: git pull --rebase origin main^)
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   HO GAYA! Project GitHub par upload ho chuka hai.
echo.
echo   Agar Streamlit Cloud par deploy hai, woh 1-2 minute
echo   mein khud redeploy ho jayega.
echo ========================================================
echo.
pause
exit /b 0

:fail
echo.
echo [ERROR] Ek git command fail ho gayi. Upar ka message dekho.
echo.
pause
exit /b 1
