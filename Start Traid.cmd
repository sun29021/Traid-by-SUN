@echo off
rem Double-click to start Traid. Close this window (or press Ctrl+C) to stop it.
title Traid - by Xavier Sun
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" %*
