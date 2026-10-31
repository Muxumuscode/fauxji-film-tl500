@echo off
rem Starts Ghidra using the portable Java 25 kept in ghidra-install\jdk
set "JAVA_HOME=%~dp0ghidra-install\jdk\jdk-25.0.5+8"
set "PATH=%JAVA_HOME%\bin;%PATH%"
call "%~dp0ghidra-install\ghidra_12.2_PUBLIC\ghidraRun.bat"
