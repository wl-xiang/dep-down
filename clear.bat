@echo off
setlocal enabledelayedexpansion

set "clear_all=1"
set "clear_wheels="
set "clear_packages="
set "clear_node_modules="

:parse_args
if "%~1"=="" goto end_parse
if /i "%~1"=="/h" goto show_help
if /i "%~1"=="-h" goto show_help
if /i "%~1"=="--help" goto show_help
if /i "%~1"=="wheels" (
    set "clear_all="
    set "clear_wheels=1"
    shift
    goto parse_args
)
if /i "%~1"=="packages" (
    set "clear_all="
    set "clear_packages=1"
    shift
    goto parse_args
)
if /i "%~1"=="node_modules" (
    set "clear_all="
    set "clear_node_modules=1"
    shift
    goto parse_args
)
echo Error: Unknown argument: %~1
goto show_help

:end_parse

if defined clear_all (
    set "clear_wheels=1"
    set "clear_packages=1"
    set "clear_node_modules=1"
    set "clear_tarballs=1"
)

if defined clear_wheels (
    if exist .\wheels (
        rd /S /Q .\wheels
        mkdir .\wheels
        echo wheels directory cleared
    ) else (
        echo wheels directory does not exist, skipped
    )
)

if defined clear_packages (
    if exist .\packages (
        rd /S /Q .\packages
        mkdir .\packages
        echo packages directory cleared
    ) else (
        echo packages directory does not exist, skipped
    )
)

if defined clear_node_modules (
    if exist .\node_modules (
        rd /S /Q .\node_modules
        mkdir .\node_modules
        echo node_modules directory cleared
    ) else (
        echo node_modules directory does not exist, skipped
    )
)

if defined clear_tarballs (
    if exist .\tarballs (
        rd /S /Q .\tarballs
        mkdir .\tarballs
        echo tarballs directory cleared
    ) else (
        echo tarballs directory does not exist, skipped
    )
)

goto end

:show_help
echo Usage: %~nx0 [OPTIONS] [DIRECTORIES...]
echo.
echo Clear specified directories. If no directories are specified,
echo clears wheels, packages, and node_modules by default.
echo.
echo Options:
echo   -h, --help, /h    Show this help message
echo.
echo Available directories:
echo   wheels         Clear .\wheels
echo   packages       Clear .\packages
echo   node_modules   Clear .\node_modules
echo   tarballs       Clear .\tarballs
echo.
echo Examples:
echo   %~nx0                    ^& rem Clear all default directories
echo   %~nx0 wheels             ^& rem Clear only wheels
echo   %~nx0 packages node_modules  ^& rem Clear packages and node_modules

:end
endlocal
