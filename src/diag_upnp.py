"""Diagnóstico UPnP: ¿siguen los mapeos 80/443 hacia este PC?"""
import miniupnpc

u = miniupnpc.UPnP()
u.discoverdelay = 2000
n = u.discover()
print("routers:", n)
u.selectigd()
try:
    print("external IP:", u.externalipaddress())
except Exception as e:
    print("external IP ERR:", e)
print("lanaddr:", u.lanaddr)
i = 0
while True:
    m = u.getgenericportmapping(i)
    if not m:
        break
    print(i, m)
    i += 1
    if i > 40:
        break
