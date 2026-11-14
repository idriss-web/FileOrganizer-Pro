const {app,BrowserWindow,ipcMain,dialog,shell}=require('electron');
const {spawn}=require('child_process');const path=require('path');const fs=require('fs');
let win;const watchers=new Map();
const py=()=>{const p=path.join(__dirname,'venv','Scripts','python.exe');return fs.existsSync(p)?p:'python';};
function engine(payload,onEv){return new Promise(res=>{
  const c=spawn(py(),[path.join(__dirname,'engine','engine.py')],{windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8'}});
  let buf='',result=null;
  c.stdout.on('data',d=>{buf+=d;let i;while((i=buf.indexOf('\n'))>=0){const l=buf.slice(0,i);buf=buf.slice(i+1);
    try{const m=JSON.parse(l);(m.type==='result'||m.type==='error')?result=m:onEv&&onEv(m);}catch{}}});
  c.stderr.on('data',d=>{result=result||{type:'error',message:String(d)}});
  c.on('close',()=>res(result||{type:'error',message:'Engine stopped unexpectedly'}));
  c.stdin.end(JSON.stringify(payload));});}
app.whenReady().then(()=>{
  win=new BrowserWindow({width:1320,height:840,minWidth:1000,minHeight:640,backgroundColor:'#eef1f4',autoHideMenuBar:true,
    webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false}});
  win.loadFile('ui/index.html');
  ipcMain.handle('pick',async()=>{const r=await dialog.showOpenDialog(win,{properties:['openDirectory']});return r.canceled?null:r.filePaths[0];});
  ipcMain.handle('run',(e,p)=>engine(p,m=>win.webContents.send('ev',m)));
  ipcMain.handle('open',(e,p)=>shell.openPath(p));
  ipcMain.handle('show',(e,p)=>shell.showItemInFolder(p));
  ipcMain.handle('watch',(e,{on,payload})=>{
    const k=payload.source;watchers.get(k)?.w.close();watchers.delete(k);if(!on)return true;
    let t=null,busy=false;
    const w=fs.watch(k,{recursive:payload.recursive},()=>{clearTimeout(t);t=setTimeout(async()=>{if(busy)return;busy=true;
      const r=await engine({...payload,cmd:'apply'});busy=false;win.webContents.send('ev',{type:'watch',result:r});},4000);});
    watchers.set(k,{w});return true;});
});
app.on('window-all-closed',()=>app.quit());
