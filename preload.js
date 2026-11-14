const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('api',{pick:()=>ipcRenderer.invoke('pick'),run:p=>ipcRenderer.invoke('run',p),
 open:p=>ipcRenderer.invoke('open',p),show:p=>ipcRenderer.invoke('show',p),watch:(on,payload)=>ipcRenderer.invoke('watch',{on,payload}),
 onEvent:cb=>ipcRenderer.on('ev',(e,m)=>cb(m))});
