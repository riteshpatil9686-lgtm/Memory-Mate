import subprocess, sys, os
log = open("C:/Users/Ritesh/telegram-reminder-bot/bot.log", "w", 1)
proc = subprocess.Popen(
    ["C:/Users/Ritesh/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe", "-u", "C:/Users/Ritesh/telegram-reminder-bot/bot.py"],
    stdout=log, stderr=subprocess.STDOUT, text=True
)
with open("C:/Users/Ritesh/telegram-reminder-bot/bot.pid", "w") as f:
    f.write(str(proc.pid))
print("Started PID", proc.pid)
