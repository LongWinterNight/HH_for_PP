@echo off
rem ============================================================
rem BaseVacancy - run the site
rem ============================================================
rem Double-click this file to launch the app and open access
rem from the internet. While this window is open, the site works.
rem Close the window or shut down the PC - access is gone.
rem
rem Comments are in latin on purpose: cmd reads .bat in the console
rem codepage, and cyrillic here turns into garbage.
rem ============================================================

rem UTF-8 in the console, otherwise russian output looks broken.
chcp 65001 > nul

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\serve.ps1"

rem Keep the window open on failure so the error stays readable.
if errorlevel 1 pause
