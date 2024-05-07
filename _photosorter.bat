rem https://superuser.com/questions/1079403/how-to-run-multiple-commands-one-after-another-in-cmd/1079420

call activate_venv.bat
call python ./src/main.py
call echo " "
call echo Done
call echo " "
call cmd.exe
