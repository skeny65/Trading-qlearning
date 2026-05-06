@echo off
REM Create all necessary directories
mkdir "core" 2>nul
mkdir "manager" 2>nul
mkdir "strategies\pinescript" 2>nul
mkdir "data\qlearning" 2>nul
mkdir "data\trades\archive" 2>nul
mkdir "data\reports" 2>nul
mkdir "dashboard\output" 2>nul
mkdir "dashboard\history" 2>nul
mkdir "utils" 2>nul
mkdir "scripts" 2>nul
mkdir "docs" 2>nul
mkdir "tests\fixtures" 2>nul
mkdir "logs\dry_run" 2>nul
mkdir "signals" 2>nul

REM Create __init__.py files
type nul > "core\__init__.py"
type nul > "manager\__init__.py"
type nul > "strategies\__init__.py"
type nul > "utils\__init__.py"
type nul > "tests\__init__.py"

REM Create .gitkeep files
type nul > "data\qlearning\.gitkeep"
type nul > "data\trades\.gitkeep"
type nul > "data\reports\.gitkeep"
type nul > "dashboard\output\.gitkeep"
type nul > "dashboard\history\.gitkeep"
type nul > "logs\dry_run\.gitkeep"
type nul > "signals\.gitkeep"

echo Setup complete!
