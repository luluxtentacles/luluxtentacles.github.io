@echo off
setlocal
title fix her git perms and identity

:: ---------------------------------------------------------------------------
:: One-time repair for C:\lulu\projects, 2026-09-21.
::
:: WHY: she runs as lulu-bot, but her repo is owned by Tentacles, so git refuses it
:: with "dubious ownership". She worked around it with safe.directory, which is
:: an EXEMPTION - it tells git to stop checking who owns the repo - and the
:: system gitconfig's own entries do not cover this path, because safe.directory
:: does not recurse. The root fix is for her tree to be owned by her, which is
:: what this does.
::
:: The second half pins her git identity and credential helper into HER global
:: config. An empty helper FIRST resets the inherited chain, so the machine-wide
:: Git Credential Manager (credential.helper = manager, installed by Git in
:: C:\Program Files\Git\etc\gitconfig) is never reached from one of her repos.
:: That helper is the one route by which a push could end up authenticating as
:: master - it opens an interactive sign-in and saves whatever account is used.
::
:: Reversible:  icacls C:\lulu\projects /setowner "KITSUNE\Kei" /T /C
:: Tentacles keeps full access either way - Administrators (F) and Authenticated
:: Users (M) are inherited ACLs and are not touched by an ownership change.
:: ---------------------------------------------------------------------------

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Not elevated - relaunching with a UAC prompt...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

set "HER=KITSUNE\lulu-bot"
set "TREE=C:\lulu\projects"
set "CFG=C:\Users\lulu-bot\.gitconfig"

echo.
echo ================ BEFORE ================
powershell -NoProfile -Command "foreach ($p in @('%TREE%','%TREE%\site','%TREE%\site\.git')) { '{0,-32} owner={1}' -f $p, (Get-Acl $p).Owner }"
echo.
echo --- her git config, before ---
git config --file "%CFG%" --list 2>nul | findstr /i "user\. credential\. safe\." || echo (nothing relevant set)
echo.

echo ================ OWNERSHIP ================
takeown /F "%TREE%" /R /D Y >nul 2>&1
icacls "%TREE%" /setowner "%HER%" /T /C >nul 2>&1
icacls "%TREE%" /grant "%HER%:(OI)(CI)M" /T /C >nul 2>&1
echo done - tree is hers now.

echo.
echo ================ HER GIT IDENTITY ================
:: The file lives in HER profile and this process is ELEVATED, so without the
:: ownership fix after it, the file is owned by Administrators and she may not be
:: able to read her own git config. That failure is silent and reads as "git has
:: no idea who I am", so it gets fixed here rather than hoped for.
if not exist "%CFG%" ( type nul > "%CFG%" )
git config --file "%CFG%" --unset-all credential.helper >nul 2>&1
git config --file "%CFG%" --add credential.helper ""
git config --file "%CFG%" --add credential.helper "store --file=C:/lulu/.git-credentials"
git config --file "%CFG%" user.name "Lulu"
git config --file "%CFG%" user.email "331892765+luluxtentacles@users.noreply.github.com"
icacls "%CFG%" /setowner "%HER%" >nul 2>&1
icacls "%CFG%" /grant "%HER%:F" >nul 2>&1
echo done - her account, her name, and GCM can no longer be reached.

echo.
echo ================ AFTER ================
powershell -NoProfile -Command "foreach ($p in @('%TREE%','%TREE%\site','%TREE%\site\.git')) { '{0,-32} owner={1}' -f $p, (Get-Acl $p).Owner }"
echo.
echo --- her git config, after ---
git config --file "%CFG%" --list 2>nul | findstr /i "user\. credential\. safe\." || echo (nothing relevant set)
echo --- that file must be OURS is wrong: it must be HERS ---
powershell -NoProfile -Command "'%CFG%  owner=' + (Get-Acl '%CFG%').Owner"
echo --- and it must be readable by her, not just by us ---
icacls "%CFG%" | findstr /i "lulu-bot"
echo.
echo --- looks wrong above? she needs lulu-bot against these paths, and NO bare '*' ---
icacls "%TREE%" | findstr /i "lulu-bot Tentacles"
echo.
echo Done. She can drop a safe.directory entry for %TREE%\site if she added one -
echo the ownership check passes on its own now.
echo.
pause
