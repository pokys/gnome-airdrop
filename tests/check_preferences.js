const NativeGLib = imports.gi.GLib;
const requests = [], savedFiles = [];
const settings = {download_dir:'/tmp/original',receiver_name:'My Laptop',duration_seconds:300};
const report = JSON.stringify({schema:1,application_version:'0.2.0',service:{state:'active'}});
const tick = async () => {for (let i=0;i<12;i++) await Promise.resolve();};
const check = (condition,message) => {if (!condition) throw new Error(message);};
class Widget {
    constructor(values={}) {Object.assign(this,values);this.children=[];this.handlers={};}
    add(child) {this.children.push(child);}
    add_suffix(child) {this.children.push(child);}
    connect(signal,fn) {this.handlers[signal]=fn;}
}
const Adw = {PreferencesPage:Widget,PreferencesGroup:Widget,ActionRow:Widget,EntryRow:Widget,ComboRow:Widget};
const GLib = {PRIORITY_DEFAULT:0,SOURCE_REMOVE:false,timeout_add_seconds:()=>1,source_remove(){}};
const Gio = {
    SubprocessFlags:{STDOUT_PIPE:1,STDERR_PIPE:2},
    FileCreateFlags:{PRIVATE:1},IOErrorEnum:{CANCELLED:1},
    Cancellable:class {cancel(){this.cancelled=true;}},
    File:{new_for_path:path=>({get_path:()=>path})},
    Subprocess:{new(argv) {
        requests.push(argv);
        return {force_exit(){},get_successful:()=>true,
            communicate_utf8_async(_input,_cancel,callback){Promise.resolve().then(()=>callback(this,null));},
            communicate_utf8_finish(){return [true,argv[1]==='status'
                ? JSON.stringify({state:'active',preferences:settings})
                : argv[1]==='diagnostics'?report:'',''];},
        };
    }},
};
const file = {get_path:()=>'/tmp/report.json',replace_contents(bytes,_etag,_backup,flags){
    check(flags===Gio.FileCreateFlags.PRIVATE,'Report must be a private file');
    savedFiles.push(new TextDecoder().decode(bytes));
}};
const Gtk = {Align:{CENTER:1},Button:Widget,StringList:{new:values=>values},DialogError:{DISMISSED:1},
    FileDialog:class extends Widget {
        select_folder(_window,_cancel,callback){Promise.resolve().then(()=>callback(this,null));}
        select_folder_finish(){return {get_path:()=>'/tmp/chosen'};}
        save(_window,_cancel,callback){Promise.resolve().then(()=>callback(this,null));}
        save_finish(){return file;}
    },
};
class ExtensionPreferences {}
const [,bytes]=NativeGLib.file_get_contents(imports.system.programPath.replace(/tests\/check_preferences.js$/,'extension/prefs.js'));
const source=imports.byteArray.toString(bytes).replace(/^import .*;\n/gm,'').replace('export default class','class');
const Preferences=new Function('Adw','Gio','GLib','Gtk','ExtensionPreferences',source+'\nreturn AirDropPreferences;')(
    Adw,Gio,GLib,Gtk,ExtensionPreferences);
const loop=new NativeGLib.MainLoop(null,false);
(async()=>{
    const window=new Widget();new Preferences().fillPreferencesWindow(window);
    await tick();
    const group=window.children[0].children[0];
    const [name,duration,folder,result]=group.children;
    check(name.text==='My Laptop' && duration.selected===1,'Saved name and duration must load');
    check(folder.subtitle==='/tmp/original','Destination must use preferences, not active-session folder');
    folder.children[0].handlers.clicked();await tick();
    check(!requests.some(args=>args[1]==='set-preferences'),'Folder chooser prepares a change without applying it');
    name.text='New Name';duration.selected=2;
    result.children[0].handlers.clicked();await tick();
    const command=requests.find(args=>args[1]==='set-preferences');
    const value=JSON.parse(command[2]);
    check(value.download_dir==='/tmp/chosen' && value.receiver_name==='New Name' && value.duration_seconds===600,
        'Save must send all preferences in one operation');
    check(!requests.some(args=>args.includes('start')||args.includes('stop')||args.includes('pkexec')),
        'Saving during reception must not restart service or request privilege');
    const diagnostic=window.children[0].children[1].children[0];
    diagnostic.children[0].handlers.clicked();await tick();
    check(savedFiles[0]===report && !savedFiles[0].includes('My Laptop'),'Export writes only allowlisted report');
    const secondWindow=new Widget();new Preferences().fillPreferencesWindow(secondWindow);
    secondWindow.handlers['close-request']();await tick();
    check(secondWindow.children[0].children[0].children[3].children[0].sensitive===false,
        'Closed preferences must ignore pending status replies');
    print('Preferences load, explicit save, active-session isolation, diagnostic export and close checks OK');
})().then(()=>loop.quit()).catch(error=>{printerr(error.stack);imports.system.exit(1);});
loop.run();
