@echo OFF
echo Will activate the venv virtual environment
rem ERROR - "<python> was unexpected at this time.""

C:\Users\luxxa\_DEV\__VENV\photosorter\Scripts\activate
& if (photosorter.py) (echo Success) else (echo Error) &
deactivate &
echo Finished
