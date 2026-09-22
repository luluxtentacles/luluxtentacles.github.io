@echo off
REM Fold master's signed-in Chrome Canary logins into Lulu's jars.
REM
REM This is the button. It does the WHOLE jar process every time it is pressed -
REM master, 2026-09-23: "just do the whole jar process every time i press it dont
REM worry about diff." So it always rewrites her jars from the Canary profile,
REM changed or not, with --force.
REM
REM The profile is named RELATIVE to %LOCALAPPDATA% on purpose: that resolves to
REM whichever account runs this, so no account name is ever written down here.
REM
REM Master, 2026-09-23: "yeah it should always be profile 3." So the slot is NAMED
REM rather than guessed, with a fallback to whichever slot Chrome wrote most
REM recently if it ever moves - rather than failing quietly.
REM
REM Why this exists: her browser reads browser\*_jar.json at every launch, but the
REM jars only hold what was put in them. When a session ages out, master signs in
REM again on his own Canary and presses this, and her next browser launch carries it.
setlocal
set "HERE=%~dp0"
set "PROFILE=%LOCALAPPDATA%\Google\Chrome SxS\User Data\Profile 3"

echo.
echo   Lulu - loading your signed-in Canary logins
echo   ------------------------------------------
echo.

if not exist "%PROFILE%\Network\Cookies" (
    echo   Profile 3 has no cookies on disk - falling back to the slot Chrome
    echo   wrote most recently.
    echo.
    python "%HERE%grab_session.py" --profile "%PROFILE%\.." --newest --force
) else (
    python "%HERE%grab_session.py" --profile "%PROFILE%" --force
)
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo   Done. Her next browser launch carries these.
) else (
    echo   That did not finish cleanly ^(exit %RC%^). Read the lines above.
)
echo.
pause
exit /b %RC%
