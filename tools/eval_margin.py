#!/usr/bin/env python3
"""A negative result: does a score-margin gate work better than the score-band gate?

    python3 tools/eval_margin.py        # needs numpy, Pillow, scikit-learn

The idea: the ratio of the strongest competing peak to the best peak should not depend on how bright the object is, so a
threshold calibrated on the synthetic camera might generalise where the score band (tools/eval_confidence.py) does not.
It does not: real-photo backgrounds produce strong competing peaks, so almost every right answer is rejected.
Kept so the result can be reproduced. See docs/confidence-gate.md.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import eval_real_images as E

def smap(wts, frame):
    x=(np.clip(frame,0,255).astype(np.float32)/255.0)[None]
    x=np.maximum(E.conv(x,wts["cnn_w1"],wts["cnn_b1"],3),0)
    x=np.maximum(E.conv(x,wts["cnn_w2"],wts["cnn_b2"],3),0)
    return E.conv(x,wts["cnn_w3"],wts["cnn_b3"],1)[0]

def ratio(s):
    i=int(s.argmax()); y,x=divmod(i,28); best=s[y,x]
    m=s.copy(); m[max(0,y-3):y+4, max(0,x-3):x+4]=-1e9
    second=m.max()
    return (second/best if best>0 else 1.0), best, (x+2,y+2)

wts=E.load_weights()
rng=np.random.default_rng(3)
# synthetic calibration
rs=[]
for _ in range(3000):
    f=rng.integers(0,16,size=(E.W,E.W)).astype(np.float32); bx,by=rng.integers(4,28,size=2)
    f[by-2:by+3,bx-2:bx+3]=200
    r,b,(px,py)=ratio(smap(wts,f))
    if abs(px-bx)<=1 and abs(py-by)<=1: rs.append(r)
print("synthetic ratio: max %.3f p99 %.3f mean %.3f"%(max(rs),np.percentile(rs,99),np.mean(rs)))
tau=max(rs)*1.5
print("tau",tau)
rng=np.random.default_rng(5)
def run(level,size,cap,n=150):
    half=size//2; out=[]
    for _,im in E.photos():
        h,w=im.shape; im=im/im.max()*cap; x0=int(w*0.7)
        for _ in range(n):
            cx=rng.integers(x0,w-E.W); cy=rng.integers(0,h-E.W)
            f=im[cy:cy+E.W,cx:cx+E.W].copy(); bx,by=rng.integers(4,28,size=2)
            f[by-half:by+half+1,bx-half:bx+half+1]=level
            r,b,(px,py)=ratio(smap(wts,f))
            out.append((abs(px-bx)<=1 and abs(py-by)<=1, r))
    return out
print(f"{'level':>5} {'size':>4} {'cap':>4} {'acc':>5} {'right kept':>10} {'right drop':>10} {'wrong kept':>10} {'wrong drop':>10}")
for level in (150,200,250):
    for size in (3,5,7):
        for cap in (140,255):
            d=run(level,size,cap)
            ra=sum(1 for a,r in d if a and r<=tau); rr=sum(1 for a,r in d if a and r>tau)
            wa=sum(1 for a,r in d if not a and r<=tau); wr=sum(1 for a,r in d if not a and r>tau)
            print(f"{level:>5} {size:>4} {cap:>4} {sum(a for a,_ in d)/len(d):>5.2f} {ra:>10} {rr:>10} {wa:>10} {wr:>10}")
