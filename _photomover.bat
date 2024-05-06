rem https://superuser.com/questions/1079403/how-to-run-multiple-commands-one-after-another-in-cmd/1079420

call activate_venv.bat
call python photo_mover_from_ready.py
call echo Done
call cmd.exe
