var messages = [];
var removed = [];
var applicationVersion = "6.7.5";
var knownWidgetTypes = __TYPES__;
var fakeForeignChange = false;
var fakeFailType = "";
var fakeNativeTrayConfig = null;
var trayConfigWrites = [];
// Synthetic model of delayed QML layout, separate from native validation.
var fakeDelayedOrder = false;
var fakeNativeEnumeration = false;
var indexWrites = [];
function readyOrder(panel) {
    panel.layoutReady = true;
    panel.layoutOrder = panel.items.map(item=>item.id).sort((a,b)=>a-b);
}
function print(text) {messages.push(text);}
function makeWidget(id,type,panel) {
    var widget = {id:id,type:type,owner:panel,values:{},currentConfigGroup:[],reloadConfig:function(){}};
    Object.defineProperty(widget,"index",{get:function(){
        if(this.owner.delayedIndex)return this.owner.layoutReady?this.owner.layoutOrder.indexOf(this.id):-1;
        return this.owner.items.indexOf(this);},
        set:function(value){
            indexWrites.push({id:this.id,index:value,ready:this.owner.layoutReady});
            if(this.owner.delayedIndex){
                if(!this.owner.layoutReady)return;
                var order=this.owner.layoutOrder;order.splice(order.indexOf(this.id),1);
                // Plasma setter removes first, then clamps to order.length()-1.
                order.splice(Math.min(Math.max(value,0),order.length-1),0,this.id);return;
            }
            var items=this.owner.items;items.splice(items.indexOf(this),1);items.splice(value,0,this);
        }});
    widget.readConfig=function(key,fallback){
        if(fakeNativeTrayConfig&&this.type==="org.kde.plasma.systemtray"&&this.currentConfigGroup.join("/")==="General"
                &&(key==="hiddenItems"||key==="shownItems"))return fakeNativeTrayConfig(key,fallback);
        var value=this.values[this.currentConfigGroup.join("/")+"/"+key];return value===undefined?fallback:value;};
    widget.writeConfig=function(key,value){
        if(this.type==="org.kde.plasma.systemtray")trayConfigWrites.push({key:key,value:value});
        this.values[this.currentConfigGroup.join("/")+"/"+key]=value;};
    return widget;
}
var nextId=100;
var allPanels=[];
function Panel(type) {
    this.delayedIndex=fakeDelayedOrder;this.layoutReady=!fakeDelayedOrder;this.layoutOrder=[];
    this.id=nextId++;this.type=type;this.screen=7;this.height=32;this.items=[];this.values={};this.currentConfigGroup=[];
    this.readConfig=function(key,fallback){var value=this.values[this.currentConfigGroup.join("/")+"/"+key];return value===undefined?fallback:value;};
    this.writeConfig=function(key,value){this.values[this.currentConfigGroup.join("/")+"/"+key]=value;};
    this.widgets=function(){var items=this.items.slice();return fakeNativeEnumeration&&this.delayedIndex?items.sort((a,b)=>a.id-b.id):items;};
    this.widgetById=function(id){return this.items.find(item=>item.id===id);};
    this.addWidget=function(value){
        if(value===fakeFailType)return null;
        var widget;
        if(typeof value==="string")widget=makeWidget(nextId++,value,this);
        else {widget=value;widget.owner.items.splice(widget.owner.items.indexOf(widget),1);widget.owner=this;}
        this.items.push(widget);
        if(fakeForeignChange&&widget.type==="org.kde.plasma.digitalclock")
            panelById(28).items.push(makeWidget(88,"foreign.widget",panelById(28)));
        return widget;
    };
    this.remove=function(){removed.push(this.id);allPanels.splice(allPanels.indexOf(this),1);};
    allPanels.push(this);
}
var original=new Panel("org.kde.panel");original.id=28;
original.items=[makeWidget(35,"org.orla.bar",original),makeWidget(7,"org.kde.plasma.systemtray",original)];
function panels(){return allPanels.slice();}
function desktops(){return [{screen:2},{screen:7}];}
function panelById(id){return allPanels.find(panel=>panel.id===id);}
function screenForConnector(connector){return connector==="DP-1"?7:-1;}
function screenGeometry(id){return {x:0,y:0,width:1600,height:900};}
