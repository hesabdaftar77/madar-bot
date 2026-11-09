import datetime as _dt
def _j2g(jy,jm,jd):
    jy+=1595; days=-355668+(365*jy)+((jy//33)*8)+(((jy%33)+3)//4)+jd+((jm-1)*31 if jm<7 else ((jm-7)*30)+186)
    gy=400*(days//146097); days%=146097
    if days>36524:
        days-=1; gy+=100*(days//36524); days%=36524
        if days>=365: days+=1
    gy+=4*(days//1461); days%=1461
    if days>365: gy+=(days-1)//365; days=(days-1)%365
    gd=days+1
    sal=[0,31,29 if (gy%4==0 and gy%100!=0) or gy%400==0 else 28,31,30,31,30,31,31,30,31,30,31]
    gm=0
    while gm<13 and gd>sal[gm]: gd-=sal[gm]; gm+=1
    return gy,gm,gd
def _g2j(gy,gm,gd):
    g=[0,31,59,90,120,151,181,212,243,273,304,334]
    gy2=gy+1 if gm>2 else gy
    days=355666+(365*gy)+((gy2+3)//4)-((gy2+99)//100)+((gy2+399)//400)+gd+g[gm-1]
    jy=-1595+33*(days//12053); days%=12053
    jy+=4*(days//1461); days%=1461
    if days>365: jy+=(days-1)//365; days=(days-1)%365
    if days<186: jm=1+days//31; jd=1+days%31
    else: jm=7+(days-186)//30; jd=1+(days-186)%30
    return jy,jm,jd
class date:
    def __init__(s,y,m,d):
        if not(1<=m<=12) or d<1 or d>(31 if m<=6 else 30 if m<=11 else 30): raise ValueError
        if m==12 and d==30 and _g2j(*_j2g(y,12,30))!=(y,12,30): raise ValueError
        s.year,s.month,s.day=y,m,d
    @classmethod
    def fromgregorian(cls,date): 
        y,m,d=_g2j(date.year,date.month,date.day); return cls(y,m,d)
    def togregorian(s): return _dt.date(*_j2g(s.year,s.month,s.day))
