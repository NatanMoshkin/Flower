Flower_PLC_HMI.sln
First was created to develop and test on Local PC, then on the temporary PLC.

167_01_Saad_PLC.sln
real CP6606 Panel
First stage to check and test with temporary IO.
- Communication with Robot will be TCP/IP. Tc2_TcpIp (ver. 3.4.5.0) will be used - installed on the CP6606 panel.
 - need to rewrite the code and test It with local (this) Eng. PC (simulated robot) connected to the CP6606.
- There are multiple Auto controls: FB_MasterAutoCycle and FB_PistonAutoCycle for each pistons. And Manual control option for each piston.
  - need to separate the controls:
	- MasterAutoCycle need to take over all PistonAutoCycle and take control on all Pistons.
	- need to be Global Auto/Manual control switch, that will put all the Pistons to Auto/Manual mode. So there 	will be no option to double control.
 - Panel GUI. I've created the VISU screens - the Panel screens. PistonsManual created. AutoMain still need to be coded.

* After all tests next stage will be to work with real IO on the field. 16 Digital In, 16 DO, TCP/IP to Robot.
* Future additions:
	- 3 Push buttons (with leds) to give the operator additional option to main controls without the GUI HMI.
	- extend TCP/IP communication to Robot to set main parameters, like speed, acc, dcc, timers.

