@echo off

set PGPASSWORD=AhNUUhSqVlWnxUqrTyezkmnPjZDHAKrI
set PGSSLMODE=require

"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" ^
-h crossover.proxy.rlwy.net ^
-U postgres ^
-p 56054 ^
-d railway ^
-F c ^
-f "C:\reneicloud\iCloudDrive\sistema\Backup_SGI\backup_sgi_%date:~6,4%-%date:~3,2%-%date:~0,2%.backup"

echo Backup enviado para iCloud com sucesso!
pause