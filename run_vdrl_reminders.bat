@echo off

cd /d C:\VDRL_APP

C:\VDRL_APP\.venv\Scripts\python.exe ^
C:\VDRL_APP\manage.py ^
send_vdrl_reminders ^
>> C:\VDRL_APP\logs\vdrl_reminders.log 2>&1

C:\VDRL_APP\.venv\Scripts\python.exe ^
C:\VDRL_APP\manage.py ^
sync_vdrl_notifications ^
>> C:\VDRL_APP\logs\vdrl_reminders.log 2>&1