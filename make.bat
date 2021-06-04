@echo off

if [%1] == [] goto help

REM This allows us to expand variables at execution
setlocal ENABLEDELAYEDEXPANSION

goto %1

:reformat
isort --use-parentheses .
black .
exit /B %ERRORLEVEL%

:stylecheck
isort --check --profile black .
black --check .
exit /B %ERRORLEVEL%

:stylediff
isort --check --diff .
black --check --diff .
exit /B %ERRORLEVEL%

:help
echo Usage:
echo   make ^<command^>
echo.
echo Commands:
echo   reformat                   Reformat all .py files being tracked by git.
echo   stylecheck                 Check which tracked .py files need reformatting.
echo   stylediff                  Check which tracked .py files need reformatting and show the diff.
