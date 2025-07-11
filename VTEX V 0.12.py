import json, threading, requests, tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path
from unicodedata import normalize

ACCOUNT = "mundooutdoorar"
ENV     = "vtexcommercestable"
KEY     = "vtexappkey-mundooutdoorar-AEILPS"
TOK     = ("UIPFPODQNBQASXDRDQVHOZFUUDGZMSEFOOLHSHPZNRSWUJEHXVQARMFGABTLRMSR"
           "BOMWUJRSBDJIZHTYBLFFZPUSDGOTHTPWFCIXZHKZTCZYRGOGXBJYELWENYSDVSBE")
H = {"X-VTEX-API-AppKey": KEY, "X-VTEX-API-AppToken": TOK, "Accept": "application/json"}

READY_STATUS = {
    "ready-for-handling","start-handling","handling",
    "invoiced","invoice","on-order-completed","on-order-completed-ffm",
}

SEEN_FILE = Path("orders_seen.json")

def load_seen() -> set[str]:
    try: return set(json.loads(SEEN_FILE.read_text()))
    except: return set()
def save_seen(s:set[str]): SEEN_FILE.write_text(json.dumps(sorted(s)))

def _slug(t:str)->str:
    return normalize("NFKD",t).encode("ascii","ignore").decode().lower().strip().replace(" ","-")
def canonical_status(d:dict)->str:
    raw=d.get("status") or d.get("statusDescription") or ""
    s=_slug(raw)
    if "listo-para-preparacion" in s: return "ready-for-handling"
    if s=="facturado": return "invoiced"
    return s

_order_cache={}
def latest_orders(n=40):
    u=(f"https://{ACCOUNT}.{ENV}.com.br/api/oms/pvt/orders"
       f"?orderBy=creationDate,desc&page=1&per_page={n}")
    r=requests.get(u,headers=H,timeout=15)
    return r.json().get("list",[]) if r.status_code==200 else []
def order_detail(oid:str):
    if oid in _order_cache: return _order_cache[oid]
    r=requests.get(f"https://{ACCOUNT}.{ENV}.com.br/api/oms/pvt/orders/{oid}",
                   headers=H,timeout=15)
    _order_cache[oid]=r.json() if r.status_code==200 else {}
    return _order_cache[oid]

def fmt(ts:str):
    try: return datetime.fromisoformat(ts.replace("Z","+00:00")).strftime("%d/%m/%Y %H:%M")
    except: return ts

class Monitor:
    COLS=("orderId","fecha","status","cliente","total","itemId","qty")
    def __init__(self,ms=60000):
        self.ms=ms; self.cancelled=load_seen()
        self.tk=tk.Tk(); self.tk.title("VTEX – ventas"); self.tk.geometry("830x520")
        self._gui(); self._schedule()
        self.tk.protocol("WM_DELETE_WINDOW",self._close)
        self.tk.mainloop()
    def _gui(self):
        bar=ttk.Frame(self.tk,padding=4); bar.pack(fill="x")
        ttk.Button(bar,text="Cancelar orden",command=self._cancel).pack(side="left")
        self.tree=ttk.Treeview(self.tk,columns=self.COLS,show="headings")
        for c,w in zip(self.COLS,(150,130,130,160,80,100,60)):
            self.tree.heading(c,text=c); self.tree.column(c,width=w,anchor="w")
        self.tree.pack(fill=tk.BOTH,expand=True)
        vsb=ttk.Scrollbar(self.tk,orient="vertical",command=self.tree.yview)
        vsb.pack(side="right",fill="y"); self.tree.configure(yscroll=vsb.set)
        self.tree.tag_configure("ready",background="#ddffdd")
        self.tree.tag_configure("other",background="#ffdddd")
        self.tree.tag_configure("canceled",background="#d0d0d0",foreground="#808080")
    def _schedule(self):
        threading.Thread(target=self._poll,daemon=True).start()
        self.tk.after(self.ms,self._schedule)
    def _poll(self):
        try:
            for o in latest_orders():
                oid=o["orderId"]
                if oid in self.cancelled: continue
                try: det=order_detail(oid)
                except Exception as e:
                    self.tk.after(0,lambda err=e: messagebox.showwarning("Error",str(err))); continue
                st=canonical_status(det)
                tag="ready" if st in READY_STATUS else "other"
                client=det.get("clientProfileData",{}).get("firstName","")
                total=det.get("value",0)/100
                qty=sum(i["quantity"] for i in det.get("items",[]))
                item_id=det.get("items",[{}])[0].get("id","")
                self.tk.after(
                    0,
                    lambda v=(oid,fmt(det["creationDate"]),st,client,total,item_id,qty),t=tag:
                        self.tree.insert("",0,values=v,tags=(t,))
                )
                if tag=="ready":
                    self.tk.after(0,lambda o=oid: messagebox.showinfo(
                        "READY",f"LISTO PARA DISPARAR LOS MOVIMIENTOS\nOrden: {o}"))
        except Exception as e:
            self.tk.after(0,lambda err=e: messagebox.showwarning("Error",str(err)))
    def _cancel(self):
        sel=self.tree.selection()
        if not sel: messagebox.showinfo("Cancelar","Seleccione una fila"); return
        oid=self.tree.item(sel[0],"values")[0]
        if messagebox.askyesno("Confirmar",f"Marcar {oid} como cancelada?"):
            self.cancelled.add(oid); save_seen(self.cancelled)
            for i in sel: self.tree.item(i,tags=("canceled",))
    def _close(self):
        save_seen(self.cancelled); self.tk.destroy()

if __name__=="__main__":
    Monitor()
